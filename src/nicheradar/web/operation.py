# src/nicheradar/web/operation.py
"""View models for the Operación screen: scraper, its recent runs and the sub-niche summary.

Every function tolerates garbage: a wrong type degrades its own card to `{"ok": False}`.
"""

import math
from datetime import datetime
from typing import Any

from nicheradar.web.format import ago, local_datetime, parse_utc

STATUS_LABEL = {
    "queued": "en cola",
    "running": "en curso",
    "succeeded": "correcta",
    "partial": "parcial",
    "failed": "falló",
    "blocked": "bloqueada",
}
STATUS_TONE = {
    "queued": "blue",
    "running": "blue",
    "succeeded": "green",
    "partial": "amber",
    "failed": "rose",
    "blocked": "gray",
}
UNKNOWN_LABEL = "desconocido"
UNKNOWN_TONE = "gray"
STAGE_LABEL = {
    "list": "listados",
    "detail": "detalle",
    "reconcile": "reconciliación",
    "classify": "clasificación",
    "verify": "verificación",
    "enrich": "enriquecimiento",
    "evidence": "evidencia",
    "snapshot": "captura",
}
MODE_LABEL = {"live": "Real", "synthetic": "De ejemplo"}
DASH = "—"
ERROR_CODE_MAX = 60
MAX_RUN_SECONDS = 24 * 3600  # a longer span is a bad clock, not a duration worth showing
LAST_RUN_WARNING = {
    "partial": "La última ejecución del scraper salió parcial.",
    "failed": "La última ejecución del scraper falló.",
    "blocked": "La última ejecución del scraper quedó bloqueada.",
}
PAUSED_WARNING = (
    "El scraper de mercado está pausado: no trae anuncios nuevos hasta que lo reanudes."
)
LIVE_WARNING = (
    "En modo real, el scraper no se activa hasta habilitar el scraper en vivo en el servidor."
)
# The only notices the screen can show: the query string picks a key, never the text.
AVISOS: dict[str, tuple[str, str]] = {
    "reanudado": ("Scraper reanudado.", "green"),
    "pausado": ("Scraper pausado.", "green"),
    "sin-cambio": ("El scraper ya estaba en ese estado.", "amber"),
    "error": ("No se pudo aplicar el cambio.", "rose"),
}
UNAVAILABLE: dict[str, Any] = {"ok": False}


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _moment(value: object, tz: str) -> str:
    if not isinstance(value, str):
        return DASH
    try:
        return local_datetime(value, tz)
    except (ValueError, OverflowError):
        return DASH


def _minutes(run: dict[str, Any]) -> int | None:
    started, finished = run.get("started_at"), run.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        seconds = (parse_utc(finished) - parse_utc(started)).total_seconds()
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_RUN_SECONDS:
        return None
    return math.ceil(seconds / 60)


def _run_row(run: dict[str, Any], tz: str) -> dict[str, str]:
    status = run.get("status")
    known = isinstance(status, str) and status in STATUS_LABEL
    stage = run.get("stage")
    stage_text = STAGE_LABEL.get(stage, DASH) if isinstance(stage, str) else DASH
    detail = f"etapa: {stage_text}"
    minutes = _minutes(run)
    if minutes is not None:
        detail += f" · {minutes} min"
    code = run.get("error_code")
    if isinstance(code, str) and code:
        detail += f" · error: {code[:ERROR_CODE_MAX]}"
    return {
        "when": _moment(run.get("started_at") or run.get("created_at"), tz),
        "detail": detail,
        "status_label": STATUS_LABEL[status] if known else UNKNOWN_LABEL,  # type: ignore[index]
        "tone": STATUS_TONE[status] if known else UNKNOWN_TONE,  # type: ignore[index]
    }


def runs_card(runs: object, now: datetime, tz: str, limit: int) -> dict[str, Any]:
    if not isinstance(runs, list):
        return dict(UNAVAILABLE)
    rows = [_run_row(run, tz) for run in runs if isinstance(run, dict)]
    return {"ok": True, "rows": rows, "empty": not rows, "truncated": len(runs) >= limit}


def _frequency(seconds: object) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        return DASH
    if seconds % 3600 == 0:
        return f"Cada {seconds // 3600} h"
    if seconds % 60 == 0:
        return f"Cada {seconds // 60} min"
    return DASH


def _last_status(runs: object) -> object:
    if isinstance(runs, list):
        for run in runs:
            if isinstance(run, dict):
                return run.get("status")
    return None


