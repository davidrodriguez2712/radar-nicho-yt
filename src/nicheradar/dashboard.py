"""Private initial console. No direct database or provider access."""

import json
import secrets
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import streamlit as st

from nicheradar.config import Settings
from nicheradar.domain.production import STAGES

REVIEW_LABELS = {
    "new": "Nueva",
    "watching": "En seguimiento",
    "selected": "Seleccionada",
    "dismissed": "Descartada",
}
TEMPORAL_REASONS = {
    "fewer_than_two_observations": "faltan dos observaciones distintas para todos los videos",
    "fewer_than_three_observations": "faltan tres observaciones para comparar velocidades",
    "no_eligible_recent_videos": "no hay publicaciones recientes elegibles",
    "unknown_or_conflicting_counts": "hay recuentos desconocidos o contradictorios",
    "non_increasing_dates": "las fechas no forman un intervalo válido",
    "unaligned_observation_windows": "las consultas cubren ventanas temporales distintas",
    "counts_revised_downwards": "hay recuentos revisados a la baja; su causa no está verificada",
    "non_equivalent_intervals": "los intervalos no son comparables",
    "zero_previous_velocity": "la velocidad anterior es cero y no permite un cambio relativo",
}


def api_request(
    config: Settings,
    method: str,
    path: str,
    *,
    body: object = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    if config.service_token is None:
        st.error("Configura la credencial de servicio.")
        st.stop()
    try:
        with httpx.Client(
            base_url=config.api_url,
            timeout=15,
            headers={"Authorization": f"Bearer {config.service_token.get_secret_value()}"},
        ) as client:
            response = client.request(method, "/api/v1" + path, json=body, headers=headers)
            response.raise_for_status()
            # DELETE /channel-analyses/{id} (and any future 204 endpoint) returns no
            # body at all -- response.json() raises json.JSONDecodeError on an empty
            # payload, so this must be checked before attempting to decode it.
            if response.status_code == 204 or not response.content:
                return {}
            result: dict[str, Any] = response.json()
            return result
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            st.error(
                "No se aplicó el cambio: el radar está pausado, la versión cambió "
                "o falta validar la conexión."
            )
        elif error.response.status_code == 422:
            st.error("Revisa los valores: la solicitud no cumple el formato esperado.")
        else:
            st.error(
                "No se pudo completar la solicitud. Revisa la API, PostgreSQL y la autenticación."
            )
        st.stop()
    except httpx.HTTPError:
        st.error("API no disponible. Los datos anteriores no se han actualizado.")
        st.stop()


def local_time(value: str | None, timezone: str) -> str:
    if not value:
        return "Sin datos"
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(ZoneInfo(timezone))
        .strftime("%d/%m/%Y %H:%M %Z")
    )


def render_structured(data: Any, empty_caption: str = "Sin datos.") -> None:
    """Render arbitrary JSON-like trace data as tables instead of a raw dump."""
    if isinstance(data, dict):
        if not data:
            st.caption(empty_caption)
            return
        scalars = {
            key: value
            for key, value in data.items()
            if not isinstance(value, (dict, list, tuple)) or not value
        }
        if scalars:
            st.dataframe([scalars], hide_index=True, width="stretch")
        for key, value in data.items():
            if key in scalars:
                continue
            st.caption(key.replace("_", " ").capitalize())
            render_structured(value, empty_caption="Vacío.")
    elif isinstance(data, (list, tuple)):
        if not data:
            st.caption(empty_caption)
        elif isinstance(data[0], dict):
            st.dataframe(list(data), hide_index=True, width="stretch")
        else:
            st.write(", ".join(str(item) for item in data))
    elif data is None:
        st.caption(empty_caption)
    else:
        st.write(str(data))


def render_research_status(config: Settings, status: dict[str, Any]) -> None:
    research = status.get("research", {})
    messages = {
        "provider_pending": (
            "Proveedor real pendiente: faltan validar conexión, credenciales y usos permitidos. "
            "El modo sintético sigue disponible."
        ),
        "configuration_pending": (
            "Falta configuración para continuar. Revisa credenciales, políticas, "
            "tarifas y límites en Operación."
        ),
        "budget_blocked": (
            "Trabajo aplazado por presupuesto, cuota o cobro incierto. Revisa el consumo; "
            "no se comprarán créditos automáticamente."
        ),
        "technical_error": (
            "La última ejecución registró un error técnico. Los resultados anteriores "
            "no equivalen a una actualización satisfactoria."
        ),
        "processing": (
            "Hay una ejecución pendiente o en curso. "
            "Su solicitud no significa que el análisis haya terminado."
        ),
        "evidence_expired": (
            "Los datos de las últimas evaluaciones han caducado. El historial de decisiones "
            "permanece; no se reutilizan puntuaciones vencidas."
        ),
        "evaluation_pending": (
            "Hay candidatos, pero falta evidencia, calibración o una receta completa "
            "para puntuarlos. No se rellena un top artificial."
        ),
        "no_results": (
            "Aún no hay resultados de este modo. Esto no demuestra que no existan oportunidades."
        ),
        "coverage_pending": (
            "La última ejecución fue parcial: queda evidencia por reunir "
            "dentro de los límites configurados."
        ),
    }
    for reason in research.get("reasons", []):
        if reason in messages:
            if reason in {"technical_error", "evidence_expired", "budget_blocked"}:
                st.warning(messages[reason])
            else:
                st.info(messages[reason])
    if research.get("last_observed_at"):
        st.caption(
            "Última observación disponible: "
            + local_time(research["last_observed_at"], config.timezone)
            + f" · antigüedad {research['observation_age_hours']:.1f} horas. "
            + "Reutilizar caché no cambia esta fecha."
        )


STATE_LABELS = {
    "insufficient_evidence": "Evidencia insuficiente",
    "uncalibrated": "Sin calibrar",
    "provisional": "Provisional",
    "ready_for_review": "Listo para revisar",
}

MARKET_MISSING_LABELS = {
    "D": "Falta demanda calibrada (declarar referencias o esperar más evidencia).",
    "T": "Falta tendencia (necesita observaciones repetidas en el tiempo).",
    "M": "Falta monetización/RPM declarado.",
    "B": "Falta tasa de éxito (breakout) calculable.",
    "C": "Falta concentración calculable.",
}

PROFIT_MISSING_LABELS = {
    "channel_view_rate": "Falta volumen de vistas por canal (esperar más evidencia observada).",
    "videos_per_month": "Falta asignar una receta de producción con cadencia (videos/mes).",
    "advertising_rate": "Falta declarar una tasa publicitaria (RPM) para esta oportunidad.",
    "production_cost": "Falta una receta de producción asignada (costo real).",
}


