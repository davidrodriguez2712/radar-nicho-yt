import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select, update

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.integrations.contracts import (
    Batch,
    Cost,
    Coverage,
    Operation,
    Provenance,
    ProviderError,
    Video,
)
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import ranking_entries, ranking_snapshots
from nicheradar.services.backlog import decide, latest_decision
from nicheradar.services.gateway import Gateway
from nicheradar.workers.pipeline import Pipeline, merge_youtube_video, observations
from nicheradar.workers.queue import claim, enqueue
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


class LiveFixture(SyntheticProvider):
    name = "vidiq"

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        batch = await super().fetch(operation, parameters, now)
        return batch.model_copy(
            update={
                "provenance": Provenance(
                    provider="vidiq",
                    operation=operation,
                    auth_scope="personal-primary",
                    fetched_at=now,
                    observed_at=now,
                    synthetic=False,
                ),
                "costs": (
                    Cost(
                        unit="vidiq_credit",
                        maximum=Decimal(0 if operation == Operation.BALANCE else 5),
                        actual=Decimal(0 if operation == Operation.BALANCE else 5),
                        source="invented live fixture",
                    ),
                ),
                "balance": batch.balance.model_copy(update={"renews_at": NOW + timedelta(days=30)})
                if batch.balance
                else None,
            }
        )


class ChannelLanguageFixture(SyntheticProvider):
    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        batch = await super().fetch(operation, parameters, now)
        return batch.model_copy(
            update={
                "videos": tuple(
                    video.model_copy(update={"language": None, "language_evidence": None})
                    for video in batch.videos
                )
            }
        )


class YouTubeEnrichmentFixture:
    name = "youtube"
    operations = frozenset({Operation.VIDEOS})

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        self.calls += 1
        video_id = str(parameters["id"]).split(",")[0]
        return Batch(
            provenance=Provenance(
                provider="youtube",
                operation=operation,
                auth_scope="youtube-fixture",
                fetched_at=now,
            ),
            coverage=Coverage(returned=1, complete=True, selection_method="id_lookup"),
            costs=(
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(1),
                    actual=Decimal(1),
                    source="fixture",
                ),
            ),
            videos=(
                Video(
                    id=video_id,
                    channel_id="fixture-channel",
                    title="Canonical title",
                    description="Canonical description",
                    published_at=now - timedelta(days=5),
                    views=321,
                    language="en",
                    language_evidence="declared defaultAudioLanguage",
                    duration_seconds=30,
                ),
            ),
        )


def live_settings() -> Settings:
    return Settings(
        mode="live",
        vidiq_token=SecretStr("fixture-token"),
        vidiq_auth_scope="personal-primary",
        vidiq_connection_validated_at=NOW,
        vidiq_credit_cycle_started_at=NOW - timedelta(days=10),
        vidiq_live_enabled=True,
        vidiq_pilot_authorized=True,
    )


def enable_live_requirements(engine: Engine) -> tuple[UUID, UUID]:
    profile = CreatorProfile(paid_limits_confirmed=True)
    with engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        connection.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == profile_id)
            .values(configuration=profile.model_dump(mode="json"))
        )
        for usage in ("query", "storage", "history", "derived"):
            insert_record(
                connection,
                "provider_policies",
                {
                    "provider": "vidiq",
                    "operation": "*",
                    "data_type": "metadata",
                    "usage": usage,
                    "version": "fixture-only",
                    "status": "enabled",
                    "effective_at": NOW,
                    "evidence_source": "invented fixture",
                    "retention_seconds": 86400,
                },
            )
        job_id = enqueue(connection, profile_id, "live-pilot-fixture", NOW, {}, mode="live")
        assert claim(connection, "live-worker", NOW) is not None
    return profile_id, job_id


