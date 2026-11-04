# src/nicheradar/web/deps.py
"""Request helpers: session guard, safe redirects and template rendering."""

import functools
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from nicheradar.web.security import SESSION_COOKIE, Session

TEMPLATE_DIR = Path(__file__).parent / "templates"


def make_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATE_DIR))


def safe_next(value: str | None) -> str:
    """Only local paths survive: an open redirect after login must be impossible."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def _login_target(request: Request) -> str:
    """HX-Redirect target: remember the page the user was on if it is a same-origin path."""
    current = request.headers.get("hx-current-url")
    if not current:
        return "/login"
    parts = urlsplit(current)
    if parts.netloc != request.url.netloc or parts.scheme not in ("http", "https"):
        return "/login"
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    destination = safe_next(path)
    return f"/login?next={quote(destination, safe='')}" if destination != "/" else "/login"


def current_session(request: Request) -> Session:
    signer = request.app.state.signer
    session: Session | None = (
        signer.read(request.cookies.get(SESSION_COOKIE)) if signer is not None else None
    )
    if session is not None:
        return session
    if request.headers.get("hx-request"):
        raise HTTPException(401, "login required", headers={"HX-Redirect": _login_target(request)})
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    raise HTTPException(
        303, "login required", headers={"Location": f"/login?next={quote(target, safe='')}"}
    )


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    session: Session | None = None,
) -> Response:
    data: dict[str, Any] = {"active_tab": None, "csrf_token": None}
    if session is not None:
        data["csrf_token"] = request.app.state.signer.csrf(session)
    data.update(context or {})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, name, data, status_code=status_code)


def is_fragment(request: Request) -> bool:
    """An htmx partial request; a history restore needs the whole page."""
    return bool(request.headers.get("hx-request")) and not request.headers.get(
        "hx-history-restore-request"
    )


SHAPE_ERRORS = (KeyError, IndexError, TypeError, AttributeError, ValueError, ArithmeticError)
SHAPE_MESSAGE = (
    "La API devolvió datos con un formato inesperado, así que no se puede mostrar esta pantalla. "
    "Intenta de nuevo o revisa la API."
)
_log = logging.getLogger(__name__)


def shape_guard(handler: Callable[..., Response]) -> Callable[..., Response]:
    """A malformed API payload is a 503 with a Spanish message, never an unhandled 500.

    It only wraps view building of GET screens: API failures keep their own, more specific messages.
    """

    @functools.wraps(handler)
    def guarded(*args: Any, **kwargs: Any) -> Response:
        try:
            return handler(*args, **kwargs)
        except SHAPE_ERRORS:
            _log.exception("unexpected API payload shape on %s", handler.__name__)
            request: Request = kwargs["request"]
            if is_fragment(request):
                # htmx does not swap 5xx and the full page would nest inside #contenido.
                response = render(
                    request,
                    "_aviso_error.html",
                    {"message": SHAPE_MESSAGE},
                    session=kwargs.get("session"),
                )
                response.headers["Vary"] = "HX-Request, HX-History-Restore-Request"
                return response
            return render(
                request,
                "error.html",
                {"message": SHAPE_MESSAGE},
                status_code=503,
                session=kwargs.get("session"),
            )

    return guarded
