# src/nicheradar/web/niches.py
"""View models for the niche list (M2): what the template shows, never raw API payloads."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from nicheradar.web.research import valid_id

DECISION_CHIP = {
    "nuevo": ("Sin decidir", "neutral"),
    "tentativo": ("Tentativo", "rose"),
    "descartado": ("Descartado", "neutral"),
}
RESEARCH_CHIP = {
    "pendiente": ("En cola", "amber"),
    "en_curso": ("Investigando", "blue"),
    "listo": ("Dossier listo", "green"),
    "rechazado": ("Rechazada", "rose"),
}
CONFIDENCE = {"alta": "Alta", "media": "Media", "baja": "Baja"}
FORMATS = {"long": "Largos", "shorts": "Shorts"}
ORDERS = ("opportunity", "automation")
AVISOS_NICHOS = {
    "marcado": ("Marcado como tentativo.", "green"),
    "guardada": ("Decisión guardada.", "green"),
    "error": ("No se pudo guardar la decisión. Revisa la API e inténtalo de nuevo.", "rose"),
    "error-creada": ("No se pudo abrir el informe de la investigación creada.", "rose"),
    "invalida": ("La decisión no es válida.", "amber"),
}


@dataclass(frozen=True)
class NicheFilters:
    formato: str = ""
    alta: bool = False
    ingresos: bool = False
    orden: str = "opportunity"


def parse_filters(params: Mapping[str, str]) -> NicheFilters:
    formato = params.get("formato", "")
    orden = params.get("orden", "")
    return NicheFilters(
        formato=formato if formato in FORMATS else "",
        alta=params.get("alta") == "1",
        ingresos=params.get("ingresos") == "1",
        orden=orden if orden in ORDERS else "opportunity",
    )


def investigate_href(label: str, fmt: str) -> str:
    return f"/nichos/investigar?etiqueta={quote(label, safe='')}&formato={quote(fmt, safe='')}"


def research_index(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Newest research per (label, format): the API lists newest first, so the first one wins."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        index.setdefault((item["niche_label"], item["format"]), item)
    return index


def _score(block: dict[str, Any] | None) -> int | None:
    value = (block or {}).get("value")
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return round(value)


def card(item: dict[str, Any], research: dict[str, Any] | None, rank: int) -> dict[str, Any]:
    decision = item["decision"]["decision"]
    state = research["status"] if research else None
    research_id = research["id"] if research else None
    opportunity = _score(item["opportunity"])
    d_text, d_kind = DECISION_CHIP.get(decision, DECISION_CHIP["nuevo"])
    r_text, r_kind = RESEARCH_CHIP.get(state, (None, None)) if state else (None, None)
    label, fmt = item["niche_label"], item["format"]
    action: dict[str, Any]
    if opportunity is None:
        # Deliberate: without a score there is nothing to decide or research, even if an
        # older dossier exists; the dossier chip still shows its state.
        action = {"kind": "disabled", "label": "Falta puntaje"}
    elif state in ("listo", "pendiente", "en_curso") and not valid_id(research_id):
        action = {"kind": "disabled", "label": "Ver estado"}
    elif state == "listo":
        # (A niche without score never reaches here: "Falta puntaje" wins even with a dossier.)
        action = {
            "kind": "link",
            "label": "Ver dossier",
            "style": "secondary",
            "href": f"/informes/{research_id}",
        }
    elif state in ("pendiente", "en_curso"):
        action = {
            "kind": "link",
            "label": "Ver estado",
            "style": "secondary",
            "href": f"/informes/{research_id}",
        }
    elif decision == "tentativo":
        action = {
            "kind": "link",
            "label": "Investigar",
            "style": "primary",
            "href": investigate_href(label, fmt),
        }
    else:
        action = {"kind": "decide", "label": "Marcar tentativo", "label_raw": label, "format": fmt}
    return {
        "rank": rank if opportunity is not None else "—",
        "label": label,
        "format": fmt,
        "format_text": "Shorts" if fmt == "shorts" else "Largo",
        "decision_text": d_text,
        "decision_kind": d_kind,
        "research_text": r_text,
        "research_kind": r_kind,
        "scores": [
            ("Opportunity", opportunity if opportunity is not None else "sin puntaje"),
            (
                "Automat.",
                _score(item["automation"]) if _score(item["automation"]) is not None else "—",
            ),
            ("Confianza", CONFIDENCE.get(item["confidence"], "—")),
        ],
        "action": action,
    }


def list_view(
    items: list[dict[str, Any]],
    research_items: list[dict[str, Any]],
    filters: NicheFilters,
    api_total: int | None = None,
) -> dict[str, Any]:
    index = research_index(research_items)
    shown = [
        item
        for item in items
        if (not filters.formato or item["format"] == filters.formato)
        and (not filters.alta or item["confidence"] == "alta")
        and (not filters.ingresos or ((item.get("metrics") or {}).get("n_income") or 0) > 0)
    ]
    counts = {fmt: sum(1 for item in items if item["format"] == fmt) for fmt in FORMATS}
    return {
        "cards": [
            card(item, index.get((item["niche_label"], item["format"])), rank)
            for rank, item in enumerate(shown, 1)
        ],
        "total": len(items),
        "api_total": max(api_total or 0, len(items)),
        "truncated": (api_total or 0) > len(items),
        "shown": len(shown),
        "counts": counts,
        "filtros": filters,
    }
