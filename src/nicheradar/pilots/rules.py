# src/nicheradar/pilots/rules.py
"""Evalúa las reglas de parada de un piloto contra lo que reporta el canal.

Puro y determinista: sin base de datos ni reloj propio. Principio rector (workflow
pilot-lifecycle del Foundry de YouTube): con pocos casos NO se concluye. Una regla solo se da
por cumplida cuando ya lo está, y por incumplida cuando ya no puede alcanzarse; mientras tanto es
``sin_datos_suficientes``. NicheRadar
propone y el humano decide: aquí no se cierra nada.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

PENDING = "pendiente"
MET = "cumple"
FAILED = "no_cumple"
UNDECIDED = "sin_datos_suficientes"
NOT_EVALUABLE = "no_evaluable"
MANUAL = "revision_manual"
CONCLUDED = {MET, FAILED}
NEEDS_HUMAN = {MANUAL, NOT_EVALUABLE}
SHORTS_METRICS = {"engaged_view_ratio_pct", "avg_view_pct", "shorts_feed_share_pct"}
MIN_SHORTS_VIEWS = 100  # un Short con menos vistas se guarda, pero no cuenta para una regla
MEASURED_FIELDS = ("avd_pct", *sorted(SHORTS_METRICS))
MONTH_DAYS = 30  # un «mes» del hito son 30 días corridos

Video = dict[str, Any]
Rule = dict[str, Any]


def milestone_key(rule: Rule) -> str:
    milestone = rule["milestone"]
    return f"{milestone['kind']}:{milestone['value']}"


def _published(videos: Sequence[Video]) -> list[Video]:
    done = [video for video in videos if video.get("published_at") is not None]
    return sorted(done, key=lambda video: (video["published_at"], video["video_id"]))


def _due(rule: Rule, published: list[Video], now: datetime, authorized_at: datetime) -> bool:
    milestone = rule["milestone"]
    value = int(milestone["value"])
    if milestone["kind"] == "video":
        return len(published) >= value
    days = value * 7 if milestone["kind"] == "week" else value * MONTH_DAYS
    return now - authorized_at >= timedelta(days=days)


def _scope(rule: Rule, published: list[Video]) -> list[Video]:
    milestone = rule["milestone"]
    return published[: int(milestone["value"])] if milestone["kind"] == "video" else published


def _count_rule(rule: Rule, scope: list[Video], field: str) -> tuple[str, str]:
    """«Al menos min_cases videos con la métrica >= umbral» sobre el alcance del hito."""
    needed = int(rule["min_cases"] or 1)
    threshold = Decimal(str(rule["threshold"]))
    values = [video.get(field) for video in scope]
    meeting = sum(1 for value in values if value is not None and value >= threshold)
    unmeasured = sum(1 for value in values if value is None)
    if meeting >= needed:
        return MET, f"{meeting} de {len(scope)} videos llegan al umbral (se pedían {needed})"
    if meeting + unmeasured < needed:
        return (
            FAILED,
            f"solo {meeting} llegan y no alcanza con los {unmeasured} sin medir (piden {needed})",
        )
    return UNDECIDED, f"{meeting} llegan; faltan {unmeasured} por medir y se piden {needed}"


def _counted(scope: list[Video], field: str) -> list[Video]:
    """Shorts: la medición de un video con pocas vistas no cuenta (queda como sin medir)."""
    return [
        video if (video.get("views") or 0) >= MIN_SHORTS_VIEWS else {**video, field: None}
        for video in scope
    ]


def _latest_rule(rule: Rule, scope: list[Video], field: str) -> tuple[str, str]:
    """Usa el último valor medido del alcance: la tendencia no se evalúa automáticamente."""
    threshold = Decimal(str(rule["threshold"]))
    measured = [video[field] for video in scope if video.get(field) is not None]
    if not measured:
        return UNDECIDED, "todavía no hay ninguna medición de esta métrica"
    last = measured[-1]
    return (
        MET if last >= threshold else FAILED
    ), f"último valor medido {last} frente al umbral {threshold}"


def _evaluate_rule(
    rule: Rule, published: list[Video], now: datetime, authorized_at: datetime
) -> tuple[str, str]:
    if not _due(rule, published, now, authorized_at):
        return PENDING, "el hito todavía no llegó"
    metric = rule["metric"]
    if metric == "manual":
        return MANUAL, "la juzga el humano"
    if metric == "revenue_vs_cost":
        return NOT_EVALUABLE, "el canal no reporta ingresos: lo decide el humano"
    if metric == "pipeline_e2e":
        ok = bool(published)
        return (MET, "hay un video publicado") if ok else (FAILED, "no hay ningún video publicado")
    scope = _scope(rule, published)
    if metric in SHORTS_METRICS:
        counted = _counted(scope, metric)
        if metric == "shorts_feed_share_pct":
            return _latest_rule(rule, counted, metric)
        return _count_rule(rule, counted, metric)
    if metric == "avd_pct":
        return _count_rule(rule, scope, "avd_pct")
    if metric == "browse_share_pct":
        return _latest_rule(rule, scope, "browse_share_pct")
    return UNDECIDED, "métrica desconocida"


def _totals(videos: Sequence[Video], max_videos: int) -> tuple[dict[str, Any], list[str]]:
    by_stage: dict[str, int] = {}
    for video in videos:
        by_stage[video["stage"]] = by_stage.get(video["stage"], 0) + 1
    equivalent = [
        video["cost_equivalent_usd"]
        for video in videos
        if video.get("cost_equivalent_usd") is not None
    ]
    minutes = [
        video["machine_minutes"] for video in videos if video.get("machine_minutes") is not None
    ]
    published = sum(1 for video in videos if video.get("published_at") is not None)
    totals = {
        "videos": len(videos),
        "published": published,
        "measured": sum(
            1 for video in videos if any(video.get(field) is not None for field in MEASURED_FIELDS)
        ),
        "by_stage": by_stage,
        "spent_usd": sum((video["cost_usd"] for video in videos), Decimal(0)),
        "equivalent_usd": sum(equivalent, Decimal(0)),
        "machine_minutes": sum(minutes),
        "machine_minutes_complete": len(minutes) == len(videos),
    }
    warnings = []
    unknown = by_stage.get("unknown", 0)
    if unknown:
        warnings.append(f"{unknown} video(s) con un estado del canal sin traducir; revisión humana")
    if published > max_videos:
        warnings.append(
            f"se superó max_videos: {published} publicados de {max_videos}; revisar con el humano"
        )
    return totals, warnings


def evaluate(
    rules: Sequence[Rule],
    videos: Sequence[Video],
    *,
    now: datetime,
    authorized_at: datetime,
    max_videos: int,
    close_after: int,
) -> dict[str, Any]:
    published = _published(videos)
    results: list[dict[str, Any]] = []
    for rule in rules:
        status, detail = _evaluate_rule(rule, published, now, authorized_at)
        results.append(
            {
                "id": rule["id"],
                "text": rule["text"],
                "milestone": milestone_key(rule),
                "status": status,
                "detail": detail,
            }
        )
    milestones: dict[str, dict[str, Any]] = {}
    for item in results:
        slot = milestones.setdefault(
            item["milestone"], {"key": item["milestone"], "rules": [], "statuses": []}
        )
        slot["rules"].append(item["id"])
        slot["statuses"].append(item["status"])
    summary = []
    for slot in milestones.values():
        statuses = set(slot["statuses"])
        if statuses == {PENDING}:
            overall = PENDING
        elif FAILED in statuses:
            overall = FAILED
        elif UNDECIDED in statuses or PENDING in statuses:
            overall = UNDECIDED
        elif statuses & NEEDS_HUMAN:
            overall = MANUAL if MANUAL in statuses else NOT_EVALUABLE
        else:
            overall = MET
        summary.append({"key": slot["key"], "rules": slot["rules"], "status": overall})
    totals, warnings = _totals(videos, max_videos)
    return {
        "rules": results,
        "milestones": summary,
        "totals": totals,
        "warnings": warnings,
        "close_after": close_after,
    }


def proposal(evaluation: dict[str, Any], acknowledged: Sequence[str]) -> dict[str, Any]:
    """Propone seguir o cerrar con los números a la vista. No decide: lo confirma el humano."""
    milestones = evaluation["milestones"]
    close_after = int(evaluation["close_after"])
    trailing = 0
    for item in milestones:  # hitos vencidos y concluidos, en el orden de las reglas
        if item["status"] == FAILED:
            trailing += 1
        elif item["status"] == MET:
            trailing = 0
    fresh = [item for item in milestones if item["key"] not in set(acknowledged)]
    if trailing >= close_after:
        return {
            "action": "cerrar",
            "reason": f"{trailing} hitos fallidos seguidos (se cierra tras {close_after})",
        }
    failed = [item["key"] for item in fresh if item["status"] == FAILED]
    met = [item["key"] for item in fresh if item["status"] == MET]
    if failed:
        return {
            "action": "seguir",
            "reason": f"hito no cumplido ({', '.join(failed)}); cierre tras {close_after} seguidos",
        }
    if met:
        return {"action": "seguir", "reason": f"hito cumplido ({', '.join(met)})"}
    if any(item["status"] in NEEDS_HUMAN for item in fresh):
        return {"action": MANUAL, "reason": "hay reglas que solo puede juzgar el humano"}
    return {"action": UNDECIDED, "reason": "sin datos suficientes para proponer algo"}


def needs_decision(evaluation: dict[str, Any], acknowledged: Sequence[str]) -> bool:
    """¿Hay algo concluido o manual que el humano todavía no revisó?"""
    open_items = [m for m in evaluation["milestones"] if m["key"] not in set(acknowledged)]
    return any(m["status"] in CONCLUDED or m["status"] in NEEDS_HUMAN for m in open_items)