def test_live_pipeline_fails_closed_before_provider_call(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = enqueue(connection, profile_id, "blocked-live", NOW, {}, mode="live")
        assert claim(connection, "blocked-worker", NOW) is not None
    provider = LiveFixture()
    asyncio.run(
        Pipeline(
            isolated_engine,
            clock=lambda: NOW,
            provider=provider,
            settings=Settings(mode="live"),
        ).process(job_id, "blocked-worker")
    )
    assert provider.calls == 0
    with isolated_engine.connect() as connection:
        row = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        assert row["status"] == "deferred"
        assert row["error_code"] == "live_prerequisites_incomplete"
        assert (
            connection.execute(select(func.count()).select_from(s.provider_requests)).scalar_one()
            == 0
        )


def test_live_pipeline_uses_vidiq_gateway_and_credit_cap(isolated_engine: Engine) -> None:
    _, job_id = enable_live_requirements(isolated_engine)
    provider = LiveFixture()
    moments = iter(NOW + timedelta(microseconds=index) for index in range(1000))
    asyncio.run(
        Pipeline(
            isolated_engine,
            clock=lambda: next(moments),
            provider=provider,
            settings=live_settings(),
        ).process(job_id, "live-worker")
    )
    with isolated_engine.connect() as connection:
        job = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        assert job["status"] == "partial", (job["error_code"], job["checkpoints"])
        assert job["checkpoints"]["query"]["reason"] == "run_budget_exhausted"
        requests = connection.execute(
            select(s.provider_requests.c.provider, s.provider_requests.c.operation).order_by(
                s.provider_requests.c.created_at
            )
        ).all()
        assert [tuple(row) for row in requests] == [
            ("vidiq", "balance"),
            ("vidiq", "channel_search"),
            ("vidiq", "balance"),
        ]
        assert set(connection.execute(select(s.channels.c.platform)).scalars()) == {"youtube"}
        assert connection.execute(select(func.sum(s.cost_ledger.c.amount))).scalar_one() == Decimal(
            5
        )
        assert (
            connection.execute(select(s.analysis_runs.c.coverage)).scalar_one()["synthetic"]
            is False
        )


def test_youtube_enrichment_is_bounded_durable_and_uses_canonical_identity(
    isolated_engine: Engine,
) -> None:
    profile = CreatorProfile(paid_limits_confirmed=True)
    base_video = Video(
        id="fixture-video",
        channel_id="fixture-channel",
        title="Provider title",
        description=None,
        published_at=NOW - timedelta(days=6),
        views=123,
        format=VideoFormat.LONG,
        format_evidence="vidIQ response format",
        language=None,
        subscriber_count=10_000,
    )
    batch = Batch(
        provenance=Provenance(
            provider="vidiq",
            operation=Operation.CHANNEL_VIDEOS,
            auth_scope="personal-primary",
            fetched_at=NOW,
        ),
        coverage=Coverage(returned=1, complete=True, selection_method="recent"),
        costs=(Cost(unit="vidiq_credit", maximum=Decimal(5), actual=Decimal(5), source="fixture"),),
        videos=(base_video,)
        + tuple(
            base_video.model_copy(update={"id": f"fixture-video-{index:03d}"})
            for index in range(50)
        ),
    )
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        vidiq_policy_id = insert_record(
            connection,
            "provider_policies",
            {
                "provider": "vidiq",
                "operation": "*",
                "data_type": "metadata",
                "usage": "storage",
                "version": "fixture",
                "status": "enabled",
                "evidence_source": "fixture",
                "retention_seconds": 7 * 86400,
                "effective_at": NOW,
            },
        )
        for usage in ("query", "storage", "history", "derived"):
            insert_record(
                connection,
                "provider_policies",
                {
                    "provider": "youtube",
                    "operation": "videos",
                    "data_type": "metadata",
                    "usage": usage,
                    "version": "fixture",
                    "status": "enabled",
                    "evidence_source": "fixture",
                    "retention_seconds": 7 * 86400,
                    "effective_at": NOW,
                },
            )
        job_id = enqueue(connection, profile_id, "youtube-enrichment", NOW, {}, mode="live")
        run_id = connection.execute(
            select(s.jobs.c.run_id).where(s.jobs.c.id == job_id)
        ).scalar_one()
        request_id = insert_record(
            connection,
            "provider_requests",
            {
                "run_id": run_id,
                "provider": "vidiq",
                "operation": Operation.CHANNEL_VIDEOS.value,
                "auth_scope": "personal-primary",
                "cache_key": "b" * 64,
                "idempotency_key": "youtube-enrichment-source",
                "state": "completed",
            },
        )
        raw_id = insert_record(
            connection,
            "raw_observations",
            {
                "request_id": request_id,
                "policy_id": vidiq_policy_id,
                "normalization_version": "normalized-v1",
                "fetched_at": NOW,
                "retain_until": NOW + timedelta(days=7),
                "payload": batch.model_dump(mode="json"),
                "coverage": batch.coverage.model_dump(mode="json"),
            },
        )
        connection.execute(
            update(s.jobs)
            .where(s.jobs.c.id == job_id)
            .values(stage="enrichment", checkpoints={"query": {"raw_ids": [str(raw_id)]}})
        )
        job = claim(connection, "youtube-worker", NOW)
        assert job is not None
    fixture = YouTubeEnrichmentFixture()
    settings = live_settings().model_copy(
        update={
            "youtube_api_key": SecretStr("youtube-fixture-key"),
            "youtube_auth_scope": "youtube-fixture",
            "youtube_connection_validated_at": NOW,
            "youtube_live_enabled": True,
            "youtube_quota_per_run": 2,
            "youtube_quota_per_week": 10,
            "youtube_quota_per_month": 20,
        }
    )
    pipeline = Pipeline(
        isolated_engine,
        clock=lambda: NOW,
        provider=LiveFixture(),
        youtube=fixture,
        settings=settings,
    )
    asyncio.run(
        pipeline.enrich_youtube(
            job,
            profile_id,
            profile,
            "youtube-worker",
            live=True,
            scheduled=False,
        )
    )
    assert fixture.calls == 2
    with isolated_engine.begin() as connection:
        connection.execute(update(s.jobs).where(s.jobs.c.id == job_id).values(stage="enrichment"))
        resumed_job = dict(
            connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        )
    asyncio.run(
        pipeline.enrich_youtube(
            resumed_job,
            profile_id,
            profile,
            "youtube-worker",
            live=True,
            scheduled=False,
        )
    )
    assert fixture.calls == 2
    with isolated_engine.begin() as connection:
        stored_job = (
            connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        )
        assert stored_job["stage"] == "normalization"
        enriched_ids = stored_job["checkpoints"]["enrichment"]["raw_ids"]
        assert len(enriched_ids) == 3
        raw = observations(connection, enriched_ids, NOW)
        pipeline.normalize(connection, raw, "en", NOW)
        assert set(connection.execute(select(s.channels.c.platform)).scalars()) == {"youtube"}
        canonical_video_id = connection.execute(
            select(s.videos.c.id).where(s.videos.c.external_id == "fixture-video")
        ).scalar_one()
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.video_observations)
                .where(s.video_observations.c.video_id == canonical_video_id)
            ).scalar_one()
            == 2
        )
        assert connection.execute(
            select(func.sum(s.cost_ledger.c.amount)).where(s.cost_ledger.c.unit == "youtube_quota")
        ).scalar_one() == Decimal(2)
        supplemental = next(
            Batch.model_validate(item["payload"]).videos[0]
            for item in raw
            if Batch.model_validate(item["payload"]).provenance.provider == "youtube"
        )
        merged = merge_youtube_video(base_video, supplemental)
        assert merged.format.value == "long"
        assert merged.views == 321
        assert merged.language == "en"


