# src/nicheradar/flow_research_dashboard.py
"""Streamlit panel for flow research: order it from a tentative niche, read the dossier.

Everything the dossier says came from the web through a person-driven session, so free text is
shown with ``st.text`` (never Markdown) and figures are labelled as orientative.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import streamlit as st

from nicheradar.config import Settings
from nicheradar.flow_research.evidence import REASONS, ineligible_reason

ApiRequest = Callable[..., dict[str, Any]]
STATUS_LABELS = {
    "pendiente": "pendiente: esperando a Claude Code (usa el skill flow-research)",
    "en_curso": "en curso: Claude Code está investigando",
    "listo": "listo",
    "rechazado": "rechazado: el dossier no cumplió el contrato",
}
RECOMMENDATIONS = {
    "go": "Avanzar",
    "go_with_conditions": "Avanzar con condiciones",
    "no_go": "No avanzar",
}
RECURRENCE = {"one_time": "una vez", "monthly": "mensual"}
AUTOMATION = {"manual": "manual", "semi": "semiautomático", "auto": "automático"}


def budget_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Fase": line["phase"],
            "Herramienta": line["tool"],
            "Descripción": line["description"],
            "Costo unitario (US$)": float(line["unit_cost_usd"]),
            "Cantidad": float(line["quantity"]),
            "Recurrencia": RECURRENCE[line["recurrence"]],
            "Subtotal (US$)": float(line["subtotal_usd"]),
            "Precio verificado el": line["price_checked_on"],
            "Fuente": line["source_id"],
        }
        for line in content["budget"]["lines"]
    ]


def roadmap_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Fase": phase["name"],
            "Semanas": phase["weeks"],
            "Objetivo": phase["objective"],
            "Criterios de salida": " | ".join(phase["exit_criteria"]),
            "Costo (US$)": float(phase["cost_usd"]),
        }
        for phase in content["roadmap"]
    ]


def tool_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Herramienta": tool["name"],
            "Fase": tool["phase"],
            "Para qué": tool["purpose"],
            "Precio": tool["pricing"],
            "Alternativa más barata": tool.get("cheaper_alternative") or "",
            "Automatización": AUTOMATION[tool["automation"]],
            "Fuente": tool["source_id"],
        }
        for tool in content["tools"]
    ]


def competitor_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Canal": item["name"],
            "Enlace": item["channel_url"],
            "Suscriptores": item["subscribers"],
            "Cadencia": item["cadence"],
            "Estilo": item["production_style"],
            "Fuente": item["source_id"],
        }
        for item in content["competitors"]
    ]


def flow_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Paso": step["order"],
            "Etapa": step["name"],
            "Minutos humanos por video": step["human_minutes_per_video"],
            "Automatización": AUTOMATION[step["automation"]],
            "Herramientas": ", ".join(step["tools"]),
            "Sigue siendo humano": step.get("stays_human") or "",
        }
        for step in sorted(content["production_flow"], key=lambda step: step["order"])
    ]


def source_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Id": s["id"], "Título": s["title"], "Enlace": s["url"], "Consultada el": s["accessed_on"]}
        for s in content["sources"]
    ]


def render_dossier(content: dict[str, Any]) -> None:
    verdict = content["verdict"]
    st.caption(
        "Dossier generado por una investigación web: las cifras son orientativas. "
        "Revisa la fecha y la fuente de cada precio."
    )
    st.text(
        f"Recomendación: {RECOMMENDATIONS[verdict['recommendation']]} · "
        f"confianza {verdict['confidence']} · horizonte {content['horizon']}"
    )
    st.text(verdict["thesis"])
    for risk in verdict["main_risks"]:
        st.text("Riesgo: " + risk)
    for unknown in verdict["unknowns"]:
        st.text("No verificado: " + unknown)
    st.markdown("**Competencia de referencia**")
    st.dataframe(competitor_rows(content), hide_index=True, width="stretch")
    st.markdown("**Flujo de producción**")
    st.dataframe(flow_rows(content), hide_index=True, width="stretch")
    st.markdown("**Roadmap**")
    st.dataframe(roadmap_rows(content), hide_index=True, width="stretch")
    st.markdown("**Presupuesto**")
    st.dataframe(budget_rows(content), hide_index=True, width="stretch")
    totals = content["budget"]["totals"]
    st.text(
        "Total (bajo / probable / alto): US$ "
        f"{float(totals['low']):.2f} / {float(totals['likely']):.2f} / {float(totals['high']):.2f}"
    )
    for assumption in content["budget"]["assumptions"]:
        st.text("Supuesto: " + assumption)
    st.markdown("**Herramientas**")
    st.dataframe(tool_rows(content), hide_index=True, width="stretch")
    st.markdown("**Mapa de automatización**")
    for item in content["automation_map"]:
        st.text(
            f"{item['step']}: hoy {item['automated_today']} · semi {item['semi_automated']} · "
            f"riesgo {item['dependency_risk']} · respaldo {item['manual_fallback']}"
        )
    policy = content["policy_risk"]
    st.markdown("**Riesgo de política de YouTube**")
    st.text(f"Nivel {policy['level']}: {policy['summary']}")
    for mitigation in policy["mitigations"]:
        st.text("Mitigación: " + mitigation)
    st.markdown("**Punto de equilibrio (estimación)**")
    income = content["break_even"]["monthly_income_usd"]
    months = content["break_even"]["months_to_recover"]
    st.text(
        "Ingreso mensual US$ "
        f"{float(income['low']):.2f} / {float(income['likely']):.2f} / {float(income['high']):.2f}"
        f" · meses para recuperar: {months['low']} / {months['likely']} / {months['high']}"
    )
    for assumption in content["break_even"]["assumptions"]:
        st.text("Supuesto: " + assumption)
    st.markdown("**Fuentes**")
    st.dataframe(source_rows(content), hide_index=True, width="stretch")


def render_flow_research(config: Settings, api: ApiRequest, entry: dict[str, Any]) -> None:
    st.subheader("Investigación de flujo")
    query = urlencode({"niche_label": entry["niche_label"], "format": entry["format"], "limit": 1})
    items = api(config, "GET", "/flow-research?" + query)["items"]
    latest = items[0] if items else None
    active = latest is not None and latest["status"] in ("pendiente", "en_curso")
    reason = ineligible_reason(entry)
    if reason is not None:
        st.caption(REASONS[reason])
    if latest is not None:
        st.caption("Última investigación: " + STATUS_LABELS[latest["status"]])
    if st.button("Iniciar investigación de flujo", disabled=reason is not None or active):
        api(
            config,
            "POST",
            "/flow-research",
            body={"niche_label": entry["niche_label"], "format": entry["format"]},
        )
        st.rerun()
    if latest is None:
        return
    if latest["status"] == "rechazado":
        for problem in (latest["rejection"] or {}).get("problems", []):
            st.text(f"{problem['path']}: {problem['message']}")
    elif latest["status"] == "listo":
        detail = api(config, "GET", f"/flow-research/{latest['id']}")
        render_dossier(detail["dossier"])