def format_range(range_value: dict[str, Any]) -> str:
    return f"{range_value['low']} – {range_value['high']}"


def translate_blocker(code: str) -> str:
    fixed = {
        "resources_not_viable": "Los recursos declarados no alcanzan para este volumen.",
        "resources_not_evaluable": "Faltan datos para evaluar los recursos de producción.",
        "creator_fit_incomplete": "Creator Fit aún no se puede calcular.",
        "production_reviews_pending": "Revisiones de derechos, originalidad o repetición "
        "pendientes.",
    }
    if code in fixed:
        return fixed[code]
    if code.startswith("resource:"):
        return f"Se excede el recurso declarado: {code.removeprefix('resource:')}."
    if code.startswith("unknown:"):
        return f"Falta declarar: {code.removeprefix('unknown:')}."
    return code


def render_home(config: Settings) -> None:
    result = api_request(config, "GET", "/opportunities?limit=100")
    items = result["items"]
    st.subheader("Panorama de oportunidades")
    if not items:
        st.info(
            "Todavía no hay oportunidades evaluadas. "
            "En Operación puedes reanudar el radar sintético y revisar sus ejecuciones."
        )
        return
    counts = Counter(item.get("evaluation_state") or "sin_evaluar" for item in items)
    with_fit = sum(1 for item in items if item.get("creator_fit") is not None)
    with_market = sum(1 for item in items if item.get("market_score") is not None)
    with_final = sum(1 for item in items if item.get("final_score") is not None)
    cols = st.columns(4)
    cols[0].metric("Oportunidades", result["total"])
    cols[1].metric("Con Creator Fit", with_fit)
    cols[2].metric("Con Market Score", with_market)
    cols[3].metric("Listas (score final)", with_final)
    st.dataframe(
        [
            {"Estado": STATE_LABELS.get(key, key), "Cantidad": value}
            for key, value in counts.items()
        ],
        hide_index=True,
        width="stretch",
    )

    st.subheader("Candidatos, ordenados por madurez")
    st.caption(
        "Orden: score final → Market Score → volumen de evidencia (videos observados) → "
        "Creator Fit. La mayoría de los scores siguen null mientras se acumula evidencia; "
        "el orden sigue siendo significativo."
    )
    ranked = sorted(
        items,
        key=lambda item: (
            item.get("final_score") is not None,
            item.get("final_score") or 0,
            item.get("market_score") is not None,
            item.get("market_score") or 0,
            item.get("evidence_videos") or 0,
            item.get("creator_fit") or 0,
        ),
        reverse=True,
    )
    st.dataframe(
        [
            {
                "Tema": item.get("label") or "(sin etiqueta)",
                "Formato": item["format"],
                "Estado": STATE_LABELS.get(item.get("evaluation_state"), "Sin evaluar"),
                "Confianza": item.get("confidence"),
                "Videos observados": item.get("evidence_videos"),
                "Creator Fit": item.get("creator_fit"),
                "Market Score": item.get("market_score"),
                "Score final": item.get("final_score"),
                "Viabilidad": item.get("viability"),
            }
            for item in ranked[:10]
        ],
        hide_index=True,
        width="stretch",
    )

    top = ranked[0]
    st.subheader("Hacia dónde ir ahora")
    audience = top.get("audience_key", "")
    st.markdown(f"**{top.get('label') or '(sin etiqueta)'}** · {top['format']} · {audience}")
    detail = api_request(config, "GET", f"/opportunities/{top['id']}")
    evaluation = detail["evaluations"][0] if detail["evaluations"] else None
    if evaluation is None or not evaluation.get("evidence_available", True):
        st.info(
            "La evaluación más reciente de este candidato ya expiró (conservación) o no "
            "está disponible. Espera al próximo ciclo para ver bloqueos actualizados."
        )
    else:
        explanation = evaluation.get("explanation") or {}
        combined = explanation.get("combined") or {}
        market = explanation.get("market") or {}
        blockers = list(combined.get("blockers") or [])
        missing = list(market.get("missing") or [])
        reasons = [translate_blocker(code) for code in blockers] + [
            MARKET_MISSING_LABELS.get(code, f"Falta componente de mercado: {code}.")
            for code in missing
        ]
        if reasons:
            st.caption("Qué falta para que avance:")
            for reason in dict.fromkeys(reasons):
                st.write("- " + reason)
        else:
            st.success("Sin bloqueos detectados en la última evaluación.")

    profit = api_request(config, "GET", f"/opportunities/{top['id']}/profit")
    st.caption("Ganancia mensual estimada (rango mejor/peor canal competidor, sin inventar vistas)")
    if profit["status"] == "incomplete":
        for code in profit["missing"]:
            st.write("- " + PROFIT_MISSING_LABELS.get(code, f"Falta dato: {code}."))
    else:
        st.dataframe(
            [
                {
                    "Vistas/mes (rango)": format_range(profit["monthly_views"]),
                    "Ingreso USD/mes": format_range(profit["monthly_revenue_usd"]),
                    "Costo USD/mes": format_range(profit["monthly_cost_usd"]),
                    "Ganancia USD/mes": format_range(profit["monthly_profit_usd"]),
                }
            ],
            hide_index=True,
            width="stretch",
        )
        for limitation in profit["limitations"]:
            st.caption("⚠ " + limitation)


