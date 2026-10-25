# src/nicheradar/pilots/contracts.py
"""pilot-package-v1 (NicheRadar -> canal) y channel-report-v1 (canal -> NicheRadar).

Especificación: docs/contracts/. Ambos payloads son NO confiables: la forma la valida pydantic y la
coherencia ``*_problems``. Los mensajes nunca repiten los valores enviados. La huella del paquete es
el SHA-256 de su JSON canónico (claves ordenadas, sin espacios, UTF-8) sin el propio campo de la
huella.
"""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationError,
)
from pydantic_core import ErrorDetails

from nicheradar.pilots.translation import translate

PACKAGE_CONTRACT = "pilot-package-v1"
REPORT_CONTRACT = "channel-report-v1"
CLOCK_SKEW = timedelta(minutes=5)
MAX_PROBLEMS = 50
MAX_REPORT_VIDEOS = 100
MAX_REPORT_BYTES = 256 * 1024
PILOT_ID = r"^pil_[0-9]{8}_[a-z0-9-]{1,40}$"
CHANNEL_ID = r"^canal-[a-z0-9-]{1,40}$"
UNMEASURABLE = {"manual", "pipeline_e2e"}  # reglas sin umbral numérico


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


Number = Annotated[
    Decimal,
    Field(allow_inf_nan=False),
    PlainSerializer(_json_number, return_type=int | float, when_used="json"),
]
Money = Annotated[
    Decimal,
    Field(ge=0, le=Decimal("1000000"), decimal_places=2, allow_inf_nan=False),
    PlainSerializer(_json_number, return_type=int | float, when_used="json"),
]
Pct = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Score = Annotated[int, Field(ge=0, le=100)] | None
Confidence = Literal["low", "medium", "high"]


class Problem(TypedDict):
    path: str
    message: str


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


# ---- pilot-package-v1 ----------------------------------------------------------


class Niche(Contract):
    label: Label
    format: Literal["long", "shorts"]
    language: Annotated[
        str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    ]  # sin valor por defecto


class Scores(Contract):
    opportunity: Score
    automation: Score
    creator_fit: Score
    market: Score


class Figure(Contract):
    name: Label
    value: Number
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    origin: Literal["seller_declared", "estimate", "verified"]


class LanguageShare(Contract):
    language: Annotated[str, StringConstraints(pattern=r"^([a-z]{2}(-[A-Z]{2})?|unknown)$")]
    share_pct: Number = Field(ge=0, le=100)


class Evidence(Contract):
    captured_at: AwareDatetime
    scores: Scores
    confidence: Confidence
    listings_with_income: Annotated[int, Field(ge=0)]
    language_mix: Annotated[list[LanguageShare], Field(max_length=10)]
    figures: Annotated[list[Figure], Field(max_length=30)]


class DossierSummary(Contract):
    request_id: UUID
    schema_: Annotated[Literal["dossier-v1"], Field(alias="schema")]
    recommendation: Literal["go", "go_with_conditions", "no_go"]
    confidence: Confidence
    thesis: Text
    unknowns: Annotated[list[Text], Field(max_length=20)]

    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, populate_by_name=True
    )


class Budget(Contract):
    currency: Literal["USD"]
    low: Money
    likely: Money
    high: Money
    max_videos: Annotated[int, Field(ge=1, le=50)]
    basis: Text


class Milestone(Contract):
    kind: Literal["week", "video", "month"]
    value: Annotated[int, Field(ge=1)]


class StopRule(Contract):
    id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
    text: ShortText
    metric: Literal["pipeline_e2e", "avd_pct", "browse_share_pct", "revenue_vs_cost", "manual"]
    comparator: Literal[">="]
    threshold: Number | None
    min_cases: Annotated[int, Field(ge=1)] | None
    milestone: Milestone


class Recipe(Contract):
    name: Label
    version: Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]


class Package(Contract):
    contract: Literal["pilot-package-v1"]
    pilot_id: Annotated[str, StringConstraints(pattern=PILOT_ID)]
    supersedes: Annotated[str, StringConstraints(pattern=PILOT_ID)] | None
    authorized_by: Label
    authorized_at: AwareDatetime
    valid_until: AwareDatetime
    niche: Niche
    evidence: Evidence
    dossier: DossierSummary
    budget: Budget
    stop_rules: Annotated[list[StopRule], Field(min_length=1, max_length=10)]
    close_after_failed_milestones: Annotated[int, Field(ge=1, le=5)]
    target_channel: Annotated[str, StringConstraints(pattern=CHANNEL_ID)] | None
    recipe: Recipe | None
    package_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def package_sha256(payload: dict[str, Any]) -> str:
    body = {key: item for key, item in payload.items() if key != "package_sha256"}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def with_sha256(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "package_sha256": package_sha256(body)}


def _problem(item: ErrorDetails) -> Problem:
    location = [str(part) for part in item["loc"]]
    if item["type"] == "extra_forbidden" and location:
        location[-1] = "(campo no permitido)"  # la clave es texto no confiable: no se repite
    return {"path": ".".join(location) or "(raiz)", "message": item["msg"]}


def _shape_problems(error: ValidationError) -> list[Problem]:
    items = error.errors(include_url=False, include_context=False, include_input=False)
    return [_problem(item) for item in items[:MAX_PROBLEMS]]


