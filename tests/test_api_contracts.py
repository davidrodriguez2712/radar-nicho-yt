from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def client_for(engine: Engine, *, mode: str = "synthetic", now: datetime = NOW) -> TestClient:
    client = TestClient(
        create_app(
            Settings.model_validate({"service_token": TOKEN, "mode": mode}),
            engine=engine,
            clock=lambda: now,
        )
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/profile"),
        ("PUT", "/profile"),
        ("GET", "/status"),
        ("PUT", "/radar"),
        ("GET", "/catalog"),
        ("GET", "/providers"),
        ("POST", "/runs"),
        ("GET", "/jobs"),
        ("GET", f"/jobs/{uuid4()}"),
    ],
)
def test_operational_routes_require_auth_before_database(
    method: str, path: str, isolated_engine: Engine
) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    for authorization in (None, "Bearer wrong", "Basic wrong"):
        headers = {"Authorization": authorization} if authorization else {}
        assert client.request(method, "/api/v1" + path, headers=headers).status_code == 401
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(s.creator_profiles)).scalar_one() == 0


def test_manual_concurrent_retry_is_one_job_and_remains_queryable(isolated_engine: Engine) -> None:
    client = client_for(isolated_engine)
    client.put("/api/v1/radar", json={"paused": False})

    def submit() -> dict[str, str]:
        with client_for(isolated_engine) as requester:
            response = requester.post("/api/v1/runs", headers={"Idempotency-Key": "same-request"})
            assert response.status_code == 202
            return response.json()  # type: ignore[no-any-return]

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = list(pool.map(lambda _: submit(), range(2)))
    assert requests[0] == requests[1]
    accepted = requests[0]
    detail = client.get(accepted["status_url"])
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"
    assert detail.json()["completed_stages"] == []
    assert "occurrence_key" not in detail.json()
    assert "lease_owner" not in detail.json()
    assert "checkpoints" not in detail.json()
    client.put("/api/v1/radar", json={"paused": True})
    assert (
        client.post("/api/v1/runs", headers={"Idempotency-Key": "same-request"}).json() == accepted
    )
    assert (
        client.post("/api/v1/runs", headers={"Idempotency-Key": "new-request"}).status_code == 409
    )
    assert client.get(f"/api/v1/jobs/{uuid4()}").status_code == 404
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(s.jobs)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(s.analysis_runs)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(s.provider_requests)).scalar_one() == 0


def test_live_manual_cannot_bypass_persisted_synthetic_unpause(isolated_engine: Engine) -> None:
    synthetic = client_for(isolated_engine)
    synthetic.put("/api/v1/radar", json={"paused": False})
    synthetic.post("/api/v1/runs", headers={"Idempotency-Key": "same-request"})
    live = client_for(isolated_engine, mode="live")
    assert live.post("/api/v1/runs", headers={"Idempotency-Key": "same-request"}).status_code == 409
    assert (
        live.post("/api/v1/runs", headers={"Idempotency-Key": "another-request"}).status_code == 409
    )
    assert synthetic.get("/api/v1/jobs").json()["total"] == 1


def test_jobs_and_provider_policies_paginate_without_overlap(isolated_engine: Engine) -> None:
    client = client_for(isolated_engine)
    client.put("/api/v1/radar", json={"paused": False})
    for index in range(5):
        client.post("/api/v1/runs", headers={"Idempotency-Key": f"request-{index}"})
    with isolated_engine.begin() as db:
        for index in range(5):
            insert_record(
                db,
                "provider_policies",
                {
                    "provider": "fixture",
                    "data_type": "video",
                    "operation": "recent",
                    "usage": "storage",
                    "version": f"v{index}",
                    "status": "pending",
                    "evidence_source": "synthetic test",
                    "effective_at": NOW,
                },
            )
    for endpoint, key in (("jobs", "items"), ("providers", "policies")):
        seen: list[str] = []
        for offset in (0, 2, 4):
            response = client.get(f"/api/v1/{endpoint}?limit=2&offset={offset}")
            assert response.status_code == 200
            page = response.json()
            assert page["total"] == 5
            assert page["limit"] == 2
            assert page["offset"] == offset
            seen.extend(row["id"] for row in page[key])
        assert len(set(seen)) == len(seen) == 5
        assert client.get(f"/api/v1/{endpoint}?offset=5").json()[key] == []
        for query in ("limit=0", "limit=101", "offset=-1", "limit=invalid"):
            assert client.get(f"/api/v1/{endpoint}?{query}").status_code == 422


def test_invalid_values_are_not_echoed_and_do_not_mutate_state(isolated_engine: Engine) -> None:
    client = client_for(isolated_engine)
    secret = "mistakenly-pasted-sensitive-value"
    for method, path, kwargs in (
        ("PUT", "/radar", {"json": {"paused": secret}}),
        ("PUT", "/profile", {"json": {"profile": {"weekly_hours": secret}, "expected_version": 1}}),
        ("POST", "/runs", {"headers": {"Idempotency-Key": secret * 5}}),
        ("GET", "/jobs/" + secret, {}),
    ):
        response = client.request(method, "/api/v1" + path, **kwargs)
        assert response.status_code == 422
        assert secret not in response.text
    assert client.get("/api/v1/status").json()["radar_paused"]
    assert client.get("/api/v1/jobs").json()["total"] == 0
