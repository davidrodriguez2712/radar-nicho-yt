# src/nicheradar/web/app.py
"""Mobile web UI (FastAPI + Jinja2 + HTMX) served in place of the Streamlit dashboard."""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from nicheradar.config import Settings
from nicheradar.web import routes_auth, routes_subniches
from nicheradar.web.client import ApiClient
from nicheradar.web.deps import make_templates, render
from nicheradar.web.security import LoginLimiter, SessionSigner

STATIC_DIR = Path(__file__).parent / "static"

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
    app.state.api = ApiClient(config, transport=transport)
    app.state.signer = SessionSigner.from_settings(config, clock)
    app.state.limiter = LoginLimiter(clock)
    app.state.templates = make_templates()
    app.state.radar_cache = {"until": 0.0, "value": None}
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

    @app.get("/sw.js")
    def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.get("/sin-conexión")
    def offline(request: Request) -> Response:
        return render(request, "offline.html")

    app.include_router(routes_auth.router)
    app.include_router(routes_subniches.router)
    return app
