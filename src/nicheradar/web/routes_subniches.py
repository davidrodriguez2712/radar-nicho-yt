# src/nicheradar/web/routes_subniches.py
"""Sub-niche screens: M9 list (this task) and M10 card (next task)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render
from nicheradar.web.security import Session
from nicheradar.web.subniches import list_view, parse_filters

router = APIRouter()


VARY = "HX-Request, HX-History-Restore-Request"
INACTIVE_STATES = ("paused", "archived")


@router.get("/subnichos")
def subniche_list(
    request: Request, session: Annotated[Session, Depends(current_session)]
) -> Response:
    filters = parse_filters(request.query_params)
    # A history restore asks for the whole page even though htmx sets hx-request.
    htmx = bool(request.headers.get("hx-request")) and not request.headers.get(
        "hx-history-restore-request"
    )
    template = "subnichos/_lista.html" if htmx else "subnichos/lista.html"
    # Choosing paused/archived is explicit intent: the API hides them unless asked.
    inactive = filters.inactivos or filters.estado in INACTIVE_STATES
    try:
        data = request.app.state.api.request(
            "GET", "/subniches", params={"include_inactive": "true" if inactive else "false"}
        )
    except ApiError as error:
        # htmx does not swap 5xx, so a fragment request gets the error as a 200 fragment.
        response = render(
            request,
            template,
            {"active_tab": "nichos", "error": error.message, "view": None, "filtros": filters},
            status_code=200 if htmx else 503,
            session=session,
        )
    else:
        view = list_view(data["items"], filters)
        response = render(
            request,
            template,
            {"active_tab": "nichos", "error": None, "view": view, "filtros": view["filtros"]},
            session=session,
        )
    response.headers["Vary"] = VARY
    return response
