# tests/test_api_body_limit.py
"""Límite de cuerpo ASGI de `/api/v1`: corre antes de autenticar y no lee más de lo necesario."""

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.api import create_app
from nicheradar.api_limits import (
    BODY_LIMITS,
    BODY_METHODS,
    DEFAULT_BODY_LIMIT,
    LEAD_BODY_LIMIT,
    PAYLOAD_TOO_LARGE,
    ApiBodyLimitMiddleware,
    limit_for,
)
from nicheradar.config import Settings
from tests.flow_research_samples import valid_dossier
from tests.pilot_samples import report_v3, video_v3
from tests.test_persistence import NOW

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
EXPECTED = {
    "code": "payload_too_large",
    "message": "El cuerpo de la solicitud es demasiado grande.",
}


def api() -> TestClient:
    return TestClient(create_app(Settings(service_token=SecretStr(TOKEN))))


def big_json(size: int) -> bytes:
    """Un JSON válido de `size` bytes exactos."""
    filler = size - len(b'{"x":""}')
    return b'{"x":"' + b"a" * filler + b'"}'


def test_the_limit_table_is_named_and_ordered() -> None:
    assert LEAD_BODY_LIMIT == 64 * 1024
    assert DEFAULT_BODY_LIMIT == 4 * 1024 * 1024
    assert limit_for("/api/v1/leads/tweets") == LEAD_BODY_LIMIT
    assert limit_for(f"/api/v1/leads/{uuid4()}/names") == LEAD_BODY_LIMIT
    assert limit_for(f"/api/v1/leads/{uuid4()}/proposals") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/subniches/proposals") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/leads/images") is None
    assert limit_for("/api/v1/flow-research/x/dossier") == DEFAULT_BODY_LIMIT
    assert limit_for("/api/v1/runs") == DEFAULT_BODY_LIMIT
    assert limit_for("/api/v1leads") is None  # fuera de /api/v1
    assert limit_for("/") is None
    assert limit_for("/subnichos/proponer") is None
    assert all(rule.path.startswith("/api/v1/") for rule in BODY_LIMITS)
    # Criterio: la exención es por igualdad exacta; las demás reglas cubren también sus subrutas.
    assert [rule.path for rule in BODY_LIMITS if rule.limit is None] == ["/api/v1/leads/images"]
    assert all(rule.exact for rule in BODY_LIMITS if rule.limit is None)
    assert limit_for("/api/v1/leads/images/names") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/leads/images/proposals") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/leads/images/x") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/leads/images/") == LEAD_BODY_LIMIT
    assert limit_for("/api/v1/subniches/proposals/x") == LEAD_BODY_LIMIT


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/leads/images/names",
        "/api/v1/leads/images/proposals",
        "/api/v1/leads/images%2Fnames",
        "/api/v1/leads/images/x",
    ],
)
def test_the_images_exemption_does_not_leak_to_sibling_routes(path: str) -> None:
    response = api().post(
        path,
        content=big_json(LEAD_BODY_LIMIT + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413 and response.json() == EXPECTED


def test_put_and_patch_are_limited_too() -> None:
    assert {"POST", "PUT", "PATCH"} <= BODY_METHODS
    client = api()
    for method, path in (
        ("PUT", "/api/v1/profile"),
        ("PUT", "/api/v1/radar"),
        ("PUT", "/api/v1/market/schedule"),
        ("PATCH", "/api/v1/profile"),
    ):
        response = client.request(
            method,
            path,
            content=big_json(DEFAULT_BODY_LIMIT + 1),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413, (method, path)
        assert response.json() == EXPECTED


@pytest.mark.parametrize("token", [True, False])
@pytest.mark.parametrize("path", ["/api/v1/leads/tweets", "/api/v1/subniches/proposals"])
def test_declared_length_over_the_limit_is_413_with_or_without_token(
    token: bool, path: str
) -> None:
    response = api().post(
        path,
        content=big_json(LEAD_BODY_LIMIT + 1),
        headers=(AUTH if token else {}) | {"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == EXPECTED
    assert response.headers["content-type"].startswith("application/json")


def test_default_limit_applies_to_the_rest_of_the_api() -> None:
    over = api().post(
        "/api/v1/runs",
        content=big_json(DEFAULT_BODY_LIMIT + 1),
        headers={"Content-Type": "application/json"},
    )
    assert over.status_code == 413 and over.json() == EXPECTED


def test_a_body_exactly_at_the_limit_goes_through_to_authentication() -> None:
    response = api().post(
        "/api/v1/leads/tweets",
        content=big_json(LEAD_BODY_LIMIT),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_the_message_is_fixed_and_repeats_nothing_from_the_request() -> None:
    response = api().post(
        "/api/v1/leads/tweets/zzz-secreto?q=otro-secreto",
        content=b'{"x":"' + b"a" * LEAD_BODY_LIMIT + b'"}',
        headers={"Content-Type": "application/json", "X-Raro": "valor-raro"},
    )
    assert response.status_code == 413
    assert response.content == json.dumps(EXPECTED, ensure_ascii=False).encode()
    assert "secreto" not in response.text and "raro" not in response.text.lower()


def test_leads_images_is_exempt_and_reaches_its_own_validation() -> None:
    body = json.dumps({"media_type": "image/png", "data": "A" * 1_000_000}).encode()
    response = api().post(
        "/api/v1/leads/images",
        content=body,
        headers=AUTH | {"Content-Type": "application/json", "Idempotency-Key": "clave-imagen-01"},
    )
    assert response.status_code != 413


def test_routes_outside_the_api_and_bodyless_methods_are_untouched() -> None:
    client = api()
    outside = client.post("/otra/ruta", content=big_json(DEFAULT_BODY_LIMIT + 1))
    assert outside.status_code == 404
    get = client.get("/api/v1/leads/tweets", headers={"Content-Length": "999999999"})
    assert get.status_code != 413


def test_the_largest_legitimate_requests_still_work() -> None:
    client = api()
    dossier = json.dumps({"owner": "agente", "dossier": valid_dossier(uuid4(), NOW)}).encode()
    assert len(dossier) < DEFAULT_BODY_LIMIT
    pad = json.dumps(
        {"owner": "agente", "dossier": {"relleno": "a" * 2_000_000}}  # cerca del peor caso teórico
    ).encode()
    report = json.dumps(report_v3(*[video_v3(f"v_20261103_a{n:03d}") for n in range(100)])).encode()
    for body, path in (
        (dossier, f"/api/v1/flow-research/{uuid4()}/dossier"),
        (pad, f"/api/v1/flow-research/{uuid4()}/dossier"),
        (report[: 256 * 1024], f"/api/v1/pilots/{uuid4()}/reports"),
    ):
        response = client.post(
            path, content=body, headers=AUTH | {"Content-Type": "application/json"}
        )
        assert response.status_code != 413, path


# --- nivel ASGI: cuerpo en streaming, sin Content-Length -------------------------------------


class Probe:
    """Una app ASGI mínima que lee el cuerpo entero y cuenta lo que consume."""

    def __init__(self) -> None:
        self.called = False
        self.lifespan_seen = False

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            self.lifespan_seen = True
            return
        self.called = True
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def run_asgi(
    app: Any,
    path: str,
    chunks: list[bytes],
    headers: list[tuple[bytes, bytes]],
    method: str = "POST",
) -> tuple[list[dict[str, Any]], int]:
    served = 0
    queue = list(chunks)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal served
        if not queue:
            return {"type": "http.disconnect"}
        served += 1
        body = queue.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(queue)}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": b"",
    }
    asyncio.run(app(scope, receive, send))
    return sent, served


def test_chunked_body_is_cut_without_reading_the_rest() -> None:
    probe = Probe()
    app = ApiBodyLimitMiddleware(probe)
    chunk = b"a" * 16_384
    chunks = [chunk] * 1000  # 16 MB: nada de esto debe consumirse entero
    sent, served = run_asgi(app, "/api/v1/leads/tweets", chunks, [])
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"]) == EXPECTED
    # tope + un chunk: 64 KiB / 16 KiB = 4 chunks caben, el quinto lo supera.
    assert served <= LEAD_BODY_LIMIT // len(chunk) + 1
    assert served < 10


def test_chunked_body_at_the_limit_passes_through() -> None:
    probe = Probe()
    app = ApiBodyLimitMiddleware(probe)
    chunks = [b"a" * 16_384] * (LEAD_BODY_LIMIT // 16_384)
    sent, served = run_asgi(app, "/api/v1/leads/tweets", chunks, [])
    assert probe.called and sent[0]["status"] == 200
    assert served == len(chunks)


def test_a_lying_content_length_cannot_hide_a_bigger_body() -> None:
    probe = Probe()
    app = ApiBodyLimitMiddleware(probe)
    headers = [(b"content-length", b"10")]
    sent, served = run_asgi(app, "/api/v1/leads/tweets", [b"a" * 40_000] * 5, headers)
    assert sent[0]["status"] == 413 and served <= 3


def test_declared_oversize_never_calls_the_app() -> None:
    probe = Probe()
    app = ApiBodyLimitMiddleware(probe)
    headers = [(b"content-length", str(LEAD_BODY_LIMIT + 1).encode())]
    sent, served = run_asgi(app, "/api/v1/leads/tweets", [b"x"], headers)
    assert sent[0]["status"] == 413 and not probe.called and served == 0


def test_invalid_content_length_is_ignored_not_trusted() -> None:
    probe = Probe()
    app = ApiBodyLimitMiddleware(probe)
    sent, _ = run_asgi(app, "/api/v1/leads/tweets", [b"ok"], [(b"content-length", b"abc")])
    assert probe.called and sent[0]["status"] == 200


def test_lifespan_and_websocket_pass_through_untouched() -> None:
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    async def receive() -> dict[str, Any]:
        raise AssertionError("no se debe leer nada")

    async def send(message: MutableMapping[str, Any]) -> None:
        raise AssertionError("no se debe responder nada")

    wrapped = ApiBodyLimitMiddleware(inner)

    async def go() -> None:
        for kind in ("lifespan", "websocket"):
            await wrapped({"type": kind, "path": "/api/v1/x"}, receive, send)

    asyncio.run(go())
    assert seen == ["lifespan", "websocket"]


def test_the_fixed_response_is_the_public_constant() -> None:
    assert PAYLOAD_TOO_LARGE == EXPECTED


def test_the_middleware_is_pure_asgi() -> None:
    from starlette.middleware.base import BaseHTTPMiddleware

    assert not issubclass(ApiBodyLimitMiddleware, BaseHTTPMiddleware)


def test_chunked_body_against_the_real_app_is_413_not_400() -> None:
    app = create_app(Settings(service_token=SecretStr(TOKEN)))
    headers = [(b"content-type", b"application/json")]
    chunks = [b'{"x":"' + b"a" * 16_000] + [b"a" * 16_384] * 500
    sent, served = run_asgi(app, "/api/v1/leads/tweets", chunks, headers)
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"]) == EXPECTED
    assert served <= 5


def test_the_cut_inside_a_task_group_is_still_a_413() -> None:
    """Un `BaseExceptionGroup` (anyio task group en la app) no debe saltarse el corte."""
    import anyio

    async def grouped(scope: Any, receive: Any, send: Any) -> None:
        async def read() -> None:
            while True:
                if not (await receive()).get("more_body"):
                    return

        async with anyio.create_task_group() as group:
            group.start_soon(read)

    app = ApiBodyLimitMiddleware(grouped)
    sent, served = run_asgi(app, "/api/v1/leads/tweets", [b"a" * 16_384] * 100, [])
    assert sent[0]["status"] == 413 and json.loads(sent[1]["body"]) == EXPECTED
    assert served <= 5


def test_if_the_response_already_started_the_cut_is_not_answered_twice() -> None:
    async def late(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while (await receive()).get("more_body"):
            pass

    app = ApiBodyLimitMiddleware(late)
    sent: list[dict[str, Any]] = []
    with pytest.raises(BaseException):  # noqa: B017, PT011 - la interrupción interna
        sent, _ = run_asgi(app, "/api/v1/leads/tweets", [b"a" * 40_000] * 5, [])
    assert sent == []  # no se envió ningún segundo inicio de respuesta
