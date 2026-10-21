# tests/test_market_intel_runs.py
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.market_intel.runs import (
    LEASE_SECONDS,
    MAXIMUM_ATTEMPTS,
    STAGES,
    LeaseLost,
    StageConflict,
    advance,
    advance_schedule,
    claim_run,
    ensure_run,
    ensure_schedule,
    finish,
    get_run,
    get_schedule,
    local_date,
    recent_runs,
    run_key,
    set_paused,
)
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from nicheradar.workers.queue import create_schedule

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
LIMA = "America/Lima"


def test_run_key_uses_the_local_date_not_utc() -> None:
    before_midnight_in_lima = datetime(2026, 10, 20, 4, 59, tzinfo=UTC)
    after_midnight_in_lima = datetime(2026, 10, 20, 5, 0, tzinfo=UTC)
    assert run_key(before_midnight_in_lima, LIMA) == "market_scrape:2026-10-19"
    assert run_key(after_midnight_in_lima, LIMA) == "market_scrape:2026-10-20"
    assert local_date(after_midnight_in_lima, "UTC").isoformat() == "2026-10-20"


@pytest.mark.postgres
def test_schedule_is_born_paused_and_toggles(db: Connection) -> None:
    ensure_schedule(db, NOW)
    ensure_schedule(db, NOW + timedelta(hours=1))
    schedule = get_schedule(db)
    assert schedule["paused"] is True and schedule["interval_seconds"] == 86_400
    assert schedule["next_due_at"] == NOW
    resumed = set_paused(db, False, NOW + timedelta(days=3))
    assert resumed["paused"] is False and resumed["next_due_at"] == NOW + timedelta(days=3)
    assert set_paused(db, True, NOW)["paused"] is True
    advance_schedule(db, NOW)
    assert get_schedule(db)["next_due_at"] == NOW + timedelta(days=1)


@pytest.mark.postgres
def test_market_pause_is_independent_from_the_radar_pause(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    create_schedule(db, profile_id, NOW, {})
    radar = s.radar_schedules.c.paused
    assert db.execute(sa.select(radar)).scalar_one() is True
    set_paused(db, False, NOW)
    assert (
        db.execute(sa.select(radar)).scalar_one() is True
    )  # resuming the scraper never resumes the radar
    db.execute(sa.update(s.radar_schedules).values(paused=False))
    set_paused(db, True, NOW)
    assert (
        db.execute(sa.select(radar)).scalar_one() is False
    )  # pausing the scraper never pauses the radar
    assert db.execute(sa.select(sa.func.count()).select_from(s.jobs)).scalar_one() == 0


@pytest.mark.postgres
def test_ensure_run_is_idempotent_and_mirrors_an_analysis_run(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    first = ensure_run(db, "market_scrape:2026-10-20", NOW, mode="synthetic", profile_id=profile_id)
    again = ensure_run(db, "market_scrape:2026-10-20", NOW, mode="synthetic", profile_id=profile_id)
    assert first == again
    run = get_run(db, first)
    assert run["status"] == "queued" and run["stage"] == STAGES[0] and run["attempts"] == 0
    analysis = db.execute(sa.select(s.analysis_runs)).mappings().one()
    assert analysis["trigger"] == "market_scrape" and analysis["mode"] == "synthetic"
    assert analysis["id"] == run["analysis_run_id"]


@pytest.mark.postgres
def test_claim_lease_attempts_and_exhaustion(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = ensure_run(db, "k", NOW, mode="synthetic", profile_id=profile_id)
    claimed = claim_run(db, run_id, "worker-a", NOW)
    assert claimed is not None and claimed["attempts"] == 1 and claimed["started_at"] == NOW
    assert claim_run(db, run_id, "worker-b", NOW + timedelta(seconds=LEASE_SECONDS - 1)) is None
    expired = NOW + timedelta(seconds=LEASE_SECONDS + 1)
    taken = claim_run(db, run_id, "worker-b", expired)
    assert taken is not None and taken["attempts"] == 2 and taken["lease_owner"] == "worker-b"
    assert taken["started_at"] == NOW  # the original start is kept for a resumed run
    later = expired
    for _ in range(MAXIMUM_ATTEMPTS - 2):
        later += timedelta(seconds=LEASE_SECONDS + 1)
        assert claim_run(db, run_id, "worker-c", later) is not None
    later += timedelta(seconds=LEASE_SECONDS + 1)
    assert claim_run(db, run_id, "worker-d", later) is None
    final = get_run(db, run_id)
    assert final["status"] == "failed" and final["error_code"] == "attempts_exhausted"
    analysis_status = db.execute(sa.select(s.analysis_runs.c.status)).scalar_one()
    assert analysis_status == "failed"


@pytest.mark.postgres
def test_advance_moves_one_stage_at_a_time_and_guards_the_lease(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = ensure_run(db, "k", NOW, mode="synthetic", profile_id=profile_id)
    claim_run(db, run_id, "worker-a", NOW)
    advance(db, run_id, "worker-a", NOW, "list", {"pages": 2})
    run = get_run(db, run_id)
    assert run["stage"] == "detail" and run["checkpoints"] == {"list": {"pages": 2}}
    with pytest.raises(StageConflict):
        advance(db, run_id, "worker-a", NOW, "list", {})
    with pytest.raises(LeaseLost):
        advance(db, run_id, "worker-b", NOW, "detail", {})
    with pytest.raises(LeaseLost):
        advance(db, run_id, "worker-a", NOW + timedelta(seconds=LEASE_SECONDS + 1), "detail", {})
    for stage in STAGES[1:]:
        advance(db, run_id, "worker-a", NOW, stage, {})
    assert get_run(db, run_id)["stage"] == "done"


@pytest.mark.postgres
def test_finish_records_status_and_blocks_further_claims(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = ensure_run(db, "k", NOW, mode="synthetic", profile_id=profile_id)
    claim_run(db, run_id, "worker-a", NOW)
    finish(db, run_id, "worker-a", NOW, status="blocked", error_code="blocked", stats={"pages": 3})
    run = get_run(db, run_id)
    assert run["status"] == "blocked" and run["finished_at"] == NOW and run["lease_owner"] is None
    assert run["error_code"] == "blocked" and run["stats"] == {"pages": 3}
    assert claim_run(db, run_id, "worker-b", NOW + timedelta(days=1)) is None
    assert db.execute(sa.select(s.analysis_runs.c.status)).scalar_one() == "failed"
    listed = recent_runs(db, 5)
    assert [item["run_key"] for item in listed] == ["k"] and listed[0]["status"] == "blocked"