def scraper_card(schedule: object, runs: object, now: datetime, tz: str) -> dict[str, Any]:
    if not isinstance(schedule, dict):
        return dict(UNAVAILABLE)
    paused = schedule.get("paused")
    if not isinstance(paused, bool):
        return dict(UNAVAILABLE)
    mode = schedule.get("mode")
    warnings: list[str] = []
    if paused:
        warnings.append(PAUSED_WARNING)
    last = _last_status(runs)
    if isinstance(last, str) and last in LAST_RUN_WARNING:
        warnings.append(LAST_RUN_WARNING[last])
    if mode == "live" and schedule.get("live_enabled") is not True:
        warnings.append(LIVE_WARNING)
    return {
        "ok": True,
        "paused": paused,
        "state_text": "Pausado" if paused else "Activo",
        "mode_text": MODE_LABEL.get(mode, DASH) if isinstance(mode, str) else DASH,
        "frequency_text": _frequency(schedule.get("interval_seconds")),
        "next_text": "—  (pausado)" if paused else _moment(schedule.get("next_due_at"), tz),
        "action": "reanudar" if paused else "pausar",
        "warnings": warnings,
    }


def subniches_card(items: object, now: datetime) -> dict[str, Any]:
    if not isinstance(items, list):
        return dict(UNAVAILABLE)
    counts = {"active": 0, "proposed": 0, "paused": 0}
    unmeasured = 0
    latest: tuple[datetime, str] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if isinstance(status, str) and status in counts:
            counts[status] += 1
        measurement = item.get("measurement")
        if isinstance(measurement, dict):
            at = measurement.get("measured_at")
            if isinstance(at, str):
                try:
                    moment = parse_utc(at)
                except (ValueError, OverflowError):
                    continue
                if moment > now:  # a future date is a bad clock: it never wins as the latest
                    continue
                if latest is None or moment > latest[0]:
                    latest = (moment, at)
        elif status == "active":
            unmeasured += 1
    return {
        "ok": True,
        "active": counts["active"],
        "proposed": counts["proposed"],
        "paused": counts["paused"],
        "unmeasured": unmeasured,
        "last_measured_text": ago(latest[1], now) if latest else "sin mediciones",
    }


def warnings(schedule_card: dict[str, object], runs_card: dict[str, object]) -> list[str]:
    """The top notices: only the scraper card produces them; a failed source adds none."""
    found = schedule_card.get("warnings")
    return list(found) if isinstance(found, list) else []


RUNS_LIMIT = 20


def operation_view(sources: dict[str, object], now: datetime, tz: str) -> dict[str, Any]:
    """`sources`: raw `schedule`, `runs` and `subniches` payloads (None when a read failed)."""
    scraper = scraper_card(sources.get("schedule"), sources.get("runs"), now, tz)
    runs = runs_card(sources.get("runs"), now, tz, RUNS_LIMIT)
    return {
        "scraper": scraper,
        "runs": runs,
        "subniches": subniches_card(sources.get("subniches"), now),
        "warnings": warnings(scraper, runs),
    }


LIVE_BLOCK = (
    "En modo real, el scraper en vivo debe estar habilitado en el servidor. "
    "Mientras no lo esté, no se puede reanudar."
)
# The only actions the confirmation accepts; the route's id picks one, the form never does.
ACTIONS: dict[str, dict[str, Any]] = {
    "reanudar": {
        "title": "Reanudar el scraper",
        "consequence": (
            "El scraper de mercado volverá a recorrer los anuncios en su próxima hora programada."
        ),
        "button": "Confirmar y reanudar",
        "kind": "primary",
        "paused": False,
    },
    "pausar": {
        "title": "Pausar el scraper",
        "consequence": (
            "El scraper de mercado dejará de traer anuncios nuevos hasta que lo reanudes. "
            "No borra nada."
        ),
        "button": "Confirmar y pausar",
        "kind": "danger",
        "paused": True,
    },
}
NEXT_ON_RESUME = "En cuanto el servidor lo recoja"


def confirm_view(action: str, schedule: object, now: datetime, tz: str) -> dict[str, Any]:
    """The confirmation for `action` over the schedule just read (a non-object raises TypeError)."""
    spec = ACTIONS[action]
    if not isinstance(schedule, dict):
        raise TypeError("schedule is not an object")
    if not isinstance(schedule.get("paused"), bool):
        raise TypeError("schedule.paused is not a boolean")
    mode = schedule.get("mode")
    rows = [("Frecuencia", _frequency(schedule.get("interval_seconds")))]
    if action == "reanudar":
        rows.append(("Próxima ejecución", NEXT_ON_RESUME))
    rows.append(("Modo", MODE_LABEL.get(mode, DASH) if isinstance(mode, str) else DASH))
    blocked = (
        LIVE_BLOCK
        if action == "reanudar" and mode == "live" and schedule.get("live_enabled") is not True
        else None
    )
    return {
        "title": spec["title"],
        "consequence": spec["consequence"],
        "button": spec["button"],
        "kind": spec["kind"],
        "rows": rows,
        "blocked": blocked,
        "already": schedule["paused"] is spec["paused"],
    }
