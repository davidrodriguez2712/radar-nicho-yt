# src/nicheradar/web/routes_proposals.py
"""M25 form and M26/M27 preparation of a proposal. The web never calls YouTube or the model."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import (
    SHAPE_ERRORS,
    SHAPE_MESSAGE,
    current_session,
    is_fragment,
    render,
    shape_guard,
)
from nicheradar.web.proposals import (
    FORM_ERRORS,
    INPUT_MAX,
    MAX_POLLS,
    error_text,
    idempotency_key,
    new_nonce,
    parse_form,
    poll_count,
    proposal_view,
    valid_nonce,
    valid_proposal_id,
)
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
VARY = "HX-Request, HX-History-Restore-Request"
INVALID_REQUEST = "La solicitud no es válida."
MISSING = "No se encontró lo que buscabas."
POLLING = ("en_cola", "preparando")
STOP_POLLING = 286  # htmx stops a polling element on this status


def _form(
    request: Request,
    session: Session,
    *,
    values: dict[str, str],
    nonce: str | None = None,
    error: str | None = None,
    status: int = 200,
) -> Response:
    """`nonce` is kept only when the request may still be queued (a transient failure)."""
    response = render(
        request,
        "subnichos/proponer.html",
        {
            "active_tab": "nichos",
            "nonce": nonce if nonce is not None and valid_nonce(nonce) else new_nonce(),
            "values": values,
            "error": error,
            "input_max": INPUT_MAX,
        },
        status_code=status,
        session=session,
    )
    response.headers["Vary"] = VARY
    return response


def _error_page(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


@router.get("/subnichos/proponer")
@shape_guard
def propose_form(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    q: str = "",
) -> Response:
    return _form(request, session, values={"input": q[:INPUT_MAX]})


@router.post("/subnichos/proponer")
def propose(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    nonce: Annotated[str, Form()] = "",
    input: Annotated[str, Form()] = "",  # noqa: A002 - the field name of the API body
    manual: Annotated[str, Form()] = "",
    modo: Annotated[str, Form()] = "",
    label: Annotated[str, Form()] = "",
    family: Annotated[str, Form()] = "",
    parent: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error_page(request, session, INVALID_REQUEST, 403)
    manual_mode = manual == "1" or modo == "manual"
    values = {
        "input": input[:INPUT_MAX],
        "manual": "1" if manual_mode else "",
        "label": label[:200],
        "family": family[:100],
        "parent": parent[:100],
    }
    if not valid_nonce(nonce):
        return _form(
            request, session, values=values, error=FORM_ERRORS["nonce_invalid"], status=422
        )
    body, key = parse_form(input, manual_mode, label, family, parent)
    if key is not None:
        return _form(
            request, session, values=values, nonce=nonce, error=FORM_ERRORS[key], status=422
        )
    try:
        result = request.app.state.api.request(
            "POST",
            "/subniches/proposals",
            body=body,
            headers={
                "Idempotency-Key": idempotency_key(request.app.state.signer, session, nonce, body)
            },
        )
        proposal_id = result.get("id")
        if not valid_proposal_id(proposal_id):
            raise TypeError("proposal id is not a UUID")
    except ApiError as err:
        domain = err.code is not None and err.status in (422, 429)
        # A domain rejection is final: the retry is a new request. A transient failure may have
        # queued it, so the same nonce (the same key) keeps a retry from creating a second one.
        return _form(
            request,
            session,
            values=values,
            nonce=None if domain else nonce,
            error=error_text(err.code) if domain else err.message,
            status=err.status if domain and err.status else 503,
        )
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on propose")
        return _form(request, session, values=values, nonce=nonce, error=SHAPE_MESSAGE, status=503)
    return RedirectResponse(f"/subnichos/propuestas/{proposal_id}", status_code=303)


@router.get("/subnichos/propuestas/{proposal_id}")
@shape_guard
def proposal_detail(
    request: Request,
    proposal_id: str,
    session: Annotated[Session, Depends(current_session)],
    n: str = "",
) -> Response:
    fragment = is_fragment(request)
    if not valid_proposal_id(proposal_id):
        return _error_page(request, session, MISSING, 404)
    try:
        item = request.app.state.api.request("GET", f"/subniches/proposals/{proposal_id}")
    except ApiError as err:
        if fragment:
            # A transient error keeps the screen (204 swaps nothing) and the next poll retries.
            # 286 does swap, even with an empty body (it would erase #estado), so it carries
            # a real fragment.
            if err.kind == "not_found":
                return render(
                    request,
                    "_aviso_error.html",
                    {"message": MISSING},
                    status_code=STOP_POLLING,
                    session=session,
                )
            return Response(status_code=204)
        missing = err.kind in ("not_found", "invalid")
        return _error_page(
            request, session, MISSING if missing else err.message, 404 if missing else 503
        )
    view = proposal_view(item, datetime.now(UTC))
    count = poll_count(n)
    response = render(
        request,
        "subnichos/_propuesta.html" if fragment else "subnichos/propuesta.html",
        {
            "active_tab": "nichos",
            "v": view,
            "proposal_id": proposal_id,
            "polling": view["state"] in POLLING and count < MAX_POLLS,
            "exhausted": view["state"] in POLLING and count >= MAX_POLLS,
            "next_poll": count + 1,
        },
        session=session,
    )
    response.headers["Vary"] = VARY
    return response
