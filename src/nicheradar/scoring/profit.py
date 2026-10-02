"""Monthly profit range: real competitor view spread x researched RPM, minus real cost.

Never a single-channel projection: the range is bounded by the best and worst channel
already observed competing in the niche, not an assumption fed in about a new channel.
"""

from decimal import Decimal
from typing import Literal, Self

from pydantic import model_validator

from nicheradar.domain.production import EstimateRange
from nicheradar.integrations.contracts import Contract
from nicheradar.scoring.advertising import AdvertisingBenchmark


class SignedRange(Contract):
    """Like EstimateRange, but allows negative bounds: a profit estimate can be a loss."""

    low: Decimal
    high: Decimal

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.low > self.high:
            raise ValueError("low exceeds high")
        return self


LIMITATIONS = (
    "Rango entre el canal mejor y peor posicionado ya compitiendo en este nicho; un canal "
    "nuevo no tiene garantía de alcanzar ni siquiera el límite inferior, porque el peor "
    "canal observado ya tiene audiencia propia.",
    "La tasa publicitaria es una asunción manual investigada, no datos propios de "
    "monetización de este canal.",
    "No certifica elegibilidad de monetización ni ingresos por membresías o Premium.",
)


class ProfitEstimate(Contract):
    method_version: str = "profit-v1"
    status: Literal["estimated", "incomplete"]
    missing: tuple[str, ...]
    monthly_views: EstimateRange | None
    monthly_revenue_usd: EstimateRange | None
    monthly_cost_usd: EstimateRange | None
    monthly_profit_usd: SignedRange | None
    limitations: tuple[str, ...] = LIMITATIONS


def estimate_profit(
    *,
    best_channel_views_per_day: float | None,
    worst_channel_views_per_day: float | None,
    videos_per_month: int | None,
    advertising: AdvertisingBenchmark | None,
    monthly_cost_usd: EstimateRange | None,
) -> ProfitEstimate:
    missing = []
    if best_channel_views_per_day is None or worst_channel_views_per_day is None:
        missing.append("channel_view_rate")
    if videos_per_month is None:
        missing.append("videos_per_month")
    if advertising is None:
        missing.append("advertising_rate")
    if monthly_cost_usd is None:
        missing.append("production_cost")
    if missing:
        return ProfitEstimate(
            status="incomplete",
            missing=tuple(missing),
            monthly_views=None,
            monthly_revenue_usd=None,
            monthly_cost_usd=monthly_cost_usd,
            monthly_profit_usd=None,
        )
    assert best_channel_views_per_day is not None
    assert worst_channel_views_per_day is not None
    assert videos_per_month is not None
    assert advertising is not None
    assert monthly_cost_usd is not None
    views_low = Decimal(str(worst_channel_views_per_day * 30 * videos_per_month))
    views_high = Decimal(str(best_channel_views_per_day * 30 * videos_per_month))
    if views_low > views_high:
        views_low, views_high = views_high, views_low
    revenue_low = views_low * advertising.rate.low / 1000
    revenue_high = views_high * advertising.rate.high / 1000
    profit_low = revenue_low - monthly_cost_usd.high
    profit_high = revenue_high - monthly_cost_usd.low
    return ProfitEstimate(
        status="estimated",
        missing=(),
        monthly_views=EstimateRange(low=views_low, high=views_high),
        monthly_revenue_usd=EstimateRange(low=revenue_low, high=revenue_high),
        monthly_cost_usd=monthly_cost_usd,
        monthly_profit_usd=SignedRange(
            low=min(profit_low, profit_high), high=max(profit_low, profit_high)
        ),
    )
