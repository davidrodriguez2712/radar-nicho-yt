"""Fault injection against the actual queue/gateway/pipeline and isolated PostgreSQL.

All provider payloads and dollar costs are invented. No live integration is enabled.
"""

import asyncio
import multiprocessing
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from pydantic_settings import SettingsConfigDict
from sqlalchemy import Connection, Engine, create_engine, event, func, select, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.discovery.queries import collect
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Batch, Cost, Operation, ProviderError
from nicheradar.integrations.retention import expire
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.schema import discovery_cursors, ranking_snapshots
from nicheradar.services.budget import Limits
from nicheradar.services.console import consumption
from nicheradar.services.gateway import Gateway
from nicheradar.workers import main as worker_module
from nicheradar.workers import pipeline as pipeline_module
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim, create_schedule, enqueue, owned_job
from tests.test_persistence import NOW
from tests.test_scheduling_retries import MeteredFixture

pytestmark = pytest.mark.postgres
CAPS = {
    "USD": Limits(operation=Decimal(1), run=Decimal(100), week=Decimal(100), period=Decimal(100))
}
TARIFFS: dict[Operation, tuple[Cost, ...]] = {
    operation: (Cost(unit="USD", maximum=Decimal(1), source="invented fixture"),)
    for operation in Operation
}


class ProcessDeath(BaseException):
    """Skip ordinary error handlers to model interruption, not a retryable exception."""


class RecordingFixture(MeteredFixture):
    def __init__(self, failure: str | None = None) -> None:
        super().__init__()
        self.received: list[tuple[Operation, dict[str, Any]]] = []
        self.failure = failure

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        self.received.append((operation, dict(parameters)))
        if self.failure:
            self.calls += 1
            if self.failure == "cancelled":
                raise asyncio.CancelledError()
            raise ProviderError(self.failure, may_have_charged=True)
        return await super().fetch(operation, parameters, now)


class MeteredPipeline(Pipeline):
    """Test-only wiring: normal production checks, but an invented priced transport."""

    async def query(
        self,
        job: dict[str, Any],
        profile_id: UUID,
        profile: CreatorProfile,
        owner: str,
        *,
        scheduled: bool = False,
    ) -> None:
        gateway = Gateway(
            self.engine,
            self.provider,
            profile_id,
            job["run_id"],
            "synthetic",
            profile,
            CAPS,
            TARIFFS,
            scheduled=scheduled,
            maximum_calls=self.maximum_calls,
        )
        await collect(self.engine, gateway, job, owner, profile, self.clock, self.maximum_calls)


def setup_run(engine: Engine, *, run_cap: int = 30) -> tuple[UUID, UUID, UUID]:
    profile = CreatorProfile(
        paid_limits_confirmed=True,
        radar_usd_per_operation=Decimal(1),
        radar_usd_per_run=Decimal(run_cap),
        radar_usd_per_week=Decimal(100),
        radar_usd_per_month=Decimal(100),
    )
    with engine.begin() as db:
        profile_id = seed_profile(db, profile, initial_catalog())
        for usage in ("query", "storage", "history", "derived", "scheduled"):
            db.execute(
                s.provider_policies.insert().values(
                    provider=MeteredFixture.name,
                    operation="*",
                    data_type="metadata",
                    usage=usage,
                    version="invented-only",
                    status="enabled",
                    evidence_source="own test fixtures",
                    effective_at=NOW,
                    retention_seconds=7 * 86400,
                )
            )
        job = enqueue(db, profile_id, "fault-test", NOW, {})
        run = db.execute(select(s.jobs.c.run_id).where(s.jobs.c.id == job)).scalar_one()
    return profile_id, job, run


def take(engine: Engine, owner: str, when: datetime = NOW) -> dict[str, Any]:
    with engine.begin() as db:
        result = claim(db, owner, when)
    assert result is not None
    return result


def run_pipeline(
    engine: Engine, job: UUID, owner: str, provider: RecordingFixture, when: datetime = NOW
) -> None:
    asyncio.run(
        MeteredPipeline(
            engine, provider=provider, clock=lambda: when, settings=fixture_settings()
        ).process(job, owner)
    )


class FixtureSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


def fixture_settings() -> Settings:
    return FixtureSettings(
        mode="synthetic",
        llm_enabled=False,
        llm_api_key=None,
        llm_configuration=None,
        embedding_model_directory=None,
        embedding_model_version=None,
    )