def test_youtube_enrichment_makes_no_call_when_disabled(isolated_engine: Engine) -> None:
    profile = CreatorProfile(paid_limits_confirmed=True)
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        job_id = enqueue(connection, profile_id, "youtube-disabled", NOW, {}, mode="live")
        connection.execute(
            update(s.jobs)
            .where(s.jobs.c.id == job_id)
            .values(stage="enrichment", checkpoints={"query": {"raw_ids": []}})
        )
        job = claim(connection, "youtube-disabled-worker", NOW)
        assert job is not None
    fixture = YouTubeEnrichmentFixture()
    pipeline = Pipeline(
        isolated_engine,
        clock=lambda: NOW,
        provider=LiveFixture(),
        youtube=fixture,
        settings=live_settings(),
    )
    asyncio.run(
        pipeline.enrich_youtube(
            job,
            profile_id,
            profile,
            "youtube-disabled-worker",
            live=True,
            scheduled=False,
        )
    )
    assert fixture.calls == 0
    with isolated_engine.connect() as connection:
        stored = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
    assert stored["stage"] == "normalization"
    assert stored["checkpoints"]["enrichment"]["status"] == "disabled"


def test_synthetic_pipeline_to_backlog_and_cached_second_run(isolated_engine: Engine) -> None:
    engine = isolated_engine
    with engine.begin() as connection:
        profile = seed_profile(connection, CreatorProfile(), initial_catalog())
        first_job = enqueue(connection, profile, "first", NOW, {})
        assert claim(connection, "worker", NOW) is not None
    provider = SyntheticProvider()
    asyncio.run(Pipeline(engine, clock=lambda: NOW, provider=provider).process(first_job, "worker"))
    with engine.begin() as connection:
        assert (
            connection.execute(select(s.jobs.c.status).where(s.jobs.c.id == first_job)).scalar_one()
            == "succeeded"
        )
        assert set(connection.execute(select(s.opportunities.c.format)).scalars()) == {
            "long",
            "shorts",
        }
        assert set(connection.execute(select(s.evaluation_versions.c.state)).scalars()) == {
            "uncalibrated"
        }
        opportunity = connection.execute(select(s.opportunities.c.id).limit(1)).scalar_one()
        decide(connection, opportunity, "dismissed", "Keep this decision", 0, NOW)
        family = connection.execute(select(s.topics.c.family_id).limit(1)).scalar_one()
        config = connection.execute(
            select(s.seed_families.c.configuration).where(s.seed_families.c.id == family)
        ).scalar_one()
        connection.execute(
            update(s.seed_families)
            .where(s.seed_families.c.id == family)
            .values(configuration=config | {"pending": True})
        )
        second = enqueue(connection, profile, "second", NOW + timedelta(minutes=1), {})
        assert claim(connection, "worker", NOW + timedelta(minutes=1)) is not None
    previous_calls = provider.calls
    asyncio.run(
        Pipeline(engine, clock=lambda: NOW + timedelta(minutes=1), provider=provider).process(
            second, "worker"
        )
    )
    assert provider.calls == previous_calls
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(ranking_snapshots)).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                select(ranking_entries.c.position).where(ranking_entries.c.position.is_not(None))
            ).first()
            is None
        )
        assert latest_decision(connection, opportunity)["state"] == "dismissed"
        assert connection.execute(select(func.sum(s.cost_ledger.c.amount))).scalar_one() == Decimal(
            0
        )
        assert (
            connection.execute(select(func.count()).select_from(s.evaluation_versions)).scalar_one()
            == 4
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.discovery_queries)
                .where(s.discovery_queries.c.parent_query_id.is_not(None))
            ).scalar_one()
            >= 1
        )


