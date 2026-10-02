import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.workers.main import tick
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim
from tests.test_evaluation import fixture_scenario
from tests.test_foundation import TOKEN

pytestmark = pytest.mark.postgres


def test_private_api_async_jobs_decisions_and_scenarios(isolated_engine: Engine) -> None:
    config = Settings(service_token=SecretStr(TOKEN))
    client = TestClient(create_app(config, engine=isolated_engine))
    assert client.get("/api/v1/opportunities").status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert client.get("/api/v1/status").json()["radar_paused"]
    assert client.get("/api/v1/opportunities").json()["items"] == []
    assert (
        client.post("/api/v1/runs", headers={"Idempotency-Key": "fixture-run"}).status_code == 409
    )
    assert client.put("/api/v1/radar", json={"paused": False}).status_code == 200
    request = client.post("/api/v1/runs", headers={"Idempotency-Key": "fixture-run"})
    assert request.status_code == 202
    assert (
        client.post("/api/v1/runs", headers={"Idempotency-Key": "fixture-run"}).json()
        == request.json()
    )
    assert client.get("/api/v1/opportunities?limit=101").status_code == 422
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    with isolated_engine.begin() as connection:
        job = claim(connection, "api-test", now)
        assert job is not None
    asyncio.run(Pipeline(isolated_engine, clock=lambda: now).process(job["id"], "api-test"))
    backlog = client.get("/api/v1/opportunities").json()
    assert backlog["total"] == 2
    run = client.get("/api/v1/jobs").json()["items"][0]
    assert run["source_mode"] == "synthetic"
    assert run["coverage"]["work_kind"] == "catalog"
    assert run["coverage"]["complete"] is True
    assert run["coverage"]["catalog_pending"]
    assert all(item["source_mode"] == "synthetic" for item in backlog["items"])
    opportunity = backlog["items"][0]["id"]
    assert client.get("/api/v1/opportunities?format=shorts").json()["total"] == 1
    payload = {"state": "dismissed", "note": "Personal review", "expected_version": 0}
    assert (
        client.post(f"/api/v1/opportunities/{opportunity}/decisions", json=payload).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/opportunities/{opportunity}/decisions", json=payload).status_code
        == 409
    )
    assert client.get("/api/v1/opportunities?state=dismissed").json()["total"] == 1
    detail = client.get(f"/api/v1/opportunities/{opportunity}").json()
    assert detail["decision"]["note"] == "Personal review"
    assert detail["evaluations"][0]["source_mode"] == "synthetic"
    assert detail["evidence"][0]["payload"]["provenance"]["synthetic"]
    before = client.get("/api/v1/consumption").json()
    scenario = client.post("/api/v1/scenarios", json=fixture_scenario().model_dump(mode="json"))
    assert scenario.status_code == 201
    assert scenario.json()["result"]["status"] == "viable"
    assert client.get("/api/v1/consumption").json() == before
    assert len(client.get("/api/v1/scenarios").json()["items"]) == 1


def test_worker_honors_persisted_pause_without_dashboard(isolated_engine: Engine) -> None:
    config = Settings()
    assert tick(config, isolated_engine)["status"] == "paused"
    with isolated_engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(s.jobs)).scalar_one() == 0
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    client.put("/api/v1/radar", json={"paused": False})
    assert tick(config, isolated_engine)["status"] == "succeeded"
    assert tick(config, isolated_engine)["status"] == "idle"
    client.put("/api/v1/radar", json={"paused": True})
    assert tick(config, isolated_engine)["status"] == "paused"


def test_profile_optimistic_edit_and_live_mode_block(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    profile = client.get("/api/v1/profile").json()
    version = profile.pop("version_number")
    profile["weekly_hours"] = "18"
    payload = {"profile": profile, "expected_version": version}
    assert client.put("/api/v1/profile", json=payload).status_code == 200
    assert client.put("/api/v1/profile", json=payload).status_code == 409
    assert client.get("/api/v1/profile").json()["weekly_hours"] == "18"
    live = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN), mode="live"), engine=isolated_engine)
    )
    live.headers["Authorization"] = f"Bearer {TOKEN}"
    assert live.put("/api/v1/radar", json={"paused": False}).status_code == 409
