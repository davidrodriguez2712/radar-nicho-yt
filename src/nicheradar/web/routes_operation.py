# src/nicheradar/web/routes_operation.py
"""M15 Operación: the market scraper, its recent runs and the sub-niche measurement summary."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import (
    SHAPE_ERRORS,
    SHAPE_MESSAGE,
    current_session,
    render,
    shape_guard,
)
from nicheradar.web.operation import (
    ACTIONS,
    AVISOS,
    LIVE_BLOCK,
    RUNS_LIMIT,
    confirm_view,
    operation_view,
    runs_card,
)
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
NOT_FOUND = "No se encontró lo que buscabas."
INVALID_REQUEST = "La solicitud no es válida."
FAILED = AVISOS["error"][0]
DONE = {"reanudar": "reanudado", "pausar": "pausado"}

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


def _error(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "mas"},
        status_code=status,
        session=session,
    )


def _screen(
    request: Request,
    session: Session,
    action: str,
    schedule: object,
    *,
    error: str | None = None,
    blocked: str | None = None,
    status: int = 200,
) -> Response:
    view = confirm_view(action, schedule, datetime.now(UTC), request.app.state.config.timezone)
    if blocked:
        view["blocked"] = blocked
    return render(
        request,
        "operacion/confirmar.html",
        {"active_tab": "mas", "view": view, "action": action, "error": error},
        status_code=409 if view["blocked"] and status == 200 else status,
        session=session,
    )


def _schedule(request: Request, session: Session) -> object | Response:
    try:
        schedule: object = request.app.state.api.request("GET", "/market/schedule")
    except ApiError as err:
        return _error(request, session, err.message, 503)
    return schedule


@router.get("/operacion/ejecuciones")
@shape_guard
def runs_screen(
    request: Request, session: Annotated[Session, Depends(current_session)]
) -> Response:
    try:
        data = request.app.state.api.request(
            "GET", "/market/runs", params={"limit": str(RUNS_LIMIT)}
        )
    except ApiError as err:
        return _error(request, session, err.message, 503)
    runs = runs_card(
        data.get("items"), datetime.now(UTC), request.app.state.config.timezone, RUNS_LIMIT
    )
    if not runs["ok"]:
        raise TypeError("runs is not a list")
    return render(
        request, "operacion/ejecuciones.html", {"active_tab": "mas", "runs": runs}, session=session
    )


@router.get("/operacion/scraper/{action}")
@shape_guard
def confirm(
    request: Request, action: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    if action not in ACTIONS:
        return _error(request, session, NOT_FOUND, 404)
    schedule = _schedule(request, session)
    if isinstance(schedule, Response):
        return schedule
    return _screen(request, session, action, schedule)


def _submit(request: Request, session: Session, action: str) -> Response:
    schedule = _schedule(request, session)
    if isinstance(schedule, Response):
        return schedule
    view = confirm_view(action, schedule, datetime.now(UTC), request.app.state.config.timezone)
    if view["already"]:
        return RedirectResponse("/operacion?aviso=sin-cambio", status_code=303)
    if view["blocked"]:
        return _screen(request, session, action, schedule)
    try:
        request.app.state.api.request(
            "PUT", "/market/schedule", body={"paused": ACTIONS[action]["paused"]}
        )
    except ApiError as err:
        if err.kind == "conflict":
            if action == "reanudar":
                return _screen(request, session, action, schedule, blocked=LIVE_BLOCK, status=409)
            return _screen(request, session, action, schedule, error=FAILED, status=409)
        return _screen(request, session, action, schedule, error=err.message, status=503)
    return RedirectResponse(f"/operacion?aviso={DONE[action]}", status_code=303)


@router.post("/operacion/scraper/{action}")
def change(
    request: Request,
    action: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error(request, session, INVALID_REQUEST, 403)
    if action not in ACTIONS:
        return _error(request, session, NOT_FOUND, 404)
    try:
        return _submit(request, session, action)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on %s", action)
        return _error(request, session, SHAPE_MESSAGE, 503)
