# src/nicheradar/flow_research/gates.py
"""Selection gates: automation, policy risk, human minutes per video and rights.

The gates stop the flow; they never change a score (the score still does not subtract
``policy_risk``). Thresholds are configurable (``NR_GATE_MIN_AUTOMATION``,
``NR_GATE_MAX_HUMAN_MINUTES``) and are initial assumptions, not measured values.
A gate can be overridden only by an explicit, recorded human decision.
"""

from dataclasses import dataclass
from typing import Any, Self, TypedDict

from nicheradar.config import Settings


class GateReason(TypedDict):
    gate: str  # automation | policy_risk | human_minutes | rights
    message: str


@dataclass(frozen=True)
class Gates:
    min_automation: float = 90
    max_human_minutes: int = 60
    block_high_policy_risk: bool = True

    @classmethod
    def from_settings(cls, config: Settings) -> Self:
        return cls(
            config.gate_min_automation,
            config.gate_max_human_minutes,
            config.gate_block_high_policy_risk,
        )


DEFAULT_GATES = Gates()


def niche_reasons(niche: dict[str, Any], gates: Gates) -> list[GateReason]:
    """``niche`` is a backlog entry. An unknown automation score does not fail the gate."""
    reasons: list[GateReason] = []
    automation = niche.get("automation") or {}
    value = automation.get("value")
    if value is not None and value < gates.min_automation:
        reasons.append(
            {
                "gate": "automation",
                "message": f"La automatización del nicho es {value:g} y el mínimo es "
                f"{gates.min_automation:g}.",
            }
        )
    level = (automation.get("policy_risk") or {}).get("level")
    if level == "alto" and gates.block_high_policy_risk:
        reasons.append(
            {"gate": "policy_risk", "message": "El riesgo de política del nicho es alto."}
        )
    return reasons


def minutes_reasons(minutes: int, gates: Gates) -> list[GateReason]:
    if minutes > gates.max_human_minutes:
        return [
            {
                "gate": "human_minutes",
                "message": f"El flujo exige {minutes} minutos humanos por video y el máximo es "
                f"{gates.max_human_minutes}.",
            }
        ]
    return []


def annotation(niche: dict[str, Any], gates: Gates) -> dict[str, Any]:
    """What goes into the frozen evidence: the thresholds used and what the niche scored."""
    automation = niche.get("automation") or {}
    reasons = niche_reasons(niche, gates)
    return {
        "min_automation": gates.min_automation,
        "max_human_minutes": gates.max_human_minutes,
        "block_high_policy_risk": gates.block_high_policy_risk,
        "automation_value": automation.get("value"),
        "automation_known": automation.get("value") is not None,
        "policy_risk_level": (automation.get("policy_risk") or {}).get("level"),
        "passed": not reasons,
        "reasons": reasons,
    }


def authorization_reasons(
    dossier: dict[str, Any], niche: dict[str, Any], gates: Gates
) -> list[GateReason]:
    """Every gate again, on a stored dossier (any version) just before a pilot is authorized."""
    reasons = niche_reasons(niche, gates)
    minutes = sum(step["human_minutes_per_video"] for step in dossier["production_flow"])
    reasons += minutes_reasons(minutes, gates)
    rights = dossier.get("rights")
    if rights is None:
        reasons.append(
            {
                "gate": "rights",
                "message": f"El dossier es {dossier['schema_version']}: no evalúa derechos "
                "ni plan de automatización.",
            }
        )
    elif rights["verdict"] == "blocked":
        reasons.append({"gate": "rights", "message": "Los derechos del material están bloqueados."})
    return reasons


def describe(reasons: list[GateReason]) -> str:
    return "; ".join(reason["message"] for reason in reasons)
