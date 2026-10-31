# tests/subniche_samples.py
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema
from nicheradar.repositories.core import insert_record, seed_profile

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def make_run(db: Connection, now: datetime = NOW) -> tuple[UUID, UUID, UUID]:
    """(discovery_run_id, analysis_run_id, profile_id)."""
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    analysis_id = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": "subniche",
            "status": "queued",
            "configuration": {},
        },
    )
    run_id = uuid4()
    db.execute(
        sa.insert(schema.discovery_runs).values(
            id=run_id, analysis_run_id=analysis_id, status="running", started_at=now, stats={}
        )
    )
    return run_id, analysis_id, profile_id
