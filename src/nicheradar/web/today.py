# src/nicheradar/web/today.py
"""View models for Hoy (M1/M14): four independent cards, each of which may be unavailable."""

import math
from datetime import datetime
from typing import Any

from nicheradar.web import calibration, niches, subniches
from nicheradar.web.deps import SHAPE_ERRORS
from nicheradar.web.pilots_view import CLOSED as PILOT_CLOSED
from nicheradar.web.pilots_view import PILOT_RE, blockers, next_action
from nicheradar.web.research import UUID_RE

PAGE = 100  # size of the flow-research and pilots reads: exactly this many may hide older rows
SHOWN = 2  # niche and subniche cards
REPORTS_SHOWN = 3  # ready reports listed inside the pending section
OLDER = "Puede haber registros más antiguos que no se ven."
CALIBRATION_PILOTS = 5  # each one costs three reads: the card looks at a few and says so
CALIBRATING = ("entregado", "en_ejecucion", "decision_pendiente")
CLOSED = ("cerrado", "cancelado")
FAILED = SHAPE_ERRORS


def attention_cards(
    pilots: list[dict[str, Any]], now: datetime, timezone: str = "UTC"
) -> list[dict[str, Any]]:
    """Open pilots needing something: next action or first blocker, linked to their panel."""
    cards = []
    for pilot in pilots:
        if not isinstance(pilot, dict):
            continue
        status = pilot.get("status")
        if isinstance(status, str) and status in PILOT_CLOSED:
            continue
        action = next_action(pilot)
        found = blockers(pilot, now, timezone)
        if pilot.get("needs_decision") is not True and not action and not found:
            continue
        pilot_id = pilot.get("pilot_id")
        valid = isinstance(pilot_id, str) and PILOT_RE.fullmatch(pilot_id) is not None
        label, channel = pilot.get("niche_label"), pilot.get("target_channel")
        if pilot.get("needs_decision") is True:
            chip = "decisión pendiente"
        elif found and found[0]["kind"] == "falta":
            chip = "antes de producir"
        else:
            chip = "requiere atención"
        cards.append(
            {
                "label": label if isinstance(label, str) and label else "—",
                "channel": channel if isinstance(channel, str) and channel else "Canal nuevo",
                "text": action or (found[0]["text"] if found else "Hay una decisión pendiente"),
                "chip": chip,
                "href": f"/pilotos/{pilot_id}" if valid else None,
            }
        )
    return cards