def render_backlog(config: Settings) -> None:
    st.subheader("Selección de oportunidades")
    filters = st.columns(3)
    format = filters[0].selectbox(
        "Formato",
        ["", "long", "shorts"],
        format_func=lambda value: {"": "Ambos", "long": "Videos largos", "shorts": "Shorts"}[value],
    )
    state = filters[1].selectbox(
        "Revisión",
        ["", *REVIEW_LABELS],
        format_func=lambda value: REVIEW_LABELS.get(value, "Todas"),
    )
    confidence = filters[2].selectbox(
        "Evidencia",
        ["", "insufficient", "provisional", "supported"],
        format_func=lambda value: {
            "": "Todas",
            "insufficient": "Insuficiente",
            "provisional": "Provisional",
            "supported": "Sustentada",
        }[value],
    )
    query = st.text_input("Buscar tema", max_chars=100)
    sorts = {
        "score": "Puntuación",
        "date": "Fecha",
        "topic": "Tema",
        "format": "Formato",
        "state": "Revisión",
        "confidence": "Confianza",
        "viability": "Viabilidad estimada",
    }
    order = st.columns(2)
    sort_by = order[0].selectbox("Ordenar por", list(sorts), format_func=lambda value: sorts[value])
    descending = order[1].selectbox(
        "Dirección",
        [True, False],
        format_func=lambda value: "Descendente" if value else "Ascendente",
    )
    parameters: dict[str, Any] = {
        "limit": 20,
        "sort_by": sort_by,
        "descending": str(descending).lower(),
    }
    if query:
        parameters["query"] = query
    with st.expander("Más filtros"):
        viability = st.selectbox(
            "Viabilidad estimada",
            ["", "viable", "not_viable", "not_evaluable"],
            format_func=lambda value: {
                "": "Todas",
                "viable": "Viable",
                "not_viable": "No viable",
                "not_evaluable": "No evaluable",
            }[value],
        )
        if viability:
            parameters["viability"] = viability
        if st.checkbox("Exigir puntuación mínima"):
            parameters["minimum_score"] = st.number_input(
                "Puntuación mínima", min_value=0.0, max_value=100.0, value=0.0
            )
        if st.checkbox("Limitar por fecha de evaluación"):
            date = st.date_input("Evaluada desde")
            parameters["evaluated_after"] = datetime.combine(
                date, datetime.min.time(), tzinfo=ZoneInfo(config.timezone)
            ).isoformat()
    for key, value in (("format", format), ("state", state), ("confidence", confidence)):
        if value:
            parameters[key] = value
    signature = urlencode(parameters)
    if st.session_state.get("backlog_filters") != signature:
        st.session_state.backlog_filters = signature
        st.session_state.backlog_page = 1
    page = int(st.number_input("Página", min_value=1, value=1, step=1, key="backlog_page"))
    parameters["offset"] = (page - 1) * 20
    filters_query = "?" + urlencode(parameters)
    result = api_request(config, "GET", "/opportunities" + filters_query)
    if not result["items"]:
        st.info(
            "No hay resultados en esta página. Revisa los filtros o vuelve a la primera página; "
            "una lista vacía no demuestra que no existan oportunidades."
        )
        return
    st.caption(
        f"{result['total']} oportunidades en esta consulta. No se completa un top artificial."
    )
    if any(item.get("source_mode") == "synthetic" for item in result["items"]):
        st.warning("Esta vista contiene datos sintéticos: no son recomendaciones de inversión.")
    display = [
        item | {"evaluated_at": local_time(item.get("evaluated_at"), config.timezone)}
        for item in result["items"]
    ]
    st.dataframe(display, hide_index=True, width="stretch")
    labels = {
        item["id"]: f"{item['label'] or 'Grupo sin etiqueta'} · {item['format']} · {item['id'][:8]}"
        for item in result["items"]
    }
    selected = st.selectbox("Abrir detalle", list(labels), format_func=lambda key: labels[key])
    detail = api_request(config, "GET", f"/opportunities/{selected}")
    tabs = st.tabs(
        [
            "Análisis",
            "Evidencia original",
            "Historial y decisión",
            "Producción",
            "Publicidad y puntuación",
        ]
    )
    with tabs[0]:
        grouping = detail.get("grouping")
        if grouping:
            st.caption("Agrupación temática · " + grouping["method"])
            if grouping["ambiguous_matches"]:
                st.warning("Correspondencia ambigua: este grupo no se fusionó automáticamente.")
            elif grouping["method"] in {"noise", "unclassified"}:
                st.info("Sin evidencia suficiente para confirmar un subnicho.")
            elif grouping["fallback_reason"]:
                st.info("Categoría del proveedor; no es un agrupamiento semántico validado.")
            with st.expander("Método y trazabilidad temática"):
                render_structured(grouping)
        if detail["evaluations"]:
            latest = detail["evaluations"][0]
            if latest.get("source_mode") == "synthetic":
                st.warning(
                    "Evaluación sintética de prueba, independiente del modo actual del radar."
                )
            st.caption("Evaluación: " + local_time(latest["created_at"], config.timezone))
            if not latest["evidence_available"]:
                st.warning(
                    "La evidencia caducó. Esta evaluación ya no es completamente verificable."
                )
            explanation = latest["explanation"] or {}
            narrative = explanation.get("narrative")
            if narrative:
                st.subheader("Explicación de la evaluación")
                for claim in narrative["claims"]:
                    st.write(claim["text"])
                st.caption(
                    "IA: énfasis ordenado sobre afirmaciones verificadas."
                    if narrative["enrichment"] == "llm_emphasis_only"
                    else "Explicación determinista; no necesita una llamada de IA."
                )
                with st.expander("Trazabilidad de cada afirmación"):
                    render_structured(narrative)
                    enrichment = explanation.get("enrichment")
                    if enrichment:
                        st.caption("Enriquecimiento")
                        render_structured(enrichment)
            scores = st.columns(3)
            for column, label, key in zip(
                scores,
                ("Mercado", "Creator Fit", "Puntuación combinada"),
                ("market_score", "creator_fit", "final_score"),
                strict=True,
            ):
                value = latest.get(key)
                column.metric(
                    label, "No disponible" if value is None else f"{float(value):.1f} / 100"
                )
            st.caption(
                "Confianza en la evidencia: "
                + {
                    "insufficient": "insuficiente",
                    "provisional": "provisional",
                    "supported": "sustentada",
                }.get(latest["confidence"], latest["confidence"])
            )
            combined = explanation.get("combined")
            if combined and combined["resource_gate"] != "viable":
                st.warning(
                    "Los recursos excedidos o desconocidos impiden dar por viable esta propuesta, "
                    "independientemente del score."
                )
            st.caption(
                "Puntuaciones heurísticas, no probabilidades de éxito "
                "ni autorización para lanzar un canal."
            )
            temporal = explanation.get("temporal")
            if temporal:
                st.caption(
                    "Cambios observados en los mismos videos; no son vistas/día desde publicación."
                )
                if temporal["trend_relative_change"] is not None:
                    st.metric(
                        "Cambio de velocidad observada", f"{temporal['trend_relative_change']:+.1%}"
                    )
                else:
                    st.info(
                        "Tendencia no calculable: "
                        + TEMPORAL_REASONS.get(temporal["reason"], "historial insuficiente")
                    )
                with st.expander("Intervalos y cobertura temporal"):
                    render_structured(temporal)
            with st.expander("Detalle técnico completo de la evaluación"):
                render_structured(explanation or {"estado": "evidencia_no_disponible"})
    with tabs[1]:
        for evidence in detail["evidence"]:
            st.caption(
                "Consulta original: " + local_time(evidence.get("fetched_at"), config.timezone)
            )
            if evidence["payload"] is None:
                st.warning("Evidencia caducada; no se conserva una copia en la explicación.")
            else:
                st.json(evidence["payload"], expanded=False)
    with tabs[2]:
        st.caption("Seleccionar aquí no crea canales, no compra herramientas ni publica videos.")
        decision = detail["decision"]
        with st.form("review-decision"):
            next_state = st.selectbox(
                "Estado de revisión",
                list(REVIEW_LABELS),
                index=list(REVIEW_LABELS).index(decision["state"]),
                format_func=lambda key: REVIEW_LABELS[key],
            )
            note = st.text_area("Motivo o nota", value=decision["note"], max_chars=4000)
            if st.form_submit_button("Guardar decisión"):
                api_request(
                    config,
                    "POST",
                    f"/opportunities/{selected}/decisions",
                    body={
                        "state": next_state,
                        "note": note,
                        "expected_version": decision["version"],
                    },
                )
                st.rerun()
        render_history(config, selected, detail)
    with tabs[3]:
        render_production(config, selected, detail["opportunity"])
    with tabs[4]:
        render_scoring(config, selected, detail["opportunity"])


