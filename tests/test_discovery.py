import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select, update

from nicheradar.discovery.planning import plan_family
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Batch, Operation
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.schema import discovery_cursors
from nicheradar.services.backlog import decide
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim, create_schedule, enqueue, schedule_due
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


class RecordingProvider(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[Operation, dict[str, Any]]] = []

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        self.requests.append((operation, parameters))
        return await super().fetch(operation, parameters, now)


def run_pipeline(
    engine: Engine, now: datetime, provider: SyntheticProvider, maximum_calls: int = 20
) -> dict[str, Any]:
    with engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = enqueue(connection, profile_id, str(uuid4()), now, {})
        assert claim(connection, "test-worker", now) is not None
    asyncio.run(
        Pipeline(engine, clock=lambda: now, provider=provider, maximum_calls=maximum_calls).process(
            job_id, "test-worker"
        )
    )
    with engine.connect() as connection:
        return dict(
            connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        )


def test_subtopics_generate_bounded_queries_with_source_references(isolated_engine: Engine) -> None:
    provider = RecordingProvider()
    job = run_pipeline(isolated_engine, NOW, provider)
    assert job["status"] == "succeeded"
    searches = [
        params["query"]
        for operation, params in provider.requests
        if operation == Operation.CHANNEL_SEARCH
    ]
    family = job["checkpoints"]["planning"]["family_key"]
    assert searches[-1] == f"{family} explained"
    assert len(searches) == 3
    assert provider.calls == 17
    with isolated_engine.connect() as connection:
        query = (
            connection.execute(
                select(s.discovery_queries).where(
                    s.discovery_queries.c.selection_method == "provider_subtopic_expansion"
                )
            )
            .mappings()
            .one()
        )
        assert query["parent_query_id"] is not None
        raw_id = UUID(query["query"].split(":")[1])
        assert (
            connection.execute(
                select(s.raw_observations.c.id).where(s.raw_observations.c.id == raw_id)
            ).scalar_one()
            == raw_id
        )
        assert f"{family} explained" not in str(job["checkpoints"])


def test_partial_batches_continue_retained_receipts_after_cache_expiry(
    isolated_engine: Engine,
) -> None:
    provider = RecordingProvider()
    first = run_pipeline(isolated_engine, NOW, provider, maximum_calls=2)
    assert first["status"] == "partial"
    assert first["checkpoints"]["query"]["reason"] == "batch_limit"
    assert provider.calls == 2
    second = run_pipeline(isolated_engine, NOW + timedelta(days=2), provider, maximum_calls=4)
    assert second["status"] == "partial"
    assert second["checkpoints"]["planning"]["source_job_id"] == str(first["id"])
    assert provider.calls == 6
    final = run_pipeline(isolated_engine, NOW + timedelta(days=2, hours=1), provider)
    assert final["status"] == "succeeded"
    assert provider.calls == 17
    assert sum(operation == Operation.CHANNEL_SEARCH for operation, _ in provider.requests) == 3
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(discovery_cursors)
                .where(discovery_cursors.c.pending_job_id.is_not(None))
            ).scalar_one()
            == 0
        )


def test_selected_refresh_is_daily_and_only_updates_target_format(isolated_engine: Engine) -> None:
    provider = RecordingProvider()
    first = run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.begin() as connection:
        opportunities = (
            connection.execute(select(s.opportunities).order_by(s.opportunities.c.format))
            .mappings()
            .all()
        )
        selected = opportunities[0]
        decide(connection, selected["id"], "selected", "Research only", 0, NOW)
        decide(connection, opportunities[1]["id"], "watching", "Weekly follow-up", 0, NOW)
    count = provider.calls
    second = run_pipeline(isolated_engine, NOW + timedelta(days=1), provider)
    plan = second["checkpoints"]["planning"]
    assert plan["kind"] == "refresh"
    assert plan["opportunity_id"] == str(selected["id"])
    assert plan["family_id"] == first["checkpoints"]["planning"]["family_id"]
    assert provider.calls - count == 6
    assert all(operation == Operation.CHANNEL_VIDEOS for operation, _ in provider.requests[count:])
    with isolated_engine.connect() as connection:
        versions = (
            connection.execute(
                select(s.evaluation_versions.c.version).where(
                    s.evaluation_versions.c.opportunity_id == selected["id"]
                )
            )
            .scalars()
            .all()
        )
        assert sorted(versions) == [1, 2]
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunities[1]["id"])
            ).scalar_one()
            == 1
        )
    third = run_pipeline(isolated_engine, NOW + timedelta(days=1, minutes=1), provider)
    assert third["checkpoints"]["planning"]["kind"] == "catalog"
    assert third["checkpoints"]["planning"]["family_id"] != plan["family_id"]


