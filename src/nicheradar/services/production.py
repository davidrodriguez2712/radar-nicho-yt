"""Manual production assumptions, immutable recipe versions, no purchases or publishing."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from nicheradar.domain.production import (
    FIT_WEIGHTS,
    STAGES,
    EstimateRange,
    FitAnchor,
    ProductionStage,
    Recipe,
    rubric_score,
)
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.integrations.contracts import Contract
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import ConflictError
from nicheradar.repositories.schema import opportunity_recipe_assignments as assignments
from nicheradar.repositories.schema import production_recipe_defaults as defaults_table
from nicheradar.services.scenarios import Proposal, Scenario, SharedTool, simulate

# Owner-declared standing assumption, not a fabricated business metric: a weekly cadence.
DEFAULT_VIDEOS_PER_MONTH = 4
# The radar's own discovery/scoring cost is tracked at the profile/budget level, not
# duplicated here; declared zero rather than left unknown, per production stage costs.
DEFAULT_RADAR_MONTHLY_USD = EstimateRange(low=Decimal(0), high=Decimal(0))


class ProductionPlan(Contract):
    recipe: Recipe
    tools: tuple[SharedTool, ...] = ()
    videos_per_month: int = Field(gt=0, le=10000)
    radar_monthly_usd: EstimateRange | None = None
    reserve_usd: Decimal = Field(default=Decimal(0), ge=0)


def evaluate_plan(plan: ProductionPlan, profile: CreatorProfile) -> dict[str, Any]:
    resources = simulate(
        Scenario(
            name="Production recipe estimate",
            proposals=(
                Proposal(
                    channel_key="planned-channel",
                    opportunity_keys=(),
                    recipe=plan.recipe,
                    videos_per_month=plan.videos_per_month,
                ),
            ),
            tools=plan.tools,
            radar_monthly_usd=plan.radar_monthly_usd,
            reserve_usd=plan.reserve_usd,
        ),
        profile,
    )
    recipe = plan.recipe
    unknown = list(resources.unknown)
    if not recipe.audience_key or not recipe.audience_key.strip():
        unknown.append("audience")
    unknown.extend(f"anchor:{name}" for name in FIT_WEIGHTS if name not in recipe.anchors)
    for stage in recipe.stages:
        if stage.automation == "unknown":
            unknown.append(f"{stage.name}:automation")
        if stage.automation in {"ai", "semi"} and not stage.tool_key:
            unknown.append(f"{stage.name}:tool")
    if set(stage.name for stage in recipe.stages) != set(STAGES):
        unknown.append("incomplete_stages")
    score = rubric_score(recipe) if not unknown else None
    reviews = {
        name: getattr(recipe, name)
        for name in ("rights_review", "originality_review", "repetition_review")
    }
    return {
        "rubric_version": "creator-fit-v2",
        "recipe_key": recipe.key,
        "recipe_version": recipe.version,
        "score": str(score) if score is not None else None,
        "status": "estimated" if score is not None else "incomplete",
        "resources": resources.model_dump(mode="json"),
        "unknown": sorted(set(unknown)),
        "reviews": reviews,
        "anchors": {key: value.model_dump(mode="json") for key, value in recipe.anchors.items()},
        "videos_per_month": plan.videos_per_month,
        "rework_margin": str(recipe.rework_margin),
        "plan": plan.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "limitations": [
            "Manual estimates, not a tested production workflow.",
            "Fit does not override resource limits or certify monetization or rights.",
            "Standalone channel estimate; use a combined scenario "
            "for shared capacity across channels.",
        ],
    }


def latest_plan(
    connection: Connection, opportunity_id: UUID, profile_id: UUID
) -> dict[str, Any] | None:
    row = (
        connection.execute(
            select(assignments, s.production_recipes.c.configuration)
            .join(s.production_recipes, s.production_recipes.c.id == assignments.c.recipe_id)
            .where(
                assignments.c.opportunity_id == opportunity_id,
                assignments.c.profile_id == profile_id,
            )
            .order_by(assignments.c.version.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def save_plan(
    connection: Connection,
    opportunity_id: UUID,
    profile_id: UUID,
    plan: ProductionPlan,
    expected_version: int,
    now: datetime,
) -> dict[str, Any]:
    opportunity = (
        connection.execute(
            select(s.opportunities).where(s.opportunities.c.id == opportunity_id).with_for_update()
        )
        .mappings()
        .one()
    )
    if (
        plan.recipe.language != opportunity["language"]
        or plan.recipe.format != opportunity["format"]
        or (
            plan.recipe.audience_key is not None
            and plan.recipe.audience_key != opportunity["audience_key"]
        )
    ):
        raise ValueError("recipe audience or format does not match opportunity")
    previous = latest_plan(connection, opportunity_id, profile_id)
    version = previous["version"] if previous else 0
    if expected_version != version:
        raise ConflictError("recipe assignment changed")
    configuration = plan.model_dump(mode="json")
    connection.execute(
        insert(s.production_recipes)
        .values(
            recipe_key=plan.recipe.key,
            version=plan.recipe.version,
            configuration=configuration,
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    stored = (
        connection.execute(
            select(s.production_recipes).where(
                s.production_recipes.c.recipe_key == plan.recipe.key,
                s.production_recipes.c.version == plan.recipe.version,
            )
        )
        .mappings()
        .one()
    )
    if stored["configuration"] != configuration:
        raise ConflictError("recipe versions are immutable")
    connection.execute(
        insert(assignments).values(
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            recipe_id=stored["id"],
            version=version + 1,
            created_at=now,
        )
    )
    return {"recipe_id": str(stored["id"]), "version": version + 1}


# --- Default recipe: auto-applied when no assignment exists, always visible/editable. ---

_LLM_TARIFF_SOURCE = (
    "OpenAI gpt-6-luna, tarifa verificada 2026-09-27 (docs/release-20260927-008.md): "
    "US$0,10 / US$0,01 / US$0,50 por millón de tokens de entrada, entrada cacheada y salida."
)
_GEMINI_IMAGE_SOURCE = (
    "ai.google.dev/gemini-api/docs/pricing, consultado 2026-09-28: Gemini 3.1 Flash Image, "
    "US$0,067/imagen estándar. 10 imágenes/video acordadas con el propietario."
)
_LOCAL_TTS_SOURCE = (
    "Modelo de texto a voz local declarado por el propietario; sin costo marginal de API, "
    "cómputo ya incluido en la infraestructura existente."
)
_FFMPEG_SOURCE = (
    "Ensamblaje determinista con ffmpeg local declarado por el propietario; sin costo marginal "
    "ni intervención manual. El esquema solo distingue ai/semi/manual/unknown, sin una categoría "
    "de código determinista, por lo que se marca 'ai' al no requerir trabajo manual por video."
)
_LLM_CAPACITY_SOURCE = (
    "Derivado de docs/release-20260927-008.md: tope real US$5/semana de gpt-6-luna "
    "÷ reserva máxima real US$0,105256/llamada (peor caso), x 52/12 semanas por mes "
    "(misma conversión ya usada en scenarios.py) ≈ 205 llamadas/mes."
)
_GEMINI_CAPACITY_SOURCE = (
    "Tope declarado por el propietario para Gemini image API: US$5/semana, misma lógica "
    "que el tope del LLM. ÷ US$0,067/imagen (ai.google.dev/gemini-api/docs/pricing) "
    "x 52/12 semanas por mes ≈ 323 imágenes/mes."
)
_LOCAL_CAPACITY_SOURCE = (
    "Declarado por el propietario: a la cadencia actual (4 videos/mes) el equipo local "
    "no es el cuello de botella; 30 videos/mes es un techo de holgura declarado, no una "
    "métrica de negocio."
)
_ZERO_HOURS = EstimateRange(low=Decimal(0), high=Decimal(0))
_ZERO_COST = EstimateRange(low=Decimal(0), high=Decimal(0))


def _default_stages() -> tuple[ProductionStage, ...]:
    return (
        ProductionStage(
            name="ideation",
            tool_key="gpt-6-luna",
            automation="ai",
            variable_usd_per_video=EstimateRange(low=Decimal("0.0001"), high=Decimal("0.0004")),
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="calls",
            source=_LLM_TARIFF_SOURCE,
        ),
        ProductionStage(
            name="research",
            tool_key="gpt-6-luna",
            automation="ai",
            variable_usd_per_video=EstimateRange(low=Decimal("0.0003"), high=Decimal("0.0008")),
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="calls",
            source=_LLM_TARIFF_SOURCE,
        ),
        ProductionStage(
            name="script",
            tool_key="gpt-6-luna",
            automation="ai",
            variable_usd_per_video=EstimateRange(low=Decimal("0.0005"), high=Decimal("0.0015")),
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="calls",
            source=_LLM_TARIFF_SOURCE,
        ),
        ProductionStage(
            name="voice",
            tool_key="local-tts-model",
            automation="ai",
            variable_usd_per_video=_ZERO_COST,
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="videos",
            source=_LOCAL_TTS_SOURCE,
        ),
        ProductionStage(
            name="visuals",
            tool_key="gemini-3.1-flash-image",
            automation="ai",
            variable_usd_per_video=EstimateRange(low=Decimal("0.67"), high=Decimal("1.34")),
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(10),
            tool_capacity_unit="images",
            source=_GEMINI_IMAGE_SOURCE,
        ),
        ProductionStage(
            name="editing",
            tool_key="ffmpeg-local",
            automation="ai",
            variable_usd_per_video=_ZERO_COST,
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="videos",
            source=_FFMPEG_SOURCE,
        ),
        ProductionStage(
            name="review",
            tool_key="gpt-6-luna",
            automation="ai",
            variable_usd_per_video=EstimateRange(low=Decimal("0.0001"), high=Decimal("0.0004")),
            human_hours_per_video=_ZERO_HOURS,
            tool_units_per_video=Decimal(1),
            tool_capacity_unit="calls",
            source=_LLM_TARIFF_SOURCE
            + " QA automatizado: reglas deterministas y una pasada del LLM.",
        ),
    )


def _default_tools() -> tuple[SharedTool, ...]:
    return (
        SharedTool(
            key="gpt-6-luna",
            monthly_usd=_ZERO_COST,
            monthly_capacity=Decimal(205),
            capacity_unit="calls",
            source=_LLM_CAPACITY_SOURCE,
        ),
        SharedTool(
            key="gemini-3.1-flash-image",
            monthly_usd=_ZERO_COST,
            monthly_capacity=Decimal(323),
            capacity_unit="images",
            source=_GEMINI_CAPACITY_SOURCE,
        ),
        SharedTool(
            key="local-tts-model",
            monthly_usd=_ZERO_COST,
            monthly_capacity=Decimal(30),
            capacity_unit="videos",
            source=_LOCAL_CAPACITY_SOURCE,
        ),
        SharedTool(
            key="ffmpeg-local",
            monthly_usd=_ZERO_COST,
            monthly_capacity=Decimal(30),
            capacity_unit="videos",
            source=_LOCAL_CAPACITY_SOURCE,
        ),
    )


def _default_anchors() -> dict[str, FitAnchor]:
    return {
        "automation": FitAnchor(
            grade=100,
            evidence=(
                "Las 7 etapas corren con IA local/API o código determinista; "
                "ninguna requiere intervención manual por video."
            ),
        ),
        "human_effort": FitAnchor(
            grade=100,
            evidence=(
                "human_hours_per_video=0 en las 7 etapas; solo hay supervisión ocasional "
                "del propietario, no por video producido."
            ),
        ),
        "cost": FitAnchor(
            grade=75,
            evidence=(
                "Costo variable total estimado ≈ US$0,67-1,35/video, dominado por la etapa "
                "visuals (Gemini image API, 10 imágenes x US$0,067)."
            ),
        ),
        "assets": FitAnchor(
            grade=75,
            evidence=(
                "Los modelos locales de voz y edición, y las plantillas de prompts de imagen, "
                "se reutilizan entre videos y nichos sin costo adicional de configuración."
            ),
        ),
    }


class DefaultRecipeTemplate(Contract):
    recipe: Recipe
    tools: tuple[SharedTool, ...] = ()


def default_recipe(video_format: VideoFormat, language: str = "en") -> Recipe:
    """The owner-declared generic recipe: every stage runs on AI tools or deterministic code."""
    return Recipe(
        key=f"default-{video_format.value}",
        version="2026-09-28",
        audience_key=None,
        language=language,
        format=video_format,
        stages=_default_stages(),
        anchors=_default_anchors(),
    )


def default_template(video_format: VideoFormat, language: str = "en") -> DefaultRecipeTemplate:
    """The recipe plus the shared-tool capacity that makes its Creator Fit resolvable."""
    return DefaultRecipeTemplate(
        recipe=default_recipe(video_format, language), tools=_default_tools()
    )


def preview_plan(template: DefaultRecipeTemplate) -> ProductionPlan:
    """A standalone preview for Configuración; a real opportunity fills its own audience."""
    recipe = template.recipe
    if not recipe.audience_key:
        recipe = recipe.model_copy(update={"audience_key": "(definida por la oportunidad)"})
    return ProductionPlan(
        recipe=recipe,
        tools=template.tools,
        videos_per_month=DEFAULT_VIDEOS_PER_MONTH,
        radar_monthly_usd=DEFAULT_RADAR_MONTHLY_USD,
    )


def latest_recipe_default(
    connection: Connection, profile_id: UUID, video_format: str
) -> dict[str, Any] | None:
    row = (
        connection.execute(
            select(defaults_table)
            .where(
                defaults_table.c.profile_id == profile_id,
                defaults_table.c.format == video_format,
            )
            .order_by(defaults_table.c.version.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def save_recipe_default(
    connection: Connection,
    profile_id: UUID,
    video_format: str,
    template: DefaultRecipeTemplate,
    expected_version: int,
    now: datetime,
) -> dict[str, Any]:
    if template.recipe.format.value != video_format:
        raise ValueError("recipe format does not match the requested default slot")
    previous = latest_recipe_default(connection, profile_id, video_format)
    version = previous["version"] if previous else 0
    if version != expected_version:
        raise ConflictError("default recipe changed")
    connection.execute(
        defaults_table.insert().values(
            profile_id=profile_id,
            format=video_format,
            version=version + 1,
            configuration=template.model_dump(mode="json"),
            created_at=now,
        )
    )
    result = latest_recipe_default(connection, profile_id, video_format)
    assert result is not None
    return result


def effective_recipe_default(
    connection: Connection, profile_id: UUID, video_format: VideoFormat, now: datetime
) -> dict[str, Any]:
    """The current default recipe for this format, seeding the owner-declared one on first use."""
    existing = latest_recipe_default(connection, profile_id, video_format.value)
    if existing is not None:
        return existing
    connection.execute(
        insert(defaults_table)
        .values(
            profile_id=profile_id,
            format=video_format.value,
            version=1,
            configuration=default_template(video_format).model_dump(mode="json"),
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    result = latest_recipe_default(connection, profile_id, video_format.value)
    assert result is not None
    return result


def ensure_default_recipe(
    connection: Connection, opportunity_id: UUID, profile_id: UUID, now: datetime
) -> dict[str, Any] | None:
    """Auto-apply the current default recipe when no assignment exists yet; never overwrite one."""
    if latest_plan(connection, opportunity_id, profile_id):
        return None
    opportunity = (
        connection.execute(select(s.opportunities).where(s.opportunities.c.id == opportunity_id))
        .mappings()
        .one()
    )
    template = effective_recipe_default(
        connection, profile_id, VideoFormat(opportunity["format"]), now
    )
    configuration = template["configuration"]
    # production_recipes stores content by (key, version); key must stay unique per
    # opportunity so two opportunities sharing a template never collide on content.
    # audience_key/language come from the opportunity itself, never invented.
    recipe = Recipe.model_validate(
        configuration["recipe"]
        | {
            "language": opportunity["language"],
            "audience_key": opportunity["audience_key"],
            "key": f"default-{opportunity['format']}-{opportunity_id}",
            "version": f"template-v{template['version']}",
        }
    )
    tools = tuple(SharedTool.model_validate(tool) for tool in configuration["tools"])
    plan = ProductionPlan(
        recipe=recipe,
        tools=tools,
        videos_per_month=DEFAULT_VIDEOS_PER_MONTH,
        radar_monthly_usd=DEFAULT_RADAR_MONTHLY_USD,
    )
    try:
        return save_plan(connection, opportunity_id, profile_id, plan, 0, now)
    except ConflictError:
        return None
