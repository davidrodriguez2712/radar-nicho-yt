# src/nicheradar/web/routes_today.py
"""Hoy (M1 and M14): what needs the owner today; every source degrades its own card."""

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web import calibration
from nicheradar.web.client import ApiClient, ApiError
from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.format import spanish_date
from nicheradar.web.security import Session
from nicheradar.web.today import PAGE, calibration_candidates, today_view

router = APIRouter()
NICHE_POOL = "10"  # some niches have no score: ask for more than the three that are shown


def _items(api: ApiClient, path: str, params: dict[str, str] | None = None) -> list[Any] | None:
    """The `items` of one source, or None when it fails or answers with an unexpected shape."""
    try:
        data = api.request("GET", path, params=params)
    except ApiError:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return None
    return items


def _calibration_entry(api: ApiClient, pilot: dict[str, Any]) -> dict[str, Any]:
    """The dossier and videos of one active pilot; `skipped` when its package has no dossier-v3."""
    pilot_id = pilot["pilot_id"]
    entry: dict[str, Any] = {"pilot": pilot, "dossier": None, "videos": None}
    try:
        detail = api.request("GET", f"/pilots/{quote(pilot_id, safe='')}")
    except ApiError:
        return entry
    if not calibration.has_calibration_schema(detail):
        return entry | {"skipped": True}
    rid = calibration.request_id(detail)
    if rid is None:
        return entry
    entry["dossier"], entry["videos"] = calibration.load(api, pilot_id, rid)
    return entry


@router.get("/")
@shape_guard
def today(request: Request, session: Annotated[Session, Depends(current_session)]) -> Response:
    api: ApiClient = request.app.state.api
    # The topbar badge already reads /status (cached); the timezone is the configured one.
    sources = {
        "niches": _items(api, "/market/niches", {"limit": NICHE_POOL, "order": "opportunity"}),
        "flows": _items(api, "/flow-research", {"limit": str(PAGE)}),
        "pilots": _items(api, "/pilots", {"limit": str(PAGE)}),
        "subniches": _items(api, "/subniches"),
    }
    entries: list[dict[str, Any]] = []
    candidates, more = calibration_candidates(sources["pilots"] or [])
    for pilot in candidates:
        entries.append(_calibration_entry(api, pilot))
    config = request.app.state.config
    now = datetime.fromtimestamp(request.app.state.clock(), UTC)
    return render(
        request,
        "hoy.html",
        {
            "active_tab": "hoy",
            "today": spanish_date(now, config.timezone),
            "v": today_view(
                sources,
                now,
                config.timezone,
                {"entries": entries, "more": more} if sources["pilots"] is not None else None,
            ),
        },
        session=session,
    )
