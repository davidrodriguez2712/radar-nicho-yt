import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import Connection, func, insert, select, update

from nicheradar.integrations.cache import cached_batch, store_cache
from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.integrations.retention import expire, shorten_policy_retention
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from tests.test_persistence import NOW, seed_evidence

pytestmark = pytest.mark.postgres


def test_policy_pending_is_per_usage(db: Connection) -> None:
    assert (
        require_usage(db, "synthetic", Operation.CHANNEL_SEARCH, Usage.DERIVED, "video", NOW)
        is None
    )
    with pytest.raises(ProviderError, match="policy_pending"):
        require_usage(db, "vidiq", Operation.CHANNEL_SEARCH, Usage.DERIVED, "video", NOW)
    policy = insert_record(
        db,
        "provider_policies",
        {
            "provider": "vidiq",
            "data_type": "video",
            "operation": "channel_search",
            "usage": "query",
            "version": "test-only",
            "status": "enabled",
            "evidence_source": "Synthetic permission, not provider approval",
            "effective_at": NOW,
        },
    )
    assert require_usage(db, "vidiq", Operation.CHANNEL_SEARCH, Usage.QUERY, "video", NOW) == policy
    with pytest.raises(ProviderError, match="policy_pending"):
        require_usage(db, "vidiq", Operation.CHANNEL_SEARCH, Usage.HISTORY, "video", NOW)


def test_cache_preserves_original_dates_and_expiration(db: Connection) -> None:
    ids = seed_evidence(db)
    provider = SyntheticProvider()
    batch = asyncio.run(provider.fetch(Operation.CHANNEL_VIDEOS, {}, NOW))
    db.execute(
        update(s.raw_observations)
        .where(s.raw_observations.c.id == ids["raw"])
        .values(payload=batch.model_dump(mode="json"))
    )
    store_cache(db, "key", ids["raw"], NOW + timedelta(hours=1))
    hit = cached_batch(db, "key", NOW + timedelta(minutes=30))
    assert hit is not None
    assert hit.provenance.fetched_at == NOW
    assert provider.calls == 1
    assert cached_batch(db, "other-key", NOW) is None
    assert cached_batch(db, "key", NOW + timedelta(hours=1)) is None
    store_cache(db, "key", ids["raw"], NOW + timedelta(days=5))
    assert cached_batch(db, "key", NOW + timedelta(days=1)) is None


def test_expiration_removes_derived_text_not_user_decisions(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation = insert_record(
        db,
        "evaluation_versions",
        {
            "opportunity_id": ids["opportunity"],
            "cohort_id": ids["cohort"],
            "run_id": ids["run"],
            "version": 1,
            "method_version": "synthetic-v1",
            "state": "provisional",
            "confidence": "provisional",
            "market_score": 50,
            "explanation": {"text": "fixture data"},
            "retain_until": NOW + timedelta(days=10),
        },
    )
    insert_record(
        db,
        "feature_values",
        {
            "evaluation_id": evaluation,
            "name": "views",
            "value": 50,
            "unit": "views",
            "definition": {},
            "retain_until": NOW + timedelta(days=10),
        },
    )
    insert_record(
        db,
        "evidence_links",
        {
            "evaluation_id": evaluation,
            "observation_id": ids["raw"],
            "availability": "available",
            "claim_key": "demand",
            "retain_until": NOW + timedelta(days=10),
        },
    )
    insert_record(
        db,
        "topic_artifacts",
        {
            "topic_id": ids["topic"],
            "observation_id": ids["raw"],
            "data": {"embedding": [1, 2]},
            "retain_until": NOW + timedelta(days=10),
        },
    )
    db.execute(
        insert(s.opportunity_decisions).values(
            opportunity_id=ids["opportunity"],
            version=1,
            state="dismissed",
            note="Not suitable for my workflow",
        )
    )
    assert expire(db, NOW)["expired_observations"] == 0
    counts = expire(db, NOW + timedelta(days=1))
    assert counts == {"expired_observations": 1, "expired_evaluations": 1}
    row = db.execute(select(s.evaluation_versions)).mappings().one()
    assert row["market_score"] is None
    assert row["explanation"] is None
    assert row["expired_at"] is not None
    assert db.execute(select(s.evidence_links.c.availability)).scalar_one() == "expired"
    assert db.execute(select(s.opportunity_decisions.c.state)).scalar_one() == "dismissed"
    assert db.execute(select(s.topics.c.label)).scalar_one() is None
    for table in [s.raw_observations, s.feature_values, s.video_observations, s.topic_artifacts]:
        assert db.execute(select(func.count()).select_from(table)).scalar_one() == 0


def test_policy_shortening_revisits_existing_observations(db: Connection) -> None:
    seed_evidence(db)
    policy_id = db.execute(select(s.provider_policies.c.id)).scalar_one()
    assert shorten_policy_retention(db, policy_id, 60, NOW + timedelta(seconds=61)) == 1
    assert db.execute(select(func.count()).select_from(s.raw_observations)).scalar_one() == 0


def test_immediate_policy_revocation_does_not_violate_deadline_constraint(db: Connection) -> None:
    seed_evidence(db)
    policy_id = db.execute(select(s.provider_policies.c.id)).scalar_one()
    assert shorten_policy_retention(db, policy_id, 0, NOW) == 1
    assert db.execute(select(func.count()).select_from(s.raw_observations)).scalar_one() == 0
    assert db.execute(select(func.count()).select_from(s.video_observations)).scalar_one() == 0
