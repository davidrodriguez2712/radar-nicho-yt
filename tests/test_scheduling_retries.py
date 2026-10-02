import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Connection, Engine, func, select, update

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Batch, Cost, Operation, ProviderError
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.budget import Limits, reserve
from nicheradar.services.gateway import Gateway
from nicheradar.services.requests import mark_sent, prepare_request
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim, create_schedule, enqueue, fail_job, schedule_due
from tests.test_api_contracts import client_for
from tests.test_persistence import NOW, seed_evidence

pytestmark = pytest.mark.postgres


def schedule(db: Connection, *, due: datetime = NOW) -> dict[str, UUID]:
    ids = seed_evidence(db)
    create_schedule(db, ids["profile"], due, {"mode": "synthetic"})
    db.execute(update(s.radar_schedules).values(paused=False))
    return ids


def test_two_schedulers_share_one_occurrence(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        schedule(db, due=NOW - timedelta(days=7))

    def plan() -> list[UUID]:
        with isolated_engine.begin() as db:
            return schedule_due(db, NOW, globally_paused=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: plan(), range(2)))
    assert sorted(map(len, results)) == [0, 1]
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(s.jobs)).scalar_one() == 1
        assert db.execute(select(s.radar_schedules.c.next_due_at)).scalar_one() == NOW + timedelta(
            hours=1
        )


def test_outstanding_work_does_not_accumulate_hourly_catchup_jobs(db: Connection) -> None:
    schedule(db)
    jobs = schedule_due(db, NOW, globally_paused=False)
    for hours in (1, 2, 24, 72):
        assert schedule_due(db, NOW + timedelta(hours=hours), globally_paused=False) == []
    assert db.execute(select(func.count()).select_from(s.jobs)).scalar_one() == 1
    db.execute(update(s.jobs).where(s.jobs.c.id == jobs[0]).values(status="succeeded"))
    assert len(schedule_due(db, NOW + timedelta(hours=73), globally_paused=False)) == 1


def test_lima_and_utc_represent_the_same_due_instant(db: Connection) -> None:
    lima = datetime(2026, 9, 14, 0, tzinfo=ZoneInfo("America/Lima"))
    schedule(db, due=lima)
    assert not schedule_due(db, lima - timedelta(microseconds=1), globally_paused=False)
    assert len(schedule_due(db, lima.astimezone(UTC), globally_paused=False)) == 1
    assert not schedule_due(db, lima, globally_paused=False)
    assert db.execute(select(s.radar_schedules.c.next_due_at)).scalar_one() == datetime(
        2026, 9, 14, 6, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="aware"):
        schedule_due(db, lima.replace(tzinfo=None))


@pytest.mark.parametrize(
    "code", ["authentication_required", "quota", "unknown_charge", "policy_pending"]
)
def test_attention_errors_never_retry_even_if_flagged_safe(db: Connection, code: str) -> None:
    schedule(db)
    [job] = schedule_due(db, NOW, globally_paused=False)
    assert claim(db, "worker", NOW)
    fail_job(db, job, "worker", NOW, ProviderError(code, retry_safe=True))
    assert claim(db, "worker", NOW + timedelta(days=2)) is None
    assert schedule_due(db, NOW + timedelta(days=2), globally_paused=False) == []
    # An explicit reactivation after fixing the cause permits a later occurrence.
    db.execute(
        update(s.radar_schedules).values(
            configuration={
                "mode": "synthetic",
                "retry_authorized_after": (NOW + timedelta(days=2)).isoformat(),
            }
        )
    )
    assert len(schedule_due(db, NOW + timedelta(days=3), globally_paused=False)) == 1


def test_backoff_timing_and_terminal_failure_free_next_job(db: Connection) -> None:
    ids = seed_evidence(db)
    job = enqueue(db, ids["profile"], "safe-retry", NOW, {})
    now = NOW
    for index in range(3):
        claimed = claim(db, "worker", now)
        assert claimed and claimed["attempts"] == index + 1
        fail_job(
            db, job, "worker", now, ProviderError("connect", retry_safe=True), jitter_seconds=7
        )
        if index < 2:
            next_at = now + timedelta(seconds=30 * 2**index + 7)
            assert db.execute(select(s.jobs.c.available_at)).scalar_one() == next_at
            assert claim(db, "early", next_at - timedelta(microseconds=1)) is None
            now = next_at
    assert claim(db, "worker", now + timedelta(days=1)) is None
    other = enqueue(db, ids["profile"], "other-work", now, {})
    next_job = claim(db, "worker", now)
    assert next_job and next_job["id"] == other


