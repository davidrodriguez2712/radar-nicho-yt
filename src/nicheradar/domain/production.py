from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Contract

STAGES = ("ideation", "research", "script", "voice", "visuals", "editing", "review")
FIT_WEIGHTS = {
    "automation": Decimal(".30"),
    "human_effort": Decimal(".25"),
    "cost": Decimal(".25"),
    "assets": Decimal(".20"),
}


class EstimateRange(Contract):
    low: Decimal = Field(ge=0)
    high: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.low > self.high:
            raise ValueError("low exceeds high")
        return self


class ProductionStage(Contract):
    name: Literal["ideation", "research", "script", "voice", "visuals", "editing", "review"]
    tool_key: str | None = None
    variable_usd_per_video: EstimateRange | None = None
    human_hours_per_video: EstimateRange | None = None
    tool_units_per_video: Decimal | None = Field(default=None, ge=0)
    tool_capacity_unit: str | None = None
    source: str | None = None
    automation: Literal["ai", "semi", "manual", "unknown"] = "unknown"


class FitAnchor(Contract):
    grade: Literal[0, 25, 50, 75, 100]
    evidence: str = Field(min_length=1)

    @field_validator("evidence")
    @classmethod
    def nonblank_evidence(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence cannot be blank")
        return value.strip()


class Recipe(Contract):
    key: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    audience_key: str | None = Field(default=None, min_length=1, max_length=120)
    language: str = Field(default="en", min_length=2, max_length=30)
    format: VideoFormat
    stages: tuple[ProductionStage, ...]
    rework_margin: Decimal = Field(default=Decimal(".20"), ge=0, le=5)
    anchors: dict[str, FitAnchor] = Field(default_factory=dict)
    rights_review: str = "pending"
    originality_review: str = "pending"
    repetition_review: str = "pending"

    @model_validator(mode="after")
    def stage_uniqueness(self) -> Self:
        if self.format == VideoFormat.UNKNOWN:
            raise ValueError("a production recipe needs a confirmed format")
        if len({stage.name for stage in self.stages}) != len(self.stages):
            raise ValueError("duplicate production stage")
        if set(self.anchors) - set(FIT_WEIGHTS):
            raise ValueError("unknown fit dimension")
        return self


def rubric_score(recipe: Recipe) -> Decimal | None:
    """Raw manual rubric only; use evaluate_plan for a complete Creator Fit."""
    complete_stages = set(stage.name for stage in recipe.stages) == set(STAGES) and all(
        stage.source
        and stage.source.strip()
        and stage.variable_usd_per_video is not None
        and stage.human_hours_per_video is not None
        and stage.automation != "unknown"
        for stage in recipe.stages
    )
    if not complete_stages or set(recipe.anchors) != set(FIT_WEIGHTS):
        return None
    return sum(
        (weight * recipe.anchors[key].grade for key, weight in FIT_WEIGHTS.items()), Decimal(0)
    )
