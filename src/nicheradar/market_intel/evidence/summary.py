"""Assemble the `derived` block stored with each extraction (contract §6, §8).

Pure and recomputable from the stored `model_evidence`; it never uses YouTube API data, so the
stored row carries no data subject to the 30-day API retention rule.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from nicheradar.market_intel.evidence.contracts import ModelEvidence, RiskFlag
from nicheradar.market_intel.evidence.derive import (
    Fx,
    ObservationSet,
    _same_period,
    code_risk_flags,
    grade,
    observation_sets,
    rpm_sample_eligible,
    select_primary,
    tier1_share,
    to_usd,
)

CENT = Decimal("0.01")
RPM_PLACES = Decimal("0.0001")
RPM_CHECK_TOLERANCE = 0.15


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(CENT))


def _set_row(found: ObservationSet) -> dict[str, Any]:
    return {
        "image_index": found.image_index,
        "scope": found.scope,
        "period": {
            "kind": found.period.kind,
            "start": found.period.start.isoformat() if found.period.start else None,
            "end": found.period.end.isoformat() if found.period.end else None,
        },
        "days": found.days,
        "capture_age_days": found.capture_age_days,
        "currency": found.currency,
        "revenue_usd": _money(found.revenue_usd),
        "views": format(found.views.normalize(), "f"),
        "rpm_usd": str(found.rpm_usd.quantize(RPM_PLACES)),
        "monthly_revenue_usd": _money(found.monthly_revenue_usd),
        "monthly_views": None if found.monthly_views is None else str(round(found.monthly_views)),
    }


def _concentration(
    evidence: ModelEvidence, primary: ObservationSet | None, fx: Fx
) -> tuple[float | None, float | None]:
    if primary is None:
        return None, None
    rows = [t for t in evidence.top_content if _same_period(t.period, primary.period)]
    if not rows:
        return None, None
    revenues = [
        usd
        for row in rows
        if row.revenue is not None
        and (usd := to_usd(row.revenue, row.period.end or primary.period.end, fx)) is not None  # type: ignore[arg-type]
    ]
    revenue_share = (
        float(max(revenues) / primary.revenue_usd) if revenues and primary.revenue_usd else None
    )
    views = [row.views for row in rows if row.views is not None]
    views_share = float(max(views) / float(primary.views)) if views and primary.views else None
    return revenue_share, views_share


def _rpm_check(evidence: ModelEvidence, primary: ObservationSet | None) -> float | None:
    if primary is None or primary.rpm_usd == 0:
        return None
    for rate in evidence.rates:
        if (
            rate.metric == "rpm"
            and rate.scope == primary.scope
            and (rate.currency in (None, "USD"))
            and _same_period(rate.period, primary.period)
            and rate.value > 0
        ):
            return float((primary.rpm_usd - Decimal(str(rate.value))) / Decimal(str(rate.value)))
    return None


def build_derived(
    evidence: ModelEvidence,
    *,
    fx: Fx,
    extracted_at: datetime,
    declared_income: Decimal | None,
) -> dict[str, Any]:
    sets = observation_sets(evidence, fx, extracted_at.date())
    primary = select_primary(sets)
    has_revenue = any(e.metric in {"estimated_revenue", "ad_revenue"} for e in evidence.earnings)
    observed_monthly = primary.monthly_revenue_usd if primary else None
    if primary is not None:
        income_level = "L1"
    elif has_revenue and evidence.earnings:
        income_level = "L2"
        observed_monthly = None
    else:
        income_level = "L4" if declared_income else "L5"
    rpm_check = _rpm_check(evidence, primary)
    inconsistent = any(
        flag.code == "edited_or_inconsistent_numbers" and flag.severity == "high"
        for flag in evidence.risk_flags
    )
    evidence_grade = grade(
        evidence, primary, sets, has_api_views=False, high_severity_inconsistency=inconsistent
    )
    revenue_share, views_share = _concentration(evidence, primary, fx)
    ratio = (
        float(observed_monthly / declared_income)
        if observed_monthly is not None and declared_income
        else None
    )
    flags = code_risk_flags(
        evidence,
        primary,
        declared_income=declared_income,
        observed_monthly=observed_monthly,
        api=None,
        now=extracted_at,
        previous_views=primary.previous_views if primary else None,
        top1_revenue_share=revenue_share,
        top1_views_share=views_share,
    )
    if rpm_check is not None and abs(rpm_check) > RPM_CHECK_TOLERANCE:
        flags = (
            *flags,
            *code_flag("edited_or_inconsistent_numbers", "medium", primary),
        )
    eligible = rpm_sample_eligible(primary, evidence, evidence_grade)
    return {
        "observation_sets": [_set_row(s) for s in sets],
        "primary": _set_row(primary) if primary else None,
        "income_level": income_level,
        "observed_monthly_income_usd": _money(observed_monthly),
        "declared_vs_observed_ratio": ratio,
        "evidence_grade": evidence_grade,
        "scoring_eligible_income": evidence_grade in {"A", "B", "C"},
        "rpm_usd": str(primary.rpm_usd.quantize(RPM_PLACES)) if primary else None,
        "rpm_check": rpm_check,
        "rpm_sample_eligible": eligible,
        "tier1_share": tier1_share(evidence),
        "top1_revenue_share": revenue_share,
        "top1_views_share": views_share,
        "risk_flags": [f.model_dump(mode="json") for f in flags],
    }


def code_flag(code: str, severity: str, primary: ObservationSet | None) -> tuple[Any, ...]:
    refs: tuple[int | str, ...] = (primary.image_index,) if primary else ()
    return (RiskFlag(code=code, severity=severity, origin="code", evidence=refs),)  # type: ignore[arg-type]
