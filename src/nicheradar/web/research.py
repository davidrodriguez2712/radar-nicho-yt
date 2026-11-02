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
    known = [
        entry
        for entry in mix
        if entry["language"] != "unknown" and LANG_RE.match(entry["language"])
    ]
    unknown = next((e["share_pct"] for e in mix if e["language"] == "unknown"), None)
    options = [
        {
            "code": e["language"],
            "name": LANGUAGE_NAMES.get(e["language"], e["language"]),
            "share": round(e["share_pct"]),
            "suggested": False,
        }
        for e in sorted(known, key=lambda e: -e["share_pct"])
    ]
    suggested: str | None = None
    if options:
        top = max(mix, key=lambda e: e["share_pct"])
        runner_up = sorted((e["share_pct"] for e in mix), reverse=True)[1:2]
        # No pre-selection on a tie or when "unknown" leads: the owner must choose.
        if top["language"] != "unknown" and (not runner_up or top["share_pct"] > runner_up[0]):
            suggested = top["language"]
            for option in options:
                option["suggested"] = option["code"] == suggested
    return {
        "options": options,
        "unknown_share": None if unknown is None else round(unknown),
        "suggested": suggested,
        "no_choice": not options,
    }
