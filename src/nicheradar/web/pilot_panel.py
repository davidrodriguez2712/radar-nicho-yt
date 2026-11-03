# src/nicheradar/web/pilot_panel.py
"""Pilot panel (M6) and channel preparation (M7): the view model behind /pilotos/{id}.

The payload is never trusted to the point of crashing a screen: every reader tolerates a wrong type
or a missing key, a derivation the data cannot support is omitted (the preparation deadline only
exists when the package carries ``preparation_days``) and every list is capped.
"""

from datetime import datetime, timedelta
from typing import Any

from nicheradar.web.format import es_int, short_date, zone
from nicheradar.web.pilots_view import (
    MAX_PREPARATION_DAYS,
    PILOT_RE,
    STATUS_CHIP,
    _ago,
    _check_label,
    _checks,
    _count,
    _dict,
    _moment,
    _num,
    _plural,
    _status,
    _str,
    blockers,
    dates,
    next_action,
)
from nicheradar.web.research import LANGUAGE_NAMES

TABS = ("resumen", "preparacion", "videos", "reglas", "historial")
TAB_LABELS = {
    "resumen": "Resumen",
    "preparacion": "Preparación",
    "videos": "Videos",
    "reglas": "Reglas",
    "historial": "Historial",
}
LIST_CAP = 100
DETAIL_CAP = 300
STATES_LINE = (
    "Autorizado",
    "Entregado",
    "Preparando",
    "En ejecución",
    "Decisión pendiente",
    "Cerrado",
)
# The API status that marks each step; "Entregado" is a milestone passed on the way to
# "Preparando" (status ``entregado``), so it is never the current step by itself.
CURRENT_STEP = {
    "autorizado": 0,
    "entregado": 2,
    "en_ejecucion": 3,
    "decision_pendiente": 4,
    "cerrado": 5,
}
FORMATS = {"long": "Largo", "shorts": "Shorts"}
OWNER = {
    "falta": "El canal",
    "vence": "El canal",
    "vigencia": "Tú, en tu Mac",
    "contacto": "Tú, en tu Mac",
    "desconocido": "Tú",
    "decision": "Tú",
}
PROPOSAL_TEXT = {
    "seguir": "Seguir",
    "cerrar": "Cerrar",
    "revision_manual": "Revisión manual",
    "sin_datos_suficientes": "Sin datos suficientes",
}
STAGE_TEXT = {
    "in_production": "En producción",
    "awaiting_human": "Espera tu veredicto",
    "uploaded": "Subido",
    "published": "Publicado",
    "measuring": "Midiendo",
    "killed": "Descartado",
    "blocked": "Bloqueado",
    "unknown": "Estado desconocido",
}
RULE_STATUS_TEXT = {
    "cumple": "Cumple",
    "no_cumple": "No cumple",
    "pendiente": "Pendiente",
    "sin_datos_suficientes": "Sin datos suficientes",
    "revision_manual": "Revisión manual",
    "no_evaluable": "No evaluable",
}
RULE_COUNT_TEXT = {
    "cumple": "cumple",
    "no_cumple": "no cumple",
    "pendiente": "pendiente",
    "sin_datos_suficientes": "sin datos",
    "revision_manual": "revisión manual",
    "no_evaluable": "no evaluable",
}
MILESTONE_UNIT = {"video": "video", "week": "semana", "month": "mes"}
EVENT_TEXT = {
    "authorized": "Autorizado",
    "delivered": "Entregado al canal",
    "first_report": "Primer reporte",
    "decision_pending": "Decisión pendiente",
    "decision_seguir": "Decidiste seguir",
    "decision_cerrar": "Decidiste cerrar",
    "cancelled": "Cancelado",
    "superseded": "Reemplazado",
    "gate_failure_accepted": "Aceptaste una compuerta no cumplida",
}
EVENT_DETAIL_KEYS = {"note": "Nota", "proposal": "Propuesta"}
NOTICES = {
    "autorizado": ("Piloto autorizado. Falta que tu Mac baje el paquete.", "green"),
    "seguido": ("Decidiste seguir: el piloto continúa.", "green"),
    "cerrado": ("Piloto cerrado.", "green"),
    "cancelado": ("Piloto cancelado.", "green"),
}
ACTION_REASONS = {
    "seguir": "Solo cuando hay una decisión pendiente.",
    "cerrar": "Solo mientras el piloto está en ejecución o con una decisión pendiente.",
    "cancelar": "Solo antes de que el piloto empiece a ejecutarse.",
    "cierre": "Solo cuando el piloto está cerrado.",
}
NO_BLOCKERS_NEXT = "Nada te espera por ahora"


