# tests/test_market_api.py
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.market_intel.worker import tick_market
from tests.test_foundation import TOKEN
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def client(engine: Engine, **settings: Any) -> TestClient:
    config = Settings(service_token=SecretStr(TOKEN), **settings)
    return TestClient(create_app(config, engine=engine, clock=lambda: NOW))


def seeded(engine: Engine) -> TestClient:
    with engine.begin() as connection:
        seed_niche(connection, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
        seed_niche(connection, "gaming_general", (60, 80, 100, 120), price=720)
        seed_niche(connection, "cooking_recipes", (400, 500))
        seed_niche(connection, "personal_finance", (900, 1000, 1100), fmt="shorts")
    return client(engine)


def test_market_endpoints_require_the_service_token(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    for path in ("/niches", "/listings", "/runs", "/schedule"):
        assert api.get("/api/v1/market" + path).status_code == 401
    assert (
        api.get("/api/v1/market/niches", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )


def test_niches_list_filters_and_validates(isolated_engine: Engine) -> None:
    api = seeded(isolated_engine)
    everything = api.get("/api/v1/market/niches", headers=AUTH).json()
    assert everything["total"] == 4
    longs = api.get("/api/v1/market/niches?format=long", headers=AUTH).json()["items"]
    assert [item["niche_label"] for item in longs] == [
        "personal_finance",
        "gaming_general",
        "cooking_recipes",
    ]
    assert longs[0]["opportunity"]["value"] is not None
    assert longs[2]["opportunity"]["state"] == "insufficient_evidence"
    shorts = api.get("/api/v1/market/niches?format=shorts", headers=AUTH).json()["items"]
    assert [item["rpm_state"] for item in shorts] == ["uncalibrated"]
    by_automation = api.get("/api/v1/market/niches?order=automation", headers=AUTH)
    assert by_automation.status_code == 200
    assert api.get("/api/v1/market/niches?order=bogus", headers=AUTH).status_code == 422
    assert api.get("/api/v1/market/niches?limit=0", headers=AUTH).status_code == 422


def test_niche_detail_and_decisions(isolated_engine: Engine) -> None:
    api = seeded(isolated_engine)
    path = "/api/v1/market/niches/personal_finance"
    detail = api.get(path + "?format=long", headers=AUTH)
    assert detail.status_code == 200 and len(detail.json()["listings"]) == 4
    assert all(item["seller_declared"] for item in detail.json()["listings"])
    assert api.get(path, headers=AUTH).status_code == 422  # the format is required
    assert api.get("/api/v1/market/niches/nope?format=long", headers=AUTH).status_code == 404
    body = {"format": "long", "decision": "tentativo", "note": "revisar"}
    assert api.post(path + "/decisions", json=body, headers=AUTH).status_code == 201
    listed = api.get("/api/v1/market/niches?format=long", headers=AUTH).json()["items"][0]
    assert listed["decision"]["decision"] == "tentativo" and listed["decision"]["note"] == "revisar"
    discard = {"format": "long", "decision": "descartado"}
    assert api.post(path + "/decisions", json=discard, headers=AUTH).status_code == 201
    hidden = api.get("/api/v1/market/niches?format=long", headers=AUTH).json()["items"]
    assert "personal_finance" not in [item["niche_label"] for item in hidden]
    shown = api.get("/api/v1/market/niches?format=long&include_discarded=true", headers=AUTH)
    assert "personal_finance" in [item["niche_label"] for item in shown.json()["items"]]
    for bad in ({"format": "long", "decision": "bogus"}, {"format": "x", "decision": "nuevo"}):
        assert api.post(path + "/decisions", json=bad, headers=AUTH).status_code == 422
    extra = {"format": "long", "decision": "nuevo", "unexpected": 1}
    assert api.post(path + "/decisions", json=extra, headers=AUTH).status_code == 422
    unknown = api.post("/api/v1/market/niches/nope/decisions", json=body, headers=AUTH)
    assert unknown.status_code == 404


def test_listings_endpoint_filters_and_paginates(isolated_engine: Engine) -> None:
    api = seeded(isolated_engine)
    page = api.get("/api/v1/market/listings?limit=3", headers=AUTH).json()
    assert page["total"] == 4 + 4 + 2 + 3 and len(page["items"]) == 3
    assert page["items"][0]["seller_declared"] is True
    assert api.get("/api/v1/market/listings?status=disappeared", headers=AUTH).json()["total"] == 0
    found = api.get("/api/v1/market/listings?query=Channel", headers=AUTH).json()
    assert found["total"] == 13
    assert api.get("/api/v1/market/listings?status=bogus", headers=AUTH).status_code == 422


def test_schedule_is_paused_by_default_and_independent_from_the_radar(
    isolated_engine: Engine,
) -> None:
    api = client(isolated_engine)
    first = api.get("/api/v1/market/schedule", headers=AUTH).json()
    assert first["paused"] is True and first["mode"] == "synthetic"
    assert first["radar_paused"] is None or first["radar_paused"] is True
    resumed = api.put("/api/v1/market/schedule", json={"paused": False}, headers=AUTH)
    assert resumed.status_code == 200 and resumed.json()["paused"] is False
    after = api.get("/api/v1/market/schedule", headers=AUTH).json()
    assert after["paused"] is False and after["radar_paused"] in (None, True)
    assert (
        api.put("/api/v1/market/schedule", json={"paused": "maybe"}, headers=AUTH).status_code
        == 422
    )
    assert (
        api.put("/api/v1/market/schedule", json={"paused": True}, headers=AUTH).json()["paused"]
        is True
    )


def test_live_schedule_cannot_be_resumed_without_the_terms_gate(isolated_engine: Engine) -> None:
    live = client(isolated_engine, mode="live")
    denied = live.put("/api/v1/market/schedule", json={"paused": False}, headers=AUTH)
    assert denied.status_code == 409
    assert live.get("/api/v1/market/schedule", headers=AUTH).json()["paused"] is True
    allowed = client(isolated_engine, mode="live", market_intel_live_enabled=True)
    assert (
        allowed.put("/api/v1/market/schedule", json={"paused": False}, headers=AUTH).status_code
        == 200
    )
    # Pausing is always allowed, gate or not.
    assert (
        live.put("/api/v1/market/schedule", json={"paused": True}, headers=AUTH).status_code == 200
    )


def test_runs_endpoint_lists_the_latest_scrapes(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    assert api.get("/api/v1/market/runs", headers=AUTH).json()["items"] == []
    api.put("/api/v1/market/schedule", json={"paused": False}, headers=AUTH)
    config = Settings(mode="synthetic")
    assert tick_market(config, isolated_engine, clock=lambda: NOW)["status"] == "succeeded"
    runs = api.get("/api/v1/market/runs?limit=5", headers=AUTH).json()["items"]
    assert len(runs) == 1 and runs[0]["status"] == "succeeded"
    assert runs[0]["stats"]["listings_seen"] == 6 and runs[0]["error_code"] is None
