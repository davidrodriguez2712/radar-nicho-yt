# tests/test_flow_research_api.py
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.flow_research_samples import valid_dossier
from tests.test_market_api import AUTH, seeded
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres
BASE = "/api/v1/flow-research"


def tentative_api(engine: Engine) -> TestClient:
    api = seeded(engine)
    body = {"format": "long", "decision": "tentativo"}
    path = "/api/v1/market/niches/personal_finance/decisions"
    assert api.post(path, json=body, headers=AUTH).status_code == 201
    return api


def create(api: TestClient) -> dict[str, Any]:
    response = api.post(
        BASE, json={"niche_label": "personal_finance", "format": "long"}, headers=AUTH
    )
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    api = seeded(isolated_engine)
    some = uuid4()
    assert api.get(BASE).status_code == 401
    assert api.get(BASE + "/pending").status_code == 401
    assert api.get(f"{BASE}/{some}").status_code == 401
    assert api.post(f"{BASE}/{some}/claim", json={"owner": "w"}).status_code == 401
    assert api.post(f"{BASE}/{some}/dossier", json={}).status_code == 401
    wrong = {"Authorization": "Bearer wrong"}
    assert api.get(BASE, headers=wrong).status_code == 401


def test_create_is_idempotent_and_refuses_ineligible_niches(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    first = create(api)
    assert first["status"] == "pendiente" and first["created"] is True
    again = api.post(BASE, json={"niche_label": "personal_finance", "format": "long"}, headers=AUTH)
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    assert again.json()["created"] is False
    gaming = api.post(BASE, json={"niche_label": "gaming_general", "format": "long"}, headers=AUTH)
    assert gaming.status_code == 409 and gaming.json()["detail"]["code"] == "not_tentative"
    missing = api.post(BASE, json={"niche_label": "nope", "format": "long"}, headers=AUTH)
    assert missing.status_code == 404
    bad = api.post(BASE, json={"niche_label": "personal_finance", "format": "x"}, headers=AUTH)
    assert bad.status_code == 422


def test_the_full_round_trip(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    request_id = create(api)["id"]
    pending = api.get(BASE + "/pending", headers=AUTH).json()["items"]
    assert [item["id"] for item in pending] == [request_id]
    assert "evidence" not in pending[0]

    claim = api.post(f"{BASE}/{request_id}/claim", json={"owner": "w1"}, headers=AUTH)
    assert claim.status_code == 200 and claim.json()["status"] == "en_curso"
    assert claim.json()["evidence"]["niche"]["niche_label"] == "personal_finance"
    again = api.post(f"{BASE}/{request_id}/claim", json={"owner": "w2"}, headers=AUTH)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "not_claimable"

    path = f"{BASE}/{request_id}/dossier"
    stranger = api.post(path, json={"owner": "w2", "dossier": {}}, headers=AUTH)
    assert stranger.status_code == 409 and stranger.json()["detail"]["code"] == "lease_lost"

    bad = valid_dossier(uuid4(), NOW)
    rejected = api.post(path, json={"owner": "w1", "dossier": bad}, headers=AUTH)
    assert rejected.status_code == 422
    body = rejected.json()
    assert body["accepted"] is False and body["status"] == "en_curso"
    assert body["remaining_attempts"] == 1 and body["problems"]

    good = valid_dossier(UUID(request_id), NOW)
    accepted = api.post(path, json={"owner": "w1", "dossier": good}, headers=AUTH)
    assert accepted.status_code == 200 and accepted.json()["accepted"] is True

    detail = api.get(f"{BASE}/{request_id}", headers=AUTH).json()
    assert detail["status"] == "listo" and detail["dossier"]["niche_label"] == "personal_finance"
    listed = api.get(BASE + "?niche_label=personal_finance&format=long&limit=1", headers=AUTH)
    assert [item["status"] for item in listed.json()["items"]] == ["listo"]


def test_the_second_invalid_dossier_rejects_the_request(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    request_id = create(api)["id"]
    api.post(f"{BASE}/{request_id}/claim", json={"owner": "w1"}, headers=AUTH)
    path = f"{BASE}/{request_id}/dossier"
    for expected in ("en_curso", "rechazado"):
        response = api.post(path, json={"owner": "w1", "dossier": {"x": 1}}, headers=AUTH)
        assert response.status_code == 422 and response.json()["status"] == expected
    detail = api.get(f"{BASE}/{request_id}", headers=AUTH).json()
    assert detail["status"] == "rechazado" and detail["rejection"]["problems"]


def test_unknown_ids_and_bad_bodies(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    assert api.get(f"{BASE}/{uuid4()}", headers=AUTH).status_code == 404
    assert api.post(f"{BASE}/{uuid4()}/claim", json={"owner": "w"}, headers=AUTH).status_code == 404
    assert api.post(f"{BASE}/{uuid4()}/claim", json={}, headers=AUTH).status_code == 422
    assert api.get(f"{BASE}/not-a-uuid", headers=AUTH).status_code == 422
    assert api.get(BASE + "?limit=0", headers=AUTH).status_code == 422
