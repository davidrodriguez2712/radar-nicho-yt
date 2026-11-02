# src/nicheradar/web/research.py
"""View model of the 'start flow research' screen (M8)."""

import re
from typing import Any

LANG_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
LANGUAGE_NAMES = {
    "en": "Inglés",
    "es": "Español",
    "pt": "Portugués",
    "de": "Alemán",
    "fr": "Francés",
    "ru": "Ruso",
    "it": "Italiano",
    "ja": "Japonés",
    "ko": "Coreano",
    "ar": "Árabe",
    "hi": "Hindi",
    "tr": "Turco",
}
CONFLICT_MESSAGES = {
    "not_tentative": "Primero marca el nicho como tentativo para poder investigarlo.",
    "no_evidence": "El nicho todavía no tiene puntaje: falta evidencia para investigarlo.",
    "invalid_language": "El idioma no es válido: elige uno de la lista.",
    "gate_failed": "El nicho no pasa una compuerta de selección.",
    "not_found": "No se encontró el nicho.",
}


def language_options(mix: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [
        (e["language"], float(e["share_pct"]))
        for e in mix
        if isinstance(e.get("language"), str) and isinstance(e.get("share_pct"), int | float)
    ]
    known = sorted(
        (e for e in entries if e[0] != "unknown" and LANG_RE.match(e[0])), key=lambda e: -e[1]
    )
    unknown = next((share for code, share in entries if code == "unknown"), None)
    options = [
        {
            "code": code,
            "name": LANGUAGE_NAMES.get(code, code),
            "share": round(share),
            "suggested": False,
        }
        for code, share in known
    ]
    suggested: str | None = None
    if known:
        # The leader of the valid options, who must also beat EVERY other entry (an
        # "unknown" or malformed code that leads or ties blocks the suggestion).
        others = [share for code, share in entries if (code, share) != known[0]]
        if known[0][1] > max(others, default=-1.0) and not (
            len([e for e in entries if e == known[0]]) > 1
        ):
            suggested = known[0][0]
            options[0]["suggested"] = True
    return {
        "options": options,
        "unknown_share": None if unknown is None else round(unknown),
        "suggested": suggested,
        "no_choice": not options,
    }
