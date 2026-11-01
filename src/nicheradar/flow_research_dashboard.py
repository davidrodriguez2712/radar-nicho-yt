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
from nicheradar.flow_research.contracts import calibration_total_hours
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
LANGUAGE_NAMES = {
    "en": "Inglés",
    "es": "Español",
    "pt": "Portugués",
    "ru": "Ruso",
    "de": "Alemán",
    "fr": "Francés",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def suggested_language(mix: list[dict[str, Any]]) -> str | None:
    """The dominant detected language, or ``None`` when it is a tie or mostly unknown."""
    if not mix or mix[0]["language"] == "unknown":
        return None
    if len(mix) > 1 and mix[1]["share_pct"] == mix[0]["share_pct"]:
        return None
    return str(mix[0]["language"])


def language_options(mix: list[dict[str, Any]]) -> list[str]:
    """Detected languages first (largest share), then the usual ones; never ``unknown``."""
    detected = [item["language"] for item in mix if item["language"] != "unknown"]
    return detected + [code for code in LANGUAGE_NAMES if code not in detected]


def mix_text(mix: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{'sin dato' if item['language'] == 'unknown' else language_name(item['language'])} "
        f"{item['share_pct']:g}%"
        for item in mix
    )


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


RIGHTS_VERDICT = {
    "cleared": "resuelto",
    "conditional": "con condiciones",
    "blocked": "bloqueado",
}
ORIGIN = {
    "own_capture": "captura propia",
    "own_generation": "generación propia",
    "licensed": "con licencia",
    "platform_policy": "política del editor o plataforma",
    "public_domain": "dominio público",
    "third_party": "de terceros",
    "unknown": "sin determinar",
}


def rights_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Material": item["kind"],
            "Descripción": item["description"],
            "Origen": ORIGIN[item["origin"]],
            "Licencia o política": item["license_or_policy"],
            "Requiere permiso": "sí" if item["requires_permission"] else "no",
            "Plan del permiso": item.get("permission_plan") or "",
            "Fuente": item.get("source_id") or "",
        }
        for item in content["rights"]["materials"]
    ]


def stage_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Etapa": stage["step"],
            "Automatización": AUTOMATION[stage["mode"]],
            "Cómo se automatiza": stage["approach"],
            "Herramientas": ", ".join(
                f"{tool['name']} ({tool['interface']}, US$ {float(tool['cost_usd_per_video']):.2f}"
                " por video)"
                for tool in stage["tools"]
            ),
            "Entrada": stage["inputs"],
            "Salida": stage["outputs"],
            "Compuerta de calidad": stage["quality_gate"],
            "Si falla": f"{stage['failure_mode']} → {stage['retry_policy']}",
            "Minutos humanos": stage["human_minutes_per_video"],
            "Sigue siendo humano": stage.get("stays_human") or "",
        }
        for stage in content["automation_plan"]["stages"]
    ]


def milestone_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Hito": item["order"],
            "Nombre": item["name"],
            "Descripción": item["description"],
            "Criterios de aceptación": " | ".join(item["acceptance_criteria"]),
            "Depende de": ", ".join(str(dep) for dep in item["depends_on"]),
        }
        for item in sorted(content["automation_plan"]["milestones"], key=lambda m: m["order"])
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
            "Minutos humanos por video (régimen)": step["human_minutes_per_video"],
            "Automatización": AUTOMATION[step["automation"]],
            "Herramientas": ", ".join(step["tools"]),
            "Sigue siendo humano": step.get("stays_human") or "",
        }
        for step in sorted(content["production_flow"], key=lambda step: step["order"])
    ]


BASIS = {
    "measured": "medido",
    "mapped_flow_equivalent": "flujo equivalente ya mapeado",
    "estimate": "estimación",
}


def calibration_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    regime = {step["name"]: step["human_minutes_per_video"] for step in content["production_flow"]}
    return [
        {
            "Etapa": item["step"],
            "Minutos en régimen": regime.get(item["step"]),
            "Minutos en calibración": item["minutes_per_video"],
        }
        for item in content["calibration"]["minutes_by_step"]
    ]