def crashing_child(url: URL, schema: str, job: UUID) -> None:
    """Spawned test worker: no finalizers run after the normalization commit."""
    assert re.fullmatch(r"nrtest_[0-9a-f]{32}", schema)
    engine = create_engine(
        url,
        hide_parameters=True,
        connect_args={
            "options": f"-c search_path={schema} -c timezone=UTC -c statement_timeout=5000"
        },
    )

    def terminate(
        connection: Connection, job_id: UUID, owner: str, now: datetime
    ) -> dict[str, Any]:
        row = owned_job(connection, job_id, owner, now)
        if row["stage"] == "cohort":
            os._exit(78)
        return row

    pytest.MonkeyPatch().setattr(pipeline_module, "owned_job", terminate)
    run_pipeline(engine, job, "old", RecordingFixture())


def test_abrupt_child_process_exit_recovers_only_from_postgres(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job, run = setup_run(isolated_engine)
    take(isolated_engine, "old")
    with isolated_engine.connect() as db:
        schema = db.execute(select(func.current_schema())).scalar_one()
    child = multiprocessing.get_context("spawn").Process(
        target=crashing_child, args=(isolated_engine.url, schema, job)
    )
    # Streamlit's AppTest can leave its script as __main__. The child only needs this
    # importable test target, never a replay of a dashboard script or pytest entrypoint.
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "__main__", ModuleType("__main__"))
        child.start()
    try:
        child.join(timeout=20)
        assert not child.is_alive(), "isolated worker did not reach its crash checkpoint"
        assert child.exitcode == 78
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        child.close()
    with isolated_engine.connect() as db:
        assert db.execute(select(s.jobs.c.stage)).scalar_one() == "cohort"
        calls = db.execute(select(func.count()).select_from(s.provider_requests)).scalar_one()
        assert calls > 0
    later = NOW + timedelta(minutes=3)
    take(isolated_engine, "replacement", later)
    provider = RecordingFixture()
    run_pipeline(isolated_engine, job, "replacement", provider, later)
    assert provider.calls == 0
    with isolated_engine.connect() as db:
        assert_success_once(db, job, run, calls)


@pytest.mark.parametrize("after_query", [False, True])
def test_worker_database_error_does_not_report_false_zero_or_exception_details(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch, after_query: bool
) -> None:
    profile, _, _ = setup_run(isolated_engine)
    with isolated_engine.begin() as db:
        create_schedule(db, profile, NOW, {})
        db.execute(
            update(s.radar_schedules).values(paused=False, next_due_at=NOW + timedelta(days=30))
        )

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "FixedDatetime":
            return cls.fromtimestamp(NOW.timestamp(), tz=NOW.tzinfo)

    provider = RecordingFixture()

    def pipeline_factory(engine: Engine, **kwargs: Any) -> Pipeline:
        return MeteredPipeline(engine, provider=provider, clock=lambda: NOW, **kwargs)

    def fail(connection: Connection, job_id: UUID, owner: str, now: datetime) -> dict[str, Any]:
        row = owned_job(connection, job_id, owner, now)
        if row["stage"] == ("normalization" if after_query else "planning"):
            raise SQLAlchemyError("sensitive-driver-detail")
        return row

    monkeypatch.setattr(worker_module, "datetime", FixedDatetime)
    monkeypatch.setattr(worker_module, "Pipeline", pipeline_factory)
    monkeypatch.setattr(pipeline_module, "owned_job", fail)
    status = worker_module.tick(fixture_settings(), isolated_engine)
    assert status["status"] == "error"
    assert status["error_code"] == "database_unavailable"
    assert "sensitive-driver-detail" not in str(status)
    assert provider.calls > 0 if after_query else provider.calls == 0
    assert status["provider_calls"] == provider.calls


