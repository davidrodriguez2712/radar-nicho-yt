import math
from typing import Literal, Self

from pydantic import Field, model_validator

from nicheradar.domain.profile import VideoFormat
from nicheradar.features.metrics import CohortMetrics
from nicheradar.integrations.contracts import Contract
from nicheradar.scoring.advertising import AdUnit, AdvertisingAssessment, Documented


class References(Contract):
    version: Documented
    format: VideoFormat
    source: Documented
    synthetic: bool
    reviewed: bool
    demand_p90_by_age: dict[str, float]
    trend_p90_abs_change: float | None = Field(default=None, gt=0)
    monetization_p90: float | None = Field(default=None, gt=0)
    monetization_unit: AdUnit | None = None
    monetization_geography: Documented | None = None

    @model_validator(mode="after")
    def positive_references(self) -> Self:
        if self.format == VideoFormat.UNKNOWN or not self.demand_p90_by_age:
            raise ValueError("format and age references required")
        if any(not math.isfinite(value) or value <= 0 for value in self.demand_p90_by_age.values()):
            raise ValueError("references must be positive and finite")
        return self


class MarketEvaluation(Contract):
    method_version: str = "market-v2"
    reference_version: str | None = None
    state: Literal["insufficient_evidence", "uncalibrated", "provisional", "ready_for_review"]
    confidence: Literal["insufficient", "provisional", "supported"]
    components: dict[str, float | None]
    weight_coverage: float
    score: float | None
    missing: tuple[str, ...]
    limitations: tuple[str, ...]


WEIGHTS = {"D": 0.25, "B": 0.30, "C": 0.20, "T": 0.15, "M": 0.10}


def normalize(value: float, reference: float) -> float:
    if not math.isfinite(value) or value < 0 or not math.isfinite(reference) or reference <= 0:
        raise ValueError("invalid normalization values")
    return 100 * min(1, math.log1p(value) / math.log1p(reference))


def evaluate_market(
    metrics: CohortMetrics,
    format: VideoFormat,
    references: References | None,
    *,
    synthetic: bool,
    advertising: AdvertisingAssessment | None = None,
    relevance_reviewed: bool = False,
) -> MarketEvaluation:
    components: dict[str, float | None] = {
        "D": None,
        "B": 100 * metrics.breakout_rate if metrics.breakout_rate is not None else None,
        "C": metrics.concentration_score,
        "T": None,
        "M": None,
    }
    calibrated = (
        references is not None
        and references.format == format
        and references.reviewed
        and (synthetic or not references.synthetic)
    )
    if calibrated and references:
        demand = [
            normalize(value, references.demand_p90_by_age[band])
            for band, value in metrics.demand_by_age.items()
            if value is not None and band in references.demand_p90_by_age
        ]
        # Require reference coverage for every contributing age stratum.
        if demand and len(demand) == len(metrics.demand_by_age):
            components["D"] = sum(demand) / len(demand)
        if metrics.trend_relative_change is not None and references.trend_p90_abs_change:
            components["T"] = 50 + 50 * math.tanh(
                metrics.trend_relative_change / references.trend_p90_abs_change
            )
        if (
            advertising is not None
            and advertising.scoring_value is not None
            and advertising.benchmark is not None
            and advertising.benchmark.format == format
            and (synthetic or advertising.benchmark.origin != "synthetic")
            and references.monetization_p90
            and references.monetization_unit == advertising.benchmark.unit
            and references.monetization_geography == advertising.benchmark.audience_geography
        ):
            components["M"] = normalize(advertising.scoring_value, references.monetization_p90)
    enough = (
        metrics.videos >= 20
        and metrics.channels >= 5
        and metrics.breakout_classified >= 10
        and metrics.breakout_channels >= 3
        and metrics.breakout_coverage is not None
        and metrics.breakout_coverage >= 0.8
        and components["B"] is not None
        and components["C"] is not None
        and bool(metrics.demand_by_age)
    )
    missing = tuple(key for key, value in components.items() if value is None)
    weight = sum(WEIGHTS[key] for key, value in components.items() if value is not None)
    score = (
        sum(WEIGHTS[key] * value for key, value in components.items() if value is not None) / weight
        if enough and calibrated and components["D"] is not None
        else None
    )
    provisional = (
        bool(missing)
        or not relevance_reviewed
        or advertising is None
        or advertising.status != "documented"
    )
    state: Literal["insufficient_evidence", "uncalibrated", "provisional", "ready_for_review"] = (
        "insufficient_evidence"
        if not enough
        else "uncalibrated"
        if score is None
        else "provisional"
        if provisional
        else "ready_for_review"
    )
    confidence: Literal["insufficient", "provisional", "supported"] = (
        "insufficient"
        if not enough
        else "provisional"
        if provisional or not calibrated
        else "supported"
    )
    return MarketEvaluation(
        state=state,
        confidence=confidence,
        components=components,
        score=score,
        reference_version=references.version if calibrated and references else None,
        missing=missing,
        weight_coverage=weight,
        limitations=(
            "Heuristic score, not a probability of success.",
            "Advertising estimates are conditional on monetization eligibility.",
        )
        + (("No reviewed real calibration available.",) if not calibrated else ()),
    )