def test_repeated_process_deaths_exhaust_attempts_without_losing_liability(db: Connection) -> None:
    ids = seed_evidence(db)
    job_id = enqueue(db, ids["profile"], "crash-loop", NOW, {})
    run_id = db.execute(select(s.jobs.c.run_id).where(s.jobs.c.id == job_id)).scalar_one()
    for index in range(3):
        assert claim(db, f"worker-{index}", NOW + timedelta(seconds=31 * index), lease_seconds=30)
    request = prepare_request(
        db, run_id, "synthetic", Operation.CHANNEL_SEARCH, "scope", "key", "sent-intent", NOW
    )
    free = Cost(unit="USD", maximum=Decimal(0), source="fixture")
    caps = {"USD": Limits(operation=Decimal(0), run=Decimal(0), week=Decimal(0), period=Decimal(0))}
    reserve(db, request, ids["profile"], (free,), caps, NOW)
    mark_sent(db, request, NOW)
    prepared = prepare_request(
        db, run_id, "synthetic", Operation.CHANNEL_SEARCH, "scope", "other", "never-sent", NOW
    )
    reserve(db, prepared, ids["profile"], (free,), caps, NOW)
    assert claim(db, "fourth", NOW + timedelta(seconds=94)) is None
    assert db.execute(select(s.jobs.c.error_code)).scalar_one() == "attempts_exhausted"
    states = {
        row.id: row.state
        for row in db.execute(select(s.provider_requests.c.id, s.provider_requests.c.state))
    }
    assert states[request] == "unknown_charge"
    assert states[prepared] == "released"


class FailingTransport(SyntheticProvider):
    def __init__(self, *, certified: bool, persistent: bool = False):
        super().__init__()
        self.certified, self.persistent = certified, persistent

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if self.calls == 0 or self.persistent:
            self.calls += 1
            raise ProviderError("connection_failed", retry_safe=True, not_sent=self.certified)
        return await super().fetch(operation, parameters, now)


@pytest.mark.parametrize("certified", [True, False])
def test_gateway_requires_explicit_unsent_proof_for_retry(
    isolated_engine: Engine, certified: bool
) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
    provider = FailingTransport(certified=certified)
    gateway = Gateway(
        isolated_engine, provider, ids["profile"], ids["run"], "test", CreatorProfile(), {}, {}
    )
    with pytest.raises(ProviderError):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW))
    with isolated_engine.connect() as db:
        state = db.execute(
            select(s.provider_requests.c.state).where(
                s.provider_requests.c.auth_scope == "test",
                s.provider_requests.c.cache_key != "a" * 64,
            )
        ).scalar_one()
        assert state == ("released" if certified else "unknown_charge")
    if certified:
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW))
        assert provider.calls == 2
    else:
        with pytest.raises(ProviderError, match="unknown_charge"):
            asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW))
        assert provider.calls == 1


