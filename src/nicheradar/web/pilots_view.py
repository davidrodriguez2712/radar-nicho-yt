# src/nicheradar/web/pilots_view.py
"""Pilot list (M5): blockers, next action, progress and tentative dates derived from the API.

Every helper tolerates malformed input (wrong types, missing keys, garbage dates, NaN): the API
payload is not trusted to the point of crashing a screen, and a derivation it cannot make is
simply omitted rather than invented.
"""

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from nicheradar.web.format import short_date

STATUS_CHIP: dict[str, tuple[str, str]] = {
    "autorizado": ("Autorizado", "neutral"),
    "entregado": ("Preparando", "amber"),
    "en_ejecucion": ("En ejecución", "green"),
    "decision_pendiente": ("Decisión pendiente", "rose"),
    "cerrado": ("Cerrado", "neutral"),
    "cancelado": ("Cancelado", "neutral"),
}
CLOSED = frozenset({"cerrado", "cancelado"})
PILOT_RE = re.compile(r"^pil_[0-9]{8}_[a-z0-9-]{1,40}$")  # pilots/contracts.py PILOT_ID
FILTERS = ("todos", "activos", "bloqueo", "cerrados")
EXPIRY_WINDOW = timedelta(days=7)
VALIDITY_WINDOW = timedelta(days=3)
STALE_CONTACT = timedelta(hours=48)
NO_CONTACT = "Tu Mac: sin contacto todavía"
FORMATS = {"long": "Largo", "shorts": "Shorts"}
MIN_YEAR, MAX_YEAR = 1970, 2200
MAX_PREPARATION_DAYS = 3650
MAX_MILESTONE = 1200


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _num(value: object) -> float | None:
    """A finite real number; booleans, strings, NaN and infinity are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _count(value: object) -> int:
    number = _num(value)
    return int(number) if number is not None and number > 0 else 0


def _moment(value: object) -> datetime | None:
    """An ISO string as an aware datetime (no zone means UTC); anything else is None."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        moment.astimezone(UTC)  # raises OverflowError at the edge of the calendar
    except (ValueError, OverflowError):
        return None
    return moment if MIN_YEAR <= moment.year <= MAX_YEAR else None


def _status(item: dict[str, Any]) -> str:
    return _str(item.get("status"))


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _checks(item: dict[str, Any]) -> list[dict[str, Any]]:
    checks = _dict(item.get("channel")).get("checks")
    return [c for c in checks if isinstance(c, dict)] if isinstance(checks, list) else []


def _check_label(check: dict[str, Any]) -> str:
    return _str(check.get("label")) or _str(check.get("id")) or "Requisito del canal"


def _by_stage(item: dict[str, Any], stage: str) -> int:
    return _count(_dict(_dict(item.get("totals")).get("by_stage")).get(stage))