def test_watching_weekly_dismissal_and_real_mode_isolation(isolated_engine: Engine) -> None:
    provider = RecordingProvider()
    run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.begin() as connection:
        opportunity = connection.execute(select(s.opportunities.c.id).limit(1)).scalar_one()
        decide(connection, opportunity, "watching", "Weekly", 0, NOW)
    early = run_pipeline(isolated_engine, NOW + timedelta(days=6), provider)
    assert early["checkpoints"]["planning"]["kind"] == "catalog"
    due = run_pipeline(isolated_engine, NOW + timedelta(days=7), provider)
    assert due["checkpoints"]["planning"]["opportunity_id"] == str(opportunity)
    with isolated_engine.begin() as connection:
        decide(connection, opportunity, "dismissed", "Stop tracking", 1, NOW + timedelta(days=7))
    dismissed = run_pipeline(isolated_engine, NOW + timedelta(days=15), provider)
    assert dismissed["checkpoints"]["planning"]["kind"] == "catalog"
    with isolated_engine.begin() as connection:
        profile = connection.execute(select(s.creator_profiles.c.id)).scalar_one()
        live_job = enqueue(connection, profile, "live-planning-only", NOW, {}, mode="live")
        run_id = connection.execute(
            select(s.jobs.c.run_id).where(s.jobs.c.id == live_job)
        ).scalar_one()
        plan = plan_family(connection, profile, run_id, NOW)
        assert plan["kind"] == "catalog"
        assert plan["opportunity_id"] is None
        assert set(connection.execute(select(discovery_cursors.c.mode)).scalars()) == {
            "live",
            "synthetic",
        }


def test_catalog_keeps_capacity_with_overdue_favorites(isolated_engine: Engine) -> None:
    provider = RecordingProvider()
    first = run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.begin() as connection:
        for opportunity in connection.execute(select(s.opportunities.c.id)).scalars():
            decide(connection, opportunity, "selected", "Favorite", 0, NOW)
    plans = [
        run_pipeline(isolated_engine, NOW + timedelta(days=index), provider)["checkpoints"][
            "planning"
        ]
        for index in range(1, 12)
    ]
    assert any(plan["kind"] == "refresh" for plan in plans)
    assert any(
        plan["kind"] == "catalog"
        and plan["family_id"] != first["checkpoints"]["planning"]["family_id"]
        for plan in plans
    )


