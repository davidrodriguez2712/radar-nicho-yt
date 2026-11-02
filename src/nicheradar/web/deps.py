# src/nicheradar/web/deps.py
"""Request helpers: session guard, safe redirects and template rendering."""

from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from nicheradar.web.client import STATUS_TIMEOUT_SECONDS, ApiError
from nicheradar.web.security import SESSION_COOKIE, Session

TEMPLATE_DIR = Path(__file__).parent / "templates"
RADAR_TTL_SECONDS = 30


def make_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATE_DIR))


def radar_state(request: Request) -> str | None:
    """'paused', 'active' or None when the API cannot say; cached so pages are not status calls."""
    app = request.app
    cache: dict[str, Any] = app.state.radar_cache
    now = app.state.clock()
    if cache["until"] > now:
        cached: str | None = cache["value"]
        return cached
    value: str | None
    try:
        data = app.state.api.request("GET", "/status", timeout=STATUS_TIMEOUT_SECONDS)
        value = "paused" if data.get("radar_paused") else "active"
    except ApiError:
        value = None
    cache.update(until=now + RADAR_TTL_SECONDS, value=value)
    return value


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
    with_radar: bool = True,
) -> Response:
    data: dict[str, Any] = {"active_tab": None, "radar_state": None, "csrf_token": None}
    if session is not None:
        data["csrf_token"] = request.app.state.signer.csrf(session)
        # A page whose own API call failed skips the badge: the API is down, do not wait again.
        data["radar_state"] = radar_state(request) if with_radar else None
    data.update(context or {})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, name, data, status_code=status_code)
