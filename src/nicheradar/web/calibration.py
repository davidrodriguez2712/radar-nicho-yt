# src/nicheradar/web/calibration.py
"""Calibration of a pilot (M13/M14): the owner's time per video against the exit criterion.

Computed at read time, in the web, from the dossier-v3 ``calibration`` block and the human minutes
of the pilot's videos. It is a suggestion shown as text ("pasa a régimen"): nothing is evaluated or
stored on the server. Every reader tolerates a wrong type; a number the data cannot support is
shown as not measured, never as zero.

Ruling 4: ``max_minutes_per_video`` is inclusive. A video meets the criterion when its human
minutes are at most that value. A measured zero is valid; only None or an invalid value (negative,
not finite, not an int) is "sin medir".
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

from nicheradar.flow_research.contracts import calibration_total_hours
from nicheradar.web.client import ApiClient, ApiError
from nicheradar.web.format import short_date
from nicheradar.web.pilots_view import _dict, _moment, _num, _str
from nicheradar.web.report import _calibration, _items, _minutes
from nicheradar.web.research import UUID_RE

ROW_CAP = 100
MAX_VIDEOS = 100  # the contract allows at most 12; this bounds a hostile payload
METHOD_CAP = 60
MAX_MEASURE = 100_000  # the contract's range for human_minutes; beyond it is not a measure
STATEMENT_CAP = 500
STEP_CAP = 15
# The setup hours are the dossier's plan: they only count as done once the pilot is running.
SETUP_DONE = ("en_ejecucion", "decision_pendiente", "cerrado")
# A figure from these methods is a floor (the human's reading/typing time plus a declared
# assumption, with most measured time unattributed): a streak built on it is only "possible".
LOWER_BOUND_METHODS: frozenset[str] = frozenset({"claude_sessions_plus_assumed"})
LOWER_BOUND_NOTE = "Las cifras son un mínimo estimado: confírmalo con tu propio criterio."
ROW_KIND = {"ok": "green", "over": "amber", "pending": "neutral", "unmeasured": "neutral"}


@dataclass(frozen=True)
class Calibration:
    videos_planned: int
    setup_hours: float
    max_minutes: int
    consecutive: int
    statement: str
    steps: list[tuple[str, int]]
    regime_minutes: int | None = None


def request_id(detail: object) -> str | None:
    """The flow-research order of a pilot whose package carries a dossier-v3, else None.

    The pilot detail always has it, so a screen can tell whether the pilot has a calibration
    without reading the dossier itself.
    """
    dossier = _dict(_dict(_dict(detail).get("package")).get("dossier"))
    rid = dossier.get("request_id")
    ok = dossier.get("schema") == "dossier-v3" and isinstance(rid, str)
    return rid if ok and isinstance(rid, str) and UUID_RE.fullmatch(rid) else None


def has_calibration_schema(detail: object) -> bool:
    dossier = _dict(_dict(_dict(detail).get("package")).get("dossier"))
    return dossier.get("schema") == "dossier-v3"


def load(api: ApiClient, pilot_id: str, rid: str | None) -> tuple[object | None, list[Any] | None]:
    """(dossier, videos) of a pilot; each is None when it cannot be read (the other still is)."""
    dossier: object | None = None
    videos: list[Any] | None = None
    if rid is not None:
        try:
            order = api.request("GET", f"/flow-research/{quote(rid, safe='')}")
            dossier = order.get("dossier") if isinstance(order, dict) else None
        except ApiError:
            dossier = None
    try:
        data = api.request("GET", f"/pilots/{quote(pilot_id, safe='')}/videos")
        items = data.get("items") if isinstance(data, dict) else None
        videos = items if isinstance(items, list) else None
    except ApiError:
        videos = None
    return dossier, videos


def _whole(value: object, low: int, high: int) -> int | None:
    number = _num(value)
    if number is None or number != int(number) or not low <= number <= high:
        return None
    return int(number)


def parse_calibration(dossier: object) -> Calibration | None:
    """The calibration of a dossier-v3, or None when it is older, lacks it or is malformed."""
    try:
        if not isinstance(dossier, dict) or _calibration(dossier) is None:
            return None
        block = _dict(dossier.get("calibration"))
        criterion = _dict(block.get("exit_criterion"))
        videos = _whole(block.get("videos"), 1, MAX_VIDEOS)
        setup = _num(block.get("setup_hours"))
        maximum = _whole(criterion.get("max_minutes_per_video"), 1, 10_000)
        consecutive = _whole(criterion.get("consecutive_videos"), 1, MAX_VIDEOS)
        statement = criterion.get("statement")
        raw_steps = block.get("minutes_by_step")
        steps: list[tuple[str, int]] = []
        for item in raw_steps[:STEP_CAP] if isinstance(raw_steps, list) else []:
            name = item.get("step") if isinstance(item, dict) else None
            minutes = _num(item.get("minutes_per_video")) if isinstance(item, dict) else None
            if not isinstance(name, str) or not name or minutes is None or minutes < 0:
                return None
            steps.append((name, round(minutes)))
        if (
            videos is None
            or setup is None
            or setup < 0
            or maximum is None
            or consecutive is None
            or not isinstance(statement, str)
            or not statement
            or not steps
        ):
            return None
        flow = _items(dossier.get("production_flow"))
        return Calibration(
            videos_planned=videos,
            setup_hours=setup,
            max_minutes=maximum,
            consecutive=consecutive,
            statement=statement[:STATEMENT_CAP],
            steps=steps,
            regime_minutes=_minutes(flow, "human_minutes_per_video") if flow else None,
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _measure(value: object) -> int | None:
    """Human minutes of one video: an int >= 0 (a measured zero is valid); else not measured."""
    ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_MEASURE
    return value if ok and isinstance(value, int) else None


def _row_text(value: int | None, lower_bound: bool = False) -> str:
    if value is None:
        return "sin medir"
    return f"≥ {value} min" if lower_bound else f"{value} min"


def streak(minutes: Sequence[object], max_minutes: int) -> int:
    """The final run of consecutive videos that meet the criterion (``<= max_minutes``).

    A video that was not measured (None, negative, not finite, not an int) breaks the run.
    """
    run = 0
    for value in reversed(minutes):
        measured = _measure(value)
        if measured is None or measured > max_minutes:
            break
        run += 1
    return run


def _hours(value: float) -> str:
    return f"{round(value, 1):g}".replace(".", ",")


def _methods(videos: list[dict[str, Any]]) -> list[str]:
    methods: list[str] = []
    for video in videos:
        if _measure(video.get("human_minutes")) is None:
            continue  # a not-measured row may still carry a method: it says nothing
        method = _str(video.get("human_minutes_method")).strip()[:METHOD_CAP]
        if method and method not in methods:
            methods.append(method)
    return methods


def _method_text(methods: list[str]) -> str | None:
    if not methods:
        return None
    if len(methods) > 1:
        return "métodos mezclados"
    prefix = "mínimo estimado" if methods[0] in LOWER_BOUND_METHODS else "estimado"
    return f"{prefix} (método {methods[0]})"


def view(
    calibration: Calibration,
    videos: list[Any] | None,
    now: datetime,
    tz: str = "UTC",
    status: str | None = None,
) -> dict[str, Any]:
    """The M13 model. ``now`` is only kept for symmetry with the other views."""
    del now
    # Only published videos count: drafts (published_at null) come last and are not calibration.
    items = [
        v
        for v in (videos or [])
        if isinstance(v, dict) and _moment(v.get("published_at")) is not None
    ]
    measures = [_measure(v.get("human_minutes")) for v in items]
    methods = _methods(items)
    lower_bound = any(m in LOWER_BOUND_METHODS for m in methods)
    limit = calibration.max_minutes
    count = max(calibration.videos_planned, len(items))
    rows: list[dict[str, str]] = []
    for index in range(min(count, ROW_CAP)):
        if index >= len(items):
            text, state = "pendiente", "pending"
        elif measures[index] is None:
            text, state = "sin medir", "unmeasured"
        else:
            value = measures[index]
            text = _row_text(value, lower_bound)
            state = "ok" if value is not None and value <= limit else "over"
        rows.append(
            {
                "label": f"Video {index + 1}",
                "text": text,
                "state": state,
                "kind": ROW_KIND[state],
            }
        )
    done = [m for m in measures if m is not None]
    run = streak(measures, limit)
    planned_hours = calibration_total_hours(
        calibration.setup_hours,
        calibration.videos_planned,
        sum(minutes for _, minutes in calibration.steps),
    )
    setup_done = status in SETUP_DONE
    hours_text = (
        f"Horas de calibración hasta hoy: "
        f"{_hours(calibration.setup_hours + sum(done) / 60)} h de {_hours(planned_hours)} previstas"
        + ("" if setup_done else " (incluye preparación prevista)")
        if done
        else None
    )
    last = None
    if items:
        position = len(items)
        parts = [f"Video {position}", _row_text(measures[-1], lower_bound)]
        published = _moment(items[-1].get("published_at"))
        if published is not None:
            parts.append(short_date(published, tz))
        last = " · ".join(parts)
    incomplete = any(m is None for m in measures)
    over = any(m is not None and m > limit for m in measures)
    passes = run >= calibration.consecutive
    regime = calibration.regime_minutes
    return {
        "rows": rows,
        "capped": count > ROW_CAP,
        "streak": run,
        "streak_text": f"Racha de hasta {limit} minutos: {run} de {calibration.consecutive}"
        + (" (posible: las cifras son un mínimo)" if lower_bound else ""),
        "passes": passes,
        "lower_bound": lower_bound,
        "lower_bound_note": LOWER_BOUND_NOTE,
        "measured": bool(done),
        "incomplete": incomplete,
        "hours_text": hours_text,
        "hours_incomplete": bool(done) and incomplete,
        "setup_label": "Preparación del canal (hecha)"
        if setup_done
        else "Preparación del canal (prevista)",
        "setup_text": f"{_hours(calibration.setup_hours)} h"
        if calibration.setup_hours > 0
        else None,
        "regime_text": f"Régimen que buscamos: {regime} min por video" if regime else None,
        "last_video": last,
        "method_text": _method_text(methods),
        "statement": calibration.statement,
        "steps": list(calibration.steps),
        "warning": (
            (f"Algún video pasó de {limit} minutos", "Es normal en calibración")
            if over and not passes
            else None
        ),
    }