def test_pipeline_records_retained_channel_language_claim_for_videos(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as connection:
        profile = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = enqueue(connection, profile, "channel-language", NOW, {})
        assert claim(connection, "language-worker", NOW) is not None
    asyncio.run(
        Pipeline(
            isolated_engine,
            clock=lambda: NOW,
            provider=ChannelLanguageFixture(),
        ).process(job_id, "language-worker")
    )
    with isolated_engine.connect() as connection:
        observations = connection.execute(select(s.video_observations)).mappings().all()
        assert observations
        assert {row["language"] for row in observations} == {"en"}
        assert {row["data"]["language_evidence"] for row in observations} == {
            "provider channel content-language claim; video audio unverified"
        }
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.cohort_memberships)
                .where(s.cohort_memberships.c.included.is_(True))
            ).scalar_one()
            > 0
        )


class FailingSynthetic(SyntheticProvider):
    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        self.calls += 1
        raise ProviderError("timeout", may_have_charged=True)


def test_unknown_charge_cannot_repeat_across_runs(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        job_id = enqueue(connection, profile_id, "unknown-first", NOW, {})
        run = connection.execute(select(s.jobs.c.run_id).where(s.jobs.c.id == job_id)).scalar_one()
    provider = FailingSynthetic()
    gateway = Gateway(
        isolated_engine, provider, profile_id, run, "synthetic", CreatorProfile(), {}, {}
    )
    with pytest.raises(ProviderError, match="timeout"):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "science"}, NOW))
    with isolated_engine.begin() as connection:
        next_job = enqueue(connection, profile_id, "unknown-second", NOW, {})
        next_run = connection.execute(
            select(s.jobs.c.run_id).where(s.jobs.c.id == next_job)
        ).scalar_one()
    another = Gateway(
        isolated_engine, provider, profile_id, next_run, "synthetic", CreatorProfile(), {}, {}
    )
    with pytest.raises(ProviderError, match="unknown_charge"):
        asyncio.run(another.fetch(Operation.CHANNEL_SEARCH, {"query": "science"}, NOW))
    assert provider.calls == 1