def parse_tab(value: object) -> str:
    return value if isinstance(value, str) and value in TABS else "resumen"


def notice(key: object) -> tuple[str, str] | None:
    return NOTICES.get(key) if isinstance(key, str) else None


MAX_MONEY = 1e9


def _money(value: object) -> str:
    """One money format for the whole panel: US$ with a Spanish decimal comma.

    A whole amount has no decimals ("US$ 41"); under 100 it keeps two ("US$ 0,96"); from 100 up it
    rounds to a whole number. Negative, non-finite or absurdly large amounts read as unknown.
    """
    number = _num(value)
    if number is None or number < 0 or number > MAX_MONEY:
        return "—"
    if number >= 100 or number == int(number):
        return f"US$ {es_int(number)}"
    return "US$ " + f"{number:.2f}".replace(".", ",")


def _minutes(value: object) -> str:
    number = _num(value)
    if number is None or number < 0:
        return "—"
    total = int(number)
    return f"{total // 60} h {total % 60} min"


def _stamp(moment: datetime | None, timezone: str) -> str:
    if moment is None:
        return "—"
    return moment.astimezone(zone(timezone)).strftime("%d/%m/%Y %H:%M")


def _day(moment: datetime | None, timezone: str) -> str | None:
    return short_date(moment, timezone) if moment is not None else None


def _int(value: object, low: int, high: int) -> int | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    return value if ok and isinstance(value, int) else None


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _states(status: str) -> list[dict[str, str]]:
    current = CURRENT_STEP.get(status)
    rows = []
    for index, label in enumerate(STATES_LINE):
        if current is None or index > current:
            state = "todo"
        elif index == current:
            state = "current"
        else:
            state = "done"
        rows.append({"label": label, "state": state})
    return rows


