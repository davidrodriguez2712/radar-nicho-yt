import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine, select

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.integrations.contracts import Batch, Operation, ProviderError
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import channel_analyses
from nicheradar.scoring.advertising import AdvertisingBenchmark
from nicheradar.workers.channel_analysis_queue import CHANNEL_ANALYSIS_STAGES
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_channel_analysis_run_completes_through_every_stage(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        benchmark = AdvertisingBenchmark(
            version="2026-10-02",
            source="owner_declared_estimate",
            origin="manual_assumption",
            format=VideoFormat.LONG,
            language="es",
            audience_key="general",
            unit="usd_ads_per_1000_views",
            rate=EstimateRange(low=Decimal("1.0"), high=Decimal("3.0")),
            revenue_scope="youtube_ads_only_after_revenue_share",
            assumptions="Prueba.",
            observed_at=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=180),
        )
        profile_id = seed_profile(
            connection,
            CreatorProfile(
                paid_limits_confirmed=True,
                # channel_analysis_advertising is stored raw (dict[str, Any] | None,
                # per Task 5); the pipeline re-validates it into a real
                # AdvertisingBenchmark, so it must be seeded as its JSON-mode dump,
                # not the model instance itself.
                channel_analysis_advertising=benchmark.model_dump(mode="json"),
            ),
            initial_catalog(),
        )
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": "synthetic",
                "trigger": "channel_analysis",
                "status": "running",
                "configuration": {"channel_input": "@scienceexplained"},
            },
        )
        job_id = insert_record(
            connection,
            "jobs",
            {
                "run_id": run_id,
                "occurrence_key": "test-ca-pipeline-1",
                "status": "queued",
                "stage": CHANNEL_ANALYSIS_STAGES[0],
                "checkpoints": {},
                "available_at": NOW,
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    with isolated_engine.connect() as connection:
        job = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        run = (
            connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == job["run_id"]))
            .mappings()
            .one()
        )
        analysis = (
            connection.execute(
                select(channel_analyses).where(channel_analyses.c.run_id == job["run_id"])
            )
            .mappings()
            .one()
        )
    assert job["status"] == "succeeded"
    assert set(job["checkpoints"]) >= set(CHANNEL_ANALYSIS_STAGES[:1])
    assert run["status"] == "succeeded"
    assert analysis["status"] == "completed"
    # Synthetic runs plan no vidIQ call, so nothing was omitted -- but the marker is wired.
    assert job["checkpoints"]["discover_comparables"]["vidiq_omitted"] is None
    assert analysis["configuration"]["max_comparables"] == 8
    assert analysis["configuration"]["channel_input"] == "@scienceexplained"
    assert set(analysis["consumption"]) == {"confirmed", "reservations"}
    panorama = analysis["snapshot"]["metrics"]["panorama"]
    assert panorama["status"] in {"computed", "incomplete"}
    if panorama["status"] == "computed":
        assert panorama["metrics"]["videos"] > 0
    # Loose on purpose: whether profit fully resolves to "estimated" also depends on
    # real comparable view-rate data existing in this synthetic run, which this test
    # isn't changing. The point here is confirming the wiring runs without crashing
    # and that videos_per_month/advertising are no longer unconditionally None.
    profit = analysis["snapshot"]["metrics"]["profit"]
    assert profit["status"] in {"estimated", "incomplete"}
    assert profit["status"] != "incomplete" or "advertising_rate" not in profit["missing"]


class _SearchQuotaExhaustedAfterFirstCall:
    """Delegates to a real SyntheticProvider for everything, but raises a budget
    ProviderError on the second Operation.SEARCH call — deterministically exercises
    the mid-sequence carry-forward/partial path without depending on real quota
    reservation arithmetic (budget.py's reserve() math has its own test suite;
    this test is only about Pipeline's dispatch/carry-forward behavior)."""

    name = "synthetic"

    def __init__(self) -> None:
        self._delegate = SyntheticProvider()
        self.operations = self._delegate.operations
        self._search_calls = 0

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if operation == Operation.SEARCH:
            self._search_calls += 1
            if self._search_calls > 1:
                raise ProviderError("period_budget_exhausted")
        return await self._delegate.fetch(operation, parameters, now)


