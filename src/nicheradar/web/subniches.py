# src/nicheradar/web/subniches.py
"""View models for the sub-niche screens: what the templates show, never raw API payloads."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

from nicheradar.web.format import usd_range

FAMILIES = {
    "nature_science": "Ciencia y naturaleza",
    "history": "Historia",
    "tech_engineering": "Ingeniería",
    "scifi": "Ciencia ficción",
    "business": "Negocios",
    "mysteries": "Misterios",
    "stories": "Historias narradas",
    "black_audience": "Audiencia afro",
}
STATUS_LABELS = {
    "active": "Activos",
    "proposed": "Propuestos",
    "paused": "Pausados",
    "archived": "Archivados",
}
RESEARCH = {
    None: ("Sin investigar", "neutral"),
    "pendiente": ("En cola", "amber"),
    "en_curso": ("Investigando", "blue"),
    "listo": ("Dossier listo", "green"),
    "rechazado": ("Rechazada", "rose"),
}


@dataclass(frozen=True)
class Filters:
    finalistas: bool = False
    familia: str = ""
    estado: str = ""
    inactivos: bool = False


def parse_filters(params: Mapping[str, str]) -> Filters:
    estado = params.get("estado", "")
    return Filters(
        finalistas=params.get("finalistas") == "1",
        familia=params.get("familia", "")[:40],
        estado=estado if estado in STATUS_LABELS else "",
        inactivos=params.get("inactivos") == "1",
    )


def card(item: dict[str, Any], rank: int) -> dict[str, Any]:
    measured = item["measurement"]
    research = item["research"]
    state = research["status"] if research else None
    text, kind = RESEARCH.get(state, ("Investigación", "neutral"))
    if item["status"] != "active" or measured is None:
        button = ("Ver subnicho", "secondary")
    elif state in (None, "rechazado"):
        button = ("Investigar", "primary")
    elif state in ("pendiente", "en_curso"):
        button = ("Ver estado", "secondary")
    else:
        button = ("Ver subnicho", "secondary")
    return {
        "slug": item["slug"],
        "label": item["label"],
        "rank": rank,
        "finalist": item["finalist"],
        "family": FAMILIES.get(item["family"], item["family"]),
        "language": str(item["language"]).upper(),
        "research_text": text,
        "research_kind": kind,
        "income": usd_range(measured["income_low"], measured["income_high"]) if measured else None,
        "stats": (
            [
                ("Despegaron", measured["traction_channels"]),
                ("Constantes", measured["stable_channels"]),
                ("Grandes", measured["large_channels"]),
            ]
            if measured
            else None
        ),
        "button_label": button[0],
        "button_kind": button[1],
        "href": f"/subnichos/{quote(item['slug'], safe='')}",
    }


def list_view(items: list[dict[str, Any]], filters: Filters) -> dict[str, Any]:
    families = sorted({str(item["family"]) for item in items})
    familia = filters.familia if filters.familia in families else ""
    shown = [
        item
        for item in items
        if (not familia or item["family"] == familia)
        and (not filters.estado or item["status"] == filters.estado)
        and (not filters.finalistas or item["finalist"])
    ]
    return {
        "cards": [card(item, rank) for rank, item in enumerate(shown, 1)],
        "total": len(items),
        "finalists": sum(1 for item in items if item["finalist"]),
        "familias": [(family, FAMILIES.get(family, family)) for family in families],
        "estados": list(STATUS_LABELS.items()),
        "filtros": replace(filters, familia=familia),
    }
