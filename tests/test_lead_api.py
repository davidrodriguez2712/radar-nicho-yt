import base64
import json
import socket
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.integrations.tweets import FxTwitterReader, TweetRef
from nicheradar.integrations.youtube import YouTubeProvider
from nicheradar.lead_api import LEAD_MESSAGES, _present, lead_error
from nicheradar.repositories import schema
from nicheradar.subniche_api import MESSAGES
from nicheradar.subniche_discovery import leads
from nicheradar.subniche_discovery.resolve import Candidate
from nicheradar.web.client import CODE_MESSAGES
from tests.lead_samples import GIF, PNG, TWEET_ID
from tests.subniche_samples import NOW
from tests.test_market_api import AUTH
from tests.test_market_api import client as base_client

pytestmark = pytest.mark.postgres
BASE = "/api/v1/leads"
TWEET = f"https://x.com/autor_x/status/{TWEET_ID}?s=20"
UC_A = "UC" + "a" * 22


def client(engine: Engine, **settings: Any) -> TestClient:
    return base_client(engine, **({"subniche_enabled": True, "mode": "live"} | settings))


def headers(key: str = "clave-lectura-0001") -> dict[str, str]:
    return AUTH | {"Idempotency-Key": key}


def image_body(data: bytes = PNG, media_type: str = "image/png") -> dict[str, str]:
    return {"media_type": media_type, "data": base64.b64encode(data).decode()}


def ready_read(engine: Engine, candidates: list[Candidate]) -> UUID:
    with engine.begin() as connection:
        read_id, _ = leads.enqueue_tweet(
            connection,
            TweetRef("autor_x", TWEET_ID),
            key=f"clave-{uuid4().hex}",
            now=NOW,
            per_day=50,
        )
        leads.claim_next(connection, NOW)
        leads.finish_ready(
            connection,
            read_id,
            author="autor_x",
            text="Texto <script>x</script>",
            candidates=candidates,
            photos_read=1,
            warning="llm_disabled",
            now=NOW,
        )
    return read_id


RESOLVED = Candidate("handle", "@historia_uno", "image", "resolved", UC_A, "Historia Uno", 38000)
NAME = Candidate("name", "Batallas Olvidadas", "text", "name_only")


