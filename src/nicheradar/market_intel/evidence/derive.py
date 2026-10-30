"""Everything the code computes from model + API evidence (contract §6, §8). Pure functions."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from nicheradar.market_intel.evidence.contracts import (
    ApiEvidence,
    Earning,
    ModelEvidence,
    Money,
    Period,
    RiskFlag,
    ViewMetric,
)

DAYS_PER_MONTH = Decimal("30.4375")
REVENUE_METRICS = {"estimated_revenue", "ad_revenue"}
TIER1 = frozenset({"US", "CA", "GB", "AU", "DE", "NL", "SE", "NO", "DK", "CH", "AT", "IE", "NZ"})
PERIOD_ORDER = {"last_28d": 0, "last_90d": 1, "calendar_month": 2, "last_365d": 3}

Fx = Mapping[tuple[str, date], Decimal]  # (currency, day) -> USD per unit
Grade = Literal["A", "B", "C", "D", "E", "X"]


def to_usd(money: Money, on: date, fx: Fx) -> Decimal | None:
    """USD value, or None when no rate exists for that currency and day (contract §6.1)."""
    if money.currency == "USD":
        return money.value
    rate = fx.get((money.currency, on))
    return None if rate is None else money.value * rate


@dataclass(frozen=True)
class ObservationSet:
    scope: str
    period: Period
    image_index: int
    captured_on: date | None
    capture_age_days: int | None
    revenue_usd: Decimal
    views: Decimal
    currency: str
    days: int | None
    shorts_share: float | None = None
    previous_views: float | None = None

    @property
    def rpm_usd(self) -> Decimal:
        return self.revenue_usd / self.views * 1000 if self.views else Decimal(0)

    @property
    def monthly_revenue_usd(self) -> Decimal | None:
        return None if not self.days else self.revenue_usd * DAYS_PER_MONTH / self.days

    @property
    def monthly_views(self) -> Decimal | None:
        return None if not self.days else self.views * DAYS_PER_MONTH / self.days


def _same_period(a: Period, b: Period) -> bool:
    if a.kind == "lifetime" or b.kind == "lifetime":
        return a.kind == b.kind and a.start == b.start and a.end == b.end
    if a.start is None or a.end is None or b.start is None or b.end is None:
        return False
    if (a.start, a.end) == (b.start, b.end):
        return True
    return (
        a.kind == b.kind and abs((a.start - b.start).days) <= 1 and abs((a.end - b.end).days) <= 1
    )


def same_window(a: Period, a_image: int, b: Period, b_image: int) -> bool:
    """Same period; two undated windows only match when they come from the same capture (D8)."""
    if a.dated or b.dated:
        return _same_period(a, b)
    return a.kind == b.kind and a_image == b_image


def _capture_date(evidence: ModelEvidence, image_index: int, period: Period) -> date | None:
    image = next((i for i in evidence.images if i.index == image_index), None)
    if image is not None and image.captured_on is not None:
        return image.captured_on
    return period.end


def observation_sets(
    evidence: ModelEvidence, fx: Fx, extracted_on: date
) -> tuple[ObservationSet, ...]:
    """Pair revenue with views of the same scope and period (§6.2)."""
    sets: list[ObservationSet] = []
    revenue: list[Earning] = [e for e in evidence.earnings if e.metric in REVENUE_METRICS]
    views: list[ViewMetric] = [v for v in evidence.views if v.metric == "views"]
    for earning in revenue:
        day = earning.period.end or extracted_on
        usd = to_usd(earning.amount, day, fx)
        if usd is None:
            continue
        match = next(
            (
                v
                for v in views
                if v.scope == earning.scope
                and same_window(v.period, v.image_index, earning.period, earning.image_index)
            ),
            None,
        )
        if match is None:
            continue
        captured = _capture_date(evidence, earning.image_index, earning.period)
        sets.append(
            ObservationSet(
                scope=earning.scope,
                period=earning.period,
                image_index=earning.image_index,
                captured_on=captured,
                capture_age_days=(extracted_on - captured).days if captured else None,
                revenue_usd=usd,
                views=Decimal(str(match.value)),
                currency=earning.amount.currency,
                days=earning.period.days,
                previous_views=match.previous_value,
            )
        )
    return tuple(sets)


def select_primary(sets: tuple[ObservationSet, ...]) -> ObservationSet | None:
    """Scope all/long, preferred period, freshest capture, most views (§6.2). Never lifetime."""
    candidates = [s for s in sets if s.scope in {"all", "long"} and s.period.kind in PERIOD_ORDER]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda s: (
            PERIOD_ORDER[s.period.kind],
            s.capture_age_days if s.capture_age_days is not None else 10**9,
            -s.views,
        ),
    )


def isolated_monthly_revenue(evidence: ModelEvidence, fx: Fx, extracted_on: date) -> Decimal | None:
    """Revenue with no matching views, normalized to a month (contract §6.5, no primary set).

    Same preference as the primary set (shortest window first), channel-wide or long-form scope
    only, and only a window with a known length: a lifetime figure or a foreign currency without a
    rate cannot be normalized.
    """
    candidates: list[tuple[int, Decimal]] = []
    for earning in evidence.earnings:
        days = earning.period.days
        if (
            earning.metric not in REVENUE_METRICS
            or earning.scope not in {"all", "long"}
            or earning.period.kind not in PERIOD_ORDER
            or not days
        ):
            continue
        usd = to_usd(earning.amount, earning.period.end or extracted_on, fx)
        if usd is not None:
            candidates.append((PERIOD_ORDER[earning.period.kind], usd * DAYS_PER_MONTH / days))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def monthly_views_lower_bound(api: ApiEvidence | None, now: datetime) -> Decimal | None:
    """Views of videos published in the last 90 days, divided by 3 (contract §6.5)."""
    if api is None:
        return None
    recent = [v for v in api.recent_videos if (now - v.published_at).days <= 90]
    return Decimal(sum(v.views for v in recent)) / 3 if api.recent_videos else None


def grade(
    evidence: ModelEvidence,
    primary: ObservationSet | None,
    sets: tuple[ObservationSet, ...],
    *,
    has_api_views: bool,
    high_severity_inconsistency: bool = False,
) -> Grade:
    """Evidence grade A-E/X (contract §8)."""
    identity = evidence.identity_check
    if (
        identity.matches_api_channel == "no"
        or (identity.matches_listing_title == "no" and identity.matches_api_channel != "yes")
        or high_severity_inconsistency
    ):
        return "X"
    status = evidence.monetization.ypp_status
    has_revenue = any(e.metric in REVENUE_METRICS for e in evidence.earnings)
    if status in {"suspended", "not_eligible", "base_terms_only", "applied_pending"} or (
        status == "unknown" and not has_revenue
    ):
        return "E"
    if primary is None:
        if has_revenue or sets:
            return "C"
        return "D" if has_api_views else "E"
    if identity.matches_api_channel != "yes":
        return "C"
    age = primary.capture_age_days
    if age is None or age > 365:
        return "C"
    misses = 0
    misses += 1 if age > 120 else 0
    misses += 1 if primary.views < 10_000 else 0
    misses += 1 if (primary.days or 0) < 28 else 0
    if primary.views < 1_000 or (primary.days or 0) < 7 or misses > 1:
        return "C"
    assumed = primary.image_index in evidence.usd_symbol_images
    return "A" if misses == 0 and not assumed else "B"


def rpm_sample_eligible(
    primary: ObservationSet | None, evidence: ModelEvidence, grade_value: Grade
) -> bool:
    """R1-R9 of contract §6.4 (R9, one sample per listing, holds by construction)."""
    if primary is None or grade_value not in {"A", "B"}:
        return False
    if primary.scope == "shorts" or (primary.scope == "all" and (primary.shorts_share or 0) >= 0.1):
        return False
    if primary.days is None or not 28 <= primary.days <= 365:
        return False
    if primary.views < 10_000 or (primary.capture_age_days or 10**9) > 365:
        return False
    if evidence.identity_check.matches_api_channel != "yes":
        return False
    since = evidence.monetization.monetized_since
    if since is not None and primary.period.start is not None and since > primary.period.start:
        return False
    return evidence.monetization.ypp_status == "active"


def code_risk_flags(
    evidence: ModelEvidence,
    primary: ObservationSet | None,
    *,
    declared_income: Decimal | None,
    observed_monthly: Decimal | None,
    api: ApiEvidence | None,
    now: datetime,
    previous_views: float | None = None,
    top1_revenue_share: float | None = None,
    top1_views_share: float | None = None,
    shorts_share_of_views: float | None = None,
) -> tuple[RiskFlag, ...]:
    flags: list[RiskFlag] = []

    def add(
        code: str,
        severity: Literal["low", "medium", "high"],
        evidence_ref: tuple[int | str, ...] = (),
    ) -> None:
        flags.append(RiskFlag(code=code, severity=severity, origin="code", evidence=evidence_ref))  # type: ignore[arg-type]

    identity = evidence.identity_check
    if identity.matches_api_channel == "no" or (
        identity.matches_listing_title == "no" and identity.matches_api_channel != "yes"
    ):
        add("identity_mismatch", "high")
    if any(i.third_party_watermark for i in evidence.images):
        add("third_party_watermark", "low")
    if primary is not None and primary.currency != "USD":
        add("foreign_currency", "low", (primary.image_index,))
    if primary is not None and primary.image_index in evidence.usd_symbol_images:
        add("currency_assumed_usd", "low", (primary.image_index,))
    if primary is not None and (primary.capture_age_days or 0) > 120:
        add("stale_capture", "medium", (primary.image_index,))
    monetization = evidence.monetization
    if monetization.payments_status in {"setup_in_progress", "disabled"}:
        add("payments_not_configured", "medium")
    if monetization.ypp_status in {"suspended", "not_eligible"}:
        add("ypp_suspended", "high")
    if (
        monetization.monetized_since is not None
        and (now.date() - monetization.monetized_since).days < 90
    ):
        add("recently_monetized", "medium")
    if api is not None and (now - api.created_at).days < 180:
        add("new_channel", "medium", ("api",))
    if primary is not None and previous_views:
        if (float(primary.views) - previous_views) / previous_views * 100 < -25:
            add("declining_traffic", "medium", (primary.image_index,))
    if (top1_revenue_share or 0) > 0.5 or (top1_views_share or 0) > 0.5:
        add("single_video_dependence", "high")
    if (
        declared_income
        and observed_monthly is not None
        and observed_monthly / declared_income < Decimal("0.5")
    ):
        add("declared_income_unsupported", "medium")
    audience = evidence.audience
    if audience and any(c.pct > 85 for c in audience.countries):
        add("audience_concentrated", "low", (audience.image_index,))
    if (shorts_share_of_views or 0) > 0.5:
        add("shorts_dominant", "medium")
    if identity.manager_not_owner_seen:
        add("manager_not_owner", "medium")
    if primary is not None and primary.views < 10_000:
        add("low_sample_period", "low", (primary.image_index,))
    return tuple(flags)


def tier1_share(evidence: ModelEvidence) -> float | None:
    if evidence.audience is None or not evidence.audience.countries:
        return None
    return sum(c.pct for c in evidence.audience.countries if c.code in TIER1)
