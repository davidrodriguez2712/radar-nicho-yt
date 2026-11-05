# src/nicheradar/web/routes_lifecycle.py
"""M28 (confirm the approval) and the lifecycle POSTs: approve, pause, resume, archive."""

import logging
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import SHAPE_ERRORS, current_session, render, shape_guard
from nicheradar.web.lifecycle import (
    ACTIONS,
    ALREADY_ARCHIVED,
    CONFIRM_NEEDED,
    NOT_PROPOSED,
    approval_view,
    valid_slug,
)
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
INVALID_REQUEST = "La solicitud no es válida."
MISSING = "No se encontró lo que buscabas."
CONFIRM_VALUE = "1"


def _error_page(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


def _card_hypothesis(request: Request, slug: str) -> dict[str, Any] | None:
    """The hypothesis of the card (label and status), None if it cannot be read."""
    try:
        hypothesis = request.app.state.api.request("GET", f"/subniches/{quote(slug, safe='')}")[
            "hypothesis"
        ]
    except (ApiError, KeyError, TypeError):
        return None
    return hypothesis if isinstance(hypothesis, dict) else None


def _label(hypothesis: dict[str, Any] | None) -> str | None:
    label = hypothesis.get("label") if hypothesis else None
    return label if isinstance(label, str) and label.strip() else None


@router.get("/subnichos/{slug}/aprobar")
@shape_guard
def approve_form(
    request: Request, slug: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    if not valid_slug(slug):
        return _error_page(request, session, MISSING, 404)
    try:
        data = request.app.state.api.request("GET", f"/subniches/{slug}/approval")
    except ApiError as err:
        missing = err.kind in ("not_found", "invalid")
        return _error_page(
            request, session, MISSING if missing else err.message, 404 if missing else 503
        )
    view = approval_view(data, _label(_card_hypothesis(request, slug)), slug)
    return render(
        request,
        "subnichos/aprobar.html",
        {"active_tab": "nichos", "v": view, "not_proposed": NOT_PROPOSED},
        session=session,
    )


def _archive_page(
    request: Request, session: Session, slug: str, *, error: str | None = None, status: int = 200
) -> Response:
    hypothesis = _card_hypothesis(request, slug)
    if hypothesis is None:
        return _error_page(request, session, MISSING, 404)
    return render(
        request,
        "subnichos/archivar.html",
        {
            "active_tab": "nichos",
            "slug": slug,
            "label": _label(hypothesis) or slug,
            "archived": hypothesis.get("status") == "archived",
            "already": ALREADY_ARCHIVED,
            "error": error,
        },
        status_code=status,
        session=session,
    )


@router.get("/subnichos/{slug}/archivar")
@shape_guard
def archive_form(
    request: Request, slug: str, session: Annotated[Session, Depends(current_session)]
) -> Response:
    if not valid_slug(slug):
        return _error_page(request, session, MISSING, 404)
    return _archive_page(request, session, slug)


def _transition(
    request: Request, slug: str, action: str, session: Session, csrf: str, confirmar: str
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error_page(request, session, INVALID_REQUEST, 403)
    if not valid_slug(slug):
        return _error_page(request, session, MISSING, 404)
    if action == "archivar" and confirmar != CONFIRM_VALUE:
        return _archive_page(request, session, slug, error=CONFIRM_NEEDED, status=422)
    endpoint, notice = ACTIONS[action]
    target = f"/subnichos/{slug}"
    try:
        request.app.state.api.request("POST", f"/subniches/{slug}/{endpoint}")
    except ApiError as err:
        if err.kind == "not_found":
            return _error_page(request, session, MISSING, 404)
        key = "transicion_invalida" if err.kind == "conflict" else "transicion_fallida"
        return RedirectResponse(f"{target}?aviso={key}", status_code=303)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on %s", action)
        return RedirectResponse(f"{target}?aviso=transicion_fallida", status_code=303)
    return RedirectResponse(f"{target}?aviso={notice}", status_code=303)


def _post(action: str) -> None:
    def handler(
        request: Request,
        slug: str,
        session: Annotated[Session, Depends(current_session)],
        csrf: Annotated[str, Form()] = "",
        confirmar: Annotated[str, Form()] = "",
    ) -> Response:
        return _transition(request, slug, action, session, csrf, confirmar)

    handler.__name__ = f"{action}_post"
    router.post(f"/subnichos/{{slug}}/{action}")(handler)


for _action in ACTIONS:
    _post(_action)
