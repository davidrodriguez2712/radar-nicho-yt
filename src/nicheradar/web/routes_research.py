# src/nicheradar/web/routes_research.py
"""M8: choose the language and create a flow-research order for a backlog niche."""

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import SHAPE_ERRORS, SHAPE_MESSAGE, current_session, render, shape_guard
from nicheradar.web.research import CONFLICT_MESSAGES, LANG_RE, UUID_RE, language_options
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
FORMATS = ("long", "shorts")
NOT_FOUND = "No se encontró lo que buscabas."


def _valid_target(label: str, fmt: str) -> bool:
    return 1 <= len(label) <= 140 and label not in (".", "..") and fmt in FORMATS


def _error_page(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
        with_radar=False,
    )


def _page(
    request: Request,
    session: Session,
    label: str,
    fmt: str,
    *,
    status: int = 200,
    error: str | None = None,
    reasons: list[str] | None = None,
    chosen: str | None = None,
) -> Response:
    try:
        detail = request.app.state.api.request(
            "GET", f"/market/niches/{quote(label, safe='')}", params={"format": fmt}
        )
    except ApiError as err:
        if error is not None:
            # The order already failed: keep its message even if the form cannot be redrawn.
            return _error_page(request, session, error, status)
        return _error_page(request, session, err.message, 404 if err.kind == "not_found" else 503)
    view = language_options(detail["language_mix"])
    codes = {o["code"] for o in view["options"]}
    return render(
        request,
        "nichos/investigar.html",
        {
            "active_tab": "nichos",
            "label": label,
            "format": fmt,
            "format_text": "Shorts" if fmt == "shorts" else "Largos",
            "lang": view,
            "error": error,
            "reasons": reasons or [],
            "chosen": chosen if chosen in codes else view["suggested"],
        },
        status_code=status,
        session=session,
        # After a failed order the API already answered: skip the radar badge's extra call.
        with_radar=error is None,
    )


@router.get("/nichos/investigar")
@shape_guard
def form(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    etiqueta: str = "",
    formato: str = "",
) -> Response:
    if not _valid_target(etiqueta, formato):
        return _error_page(request, session, NOT_FOUND, 404)
    return _page(request, session, etiqueta, formato)


@router.post("/nichos/investigar")
def start(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    etiqueta: Annotated[str, Form()] = "",
    formato: Annotated[str, Form()] = "",
    idioma: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error_page(request, session, "La solicitud no es válida.", 403)
    if not _valid_target(etiqueta, formato):
        return _error_page(request, session, NOT_FOUND, 404)
    if not LANG_RE.fullmatch(idioma):
        return _error_page(request, session, "Elige un idioma válido de la lista.", 422)
    try:
        return _start(request, session, etiqueta, formato, idioma)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on start")
        return _error_page(request, session, SHAPE_MESSAGE, 503)


def _start(
    request: Request, session: Session, etiqueta: str, formato: str, idioma: str
) -> Response:
    api = request.app.state.api
    try:
        detail = api.request(
            "GET", f"/market/niches/{quote(etiqueta, safe='')}", params={"format": formato}
        )
    except ApiError as err:
        return _error_page(request, session, err.message, 404 if err.kind == "not_found" else 503)
    allowed = {o["code"] for o in language_options(detail["language_mix"])["options"]}
    if idioma not in allowed:
        return _page(
            request,
            session,
            etiqueta,
            formato,
            status=422,
            error="Elige un idioma válido de la lista.",
        )
    try:
        result = api.request(
            "POST",
            "/flow-research",
            body={"niche_label": etiqueta, "format": formato, "language": idioma},
        )
    except ApiError as err:
        info = err.detail if isinstance(err.detail, dict) else {}
        code = str(info.get("code"))
        reasons = [
            str(r.get("message", "")) for r in info.get("reasons") or [] if isinstance(r, dict)
        ]
        if err.kind in ("conflict", "not_found"):
            return _page(
                request,
                session,
                etiqueta,
                formato,
                status=409 if err.kind == "conflict" else 404,
                chosen=idioma,
                error=CONFLICT_MESSAGES.get(code, err.message),
                reasons=reasons,
            )
        return _page(
            request,
            session,
            etiqueta,
            formato,
            status=422 if err.kind == "invalid" else 503,
            chosen=idioma,
            error=err.message,
        )
    report = result.get("id")
    if not isinstance(report, str) or not UUID_RE.fullmatch(report):
        return RedirectResponse("/nichos?aviso=error-creada", status_code=303)
    aviso = "creada" if result.get("created") else "existente"
    return RedirectResponse(f"/informes/{report}?aviso={aviso}", status_code=303)
