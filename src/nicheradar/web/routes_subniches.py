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


@router.get("/subnichos")
def subniche_list(
    request: Request, session: Annotated[Session, Depends(current_session)]
) -> Response:
    filters = parse_filters(request.query_params)
    htmx = bool(request.headers.get("hx-request"))
    template = "subnichos/_lista.html" if htmx else "subnichos/lista.html"
    try:
        data = request.app.state.api.request(
            "GET",
            "/subniches",
            params={"include_inactive": "true" if filters.inactivos else "false"},
        )
    except ApiError as error:
        return render(
            request,
            template,
            {"active_tab": "nichos", "error": error.message, "view": None, "filtros": filters},
            status_code=503,
            session=session,
        )
    view = list_view(data["items"], filters)
    return render(
        request,
        template,
        {"active_tab": "nichos", "error": None, "view": view, "filtros": view["filtros"]},
        session=session,
    )