@pytest.mark.postgres
def test_second_analysis_same_week_hits_search_quota_cleanly(isolated_engine: Engine) -> None:
    """A budget-coded ProviderError mid-sequence must leave the job a clean partial,
    never hang, crash, or silently skip to a disallowed source."""

    def make_job(
        connection: Connection, profile_id: UUID, key: str, channel: dict[str, str]
    ) -> UUID:
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": "synthetic",
                "trigger": "channel_analysis",
                "status": "running",
                "configuration": {"channel_input": "@scienceexplained"},
            },
        )
        return insert_record(
            connection,
            "jobs",
            {
                "run_id": run_id,
                "occurrence_key": key,
                "status": "queued",
                "stage": "discover_comparables",
                "checkpoints": {
                    "resolve": {"channel": channel},
                    "target_videos": {"videos": []},
                },
                "available_at": NOW,
            },
        )

    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())

    pipeline = Pipeline(
        isolated_engine, clock=lambda: NOW, provider=_SearchQuotaExhaustedAfterFirstCall()
    )

    with isolated_engine.begin() as connection:
        first_job_id = make_job(
            connection, profile_id, "test-ca-quota-1", {"id": "UC1", "title": "Science"}
        )
        assert claim(connection, "test-worker", NOW) is not None
    asyncio.run(pipeline.process(first_job_id, "test-worker"))

    with isolated_engine.begin() as connection:
        second_job_id = make_job(
            connection, profile_id, "test-ca-quota-2", {"id": "UC2", "title": "Astronomy"}
        )
        assert claim(connection, "test-worker", NOW) is not None
    asyncio.run(pipeline.process(second_job_id, "test-worker"))

    with isolated_engine.connect() as connection:
        second_job = (
            connection.execute(select(s.jobs).where(s.jobs.c.id == second_job_id)).mappings().one()
        )
        second_run = (
            connection.execute(
                select(s.analysis_runs).where(s.analysis_runs.c.id == second_job["run_id"])
            )
            .mappings()
            .one()
        )
        second_analysis = (
            connection.execute(
                select(channel_analyses).where(channel_analyses.c.run_id == second_job["run_id"])
            )
            .mappings()
            .one()
        )
    assert second_job["status"] == "partial"
    # Partial reasons live in the checkpoint JSON (same convention as the catalog flow's
    # `coverage["pending_reason"]`), not the `error_code` column — that column is only
    # written by fail_job() for hard failures, which this path deliberately avoids.
    assert second_job["checkpoints"]["discover_comparables"]["reason"] in {
        "run_budget_exhausted",
        "period_budget_exhausted",
    }
    assert second_run["status"] == "partial"
    assert second_analysis["status"] == "partial"


class _YouTubeQuotaOnSearch:
    """Real YouTubeProvider maps Google's 403 quotaExceeded / 429 to code "quota"."""

    name = "synthetic"

    def __init__(self) -> None:
        self._delegate = SyntheticProvider()
        self.operations = self._delegate.operations

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if operation == Operation.SEARCH:
            raise ProviderError("quota", may_have_charged=True)
        return await self._delegate.fetch(operation, parameters, now)


def _channel_analysis_job(
    connection: Connection,
    profile_id: UUID,
    key: str,
    stage: str,
    checkpoints: dict[str, Any],
    channel_input: str = "@scienceexplained",
) -> UUID:
    run_id = insert_record(
        connection,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "synthetic",
            "trigger": "channel_analysis",
            "status": "running",
            "configuration": {"channel_input": channel_input},
        },
    )
    return insert_record(
        connection,
        "jobs",
        {
            "run_id": run_id,
            "occurrence_key": key,
            "status": "queued",
            "stage": stage,
            "checkpoints": checkpoints,
            "available_at": NOW,
        },
    )


def _job_and_analysis(engine: Engine, job_id: UUID) -> tuple[Any, Any]:
    with engine.connect() as connection:
        job = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        analysis = (
            connection.execute(
                select(channel_analyses).where(channel_analyses.c.run_id == job["run_id"])
            )
            .mappings()
            .first()
        )
    return job, analysis


@pytest.mark.postgres
def test_real_youtube_quota_code_degrades_to_clean_partial(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-yt-quota",
            "discover_comparables",
            {
                "resolve": {"channel": {"id": "UC1", "title": "Science"}},
                "target_videos": {"videos": []},
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=_YouTubeQuotaOnSearch())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    job, analysis = _job_and_analysis(isolated_engine, job_id)
    assert job["status"] == "partial"
    assert job["error_code"] is None
    assert job["checkpoints"]["discover_comparables"]["reason"] == "quota"
    assert analysis is not None and analysis["status"] == "partial"


@pytest.mark.postgres
def test_hard_failure_still_fails_job_and_records_failed_analysis(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = _channel_analysis_job(
            connection, profile_id, "test-ca-not-found", "resolve", {}, "@__none__"
        )
        assert claim(connection, "test-worker", NOW) is not None
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    job, analysis = _job_and_analysis(isolated_engine, job_id)
    # The generic fail_job() bookkeeping is unchanged...
    assert job["status"] == "failed"
    assert job["error_code"] == "channel_not_found"
    # ...and the owner-facing list now also shows what happened.
    assert analysis is not None
    assert analysis["status"] == "failed"
    assert analysis["snapshot"]["failure"] == {
        "stage": "resolve",
        "error_code": "channel_not_found",
    }
    assert analysis["channel_input"] == "@__none__"


@pytest.mark.postgres
def test_failed_analysis_row_is_replaced_when_retry_later_succeeds(
    isolated_engine: Engine,
) -> None:
    # fail_job() may requeue/defer instead of finishing; a later successful persist for the
    # same run must overwrite the provisional failed row (run_id is unique), not crash.
    from nicheradar.services.channel_analysis import save_channel_analysis

    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = _channel_analysis_job(connection, profile_id, "test-ca-retry", "resolve", {})
        run_id = connection.execute(
            select(s.jobs.c.run_id).where(s.jobs.c.id == job_id)
        ).scalar_one()
        first = save_channel_analysis(
            connection,
            run_id,
            profile_id,
            {"failure": {"stage": "resolve", "error_code": "connection_failed"}},
            NOW,
            status="failed",
        )
        second = save_channel_analysis(
            connection,
            run_id,
            profile_id,
            {"resolve": {"channel": {"id": "UC1", "title": "Science"}}},
            NOW,
        )
        rows = (
            connection.execute(select(channel_analyses).where(channel_analyses.c.run_id == run_id))
            .mappings()
            .all()
        )
    assert first == second
    assert [row["status"] for row in rows] == ["completed"]
    assert rows[0]["channel_external_id"] == "UC1"
