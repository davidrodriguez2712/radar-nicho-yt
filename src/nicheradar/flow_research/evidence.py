# src/nicheradar/flow_research/evidence.py
"""Who may open a research request, and the frozen evidence package it carries."""

from typing import Any

from pydantic_core import to_jsonable_python

from nicheradar.flow_research.gates import Gates, annotation

MAX_EVIDENCE_LISTINGS = 10
REASONS = {
    "not_tentative": "El nicho debe estar marcado como tentativo.",
    "no_evidence": "Falta evidencia: el nicho no tiene score de Opportunity y de Automatización.",
}


def ineligible_reason(niche: dict[str, Any]) -> str | None:
    """``niche`` is a backlog entry (also the ``niche`` of ``niche_detail``)."""
    if niche["decision"]["decision"] != "tentativo":
        return "not_tentative"
    if niche["opportunity"]["value"] is None or niche["automation"]["value"] is None:
        return "no_evidence"
    return None


def build_evidence(
    detail: dict[str, Any],
    language: str,
    gates: Gates,
    gate_override: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Freeze scores, metrics, language, gate result and the top verified listings."""
    verified = [item for item in detail["listings"] if item.get("verification") == "verified"]
    package = {
        "niche": detail["niche"],
        "language": language,
        "language_mix": detail["language_mix"],
        "verified_listings": verified[:MAX_EVIDENCE_LISTINGS],
        "verified_count": len(verified),
        "listing_count": len(detail["listings"]),
        "history": detail["history"],
        "gate": annotation(detail["niche"], gates),
    }
    if gate_override is not None:
        package["gate_override"] = gate_override
    frozen: dict[str, Any] = to_jsonable_python(package)
    return frozen
