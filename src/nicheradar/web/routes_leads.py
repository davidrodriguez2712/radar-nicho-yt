# src/nicheradar/web/routes_leads.py
"""M31/M32/M34: leer un tweet compartido, elegir sus canales y proponerlos.

Cada acción es un POST separado con CSRF; la web nunca llama a YouTube ni al modelo y nunca
muestra el texto que envía la API: solo los textos fijos de `web.leads`.
"""

import logging
from typing import Annotated, Any

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
from nicheradar.web.leads import error_text, parse_candidate_ids, read_view
from nicheradar.web.proposals import (
    MAX_POLLS,
    idempotency_key,
    poll_count,
    valid_nonce,
)
from nicheradar.web.proposals import (
    PROPOSAL_ID as UUID_RE,
)
from nicheradar.web.routes_share import share_context
from nicheradar.web.security import Session
from nicheradar.web.share import classify

router = APIRouter()
_log = logging.getLogger(__name__)
VARY = "HX-Request, HX-History-Restore-Request"
INVALID_REQUEST = "La solicitud no es válida."
MISSING = "No se encontró lo que buscabas."
STOP_POLLING = 286  # htmx stops a polling element on this status
AVISOS = {
    "buscando": "Buscando por nombre; vuelve en un momento.",
    "sin_seleccion": "Marca al menos un canal resuelto.",
    "sin_propuestas": (
        "No se propuso ningún canal: ya estaban propuestos, ya son semillas "
        "o se llegó al tope diario."
    ),
    "error": "No se pudo completar la acción.",
}
DOMAIN_STATUSES = (409, 413, 422, 429, 503)


