# tests/test_subniche_proposals_api.py
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine

from nicheradar.repositories import schema
from nicheradar.subniche_api import MESSAGES
from nicheradar.subniche_discovery import proposals
from nicheradar.subniche_discovery.store import create_proposed
from tests.subniche_samples import NOW, draft
from tests.test_market_api import AUTH, client

pytestmark = pytest.mark.postgres
BASE = "/api/v1/subniches/proposals"
CHANNEL = "UC" + "a" * 22
KEY = {"Idempotency-Key": "clave-de-prueba-0001"}


def post(api: Any, body: Any, key: str | None = "clave-de-prueba-0001") -> Any:
    headers = dict(AUTH)
    if key is not None:
        headers["Idempotency-Key"] = key
    return api.post(BASE, json=body, headers=headers)


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    for bad in ({}, {"Authorization": "Bearer wrong"}):
        assert api.post(BASE, json={"input": "abc def"}, headers=bad | KEY).status_code == 401
        assert api.get(BASE, headers=bad).status_code == 401
        assert api.get(f"{BASE}/{uuid4()}", headers=bad).status_code == 401


@pytest.mark.parametrize("key", [None, "a" * 7, "a" * 101])
def test_the_idempotency_key_must_be_8_to_100_characters(
    isolated_engine: Engine, key: str | None
) -> None:
    assert post(client(isolated_engine), {"input": "abc def"}, key).status_code == 422


def test_the_idempotency_key_rejects_control_characters() -> None:
    from nicheradar.subniche_api import IDEMPOTENCY_KEY

    adapter = TypeAdapter(IDEMPOTENCY_KEY)
    assert adapter.validate_python("clave-de-prueba-0001")
    for bad in ("clave\x00-de-prueba", "clave\n-de-prueba", "clave\x7f-de-prueba", "a" * 101):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)


def test_valid_posts_queue_each_kind_and_never_call_providers(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    for index, raw in enumerate(
        ("historias de venganza", "https://youtu.be/dQw4w9WgXcQ", "@canal_de_prueba")
    ):
        response = post(api, {"input": raw}, f"clave-valida-{index:04d}")
        assert response.status_code == 202
        body = response.json()
        assert body["created"] is True and body["status"] == "queued"
        assert set(body) == {"id", "status", "created"}
    with isolated_engine.connect() as connection:
        kinds = connection.execute(
            sa.select(schema.subniche_proposal_requests.c.kind).order_by(
                schema.subniche_proposal_requests.c.created_at,
                schema.subniche_proposal_requests.c.kind,
            )
        ).scalars()
        assert sorted(kinds) == ["channel", "query", "video"]


def test_the_same_key_returns_the_same_request(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    first = post(api, {"input": "historias de venganza"}).json()
    second = post(api, {"input": "historias de venganza"})
    assert second.status_code == 202
    assert second.json()["created"] is False and second.json()["id"] == first["id"]


def test_manual_query_is_accepted(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    manual = {"label": "Historias de venganza", "family": "history", "parent": None}
    assert post(api, {"input": "historias manuales", "manual": manual}).status_code == 202


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"input": "https://x.com/user/status/1234567890"}, "tweet_not_supported_yet"),
        ({"input": "https://www.youtube.com/feed/trending"}, "invalid_input"),
        (
            {
                "input": "@canal_de_prueba",
                "manual": {"label": "Historias", "family": "history", "parent": None},
            },
            "manual_needs_a_query",
        ),
    ],
)
def test_rejected_inputs_carry_a_fixed_code_and_message(
    isolated_engine: Engine, body: dict[str, Any], code: str
) -> None:
    response = post(client(isolated_engine), body)
    assert response.status_code == 422
    assert response.json() == {"code": code, "message": MESSAGES[code]}


MANUAL = {"label": "Historias", "family": "history", "parent": None}


@pytest.mark.parametrize(
    "body",
    [
        {"input": "ab"},
        {"input": "x" * 501},
        {"input": "abc def", "extra": 1},
        {"input": "abc def", "manual": MANUAL | {"extra": 1}},
        {"input": "abc\x00def"},
        {"input": "abc def", "manual": MANUAL | {"label": "abc\x00def"}},
        {"input": "abc def", "manual": MANUAL | {"family": "his\x00"}},
        {"input": "abc def", "manual": MANUAL | {"parent": "a\x00b"}},
        {"input": "abc def", "manual": MANUAL | {"label": "ab"}},
        {"input": "abc def", "manual": MANUAL | {"label": "x" * 121}},
        {"input": "abc def", "manual": MANUAL | {"family": "Bad Family"}},
        {"input": "abc def", "manual": MANUAL | {"parent": "p" * 61}},
    ],
)
def test_invalid_bodies_are_422_never_500(isolated_engine: Engine, body: dict[str, Any]) -> None:
    assert post(client(isolated_engine), body).status_code == 422