def forbid_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier uso de red saliente, lector de tweets, YouTube o modelo hace fallar la prueba."""

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("la API privada no debe llamar a proveedores")

    async def aboom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("la API privada no debe llamar a proveedores")

    monkeypatch.setattr(httpx.AsyncClient, "send", aboom)
    monkeypatch.setattr(FxTwitterReader, "read", aboom)
    monkeypatch.setattr(FxTwitterReader, "photo", aboom)
    monkeypatch.setattr(YouTubeProvider, "fetch", aboom)
    monkeypatch.setattr(AnthropicClient, "message", aboom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    some = uuid4()
    calls = [
        ("post", f"{BASE}/tweets"),
        ("post", f"{BASE}/images"),
        ("get", f"{BASE}/{some}"),
        ("post", f"{BASE}/{some}/names"),
        ("post", f"{BASE}/{some}/proposals"),
        ("post", f"{BASE}/{some}/close"),
    ]
    for method, path in calls:
        assert (
            getattr(api, method)(path, headers={"Idempotency-Key": "clave-0001"}).status_code == 401
        )


def test_post_tweet_queues_once_and_never_calls_providers(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    forbid_providers(monkeypatch)
    api = client(isolated_engine)
    first = api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=headers())
    again = api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=headers())
    assert first.status_code == again.status_code == 202
    assert first.json()["created"] is True and again.json() == first.json() | {"created": False}
    read = api.get(f"{BASE}/{first.json()['id']}", headers=AUTH).json()
    assert read["status"] == "queued" and read["tweet"] == {
        "author": "autor_x",
        "url": f"https://x.com/autor_x/status/{TWEET_ID}",
    }


@pytest.mark.parametrize("url", ["https://notx.com/a/status/1", "https://x.com/a", "hola mundo"])
def test_post_tweet_refuses_other_links(isolated_engine: Engine, url: str) -> None:
    response = client(isolated_engine).post(f"{BASE}/tweets", json={"url": url}, headers=headers())
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_tweet_url",
        "message": LEAD_MESSAGES["invalid_tweet_url"],
    }


def test_post_tweet_validates_shape_and_key(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    assert api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=AUTH).status_code == 422
    assert (
        api.post(f"{BASE}/tweets", json={"url": TWEET, "x": 1}, headers=headers()).status_code
        == 422
    )


def test_daily_limit_is_429(isolated_engine: Engine) -> None:
    api = client(isolated_engine, lead_reads_per_day=1)
    assert (
        api.post(
            f"{BASE}/tweets", json={"url": TWEET}, headers=headers("clave-tope-0001")
        ).status_code
        == 202
    )
    response = api.post(f"{BASE}/images", json=image_body(), headers=headers("clave-tope-0002"))
    assert response.status_code == 429 and response.json()["code"] == "daily_limit"


def test_post_image_checks_magic_bytes_and_size(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    ok = api.post(f"{BASE}/images", json=image_body(), headers=headers("clave-img-0001"))
    assert ok.status_code == 202
    for body in (
        image_body(GIF),
        image_body(PNG, "image/jpeg"),
        {"media_type": "image/png", "data": "@@no-base64@@"},
        image_body(PNG, "image/svg+xml"),
    ):
        response = api.post(f"{BASE}/images", json=body, headers=headers(f"clave-{uuid4().hex}"))
        assert response.status_code == 422 and response.json()["code"] == "invalid_image"
    big = image_body(PNG + b"\x00" * 5_242_880)
    response = api.post(f"{BASE}/images", json=big, headers=headers("clave-img-0009"))
    assert response.status_code == 413 and response.json()["code"] == "image_too_large"


def test_read_view_shows_candidates_and_fixed_messages(isolated_engine: Engine) -> None:
    read_id = ready_read(isolated_engine, [RESOLVED, NAME])
    read = client(isolated_engine).get(f"{BASE}/{read_id}", headers=AUTH).json()
    assert read["untrusted_text"] == "Texto <script>x</script>"  # dato, no se interpreta
    assert read["warning"] == {"code": "llm_disabled", "message": LEAD_MESSAGES["llm_disabled"]}
    assert read["error"] is None
    first = read["candidates"][0]
    assert first["channel"] == {"id": UC_A, "title": "Historia Uno", "subscribers": 38000}
    assert read["candidates"][1]["channel"] is None
    assert "idempotency_key" not in str(read) and "image_data" not in str(read)


def test_missing_or_bad_ids(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    missing = api.get(f"{BASE}/{uuid4()}", headers=AUTH)
    assert missing.status_code == 404
    assert missing.json()["detail"] == {"code": "not_found", "message": "Lectura no encontrada."}
    assert api.get(f"{BASE}/no-es-uuid", headers=AUTH).status_code == 422


def test_names_and_proposals_flow(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    read_id = ready_read(isolated_engine, [RESOLVED, NAME])
    ids = [c["id"] for c in api.get(f"{BASE}/{read_id}", headers=AUTH).json()["candidates"]]
    wrong = api.post(f"{BASE}/{read_id}/names", json={"candidate_ids": [ids[0]]}, headers=AUTH)
    assert wrong.status_code == 422 and wrong.json()["code"] == "invalid_candidates"
    named = api.post(f"{BASE}/{read_id}/names", json={"candidate_ids": [ids[1]]}, headers=AUTH)
    assert named.status_code == 202 and named.json() == {"queued": 1}
    proposed = api.post(
        f"{BASE}/{read_id}/proposals", json={"candidate_ids": [ids[0]]}, headers=AUTH
    )
    assert proposed.status_code == 200
    item = proposed.json()["items"][0]
    assert item["outcome"] == "queued"
    proposal = api.get(f"/api/v1/subniches/proposals/{item['proposal_id']}", headers=AUTH).json()
    assert proposal["origin"] == {
        "code": "lead",
        "tweet_author": "autor_x",
        "tweet_url": f"https://x.com/autor_x/status/{TWEET_ID}",
    }
    again = api.post(f"{BASE}/{read_id}/proposals", json={"candidate_ids": [ids[0]]}, headers=AUTH)
    assert again.json()["items"][0]["proposal_id"] == item["proposal_id"]
    assert api.get(f"{BASE}/{read_id}", headers=AUTH).json()["untrusted_text"] is None


def test_proposals_need_a_ready_read_and_bounded_ids(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    queued = api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=headers()).json()["id"]
    response = api.post(
        f"{BASE}/{queued}/proposals", json={"candidate_ids": [str(uuid4())]}, headers=AUTH
    )
    assert response.status_code == 409 and response.json()["code"] == "not_ready"
    too_many = {"candidate_ids": [str(uuid4()) for _ in range(11)]}
    assert api.post(f"{BASE}/{queued}/proposals", json=too_many, headers=AUTH).status_code == 422
    assert (
        api.post(
            f"{BASE}/{uuid4()}/proposals", json={"candidate_ids": [str(uuid4())]}, headers=AUTH
        ).status_code
        == 404
    )


def test_close_purges_the_text(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    read_id = ready_read(isolated_engine, [RESOLVED])
    assert api.post(f"{BASE}/{read_id}/close", headers=AUTH).json() == {
        "id": str(read_id),
        "closed": True,
    }
    assert api.get(f"{BASE}/{read_id}", headers=AUTH).json()["untrusted_text"] is None


@pytest.mark.parametrize("code", ["boom: detalle secreto", "integration_disabled", None])
def test_lead_error_never_leaks_details(code: Any) -> None:
    result = lead_error(code)
    if code is None:
        assert result is None
    else:
        assert result is not None and "secreto" not in result["message"]
        assert result["code"] in LEAD_MESSAGES or result["code"] == "unknown"


def test_reading_is_refused_without_queueing_when_disabled(isolated_engine: Engine) -> None:
    for settings in ({"subniche_enabled": False}, {"mode": "synthetic"}):
        api = client(isolated_engine, **settings)
        for path, body in ((f"{BASE}/tweets", {"url": TWEET}), (f"{BASE}/images", image_body())):
            response = api.post(path, json=body, headers=headers(f"clave-{uuid4().hex}"))
            assert response.status_code == 503
            assert response.json() == {
                "code": "reading_disabled",
                "message": LEAD_MESSAGES["reading_disabled"],
            }
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(schema.lead_read_requests)
            ).scalar_one()
            == 0
        )


def test_unknown_reads_are_404_in_every_endpoint(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    body = {"candidate_ids": [str(uuid4())]}
    some = uuid4()
    for path in ("names", "proposals"):
        response = api.post(f"{BASE}/{some}/{path}", json=body, headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == {
            "code": "not_found",
            "message": "Lectura no encontrada.",
        }
    response = api.post(f"{BASE}/{some}/close", headers=AUTH)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize("key", ["corta", "x" * 101, "clave-con\x07control"])
def test_idempotency_key_bounds(isolated_engine: Engine, key: str) -> None:
    api = client(isolated_engine)
    assert (
        api.post(
            f"{BASE}/tweets", json={"url": TWEET}, headers=AUTH | {"Idempotency-Key": key}
        ).status_code
        == 422
    )
    assert (
        api.post(
            f"{BASE}/images", json=image_body(), headers=AUTH | {"Idempotency-Key": key}
        ).status_code
        == 422
    )


def test_text_with_nul_or_surrogates_is_422(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    for url in (f"{TWEET}\x00", "https://x.com/a/status/1\ud800"):
        raw = json.dumps({"url": url}).encode()
        response = api.post(
            f"{BASE}/tweets", content=raw, headers=headers() | {"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    for raw in (
        b'{"media_type": "image/png", "data": "\\ud800AAAAAAAA"}',
        b"\xff\xfe",
        b"[1]",
        b"[" * 200_000,
        b'{"media_type": "image/png", "data": "AAAAAAAA", "x": 1}',
    ):
        response = api.post(f"{BASE}/images", content=raw, headers=headers(f"clave-{uuid4().hex}"))
        assert response.status_code == 422 and response.json()["code"] == "invalid_image"


def test_oversized_declared_body_is_413_before_reading(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    raw = b'{"media_type":"image/png","data":"' + b"A" * 7_200_000 + b'"}'
    response = api.post(f"{BASE}/images", content=raw, headers=headers("clave-img-9999"))
    assert response.status_code == 413 and response.json()["code"] == "image_too_large"


def test_untrusted_text_is_bounded_by_the_presentation() -> None:
    read = {
        "id": uuid4(),
        "kind": "image",
        "status": "ready",
        "stage": "done",
        "created_at": NOW,
        "finished_at": NOW,
        "closed_at": None,
        "untrusted_text": "a" * 5000,
        "error_code": None,
        "candidates": [],
        "tweet_author": None,
        "tweet_id": None,
    }
    assert len(_present(read)["untrusted_text"]) == 1000


def test_repeated_key_at_the_cap_is_still_202(isolated_engine: Engine) -> None:
    api = client(isolated_engine, lead_reads_per_day=1)
    first = api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=headers("clave-tope-0001"))
    again = api.post(f"{BASE}/tweets", json={"url": TWEET}, headers=headers("clave-tope-0001"))
    assert first.status_code == again.status_code == 202
    assert again.json() == first.json() | {"created": False}


def test_chunked_image_body_without_length_is_413(isolated_engine: Engine) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"media_type":"image/png","data":"'
        for _ in range(72):
            yield b"A" * 100_000
        yield b'"}'

    response = client(isolated_engine).post(
        f"{BASE}/images", content=chunks(), headers=headers("clave-chunk-0001")
    )
    assert response.status_code == 413 and response.json()["code"] == "image_too_large"


def test_shared_messages_match_the_web_mirror() -> None:
    shared = MESSAGES.keys() & CODE_MESSAGES.keys()
    assert "tweet_not_supported_yet" in shared
    assert {code: MESSAGES[code] for code in shared} == {
        code: CODE_MESSAGES[code] for code in shared
    }


def test_closed_read_is_409_and_exposed_as_closed(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    read_id = ready_read(isolated_engine, [RESOLVED, NAME])
    ids = [c["id"] for c in api.get(f"{BASE}/{read_id}", headers=AUTH).json()["candidates"]]
    assert api.get(f"{BASE}/{read_id}", headers=AUTH).json()["closed"] is False
    api.post(f"{BASE}/{read_id}/close", headers=AUTH)
    read = api.get(f"{BASE}/{read_id}", headers=AUTH).json()
    assert read["closed"] is True and "closed_at" not in read
    for path, body in (("names", [ids[1]]), ("proposals", [ids[0]])):
        response = api.post(f"{BASE}/{read_id}/{path}", json={"candidate_ids": body}, headers=AUTH)
        assert response.status_code == 409
        assert response.json() == {"code": "read_closed", "message": "La lectura ya está cerrada."}


def test_expired_and_cancelled_errors_have_fixed_messages() -> None:
    for code in ("expired", "cancelled"):
        result = lead_error(code)
        assert result is not None and result["code"] == code