def calibration_candidates(pilots: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """Active pilots with a valid id (at most five), and how many more were left unchecked."""
    found = [
        p
        for p in pilots
        if isinstance(p, dict)
        and p.get("status") in CALIBRATING
        and isinstance(p.get("pilot_id"), str)
        and PILOT_RE.fullmatch(p["pilot_id"])
    ]
    return found[:CALIBRATION_PILOTS], max(len(found) - CALIBRATION_PILOTS, 0)


def _progress_line(shown: dict[str, Any]) -> str:
    """«Video N de M · último video X min»: the last row is the last published video."""
    published, rows = shown["published"], shown["rows"]
    if published < 1:
        return "Todavía sin videos publicados"
    line = f"Video {published} de {max(shown['planned'], published)}"
    if published > len(rows):
        return line
    last = rows[published - 1]
    if last["state"] == "unmeasured":
        return f"{line} · último video sin medir"
    return f"{line} · último video {last['text']}"


def _bar_class(shown: dict[str, Any]) -> str:
    total = max(shown["planned"], shown["published"], 1)
    return f"bar--p{min(shown['published'] * 100 // total, 100) // 5 * 5}"


def calibration_card(
    entries: list[dict[str, Any]], more: int, now: datetime, timezone: str = "UTC"
) -> dict[str, Any]:
    """Pilots in calibration with their streak and last video.

    Each entry is {"pilot", "dossier", "videos"} (dossier/videos None when they could not be
    read, "skipped" when the pilot has no dossier-v3). A pilot whose dossier has no readable
    calibration is simply not listed; one that could not be read is counted, and when none could
    be read at all the card says it is unavailable.
    """
    cards: list[dict[str, Any]] = []
    failed = 0
    for entry in entries:
        if entry.get("skipped"):
            continue
        dossier, videos = entry.get("dossier"), entry.get("videos")
        if dossier is None or videos is None:
            failed += 1
            continue
        parsed = calibration.parse_calibration(dossier)
        if parsed is None:
            continue
        pilot = entry["pilot"]
        shown = calibration.view(parsed, videos, now, timezone)
        label, channel = pilot.get("niche_label"), pilot.get("target_channel")
        cards.append(
            {
                "label": label if isinstance(label, str) and label else "—",
                "channel": channel if isinstance(channel, str) and channel else "Canal nuevo",
                "href": f"/pilotos/{pilot['pilot_id']}",
                "progress_line": _progress_line(shown),
                "bar": _bar_class(shown),
                "streak_text": shown["streak_text"],
                "last_video": shown["last_video"],
                "passes": shown["passes"],
                "lower_bound": shown["lower_bound"],
                "lower_bound_note": shown["lower_bound_note"],
                "measured": shown["measured"],
            }
        )
    if not cards and not failed:
        return {"show": False, "ok": True}
    if not cards:
        return {"show": True, "ok": False}
    return {
        "show": True,
        "ok": True,
        "cards": cards,
        "count": len(cards),
        "failed": failed,
        "more": more,
    }


def open_pilot_keys(pilots: list[Any]) -> tuple[set[tuple[str, str]], bool]:
    """(label, format) of every open pilot, and whether some pilot could not be read.

    Only dict pilots with a str status, label and format take part; the rest are skipped and
    reported so the card can say the crossing is incomplete instead of hiding the reports.
    """
    keys: set[tuple[str, str]] = set()
    malformed = False
    for pilot in pilots:
        label = pilot.get("niche_label") if isinstance(pilot, dict) else None
        fmt = pilot.get("format") if isinstance(pilot, dict) else None
        status = pilot.get("status") if isinstance(pilot, dict) else None
        if not (isinstance(label, str) and isinstance(fmt, str) and isinstance(status, str)):
            malformed = True
        elif status not in CLOSED:
            keys.add((label, fmt))
    return keys, malformed


def ready_reports(
    flows: list[dict[str, Any]], pilots: list[dict[str, Any]], limit: int | None = REPORTS_SHOWN
) -> list[dict[str, Any]]:
    """Ready reports whose niche and format have no open pilot yet (at most `limit`)."""
    busy, _ = open_pilot_keys(pilots)
    cards: list[dict[str, Any]] = []
    for flow in flows:
        report_id = flow.get("id")
        if (
            flow.get("status") != "listo"
            or not isinstance(report_id, str)
            or not UUID_RE.fullmatch(report_id)  # `$` would also accept a trailing newline
            or (flow.get("niche_label"), flow.get("format")) in busy
        ):
            continue
        cards.append(
            {
                "label": str(flow.get("niche_label") or "—"),
                "format_text": "Shorts" if flow.get("format") == "shorts" else "Largo",
                "text": "Informe de investigación listo: decide si lanzas el piloto",
                "chip": "listo para decidir",
                "href": f"/informes/{report_id}",
            }
        )
        if limit is not None and len(cards) == limit:
            break
    return cards


def _has_score(item: dict[str, Any]) -> bool:
    value = (item.get("opportunity") or {}).get("value")
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def top_niches(
    items: list[dict[str, Any]], research_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    index = niches.research_index(research_items)
    scored = [item for item in items if _has_score(item)][:SHOWN]
    cards = [
        niches.card(item, index.get((item["niche_label"], item["format"])), rank)
        for rank, item in enumerate(scored, 1)
    ]
    for card in cards:
        (_, opportunity), (_, automation), (_, confidence) = card["scores"]
        card["score_line"] = (
            f"Opportunity {opportunity} · Automatización {automation} · "
            f"Confianza {str(confidence).lower()}"
        )
    return cards


def top_subniches(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finalists = [item for item in items if item.get("finalist")]
    finalists.sort(key=lambda item: item.get("measurement") is None)  # stable: measured first
    return [subniches.card(item, rank) for rank, item in enumerate(finalists[:SHOWN], 1)]


def _card(build: Any, *sources: list[dict[str, Any]] | None) -> dict[str, Any]:
    """One card: unavailable when a source failed or an unexpected shape breaks its model."""
    if any(source is None for source in sources):
        return {"ok": False}
    try:
        return {"ok": True, **build()}
    except FAILED:
        return {"ok": False}


def today_view(
    sources: dict[str, list[dict[str, Any]] | None],
    now: datetime,
    timezone: str = "UTC",
    calibration_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`sources` maps status/niches/flows/pilots/subniches to its items, or None if it failed.

    `calibration_source` is {"entries": [...], "more": n} (see `calibration_card`), or None.
    """
    flows, pilots = sources.get("flows"), sources.get("pilots")
    flows_full = flows is not None and len(flows) >= PAGE
    pilots_full = pilots is not None and len(pilots) >= PAGE

    def pilot_card() -> dict[str, Any]:
        return {"cards": attention_cards(pilots or [], now, timezone)}

    def report_card() -> dict[str, Any]:
        return {
            "cards": ready_reports(flows or [], pilots or [], None),
            "unchecked": pilots is None,  # without the pilots we cannot tell which have one
            "partial": bool(pilots) and open_pilot_keys(pilots or [])[1],
        }

    def pending_view() -> dict[str, Any]:
        """One section: pilots needing something plus the ready reports, each source on its own."""
        mine, theirs = _card(pilot_card, pilots), _card(report_card, flows)
        errors = [
            f"{name}: no disponible ahora"
            for part, name in ((mine, "Pilotos"), (theirs, "Informes listos"))
            if not part["ok"]
        ]
        notes: list[str] = []
        if theirs["ok"] and theirs["unchecked"]:
            notes.append("No se pudo comprobar si ya tienen piloto.")
        if theirs["ok"] and theirs["partial"]:
            notes.append("No se pudo comprobar si algunos informes ya tienen piloto.")
        if pilots_full or flows_full:
            notes.append(OLDER)
        reports = theirs.get("cards", [])
        cards = [*mine.get("cards", []), *reports[:REPORTS_SHOWN]]
        count = len(mine.get("cards", [])) + len(reports)
        return {
            "show": bool(count or errors or notes),
            "errors": errors,
            "notes": notes,
            "cards": cards,
            "count": count,
            "hidden": len(reports[REPORTS_SHOWN:]),
        }

    def niche_card() -> dict[str, Any]:
        return {
            "cards": top_niches(sources.get("niches") or [], flows or []),
            "truncated": flows_full,
            "unchecked": flows is None,  # research states unknown: buttons may repeat one
        }

    def subniche_card() -> dict[str, Any]:
        return {"cards": top_subniches(sources.get("subniches") or [])}

    def calibration_view() -> dict[str, Any]:
        if pilots is None or calibration_source is None:
            return {"show": False, "ok": True}  # the pilots card already reports its own failure
        try:
            return calibration_card(
                calibration_source["entries"], calibration_source["more"], now, timezone
            )
        except FAILED:
            return {"show": True, "ok": False}

    return {
        "calibration": calibration_view(),
        "pending": pending_view(),
        "niches": _card(niche_card, sources.get("niches")),
        "subniches": _card(subniche_card, sources.get("subniches")),
    }
