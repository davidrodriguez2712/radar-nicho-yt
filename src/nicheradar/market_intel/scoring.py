# src/nicheradar/market_intel/scoring.py
"""Pure scoring over seller-declared data. Scores never carry confidence: it is separate."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Literal

OPPORTUNITY_VERSION = "opp-v1"
AUTOMATION_VERSION = "auto-v1"
AUTOMATION_WEIGHTS = {
    "faceless": 30.0,
    "scriptable": 25.0,
    "visuals_automatable": 20.0,
    "synthetic_voice_ok": 15.0,
    "low_copyright_dependence": 10.0,
}
OPPORTUNITY_WEIGHTS = {
    "profitability": 30.0,
    "efficiency": 30.0,
    "validation": 25.0,
    "dynamics": 15.0,
}
MINIMUM_INCOME_LISTINGS = 3
MINIMUM_AUTOMATION_TRAITS = 3
SUBS_MISMATCH_TOLERANCE = 0.25
RPM_FLOOR, RPM_CEILING = 1.0, 12.0
# price / annual income, in years: 6 months of income scores 0 and 30 months scores 100.
MULTIPLE_LOW, MULTIPLE_HIGH = 0.5, 2.5


@dataclass(frozen=True)
class ListingFacts:
    status: str
    price_usd: float | None
    subscribers: int | None
    income_usd: float | None
    expense_usd: float | None
    verification: str | None
    days_since_seen: int
    traits: dict[str, int | None]


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def log_scale(value: float | None, low: float, high: float) -> float | None:
    if value is None or value <= 0:
        return None
    span = math.log10(high) - math.log10(low)
    return clamp((math.log10(value) - math.log10(low)) / span * 100)


def outlier_mask(values: list[float]) -> list[bool]:
    """Modified z-score (MAD) > 3.5; too few samples or zero spread never flag anything."""
    if len(values) < 5:
        return [False] * len(values)
    center = median(values)
    spread = median(abs(value - center) for value in values)
    if spread == 0:
        return [False] * len(values)
    return [abs(0.6745 * (value - center) / spread) > 3.5 for value in values]


def niche_metrics(facts: Sequence[ListingFacts]) -> dict[str, Any]:
    # "$0 income" means "not reported": only strictly positive income counts as evidence.
    usable = [
        (fact, fact.income_usd)
        for fact in facts
        if fact.income_usd is not None
        and fact.income_usd > 0
        and fact.verification not in ("mismatch", "not_found")
    ]
    ratios = [
        income / (fact.subscribers / 1000) if fact.subscribers else None for fact, income in usable
    ]
    measured = [(index, ratio) for index, ratio in enumerate(ratios) if ratio is not None]
    flags = outlier_mask([ratio for _, ratio in measured])
    dropped = {index for (index, _), flag in zip(measured, flags, strict=True) if flag}
    kept = [pair for index, pair in enumerate(usable) if index not in dropped]
    kept_ratios = [
        ratio for index, ratio in enumerate(ratios) if index not in dropped and ratio is not None
    ]
    incomes = [income for _, income in kept]
    margins = [
        (income - fact.expense_usd) / income
        for fact, income in kept
        if fact.expense_usd is not None and fact.expense_usd > 0  # $0 means "not reported"
    ]
    multiples = [
        fact.price_usd / (income * 12)
        for fact, income in kept
        if fact.price_usd and fact.price_usd > 0
    ]
    total = len(facts)
    disappeared = sum(1 for fact in facts if fact.status == "disappeared")
    verified = sum(1 for fact, _ in kept if fact.verification == "verified")
    return {
        "n_listings": total,
        "n_active": total - disappeared,
        "n_income": len(kept),
        "n_outliers": len(dropped),
        "income_median": median(incomes) if incomes else None,
        "margin_median": median(margins) if margins else None,
        "income_per_1k_subs_median": median(kept_ratios) if kept_ratios else None,
        "multiple_median": median(multiples) if multiples else None,
        "disappearance_rate": disappeared / total if total else 0.0,
        "verified_share": verified / len(kept) if kept else 0.0,
        "recent_share": sum(1 for fact in facts if fact.days_since_seen <= 14) / total
        if total
        else 0.0,
    }


def opportunity_score(metrics: dict[str, Any], rpm_mid: float | None) -> dict[str, Any]:
    base: dict[str, Any] = {"version": OPPORTUNITY_VERSION}
    if metrics["n_income"] < MINIMUM_INCOME_LISTINGS:
        return base | {
            "value": None,
            "state": "insufficient_evidence",
            "components": {},
            "components_used": [],
        }
    income = log_scale(metrics["income_median"], 50, 3000) or 0.0
    margin = metrics["margin_median"]
    profitability = income if margin is None else 0.7 * income + 0.3 * clamp(margin * 100)
    parts = [
        part
        for part in (
            log_scale(metrics["income_per_1k_subs_median"], 0.5, 50),
            None
            if rpm_mid is None
            else clamp((rpm_mid - RPM_FLOOR) / (RPM_CEILING - RPM_FLOOR) * 100),
        )
        if part is not None
    ]
    efficiency = mean(parts) if parts else None
    supply = clamp(metrics["n_listings"] / 10 * 100)
    multiple = metrics["multiple_median"]
    validation = (
        supply
        if multiple is None
        else 0.6 * clamp((multiple - MULTIPLE_LOW) / (MULTIPLE_HIGH - MULTIPLE_LOW) * 100)
        + 0.4 * supply
    )
    dynamics = clamp(metrics["disappearance_rate"] / 0.3 * 100)
    components: dict[str, float | None] = {
        "profitability": profitability,
        "efficiency": efficiency,
        "validation": validation,
        "dynamics": dynamics,
    }
    used = [name for name, value in components.items() if value is not None]
    weight = sum(OPPORTUNITY_WEIGHTS[name] for name in used)
    total = sum(OPPORTUNITY_WEIGHTS[name] * (components[name] or 0.0) for name in used)
    return base | {
        "value": round(total / weight, 1),
        "state": "scored",
        "components": {
            name: round(value, 1) for name, value in components.items() if value is not None
        },
        "components_used": used,
    }


def confidence(metrics: dict[str, Any]) -> Literal["alta", "media", "baja"]:
    if metrics["n_income"] < MINIMUM_INCOME_LISTINGS:
        return "baja"
    points = (
        min(metrics["n_income"] / 10, 1) * 0.5
        + metrics["verified_share"] * 0.3
        + metrics["recent_share"] * 0.2
    )
    return "alta" if points >= 0.7 else "media" if points >= 0.4 else "baja"


def _trait_values(
    key: str, listing_traits: Sequence[dict[str, int | None]], prior: dict[str, int | None] | None
) -> list[int]:
    fallback = prior.get(key) if prior else None
    if not listing_traits:
        return [fallback] if fallback is not None else []
    values = [
        traits.get(key) if traits.get(key) is not None else fallback for traits in listing_traits
    ]
    return [value for value in values if value is not None]


def automation_score(
    listing_traits: Sequence[dict[str, int | None]], prior: dict[str, int | None] | None
) -> dict[str, Any]:
    means = {
        key: (mean(values) if (values := _trait_values(key, listing_traits, prior)) else None)
        for key in (*AUTOMATION_WEIGHTS, "policy_risk")
    }
    available = [key for key in AUTOMATION_WEIGHTS if means[key] is not None]
    value: float | None = None
    if len(available) >= MINIMUM_AUTOMATION_TRAITS:
        weight = sum(AUTOMATION_WEIGHTS[key] for key in available)
        earned = sum(AUTOMATION_WEIGHTS[key] * (means[key] or 0.0) / 2 for key in available)
        value = round(earned / weight * 100, 1)
    risk = means["policy_risk"]
    level = None if risk is None else "bajo" if risk < 0.67 else "medio" if risk < 1.34 else "alto"
    return {
        "version": AUTOMATION_VERSION,
        "value": value,
        "components": {key: means[key] for key in AUTOMATION_WEIGHTS},
        "policy_risk": {"mean": risk, "level": level},
    }
