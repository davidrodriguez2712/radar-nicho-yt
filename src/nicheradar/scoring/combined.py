"""Scores describe evidence; independent gates never authorize production."""

import math
from decimal import Decimal
from typing import Any, Literal

from nicheradar.integrations.contracts import Contract
from nicheradar.scoring.market import MarketEvaluation


def final_score(market: MarketEvaluation, fit: Decimal | None) -> float | None:
    if (
        market.score is None
        or fit is None
        or market.state not in {"provisional", "ready_for_review"}
    ):
        return None
    if (
        not fit.is_finite()
        or not 0 <= fit <= 100
        or not math.isfinite(market.score)
        or not 0 <= market.score <= 100
    ):
        raise ValueError("scores must be finite and between 0 and 100")
    return 0.65 * market.score + 0.35 * float(fit)


class CombinedEvaluation(Contract):
    method_version: str = "opportunity-v2"
    score: float | None
    confidence: Literal["insufficient", "provisional", "supported"]
    state: Literal["insufficient_evidence", "uncalibrated", "provisional", "ready_for_review"]
    resource_gate: Literal["viable", "not_viable", "not_evaluable"]
    blockers: tuple[str, ...]
    weights: dict[str, float] = {"market": 0.65, "creator_fit": 0.35}
    execution_authorized: Literal[False] = False


def combine(market: MarketEvaluation, production: dict[str, Any] | None) -> CombinedEvaluation:
    fit = (
        Decimal(str(production["score"]))
        if production
        and production.get("status") == "estimated"
        and production.get("score") is not None
        else None
    )
    score = final_score(market, fit)
    resources = production["resources"] if production else {}
    gate = resources.get("status", "not_evaluable")
    blockers = [f"resource:{key}" for key in resources.get("exceeded", [])]
    blockers.extend(f"unknown:{key}" for key in resources.get("unknown", []))
    if gate != "viable":
        blockers.append("resources_" + gate)
    if fit is None:
        blockers.append("creator_fit_incomplete")
    reviews_pending = not production or any(
        not str(value).strip() or str(value).strip().lower() in {"pending", "unknown"}
        for value in production["reviews"].values()
    )
    if reviews_pending:
        blockers.append("production_reviews_pending")
    confidence: Literal["insufficient", "provisional", "supported"] = (
        "insufficient"
        if market.confidence == "insufficient" or fit is None
        else "provisional"
        if market.confidence != "supported" or blockers
        else "supported"
    )
    state: Literal["insufficient_evidence", "uncalibrated", "provisional", "ready_for_review"] = (
        "uncalibrated"
        if market.state == "uncalibrated"
        else "insufficient_evidence"
        if confidence == "insufficient"
        else "ready_for_review"
        if confidence == "supported"
        else "provisional"
    )
    return CombinedEvaluation(
        score=score,
        confidence=confidence,
        state=state,
        resource_gate=gate,
        blockers=tuple(blockers),
    )
