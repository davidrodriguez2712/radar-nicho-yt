# src/nicheradar/web/deps.py
"""Request helpers: session guard, safe redirects and template rendering."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from nicheradar.web.client import ApiError
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
        data = app.state.api.request("GET", "/status")
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


def current_session(request: Request) -> Session:
    signer = request.app.state.signer
    session: Session | None = (
        signer.read(request.cookies.get(SESSION_COOKIE)) if signer is not None else None
    )
    if session is not None:
        return session
    if request.headers.get("hx-request"):
        raise HTTPException(401, "login required", headers={"HX-Redirect": "/login"})
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
    data: dict[str, Any] = {"active_tab": None, "radar_state": None, "csrf_token": None}
    if session is not None:
        data["csrf_token"] = request.app.state.signer.csrf(session)
        data["radar_state"] = radar_state(request)
    data.update(context or {})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, name, data, status_code=status_code)
