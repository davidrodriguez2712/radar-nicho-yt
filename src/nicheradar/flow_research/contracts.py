# src/nicheradar/flow_research/contracts.py
"""dossier-v3: the structured result a researcher hands back (v1 and v2 are legacy, read-only).

The payload is untrusted: it comes from a person-driven Claude Code session that read the web.
Shape is checked by pydantic; cross-references and arithmetic by ``consistency_problems``.
Messages never echo the submitted values.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Self, TypedDict
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_core import ErrorDetails

SCHEMA_VERSION = "dossier-v3"
LEGACY_SCHEMA_VERSIONS = ("dossier-v1", "dossier-v2")
PLAN_TEXT_MIN = 120  # approach / summary must explain, not list
MAX_PRICE_AGE = timedelta(days=90)
GENERATED_WINDOW = timedelta(hours=24)
CLOCK_SKEW = timedelta(minutes=5)
HORIZON_MAX_WEEKS = {"short": 13, "medium": 39}
MONEY_TOLERANCE = Decimal("0.01")
MAX_PROBLEMS = 50


def _https(value: str) -> str:
    if not value.startswith("https://") or any(char.isspace() for char in value):
        raise ValueError("la URL debe ser https y no contener espacios")
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
Url = Annotated[str, StringConstraints(max_length=500), AfterValidator(_https)]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000"))]
Quantity = Annotated[Decimal, Field(gt=0, le=Decimal("10000"))]
EvidenceKind = Literal["seller_declared", "researched", "estimate"]
Automation = Literal["manual", "semi", "auto"]


class Problem(TypedDict):
    path: str
    message: str


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Source(Contract):
    id: SourceId
    url: Url
    title: Label
    accessed_on: date


class Verdict(Contract):
    recommendation: Literal["go", "go_with_conditions", "no_go"]
    confidence: Literal["low", "medium", "high"]
    thesis: Text
    main_risks: list[Text] = Field(min_length=1, max_length=10)
    unknowns: list[Text] = Field(max_length=20)


class Competitor(Contract):
    name: Label
    channel_url: Url
    subscribers: int | None = Field(default=None, ge=0)
    cadence: Label
    format: Label
    production_style: Text
    evidence_kind: EvidenceKind
    source_id: SourceId


class ProductionStep(Contract):
    order: int = Field(ge=1, le=50)
    name: Label
    human_minutes_per_video: int = Field(ge=0, le=10_000)
    automation: Automation
    tools: list[Label] = Field(max_length=10)
    stays_human: Text | None = None


class Phase(Contract):
    name: Label
    weeks: int = Field(ge=1, le=39)
    objective: Text
    deliverables: list[Text] = Field(min_length=1, max_length=15)
    tasks: list[Text] = Field(min_length=1, max_length=30)
    exit_criteria: list[Text] = Field(min_length=1, max_length=10)
    cost_usd: Money


class BudgetLine(Contract):
    """``quantity`` counts units inside the horizon; for monthly lines, the number of months."""

    phase: Label
    tool: Label
    description: Text
    unit_cost_usd: Money
    quantity: Quantity
    recurrence: Literal["one_time", "monthly"]
    subtotal_usd: Money
    price_checked_on: date
    source_id: SourceId
    evidence_kind: EvidenceKind


class Scenarios(Contract):
    low: Money
    likely: Money
    high: Money

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.low <= self.likely <= self.high:
            raise ValueError("deben cumplir bajo <= probable <= alto")
        return self


class Budget(Contract):
    lines: list[BudgetLine] = Field(min_length=1, max_length=80)
    totals: Scenarios
    assumptions: list[Text] = Field(min_length=1, max_length=20)


class Tool(Contract):
    name: Label
    phase: Label
    purpose: Text
    pricing: Label
    cheaper_alternative: Label | None = None
    automation: Automation
    source_id: SourceId


class AutomationItem(Contract):
    step: Label
    automated_today: Text
    semi_automated: Text
    dependency_risk: Text
    manual_fallback: Text


class PolicyRisk(Contract):
    level: Literal["bajo", "medio", "alto"]
    summary: Text
    mitigations: list[Text] = Field(min_length=1, max_length=10)
    source_ids: list[SourceId] = Field(min_length=1, max_length=10)


class MonthsToRecover(Contract):
    low: int | None = Field(ge=0, le=240)
    likely: int | None = Field(ge=0, le=240)
    high: int | None = Field(ge=0, le=240)


class BreakEven(Contract):
    evidence_kind: Literal["estimate"]
    assumptions: list[Text] = Field(min_length=1, max_length=20)
    monthly_income_usd: Scenarios
    months_to_recover: MonthsToRecover


class DossierBody(Contract):
    """Fields shared by every dossier version."""

    request_id: UUID
    niche_label: Label
    format: Literal["long", "shorts"]
    language: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]
    horizon: Literal["short", "medium"]
    generated_at: AwareDatetime
    verdict: Verdict
    competitors: list[Competitor] = Field(min_length=3, max_length=8)
    production_flow: list[ProductionStep] = Field(min_length=3, max_length=15)
    roadmap: list[Phase] = Field(min_length=1, max_length=12)
    budget: Budget
    tools: list[Tool] = Field(min_length=1, max_length=40)
    automation_map: list[AutomationItem] = Field(min_length=1, max_length=15)
    policy_risk: PolicyRisk
    break_even: BreakEven
    sources: list[Source] = Field(min_length=1, max_length=60)


class Dossier(DossierBody):
    """dossier-v1: kept only to read dossiers that were stored before dossier-v2."""

    schema_version: Literal["dossier-v1"]


RightsOrigin = Literal[
    "own_capture",
    "own_generation",
    "licensed",
    "platform_policy",
    "public_domain",
    "third_party",
    "unknown",
]
CITED_ORIGINS = {"licensed", "platform_policy", "public_domain", "third_party"}
CLEAR_ORIGINS = {"own_capture", "own_generation", "licensed", "platform_policy", "public_domain"}
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=PLAN_TEXT_MIN, max_length=1500)
]


class RightsMaterial(Contract):
    kind: Literal["visual", "audio", "voice", "text"]
    description: Text
    origin: RightsOrigin
    license_or_policy: Text
    source_id: SourceId | None = None
    requires_permission: bool
    permission_plan: Text | None = None


class Rights(Contract):
    verdict: Literal["cleared", "conditional", "blocked"]
    summary: Text
    materials: list[RightsMaterial] = Field(min_length=1, max_length=20)
    conditions: list[Text] = Field(max_length=20)


class StageTool(Contract):
    name: Label
    interface: Label
    cost_usd_per_video: Money


class AutomationStage(Contract):
    step: Label
    mode: Automation
    approach: LongText
    tools: list[StageTool] = Field(max_length=8)
    inputs: Text
    outputs: Text
    quality_gate: Text
    failure_mode: Text
    retry_policy: Text
    human_minutes_per_video: int = Field(ge=0, le=10_000)
    stays_human: Text | None = None


class ImplementationMilestone(Contract):
    order: int = Field(ge=1, le=50)
    name: Label
    description: LongText
    acceptance_criteria: list[Text] = Field(min_length=1, max_length=10)
    depends_on: list[int] = Field(max_length=10)


class AutomationPlan(Contract):
    summary: LongText
    stages: list[AutomationStage] = Field(min_length=3, max_length=15)
    milestones: list[ImplementationMilestone] = Field(min_length=2, max_length=20)


class RightsDossier(DossierBody):
    """Fields of dossier-v2 and dossier-v3: rights and the per-stage automation plan."""

    rights: Rights
    automation_plan: AutomationPlan

    @property
    def human_minutes_per_video(self) -> int:
        return human_minutes_per_video(self)


class DossierV2(RightsDossier):
    """dossier-v2: kept only to read dossiers stored before dossier-v3."""

    schema_version: Literal["dossier-v2"]


class VerdictV3(Verdict):
    conditions: list[Text] = Field(max_length=10)


class CalibrationStep(Contract):
    step: Label
    minutes_per_video: int = Field(ge=0, le=10_000)


class ExitCriterion(Contract):
    max_minutes_per_video: int = Field(ge=1, le=10_000)
    consecutive_videos: int = Field(ge=1, le=12)
    statement: Text


class Calibration(Contract):
    """The first videos of a channel, while the flow is built and tuned (not a per-video cost)."""

    videos: int = Field(ge=1, le=12)
    setup_hours: float = Field(ge=0, le=1000)
    exit_criterion: ExitCriterion
    minutes_by_step: list[CalibrationStep] = Field(min_length=3, max_length=15)


SteadyBasis = Literal["measured", "mapped_flow_equivalent", "estimate"]


class SteadyStateEvidence(Contract):
    """What backs the regime minutes: a timed channel, an equivalent mapped flow, or a guess."""

    basis: SteadyBasis
    reference_channel: Label | None = None
    reference_minutes_per_video: int | None = Field(default=None, ge=0, le=10_000)
    reference_sample_videos: int | None = Field(default=None, ge=1, le=10_000)
    format_match: Text


class DossierV3(RightsDossier):
    schema_version: Literal["dossier-v3"]
    verdict: VerdictV3
    calibration: Calibration
    steady_state_evidence: SteadyStateEvidence

    @property
    def calibration_hours(self) -> float:
        return calibration_total_hours(
            self.calibration.setup_hours,
            self.calibration.videos,
            sum(item.minutes_per_video for item in self.calibration.minutes_by_step),
        )


def calibration_total_hours(setup_hours: float, videos: int, minutes_per_video: int) -> float:
    """Derived, never declared: preparation plus the human minutes of every calibration video."""
    return round(setup_hours + videos * minutes_per_video / 60, 2)


def human_minutes_per_video(dossier: DossierBody) -> int:
    """Total human time per video, derived from the production flow (never self-declared)."""
    return sum(step.human_minutes_per_video for step in dossier.production_flow)


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= MONEY_TOLERANCE


def consistency_problems(dossier: DossierBody, now: datetime) -> list[Problem]:
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    if not now - GENERATED_WINDOW <= dossier.generated_at <= now + CLOCK_SKEW:
        add("generated_at", "debe ser de las últimas 24 horas")

    source_ids = [source.id for source in dossier.sources]
    if len(set(source_ids)) != len(source_ids):
        add("sources", "los id de las fuentes deben ser únicos")
    known = set(source_ids)

    def cite(path: str, source_id: str) -> None:
        if source_id not in known:
            add(path, "la fuente citada no existe en sources")

    for index, competitor in enumerate(dossier.competitors):
        cite(f"competitors.{index}.source_id", competitor.source_id)
    for index, tool in enumerate(dossier.tools):
        cite(f"tools.{index}.source_id", tool.source_id)
    for index, source_id in enumerate(dossier.policy_risk.source_ids):
        cite(f"policy_risk.source_ids.{index}", source_id)

    phases = [phase.name for phase in dossier.roadmap]
    if len(set(phases)) != len(phases):
        add("roadmap", "los nombres de fase deben ser únicos")
    tools = [tool.name for tool in dossier.tools]
    if len(set(tools)) != len(tools):
        add("tools", "los nombres de herramienta deben ser únicos")
    for index, tool in enumerate(dossier.tools):
        if tool.phase not in phases:
            add(f"tools.{index}.phase", "la fase no existe en roadmap")

    weeks = sum(phase.weeks for phase in dossier.roadmap)
    limit = HORIZON_MAX_WEEKS[dossier.horizon]
    if weeks > limit:
        add("roadmap", f"las fases suman {weeks} semanas y el horizonte permite {limit}")

    orders = sorted(step.order for step in dossier.production_flow)
    if orders != list(range(1, len(orders) + 1)):
        add("production_flow", "los pasos deben numerarse 1..n sin saltos ni repeticiones")

    generated_on = dossier.generated_at.date()
    spent: dict[str, Decimal] = {}
    for index, line in enumerate(dossier.budget.lines):
        base = f"budget.lines.{index}"
        cite(f"{base}.source_id", line.source_id)
        if line.tool not in tools:
            add(f"{base}.tool", "la herramienta no existe en tools")
        if line.phase not in phases:
            add(f"{base}.phase", "la fase no existe en roadmap")
        if not _close(line.subtotal_usd, line.unit_cost_usd * line.quantity):
            add(f"{base}.subtotal_usd", "no coincide con costo unitario por cantidad")
        age = generated_on - line.price_checked_on
        if age < timedelta(0):
            add(f"{base}.price_checked_on", "es posterior a generated_at")
        elif age > MAX_PRICE_AGE:
            add(f"{base}.price_checked_on", "tiene más de 90 días")
        spent[line.phase] = spent.get(line.phase, Decimal(0)) + line.subtotal_usd

    for index, phase in enumerate(dossier.roadmap):
        if not _close(phase.cost_usd, spent.get(phase.name, Decimal(0))):
            add(f"roadmap.{index}.cost_usd", "no coincide con la suma de sus partidas")
    if not _close(dossier.budget.totals.likely, sum(spent.values(), Decimal(0))):
        add("budget.totals.likely", "no coincide con la suma de las partidas")
    return problems


def v2_problems(dossier: RightsDossier) -> list[Problem]:
    """Rights and automation plan: cross-references and the numbers that must agree."""
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    known = {source.id for source in dossier.sources}
    rights = dossier.rights
    for index, material in enumerate(rights.materials):
        base = f"rights.materials.{index}"
        if material.origin in CITED_ORIGINS and material.source_id is None:
            add(f"{base}.source_id", "este origen exige citar la licencia o política en sources")
        if material.source_id is not None and material.source_id not in known:
            add(f"{base}.source_id", "la fuente citada no existe en sources")
        if material.requires_permission and material.permission_plan is None:
            add(f"{base}.permission_plan", "explica cómo se obtiene el permiso")
    kinds = {material.kind for material in rights.materials}
    if "visual" not in kinds or not kinds & {"audio", "voice"}:
        add("rights.materials", "declara el origen del material visual y del audio o la voz")
    if rights.verdict == "cleared" and any(
        material.requires_permission or material.origin not in CLEAR_ORIGINS
        for material in rights.materials
    ):
        add(
            "rights.verdict", "«cleared» no admite material con permiso pendiente u origen incierto"
        )
    if rights.verdict == "conditional" and not rights.conditions:
        add("rights.conditions", "un veredicto «conditional» debe listar sus condiciones")
    if rights.verdict == "blocked" and dossier.verdict.recommendation != "no_go":
        add("verdict.recommendation", "los derechos están bloqueados: la recomendación es no_go")

    plan = dossier.automation_plan
    flow = {step.name: step for step in dossier.production_flow}
    stage_names = [stage.step for stage in plan.stages]
    if len(set(stage_names)) != len(stage_names) or set(stage_names) != set(flow):
        add("automation_plan.stages", "debe haber una etapa por cada paso de production_flow")
    tool_names = {tool.name for tool in dossier.tools}
    for index, stage in enumerate(plan.stages):
        base = f"automation_plan.stages.{index}"
        step = flow.get(stage.step)
        if step is not None:
            if stage.human_minutes_per_video != step.human_minutes_per_video:
                add(f"{base}.human_minutes_per_video", "no coincide con production_flow")
            if stage.mode != step.automation:
                add(f"{base}.mode", "no coincide con la automatización de production_flow")
        for number, tool in enumerate(stage.tools):
            if tool.name not in tool_names:
                add(f"{base}.tools.{number}.name", "la herramienta no existe en tools")
        if stage.human_minutes_per_video > 0 and stage.stays_human is None:
            add(f"{base}.stays_human", "explica qué sigue siendo humano y por qué")
    orders = sorted(milestone.order for milestone in plan.milestones)
    if orders != list(range(1, len(orders) + 1)):
        add("automation_plan.milestones", "los hitos deben numerarse 1..n sin saltos")
    for index, milestone in enumerate(plan.milestones):
        if any(dep >= milestone.order or dep not in orders for dep in milestone.depends_on):
            add(
                f"automation_plan.milestones.{index}.depends_on",
                "solo puede depender de hitos anteriores que existan",
            )
    return problems


def v3_problems(dossier: DossierV3) -> list[Problem]:
    """Calibration against the flow, and what the regime minutes are allowed to promise."""
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    regime = {step.name: step.human_minutes_per_video for step in dossier.production_flow}
    steps = [item.step for item in dossier.calibration.minutes_by_step]
    if len(set(steps)) != len(steps) or set(steps) != set(regime):
        add("calibration.minutes_by_step", "debe haber un valor por cada paso de production_flow")
    for index, item in enumerate(dossier.calibration.minutes_by_step):
        steady = regime.get(item.step)
        if steady is not None and item.minutes_per_video < steady:
            add(
                f"calibration.minutes_by_step.{index}.minutes_per_video",
                "la calibración no puede costar menos minutos que el régimen",
            )

    exit_criterion = dossier.calibration.exit_criterion
    if exit_criterion.consecutive_videos > dossier.calibration.videos:
        add(
            "calibration.exit_criterion.consecutive_videos",
            "la calibración dura menos videos de los que pide el criterio de salida",
        )
    if exit_criterion.max_minutes_per_video < sum(regime.values()):
        add(
            "calibration.exit_criterion.max_minutes_per_video",
            "el criterio de salida nunca se cumpliría con los minutos de régimen declarados",
        )

    evidence = dossier.steady_state_evidence
    if evidence.basis != "estimate" and evidence.reference_channel is None:
        add("steady_state_evidence.reference_channel", "cita el canal de referencia")
    if evidence.basis == "measured" and (
        evidence.reference_minutes_per_video is None or evidence.reference_sample_videos is None
    ):
        add(
            "steady_state_evidence.reference_minutes_per_video",
            "un régimen medido declara los minutos y cuántos videos se midieron",
        )

    recommendation = dossier.verdict.recommendation
    conditions = dossier.verdict.conditions
    if recommendation == "go_with_conditions" and not conditions:
        add("verdict.conditions", "go_with_conditions debe listar sus condiciones")
    if evidence.basis == "estimate":
        if recommendation == "go":
            add(
                "verdict.recommendation",
                "el régimen es una estimación: usa go_with_conditions o no_go",
            )
        elif (
            recommendation == "go_with_conditions"
            and dossier.calibration.exit_criterion.statement not in conditions
        ):
            add("verdict.conditions", "incluye el criterio de salida de la calibración tal cual")
    return problems


def _problem(item: ErrorDetails) -> Problem:
    location = [str(part) for part in item["loc"]]
    if item["type"] == "extra_forbidden" and location:
        location[-1] = "(campo no permitido)"  # the key is untrusted text: never echo it
    return {"path": ".".join(location) or "(raiz)", "message": item["msg"]}


def validate_dossier(payload: object, now: datetime) -> tuple[DossierV3 | None, list[Problem]]:
    """Return the dossier, or ``None`` with every problem found; never raises on bad input.

    Only ``dossier-v3`` is accepted: v1 and v2 exist solely for stored dossiers.
    """
    if isinstance(payload, dict) and payload.get("schema_version") in LEGACY_SCHEMA_VERSIONS:
        return None, [
            {
                "path": "schema_version",
                "message": (
                    f"{payload['schema_version']} ya no se acepta en encargos nuevos: "
                    "usa dossier-v3"
                ),
            }
        ]
    try:
        dossier = DossierV3.model_validate(payload)
    except ValidationError as error:
        return None, [
            _problem(item)
            for item in error.errors(include_url=False, include_context=False, include_input=False)[
                :MAX_PROBLEMS
            ]
        ]
    problems = (consistency_problems(dossier, now) + v2_problems(dossier) + v3_problems(dossier))[
        :MAX_PROBLEMS
    ]
    return (None if problems else dossier), problems