def regime_text(evidence: dict[str, Any]) -> str:
    text = f"Régimen: {BASIS[evidence['basis']]}"
    if evidence.get("reference_channel"):
        text += f" · canal de referencia {evidence['reference_channel']}"
    if evidence.get("reference_minutes_per_video") is not None:
        text += (
            f" · {evidence['reference_minutes_per_video']} min en "
            f"{evidence['reference_sample_videos']} videos"
        )
    return text


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
    if "rights" in content:
        st.markdown("**Derechos del material**")
        st.text(f"Veredicto: {RIGHTS_VERDICT[content['rights']['verdict']]}")
        st.text(content["rights"]["summary"])
        st.dataframe(rights_rows(content), hide_index=True, width="stretch")
        for condition in content["rights"]["conditions"]:
            st.text("Condición: " + condition)
    else:
        st.caption(
            f"Dossier {content['schema_version']}: no evalúa derechos ni plan de automatización."
        )
    st.markdown("**Competencia de referencia**")
    st.dataframe(competitor_rows(content), hide_index=True, width="stretch")
    st.markdown("**Flujo de producción**")
    st.dataframe(flow_rows(content), hide_index=True, width="stretch")
    if "calibration" in content:
        calibration = content["calibration"]
        evidence = content["steady_state_evidence"]
        hours = calibration_total_hours(
            calibration["setup_hours"],
            calibration["videos"],
            sum(item["minutes_per_video"] for item in calibration["minutes_by_step"]),
        )
        st.markdown("**Calibración y régimen**")
        st.text(
            f"Calibración: {calibration['videos']} videos, {hours:g} horas en total "
            f"({calibration['setup_hours']:g} h de preparación). "
            f"Salida: {calibration['exit_criterion']['statement']}"
        )
        st.dataframe(calibration_rows(content), hide_index=True, width="stretch")
        st.text(regime_text(evidence))
        st.text("Formato: " + evidence["format_match"])
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
    if "automation_plan" in content:
        plan = content["automation_plan"]
        minutes = sum(step["human_minutes_per_video"] for step in content["production_flow"])
        st.markdown("**Plan de automatización por etapa**")
        st.text(f"Minutos humanos por video en régimen (suma del flujo): {minutes}")
        st.text(plan["summary"])
        st.dataframe(stage_rows(content), hide_index=True, width="stretch")
        st.markdown("**Hitos de implementación**")
        st.dataframe(milestone_rows(content), hide_index=True, width="stretch")
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


def render_flow_research(
    config: Settings, api: ApiRequest, entry: dict[str, Any], language_mix: list[dict[str, Any]]
) -> None:
    st.subheader("Investigación de flujo")
    suggestion = suggested_language(language_mix)
    options = language_options(language_mix)
    st.caption(
        "Idioma de las fichas del nicho: "
        + (mix_text(language_mix) or "sin fichas")
        + ". La competencia, los precios y las herramientas cambian por idioma: elige el de "
        "esta investigación."
    )
    language = st.selectbox(
        "Idioma de la investigación",
        options,
        index=options.index(suggestion) if suggestion else None,
        format_func=language_name,
        placeholder="Elige un idioma",
        key=f"flow_language_{entry['niche_label']}_{entry['format']}",
    )
    if suggestion is None:
        st.caption("No hay un idioma dominante claro: no se preselecciona ninguno.")
    params: dict[str, Any] = {"niche_label": entry["niche_label"], "format": entry["format"]}
    if language is not None:
        params["language"] = language
    items = api(config, "GET", "/flow-research?" + urlencode(params | {"limit": 1}))["items"]
    latest = items[0] if items else None
    active = latest is not None and latest["status"] in ("pendiente", "en_curso")
    reason = ineligible_reason(entry)
    if reason is not None:
        st.caption(REASONS[reason])
    if latest is not None:
        st.caption("Última investigación: " + STATUS_LABELS[latest["status"]])
    if st.button(
        "Iniciar investigación de flujo", disabled=reason is not None or active or language is None
    ):
        api(
            config,
            "POST",
            "/flow-research",
            body={
                "niche_label": entry["niche_label"],
                "format": entry["format"],
                "language": language,
            },
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
