"""RPM recalibration (contract §7). The catalog stays as the prior and is never overwritten."""

from dataclasses import dataclass
from typing import Literal

PRIOR_WEIGHT = 5  # k: the catalog midpoint counts as five observed channels
MIN_BLENDED = 3
MIN_OBSERVED = 5


@dataclass(frozen=True)
class RpmSample:
    listing_id: str
    rpm_usd: float
    views: float
    capture_age_days: int
    grade: Literal["A", "B"]

    @property
    def weight(self) -> float:
        grade_factor = 1.0 if self.grade == "A" else 0.7
        return (
            min(self.views / 100_000, 1.0)
            * max(1 - self.capture_age_days / 365, 0.0)
            * grade_factor
        )


@dataclass(frozen=True)
class RpmEstimate:
    state: Literal["catalog", "blended", "observed"]
    rpm_usd: float
    n: int
    p25: float | None
    p75: float | None
    out_of_catalog_range: bool
    listing_ids: tuple[str, ...]


def weighted_percentile(samples: list[RpmSample], quantile: float) -> float:
    ordered = sorted(samples, key=lambda s: s.rpm_usd)
    total = sum(s.weight for s in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2].rpm_usd
    cumulative = 0.0
    for sample in ordered:
        cumulative += sample.weight
        if cumulative >= quantile * total:
            return sample.rpm_usd
    return ordered[-1].rpm_usd


def recalibrate(samples: list[RpmSample], rate_low: float, rate_high: float) -> RpmEstimate:
    midpoint = (rate_low + rate_high) / 2
    usable = [s for s in samples if s.weight > 0]
    n = len(usable)
    ids = tuple(s.listing_id for s in usable)
    if n < MIN_BLENDED:
        return RpmEstimate("catalog", midpoint, n, None, None, False, ids)
    median = weighted_percentile(usable, 0.5)
    p25, p75 = weighted_percentile(usable, 0.25), weighted_percentile(usable, 0.75)
    if n < MIN_OBSERVED:
        blended = (n * median + PRIOR_WEIGHT * midpoint) / (n + PRIOR_WEIGHT)
        return RpmEstimate(
            "blended", blended, n, p25, p75, not rate_low <= median <= rate_high, ids
        )
    return RpmEstimate("observed", median, n, p25, p75, not rate_low <= median <= rate_high, ids)