def render_history(config: Settings, opportunity_id: str, detail: dict[str, Any]) -> None:
    st.subheader("Cambios entre evaluaciones")
    labels = {
        "first_evaluation": "Primera evaluación: todavía no hay comparación.",
        "evidence_unavailable": "Evidencia caducada o retirada: comparación no disponible.",
        "scope_changed": "Cambió el modo de datos: versiones no comparables.",
        "method_changed": "Cambió el método o sus referencias; no se calcula un delta numérico.",
        "component_coverage_changed": "Cambió el conjunto de componentes disponibles.",
        "data_changed": "Cambiaron las métricas o la evidencia temporal.",
        "assumptions_changed": "Cambiaron los supuestos de producción, perfil o publicidad.",
        "unexplained_score_change": "Cambió la puntuación sin causa identificable en las copias.",
        "evaluation_state_changed": "Cambió el estado o la confianza.",
        "unchanged": "Sin cambios en los datos, método y supuestos comparados.",
    }
    comparison = detail.get("comparison")
    versions = [item["version"] for item in detail["evaluations"]]
    if len(versions) > 1:
        current = st.selectbox(
            "Evaluación actual", versions[:-1], key="compare-current-" + opportunity_id
        )
        previous = st.selectbox(
            "Evaluación anterior",
            [version for version in versions if version < current],
            key="compare-previous-" + opportunity_id,
        )
        comparison = api_request(
            config,
            "GET",
            f"/opportunities/{opportunity_id}/comparison?previous_version={previous}&current_version={current}",
        )
    if comparison:
        for change in comparison["changes"]:
            st.write(labels.get(change, change))
        with st.expander("Diferencias y límites de la comparación"):
            render_structured(comparison)
    else:
        st.info("Todavía no hay evaluaciones que comparar.")
    st.subheader("Posiciones históricas")
    st.caption(
        "Puestos dentro del mismo formato, idioma, modo, método y perfil. "
        "Empates comparten puesto. Son cortes históricos, no una clasificación en vivo "
        "ni autorización para invertir."
    )
    rank_labels = {
        "first_snapshot": "Primer corte guardado",
        "evidence_unavailable": "Clasificación caducada o retirada",
        "eligibility_changed": "Cambió la elegibilidad; no equivale a perder puestos",
        "unranked": "Sin posición calculable",
        "comparison_scope_changed": "Cambió el grupo de comparación; puestos no comparables",
        "unchanged": "Misma posición",
        "other_candidates_changed": "Desplazamiento por otros candidatos; no implica deterioro",
        "relative_rank_and_own_evaluation_changed": (
            "Cambió la posición y la evaluación propia; no se atribuye una causa única"
        ),
    }
    for item in detail.get("ranking_history", []):
        st.write(
            f"Corte {item['sequence']} · {local_time(item['created_at'], config.timezone)} · "
            f"puesto {item['position'] if item['position'] is not None else 'no disponible'}"
        )
        st.caption(rank_labels[item["change"]["kind"]])
    if not detail.get("ranking_history"):
        st.info("Aún no se ha guardado una clasificación para este modo y perfil.")
    with st.expander("Evaluaciones y posiciones guardadas"):
        st.caption("Evaluaciones")
        render_structured(detail["evaluations"])
        st.caption("Posiciones")
        render_structured(detail.get("ranking_history", []))


def render_scoring(config: Settings, opportunity_id: str, opportunity: dict[str, Any]) -> None:
    saved = api_request(config, "GET", f"/opportunities/{opportunity_id}/scoring")
    st.caption(
        "Supuestos actuales. Guardarlos se aplica al próximo análisis; "
        "no altera evaluaciones históricas ni inicia consultas."
    )
    if saved["expired"]:
        st.warning(
            "La configuración anterior caducó y sus datos fueron eliminados; "
            "no se reutiliza una versión anterior."
        )
    advertising = saved["advertising"]
    if advertising["status"] == "unavailable":
        st.info(
            "Potencial publicitario no disponible: falta evidencia utilizable. "
            "No equivale a ingresos de cero."
        )
    else:
        benchmark = advertising["benchmark"]
        rate = benchmark["rate"]
        st.metric("Rango publicitario supuesto, USD por 1.000", f"{rate['low']} – {rate['high']}")
        st.caption("Unidad: " + benchmark["unit"] + " · Fuente: " + benchmark["source"])
    st.warning(
        "Cualquier ingreso es condicional a elegibilidad y monetización activa. "
        "No se proyectan cobros para un canal nuevo."
    )
    st.caption(
        "Inglés no determina la geografía de espectadores. CPM y RPM total no sustituyen "
        "una tasa solo publicitaria. Shorts usa engaged views, no todas las reproducciones."
    )
    with st.expander("Fuente, rango, geografía, condiciones y datos faltantes"):
        render_structured(advertising)
    template = saved["configuration"] or {
        "format": opportunity["format"],
        "language": opportunity["language"],
        "audience_key": opportunity["audience_key"],
        "references": None,
        "advertising": None,
        "relevance_review": None,
        "retention_basis": "",
        "retain_until": None,
    }
    st.caption(
        "Editor técnico: documenta fuente y conservación autorizada. Sin referencias revisadas "
        "por formato, Mercado permanece sin calibrar. Consulta docs/advertising-scoring.md; "
        "no hay tarifas prellenadas."
    )
    with st.form("scoring-" + opportunity_id):
        raw = st.text_area(
            "Supuestos de puntuación (JSON)",
            json.dumps(template, indent=2, ensure_ascii=False),
            height=300,
        )
        if st.form_submit_button("Guardar supuestos de puntuación"):
            try:
                configuration = json.loads(raw)
            except json.JSONDecodeError:
                st.error("El JSON no es válido. Revisa comillas y comas.")
            else:
                api_request(
                    config,
                    "POST",
                    f"/opportunities/{opportunity_id}/scoring",
                    body={"configuration": configuration, "expected_version": saved["version"]},
                )
                st.success(
                    "Versión guardada para el siguiente análisis; "
                    "no se ha gastado ni activado ningún servicio."
                )


