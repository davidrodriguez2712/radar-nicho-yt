# src/nicheradar/subniche_dashboard.py
"""Streamlit page for sub-niche hypotheses: measurements, research order and dossier.

Everything that came from YouTube or from a hypothesis is shown with ``st.text`` or a dataframe,
never as Markdown. Income figures are estimates (inherited RPM), not verified earnings.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import streamlit as st

from nicheradar.config import Settings
from nicheradar.flow_research_dashboard import STATUS_LABELS, language_name, render_dossier

ApiRequest = Callable[..., dict[str, Any]]
ALL = "Todas"


def _yes(value: bool) -> str:
    return "sí" if value else "no"


def _income(measurement: dict[str, Any] | None) -> str:
    if measurement is None or measurement["income_low"] is None:
        return ""
    return f"{measurement['income_low']} – {measurement['income_high']}"


def subniche_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in items:
        measurement = entry["measurement"]
        research = entry["research"]
        rows.append(
            {
                "Subnicho": entry["label"],
                "Familia": entry["family"],
                "Estado": entry["status"],
                "Finalista": _yes(entry["finalist"]),
                "Ingreso por canal (US$)": _income(measurement),
                "Tracción": None if measurement is None else measurement["traction_channels"],
                "Estables": None if measurement is None else measurement["stable_channels"],
                "Grandes": None if measurement is None else measurement["large_channels"],
                "Investigación": research["status"] if research else "sin investigar",
            }
        )
    return rows


def channel_rows(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Canal": item["title"] or item["channel_id"],
            "Enlace": f"https://www.youtube.com/channel/{item['channel_id']}",
            "Suscriptores": item["subscribers"],
            "Vistas largas al mes": item["monthly_long_views"],
            "Ingreso (US$)": f"{item['income_low']} – {item['income_high']}"
            if item["income_low"] is not None
            else "",
            "Tracción": _yes(item["traction"]),
            "Señales": ", ".join(item["flags"]),
        }
        for item in channels
    ]


def _render_research(
    config: Settings, api: ApiRequest, hypothesis: dict[str, Any], research: dict[str, Any] | None
) -> None:
    st.markdown("**Investigación de flujo**")
    language = hypothesis["language"]
    st.caption(
        f"Idioma de la hipótesis: {language_name(language)}. "
        "La investigación usa el mismo idioma y formato."
    )
    active = research is not None and research["status"] in ("pendiente", "en_curso")
    if research is not None:
        st.caption("Última investigación: " + STATUS_LABELS[research["status"]])
    if st.button("Iniciar investigación de flujo", disabled=active):
        api(
            config,
            "POST",
            "/flow-research",
            body={
                "niche_label": "subniche:" + hypothesis["slug"],
                "format": hypothesis["format"],
                "language": language,
            },
        )
        st.rerun()
    if research is not None and research["status"] == "listo":
        detail = api(config, "GET", f"/flow-research/{research['id']}")
        render_dossier(detail["dossier"])
    elif research is not None and research["status"] == "rechazado":
        detail = api(config, "GET", f"/flow-research/{research['id']}")
        for problem in (detail.get("rejection") or {}).get("problems", []):
            st.text(f"{problem['path']}: {problem['message']}")


def render_subniches(config: Settings, api: ApiRequest) -> None:
    st.subheader("Subnichos: hipótesis medidas")
    st.caption(
        "El ingreso es la mediana mensual estimada por canal estable, con el RPM heredado del "
        "nicho padre: es una estimación, no ingresos verificados. «Tracción» cuenta canales "
        "pequeños con un video largo muy por encima de su tamaño."
    )
    include_inactive = st.checkbox("Mostrar pausadas y archivadas")
    data = api(
        config, "GET", "/subniches?include_inactive=" + ("true" if include_inactive else "false")
    )
    items = data["items"]
    if not items:
        st.info("Todavía no hay hipótesis. Cárgalas con scripts/subniche.py import.")
        return
    filters = st.columns(2)
    families = [ALL, *sorted({entry["family"] for entry in items})]
    family = filters[0].selectbox("Familia", families)
    only_finalists = filters[1].checkbox("Solo finalistas")
    shown = [
        entry
        for entry in items
        if (family == ALL or entry["family"] == family)
        and (not only_finalists or entry["finalist"])
    ]
    st.dataframe(subniche_rows(shown), hide_index=True, width="stretch")
    if not shown:
        return
    by_slug = {entry["slug"]: entry for entry in shown}
    selected = st.selectbox(
        "Abrir subnicho", list(by_slug), format_func=lambda slug: by_slug[slug]["label"]
    )
    card = api(config, "GET", f"/subniches/{quote(selected, safe='')}")
    hypothesis = card["hypothesis"]
    st.markdown("**Hipótesis**")
    st.text(f"{hypothesis['label']} · estado {hypothesis['status']} · {hypothesis['family']}")
    for query in hypothesis["queries"]:
        st.text("Consulta: " + query)
    measurement = card["measurement"]
    if measurement is None:
        st.info("Esta hipótesis todavía no tiene una medición.")
    else:
        st.text(
            f"Medida el {measurement['measured_at']}: {measurement['included']} canales incluidos, "
            f"{measurement['stable_channels']} estables, {measurement['volatile_channels']} "
            f"volátiles, tracción {measurement['traction_channels']}, grandes "
            f"{measurement['large_channels']}. RPM: {measurement['rpm_source']}"
        )
    st.markdown("**Canales relevantes**")
    if card["channels_available"]:
        st.dataframe(channel_rows(card["channels"]), hide_index=True, width="stretch")
    else:
        st.caption("Los datos de canales vencieron (30 días) o no hay medición vigente.")
    if measurement is not None:
        _render_research(config, api, hypothesis, card["research"])
