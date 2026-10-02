from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from nicheradar.domain.production import STAGES, EstimateRange, Recipe
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Contract


class SharedTool(Contract):
    key: str
    monthly_usd: EstimateRange | None
    monthly_capacity: Decimal | None = Field(default=None, ge=0)
    capacity_unit: str
    source: str | None = None
    excluded_existing_subscription: bool = False


class Proposal(Contract):
    channel_key: str
    opportunity_keys: tuple[str, ...]
    recipe: Recipe
    videos_per_month: int = Field(gt=0)


class Scenario(Contract):
    name: str
    proposals: tuple[Proposal, ...]
    tools: tuple[SharedTool, ...]
    radar_monthly_usd: EstimateRange | None
    reserve_usd: Decimal = Field(ge=0)
    weekly_hours_override: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def unique_tools(self) -> Self:
        if len({tool.key for tool in self.tools}) != len(self.tools):
            raise ValueError("shared tools must be declared once")
        return self


class ScenarioResult(Contract):
    status: Literal["viable", "not_viable", "not_evaluable"]
    monthly_usd: EstimateRange | None
    monthly_hours: EstimateRange | None
    monthly_hours_available: Decimal
    tool_usage: dict[str, Decimal]
    exceeded: tuple[str, ...]
    unknown: tuple[str, ...]
    channel_count: int
    estimates_only: bool = True
    weeks_per_month: str = "52/12"


def simulate(scenario: Scenario, profile: CreatorProfile) -> ScenarioResult:
    usd_low = usd_high = max(scenario.reserve_usd, profile.monthly_reserve_usd)
    hours_low = hours_high = Decimal(0)
    unknown: list[str] = []
    exceeded: list[str] = []
    tools = {tool.key: tool for tool in scenario.tools}
    usage: dict[str, Decimal] = {}
    if scenario.radar_monthly_usd is None:
        unknown.append("radar_cost")
    else:
        usd_low += scenario.radar_monthly_usd.low
        usd_high += scenario.radar_monthly_usd.high
    for proposal in scenario.proposals:
        recipe = proposal.recipe
        missing_stages = set(STAGES) - {stage.name for stage in recipe.stages}
        unknown.extend(
            f"{proposal.channel_key}:{name}:missing_stage" for name in sorted(missing_stages)
        )
        volume = Decimal(proposal.videos_per_month) * (1 + recipe.rework_margin)
        for stage in recipe.stages:
            key = f"{proposal.channel_key}:{recipe.format}:{stage.name}"
            if not stage.source or not stage.source.strip():
                unknown.append(f"{key}:source")
            if stage.variable_usd_per_video is None:
                unknown.append(f"{key}:cost")
            else:
                usd_low += stage.variable_usd_per_video.low * volume
                usd_high += stage.variable_usd_per_video.high * volume
            if stage.human_hours_per_video is None:
                unknown.append(f"{key}:hours")
            else:
                hours_low += stage.human_hours_per_video.low * volume
                hours_high += stage.human_hours_per_video.high * volume
            if stage.tool_key:
                if stage.tool_key not in tools or stage.tool_units_per_video is None:
                    unknown.append(f"{key}:tool_capacity")
                else:
                    if (
                        not stage.tool_capacity_unit
                        or stage.tool_capacity_unit != tools[stage.tool_key].capacity_unit
                    ):
                        unknown.append(f"{key}:capacity_unit")
                    usage[stage.tool_key] = (
                        usage.get(stage.tool_key, Decimal(0)) + stage.tool_units_per_video * volume
                    )
    for key, tool in tools.items():
        used = usage.get(key, Decimal(0))
        if not tool.source or not tool.source.strip():
            unknown.append(f"{key}:source")
        if tool.excluded_existing_subscription and tool.key not in profile.excluded_subscriptions:
            unknown.append(f"{key}:unconfirmed_exclusion")
        elif not tool.excluded_existing_subscription:
            if tool.monthly_usd is None:
                unknown.append(f"{key}:subscription_cost")
            else:
                usd_low += tool.monthly_usd.low
                usd_high += tool.monthly_usd.high
        if tool.monthly_capacity is None and used > 0:
            unknown.append(f"{key}:capacity")
        elif tool.monthly_capacity is not None and used > tool.monthly_capacity:
            exceeded.append(f"{key}:capacity")
    available = (scenario.weekly_hours_override or profile.weekly_hours) * Decimal(52) / Decimal(12)
    if usd_high > profile.monthly_ceiling_usd:
        exceeded.append("monthly_usd")
    if hours_high > available:
        exceeded.append("monthly_hours")
    return ScenarioResult(
        status="not_evaluable" if unknown else "not_viable" if exceeded else "viable",
        monthly_usd=None
        if any(
            "cost" in issue or "missing_stage" in issue or "source" in issue or "exclusion" in issue
            for issue in unknown
        )
        else EstimateRange(low=usd_low, high=usd_high),
        monthly_hours=None
        if any("hours" in issue or "missing_stage" in issue for issue in unknown)
        else EstimateRange(low=hours_low, high=hours_high),
        monthly_hours_available=available,
        tool_usage=usage,
        exceeded=tuple(exceeded),
        unknown=tuple(unknown),
        channel_count=len({proposal.channel_key for proposal in scenario.proposals}),
    )
