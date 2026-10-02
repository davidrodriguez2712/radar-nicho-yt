"""Compare retained snapshots without inventing causal attribution or hiding method changes."""

from typing import Any


def method_inputs(evaluation: dict[str, Any]) -> dict[str, Any]:
    snapshot = evaluation.get("explanation") or {}
    production = snapshot.get("production") or {}
    configuration = snapshot.get("scoring_configuration") or {}
    return {
        "evaluation": evaluation.get("method_version"),
        "reference_version": evaluation.get("reference_version"),
        "references": configuration.get("references"),
        "metrics": snapshot.get("metrics", {}).get("method_version"),
        "market": snapshot.get("market", {}).get("method_version"),
        "creator_fit": production.get("rubric_version"),
        "combined": snapshot.get("combined", {}).get("method_version"),
        "weights": snapshot.get("combined", {}).get("weights"),
        "context": snapshot.get("method_context"),
    }


def component_set(evaluation: dict[str, Any]) -> list[str]:
    return sorted(
        key
        for key, value in (evaluation.get("explanation") or {})
        .get("market", {})
        .get("components", {})
        .items()
        if value is not None
    )


def compare_evaluations(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "method_version": "comparison-v1",
        "previous_id": str(previous["id"]) if previous else None,
        "current_id": str(current["id"]),
        "changes": [],
        "deltas": [],
        "comparable": False,
        "limitations": [
            "Changes describe retained snapshots, not proven causes or investment advice."
        ],
    }
    if not current.get("evidence_available", not current.get("expired_at")) or (
        previous and not previous.get("evidence_available", not previous.get("expired_at"))
    ):
        return result | {"changes": ["evidence_unavailable"]}
    if previous is None:
        return result | {"changes": ["first_evaluation"]}
    old, new = previous.get("explanation") or {}, current.get("explanation") or {}
    changes = result["changes"]
    if any(previous.get(key) != current.get(key) for key in ("source_mode", "profile_id")):
        changes.append("scope_changed")
    if method_inputs(previous) != method_inputs(current):
        changes.append("method_changed")
    if component_set(previous) != component_set(current):
        changes.append("component_coverage_changed")
    result["comparable"] = not changes
    old_metrics = {
        key: value for key, value in old.get("metrics", {}).items() if key != "method_version"
    }
    new_metrics = {
        key: value for key, value in new.get("metrics", {}).items() if key != "method_version"
    }
    if old_metrics != new_metrics or old.get("temporal") != new.get("temporal"):
        changes.append("data_changed")

    def assumptions(snapshot: dict[str, Any]) -> dict[str, Any]:
        production = snapshot.get("production") or {}
        configuration = snapshot.get("scoring_configuration") or {}
        return {
            "plan": production.get("plan"),
            "profile": production.get("profile"),
            "advertising": configuration.get("advertising"),
            "relevance_review": configuration.get("relevance_review"),
        }

    if assumptions(old) != assumptions(new):
        changes.append("assumptions_changed")
    scores_changed = False
    for field in ("market_score", "creator_fit", "final_score", "state", "confidence"):
        before, after = previous.get(field), current.get(field)
        if before != after:
            scores_changed |= field.endswith("score") or field == "creator_fit"
            result["deltas"].append(
                {
                    "field": field,
                    "before": before,
                    "after": after,
                    "delta": after - before
                    if result["comparable"]
                    and isinstance(before, (int, float))
                    and isinstance(after, (int, float))
                    else None,
                }
            )
    for key in sorted(set(old_metrics) | set(new_metrics)):
        before, after = old_metrics.get(key), new_metrics.get(key)
        if before != after:
            result["deltas"].append(
                {
                    "field": "metrics." + key,
                    "before": before,
                    "after": after,
                    "delta": after - before
                    if result["comparable"]
                    and isinstance(before, (int, float))
                    and isinstance(after, (int, float))
                    else None,
                }
            )
    if scores_changed and not changes:
        changes.append("unexplained_score_change")
    if not changes:
        changes.append("evaluation_state_changed" if result["deltas"] else "unchanged")
    return result
