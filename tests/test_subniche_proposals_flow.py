# tests/test_subniche_proposals_flow.py
"""Recorrido completo: API encola, el worker prepara, la API aprueba."""

from typing import Any

import pytest
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.subniche_api import MESSAGES
from nicheradar.subniche_discovery.worker import tick_proposals
from tests.subniche_samples import NOW
from tests.test_market_api import AUTH, client
from tests.test_persistence import NOW as LLM_NOW
from tests.test_subniche_intake import client_answering
from tests.test_subniche_propose import GOOD, enabled_settings, seed_policies, seed_run

pytestmark = pytest.mark.postgres
BASE = "/api/v1/subniches"


def propose(api: Any, body: dict[str, Any], key: str) -> str:
    response = api.post(f"{BASE}/proposals", json=body, headers=AUTH | {"Idempotency-Key": key})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    return str(response.json()["id"])


def status_of(api: Any, request_id: str) -> dict[str, Any]:
    response = api.get(f"{BASE}/proposals/{request_id}", headers=AUTH)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def active_slugs(api: Any) -> list[str]:
    items = api.get(BASE, headers=AUTH).json()["items"]
    return [item["slug"] for item in items if item["status"] == "active"]


def test_manual_proposal_flows_from_request_to_active(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    request_id = propose(
        api,
        {
            "input": "history revenge",
            "manual": {"label": "History Revenge", "family": "history"},
        },
        "clave-flujo-0001",
    )
    assert status_of(api, request_id)["status"] == "queued"
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["processed"], out["ready"], out["failed"]) == (1, 1, 0)

    ready = status_of(api, request_id)
    assert ready["status"] == "ready" and ready["error"] is None
    assert ready["hypothesis"]["slug"] == "history_revenge"
    assert ready["hypothesis"]["status"] == "proposed"
    assert active_slugs(api) == []

    preview = api.get(f"{BASE}/history_revenge/approval", headers=AUTH)
    assert preview.status_code == 200 and preview.json()["status"] == "proposed"

    approved = api.post(f"{BASE}/history_revenge/approve", headers=AUTH)
    assert approved.status_code == 200
    assert approved.json() == {"slug": "history_revenge", "status": "active"}
    assert active_slugs(api) == ["history_revenge"]
    assert status_of(api, request_id)["hypothesis"]["status"] == "active"


def test_query_proposal_with_the_fake_model_flows_to_active(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
    api = client(isolated_engine)
    request_id = propose(api, {"input": "history revenge"}, "clave-flujo-0002")
    out = tick_proposals(
        enabled_settings(),
        isolated_engine,
        client=client_answering(GOOD),
        clock=lambda: LLM_NOW,
    )
    assert out["ready"] == 1
    ready = status_of(api, request_id)
    assert ready["status"] == "ready"
    assert ready["hypothesis"]["slug"] == "history_revenge_stories"
    assert ready["hypothesis"]["queries"] == GOOD["queries"]
    assert api.post(f"{BASE}/history_revenge_stories/approve", headers=AUTH).status_code == 200
    assert active_slugs(api) == ["history_revenge_stories"]


def test_failed_request_has_a_fixed_message_and_no_hypothesis(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    request_id = propose(api, {"input": "history revenge"}, "clave-flujo-0003")
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["ready"], out["failed"]) == (0, 1)
    failed = status_of(api, request_id)
    assert failed["status"] == "failed"
    assert failed["error"] == {"code": "llm_disabled", "message": MESSAGES["llm_disabled"]}
    assert failed["hypothesis"] is None
    assert api.get(BASE, params={"include_inactive": "true"}, headers=AUTH).json()["items"] == []