def package_problems(package: Package, payload: dict[str, Any], now: datetime) -> list[Problem]:
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    if package.authorized_at > now + CLOCK_SKEW:
        add("authorized_at", "no puede ser futura")
    if package.valid_until <= package.authorized_at:
        add("valid_until", "debe ser posterior a authorized_at")
    budget = package.budget
    if not budget.low <= budget.likely <= budget.high:
        add("budget", "low, likely y high deben estar ordenados")
    ids = [rule.id for rule in package.stop_rules]
    if len(set(ids)) != len(ids):
        add("stop_rules", "los id de las reglas deben ser únicos")
    for index, rule in enumerate(package.stop_rules):
        if rule.metric in UNMEASURABLE and rule.threshold is not None:
            add(f"stop_rules.{index}.threshold", "debe ser null para esta métrica")
        if rule.metric not in UNMEASURABLE and rule.threshold is None:
            add(f"stop_rules.{index}.threshold", "es obligatorio para una métrica medible")
    mix = package.evidence.language_mix
    if mix and abs(sum((item.share_pct for item in mix), Decimal(0)) - 100) > 1:
        add("evidence.language_mix", "los porcentajes deben sumar 100 (±1)")
    if package.evidence.confidence == "low" and not package.dossier.unknowns:
        add("dossier.unknowns", "es obligatoria cuando la confianza del nicho es baja")
    if package.package_sha256 != package_sha256(payload):
        add("package_sha256", "no coincide con el contenido del paquete")
    return problems[:MAX_PROBLEMS]


def validate_package(payload: object, now: datetime) -> tuple[Package | None, list[Problem]]:
    """Devuelve el paquete o ``None`` con todos los problemas; nunca lanza ante una entrada mala."""
    try:
        package = Package.model_validate(payload)
    except ValidationError as error:
        return None, _shape_problems(error)
    assert isinstance(payload, dict)
    problems = package_problems(package, payload, now)
    return (None if problems else package), problems


# ---- channel-report-v1 --------------------------------------------------------------

Stage = Literal[
    "in_production",
    "awaiting_human",
    "uploaded",
    "published",
    "measuring",
    "killed",
    "blocked",
    "unknown",
]
PUBLIC_STAGES = {"published", "measuring"}
FAILED_STAGES = {"killed", "blocked"}


class Measurement(Contract):
    measured_at: AwareDatetime
    window_days: Annotated[int, Field(ge=1)]
    avd_pct: Pct
    views: Annotated[int, Field(ge=0)]
    browse_share_pct: Pct | None
    subscribers_gained: Annotated[int, Field(ge=0)] | None


class Video(Contract):
    video_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,60}$")]
    source_state: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{1,40}$")]
    visibility: Literal["private", "public", "unknown"]
    published_at: AwareDatetime | None
    cost_usd: Money
    cost_equivalent_usd: Money | None
    machine_minutes: Annotated[int, Field(ge=0)] | None
    measurement: Measurement | None
    failure_code: Annotated[str, StringConstraints(min_length=1, max_length=60)] | None


class Check(Contract):
    id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
    label: Label
    ok: bool
    detail: Annotated[str, StringConstraints(max_length=300)] | None
    expires_at: AwareDatetime | None


class Report(Contract):
    contract: Literal["channel-report-v1"]
    pilot_id: Annotated[str, StringConstraints(pattern=PILOT_ID)]
    channel_id: Annotated[str, StringConstraints(pattern=CHANNEL_ID)]
    reported_at: AwareDatetime
    channel_status: Literal["active", "paused", "closed"]
    videos: Annotated[list[Video], Field(max_length=MAX_REPORT_VIDEOS)]
    checks: Annotated[list[Check], Field(max_length=20)] = []
    note: Annotated[str, StringConstraints(max_length=1500)] | None


def stage_of(channel_id: str, video: Video) -> str:
    """Etapa gruesa tras traducir el estado del canal; las reglas de coherencia usan esta."""
    return translate(channel_id, video.source_state, video.visibility)


def report_problems(report: Report, now: datetime) -> list[Problem]:
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    if report.reported_at > now + CLOCK_SKEW:
        add("reported_at", "no puede ser futuro")
    ids = [video.video_id for video in report.videos]
    if len(set(ids)) != len(ids):
        add("videos", "los video_id no pueden repetirse")
    check_ids = [check.id for check in report.checks]
    if len(set(check_ids)) != len(check_ids):
        add("checks", "los id de las comprobaciones no pueden repetirse")
    for index, video in enumerate(report.videos):
        base = f"videos.{index}"
        stage = stage_of(report.channel_id, video)
        if stage in PUBLIC_STAGES and video.published_at is None:
            add(f"{base}.published_at", "es obligatoria para esta etapa")
        if stage in PUBLIC_STAGES and video.visibility != "public":
            add(f"{base}.visibility", "un video publicado o medido debe ser público")
        if stage in FAILED_STAGES and video.failure_code is None:
            add(f"{base}.failure_code", "es obligatorio para esta etapa")
        if video.measurement is not None:
            if video.published_at is None:
                add(f"{base}.measurement", "solo puede existir si el video tiene published_at")
            elif video.measurement.measured_at <= video.published_at:
                add(f"{base}.measurement.measured_at", "debe ser posterior a published_at")
            if video.measurement.measured_at > now + CLOCK_SKEW:
                add(f"{base}.measurement.measured_at", "no puede ser futura")
    return problems[:MAX_PROBLEMS]


def validate_report(payload: object, now: datetime) -> tuple[Report | None, list[Problem]]:
    try:
        report = Report.model_validate(payload)
    except ValidationError as error:
        return None, _shape_problems(error)
    problems = report_problems(report, now)
    return (None if problems else report), problems
