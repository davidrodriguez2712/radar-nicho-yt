# tests/test_web_smoke_screens.py
"""Cross-screen safety net: hostile text, API down, bad shapes, origins, CSRF."""

import copy
import json
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.web_helpers import (
    HOSTILE,
    REPORT_ID,
    Api,
    dossier_v3,
    flow_item,
    make_client,
    niche_detail,
    niche_item,
    pilot_item,
    report_detail,
    research,
    subniche_card,
    subniche_item,
)

ROUTES = [
    "/",
    "/nichos",
    "/nichos/investigar?etiqueta=x&formato=long",
    "/subnichos",
    "/subnichos/uno",
    f"/informes/{REPORT_ID}",
    f"/pilotos/autorizar?informe={REPORT_ID}",
]
STRUCTURAL = {
    "status", "format", "language", "decision", "recommendation", "schema_version", "id",
    "slug", "state", "kind", "confidence", "comparator", "metric", "level", "verdict", "basis",
    "origin", "stage", "stages", "source", "version", "signal", "rpm_source", "rpm_state",
    "family", "parent_niche_slug", "channel_id", "pilot_id", "report_id", "action", "code",
    "path", "unit", "currency", "kind_of", "classification", "rights", "automation", "mode",
}  # fmt: skip
SCRIPT = "<script>alert(1)</script>"