def render_creator_fit(assessment: dict[str, Any]) -> None:
    # "plan" and "profile" duplicate the editable JSON form shown right below.
    render_structured({k: v for k, v in assessment.items() if k not in {"plan", "profile"}})
    st.caption("La receta y el perfil completos están en el editor de abajo.")


def render_production(config: Settings, opportunity_id: str, opportunity: dict[str, Any]) -> None:
    saved = api_request(config, "GET", f"/opportunities/{opportunity_id}/production")
    st.caption("Estimación manual para esta oportunidad; no crea canales ni contrata herramientas.")
    assessment = saved["assessment"]
    if assessment:
        if assessment["score"] is None:
            st.info(
                "Creator Fit incompleto: faltan supuestos, costes, herramientas o valoraciones."
            )
        else:
            st.metric("Creator Fit estimado", assessment["score"] + " / 100")
        if any(value.strip().lower() == "pending" for value in assessment["reviews"].values()):
            st.warning("Hay revisiones pendientes de derechos, originalidad o repetición.")
        st.caption("El Fit no certifica derechos ni elegibilidad para monetización.")
        if assessment["resources"]["status"] == "not_viable":
            st.warning("El volumen no cabe en los recursos declarados, aunque el Fit sea alto.")
        st.caption(
            "Recalculado con el perfil actual. Las evaluaciones históricas conservan su contexto."
        )
        with st.expander("Costes, horas, capacidad y revisiones pendientes"):
            render_creator_fit(assessment)
    template = saved["plan"] or {
        "recipe": {
            "key": "recipe-" + opportunity_id,
            "version": "v1",
            "audience_key": opportunity["audience_key"],
            "language": opportunity["language"],
            "format": opportunity["format"],
            "stages": [
                {
                    "name": name,
                    "automation": "unknown",
                    "source": None,
                    "variable_usd_per_video": None,
                    "human_hours_per_video": None,
                    "tool_key": None,
                    "tool_units_per_video": None,
                    "tool_capacity_unit": None,
                }
                for name in STAGES
            ],
            "rework_margin": "0.20",
            "anchors": {},
            "rights_review": "pending",
            "originality_review": "pending",
            "repetition_review": "pending",
        },
        "videos_per_month": 4,
        "tools": [],
        "radar_monthly_usd": None,
        "reserve_usd": "0",
    }
    st.caption(
        "Editor técnico: completa rangos y fuentes. "
        "Cambia la versión al editar una receta guardada."
    )
    with st.form("production-plan-" + opportunity_id):
        raw = st.text_area(
            "Receta y supuestos (JSON)",
            json.dumps(template, indent=2, ensure_ascii=False),
            height=350,
        )
        if st.form_submit_button("Guardar receta y evaluar"):
            try:
                plan = json.loads(raw)
            except json.JSONDecodeError:
                st.error("El JSON no es válido. Revisa comillas y comas.")
            else:
                result = api_request(
                    config,
                    "POST",
                    f"/opportunities/{opportunity_id}/production",
                    body={
                        "plan": plan,
                        "expected_version": saved["version"],
                    },
                )
                render_creator_fit(result["assessment"])
                st.success("Versión guardada; no se inició ninguna producción.")
    st.caption(
        "Para varios canales, usa Escenarios: una receta aislada no reserva capacidad compartida."
    )


def render_configuration(config: Settings) -> None:
    st.subheader("Recursos compartidos")
    profile = api_request(config, "GET", "/profile")
    version = profile.pop("version_number")
    with st.form("resource-profile"):
        target = st.number_input(
            "Objetivo mensual, USD", min_value=0.0, value=float(profile["monthly_target_usd"])
        )
        ceiling = st.number_input(
            "Techo mensual, USD", min_value=0.0, value=float(profile["monthly_ceiling_usd"])
        )
        hours = st.number_input(
            "Horas disponibles por semana", min_value=0.1, value=float(profile["weekly_hours"])
        )
        reserve = st.number_input(
            "Reserva mensual mínima, USD",
            min_value=0.0,
            value=float(profile["monthly_reserve_usd"]),
        )
        per_run = st.number_input(
            "Créditos máximos por ejecución", min_value=0, value=profile["credits_per_run"]
        )
        per_week = st.number_input(
            "Créditos máximos por semana", min_value=0, value=profile["credits_per_week"]
        )
        per_cycle = st.number_input(
            "Créditos máximos por ciclo del proveedor",
            min_value=0,
            value=profile["credits_per_cycle"],
        )
        radar_limits = {}
        for period, label in (
            ("operation", "operación"),
            ("run", "ejecución"),
            ("week", "semana"),
            ("month", "mes"),
        ):
            key = f"radar_usd_per_{period}"
            radar_limits[key] = str(
                st.number_input(
                    f"Sublímite del radar por {label}, USD",
                    min_value=0.0,
                    value=float(profile[key]),
                )
            )
        st.caption("Los sublímites USD comienzan en cero; no convierten créditos en dólares.")
        discovery_limits = {}
        for key, label, minimum, maximum, default in (
            ("selected_refresh_hours", "Actualizar seleccionados cada (horas)", 1, None, 24),
            ("watching_refresh_hours", "Actualizar en seguimiento cada (horas)", 1, None, 168),
            ("discovery_max_channels", "Máximo de canales por lote", 2, 10, 10),
            ("discovery_max_expansions", "Máximo de ampliaciones por lote", 0, 5, 2),
        ):
            discovery_limits[key] = st.number_input(
                label, min_value=minimum, max_value=maximum, value=profile.get(key, default)
            )
        exploration_share = st.number_input(
            "Capacidad objetivo para descubrir familias (%)",
            min_value=1.0,
            max_value=100.0,
            value=float(profile["exploration_share"]) * 100,
        )
        st.caption(
            "Las cadencias están sujetas a presupuesto y cola; "
            "no garantizan una actualización puntual."
        )
        st.caption(
            "Claude, ChatGPT y Google AI Pro existentes quedan excluidos. "
            "Las suscripciones de chat no se asumen como saldo API."
        )
        if st.form_submit_button("Guardar límites"):
            profile.update(
                monthly_target_usd=str(target),
                monthly_ceiling_usd=str(ceiling),
                weekly_hours=str(hours),
                monthly_reserve_usd=str(reserve),
                credits_per_run=per_run,
                credits_per_week=per_week,
                credits_per_cycle=per_cycle,
                exploration_share=str(exploration_share / 100),
                **discovery_limits,
                **radar_limits,
            )
            api_request(
                config, "PUT", "/profile", body={"profile": profile, "expected_version": version}
            )
            st.success("Límites guardados. Esto no habilita proveedores reales.")
    render_default_recipes(config)