def test_two_schedulers_create_only_one_due_job(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile = seed_profile(connection, CreatorProfile(), initial_catalog())
        create_schedule(connection, profile, NOW - timedelta(days=10), {})
        connection.execute(update(s.radar_schedules).values(paused=False))

    def attempt(_: int) -> list[UUID]:
        with isolated_engine.begin() as connection:
            return schedule_due(connection, NOW, globally_paused=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(len(result) for result in results) == [0, 1]
    with isolated_engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(s.jobs)).scalar_one() == 1


def test_small_batch_includes_both_channel_size_strata(isolated_engine: Engine) -> None:
    class StratifiedProvider(RecordingProvider):
        async def fetch(
            self, operation: Operation, parameters: dict[str, Any], now: datetime
        ) -> Batch:
            batch = await super().fetch(operation, parameters, now)
            if operation == Operation.CHANNEL_SEARCH:
                lower = parameters.get("subscriberCountMin", 0)
                upper = parameters.get("subscriberCountMax", 1_000_000)
                channels = tuple(
                    channel
                    for channel in batch.channels
                    if lower <= (channel.subscribers or 0) <= upper
                )[: parameters["limit"]]
                return batch.model_copy(update={"channels": channels})
            return batch

    with isolated_engine.begin() as connection:
        seed_profile(connection, CreatorProfile(discovery_max_channels=2), initial_catalog())
    provider = StratifiedProvider()
    job = run_pipeline(isolated_engine, NOW, provider)
    assert job["status"] == "succeeded"
    queried = {
        params["channelId"]
        for operation, params in provider.requests
        if operation == Operation.CHANNEL_VIDEOS
    }
    assert len(queried) == 2
    assert any(key.endswith("channel-0") for key in queried)
    assert any(key.endswith("channel-4") for key in queried)


def test_continuation_respects_changed_formats_and_channel_limit(isolated_engine: Engine) -> None:
    from nicheradar.domain.profile import VideoFormat
    from nicheradar.repositories.core import get_profile, update_profile

    provider = RecordingProvider()
    first = run_pipeline(isolated_engine, NOW, provider, maximum_calls=8)
    assert first["status"] == "partial"
    with isolated_engine.begin() as connection:
        _, version, profile = get_profile(connection)
        update_profile(
            connection,
            profile.model_copy(
                update={
                    "formats": (VideoFormat.LONG,),
                    "discovery_max_channels": 2,
                    "discovery_max_expansions": 0,
                }
            ),
            version,
        )
    count = provider.calls
    second = run_pipeline(isolated_engine, NOW + timedelta(days=2), provider)
    assert second["status"] == "succeeded"
    assert second["checkpoints"]["query_scope_v1"] != first["checkpoints"]["query_scope_v1"]
    assert all(params.get("videoFormat") != "short" for _, params in provider.requests[count:])
    with isolated_engine.connect() as connection:
        formats = (
            connection.execute(
                select(s.cohorts.c.format).where(s.cohorts.c.run_id == second["run_id"])
            )
            .scalars()
            .all()
        )
        assert formats == ["long"]
        rows = (
            connection.execute(
                select(s.raw_observations.c.payload).where(
                    s.raw_observations.c.id.in_(
                        [UUID(key) for key in second["checkpoints"]["query"]["raw_ids"]]
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not any(video["format"] == "shorts" for row in rows for video in row["videos"])


def test_refresh_without_evidence_stays_pending(isolated_engine: Engine) -> None:
    class EmptyProvider(RecordingProvider):
        async def fetch(
            self, operation: Operation, parameters: dict[str, Any], now: datetime
        ) -> Batch:
            batch = await super().fetch(operation, parameters, now)
            return batch.model_copy(update={"videos": (), "channels": ()})

    run_pipeline(isolated_engine, NOW, RecordingProvider())
    with isolated_engine.begin() as connection:
        opportunity = connection.execute(select(s.opportunities.c.id).limit(1)).scalar_one()
        decide(connection, opportunity, "selected", "Refresh", 0, NOW)
    job = run_pipeline(isolated_engine, NOW + timedelta(days=2), EmptyProvider())
    assert job["status"] == "partial"
    with isolated_engine.connect() as connection:
        coverage = connection.execute(
            select(s.analysis_runs.c.coverage).where(s.analysis_runs.c.id == job["run_id"])
        ).scalar_one()
        assert coverage["pending_reason"] == "refresh_evidence_insufficient"
        assert (
            connection.execute(
                select(discovery_cursors.c.pending_job_id).where(
                    discovery_cursors.c.opportunity_id == opportunity
                )
            ).scalar_one()
            == job["id"]
        )
    recovered = run_pipeline(isolated_engine, NOW + timedelta(days=4), RecordingProvider())
    assert recovered["checkpoints"]["planning"]["opportunity_id"] == str(opportunity)
    assert recovered["checkpoints"]["planning"]["source_job_id"] is None
    assert recovered["status"] == "succeeded"


def test_changed_language_does_not_refresh_old_candidates(isolated_engine: Engine) -> None:
    from nicheradar.repositories.core import get_profile, update_profile

    run_pipeline(isolated_engine, NOW, RecordingProvider())
    with isolated_engine.begin() as connection:
        for opportunity in connection.execute(select(s.opportunities.c.id)).scalars():
            decide(connection, opportunity, "selected", "English only", 0, NOW)
        profile_id, version, profile = get_profile(connection)
        update_profile(connection, profile.model_copy(update={"language": "es"}), version)
        job_id = enqueue(connection, profile_id, "changed-language", NOW + timedelta(days=2), {})
        run_id = connection.execute(
            select(s.jobs.c.run_id).where(s.jobs.c.id == job_id)
        ).scalar_one()
        plan = plan_family(connection, profile_id, run_id, NOW + timedelta(days=2))
        assert plan["kind"] == "catalog"
        assert plan["refresh_pending"] == []
