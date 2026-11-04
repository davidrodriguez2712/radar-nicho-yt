# src/nicheradar/web/routes_pilot_panel.py
"""M6 and M7: the pilot panel with its tabs, and the preparation address that redirects to one."""

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web import calibration
from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.pilot_panel import notice, panel_view, parse_tab
from nicheradar.web.pilots_view import PILOT_RE
from nicheradar.web.security import Session

router = APIRouter()
NOT_FOUND = "No se encontró lo que buscabas."


def _error(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "pilotos"},
        status_code=status,
        session=session,
        with_radar=False,
    )


def _videos(request: Request, pilot_id: str) -> list[Any] | None:
    """The pilot's videos, or None when they cannot be read: only the Videos tab is affected."""
    try:
        data = request.app.state.api.request("GET", f"/pilots/{quote(pilot_id, safe='')}/videos")
    except ApiError:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else None


@router.get("/pilotos/{pilot_id}/preparacion")
@shape_guard
def preparation(
    request: Request, pilot_id: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    if not PILOT_RE.fullmatch(pilot_id):
        return _error(request, session, NOT_FOUND, 404)
    return RedirectResponse(f"/pilotos/{pilot_id}?pestana=preparacion", status_code=303)


@router.get("/pilotos/{pilot_id}")
@shape_guard
def pilot_panel(
    request: Request, pilot_id: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    # PILOT_RE is anchored with $, which also accepts a trailing newline: always fullmatch.
    if not PILOT_RE.fullmatch(pilot_id):
        return _error(request, session, NOT_FOUND, 404)
    try:
        detail = request.app.state.api.request("GET", f"/pilots/{quote(pilot_id, safe='')}")
    except ApiError as err:
        missing = err.kind in ("not_found", "invalid")
        return _error(
            request, session, NOT_FOUND if missing else err.message, 404 if missing else 503
        )
    if not isinstance(detail, dict):
        raise TypeError("pilot detail is not an object")
    detail = {**detail, "pilot_id": pilot_id}  # links use the id that was validated
    tab = parse_tab(request.query_params.get("pestana"))
    videos = _videos(request, pilot_id) if tab == "videos" else None
    dossier: object = None
    if tab == "calibracion" and calibration.has_calibration_schema(detail):
        # Only this tab reads the dossier and the videos, and a failure only affects this tab.
        dossier, videos = calibration.load(
            request.app.state.api, pilot_id, calibration.request_id(detail)
        )
    now = datetime.fromtimestamp(request.app.state.clock(), UTC)
    view = panel_view(detail, videos, now, request.app.state.config.timezone, tab, dossier=dossier)
    context = {
        "active_tab": "pilotos",
        "v": view,
        "notice": notice(request.query_params.get("aviso")),
        "closing_link": request.query_params.get("aviso") == "cerrado" and view["is_closed"],
    }
    return render(request, "pilotos/panel.html", context, session=session)
