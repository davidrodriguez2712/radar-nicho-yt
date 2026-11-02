# tests/web_helpers.py
"""Shared helpers for the mobile web tests."""

import re
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.web.app import create_app

TOKEN = "t" * 32
PASSWORD = "p" * 32


def settings(**over: object) -> Settings:
    values: dict[str, object] = {
        "service_token": SecretStr(TOKEN),
        "dashboard_password": SecretStr(PASSWORD),
        "api_url": "http://api.test",
        "dashboard_ui": "web",
    }
    return Settings(**(values | over))  # type: ignore[arg-type]


Route = tuple[int, object] | Callable[[httpx.Request], httpx.Response]


class Api:
    """Fake private API: a dict of (method, path) -> (status, json) or a callable."""

    def __init__(self, routes: dict[tuple[str, str], Route] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"detail": "not found"})
        if callable(route):
            return route(request)
        status, body = route
        return httpx.Response(status, json=body)

    def count(self, method: str, path: str) -> int:
        return sum(1 for c in self.calls if (c.method, c.url.path) == (method, path))


def make_client(api: Api, clock: Callable[[], float] | None = None, **over: object) -> TestClient:
    app = create_app(
        settings(**over), transport=httpx.MockTransport(api), **({"clock": clock} if clock else {})
    )
    web = TestClient(app, follow_redirects=False)
    response = web.post("/login", data={"password": PASSWORD})
    assert response.status_code == 303, response.text
    return web


def csrf_of(html: str) -> str:
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, html
    return found.group(1)


HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def measurement(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "measured_at": "2026-10-31T12:00:00Z",
        "included": 29,
        "stable_channels": 18,
        "volatile_channels": 11,
        "traction_channels": 19,
        "large_channels": 4,
        "excluded": {"language": 1},
        "income_low": "672.80",
        "income_high": "1681.99",
        "rpm_source": "inherited:wildlife_documentaries",
        "signal": "estimable",
    }
    return base | over


def research(status: str = "listo", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "status": status,
        "language": "en",
        "created_at": "2026-11-02T02:05:45Z",
    }
    return base | over


def subniche_item(slug: str = "prehistoric_creatures", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "slug": slug,
        "label": slug.replace("_", " ").title(),
        "family": "nature_science",
        "parent_niche_slug": "wildlife_documentaries",
        "status": "active",
        "finalist": True,
        "language": "en",
        "format": "long",
        "queries": ["prehistoric creatures documentary", "extinct animals that once ruled earth"],
        "measurement": measurement(),
        "research": None,
    }
    return base | over
