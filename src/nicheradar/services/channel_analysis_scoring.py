"""Opportunity Score (0-100): how exploitable the niche looks, computed on the fly from
a saved channel-analysis snapshot -- never stored, so the formula can change later
without reprocessing old analyses. See docs/superpowers/specs/2026-10-03-channel-
analysis-insights-and-scoring-design.md for the exact weights and rationale."""

import math
from typing import Any

WEIGHTS = {
    "concentration": 25.0,
    "breakout": 20.0,
    "demand": 20.0,
    "rpm": 20.0,
    "growth": 15.0,
}
RPM_MIN_MID = 0.9
RPM_MAX_MID = 13.0


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_score(snapshot: dict[str, Any]) -> dict[str, Any]:
    panorama = snapshot.get("metrics", {}).get("panorama", {})
    if panorama.get("status") != "computed":
        return {"value": None, "components": {}, "components_used": []}
    metrics = panorama["metrics"]
    components: dict[str, float | None] = {}

    hhi, top5 = metrics.get("hhi"), metrics.get("top5_share")
    components["concentration"] = (
        _clamp(((1 - hhi) + (1 - top5)) / 2 * 100) if hhi is not None and top5 is not None else None
    )

    breakout_rate = metrics.get("breakout_rate")
    components["breakout"] = _clamp(breakout_rate * 100) if breakout_rate is not None else None

    videos_by_channel = snapshot.get("comparable_videos", {}).get("videos_by_channel")
    if videos_by_channel:
        all_views = [
            v["views"]
            for videos in videos_by_channel.values()
            for v in videos
            if v.get("views") is not None
        ]
        if all_views:
            avg_views = sum(all_views) / len(all_views)
            avg_score = _clamp(math.log10(avg_views + 1) / math.log10(10_000) * 100)
            pool_score = _clamp(math.log10(sum(all_views) + 1) / math.log10(500_000) * 100)
            components["demand"] = (avg_score + pool_score) / 2
        else:
            components["demand"] = None
    else:
        components["demand"] = None

    matched_rate = snapshot.get("metrics", {}).get("matched_advertising_rate")
    if matched_rate is not None:
        midpoint = (matched_rate["low"] + matched_rate["high"]) / 2
        components["rpm"] = _clamp((midpoint - RPM_MIN_MID) / (RPM_MAX_MID - RPM_MIN_MID) * 100)
    else:
        components["rpm"] = None

    growth = snapshot.get("growth", {})
    subs_per_day = growth.get("subscribers_per_day")
    components["growth"] = (
        _clamp(subs_per_day / 50 * 100)
        if growth.get("tier") in ("measured", "lifetime_average") and subs_per_day is not None
        else None
    )

    available = {key: value for key, value in components.items() if value is not None}
    if not available:
        return {"value": None, "components": components, "components_used": []}
    total_weight = sum(WEIGHTS[key] for key in available)
    value = sum(value * WEIGHTS[key] for key, value in available.items()) / total_weight
    return {
        "value": round(value, 1),
        "components": components,
        "components_used": list(available),
    }