def hostile(value: Any, key: str | None = None) -> Any:
    """Replace every string leaf by HOSTILE, except structural keys, ids, dates and URLs."""
    if isinstance(value, dict):
        return {k: hostile(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [hostile(v, key) for v in value]
    if isinstance(value, str):
        keep = key in STRUCTURAL or (key or "").endswith(("_at", "_id", "_until", "_low", "_high"))
        return value if keep else HOSTILE
    return value


def fixtures() -> dict[str, Any]:
    return {
        "status": {"radar_paused": True, "timezone": "America/Lima"},
        "niches": {"items": [niche_item()], "total": 1, "limit": 200, "offset": 0},
        "niche": niche_detail(),
        "flows": {"items": [flow_item("listo", id=REPORT_ID), flow_item("en_curso")]},
        "report": report_detail(dossier=dossier_v3()),
        "pilots": {"items": [pilot_item(needs_decision=True)]},
        "subniches": {"items": [subniche_item(research=research())]},
        "card": subniche_card(research=research()),
    }


def dump(value: Any) -> bytes:
    return json.dumps(value, allow_nan=True).encode()  # NaN/Infinity come out as bare tokens


class SmokeApi(Api):
    """Fake API serving `data` by resource, read on every call so tests can mutate it in place."""

    def __init__(self, data: dict[str, Any] | None, error: Exception | None = None) -> None:
        super().__init__()
        self.data, self.error = data, error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.data is not None
        path = request.url.path.removeprefix("/api/v1")
        if request.method != "GET":
            return httpx.Response(500, json={"detail": "unexpected write"})
        key = next(
            (k for prefix, k in RESOURCES if path == prefix or path.startswith(prefix + "/")), None
        )
        if key is None:
            return httpx.Response(404, json={"detail": "not found"})
        if prefix_is_item(path, key):
            key = ITEM_KEYS[key]
        return httpx.Response(
            200, content=dump(self.data[key]), headers={"content-type": "application/json"}
        )


RESOURCES = [
    ("/status", "status"),
    ("/market/niches", "niches"),
    ("/flow-research", "flows"),
    ("/pilots", "pilots"),
    ("/subniches", "subniches"),
]
ITEM_KEYS = {"niches": "niche", "flows": "report", "subniches": "card"}


def prefix_is_item(path: str, key: str) -> bool:
    return key in ITEM_KEYS and path.count("/") > (2 if key == "niches" else 1)


def api_for(data: dict[str, Any] | None, error: Exception | None = None) -> SmokeApi:
    return SmokeApi(data, error)


def client_for(
    data: dict[str, Any] | None, error: Exception | None = None
) -> tuple[TestClient, SmokeApi]:
    api = api_for(data, error)
    web = make_client(api)
    api.calls.clear()
    return web, api


def check_safe(response: httpx.Response, route: str) -> None:
    assert response.status_code < 500 or response.status_code == 503, (route, response.status_code)
    assert "Traceback" not in response.text, route


@pytest.mark.parametrize("route", ROUTES)
def test_hostile_text_is_escaped_on_every_screen(route: str) -> None:
    web, _ = client_for(hostile(fixtures()))
    response = web.get(route)
    check_safe(response, route)
    body = response.text
    assert SCRIPT not in body
    assert not re.search(r"""href\s*=\s*["']\s*javascript:""", body, re.I)
    assert not re.search(r"""href\s*=\s*["']https?://[^"']*evil""", body, re.I)
    if not route.startswith("/nichos/investigar"):  # that form only echoes the query label
        assert "&lt;script&gt;" in body or response.status_code != 200, route


def test_a_hostile_label_in_the_investigate_query_is_escaped() -> None:
    web, _ = client_for(hostile(fixtures()))
    response = web.get("/nichos/investigar", params={"etiqueta": HOSTILE, "formato": "long"})
    check_safe(response, "investigar")
    assert SCRIPT not in response.text


@pytest.mark.parametrize("route", ROUTES)
def test_an_unreachable_api_gives_a_spanish_message_never_a_500(route: str) -> None:
    web, _ = client_for(None, httpx.ConnectError("down"))
    response = web.get(route)
    check_safe(response, route)
    assert response.status_code in (200, 503), (route, response.status_code)
    assert re.search(
        r"no disponible|No se pudo|No se encontr|Sin datos|sin conexi", response.text, re.I
    ), route


def paths(value: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    yield prefix
    if isinstance(value, dict):
        for k, v in value.items():
            yield from paths(v, (*prefix, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from paths(v, (*prefix, i))


def replaced(data: Any, path: tuple[Any, ...], new: Any) -> Any:
    copied = copy.deepcopy(data)
    if not path:
        return new
    node = copied
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = new
    return copied


BAD: list[Any] = [None, "x", 7, [], {}, float("nan"), float("inf")]


@pytest.mark.parametrize("route", ROUTES)
def test_malformed_shapes_never_give_a_500(route: str) -> None:
    base = fixtures()
    data = copy.deepcopy(base)
    web, api = client_for(data)  # the fake API reads `data` on every call
    failures: list[str] = []
    for key in base:
        for path in paths(base[key]):
            for bad in BAD:
                data[key] = replaced(base[key], path, bad)
                api.calls.clear()
                where = f"{key}{list(path)} <- {bad!r}"
                try:
                    response = web.get(route)
                except Exception as error:  # an unhandled error is a 500 for the user
                    failures.append(f"{where}: {type(error).__name__}: {error}")
                    continue
                if response.status_code >= 500 and response.status_code != 503:
                    failures.append(f"{where}: {response.status_code}")
            data[key] = base[key]
    assert not failures, (
        len(failures),
        sorted({f.split(": ", 1)[1][:90] for f in failures}),
        failures[:6],
    )


def _naive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _naive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_naive(v) for v in value]
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:]+Z", value):
        return value.removesuffix("Z")
    return value


@pytest.mark.parametrize("route", ROUTES)
def test_timezone_naive_datetimes_never_give_a_500(route: str) -> None:
    web, _ = client_for(_naive(fixtures()))
    check_safe(web.get(route), route)


def raw_nan_api() -> Api:
    nan = httpx.Response(200, content=b'{"x": NaN, "items": [{"y": Infinity}]}')
    return Api({("GET", p): lambda _r: nan for p in NAN_PATHS})


NAN_PATHS = [
    "/api/v1/status",
    "/api/v1/market/niches",
    "/api/v1/market/niches/x",
    "/api/v1/flow-research",
    f"/api/v1/flow-research/{REPORT_ID}",
    "/api/v1/pilots",
    "/api/v1/subniches",
    "/api/v1/subniches/uno",
]


@pytest.mark.parametrize("route", ROUTES)
def test_bare_nan_in_the_json_body_never_gives_a_500(route: str) -> None:
    web = make_client(raw_nan_api())
    check_safe(web.get(route), route)


THIRD_PARTY = re.compile(
    r"""(?:src|href|action|poster|srcset)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?(?:https?:)?//""",
    re.I,
)
INLINE = re.compile(r"<style|\sstyle\s*=|<script(?![^>]*\ssrc=)|\son[a-z]+\s*=", re.I)


def good_clients() -> Iterator[tuple[str, TestClient]]:
    for route in ROUTES:
        web, _ = client_for(fixtures())
        yield route, web


def test_no_screen_loads_third_party_origins_or_inline_code() -> None:
    csps: set[str | None] = set()
    for route, web in good_clients():
        response = web.get(route)
        assert response.status_code == 200, route
        csps.add(response.headers.get("content-security-policy"))
        body = response.text
        assert not INLINE.search(body), (route, INLINE.search(body))
        for found in re.finditer(r"""<a\s[^>]*href\s*=\s*["']https?://[^>]*>""", body, re.I):
            assert route.startswith("/informes/"), (route, found.group(0))
            assert "noopener" in found.group(0) and "noreferrer" in found.group(0), found.group(0)
            assert "nofollow" in found.group(0), found.group(0)
        stripped = re.sub(r"""<a\s[^>]*href\s*=\s*["']https?://[^>]*>""", "", body, flags=re.I)
        assert not THIRD_PARTY.search(stripped), (route, THIRD_PARTY.search(stripped))
    assert len(csps) == 1 and None not in csps


POSTS: list[tuple[str, dict[str, str]]] = [
    ("/nichos/decidir", {"etiqueta": "x", "formato": "long", "decision": "descartado"}),
    ("/nichos/investigar", {"etiqueta": "x", "formato": "long", "idioma": "en"}),
    ("/pilotos/autorizar", {"informe": REPORT_ID, "canal": "c"}),
    ("/subnichos/uno/investigar", {"idioma": "en"}),
    ("/salir", {}),
]


@pytest.mark.parametrize(("path", "form"), POSTS)
def test_every_post_without_csrf_is_refused_and_touches_no_api(
    path: str, form: dict[str, str]
) -> None:
    web, api = client_for(fixtures())
    response = web.post(path, data=form)
    assert response.status_code in (302, 303, 400, 403), (path, response.status_code)
    # the layout may read the cached radar badge; nothing else (no data read, no write)
    assert [c.url.path for c in api.calls if c.url.path != "/api/v1/status"] == [], path
    assert all(c.method == "GET" for c in api.calls), path
    assert web.get("/nichos").status_code == 200  # the session is intact: nothing was applied


def test_login_is_the_only_post_outside_csrf() -> None:
    web, api = client_for(fixtures())
    bare = TestClient(web.app, follow_redirects=False)
    assert bare.post("/login", data={"password": "bad"}).status_code in (200, 303, 401, 429)
    assert api.calls == []
