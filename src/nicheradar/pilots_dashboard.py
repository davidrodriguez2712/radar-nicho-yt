# src/nicheradar/pilots_dashboard.py
"""Panel de portafolio (solo lectura): pilotos, estado, lo reportado y lo que se propone.

El humano autoriza y decide por la API o ``scripts/pilots.py``; aquí solo se mira. El texto
libre (reglas, razones, notas) se muestra con ``st.text``, nunca como Markdown.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import streamlit as st

from nicheradar.config import Settings

ApiRequest = Callable[..., dict[str, Any]]
STATUS_LABELS = {
    "autorizado": "autorizado: esperando que el canal lo recoja",
    "entregado": "entregado: el canal ya tiene el paquete",
    "en_ejecucion": "en ejecución",
    "decision_pendiente": "decisión pendiente: te toca decidir",
    "cerrado": "cerrado",
    "cancelado": "cancelado",
}
PROPOSALS = {
    "seguir": "seguir",
    "cerrar": "cerrar",
    "sin_datos_suficientes": "sin datos suficientes",
    "revision_manual": "lo juzgas tú",
}
RULE_STATUS = {
    "pendiente": "pendiente (el hito no llegó)",
    "cumple": "cumple",
    "no_cumple": "no cumple",
    "sin_datos_suficientes": "sin datos suficientes",
    "no_evaluable": "no se puede evaluar: lo decides tú",
    "revision_manual": "lo juzgas tú",
}
STALE_AFTER_HOURS = 72


def contact_label(last_contact: str | None, now: datetime) -> str:
    """«sin contacto hace X» cuando el canal lleva días sin hablar con NicheRadar."""
    if last_contact is None:
        return "nunca"
    hours = int((now - datetime.fromisoformat(last_contact)).total_seconds() // 3600)
    if hours < 1:
        return "hace menos de 1 h"
    if hours < 48:
        return f"hace {hours} h"
    suffix = " (sin contacto)" if hours >= STALE_AFTER_HOURS else ""
    return f"hace {hours // 24} d{suffix}"


def portfolio_rows(items: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        totals = item["totals"]
        rows.append(
            {
                "Piloto": item["pilot_id"],
                "Canal": item["target_channel"] or "(sin canal)",
                "Nicho": item["niche_label"],
                "Formato": item["format"],
                "Estado": STATUS_LABELS[item["status"]],
                "Videos": f"{totals['published']} publicados / {totals['measured']} medidos",
                "Costo real (US$)": float(totals["spent_usd"]),
                "NicheRadar propone": PROPOSALS[item["proposal"]["action"]],
                "¿Te toca decidir?": "sí" if item["needs_decision"] else "no",
                "Contacto del canal": contact_label(item["channel_last_contact_at"], now),
            }
        )
    return rows


def rule_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Regla": rule["text"],
            "Hito": rule["milestone"],
            "Estado": RULE_STATUS[rule["status"]],
            "Detalle": rule["detail"],
        }
        for rule in detail["evaluation"]["rules"]
    ]


def event_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Cuándo": event["at"], "Quién": event["actor"], "Qué": event["kind"]}
        for event in detail["events"]
    ]


def totals_text(detail: dict[str, Any]) -> list[str]:
    totals = detail["evaluation"]["totals"]
    minutes = f"{totals['machine_minutes']} min de máquina" + (
        "" if totals["machine_minutes_complete"] else " (incompleto: faltan videos sin dato)"
    )
    return [
        f"{totals['videos']} videos reportados · {totals['published']} publicados · "
        f"{totals['measured']} medidos",
        f"Costo real US$ {float(totals['spent_usd']):.2f} · equivalente de suscripción "
        f"US$ {float(totals['equivalent_usd']):.2f} (no es dinero gastado) · {minutes}",
    ]


def render_portfolio(config: Settings, api: ApiRequest) -> None:
    st.subheader("Portafolio de pilotos")
    st.caption(
        "Solo lectura. NicheRadar propone seguir o cerrar con los números a la vista; "
        "con pocos videos medidos dice «sin datos suficientes». Tú autorizas y decides."
    )
    items = api(config, "GET", "/pilots")["items"]
    if not items:
        st.info("Todavía no hay pilotos. Se crean al autorizar un nicho con dossier listo.")
        return
    now = datetime.now(UTC)
    st.dataframe(portfolio_rows(items, now), hide_index=True, width="stretch")
    chosen = st.selectbox("Ver detalle", [item["pilot_id"] for item in items])
    detail = api(config, "GET", f"/pilots/{chosen}")
    st.markdown(f"**{detail['pilot_id']}** · {STATUS_LABELS[detail['status']]}")
    package = detail["package"]
    st.text(
        f"Nicho: {package['niche']['label']} ({package['niche']['format']}, "
        f"idioma {package['niche']['language']}) · autorizado por {detail['authorized_by']} el "
        f"{detail['authorized_at'][:10]} · válido hasta {detail['valid_until'][:10]}"
    )
    budget = package["budget"]
    st.text(
        f"Presupuesto US$ {budget['low']} / {budget['likely']} / {budget['high']} "
        f"(máximo {budget['max_videos']} videos)"
    )
    for line in totals_text(detail):
        st.text(line)
    st.text(
        "Propuesta de NicheRadar: "
        f"{PROPOSALS[detail['proposal']['action']]} — {detail['proposal']['reason']}"
    )
    for warning in detail["evaluation"]["warnings"]:
        st.warning(warning)
    st.markdown("**Reglas de parada**")
    st.dataframe(rule_rows(detail), hide_index=True, width="stretch")
    st.markdown("**Historial**")
    st.dataframe(event_rows(detail), hide_index=True, width="stretch")
    if detail["close_reason"]:
        st.text("Motivo de cierre: " + detail["close_reason"])
