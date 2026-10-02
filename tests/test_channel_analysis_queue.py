from uuid import UUID

import pytest
from sqlalchemy import Connection, select

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.workers.channel_analysis_queue import (
    CHANNEL_ANALYSIS_STAGES,
    confirm_channel_analysis_stage,
)
from nicheradar.workers.queue import claim
from tests.test_persistence import NOW


def seed_channel_analysis_job(db: Connection, occurrence_key: str, stage: str) -> dict[str, UUID]:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": "channel_analysis",
            "status": "running",
            "configuration": {},
        },
    )
    insert_record(
        db,
        "jobs",
        {
            "run_id": run_id,
            "occurrence_key": occurrence_key,
            "status": "queued",
            "stage": stage,
            "checkpoints": {},
            "available_at": NOW,
        },
    )
    return {"run_id": run_id}


@pytest.mark.postgres
def test_stage_sequence_advances_and_completes(db: Connection) -> None:
    ids = seed_channel_analysis_job(db, "test-channel-analysis-1", CHANNEL_ANALYSIS_STAGES[0])
    job = claim(db, "owner-a", NOW)
    assert job is not None
    assert job["stage"] == CHANNEL_ANALYSIS_STAGES[0]

    # Confirming a non-final stage advances "stage" but keeps the job "running" under the
    # same lease/owner (mirrors confirm_stage(): the same claimant proceeds through every
    # stage without re-claiming; it is not re-queued for another worker to pick up).
    confirm_channel_analysis_stage(
        db, job["id"], "owner-a", NOW, CHANNEL_ANALYSIS_STAGES[0], {"ok": True}
    )
    row = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert row["stage"] == CHANNEL_ANALYSIS_STAGES[1]
    assert row["status"] == "running"
    assert row["checkpoints"] == {CHANNEL_ANALYSIS_STAGES[0]: {"ok": True}}

    # A different owner cannot steal the lease while it is still held.
    assert claim(db, "owner-b", NOW) is None

    for stage in CHANNEL_ANALYSIS_STAGES[1:]:
        confirm_channel_analysis_stage(db, job["id"], "owner-a", NOW, stage, {"ok": True})

    final = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert final["status"] == "succeeded"
    assert final["stage"] == "done"
    assert final["checkpoints"] == {stage: {"ok": True} for stage in CHANNEL_ANALYSIS_STAGES}

    run = (
        db.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == ids["run_id"]))
        .mappings()
        .one()
    )
    assert run["status"] == "succeeded"
    assert run["finished_at"] == NOW


@pytest.mark.postgres
def test_partial_confirmation_marks_job_partial_not_queued(db: Connection) -> None:
    ids = seed_channel_analysis_job(db, "test-channel-analysis-2", CHANNEL_ANALYSIS_STAGES[-1])
    job = claim(db, "owner-b", NOW)
    assert job is not None
    confirm_channel_analysis_stage(
        db, job["id"], "owner-b", NOW, job["stage"], {"reason": "budget_exhausted"}, partial=True
    )
    row = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert row["status"] == "partial"
    assert row["stage"] == "done"
    assert row["lease_until"] is None

    run = (
        db.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == ids["run_id"]))
        .mappings()
        .one()
    )
    assert run["status"] == "partial"
