# src/nicheradar/web/routes_pilot_actions.py
"""Follow, close and cancel a pilot, and the closing summary.

Closing or cancelling a real pilot cannot be undone, so every POST checks the CSRF token first,
validates the id and the note locally, re-reads the pilot and only then writes. The decision and
the actor come from the route and the server, never from the form.
"""

import logging
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import SHAPE_ERRORS, SHAPE_MESSAGE, current_session, render, shape_guard
from nicheradar.web.pilot_actions import (
    ACTIONS,
    ACTOR,
    CONFLICT_MESSAGES,
    GENERIC_CONFLICT,
    NO_SUMMARY_YET,
    NOTE_MAX,
    NOTICE_KEYS,
    allowed,
    note_error,
    refusal,
    validate_note,
)
from nicheradar.web.pilots_view import PILOT_RE
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
NOT_FOUND = "No se encontró lo que buscabas."
INVALID_REQUEST = "La solicitud no es válida."


def _error(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "pilotos"},
        status_code=status,
        session=session,
        with_radar=False,
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _screen(
    request: Request,
    session: Session,
    pilot_id: str,
    action: str,
    pilot: dict[str, Any],
    *,
    note: str = "",
    error: str | None = None,
    status: int = 200,
) -> Response:
    """The confirmation for this pilot: the form when the action applies, the reason when not."""
    current = _text(pilot.get("status"))
    blocked = None if allowed(action, current) else refusal(action, current)
    form_action = (
        f"/pilotos/{pilot_id}/cancelar"
        if action == "cancelar"
        else f"/pilotos/{pilot_id}/decidir?accion={action}"
    )
    return render(
        request,
        "pilotos/confirmar.html",
        {
            "active_tab": "pilotos",
            "spec": ACTIONS[action],
            "pilot_id": pilot_id,
            "niche": _text(pilot.get("niche_label")),
            "channel": _text(pilot.get("target_channel")),
            "form_action": form_action,
            "note": note,
            "note_max": NOTE_MAX,
            "error": error,
            "blocked": blocked,
        },
        status_code=409 if blocked and status == 200 else status,
        session=session,
        # After a call the API already answered: skip the radar badge's extra call.
        with_radar=error is None and blocked is None,
    )


def _fetch(request: Request, session: Session, pilot_id: str) -> dict[str, Any] | Response:
    try:
        pilot = request.app.state.api.request("GET", f"/pilots/{quote(pilot_id, safe='')}")
    except ApiError as err:
        missing = err.kind in ("not_found", "invalid")
        return _error(
            request, session, NOT_FOUND if missing else err.message, 404 if missing else 503
        )
    if not isinstance(pilot, dict):
        raise TypeError("pilot detail is not an object")
    return pilot


def _confirmation(request: Request, session: Session, pilot_id: str, action: str) -> Response:
    if not PILOT_RE.fullmatch(pilot_id) or action not in ACTIONS:
        return _error(request, session, NOT_FOUND, 404)
    pilot = _fetch(request, session, pilot_id)
    if isinstance(pilot, Response):
        return pilot
    return _screen(request, session, pilot_id, action, pilot)


@router.get("/pilotos/{pilot_id}/decidir")
@shape_guard
def decide_form(
    request: Request, pilot_id: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    action = request.query_params.get("accion", "")
    return _confirmation(request, session, pilot_id, action if action != "cancelar" else "")


@router.get("/pilotos/{pilot_id}/cancelar")
@shape_guard
def cancel_form(
    request: Request, pilot_id: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    return _confirmation(request, session, pilot_id, "cancelar")


def _submit(request: Request, session: Session, pilot_id: str, action: str, typed: str) -> Response:
    note = validate_note(typed)
    pilot = _fetch(request, session, pilot_id)
    if isinstance(pilot, Response):
        return pilot
    if note is None:
        return _screen(
            request, session, pilot_id, action, pilot,
            note=typed, error=note_error(action), status=422,
        )  # fmt: skip
    if not allowed(action, _text(pilot.get("status"))):
        return _screen(request, session, pilot_id, action, pilot)
    pilot_path = f"/pilots/{quote(pilot_id, safe='')}"
    if action == "cancelar":
        path, body = f"{pilot_path}/cancel", {"reason": note, "actor": ACTOR}
    else:
        path, body = f"{pilot_path}/decision", {"decision": action, "note": note, "actor": ACTOR}
    try:
        request.app.state.api.request("POST", path, body=body)
    except ApiError as err:
        if err.kind == "conflict":
            info = err.detail if isinstance(err.detail, dict) else {}
            code = info.get("code")
            message = (
                CONFLICT_MESSAGES.get(code, GENERIC_CONFLICT)
                if isinstance(code, str)
                else GENERIC_CONFLICT
            )
            return _screen(
                request, session, pilot_id, action, pilot, note=note, error=message, status=409
            )
        if err.kind == "not_found":
            return _screen(
                request, session, pilot_id, action, pilot,
                note=note, error=CONFLICT_MESSAGES["not_found"], status=404,
            )  # fmt: skip
        if err.kind == "invalid":
            return _screen(
                request, session, pilot_id, action, pilot,
                note=note, error=GENERIC_CONFLICT, status=422,
            )  # fmt: skip
        return _screen(
            request, session, pilot_id, action, pilot, note=note, error=err.message, status=503
        )
    return RedirectResponse(f"/pilotos/{pilot_id}?aviso={NOTICE_KEYS[action]}", status_code=303)


def _post(
    request: Request, session: Session, csrf: str, pilot_id: str, action: str, typed: str
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error(request, session, INVALID_REQUEST, 403)
    if not PILOT_RE.fullmatch(pilot_id) or action not in ACTIONS:
        return _error(request, session, NOT_FOUND, 404)
    try:
        return _submit(request, session, pilot_id, action, typed)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on %s", action)
        return _error(request, session, SHAPE_MESSAGE, 503)


@router.post("/pilotos/{pilot_id}/decidir")
def decide(
    request: Request,
    pilot_id: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    # The decision is the route's `accion`, validated against the whitelist; the actor is fixed.
    action = request.query_params.get("accion", "")
    return _post(request, session, csrf, pilot_id, action if action != "cancelar" else "", note)


@router.post("/pilotos/{pilot_id}/cancelar")
def cancel(
    request: Request,
    pilot_id: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> Response:
    return _post(request, session, csrf, pilot_id, "cancelar", reason)


@router.get("/pilotos/{pilot_id}/cierre")
@shape_guard
def closing_summary(
    request: Request, pilot_id: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    if not PILOT_RE.fullmatch(pilot_id):
        return _error(request, session, NOT_FOUND, 404)
    try:
        text = request.app.state.api.request_text(
            "GET", f"/pilots/{quote(pilot_id, safe='')}/closing-summary"
        )
    except ApiError as err:
        info = err.detail if isinstance(err.detail, dict) else {}
        if err.kind == "conflict" and info.get("code") == "bad_transition":
            return _error(request, session, NO_SUMMARY_YET, 409)
        if err.kind in ("not_found", "invalid"):
            return _error(request, session, NOT_FOUND, 404)
        return _error(request, session, err.message, 503)
    context = {"active_tab": "pilotos", "pilot_id": pilot_id, "text": text}
    return render(request, "pilotos/cierre.html", context, session=session)
