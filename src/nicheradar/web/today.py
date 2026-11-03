# src/nicheradar/web/today.py
"""View models for Hoy (M1/M14): four independent cards, each of which may be unavailable."""

import math
from datetime import datetime
from typing import Any

from nicheradar.web import niches, subniches
from nicheradar.web.deps import SHAPE_ERRORS
from nicheradar.web.pilots_view import CLOSED as PILOT_CLOSED
from nicheradar.web.pilots_view import PILOT_RE, blockers, next_action
from nicheradar.web.research import UUID_RE

PAGE = 100  # size of the flow-research and pilots reads: exactly this many may hide older rows
SHOWN = 3
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
        cards.append(
            {
                "label": label if isinstance(label, str) and label else "—",
                "channel": channel if isinstance(channel, str) and channel else "Canal nuevo",
                "text": action or (found[0]["text"] if found else "Hay una decisión pendiente"),
                "href": f"/pilotos/{pilot_id}" if valid else None,
            }
        )
    return cards


def ready_reports(
    flows: list[dict[str, Any]], pilots: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Ready reports whose niche and format have no open pilot yet (at most three)."""
    busy = {
        (pilot.get("niche_label"), pilot.get("format"))
        for pilot in pilots
        if pilot.get("status") not in CLOSED
    }
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
                "href": f"/informes/{report_id}",
            }
        )
        if len(cards) == SHOWN:
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
    return [
        niches.card(item, index.get((item["niche_label"], item["format"])), rank)
        for rank, item in enumerate(scored, 1)
    ]


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
    sources: dict[str, list[dict[str, Any]] | None], now: datetime, timezone: str = "UTC"
) -> dict[str, Any]:
    """`sources` maps status/niches/flows/pilots/subniches to its items, or None if it failed."""
    flows, pilots = sources.get("flows"), sources.get("pilots")
    flows_full = flows is not None and len(flows) >= PAGE
    pilots_full = pilots is not None and len(pilots) >= PAGE

    def pilot_card() -> dict[str, Any]:
        cards = attention_cards(pilots or [], now, timezone)
        return {"cards": cards, "count": len(cards), "truncated": pilots_full}

    def report_card() -> dict[str, Any]:
        return {
            "cards": ready_reports(flows or [], pilots or []),
            "truncated": flows_full,
            "unchecked": pilots is None,  # without the pilots we cannot tell which have one
        }

    def niche_card() -> dict[str, Any]:
        return {
            "cards": top_niches(sources.get("niches") or [], flows or []),
            "truncated": flows_full,
            "unchecked": flows is None,  # research states unknown: buttons may repeat one
        }

    def subniche_card() -> dict[str, Any]:
        return {"cards": top_subniches(sources.get("subniches") or [])}

    return {
        "pilots": _card(pilot_card, pilots),
        "reports": _card(report_card, flows),
        "niches": _card(niche_card, sources.get("niches")),
        "subniches": _card(subniche_card, sources.get("subniches")),
    }