def _rules_source(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluated rules; before the first evaluation, the package's own rules (status unknown)."""
    evaluated = [
        r for r in _list(_dict(detail.get("evaluation")).get("rules")) if isinstance(r, dict)
    ]
    if evaluated:
        return evaluated
    found = []
    for rule in _list(_dict(detail.get("package")).get("stop_rules")):
        item = _dict(rule)
        if not item:
            continue
        milestone = _dict(item.get("milestone"))
        key = f"{_str(milestone.get('kind'))}:{milestone.get('value')}" if milestone else ""
        found.append({"text": item.get("text"), "milestone": key, "status": None, "detail": None})
    return found


def _milestone_text(value: object) -> str:
    key = _str(value)
    kind, _, number = key.partition(":")
    if kind in MILESTONE_UNIT and number.isdigit():
        return f"{MILESTONE_UNIT[kind]} {number}"
    return key or "—"


def rule_rows(detail: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for rule in _rules_source(detail)[:LIST_CAP]:
        status = rule.get("status")
        text = RULE_STATUS_TEXT.get(status, status) if isinstance(status, str) else "Sin evaluar"
        rows.append(
            {
                "text": _str(rule.get("text")) or "Regla sin texto",
                "milestone": _milestone_text(rule.get("milestone")),
                "status": text,
                "detail": _str(rule.get("detail")),
            }
        )
    return rows


def _rules_summary(detail: dict[str, Any]) -> dict[str, Any]:
    source = _rules_source(detail)
    counts: dict[str, int] = {}
    for rule in source:
        status = rule.get("status")
        if isinstance(status, str) and status in RULE_COUNT_TEXT:
            counts[status] = counts.get(status, 0) + 1
    parts = [f"{n} {RULE_COUNT_TEXT[k]}" for k, n in counts.items()]
    close_after = _int(_dict(detail.get("evaluation")).get("close_after"), 1, 100)
    return {
        "total": _plural(len(source), "regla", "reglas"),
        "counts": " · ".join(parts),
        "close_after": close_after,
    }


def _event_detail(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts = []
    for key, item in value.items():
        if isinstance(item, str) and item:
            shown = item
        elif _num(item) is not None:
            shown = str(item)
        else:
            continue
        parts.append(f"{EVENT_DETAIL_KEYS.get(str(key), str(key))}: {shown}")
    return "; ".join(parts)[:DETAIL_CAP]


def event_rows(detail: dict[str, Any], timezone: str = "UTC") -> list[dict[str, str]]:
    """The newest events first; the API lists them oldest first."""
    events = [e for e in _list(detail.get("events")) if isinstance(e, dict)]
    rows = []
    for event in reversed(events[-LIST_CAP:]):
        kind = event.get("kind")
        label = EVENT_TEXT.get(kind) if isinstance(kind, str) else None
        rows.append(
            {
                "text": label or _str(kind) or "Evento",
                "actor": _str(event.get("actor")),
                "when": _stamp(_moment(event.get("at")), timezone),
                "detail": _event_detail(event.get("detail")),
            }
        )
    return rows


def video_rows(videos: list[Any] | None, timezone: str = "UTC") -> list[dict[str, str]]:
    rows = []
    for video in [v for v in _list(videos) if isinstance(v, dict)][:LIST_CAP]:
        stage = video.get("stage")
        rows.append(
            {
                "video_id": _str(video.get("video_id")) or "—",
                "stage": STAGE_TEXT.get(stage, stage)
                if isinstance(stage, str) and stage
                else "Estado desconocido",
                "visibility": _str(video.get("visibility")) or "—",
                "published": _day(_moment(video.get("published_at")), timezone) or "—",
                "cost": _money(video.get("cost_usd")),
                "minutes": _minutes(video.get("machine_minutes")),
            }
        )
    return rows


def prep_steps(detail: dict[str, Any], now: datetime, timezone: str = "UTC") -> dict[str, Any]:
    """The preparation steps are exactly what the channel reports in ``channel.checks``."""
    checks = _checks(detail)
    steps = [
        {
            "label": _check_label(c),
            "ok": c.get("ok") is True,
            "detail": _str(c.get("detail")),
            "expires": _day(_moment(c.get("expires_at")), timezone),
        }
        for c in checks[:LIST_CAP]
    ]
    missing = sum(1 for c in checks if c.get("ok") is not True)
    delivered = _moment(detail.get("delivered_at"))
    days = _int(_dict(detail.get("package")).get("preparation_days"), 1, MAX_PREPARATION_DAYS)
    deadline = (
        _day(delivered + timedelta(days=days), timezone)
        if delivered is not None and days is not None
        else None
    )
    count = ""
    if delivered is not None:
        elapsed = max(int((now - delivered).total_seconds() // 86400), 0)
        count = f"{_plural(elapsed, 'día', 'días')} desde la entrega."
    if checks:
        rest = f"Faltan {missing} de {len(checks)} pasos." if missing else "No falta ningún paso."
        count = f"{count} {rest}".strip()
    return {
        "steps": steps,
        "total": len(checks),
        "missing": missing,
        "shown_cap": LIST_CAP if len(checks) > LIST_CAP else None,
        "deadline": deadline,
        "delivered": delivered is not None,
        "count_text": count,
        "note": _str(_dict(detail.get("channel")).get("note")),
    }


def _costs(detail: dict[str, Any], now: datetime) -> dict[str, str]:
    totals = _dict(detail.get("totals"))
    high = _num(_dict(_dict(detail.get("package")).get("budget")).get("high"))
    spent = _money(totals.get("spent_usd")) + (f" de {_money(high)}" if high is not None else "")
    incomplete = totals.get("machine_minutes_complete") is False
    last = _moment(detail.get("last_report_at"))
    return {
        "spent": spent,
        "equivalent": _money(totals.get("equivalent_usd")),
        "minutes": _minutes(totals.get("machine_minutes"))
        + (" (incompleto)" if incomplete else ""),
        "last_report": f"hace {_ago(last, now)}" if last is not None else "todavía no hay",
    }


def _summary(
    detail: dict[str, Any], now: datetime, timezone: str, pid: str | None
) -> dict[str, Any]:
    status = _status(detail)
    package = _dict(detail.get("package"))
    cap = _int(_dict(package.get("budget")).get("max_videos"), 1, 50)
    totals = _dict(detail.get("totals"))
    published = _count(totals.get("published"))
    first = _moment(detail.get("first_report_at"))
    if first is not None:
        day = max(int((now - first).total_seconds() // 86400), 0) + 1
        progress = f"{published} de {cap} publicados" if cap else f"{published} publicados"
        state_text = f"Día {day} · {progress}"
    else:
        state_text = "Todavía sin reportes del canal"
    found = [{**b, "owner": OWNER.get(b["kind"], "Tú")} for b in blockers(detail, now, timezone)]
    proposal = _dict(detail.get("proposal"))
    action = proposal.get("action")
    allowed = {
        "seguir": status == "decision_pendiente",
        "cerrar": status in ("en_ejecucion", "decision_pendiente"),
        "cancelar": status in ("autorizado", "entregado"),
        "cierre": status == "cerrado",
    }
    labels = {
        "seguir": "Seguir",
        "cerrar": "Cerrar piloto",
        "cancelar": "Cancelar piloto",
        "cierre": "Cierre del piloto",
    }
    hrefs = {
        "seguir": f"/pilotos/{pid}/decidir?accion=seguir",
        "cerrar": f"/pilotos/{pid}/decidir?accion=cerrar",
        "cancelar": f"/pilotos/{pid}/cancelar",
        "cierre": f"/pilotos/{pid}/cierre",
    }
    actions = [
        {
            "key": key,
            "label": labels[key],
            "href": hrefs[key] if allowed[key] and pid else None,
            "reason": ACTION_REASONS[key],
            "kind": "danger" if key in ("cerrar", "cancelar") else "primary",
        }
        for key in ("seguir", "cerrar", "cancelar", "cierre")
    ]
    closed_at = _moment(detail.get("closed_at"))
    return {
        "state_text": state_text,
        "closed_text": _day(closed_at, timezone),
        "close_reason": _str(detail.get("close_reason")),
        "is_closed": status == "cerrado",
        "blockers": found,
        "next_action": next_action(detail) or NO_BLOCKERS_NEXT,
        "dates": dates(detail, now, timezone),
        "proposal_text": PROPOSAL_TEXT.get(action) if isinstance(action, str) else None,
        "proposal_reason": _str(proposal.get("reason")),
        "actions": actions,
        "rules": _rules_summary(detail),
        "costs": _costs(detail, now),
    }


def panel_view(
    detail: dict[str, Any],
    videos: list[dict[str, Any]] | None,
    now: datetime,
    timezone: str,
    tab: str,
) -> dict[str, Any]:
    tab = parse_tab(tab)
    status = _status(detail)
    chip_text, chip_kind = STATUS_CHIP.get(status, (status or "Estado desconocido", "neutral"))
    raw_id = detail.get("pilot_id")
    pid = raw_id if isinstance(raw_id, str) and PILOT_RE.fullmatch(raw_id) else None
    language = _str(detail.get("language"))
    view: dict[str, Any] = {
        "tab": tab,
        "pilot_id": pid,
        "is_closed": status == "cerrado",
        "title": _str(detail.get("niche_label")) or "—",
        "status_text": chip_text,
        "status_kind": chip_kind,
        "format_text": FORMATS.get(_str(detail.get("format")), "—"),
        "language_text": LANGUAGE_NAMES.get(language, language) if language else None,
        "channel_name": _str(detail.get("target_channel")) or None,
        "states": _states(status),
        "tabs": [
            {
                "key": key,
                "label": TAB_LABELS[key],
                "href": f"/pilotos/{pid}?pestana={key}" if pid else None,
                "current": key == tab,
            }
            for key in TABS
        ],
    }
    if tab == "resumen":
        view["summary"] = _summary(detail, now, timezone, pid)
    elif tab == "preparacion":
        view["prep"] = prep_steps(detail, now, timezone)
    elif tab == "videos":
        rows = video_rows(videos, timezone)
        view["videos"] = {
            "failed": videos is None,
            "rows": rows,
            "capped": videos is not None and len(videos) > LIST_CAP,
        }
    elif tab == "reglas":
        view["rules"] = {"rows": rule_rows(detail), "capped": len(_rules_source(detail)) > LIST_CAP}
    else:
        view["events"] = {
            "rows": event_rows(detail, timezone),
            "capped": len([e for e in _list(detail.get("events")) if isinstance(e, dict)])
            > LIST_CAP,
        }
    return view
