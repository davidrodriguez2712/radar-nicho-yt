# src/nicheradar/web/routes_auth.py
"""Login, logout and the home redirect."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from nicheradar.web.deps import current_session, render, safe_next
from nicheradar.web.security import SESSION_COOKIE, SESSION_SECONDS, Session

router = APIRouter()
LIMIT_KEY = "owner"


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


@router.get("/login")
def login_form(request: Request, next: str = "/") -> Response:
    if request.app.state.config.dashboard_password is None:
        return render(request, "login.html", {"pending": True}, status_code=503)
    return render(request, "login.html", {"next": safe_next(next)})


@router.post("/login")
def login(
    request: Request,
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    config = request.app.state.config
    signer = request.app.state.signer
    if config.dashboard_password is None or signer is None:
        return render(request, "login.html", {"pending": True}, status_code=503)
    limiter = request.app.state.limiter
    if limiter.blocked(LIMIT_KEY):
        return render(
            request,
            "login.html",
            {"error": "Demasiados intentos. Espera un minuto e inténtalo de nuevo.", "next": "/"},
            status_code=429,
        )
    expected = config.dashboard_password.get_secret_value().encode()
    if not hmac.compare_digest(password.encode(), expected):
        limiter.fail(LIMIT_KEY)
        return render(
            request,
            "login.html",
            {"error": "Contraseña incorrecta.", "next": safe_next(next)},
            status_code=401,
        )
    limiter.reset(LIMIT_KEY)
    response = RedirectResponse(safe_next(next), status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        signer.issue(),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )
    return response


@router.post("/salir")
def logout(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request, "error.html", {"message": "La solicitud no es válida."}, status_code=403
        )
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/")
def home(_session: Annotated[Session, Depends(current_session)]) -> Response:
    # The mobile "Hoy" screen arrives in the next slice; until then the list is the landing page.
    return RedirectResponse("/subnichos", status_code=303)
