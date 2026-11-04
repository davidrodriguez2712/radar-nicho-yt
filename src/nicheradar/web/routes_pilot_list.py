# src/nicheradar/web/routes_pilot_list.py
"""Pilot list (M5): where each pilot is, what holds it back and when a decision is due."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, is_fragment, render, shape_guard
from nicheradar.web.pilots_view import list_view, parse_filter
from nicheradar.web.security import Session

router = APIRouter()
VARY = "HX-Request, HX-History-Restore-Request"
PAGE = 100
TRUNCATED = f"Se cargan como máximo {PAGE} pilotos: puede haber más que no se ven en esta pantalla."


@router.get("/pilotos")
@shape_guard
def pilot_list(request: Request, session: Annotated[Session, Depends(current_session)]) -> Response:
    filter_key = parse_filter(request.query_params)
    htmx = is_fragment(request)
    template = "pilotos/_lista.html" if htmx else "pilotos/lista.html"
    try:
        data = request.app.state.api.request("GET", "/pilots", params={"limit": str(PAGE)})
    except ApiError as error:
        response = render(
            request,
            template,
            {
                "active_tab": "pilotos",
                "error": error.message,
                "view": None,
                "filter": filter_key,
                "warnings": [],
            },
            status_code=200 if htmx else 503,
            session=session,
        )
    else:
        items = data["items"]
        if not isinstance(items, list):
            raise TypeError("pilot list is not a list")
        now = datetime.fromtimestamp(request.app.state.clock(), UTC)
        view = list_view(items, filter_key, now, request.app.state.config.timezone)
        response = render(
            request,
            template,
            {
                "active_tab": "pilotos",
                "error": None,
                "view": view,
                "filter": filter_key,
                "warnings": [TRUNCATED] if len(items) == PAGE else [],
            },
            session=session,
        )
    response.headers["Vary"] = VARY
    return response
