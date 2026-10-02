from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, func, insert, inspect, select
from sqlalchemy.exc import IntegrityError

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import (
    ConflictError,
    channel_identity,
    get_profile,
    insert_record,
    seed_profile,
    update_profile,
    video_identity,
)
from nicheradar.repositories.database import transaction

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 9, 13, tzinfo=UTC)


def seed_evidence(db: Connection) -> dict[str, UUID]:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "synthetic",
            "trigger": "manual",
            "status": "running",
            "configuration": {},
        },
    )
    policy_id = insert_record(
        db,
        "provider_policies",
        {
            "provider": "synthetic",
            "data_type": "video",
            "operation": "recent",
            "usage": "storage",
            "version": "v1",
            "status": "enabled",
            "evidence_source": "synthetic fixtures",
            "effective_at": NOW,
        },
    )
    request_id = insert_record(
        db,
        "provider_requests",
        {
            "run_id": run_id,
            "provider": "synthetic",
            "operation": "recent",
            "auth_scope": "test",
            "cache_key": "a" * 64,
            "idempotency_key": str(uuid4()),
            "state": "completed",
        },
    )
    raw_id = insert_record(
        db,
        "raw_observations",
        {
            "request_id": request_id,
            "policy_id": policy_id,
            "normalization_version": "v1",
            "fetched_at": NOW,
            "retain_until": NOW + timedelta(days=1),
            "payload": {},
            "coverage": {},
        },
    )
    channel_id = channel_identity(db, "synthetic", "channel-a")
    video_id = video_identity(db, "synthetic", "video-a", channel_id)
    observation_id = insert_record(
        db,
        "video_observations",
        {
            "video_id": video_id,
            "raw_observation_id": raw_id,
            "format": "long",
            "language": "en",
            "views": 0,
            "published_at": NOW - timedelta(days=10),
            "observed_at": NOW,
            "retain_until": NOW + timedelta(days=1),
            "data": {},
        },
    )
    family_id: UUID = db.execute(select(s.seed_families.c.id).limit(1)).scalar_one()
    topic_id = insert_record(
        db,
        "topics",
        {
            "family_id": family_id,
            "label": "A synthetic topic",
            "identity_key": "topic-a",
            "method_version": "fixture-v1",
        },
    )
    cohort_id = insert_record(
        db,
        "cohorts",
        {
            "run_id": run_id,
            "topic_id": topic_id,
            "format": "long",
            "language": "en",
            "criteria": {},
            "coverage": {},
        },
    )
    opportunity_id = insert_record(
        db,
        "opportunities",
        {
            "topic_id": topic_id,
            "audience_key": "english-learners",
            "language": "en",
            "format": "long",
        },
    )
    return {
        "profile": profile_id,
        "run": run_id,
        "raw": raw_id,
        "channel": channel_id,
        "video": video_id,
        "observation": observation_id,
        "family": family_id,
        "topic": topic_id,
        "cohort": cohort_id,
        "opportunity": opportunity_id,
    }


def test_migration_and_round_trip(db: Connection) -> None:
    assert set(s.metadata.tables) <= set(inspect(db).get_table_names())
    config = Config("alembic.ini")
    config.attributes["connection"] = db
    command.downgrade(config, "base")
    assert set(inspect(db).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(s.metadata.tables) <= set(inspect(db).get_table_names())


def test_profile_seed_is_idempotent_and_preserves_edits(db: Connection) -> None:
    first = seed_profile(db, CreatorProfile(), initial_catalog())
    assert first == seed_profile(db, CreatorProfile(), initial_catalog())
    profile_id, version, profile = get_profile(db)
    assert profile_id == first
    profile.weekly_hours = Decimal(18)
    assert update_profile(db, profile, version) == 2
    seed_profile(db, CreatorProfile(), initial_catalog())
    assert get_profile(db)[2].weekly_hours == 18
    with pytest.raises(ConflictError):
        update_profile(db, profile, version)


def test_identity_separate_from_observations(db: Connection) -> None:
    ids = seed_evidence(db)
    assert channel_identity(db, "synthetic", "channel-a") == ids["channel"]
    assert video_identity(db, "synthetic", "video-a", ids["channel"]) == ids["video"]
    assert "views" not in s.videos.c
    assert "subscribers" not in s.channels.c
    assert db.execute(select(s.video_observations.c.views)).scalar_one() == 0
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(s.channels).values(platform="synthetic", external_id="channel-a"))


def test_multiple_topics_but_one_member_per_cohort(db: Connection) -> None:
    ids = seed_evidence(db)
    other_topic = insert_record(
        db,
        "topics",
        {
            "family_id": ids["family"],
            "identity_key": "topic-b",
            "method_version": "fixture-v1",
        },
    )
    for topic in [ids["topic"], other_topic]:
        db.execute(
            insert(s.topic_memberships).values(
                topic_id=topic, video_id=ids["video"], observation_id=ids["raw"]
            )
        )
    member = {
        "cohort_id": ids["cohort"],
        "video_id": ids["video"],
        "video_observation_id": ids["observation"],
        "included": True,
        "reason_code": "confirmed",
        "selection_method": "recent",
        "size_stratum": "small",
        "age_band": "8-30",
    }
    db.execute(insert(s.cohort_memberships).values(**member))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(s.cohort_memberships).values(**member))
    assert db.execute(select(func.count()).select_from(s.cohort_memberships)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(s.topic_memberships)).scalar_one() == 2


def test_multiple_channel_proposals_and_exact_money(db: Connection) -> None:
    ids = seed_evidence(db)
    scenario = insert_record(
        db,
        "budget_scenarios",
        {
            "profile_id": ids["profile"],
            "name": "Two future channels",
            "assumptions": {},
        },
    )
    recipe = insert_record(
        db,
        "production_recipes",
        {
            "recipe_key": "synthetic",
            "version": "v1",
            "configuration": {},
        },
    )
    for key in ["channel-one", "channel-two"]:
        insert_record(
            db,
            "scenario_items",
            {
                "scenario_id": scenario,
                "channel_proposal_key": key,
                "opportunity_id": ids["opportunity"],
                "recipe_id": recipe,
                "production_plan": {},
            },
        )
    assert db.execute(select(func.count()).select_from(s.scenario_items)).scalar_one() == 2
    insert_record(
        db,
        "cost_ledger",
        {
            "profile_id": ids["profile"],
            "unit": "USD",
            "amount": Decimal("0.123456"),
            "kind": "manual",
            "external_reference": "synthetic-entry",
            "occurred_at": NOW,
        },
    )
    assert db.execute(select(s.cost_ledger.c.amount)).scalar_one() == Decimal("0.123456")
    assert "experiments" not in s.metadata.tables


def test_transaction_rolls_back(postgres_engine: Engine) -> None:
    key = f"rollback-{uuid4()}"
    with pytest.raises(RuntimeError), transaction(postgres_engine) as connection:
        channel_identity(connection, "synthetic", key)
        raise RuntimeError("synthetic failure")
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(select(s.channels).where(s.channels.c.external_id == key)).first()
            is None
        )