def render_default_recipes(config: Settings) -> None:
    st.subheader("Receta de producción por defecto (Creator Fit)")
    st.caption(
        "Se aplica automáticamente a toda oportunidad nueva sin receta propia. "
        "Editar aquí no cambia evaluaciones ya calculadas; el editor de una oportunidad "
        "puntual siempre tiene prioridad sobre este valor por defecto."
    )
    for video_format, label in (("long", "Videos largos"), ("shorts", "Shorts")):
        saved = api_request(config, "GET", f"/defaults/production-recipes/{video_format}")
        with st.expander(label):
            assessment = saved["assessment"]
            if assessment["score"] is not None:
                st.metric("Creator Fit por defecto", assessment["score"] + " / 100")
            render_creator_fit(assessment)
            st.caption(
                "Editor técnico: completa rangos y fuentes. "
                "Sube la versión para que las nuevas oportunidades usen los cambios."
            )
            with st.form(f"default-recipe-{video_format}"):
                raw = st.text_area(
                    "Receta y herramientas por defecto (JSON)",
                    json.dumps(
                        {"recipe": saved["recipe"], "tools": saved["tools"]},
                        indent=2,
                        ensure_ascii=False,
                    ),
                    height=450,
                )
                if st.form_submit_button("Guardar receta por defecto"):
                    try:
                        template = json.loads(raw)
                    except json.JSONDecodeError:
                        st.error("El JSON no es válido. Revisa comillas y comas.")
                    else:
                        api_request(
                            config,
                            "POST",
                            f"/defaults/production-recipes/{video_format}",
                            body={"template": template, "expected_version": saved["version"]},
                        )
                        st.success("Receta por defecto actualizada.")


def scenario_template() -> dict[str, Any]:
    return {
        "name": "Comparación de dos canales",
        "proposals": [
            {
                "channel_key": f"canal-{index}",
                "opportunity_keys": [],
                "videos_per_month": 4,
                "recipe": {
                    "key": f"receta-{index}",
                    "version": "borrador-v1",
                    "format": "long",
                    "stages": [{"name": name} for name in STAGES],
                },
            }
            for index in (1, 2)
        ],
        "tools": [],
        "radar_monthly_usd": None,
        "reserve_usd": "0",
    }


def render_scenarios(config: Settings) -> None:
    st.subheader("Escenarios de varios canales")
    st.write(
        "Compara combinaciones sin descontar saldo real. "
        "El extremo superior de costes y horas decide si caben."
    )
    st.caption(
        "Editor técnico inicial: completa costes, horas y fuentes por etapa; "
        "declara cada herramienta compartida una sola vez. "
        "Un dato esencial desconocido mantiene el escenario no evaluable."
    )
    with st.form("scenario"):
        raw = st.text_area(
            "Escenario JSON",
            value=json.dumps(scenario_template(), ensure_ascii=False, indent=2),
            height=400,
        )
        if st.form_submit_button("Calcular y guardar escenario"):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                st.error("El JSON no es válido. Revisa comillas y comas.")
            else:
                result = api_request(config, "POST", "/scenarios", body=payload)
                render_structured(result["result"])
    saved = api_request(config, "GET", "/scenarios")
    for item in saved["items"]:
        with st.expander(item["name"]):
            render_structured(item["result"])


SCORE_COMPONENT_LABELS = {
    "concentration": "Concentración",
    "breakout": "Tasa de breakout",
    "demand": "Demanda",
    "rpm": "RPM publicitario",
    "growth": "Crecimiento",
}
GROWTH_TIER_LABELS = {
    "measured": "medido",
    "lifetime_average": "promedio de vida",
    "insufficient_evidence": "sin datos",
}