def blockers(item: dict[str, Any], now: datetime, timezone: str = "UTC") -> list[dict[str, str]]:
    """What holds an open pilot back, in a fixed order; a closed pilot has none."""
    status = _status(item)
    if status in CLOSED:
        return []
    found: list[dict[str, str]] = []
    checks = _checks(item)
    for check in checks:
        if check.get("ok") is False:
            detail = _str(check.get("detail"))
            text = f"Falta: {_check_label(check)}" + (f". {detail}" if detail else "")
            found.append({"text": text, "kind": "falta"})
    for check in checks:
        expires = _moment(check.get("expires_at"))
        if expires is None:
            continue
        label, day = _check_label(check), short_date(expires, timezone)
        if expires < now:
            found.append({"text": f"{label} venció el {day}", "kind": "vence"})
        elif expires - now <= EXPIRY_WINDOW:
            found.append({"text": f"{label} vence el {day}", "kind": "vence"})
    valid_until = _moment(item.get("valid_until"))
    if (
        status == "autorizado"
        and _moment(item.get("delivered_at")) is None
        and valid_until is not None
        and valid_until - now <= VALIDITY_WINDOW
    ):
        day = short_date(valid_until, timezone)
        text = (
            f"La vigencia venció el {day} y tu Mac no bajó el paquete"
            if valid_until < now
            else f"La vigencia vence el {day} si tu Mac no baja el paquete"
        )
        found.append({"text": text, "kind": "vigencia"})
    contact = _moment(item.get("channel_last_contact_at"))
    if status in ("entregado", "en_ejecucion") and contact is not None:
        silent = now - contact
        if silent > STALE_CONTACT:
            hours = int(silent.total_seconds() // 3600)
            found.append({"text": f"Tu Mac está sin contacto hace {hours} h", "kind": "contacto"})
    unknown = _by_stage(item, "unknown")
    if unknown:
        text = _plural(unknown, "video", "videos") + " con estado desconocido"
        found.append({"text": text, "kind": "desconocido"})
    if item.get("needs_decision") is True:
        found.append({"text": "Hay una decisión pendiente", "kind": "decision"})
    return found


def next_action(item: dict[str, Any]) -> str | None:
    """Only what the data can assert; None when nothing is known to be waiting."""
    status = _status(item)
    if status in CLOSED:
        return None
    if item.get("needs_decision") is True:
        return "Decide si sigue o cierra"
    waiting = _by_stage(item, "awaiting_human")
    if waiting:
        noun = "video espera" if waiting == 1 else "videos esperan"
        return f"{waiting} {noun} tu veredicto en el canal"
    if status == "autorizado" and _moment(item.get("delivered_at")) is None:
        return "Falta que tu Mac baje el paquete"
    return None


def progress_text(item: dict[str, Any], max_videos: int | None = None) -> str:
    published = _count(_dict(item.get("totals")).get("published"))
    cap = max_videos if isinstance(max_videos, int) and not isinstance(max_videos, bool) else None
    if cap is not None and cap > 0:
        return f"{published} de {cap} videos"
    return _plural(published, "video", "videos")


def _add_months(moment: datetime, months: int) -> datetime:
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(
        moment.day,
        [
            31,
            29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return moment.replace(year=year, month=month, day=day)


def _row(label: str, moment: datetime | None, timezone: str, note: str | None) -> dict[str, Any]:
    value = short_date(moment, timezone) if moment is not None else None
    return {"label": label, "value": value, "note": note}


def _milestones(package: dict[str, Any]) -> list[tuple[str, int]]:
    rules = package.get("stop_rules")
    found: set[tuple[str, int]] = set()
    for rule in rules if isinstance(rules, list) else []:
        milestone = _dict(_dict(rule).get("milestone"))
        kind, value = milestone.get("kind"), milestone.get("value")
        if (
            kind in ("week", "month", "video")
            and isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= MAX_MILESTONE
        ):
            found.add((str(kind), value))
    order = {"week": 0, "month": 1, "video": 2}
    return sorted(found, key=lambda m: (order[m[0]], m[1]))


def dates(detail: dict[str, Any], now: datetime, timezone: str = "UTC") -> list[dict[str, Any]]:
    """Tentative dates with a real basis; each row is {label, value, note} and value may be None."""
    rows: list[dict[str, Any]] = []
    authorized = _moment(detail.get("authorized_at"))
    delivered = _moment(detail.get("delivered_at"))
    valid_until = _moment(detail.get("valid_until"))
    package = _dict(detail.get("package"))
    if authorized is not None:
        rows.append(_row("Autorizado", authorized, timezone, None))
    if delivered is not None:
        rows.append(_row("Entregado", delivered, timezone, None))
        days = package.get("preparation_days")
        if (
            isinstance(days, int)
            and not isinstance(days, bool)
            and 1 <= days <= MAX_PREPARATION_DAYS
        ):
            due = delivered + timedelta(days=days)
            note = "dentro del plazo" if now <= due else "vencido"
            rows.append(_row("Plazo de preparación (tentativa)", due, timezone, note))
    if valid_until is not None:
        note = "el paquete ya se entregó" if delivered is not None else "vence si no se entrega"
        rows.append(_row("Vigencia (tentativa)", valid_until, timezone, note))
    for kind, value in _milestones(package):
        if kind == "video":
            rows.append(_row("Revisión (tentativa)", None, timezone, f"al llegar al video {value}"))
        elif authorized is not None:
            due = (
                authorized + timedelta(weeks=value)
                if kind == "week"
                else _add_months(authorized, value)
            )
            rows.append(_row("Revisión (tentativa)", due, timezone, f"{kind_es(kind)} {value}"))
    return rows


def kind_es(kind: str) -> str:
    return {"week": "semana", "month": "mes"}[kind]


def parse_filter(params: Any) -> str:
    value = params.get("filtro", "todos")
    return value if isinstance(value, str) and value in FILTERS else "todos"


def _ago(moment: datetime, now: datetime) -> str:
    seconds = (now - moment).total_seconds()
    if seconds < 60:
        return "menos de 1 min"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86400 * 2:
        return f"{int(seconds // 3600)} h"
    days = int(seconds // 86400)
    return _plural(days, "día", "días")


def _card(item: dict[str, Any], now: datetime, timezone: str) -> dict[str, Any]:
    status = _status(item)
    text, kind = STATUS_CHIP.get(status, (status or "Estado desconocido", "neutral"))
    pilot_id = item.get("pilot_id")
    valid_id = pilot_id if isinstance(pilot_id, str) and PILOT_RE.fullmatch(pilot_id) else None
    channel = _str(item.get("target_channel"))
    return {
        "pilot_id": valid_id,
        "href": f"/pilotos/{valid_id}" if valid_id else None,
        "niche_label": _str(item.get("niche_label")) or "—",
        "status_text": text,
        "status_kind": kind,
        "format_text": FORMATS.get(_str(item.get("format")), "—"),
        "channel_text": channel or "canal por definir",
        "blockers": blockers(item, now, timezone),
        "next_action": next_action(item),
        "progress": progress_text(item),  # the list carries no package, hence no cap
        "budget_cap": None,
    }


def list_view(items: list[Any], filter_key: str, now: datetime, timezone: str) -> dict[str, Any]:
    pilots = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
    key = filter_key if filter_key in FILTERS else "todos"
    cards = [_card(p, now, timezone) for p in pilots]
    open_cards = [c for p, c in zip(pilots, cards, strict=True) if _status(p) not in CLOSED]
    counts = {
        "todos": len(cards),
        "activos": len(open_cards),
        "bloqueo": sum(1 for c in open_cards if c["blockers"]),
        "cerrados": len(cards) - len(open_cards),
    }
    shown = {
        "todos": cards,
        "activos": open_cards,
        "bloqueo": [c for c in open_cards if c["blockers"]],
        "cerrados": [c for p, c in zip(pilots, cards, strict=True) if _status(p) in CLOSED],
    }[key]
    contacts = [
        m
        for p in pilots
        if _status(p) not in CLOSED and (m := _moment(p.get("channel_last_contact_at"))) is not None
    ]
    contact_text = (
        f"Tu Mac: último contacto hace {_ago(max(contacts), now)}" if contacts else NO_CONTACT
    )
    return {
        "cards": shown,
        "counts": counts,
        "filter": key,
        "contact_text": contact_text,
    }
