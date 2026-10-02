import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine, select

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Batch, Operation, ProviderError
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import channel_analyses
from nicheradar.workers.channel_analysis_queue import CHANNEL_ANALYSIS_STAGES
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_channel_analysis_run_completes_through_every_stage(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
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