def stop_before_stage(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    def intercept(
        connection: Connection, job_id: UUID, owner: str, now: datetime
    ) -> dict[str, Any]:
        row = owned_job(connection, job_id, owner, now)
        if row["stage"] == stage:
            raise ProcessDeath()
        return row

    monkeypatch.setattr(pipeline_module, "owned_job", intercept)


def assert_success_once(db: Connection, job: UUID, run: UUID, calls: int) -> None:
    row = db.execute(select(s.jobs).where(s.jobs.c.id == job)).mappings().one()
    assert row["status"] == "succeeded"
    assert row["attempts"] == 2
    requests = (
        db.execute(select(s.provider_requests).where(s.provider_requests.c.run_id == run))
        .mappings()
        .all()
    )
    assert len(requests) == calls
    assert {request["state"] for request in requests} == {"completed"}
    assert len({request["cache_key"] for request in requests}) == calls
    assert db.execute(select(func.sum(s.cost_ledger.c.amount))).scalar_one() == calls
    assert db.execute(select(func.count()).select_from(ranking_snapshots)).scalar_one() == 1
    assert set(db.execute(select(s.opportunities.c.format)).scalars()) == {"shorts", "long"}
    assert set(db.execute(select(s.evaluation_versions.c.version)).scalars()) == {1}


@pytest.mark.parametrize(
    "stage", ["query", "normalization", "cohort", "metrics", "evaluation", "backlog"]
)
def test_restart_from_every_committed_stage_without_duplicate_spend(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    _, job, run = setup_run(isolated_engine)
    take(isolated_engine, "old")
    first = RecordingFixture()
    with monkeypatch.context() as patch:
        stop_before_stage(patch, stage)
        with pytest.raises(ProcessDeath):
            run_pipeline(isolated_engine, job, "old", first)
    with isolated_engine.connect() as db:
        assert db.execute(select(s.jobs.c.stage)).scalar_one() == stage
    # Close pooled sessions; a new pipeline/provider must rely on durable state, not memory.
    isolated_engine.dispose()
    later = NOW + timedelta(minutes=3)
    assert take(isolated_engine, "replacement", later)["id"] == job
    replacement = RecordingFixture()
    run_pipeline(isolated_engine, job, "replacement", replacement, later)
    if stage != "query":
        assert replacement.calls == 0
    with isolated_engine.connect() as db:
        assert_success_once(db, job, run, first.calls + replacement.calls)


def test_crash_after_paid_result_before_query_receipt_reuses_persisted_response(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nicheradar.discovery import queries

    _, job, run = setup_run(isolated_engine)
    take(isolated_engine, "old")
    first = RecordingFixture()

    def crash(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ProcessDeath()

    with monkeypatch.context() as patch:
        patch.setattr(queries, "owned_job", crash)
        with pytest.raises(ProcessDeath):
            run_pipeline(isolated_engine, job, "old", first)
    assert first.calls == 1
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(s.raw_observations)).scalar_one() == 1
        checkpoints = db.execute(select(s.jobs.c.checkpoints)).scalar_one()
        assert "query_receipts_v2" not in checkpoints
        assert db.execute(select(s.provider_requests.c.state)).scalar_one() == "completed"
    later = NOW + timedelta(minutes=3)
    take(isolated_engine, "replacement", later)
    second = RecordingFixture()
    run_pipeline(isolated_engine, job, "replacement", second, later)
    assert first.received[0] not in second.received
    with isolated_engine.connect() as db:
        assert_success_once(db, job, run, first.calls + second.calls)


def test_database_connection_dies_after_provider_response_before_commit(
    isolated_engine: Engine,
) -> None:
    profile, job, run = setup_run(isolated_engine)
    take(isolated_engine, "old")
    provider = RecordingFixture()
    cut = False

    def sever(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        nonlocal cut
        if not cut and statement.startswith("INSERT INTO raw_observations"):
            cut = True
            # Exact backend of this test connection only, in the temporary PostgreSQL instance.
            driver = connection.connection.driver_connection
            assert driver is not None
            pid = driver.info.backend_pid
            with isolated_engine.connect() as control:
                assert control.execute(select(func.pg_terminate_backend(pid))).scalar_one()

    event.listen(isolated_engine, "before_cursor_execute", sever)
    try:
        with pytest.raises(SQLAlchemyError):
            run_pipeline(isolated_engine, job, "old", provider)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", sever)
    assert cut and provider.calls == 1
    with isolated_engine.connect() as db:
        assert db.execute(select(s.provider_requests.c.state)).scalar_one() == "sent"
        assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "reserved"
        assert not db.execute(select(s.raw_observations)).all()
        assert not db.execute(select(s.cost_ledger)).all()
    later = NOW + timedelta(minutes=3)
    take(isolated_engine, "replacement", later)
    second = RecordingFixture()
    run_pipeline(isolated_engine, job, "replacement", second, later)
    assert second.calls == 0
    with isolated_engine.connect() as db:
        row = db.execute(select(s.jobs)).mappings().one()
        assert row["status"] == "deferred" and row["error_code"] == "unknown_charge"
        assert db.execute(select(s.provider_requests.c.state)).scalar_one() == "unknown_charge"
        report = consumption(db, later)
        assert report["reservations"] == [
            {"unit": "USD", "status": "unknown_charge", "amount": Decimal(1)}
        ]
    # A fresh gateway cannot evade the unresolved request, even under a new run ID.
    with isolated_engine.begin() as db:
        another = enqueue(db, profile, "other-run", later, {})
        next_run = db.execute(select(s.jobs.c.run_id).where(s.jobs.c.id == another)).scalar_one()
        configuration = CreatorProfile.model_validate(
            db.execute(select(s.creator_profiles.c.configuration)).scalar_one()
        )
    gateway = Gateway(
        isolated_engine, second, profile, next_run, "synthetic", configuration, CAPS, TARIFFS
    )
    operation, parameters = provider.received[0]
    with pytest.raises(ProviderError, match="unknown_charge"):
        asyncio.run(gateway.fetch(operation, parameters, later))
    assert second.calls == 0


@pytest.mark.parametrize("failure", ["timeout", "cancelled"])
def test_uncertain_transport_or_cancellation_never_repeats_paid_operation(
    isolated_engine: Engine, failure: str
) -> None:
    _, job, _ = setup_run(isolated_engine)
    take(isolated_engine, "old")
    provider = RecordingFixture(failure)
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            run_pipeline(isolated_engine, job, "old", provider)
        take(isolated_engine, "replacement", NOW + timedelta(minutes=3))
        replacement = RecordingFixture()
        run_pipeline(isolated_engine, job, "replacement", replacement, NOW + timedelta(minutes=3))
        assert replacement.calls == 0
    else:
        run_pipeline(isolated_engine, job, "old", provider)
    assert provider.calls == 1
    with isolated_engine.begin() as db:
        assert db.execute(select(s.jobs.c.status)).scalar_one() == "deferred"
        assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "unknown_charge"
        assert claim(db, "unattended", NOW + timedelta(days=2)) is None


@pytest.mark.parametrize("cap", [0, 5])
def test_budget_exhaustion_preserves_partial_coverage_without_extra_calls(
    isolated_engine: Engine, cap: int
) -> None:
    _, job, run = setup_run(isolated_engine, run_cap=cap)
    take(isolated_engine, "worker")
    provider = RecordingFixture()
    run_pipeline(isolated_engine, job, "worker", provider)
    assert provider.calls == cap
    with isolated_engine.connect() as db:
        row = (
            db.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == run)).mappings().one()
        )
        assert row["status"] == "partial"
        assert row["coverage"]["complete"] is False
        assert row["coverage"]["pending_reason"] == "run_budget_exhausted"
        assert db.execute(select(func.count()).select_from(s.provider_requests)).scalar_one() == cap
        assert (
            db.execute(select(func.coalesce(func.sum(s.cost_ledger.c.amount), 0))).scalar_one()
            == cap
        )
        assert not db.execute(
            select(discovery_cursors.c.completed_at).where(
                discovery_cursors.c.completed_at.is_not(None)
            )
        ).all()


@pytest.mark.parametrize("stage", ["normalization", "evaluation", "backlog"])
def test_expired_evidence_during_downtime_never_reappears_or_triggers_requery(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    _, job, _ = setup_run(isolated_engine)
    take(isolated_engine, "old")
    first = RecordingFixture()
    with monkeypatch.context() as patch:
        stop_before_stage(patch, stage)
        with pytest.raises(ProcessDeath):
            run_pipeline(isolated_engine, job, "old", first)
    later = NOW + timedelta(days=8)
    with isolated_engine.begin() as db:
        expire(db, later)
        assert claim(db, "replacement", later)
    replacement = RecordingFixture()
    run_pipeline(isolated_engine, job, "replacement", replacement, later)
    assert replacement.calls == 0
    with isolated_engine.connect() as db:
        assert db.execute(select(s.jobs.c.error_code)).scalar_one() == "evidence_expired"
        assert not db.execute(select(s.raw_observations)).all()
        assert not db.execute(
            select(s.evaluation_versions.c.id).where(s.evaluation_versions.c.expired_at.is_(None))
        ).all()
        assert not db.execute(select(ranking_snapshots)).all()


def test_two_workers_race_to_recover_one_paid_pipeline(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job, run = setup_run(isolated_engine)
    take(isolated_engine, "old")
    first = RecordingFixture()
    with monkeypatch.context() as patch:
        stop_before_stage(patch, "normalization")
        with pytest.raises(ProcessDeath):
            run_pipeline(isolated_engine, job, "old", first)
    later = NOW + timedelta(minutes=3)

    def recover(owner: str) -> int:
        with isolated_engine.begin() as db:
            claimed = claim(db, owner, later)
        if claimed is None:
            return 0
        provider = RecordingFixture()
        run_pipeline(isolated_engine, job, owner, provider, later)
        assert provider.calls == 0
        return 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, ["first-replacement", "second-replacement"]))
    assert sorted(results) == [0, 1]
    with isolated_engine.connect() as db:
        assert_success_once(db, job, run, first.calls)
