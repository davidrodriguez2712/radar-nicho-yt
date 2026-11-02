# src/nicheradar/web/subniches.py
"""View models for the sub-niche screens: what the templates show, never raw API payloads."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

from nicheradar.web.format import compact, local_datetime, usd_range

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
NOT_READY = "La hipótesis debe estar activa y tener al menos una medición."
LANGUAGE_NAMES = {
    "en": "inglés",
    "es": "español",
    "pt": "portugués",
    "ru": "ruso",
    "de": "alemán",
    "fr": "francés",
}
EXCLUSIONS = {
    "language": "por idioma",
    "no_recent_videos": "sin videos recientes",
    "harvest_failed": "con lectura fallida",
}
STATUS_NAMES = {
    "active": "Activo",
    "proposed": "Propuesto",
    "paused": "Pausado",
    "archived": "Archivado",
}
# The only notices the card can show: the query string picks a key, never the text.
AVISOS: dict[str, tuple[str, str]] = {
    "creada": ("Investigación creada. Claude Code la atenderá en la próxima sesión.", "green"),
    "existente": ("Ya había una investigación activa para este subnicho.", "amber"),
    "no-lista": (NOT_READY, "amber"),
    "error": ("No se pudo crear la investigación. Revisa la API e inténtalo de nuevo.", "rose"),
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


def _action(
    hypothesis: dict[str, Any], measured: Any, state: str | None, language: str
) -> dict[str, Any]:
    if measured is None:
        return {"kind": "hidden"}
    label = f"Iniciar investigación en {language}"
    if hypothesis["status"] != "active":
        return {"kind": "disabled", "label": label, "note": NOT_READY}
    if state in ("pendiente", "en_curso"):
        return {
            "kind": "disabled",
            "label": label,
            "note": "Hay una investigación en curso para este subnicho.",
        }
    if state == "listo":
        return {
            "kind": "done",
            "note": "Dossier listo. El informe móvil llega en el siguiente corte.",
        }
    prefix = "Reintentar" if state == "rechazado" else "Iniciar"
    return {"kind": "start", "label": f"{prefix} investigación en {language}"}


def detail_view(card: dict[str, Any], timezone: str) -> dict[str, Any]:
    hypothesis = card["hypothesis"]
    measured = card["measurement"]
    research = card["research"]
    state = research["status"] if research else None
    language = LANGUAGE_NAMES.get(str(hypothesis["language"]), str(hypothesis["language"]))
    text, kind = RESEARCH.get(state, ("Investigación", "neutral"))
    excluded = [
        (EXCLUSIONS.get(reason, reason), count)
        for reason, count in ((measured or {}).get("excluded") or {}).items()
    ]
    return {
        "slug": hypothesis["slug"],
        "post_href": f"/subnichos/{quote(hypothesis['slug'], safe='')}/investigar",
        "label": hypothesis["label"],
        "finalist": hypothesis["finalist"],
        "family": FAMILIES.get(hypothesis["family"], hypothesis["family"]),
        "language": str(hypothesis["language"]).upper(),
        "language_name": language,
        "status": hypothesis["status"],
        "status_name": STATUS_NAMES.get(hypothesis["status"], hypothesis["status"]),
        "queries": list(hypothesis["queries"]),
        "measured": None
        if measured is None
        else {
            "when": local_datetime(measured["measured_at"], timezone),
            "included": measured["included"],
            "income": usd_range(measured["income_low"], measured["income_high"]),
            "rows": [
                ("Canales medidos", measured["included"]),
                ("Pequeños que despegaron", measured["traction_channels"]),
                ("Con vistas constantes", measured["stable_channels"]),
                ("Con picos recientes", measured["volatile_channels"]),
                ("Grandes en el tema", measured["large_channels"]),
                *[(f"Excluidos {label}", count) for label, count in excluded],
            ],
            "rpm_source": measured["rpm_source"],
        },
        "channels": [
            {
                "name": channel["title"] or channel["channel_id"],
                "takeoff": channel["traction"],
                "line": (
                    f"{compact(channel['subscribers'])} suscriptores · "
                    f"{compact(channel['monthly_long_views'])} de vistas al mes"
                    + (
                        f" · {usd_range(channel['income_low'], channel['income_high'])}"
                        if channel["income_low"] is not None and channel["income_high"] is not None
                        else ""
                    )
                ),
            }
            for channel in card["channels"]
        ],
        "channels_available": card["channels_available"],
        "research_text": text,
        "research_kind": kind,
        "action": _action(hypothesis, measured, state, language),
    }
