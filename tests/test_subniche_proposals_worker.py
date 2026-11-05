# tests/test_subniche_proposals_worker.py
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from nicheradar.config import Settings
from nicheradar.subniche_discovery import proposals
from nicheradar.subniche_discovery.intake import ManualFields, add_hypothesis
from nicheradar.subniche_discovery.store import list_hypotheses
from nicheradar.subniche_discovery.worker import tick_proposals
from tests.subniche_samples import NOW, FakeReader
from tests.test_persistence import NOW as LLM_NOW
from tests.test_subniche_intake import client_answering
from tests.test_subniche_propose import GOOD, enabled_settings, seed_policies, seed_run

pytestmark = pytest.mark.postgres

MANUAL = ManualFields(label="History Revenge", family="history", parent=None)


def put(
    engine: Engine, raw: str, key: str, manual: ManualFields | None = None, now: Any = NOW
) -> UUID:
    with engine.begin() as connection:
        request_id, _ = proposals.enqueue(
            connection, raw, manual=manual, origin="manual", key=key, now=now, per_day=100
        )
    return request_id


def get(engine: Engine, request_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = proposals.get_request(connection, request_id)
    assert row is not None
    return row


def hypotheses(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return list_hypotheses(connection)


def test_not_configured_without_database_or_engine() -> None:
    out = tick_proposals(Settings(mode="live"), clock=lambda: NOW)
    assert out["status"] == "not_configured"
    json.dumps(out)


def test_idle_without_requests(isolated_engine: Engine) -> None:
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert out == {
        "service": "subniche_proposals",
        "status": "idle",
        "processed": 0,
        "ready": 0,
        "failed": 0,
    }


def test_manual_request_becomes_ready_and_creates_a_proposed_hypothesis(
    isolated_engine: Engine,
) -> None:
    request_id = put(isolated_engine, "history revenge", "clave-worker-01", MANUAL)
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["status"], out["processed"], out["ready"], out["failed"]) == (
        "processed",
        1,
        1,
        0,
    )
    row = get(isolated_engine, request_id)
    assert (row["status"], row["hypothesis_slug"]) == ("ready", "history_revenge")
    [hypothesis] = hypotheses(isolated_engine)
    assert (hypothesis["slug"], hypothesis["status"]) == ("history_revenge", "proposed")


def test_model_query_request_becomes_ready(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
    request_id = put(isolated_engine, "history revenge", "clave-worker-02", now=LLM_NOW)
    out = tick_proposals(
        enabled_settings(),
        isolated_engine,
        client=client_answering(GOOD),
        clock=lambda: LLM_NOW,
    )
    assert out["ready"] == 1
    row = get(isolated_engine, request_id)
    assert (row["status"], row["hypothesis_slug"]) == ("ready", "history_revenge_stories")


def test_llm_disabled_fails_with_its_code(isolated_engine: Engine) -> None:
    request_id = put(isolated_engine, "history revenge", "clave-worker-03")
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["ready"], out["failed"]) == (0, 1)
    row = get(isolated_engine, request_id)
    assert (row["status"], row["error_code"]) == ("failed", "llm_disabled")
    assert hypotheses(isolated_engine) == []


def test_duplicate_fails_with_a_trimmed_code(isolated_engine: Engine) -> None:
    first = put(isolated_engine, "history revenge", "clave-worker-04", MANUAL)
    second = put(
        isolated_engine,
        "history revenge",
        "clave-worker-05",
        MANUAL,
        now=NOW + timedelta(seconds=1),
    )
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["ready"], out["failed"]) == (1, 1)
    assert get(isolated_engine, first)["status"] == "ready"
    row = get(isolated_engine, second)
    assert row["status"] == "failed" and row["error_code"].startswith("duplicate:")
    assert len(row["error_code"]) <= 80
    assert len(hypotheses(isolated_engine)) == 1


def test_unknown_channel_fails_with_not_found(isolated_engine: Engine) -> None:
    request_id = put(isolated_engine, "@canal_de_prueba", "clave-worker-06")
    out = tick_proposals(
        Settings(mode="live"), isolated_engine, reader=FakeReader(), clock=lambda: NOW
    )
    assert out["failed"] == 1
    assert get(isolated_engine, request_id)["error_code"] == "not_found"


def test_batch_limits_each_round(isolated_engine: Engine) -> None:
    ids = [
        put(
            isolated_engine,
            f"tema numero {n}",
            f"clave-batch-{n:03d}",
            ManualFields(label=f"Tema numero {n}", family="history", parent=None),
            now=NOW + timedelta(seconds=n),
        )
        for n in range(5)
    ]
    first = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW, batch=3)
    assert first["processed"] == 3
    second = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW, batch=3)
    assert second["processed"] == 2
    third = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW, batch=3)
    assert (third["status"], third["processed"]) == ("idle", 0)
    assert all(get(isolated_engine, i)["status"] == "ready" for i in ids)
    assert len(hypotheses(isolated_engine)) == 5


def test_stale_running_request_is_abandoned_without_a_hypothesis(
    isolated_engine: Engine,
) -> None:
    request_id = put(isolated_engine, "history revenge", "clave-worker-07", MANUAL)
    with isolated_engine.begin() as connection:
        assert proposals.claim_next(connection, NOW) is not None
    later = NOW + timedelta(hours=1)
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: later)
    assert out["status"] == "idle"
    row = get(isolated_engine, request_id)
    assert (row["status"], row["error_code"]) == ("failed", "abandoned")
    assert hypotheses(isolated_engine) == []


def test_unexpected_exception_fails_that_request_and_continues(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = put(isolated_engine, "primera consulta", "clave-worker-08", MANUAL)
    fine = put(
        isolated_engine,
        "history revenge",
        "clave-worker-09",
        MANUAL,
        now=NOW + timedelta(seconds=1),
    )
    original = add_hypothesis

    async def flaky(engine: Engine, config: Settings, raw: str, **kwargs: Any) -> dict[str, Any]:
        if raw == "primera consulta":
            raise RuntimeError("boom con detalle del proveedor")
        return await original(engine, config, raw, **kwargs)

    monkeypatch.setattr("nicheradar.subniche_discovery.worker.add_hypothesis", flaky)
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (out["processed"], out["ready"], out["failed"]) == (2, 1, 1)
    assert get(isolated_engine, broken)["error_code"] == "unexpected"
    assert get(isolated_engine, fine)["status"] == "ready"


def test_database_error_is_reported_not_raised(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args: Any, **kwargs: Any) -> int:
        raise OperationalError("select 1", {}, Exception("down"))

    monkeypatch.setattr(proposals, "release_stale", down)
    out = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert out["status"] == "error"
    json.dumps(out)


def test_two_rounds_never_process_a_request_twice(isolated_engine: Engine) -> None:
    put(isolated_engine, "history revenge", "clave-worker-10", MANUAL)
    first = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    second = tick_proposals(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert (first["processed"], second["processed"]) == (1, 0)
    assert len(hypotheses(isolated_engine)) == 1
