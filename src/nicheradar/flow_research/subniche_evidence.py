# src/nicheradar/flow_research/subniche_evidence.py
"""The frozen evidence package of a research order that comes from a sub-niche hypothesis."""

from typing import Any

from pydantic_core import to_jsonable_python

from nicheradar.flow_research.gates import Gates

MEDIUM_CONFIDENCE_FROM = 10  # channels included in the measurement; assumption, not measured


def build_subniche_evidence(
    detail: dict[str, Any], gates: Gates, gate_override: dict[str, str] | None = None
) -> dict[str, Any]:
    """Freeze the hypothesis, its latest measurement and the channels still retained.

    There is no backlog score, so ``niche`` is ``None`` and the niche gates do not apply; the
    minutes, calibration and rights gates still run when the dossier arrives.
    """
    hypothesis = detail["hypothesis"]
    measurement = detail["measurement"]
    included = measurement["included"]
    package: dict[str, Any] = {
        "source": "subniche",
        "niche": None,
        "subniche": {
            key: hypothesis[key]
            for key in (
                "slug",
                "label",
                "family",
                "parent_niche_slug",
                "language",
                "format",
                "finalist",
                "queries",
            )
        },
        "measurement": measurement,
        "channels": detail["channels"],
        "channels_available": detail["channels_available"],
        "language": hypothesis["language"],
        "language_mix": [{"language": hypothesis["language"], "share_pct": 100}],
        "confidence": "media" if included >= MEDIUM_CONFIDENCE_FROM else "baja",
        "gate": {
            "min_automation": gates.min_automation,
            "max_human_minutes": gates.max_human_minutes,
            "max_calibration_hours": gates.max_calibration_hours,
            "block_high_policy_risk": gates.block_high_policy_risk,
            "automation_known": False,
            "policy_risk_level": None,
            "passed": True,
            "reasons": [],
        },
    }
    if gate_override is not None:
        package["gate_override"] = gate_override
    frozen: dict[str, Any] = to_jsonable_python(package)
    return frozen
