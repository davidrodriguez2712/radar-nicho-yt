# src/nicheradar/flow_research/contracts.py
"""dossier-v1: the structured result a researcher hands back.

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

SCHEMA_VERSION = "dossier-v1"
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


class Dossier(Contract):
    schema_version: Literal["dossier-v1"]
    request_id: UUID
    niche_label: Label
    format: Literal["long", "shorts"]
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


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= MONEY_TOLERANCE


def consistency_problems(dossier: Dossier, now: datetime) -> list[Problem]:
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


def _problem(item: ErrorDetails) -> Problem:
    location = [str(part) for part in item["loc"]]
    if item["type"] == "extra_forbidden" and location:
        location[-1] = "(campo no permitido)"  # the key is untrusted text: never echo it
    return {"path": ".".join(location) or "(raiz)", "message": item["msg"]}


def validate_dossier(payload: object, now: datetime) -> tuple[Dossier | None, list[Problem]]:
    """Return the dossier, or ``None`` with every problem found; never raises on bad input."""
    try:
        dossier = Dossier.model_validate(payload)
    except ValidationError as error:
        return None, [
            _problem(item)
            for item in error.errors(include_url=False, include_context=False, include_input=False)[
                :MAX_PROBLEMS
            ]
        ]
    problems = consistency_problems(dossier, now)[:MAX_PROBLEMS]
    return (None if problems else dossier), problems
