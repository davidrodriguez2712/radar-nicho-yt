# src/nicheradar/market_dashboard.py
"""Streamlit tab "Mercado": the niche backlog built from marketplace listings.

Every figure shown here is declared by sellers; the UI says so and keeps confidence, missing
evidence and uncalibrated values visible instead of hiding them behind a single score.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

import streamlit as st

from nicheradar.config import Settings
from nicheradar.flow_research_dashboard import render_flow_research

ApiRequest = Callable[..., dict[str, Any]]
INSUFFICIENT = "sin evidencia"
VERIFICATION_LABELS = {
    "verified": "verificado",
    "mismatch": "no coincide",
    "not_found": "canal no encontrado",
    "unverifiable": "no verificable",
    None: "sin verificar",
}
DECISIONS = ["nuevo", "tentativo", "descartado"]


def _score(block: dict[str, Any]) -> float | str:
    return block["value"] if block["value"] is not None else INSUFFICIENT


def backlog_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in items:
        metrics = entry["metrics"]
        rows.append(
            {
                "Nicho": entry["niche_label"],
                "Formato": entry["format"],
                "Opportunity": _score(entry["opportunity"]),
                "Automatización": _score(entry["automation"]),
                "Riesgo de política": entry["automation"]["policy_risk"]["level"] or "sin dato",
                "Confianza": entry["confidence"],
                "Fichas": metrics["n_listings"],
                "Con ingreso": metrics["n_income"],
                "Ingreso mediano (US$/mes)": metrics["income_median"],
                "Precio / ingreso anual": metrics["multiple_median"],
                "RPM referencia": entry["rpm_mid"]
                if entry["rpm_mid"] is not None
                else "sin calibrar",
                "Tendencia": entry["trend"],
                "Decisión": entry["decision"]["decision"],
            }
        )
    return rows


def listing_rows(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Ficha": row["title"],
            "Estado": row["status"],
            "Precio (US$)": row["price_usd"],
            "Suscriptores declarados": row["subscribers"],
            "Suscriptores en YouTube": row["real_subscribers"],
            "Ingreso declarado (US$/mes)": row["income_monthly_usd"],
            "Gasto declarado (US$/mes)": row["expense_monthly_usd"],
            "Verificación": VERIFICATION_LABELS.get(row["verification"], "sin verificar"),
            "Enlace": row["url"],
        }
        for row in listings
    ]


def prefill_analysis(url: str) -> None:
    """Callback: jump to the existing channel-analysis form with the listing's channel."""
    st.session_state["prefill_channel_input"] = url
    st.session_state["page"] = "Análisis de canal"


def _render_decision(config: Settings, api: ApiRequest, entry: dict[str, Any]) -> None:
    current = entry["decision"]["decision"]
    columns = st.columns([1, 2, 1])
    decision = columns[0].selectbox("Decisión del nicho", DECISIONS, index=DECISIONS.index(current))
    note = columns[1].text_input("Nota", value=entry["decision"].get("note") or "")
    if columns[2].button("Guardar decisión"):
        api(
            config,
            "POST",
            f"/market/niches/{quote(entry['niche_label'], safe='')}/decisions",
            body={"format": entry["format"], "decision": decision, "note": note or None},
        )
        st.success("Decisión guardada.")
        st.rerun()


def render_market(config: Settings, api: ApiRequest) -> None:
    st.subheader("Mercado: backlog de nichos")
    st.caption(
        "Las cifras salen de fichas de canales en venta y las declaran los vendedores: no son "
        "ingresos verificados. La confianza indica cuánto respaldo tiene cada nicho."
    )
    filters = st.columns(3)
    fmt = filters[0].selectbox("Formato", ["long", "shorts"])
    order = filters[1].selectbox("Ordenar por", ["Opportunity", "Automatización"])
    show_discarded = filters[2].checkbox("Mostrar descartados")
    query = urlencode(
        {
            "format": fmt,
            "order": "automation" if order == "Automatización" else "opportunity",
            "include_discarded": str(show_discarded).lower(),
            "limit": 100,
        }
    )
    data = api(config, "GET", "/market/niches?" + query)
    if fmt == "shorts":
        st.info("Shorts no tiene benchmark de RPM: su eficiencia queda sin calibrar.")
    if not data["items"]:
        st.info("Todavía no hay nichos con fichas clasificadas. Reanuda el scraper en Operación.")
        return
    st.dataframe(backlog_rows(data["items"]), hide_index=True, width="stretch")
    by_label = {entry["niche_label"]: entry for entry in data["items"]}
    selected = st.selectbox("Abrir nicho", list(by_label))
    entry = by_label[selected]
    _render_decision(config, api, entry)
    render_flow_research(config, api, entry)
    detail = api(config, "GET", f"/market/niches/{quote(selected, safe='')}?format={fmt}")
    with st.expander("Cómo se calculó"):
        st.json({"opportunity": entry["opportunity"], "automation": entry["automation"]})
    st.subheader("Fichas del nicho")
    st.dataframe(listing_rows(detail["listings"]), hide_index=True, width="stretch")
    with_channel = [row for row in detail["listings"] if row.get("channel_url")][:10]
    if with_channel:
        st.caption("Analizar el canal usa el flujo existente y su presupuesto vidIQ.")
    for index, row in enumerate(with_channel):
        st.text(row["title"])  # plain text: a seller title is never rendered as Markdown
        st.button(
            "Analizar canal",
            key=f"analyze-{index}",
            on_click=prefill_analysis,
            args=(row["channel_url"],),
        )


def render_market_operations(config: Settings, api: ApiRequest) -> None:
    st.subheader("Operación del scraper de mercado")
    schedule = api(config, "GET", "/market/schedule")
    state = "pausado" if schedule["paused"] else "activo"
    st.caption(
        f"Scraper {state}. Su pausa es independiente de la del radar "
        f"(radar pausado: {schedule['radar_paused']})."
    )
    live_blocked = schedule["mode"] == "live" and not schedule["live_enabled"]
    if live_blocked:
        st.warning(
            "En modo live el scraper espera la revisión de los Términos de Servicio de la fuente."
        )
    controls = st.columns(2)
    if controls[0].button("Pausar scraper", disabled=schedule["paused"]):
        api(config, "PUT", "/market/schedule", body={"paused": True})
        st.rerun()
    if controls[1].button("Reanudar scraper", disabled=not schedule["paused"] or live_blocked):
        api(config, "PUT", "/market/schedule", body={"paused": False})
        st.rerun()
    runs = api(config, "GET", "/market/runs?limit=10")["items"]
    if runs:
        st.dataframe(
            [
                {
                    "Corrida": run["run_key"],
                    "Estado": run["status"],
                    "Etapa": run["stage"],
                    "Error": run["error_code"],
                    "Detalle": str(run["stats"]),
                }
                for run in runs
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Aún no hay corridas del scraper.")