def test_pipeline_retries_certified_transport_error_then_continues(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        job = enqueue(db, ids["profile"], "pipeline-retry", NOW, {})
        assert claim(db, "first", NOW)
    provider = FailingTransport(certified=True)
    asyncio.run(
        Pipeline(isolated_engine, provider=provider, clock=lambda: NOW).process(job, "first")
    )
    later = NOW + timedelta(minutes=2)
    with isolated_engine.begin() as db:
        assert claim(db, "second", later)
    asyncio.run(
        Pipeline(isolated_engine, provider=provider, clock=lambda: later).process(job, "second")
    )
    with isolated_engine.connect() as db:
        row = db.execute(select(s.jobs).where(s.jobs.c.id == job)).mappings().one()
        assert row["status"] == "succeeded"
        assert row["attempts"] == 2
        assert row["error_code"] is None


def test_stale_pipeline_owner_exits_without_overwriting_current_owner(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        job = enqueue(db, ids["profile"], "stale", NOW, {})
        assert claim(db, "old", NOW, lease_seconds=1)
        assert claim(db, "new", NOW + timedelta(seconds=2))
    provider = SyntheticProvider()
    asyncio.run(
        Pipeline(
            isolated_engine, provider=provider, clock=lambda: NOW + timedelta(seconds=2)
        ).process(job, "old")
    )
    assert provider.calls == 0
    with isolated_engine.connect() as db:
        row = db.execute(select(s.jobs).where(s.jobs.c.id == job)).mappings().one()
        assert row["lease_owner"] == "new"
        assert row["status"] == "running"


class MeteredFixture(SyntheticProvider):
    name = "metered-fixture"

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        batch = await super().fetch(operation, parameters, now)
        return batch.model_copy(
            update={
                "costs": (
                    Cost(
                        unit="USD",
                        maximum=Decimal(1),
                        actual=Decimal(1),
                        source="invented test cost",
                    ),
                )
            }
        )


@pytest.mark.parametrize("scheduled", [True, False])
def test_manual_and_scheduled_gateway_apply_identical_money_limits(
    isolated_engine: Engine, scheduled: bool
) -> None:
    profile = CreatorProfile(
        paid_limits_confirmed=True,
        radar_usd_per_operation=Decimal(1),
        radar_usd_per_run=Decimal(1),
        radar_usd_per_week=Decimal(10),
        radar_usd_per_month=Decimal(10),
    )
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        db.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == ids["profile"])
            .values(configuration=profile.model_dump(mode="json"))
        )
        for usage in ("query", "storage", "history", "scheduled"):
            insert_record(
                db,
                "provider_policies",
                {
                    "provider": MeteredFixture.name,
                    "operation": "*",
                    "data_type": "metadata",
                    "usage": usage,
                    "version": "fixture",
                    "status": "enabled",
                    "evidence_source": "own fixture only",
                    "effective_at": NOW,
                    "retention_seconds": 3600,
                },
            )
    cost = Cost(unit="USD", maximum=Decimal(1), source="invented test cost")
    caps = {
        "USD": Limits(operation=Decimal(1), run=Decimal(1), week=Decimal(10), period=Decimal(10))
    }
    provider = MeteredFixture()
    gateway = Gateway(
        isolated_engine,
        provider,
        ids["profile"],
        ids["run"],
        "test",
        profile,
        caps,
        {Operation.CHANNEL_SEARCH: (cost,)},
        scheduled=scheduled,
    )
    asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW))
    with pytest.raises(ProviderError, match="run_budget_exhausted"):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "second"}, NOW))
    assert provider.calls == 1
    with isolated_engine.connect() as db:
        assert db.execute(select(func.sum(s.cost_ledger.c.amount))).scalar_one() == 1


def test_attention_is_visible_and_api_resume_permits_later_occurrence(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as db:
        schedule(db)
        [job] = schedule_due(db, NOW, globally_paused=False)
        assert claim(db, "worker", NOW)
        fail_job(db, job, "worker", NOW, ProviderError("authentication_required"))
    client = client_for(isolated_engine, now=NOW + timedelta(microseconds=1))
    assert client.get("/api/v1/status").json()["scheduler_attention_job_id"] == str(job)
    client.put("/api/v1/radar", json={"paused": True})
    client.put("/api/v1/radar", json={"paused": False})
    assert client.get("/api/v1/status").json()["scheduler_attention_job_id"] is None


def test_persistent_certified_failure_stops_at_limit(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        job = enqueue(db, ids["profile"], "persistent", NOW, {})
    provider = FailingTransport(certified=True, persistent=True)
    for index in range(3):
        instant = NOW + timedelta(minutes=2 * index)
        with isolated_engine.begin() as db:
            assert claim(db, "worker", instant)

        def clock(value: datetime = instant) -> datetime:
            return value

        asyncio.run(
            Pipeline(isolated_engine, provider=provider, clock=clock).process(job, "worker")
        )
    with isolated_engine.begin() as db:
        assert claim(db, "worker", NOW + timedelta(days=1)) is None
        assert db.execute(select(s.jobs.c.status)).scalar_one() == "failed"
        assert set(db.execute(select(s.cost_reservations.c.status)).scalars()) == {"released"}
    assert provider.calls == 3
