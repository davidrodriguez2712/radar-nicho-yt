"""Explicit ads-only assumptions, never inferred competitor earnings or payouts."""

import math
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, StringConstraints, model_validator

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Contract

Documented = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
AdUnit = Literal["usd_ads_per_1000_views", "usd_ads_per_1000_engaged_views"]


class AdvertisingBenchmark(Contract):
    version: Documented
    source: Documented
    origin: Literal["manual_assumption", "own_analytics", "synthetic"]
    format: VideoFormat
    language: Documented
    audience_key: Documented
    audience_geography: Documented | None = None
    geography_basis: Literal["unknown", "assumed", "observed"] = "unknown"
    geography_evidence: Documented | None = None
    unit: AdUnit
    rate: EstimateRange
    revenue_scope: Literal["youtube_ads_only_after_revenue_share"]
    assumptions: Documented
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    usage: Literal["pending", "enabled", "disabled"] = "pending"
    usage_evidence: Documented | None = None
    monetization: Literal["new_channel", "unknown", "active"] = "new_channel"
    monetization_evidence: Documented | None = None

    @model_validator(mode="after")
    def compatible_units(self) -> Self:
        expected = (
            "usd_ads_per_1000_engaged_views"
            if self.format == VideoFormat.SHORTS
            else "usd_ads_per_1000_views"
        )
        if self.format == VideoFormat.UNKNOWN or self.unit != expected:
            raise ValueError("confirmed format and compatible ads-only unit required")
        if not all(math.isfinite(float(value)) for value in (self.rate.low, self.rate.high)):
            raise ValueError("rate bounds must be representable finite numbers")
        if self.valid_until <= self.observed_at:
            raise ValueError("benchmark validity must follow observation")
        if self.monetization == "active" and not self.monetization_evidence:
            raise ValueError("active monetization requires documented evidence")
        return self


class AdvertisingAssessment(Contract):
    method_version: str = "advertising-v1"
    status: Literal["unavailable", "assumed", "documented"]
    benchmark: AdvertisingBenchmark | None
    reasons: tuple[str, ...]
    scoring_value: float | None
    selector: str = "lower_bound_conservative_not_expected_revenue"
    income_condition: str = "conditional_on_eligibility_activation_and_eligible_views"
    projected_payout_usd: None = None
    limitations: tuple[str, ...] = (
        "Not competitor RPM, not a revenue forecast or monetization certification.",
        "English and channel country do not establish audience geography.",
        "Ads only; total RPM, CPM, Premium and other revenue are not interchangeable.",
    )


def assess_advertising(
    benchmark: AdvertisingBenchmark | None,
    *,
    format: VideoFormat,
    language: str,
    audience_key: str,
    synthetic: bool,
    now: datetime,
) -> AdvertisingAssessment:
    reasons = []
    if benchmark is None:
        reasons.append("no_earnings_evidence")
    else:
        if (benchmark.format, benchmark.language, benchmark.audience_key) != (
            format,
            language,
            audience_key,
        ):
            reasons.append("scope_mismatch")
        if benchmark.usage != "enabled" or not benchmark.usage_evidence:
            reasons.append("usage_not_enabled")
        if benchmark.origin == "synthetic" and not synthetic:
            reasons.append("synthetic_benchmark_for_live")
        if not benchmark.observed_at <= now < benchmark.valid_until:
            reasons.append("benchmark_not_current")
        if (
            benchmark.geography_basis == "unknown"
            or not benchmark.audience_geography
            or not benchmark.geography_evidence
        ):
            reasons.append("audience_geography_unknown")
    return AdvertisingAssessment(
        status="unavailable"
        if reasons
        else "assumed"
        if benchmark
        and (benchmark.origin != "own_analytics" or benchmark.geography_basis != "observed")
        else "documented",
        benchmark=benchmark,
        reasons=tuple(reasons),
        scoring_value=float(benchmark.rate.low) if benchmark and not reasons else None,
    )