def test_lone_surrogates_are_422_not_a_database_error(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    headers = AUTH | KEY | {"Content-Type": "application/json"}
    for raw in (
        b'{"input": "abc\\ud800def"}',
        b'{"input": "abc def", "manual": {"label": "abc\\udc00", "family": "history"}}',
    ):
        assert api.post(BASE, content=raw, headers=headers).status_code == 422


def test_the_daily_limit_is_a_429(isolated_engine: Engine) -> None:
    api = client(isolated_engine, subniche_proposals_per_day=1)
    assert post(api, {"input": "primera consulta"}, "clave-valida-0001").status_code == 202
    response = post(api, {"input": "segunda consulta"}, "clave-valida-0002")
    assert response.status_code == 429
    assert response.json() == {"code": "daily_limit", "message": MESSAGES["daily_limit"]}


def seed_requests(engine: Engine) -> dict[str, Any]:
    with engine.begin() as connection:
        ids = {}
        for index, name in enumerate(("queued", "ready", "failed", "odd", "unknown")):
            request_id, _ = proposals.enqueue(
                connection,
                f"consulta {name}",
                manual=None,
                origin="manual",
                key=f"clave-semilla-{index:04d}",
                now=NOW + timedelta(minutes=index),
                per_day=100,
            )
            ids[name] = request_id
        create_proposed(connection, draft(seeds=(CHANNEL,)), NOW)
        connection.execute(
            sa.update(schema.subniche_proposal_requests)
            .where(schema.subniche_proposal_requests.c.id == ids["ready"])
            .values(status="ready", hypothesis_slug="history_revenge", finished_at=NOW)
        )
        for name, code in (
            ("failed", "llm_disabled"),
            ("odd", "duplicate:query:abc"),
            ("unknown", "algo_raro"),
        ):
            connection.execute(
                sa.update(schema.subniche_proposal_requests)
                .where(schema.subniche_proposal_requests.c.id == ids[name])
                .values(status="failed", error_code=code, finished_at=NOW)
            )
    return ids


def test_list_and_detail_expose_status_error_and_hypothesis(isolated_engine: Engine) -> None:
    ids = seed_requests(isolated_engine)
    api = client(isolated_engine)
    listing = api.get(BASE, headers=AUTH)
    assert listing.status_code == 200
    items = {item["id"]: item for item in listing.json()["items"]}
    assert len(items) == 5
    assert "idempotency_key" not in listing.text
    queued = items[str(ids["queued"])]
    assert queued["status"] == "queued" and queued["error"] is None
    assert queued["hypothesis"] is None and queued["kind"] == "query"
    assert set(queued) == {
        "id",
        "status",
        "kind",
        "input",
        "created_at",
        "finished_at",
        "error",
        "hypothesis",
    }
    ready = items[str(ids["ready"])]
    assert ready["hypothesis"]["slug"] == "history_revenge"
    assert set(ready["hypothesis"]) == {
        "slug",
        "label",
        "family",
        "parent_niche",
        "queries",
        "seed_channels",
        "status",
    }
    assert ready["hypothesis"]["queries"] == ["history revenge"]
    assert ready["hypothesis"]["seed_channels"] == [CHANNEL]
    assert ready["hypothesis"]["status"] == "proposed"
    assert items[str(ids["failed"])]["error"] == {
        "code": "llm_disabled",
        "message": MESSAGES["llm_disabled"],
    }
    odd = items[str(ids["odd"])]["error"]
    assert odd == {"code": "duplicate", "message": MESSAGES["duplicate"]}
    unknown = items[str(ids["unknown"])]["error"]
    assert unknown["message"] == "No se pudo preparar la propuesta."
    assert "abc" not in str(odd)
    detail = api.get(f"{BASE}/{ids['ready']}", headers=AUTH)
    assert detail.status_code == 200 and detail.json() == ready
    assert api.get(f"{BASE}?limit=2", headers=AUTH).json()["items"][0]["id"] == str(ids["unknown"])
    assert len(api.get(f"{BASE}?limit=2", headers=AUTH).json()["items"]) == 2
    assert api.get(f"{BASE}?limit=0", headers=AUTH).status_code == 422
    assert api.get(f"{BASE}?limit=101", headers=AUTH).status_code == 422


def test_unknown_and_malformed_ids(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    missing = api.get(f"{BASE}/{uuid4()}", headers=AUTH)
    assert missing.status_code == 404
    assert missing.json()["detail"] == {"code": "not_found", "message": "Propuesta no encontrada."}
    assert api.get(f"{BASE}/no-es-uuid", headers=AUTH).status_code in (404, 422)


def test_hostile_text_is_returned_verbatim_as_data(isolated_engine: Engine) -> None:
    hostile = "  <script>alert(1)</script> javascript:x ñ\u202e  "
    api = client(isolated_engine)
    created = post(api, {"input": hostile}).json()
    detail = api.get(f"{BASE}/{created['id']}", headers=AUTH).json()
    assert detail["input"] == hostile.strip()
