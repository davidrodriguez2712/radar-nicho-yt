# src/nicheradar/web/app.py
"""Mobile web UI (FastAPI + Jinja2 + HTMX) served in place of the Streamlit dashboard."""

import time
from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from nicheradar.config import Settings

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


def create_app(
    config: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    config = config or Settings()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.transport = transport
    app.state.clock = clock

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/_stcore/health", response_class=PlainTextResponse)
    def health() -> str:
        # Same path Streamlit exposes: compose, the smoke test and the proxy probe rely on it.
        return "ok"

    return app