def _error_page(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


def _to(read_id: str, aviso: str | None = None, path: str = "") -> RedirectResponse:
    query = f"?aviso={aviso}" if aviso else ""
    return RedirectResponse(f"/lecturas/{read_id}{path}{query}", status_code=303)


@router.post("/compartir/tweet")
def read_tweet(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    nonce: Annotated[str, Form()] = "",
    url: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf) or not valid_nonce(nonce):
        return _error_page(request, session, INVALID_REQUEST, 403)
    found = classify(url[:500])
    if found["kind"] != "tweet":
        context = share_context(found, error=error_text("invalid_tweet_url"))
        return render(request, "compartir.html", context, status_code=422, session=session)
    body = {"url": found["link"]}
    try:
        result = request.app.state.api.request(
            "POST",
            "/leads/tweets",
            body=body,
            headers={
                "Idempotency-Key": idempotency_key(request.app.state.signer, session, nonce, body)
            },
        )
        read_id = result.get("id")
        if not isinstance(read_id, str) or UUID_RE.fullmatch(read_id) is None:
            raise TypeError("read id is not a UUID")
    except ApiError as err:
        domain = err.code is not None and err.status in DOMAIN_STATUSES
        # A domain rejection is final. A transient failure may have queued the read, so the same
        # nonce (the same key) keeps a retry from creating a second one.
        context = share_context(
            found,
            nonce=None if domain else nonce,
            error=error_text(err.code) if domain else err.message,
        )
        status = err.status if domain and err.status else 503
        return render(request, "compartir.html", context, status_code=status, session=session)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on read tweet")
        context = share_context(found, nonce=nonce, error=SHAPE_MESSAGE)
        return render(request, "compartir.html", context, status_code=503, session=session)
    return _to(read_id)


def _load(request: Request, read_id: str) -> dict[str, Any]:
    item = request.app.state.api.request("GET", f"/leads/{read_id}")
    view = read_view(item)
    view["id"] = read_id  # the one that was validated, never the one the body claims
    return view


def _missing(request: Request, session: Session, fragment: bool) -> Response:
    if fragment:
        return render(
            request,
            "_aviso_error.html",
            {"message": MISSING},
            status_code=STOP_POLLING,
            session=session,
        )
    return _error_page(request, session, MISSING, 404)


@router.get("/lecturas/{read_id}")
@shape_guard
def read_detail(
    request: Request,
    read_id: str,
    session: Annotated[Session, Depends(current_session)],
    n: str = "",
    aviso: str = "",
) -> Response:
    fragment = is_fragment(request)
    if UUID_RE.fullmatch(read_id) is None:
        return _missing(request, session, fragment)
    try:
        view = _load(request, read_id)
    except ApiError as err:
        if err.kind in ("not_found", "invalid"):
            return _missing(request, session, fragment)
        if fragment:
            return Response(status_code=204)  # keep the screen; the next poll retries
        return _error_page(request, session, err.message, 503)
    count = poll_count(n)
    waiting = not view["closed"] and (view["state"] in ("en_cola", "leyendo") or view["searching"])
    response = render(
        request,
        "lecturas/_lectura.html" if fragment else "lecturas/lectura.html",
        {
            "active_tab": "nichos",
            "view": view,
            "aviso": AVISOS.get(aviso),
            "polling": waiting and count < MAX_POLLS,
            "exhausted": waiting and count >= MAX_POLLS,
            "next_poll": count + 1,
        },
        session=session,
    )
    response.headers["Vary"] = VARY
    return response


def _post_guard(request: Request, session: Session, read_id: str, csrf: str) -> Response | None:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error_page(request, session, INVALID_REQUEST, 403)
    if UUID_RE.fullmatch(read_id) is None:
        return _error_page(request, session, MISSING, 404)
    return None


@router.post("/lecturas/{read_id}/nombre")
def search_name(
    request: Request,
    read_id: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    buscar: Annotated[str, Form()] = "",
) -> Response:
    """Only the pressed button's `buscar`; the checkboxes that travel in the form are ignored."""
    if (blocked := _post_guard(request, session, read_id, csrf)) is not None:
        return blocked
    if UUID_RE.fullmatch(buscar) is None:
        return _to(read_id, "error")
    try:
        request.app.state.api.request(
            "POST", f"/leads/{read_id}/names", body={"candidate_ids": [buscar]}
        )
    except ApiError:
        return _to(read_id, "error")
    return _to(read_id, "buscando")


@router.post("/lecturas/{read_id}/proponer")
def propose(
    request: Request,
    read_id: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    candidate: Annotated[list[str] | None, Form()] = None,
) -> Response:
    if (blocked := _post_guard(request, session, read_id, csrf)) is not None:
        return blocked
    ids = parse_candidate_ids(candidate or [])
    if ids is None:
        return _to(read_id, "sin_seleccion")
    try:
        result = request.app.state.api.request(
            "POST", f"/leads/{read_id}/proposals", body={"candidate_ids": ids}
        )
    except ApiError:
        return _to(read_id, "error")
    items = result.get("items")
    if (
        isinstance(items, list)
        and items
        and all(isinstance(i, dict) and i.get("outcome") != "queued" for i in items)
    ):
        return _to(read_id, "sin_propuestas")
    return _to(read_id, path="/propuestas")


@router.get("/lecturas/{read_id}/propuestas")
@shape_guard
def proposals_screen(
    request: Request,
    read_id: str,
    session: Annotated[Session, Depends(current_session)],
) -> Response:
    if UUID_RE.fullmatch(read_id) is None:
        return _error_page(request, session, MISSING, 404)
    try:
        view = _load(request, read_id)
    except ApiError as err:
        if err.kind in ("not_found", "invalid"):
            return _error_page(request, session, MISSING, 404)
        return _error_page(request, session, err.message, 503)
    return render(
        request,
        "lecturas/propuestas.html",
        {"active_tab": "nichos", "view": view},
        session=session,
    )


@router.post("/lecturas/{read_id}/cancelar")
def cancel(
    request: Request,
    read_id: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if (blocked := _post_guard(request, session, read_id, csrf)) is not None:
        return blocked
    try:
        request.app.state.api.request("POST", f"/leads/{read_id}/close")
    except ApiError as err:
        if err.kind != "not_found":
            return _to(read_id, "error")
    return RedirectResponse("/subnichos", status_code=303)