def render_channel_analysis(config: Settings) -> None:
    st.subheader("Análisis de canal")
    st.caption(
        "Investiga si hay oportunidad de competir en el nicho de un canal real. Usa su "
        "@handle o su ID de canal (UC...); URLs con /c/ o /user/ todavía no se reconocen."
    )
    with st.form("channel-analysis-request"):
        channel_input = st.text_input("URL, handle o ID del canal")
        st.caption(
            "Costo máximo real por análisis: hasta 50 créditos vidIQ y 1 búsqueda "
            "(100 unidades) de cuota de YouTube."
        )
        if st.form_submit_button("Analizar") and channel_input:
            api_request(
                config,
                "POST",
                "/channel-analyses",
                body={"channel_input": channel_input},
                headers={"Idempotency-Key": str(uuid4())},
            )
            st.success("Análisis encolado. Aparecerá abajo cuando el radar lo procese.")

    result = api_request(config, "GET", "/channel-analyses?limit=50")
    if not result["items"]:
        st.info("Todavía no hay análisis de canal guardados.")
        return

    st.subheader("Comparativa de oportunidad")
    # None (no score yet, e.g. panorama still incomplete) sorts last, never first --
    # a real 0-100 score always outranks "unknown" rather than tying with a high score.
    overview = sorted(
        result["items"],
        key=lambda item: item["score"]["value"] if item["score"]["value"] is not None else -1.0,
        reverse=True,
    )
    st.dataframe(
        [
            {
                "Canal": item.get("channel_input"),
                "Score": item["score"]["value"],
                "Posición": (item.get("snapshot") or {}).get("metrics", {}).get("target_position"),
                "Nicho": (item.get("snapshot") or {})
                .get("advertising_match", {})
                .get("matched_niche"),
                "Estado": item.get("status"),
                "Creado": local_time(str(item.get("created_at")), config.timezone),
            }
            for item in overview
        ],
        hide_index=True,
        width="stretch",
    )

    channel_filter = st.selectbox(
        "Ver detalle",
        [item["id"] for item in overview],
        format_func=lambda analysis_id: next(
            item["channel_input"] for item in overview if item["id"] == analysis_id
        ),
    )
    if not channel_filter:
        return

    detail = api_request(config, "GET", f"/channel-analyses/{channel_filter}")
    evidence_available = detail.get("evidence_available", True)
    if not evidence_available:
        st.caption(
            "La evidencia de este análisis expiró por retención; solo se conservan su "
            "configuración y su consumo."
        )

    snapshot = detail.get("snapshot") or {}
    metrics = snapshot.get("metrics", {})
    score = detail["score"]

    st.subheader("Resumen ejecutivo")
    cols = st.columns(4)
    cols[0].metric("Score de oportunidad", score["value"] if score["value"] is not None else "—")
    cols[1].metric("Posición", metrics.get("target_position") or "—")
    cols[2].metric(
        "Nicho asignado",
        snapshot.get("advertising_match", {}).get("matched_niche") or "ninguno",
    )
    growth = snapshot.get("growth", {})
    cols[3].metric("Crecimiento", GROWTH_TIER_LABELS.get(growth.get("tier"), "—"))

    if score["components_used"]:
        st.caption("Componentes del Score (0-100; solo los disponibles cuentan):")
        st.dataframe(
            [
                {
                    "Componente": SCORE_COMPONENT_LABELS.get(key, key),
                    "Valor": round(value, 1) if value is not None else None,
                    "Usado en el Score": key in score["components_used"],
                }
                for key, value in score["components"].items()
            ],
            hide_index=True,
            width="stretch",
        )

    panorama = metrics.get("panorama")
    if panorama:
        st.subheader("Panorama del nicho")
        if panorama["status"] == "computed":
            pmetrics = panorama["metrics"]
            pcols = st.columns(3)
            pcols[0].metric("Videos analizados", pmetrics["videos"])
            pcols[1].metric("Canales comparables", pmetrics["channels"])
            pcols[2].metric(
                "Tasa de breakout",
                f"{pmetrics['breakout_rate']:.1%}"
                if pmetrics["breakout_rate"] is not None
                else "—",
            )
            st.caption(
                f"Concentración (HHI): {pmetrics['hhi']:.3f}"
                if pmetrics["hhi"] is not None
                else "Concentración: sin datos suficientes."
            )
        else:
            st.info(f"Panorama incompleto: {panorama['reason']}")

    profit = metrics.get("profit")
    if profit:
        st.subheader("Ganancia mensual estimada")
        if profit["status"] == "estimated":
            revenue, change = profit["monthly_revenue_usd"], profit["monthly_profit_usd"]
            # monthly_revenue_usd/monthly_profit_usd round-trip through the API as
            # Decimal-backed JSON strings (ProfitEstimate serializes with
            # model_dump(mode="json")), never floats -- format() rejects a str operand.
            st.write(
                f"Ingreso: ${float(revenue['low']):.2f} - ${float(revenue['high']):.2f} · "
                f"Ganancia: ${float(change['low']):.2f} - ${float(change['high']):.2f}"
            )
        else:
            st.info(f"Ganancia incompleta: falta {', '.join(profit.get('missing', ['dato']))}.")

    deep_history = snapshot.get("deep_history")
    if deep_history:
        st.subheader("Historial completo")
        if deep_history["days_to_first_breakout"] is not None:
            st.write(
                f"Días hasta el primer video breakout: {deep_history['days_to_first_breakout']}"
            )
        else:
            st.caption(f"Sin resultado concluyente ({deep_history['status']}).")
    elif evidence_available:
        # Calling /deep-history/estimate when evidence_available is False would 404
        # (the endpoint requires real evidence to size the request), so this is only
        # attempted while there is a live snapshot to estimate against.
        estimate = api_request(
            config, "GET", f"/channel-analyses/{channel_filter}/deep-history/estimate"
        )
        units = estimate.get("quota_units")
        label = (
            f"Ver historial completo (~{units} unidades de cuota real)"
            if units is not None
            else "Ver historial completo (costo desconocido)"
        )
        st.caption("El costo real se muestra en el botón antes de ejecutar la consulta.")
        if st.button(label, key=f"deep-history-{channel_filter}"):
            api_request(config, "POST", f"/channel-analyses/{channel_filter}/deep-history")
            st.success("Historial completo obtenido.")
            st.rerun()

    if st.button("Eliminar este análisis", key=f"delete-{channel_filter}"):
        api_request(config, "DELETE", f"/channel-analyses/{channel_filter}")
        st.success("Análisis eliminado.")
        st.rerun()


def render_pilot_preflight(config: Settings) -> None:
    if st.button("Ver requisitos del piloto real"):
        report = api_request(config, "GET", "/pilot/preflight")
        st.info("Comprobación de solo lectura: no conecta proveedores ni inicia consultas.")
        st.warning("Piloto real pendiente de habilitación.")
        for check in report["checks"]:
            st.write(f"{check['status']} · {check['message']}")
        with st.expander("Políticas registradas y límites del piloto"):
            st.dataframe(report["policies"], hide_index=True, width="stretch")
            render_structured(report["budget"])
        for warning in report["warnings"]:
            st.caption(warning)


