import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
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
        profile_id = seed_profile(
            connection,
            CreatorProfile(
                paid_limits_confirmed=True,
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
    # This synthetic fixture naturally produces a {long, unknown} format mix per
    # comparable channel (SyntheticProvider always marks one of its 8 videos per
    # channel UNKNOWN) -- after the mixed-format guard was loosened to evaluate the
    # confirmed majority format instead of aborting over one outlier, the panorama
    # must now actually compute, not merely be allowed to.
    assert panorama["status"] == "computed"
    assert panorama["metrics"]["videos"] > 0
    # Real wiring check (Task 10): the key must exist (not KeyError, not a crash).
    # Its value isn't asserted here -- this synthetic fixture's exact subscriber
    # counts aren't controlled by this test -- just that breakout classification
    # ran against real subscriber data without blowing up.
    assert "breakout_rate" in panorama["metrics"]
    # A synthetic-mode run never places the real, billable `advertising_match` LLM
    # call (see services/advertising_match.py's "synthetic_mode" guard), so this run's
    # matched niche is always None -- "advertising_rate" is deterministically missing
    # here, not merely allowed to be. videos_per_month is still unconditionally
    # populated though.
    assert job["checkpoints"]["advertising_match"] == {
        "matched_niche": None,
        "reason": "synthetic_mode",
    }
    profit = analysis["snapshot"]["metrics"]["profit"]
    assert profit["status"] == "incomplete"
    assert "advertising_rate" in profit["missing"]


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


@pytest.fixture
def pipeline_fixture(isolated_engine: Engine) -> tuple[Engine, UUID]:
    """Parks a channel-analysis job right at the `metrics` stage with one comparable
    channel of a known subscriber count (channel-0, 1000 subscribers) and a
    matching-format comparable video -- reusable by any test that only wants to
    exercise `metrics` stage wiring, not the full stage sequence."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        target_video = {
            "id": "t1",
            "channel_id": "UC_target",
            "title": "Target video",
            "published_at": (NOW - timedelta(days=10)).isoformat(),
            "views": 1000,
            "format": "long",
        }
        comparable_video = {
            "id": "c1",
            "channel_id": "channel-0",
            "title": "Comparable video",
            "published_at": (NOW - timedelta(days=10)).isoformat(),
            "views": 5000,
            "format": "long",
        }
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-metrics-stage",
            "metrics",
            {
                "resolve": {"channel": {"id": "UC_target", "title": "Target"}},
                "target_videos": {"videos": [target_video]},
                "discover_comparables": {
                    "comparables": [
                        {"id": "channel-0", "title": "Comparable", "subscribers": 1000}
                    ],
                    "vidiq_omitted": None,
                },
                "comparable_videos": {"videos_by_channel": {"channel-0": [comparable_video]}},
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    return isolated_engine, job_id


def run_metrics_stage(pipeline_fixture: tuple[Engine, UUID]) -> dict[str, Any]:
    engine, job_id = pipeline_fixture
    pipeline = Pipeline(engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    job, _ = _job_and_analysis(engine, job_id)
    result: dict[str, Any] = job["checkpoints"]["metrics"]
    return result


@pytest.mark.postgres
def test_metrics_stage_populates_views_subscriber_ratios(
    pipeline_fixture: tuple[Engine, UUID],
) -> None:
    """Regression for the bug confirmed in a live production run: comparable channels'
    `subscribers` (already fetched into `comparable_channels`) never got copied onto
    each `Video.subscriber_count` before `compute_panorama`/`calculate()` ran, so
    `views_subscriber_ratios` always came back all-None."""
    result = run_metrics_stage(pipeline_fixture)
    ratios = result["panorama"]["metrics"]["views_subscriber_ratios"]
    assert any(value is not None for value in ratios.values())


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
def test_metrics_stage_with_all_unknown_format_target_videos_does_not_crash(
    isolated_engine: Engine,
) -> None:
    """Real live-mode YouTube videos never carry a confirmed `format` (YouTubeProvider
    never sets it) -- the majority-format vote must skip UNKNOWN target videos, and when
    zero target videos have a confirmed format, `simulate()` must be skipped entirely
    rather than calling `default_recipe(VideoFormat.UNKNOWN, ...)`, which raises a plain
    pydantic ValidationError that nothing in this pipeline catches (a silent crash: no
    failed-row persisted, no job-status update)."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        target_video = {
            "id": "t1",
            "channel_id": "UC_target",
            "title": "Unformatted video",
            "published_at": (NOW - timedelta(days=10)).isoformat(),
            "views": 1000,
            "format": "unknown",
        }
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-unknown-format",
            "metrics",
            {
                "resolve": {"channel": {"id": "UC_target", "title": "Target"}},
                "target_videos": {"videos": [target_video]},
                "discover_comparables": {"comparables": [], "vidiq_omitted": None},
                "comparable_videos": {"videos_by_channel": {}},
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    job, analysis = _job_and_analysis(isolated_engine, job_id)
    assert job["status"] == "succeeded"  # never an uncaught crash
    assert analysis is not None and analysis["status"] == "completed"
    profit = analysis["snapshot"]["metrics"]["profit"]
    assert profit["status"] == "incomplete"
    assert "production_cost" in profit["missing"]


@pytest.mark.postgres
def test_advertising_benchmark_with_mismatched_format_is_not_used(
    isolated_engine: Engine,
) -> None:
    """Spec step 9 requires 'formato/audiencia equivalente' -- a declared Shorts-format
    benchmark must not be used for a target whose detected format is Long; it must be
    treated as unset for this run (profit degrades to "incomplete" with
    "advertising_rate" missing), never silently mixed into a mismatched-format estimate.

    The `metrics` stage now sources its benchmark exclusively via `build_benchmark()`
    from the `advertising_match` checkpoint's `matched_niche` (see Task 6), so this must
    exercise that real path end to end: a real (test-only) Shorts-format row is inserted
    directly into `advertising_benchmarks`, and the job's seeded checkpoints carry an
    `advertising_match` entry pointing at it, exactly like a real completed stage would.
    All 218 real seeded niches are `format="long"`, so a mismatched-format row has to be
    added here rather than reused from the real catalog."""
    with isolated_engine.begin() as connection:
        insert_record(
            connection,
            "advertising_benchmarks",
            {
                "niche_label": "test_shorts_mismatch_niche",
                "niche_description": "Test-only niche for format-mismatch rejection coverage.",
                "format": "shorts",
                "rate_low": Decimal("1.0"),
                "rate_high": Decimal("3.0"),
                "source": "test fixture, not a real advertising benchmark",
                "assumptions": "Test fixture only.",
                "created_at": NOW,
            },
        )
        profile_id = seed_profile(
            connection,
            CreatorProfile(
                paid_limits_confirmed=True,
            ),
            initial_catalog(),
        )
        target_video = {
            "id": "t1",
            "channel_id": "UC_target",
            "title": "Long video",
            "published_at": (NOW - timedelta(days=10)).isoformat(),
            "views": 1000,
            "format": "long",
        }
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-mismatched-format",
            "metrics",
            {
                "resolve": {"channel": {"id": "UC_target", "title": "Target"}},
                "target_videos": {"videos": [target_video]},
                "discover_comparables": {"comparables": [], "vidiq_omitted": None},
                "comparable_videos": {"videos_by_channel": {}},
                "advertising_match": {
                    "matched_niche": "test_shorts_mismatch_niche",
                    "reason": "response_received",
                },
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    job, analysis = _job_and_analysis(isolated_engine, job_id)
    assert job["status"] == "succeeded"
    profit = analysis["snapshot"]["metrics"]["profit"]
    assert profit["status"] == "incomplete"
    assert "advertising_rate" in profit["missing"]
    # The format DID get confirmed (long) and cost DID get computed -- only the
    # mismatched benchmark was rejected, nothing else degraded along with it.
    assert "production_cost" not in profit["missing"]


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


def _seed_prior_channel_analysis(
    connection: Connection,
    profile_id: UUID,
    channel_external_id: str,
    created_at: datetime,
    snapshot: dict[str, Any] | None,
    *,
    expired_at: datetime | None = None,
) -> None:
    """Inserts a real (test-only) prior `channel_analyses` row directly, the way a
    previously completed analysis run for the same channel would have left one --
    `growth`'s "reinvestigation" path reads this table for itself, so it must be
    exercised against a genuine row rather than a mock."""
    run_id = insert_record(
        connection,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "synthetic",
            "trigger": "channel_analysis",
            "status": "running",
            "configuration": {"channel_input": channel_external_id},
        },
    )
    insert_record(
        connection,
        "channel_analyses",
        {
            "profile_id": profile_id,
            "run_id": run_id,
            "channel_input": channel_external_id,
            "channel_external_id": channel_external_id,
            "status": "completed",
            "configuration": {},
            "snapshot": snapshot,
            "consumption": {},
            "created_at": created_at,
            "retain_until": created_at + timedelta(days=180),
            "expired_at": expired_at,
        },
    )


@pytest.fixture
def growth_first_analysis_fixture(isolated_engine: Engine) -> tuple[Engine, UUID]:
    """Parks a channel-analysis job right at the `persist` stage for a channel never
    seen before in this test database, published 100 days ago with 1000 subscribers --
    no prior `channel_analyses` row exists, so `growth` must fall back to the
    lifetime-average (Level 2) proxy."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-growth-first",
            "persist",
            {
                "resolve": {
                    "channel": {
                        "id": "UC_growth_first",
                        "title": "Growth First",
                        "subscribers": 1000,
                        "published_at": (NOW - timedelta(days=100)).isoformat(),
                    }
                }
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    return isolated_engine, job_id


@pytest.fixture
def growth_reinvestigation_fixture(isolated_engine: Engine) -> tuple[Engine, UUID]:
    """A prior, still-real `channel_analyses` row exists for the same
    `channel_external_id`, created 10 days ago with 500 subscribers in its snapshot --
    `growth` must use the REAL measured delta between the two observations, not the
    lifetime-average proxy."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        _seed_prior_channel_analysis(
            connection,
            profile_id,
            "UC_growth_reinvestigate",
            NOW - timedelta(days=10),
            {"resolve": {"channel": {"id": "UC_growth_reinvestigate", "subscribers": 500}}},
        )
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-growth-reinvestigation",
            "persist",
            {
                "resolve": {
                    "channel": {
                        "id": "UC_growth_reinvestigate",
                        "title": "Growth Reinvestigation",
                        "subscribers": 1000,
                        "published_at": (NOW - timedelta(days=400)).isoformat(),
                    }
                }
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    return isolated_engine, job_id


@pytest.fixture
def growth_no_published_at_fixture(isolated_engine: Engine) -> tuple[Engine, UUID]:
    """No prior `channel_analyses` row and no `published_at` on the channel --
    neither a real measured delta nor a lifetime-average proxy can be computed, so
    `growth` must land on `insufficient_evidence`."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-growth-no-published-at",
            "persist",
            {
                "resolve": {
                    "channel": {
                        "id": "UC_growth_no_published_at",
                        "title": "Growth No Published At",
                        "subscribers": 1000,
                    }
                }
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    return isolated_engine, job_id


@pytest.fixture
def growth_expired_prior_fixture(isolated_engine: Engine) -> tuple[Engine, UUID]:
    """A prior `channel_analyses` row exists for the same `channel_external_id`, but
    retention has since expired it (`snapshot=None`, `expired_at` set) -- the oldest
    row by period, but no longer the oldest with real data to read. `growth` must skip
    it (never KeyError on a None snapshot) and fall back to the lifetime-average proxy,
    exactly as if no prior row existed at all."""
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        _seed_prior_channel_analysis(
            connection,
            profile_id,
            "UC_growth_expired",
            NOW - timedelta(days=10),
            None,
            expired_at=NOW - timedelta(days=1),
        )
        job_id = _channel_analysis_job(
            connection,
            profile_id,
            "test-ca-growth-expired-prior",
            "persist",
            {
                "resolve": {
                    "channel": {
                        "id": "UC_growth_expired",
                        "title": "Growth Expired Prior",
                        "subscribers": 1000,
                        "published_at": (NOW - timedelta(days=100)).isoformat(),
                    }
                }
            },
        )
        assert claim(connection, "test-worker", NOW) is not None
    return isolated_engine, job_id


def run_persist_stage(pipeline_fixture: tuple[Engine, UUID]) -> dict[str, Any]:
    engine, job_id = pipeline_fixture
    pipeline = Pipeline(engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    _, analysis = _job_and_analysis(engine, job_id)
    assert analysis is not None
    result: dict[str, Any] = dict(analysis)
    return result


@pytest.mark.postgres
def test_growth_first_analysis_uses_lifetime_average(
    growth_first_analysis_fixture: tuple[Engine, UUID],
) -> None:
    saved = run_persist_stage(growth_first_analysis_fixture)
    growth = saved["snapshot"]["growth"]
    assert growth["tier"] == "lifetime_average"
    assert growth["subscribers_per_day"] == pytest.approx(1000 / 100, rel=0.01)
    assert growth["days_between_observations"] is None


@pytest.mark.postgres
def test_growth_reinvestigation_uses_measured_delta(
    growth_reinvestigation_fixture: tuple[Engine, UUID],
) -> None:
    saved = run_persist_stage(growth_reinvestigation_fixture)
    growth = saved["snapshot"]["growth"]
    assert growth["tier"] == "measured"
    assert growth["days_between_observations"] == 10
    assert growth["subscribers_per_day"] == pytest.approx((1000 - 500) / 10, rel=0.01)


@pytest.mark.postgres
def test_growth_no_published_at_is_insufficient_evidence(
    growth_no_published_at_fixture: tuple[Engine, UUID],
) -> None:
    saved = run_persist_stage(growth_no_published_at_fixture)
    assert saved["snapshot"]["growth"] == {
        "tier": "insufficient_evidence",
        "subscribers_per_day": None,
        "days_between_observations": None,
    }


@pytest.mark.postgres
def test_growth_prior_analysis_expired_falls_back_to_lifetime_average(
    growth_expired_prior_fixture: tuple[Engine, UUID],
) -> None:
    saved = run_persist_stage(growth_expired_prior_fixture)
    assert saved["snapshot"]["growth"]["tier"] == "lifetime_average"
