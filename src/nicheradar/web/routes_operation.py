# src/nicheradar/web/routes_operation.py
"""M15 Operación: the market scraper, its recent runs and the sub-niche measurement summary."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.operation import AVISOS, RUNS_LIMIT, operation_view
from nicheradar.web.security import Session

router = APIRouter()

VARY = "HX-Request, HX-History-Restore-Request"


def _read(
    request: Request, path: str, params: dict[str, str] | None = None, key: str | None = None
) -> object:
    """One source read on its own: a failure leaves only that card without data."""
    try:
        data: dict[str, Any] = request.app.state.api.request("GET", path, params=params)
    except ApiError:
        return None
    return data.get(key) if key else data


@router.get("/operacion")
@shape_guard
def operation(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    aviso: str = "",
) -> Response:
    sources = {
        "schedule": _read(request, "/market/schedule"),
        "runs": _read(request, "/market/runs", {"limit": str(RUNS_LIMIT)}, "items"),
        "subniches": _read(request, "/subniches", {"include_inactive": "true"}, "items"),
    }
    view = operation_view(sources, datetime.now(UTC), request.app.state.config.timezone)
    response = render(
        request,
        "operacion/operacion.html",
        {"active_tab": "mas", "view": view, "notice": AVISOS.get(aviso)},
        session=session,
    )
    response.headers["Vary"] = VARY
    return response