def render_operations(config: Settings, status: dict[str, Any]) -> None:
    st.subheader("Operación del radar")
    render_pilot_preflight(config)
    st.caption(
        "Última ejecución satisfactoria: "
        + local_time(status.get("last_success_at"), config.timezone)
    )
    controls = st.columns(3)
    if controls[0].button("Pausar radar", disabled=status["radar_paused"]):
        api_request(config, "PUT", "/radar", body={"paused": True})
        st.rerun()
    if controls[1].button(
        "Reanudar radar sintético",
        disabled=not status["radar_paused"] or status["mode"] != "synthetic",
    ):
        api_request(config, "PUT", "/radar", body={"paused": False})
        st.rerun()
    if controls[2].button("Solicitar exploración", disabled=status["radar_paused"]):
        key = st.session_state.setdefault("manual_run_key", str(uuid4()))
        result = api_request(config, "POST", "/runs", headers={"Idempotency-Key": key})
        st.session_state.manual_run_key = str(uuid4())
        st.success("Ejecución aceptada: " + result["job_id"])
    st.subheader("Ejecuciones y errores")
    page = int(st.number_input("Página de ejecuciones", min_value=1, value=1, step=1))
    jobs = api_request(config, "GET", f"/jobs?offset={(page - 1) * 20}")
    st.caption(f"{jobs['total']} trabajos registrados.")
    if jobs["items"]:
        st.dataframe(jobs["items"], hide_index=True, width="stretch")
    else:
        st.info("Aún no hay ejecuciones.")
    for job in jobs["items"]:
        with st.expander("Consumo de ejecución · " + job["id"]):
            consumption = job.get("consumption")
            if consumption is None:
                st.info("Desglose no disponible en esta versión de la API.")
            elif not consumption["confirmed"] and not consumption["reservations"]:
                st.info("Sin movimientos contables registrados para esta ejecución.")
            else:
                cols = st.columns(2)
                with cols[0]:
                    st.caption("Confirmado")
                    if consumption["confirmed"]:
                        st.dataframe(consumption["confirmed"], hide_index=True, width="stretch")
                    else:
                        st.caption("Sin gasto confirmado.")
                with cols[1]:
                    st.caption("Reservas y cobros inciertos")
                    if consumption["reservations"]:
                        st.dataframe(consumption["reservations"], hide_index=True, width="stretch")
                    else:
                        st.caption("Sin reservas abiertas.")
            st.caption(
                "Gasto confirmado separado de reservas y cobros inciertos; "
                "USD y créditos no se suman. No incluye suscripciones sin ejecución asociada "
                "ni estimaciones de producción."
            )
        coverage = job.get("coverage") or {}
        if not coverage:
            continue
        with st.expander("Cobertura de ejecución · " + job["id"]):
            st.write("Modo: " + job["source_mode"])
            st.write("Trabajo: " + coverage.get("work_kind", "desconocido"))
            if coverage.get("grouping"):
                st.caption("Agrupamiento")
                st.dataframe([coverage["grouping"]], hide_index=True, width="stretch")
            st.write(
                "Familias no exploradas en este lote: "
                + ", ".join(coverage.get("catalog_pending", []))
            )
            st.write(
                "Actualizaciones pendientes al planificar: "
                + str(len(coverage.get("refresh_pending", [])))
            )
            if not coverage.get("complete", False):
                st.warning("Lote parcial: " + str(coverage.get("pending_reason", "sin detalle")))
            st.caption(
                "Instantánea de esta ejecución; no representa cobertura exhaustiva de YouTube."
            )
    st.subheader("Proveedores y condiciones pendientes")
    policies_page = int(st.number_input("Página de políticas", min_value=1, value=1, step=1))
    result = api_request(config, "GET", f"/providers?offset={(policies_page - 1) * 20}")
    st.caption("Estado de configuración por proveedor.")
    st.dataframe(
        [
            {"proveedor": name, **fields}
            for name, fields in result["configuration"].items()
            if isinstance(fields, dict)
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(f"{result['total']} políticas registradas.")
    if result["policies"]:
        st.dataframe(result["policies"], hide_index=True, width="stretch")
    else:
        st.info("Sin políticas registradas todavía.")


def render() -> None:
    st.set_page_config(page_title="NicheRadar · Observatorio", page_icon="◎", layout="wide")
    st.markdown(
        """
    <style>
      :root { --nr-ink: #193653; --nr-blue: #315ed1; --nr-cloud: #edf3fa;
              --nr-amber: #956000; --nr-white: #ffffff; }
      .stApp { background: var(--nr-cloud); color: var(--nr-ink); }
      h1, h2, h3 { font-family: 'Avenir Next', 'Trebuchet MS', sans-serif; }
      .nr-scope { border-left: 5px solid var(--nr-blue); padding: 1rem 1.4rem;
                  background: var(--nr-white); margin-bottom: 1.5rem; }
      .nr-scope small { font-family: ui-monospace, monospace; letter-spacing: .08em; }
      button:focus-visible, input:focus-visible { outline: 3px solid var(--nr-blue); }
      [data-testid="stSidebar"] [data-testid="stRadioGroup"] { gap: .35rem; }
      [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        background: var(--nr-white); border-radius: .5rem; padding: .55rem .9rem;
        transition: background .15s ease, color .15s ease;
      }
      [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background: #dfe9f7; }
      [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) {
        background: var(--nr-blue);
      }
      [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) p {
        color: var(--nr-white); font-weight: 600;
      }
    </style>
    """,
        unsafe_allow_html=True,
    )
    config = Settings()
    if config.dashboard_password is None:
        st.warning("Acceso pendiente: configura NR_DASHBOARD_PASSWORD para abrir el observatorio.")
        st.stop()
    if not st.session_state.get("authenticated", False):
        st.title("NicheRadar")
        with st.form("login"):
            password = st.text_input("Contraseña de acceso", type="password")
            if st.form_submit_button("Entrar"):
                if secrets.compare_digest(
                    password.encode(), config.dashboard_password.get_secret_value().encode()
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta.")
        st.stop()

    st.caption("NICHE RADAR / OBSERVATORIO PERSONAL")
    st.title("Antes de producir, reúne evidencia.")
    st.markdown(
        '<div class="nr-scope"><small>ÁMBITO DE EXPLORACIÓN</small><br>'
        "Contenido en inglés · Videos largos + Shorts · Ingresos publicitarios"
        "</div>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()
    if config.service_token is None:
        st.warning("Configura NR_SERVICE_TOKEN para conectar con la API privada.")
        st.stop()
    try:
        with httpx.Client(
            base_url=config.api_url,
            timeout=5,
            headers={"Authorization": f"Bearer {config.service_token.get_secret_value()}"},
        ) as client:
            response = client.get("/api/v1/status")
            response.raise_for_status()
            status = response.json()
    except httpx.HTTPError:
        st.error("API no disponible o acceso rechazado. Revisa el servicio y su credencial.")
        st.stop()
    if status["mode"] == "synthetic":
        st.info("Modo sintético: los datos de prueba no son oportunidades reales de inversión.")
    if status["radar_paused"]:
        st.warning("Radar pausado. No se están iniciando consultas a proveedores.")
    if status.get("scheduler_attention_job_id"):
        st.warning(
            "La programación requiere atención por un fallo anterior. Revisa el trabajo "
            + status["scheduler_attention_job_id"]
            + ", corrige la causa y pausa/reanuda el radar para autorizar otro intento."
        )
    if not status["database_configured"]:
        st.warning(
            "Configura PostgreSQL y aplica las migraciones para usar el backlog y las ejecuciones."
        )
        return
    render_research_status(config, status)
    page = st.sidebar.radio(
        "Observatorio",
        [
            "Resumen",
            "Backlog",
            "Escenarios",
            "Configuración",
            "Operación",
            "Análisis de canal",
        ],
    )
    if page == "Backlog":
        render_backlog(config)
    elif page == "Escenarios":
        render_scenarios(config)
    elif page == "Configuración":
        render_configuration(config)
    elif page == "Operación":
        render_operations(config, status)
    elif page == "Análisis de canal":
        render_channel_analysis(config)
    else:
        st.caption(
            "Última ejecución satisfactoria: "
            + local_time(status.get("last_success_at"), config.timezone)
        )
        render_home(config)
        st.subheader("Consumo registrado")
        st.caption(
            "Historial completo: gasto confirmado, reservas e incertidumbres. "
            "Las simulaciones de producción no se incluyen como gasto."
        )
        report = api_request(config, "GET", "/consumption")
        cols = st.columns(2)
        with cols[0]:
            st.caption("Confirmado (histórico completo)")
            if report["confirmed"]:
                st.dataframe(report["confirmed"], hide_index=True, width="stretch")
            else:
                st.caption("Sin gasto confirmado registrado.")
        with cols[1]:
            st.caption("Reservas y cobros inciertos")
            if report["reservations"]:
                st.dataframe(report["reservations"], hide_index=True, width="stretch")
            else:
                st.caption("Sin reservas abiertas.")
        st.caption("Saldos de crédito vigentes")
        if report["balances"]:
            st.dataframe(report["balances"], hide_index=True, width="stretch")
        else:
            st.caption("Sin saldos registrados.")
        if report["balance_reconciliations"]:
            st.caption("Conciliaciones recientes")
            st.dataframe(report["balance_reconciliations"], hide_index=True, width="stretch")
        st.caption(report["reconciliation_note"])


if __name__ == "__main__":
    render()
