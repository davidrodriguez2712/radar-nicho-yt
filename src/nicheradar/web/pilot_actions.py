# src/nicheradar/web/pilot_actions.py
"""Follow, close and cancel a pilot: what each action means, when it applies and how it fails.

These actions cannot be undone, so the screens state the consequence first and the rules here
mirror the API's transitions (pilots/service.py: decide and cancel); the API stays the authority.
"""

import unicodedata
from typing import Any

NOTE_MAX = 1500  # pilots_api.Note: 1..1500 characters, for the note and for the reason
ACTOR = "humano"  # the API's own default; always set here, never taken from the browser
NOTICE_KEYS = {"seguir": "seguido", "cerrar": "cerrado", "cancelar": "cancelado"}

ACTIONS: dict[str, dict[str, Any]] = {
    "seguir": {
        "title": "Seguir con el piloto",
        "consequence": "El piloto continúa hasta el siguiente hito.",
        "field": "note",
        "label": "Nota de la decisión",
        "subject": "La nota",
        "button": "Confirmar: seguir",
        "kind": "primary",
        "states": frozenset({"decision_pendiente"}),
    },
    "cerrar": {
        "title": "Cerrar el piloto",
        "consequence": (
            "Esto cierra el piloto y no se puede deshacer. Se genera el resumen de cierre."
        ),
        "field": "note",
        "label": "Nota de cierre",
        "subject": "La nota",
        "button": "Confirmar: cerrar piloto",
        "kind": "danger",
        "states": frozenset({"en_ejecucion", "decision_pendiente"}),
    },
    "cancelar": {
        "title": "Cancelar el piloto",
        "consequence": "Esto cancela el piloto antes de producir. El canal queda libre.",
        "field": "reason",
        "label": "Motivo de la cancelación",
        "subject": "El motivo",
        "button": "Confirmar: cancelar piloto",
        "kind": "danger",
        "states": frozenset({"autorizado", "entregado"}),
    },
}

REFUSALS = {
    "seguir": "Solo se puede seguir una decisión pendiente.",
    "cerrar": "Un piloto en preparación se cancela, no se cierra.",
    "cancelar": "Solo se cancela un piloto antes de que se ejecute.",
}
FALLBACK_REFUSAL = "El piloto no está en un estado que permita esta acción."
CONFLICT_MESSAGES = {
    "bad_transition": "El piloto no está en un estado que permita esa acción.",
    "closed": "El piloto ya está cerrado o cancelado.",
    "not_found": "No se encontró el piloto.",
}
GENERIC_CONFLICT = "No se pudo aplicar la acción. Revisa el estado del piloto."
NO_SUMMARY_YET = "El resumen existe solo cuando el piloto está cerrado."


def allowed(action: str, status: str) -> bool:
    spec = ACTIONS.get(action)
    return spec is not None and status in spec["states"]


def refusal(action: str, status: str) -> str:
    """Why the action does not apply to a pilot in this state."""
    if status == "cerrado":
        return "Este piloto ya está cerrado."
    if status == "cancelado":
        return "Este piloto ya está cancelado."
    if status in ("autorizado", "entregado", "en_ejecucion", "decision_pendiente"):
        return REFUSALS[action]
    return FALLBACK_REFUSAL


def note_error(action: str) -> str:
    subject = ACTIONS[action]["subject"]
    return f"{subject} es obligatorio y admite hasta {NOTE_MAX} caracteres."


def validate_note(value: str) -> str | None:
    """The note as it will be sent (line breaks normalised, ends trimmed), or None when invalid."""
    note = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 1 <= len(note) <= NOTE_MAX:
        return None
    return note if any(_visible(char) for char in note) else None


def _visible(char: str) -> bool:
    """A character a person can read: not whitespace, not a space/format/control character."""
    return not char.isspace() and unicodedata.category(char) not in ("Cf", "Zs", "Cc")
