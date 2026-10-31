# tests/test_subniche_worker.py
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.repositories import schema
from nicheradar.subniche_discovery.store import (
    approve,
    create_proposed,
    get_hypothesis,
    set_finalist,
)
from nicheradar.subniche_discovery.worker import CADENCE, cadence_open, tick_subniche
from tests.subniche_samples import NOW, FakeReader, draft, make_run
from tests.test_subniche_measure import scripted_reader


def live(**over: Any) -> Settings:
    return Settings(
        mode="live",
        subniche_enabled=True,
        youtube_live_enabled=True,
        subniche_channels_per_hypothesis=2,
        **over,
    )


def seed_hypothesis(
    engine: Engine, slug: str = "history_revenge", words: str = "history revenge"
) -> None:
    with engine.begin() as connection:
        create_proposed(connection, draft(slug=slug, queries=(words,)), NOW)
        approve(connection, slug, NOW)


def test_disabled_and_synthetic_modes_do_nothing() -> None:
    assert tick_subniche(Settings(mode="live"), clock=lambda: NOW)["status"] == "disabled"
    status = tick_subniche(Settings(mode="synthetic", subniche_enabled=True), clock=lambda: NOW)
    assert status["status"] == "synthetic_mode"


@pytest.mark.postgres
def test_idle_when_nothing_is_due(isolated_engine: Engine) -> None:
    out = tick_subniche(live(), isolated_engine, reader=FakeReader(), clock=lambda: NOW)
    assert out["status"] == "idle"


@pytest.mark.postgres
def test_a_run_measures_the_new_hypothesis_and_records_the_run(isolated_engine: Engine) -> None:
    seed_hypothesis(isolated_engine)
    out = tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: NOW)
    assert out["status"] == "complete" and out["measured"] == 1
    with isolated_engine.connect() as connection:
        run = connection.execute(sa.select(schema.discovery_runs)).mappings().one()
        assert run["status"] == "complete" and run["finished_at"] is not None
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] == NOW


@pytest.mark.postgres
def test_second_tick_inside_the_cadence_is_idle_even_with_a_new_hypothesis(
    isolated_engine: Engine,
) -> None:
    seed_hypothesis(isolated_engine)
    tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: NOW)
    seed_hypothesis(isolated_engine, "other_idea", "other idea words")
    soon = NOW + timedelta(days=2)
    assert (
        tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: soon)[
            "status"
        ]
        == "idle"
    )
    later = NOW + CADENCE + timedelta(minutes=1)
    with isolated_engine.connect() as connection:
        first_measured = get_hypothesis(connection, "history_revenge")["last_measured_at"]
    out = tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: later)
    assert out["status"] == "complete" and out["measured"] == 1
    with isolated_engine.connect() as connection:
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] == first_measured
        assert get_hypothesis(connection, "other_idea")["last_measured_at"] is not None


@pytest.mark.postgres
def test_quota_stop_marks_the_run_partial_and_resumes_the_next_local_day(
    isolated_engine: Engine,
) -> None:
    seed_hypothesis(isolated_engine)
    stopped = FakeReader(fail_search_after=0)
    out = tick_subniche(live(), isolated_engine, reader=stopped, clock=lambda: NOW)
    assert out["status"] == "partial" and out["stopped_reason"] == "subniche_daily_search_cap"
    with isolated_engine.connect() as connection:
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] is None
    same_day = NOW + timedelta(hours=1)
    assert (
        tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: same_day)[
            "status"
        ]
        == "idle"
    )
    next_day = NOW + timedelta(days=1)
    resumed = tick_subniche(
        live(), isolated_engine, reader=scripted_reader(), clock=lambda: next_day
    )
    assert resumed["status"] == "complete" and resumed["measured"] == 1


@pytest.mark.postgres
def test_cadence_open_rules(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        assert cadence_open(connection, NOW, "America/Lima") is True  # no runs yet
        run_id, _, _ = make_run(connection, NOW)
        # a run that is still `running` and young blocks a second worker
        assert cadence_open(connection, NOW + timedelta(hours=1), "America/Lima") is False
        # a stale `running` run on the same Lima day is still closed
        assert cadence_open(connection, NOW + timedelta(hours=7), "America/Lima") is False
        assert cadence_open(connection, NOW + timedelta(days=1), "America/Lima") is True
        connection.execute(
            sa.update(schema.discovery_runs)
            .where(schema.discovery_runs.c.id == run_id)
            .values(status="complete", finished_at=NOW)
        )
        assert cadence_open(connection, NOW + timedelta(days=2), "America/Lima") is False
        assert cadence_open(connection, NOW + CADENCE, "America/Lima") is True


def set_run(
    connection: Connection,
    run_id: Any,
    status: str,
    started_at: datetime,
    finished_at: datetime | None,
) -> None:
    connection.execute(
        sa.update(schema.discovery_runs)
        .where(schema.discovery_runs.c.id == run_id)
        .values(status=status, started_at=started_at, finished_at=finished_at)
    )


@pytest.mark.postgres
def test_complete_cadence_counts_from_started_at_not_finished_at(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        run_id, _, _ = make_run(connection, NOW)
        set_run(connection, run_id, "complete", NOW, NOW + timedelta(days=2, hours=12))
        # 3 days after started_at is open; 3 days after finished_at would still be closed.
        assert cadence_open(connection, NOW + CADENCE, "America/Lima") is True
        assert (
            cadence_open(connection, NOW + CADENCE - timedelta(minutes=1), "America/Lima") is False
        )


LIMA_DAY_CASES = [
    # (status, started UTC hour, probe offset from start, expected)
    # Lima is UTC-5: 03:00 UTC is 22:00 Lima; 06:00 UTC is already the next Lima day.
    ("partial", 3, timedelta(hours=3), True),
    ("failed", 3, timedelta(hours=3), True),
    ("running", 3, timedelta(hours=6), True),
    # 23:00 UTC is 18:00 Lima; 01:00 UTC next day is 20:00 Lima, the same Lima day.
    ("partial", 23, timedelta(hours=2), False),
    ("failed", 23, timedelta(hours=2), False),
]


@pytest.mark.postgres
@pytest.mark.parametrize(("status", "hour", "offset", "expected"), LIMA_DAY_CASES)
def test_resume_day_follows_the_lima_calendar_not_utc(
    isolated_engine: Engine, status: str, hour: int, offset: timedelta, expected: bool
) -> None:
    started = datetime(2026, 10, 31, hour, tzinfo=UTC)
    with isolated_engine.begin() as connection:
        run_id, _, _ = make_run(connection, started)
        finished = None if status == "running" else started
        set_run(connection, run_id, status, started, finished)
        assert cadence_open(connection, started + offset, "America/Lima") is expected


@pytest.mark.postgres
def test_finalist_is_refreshed_only_after_seven_days(isolated_engine: Engine) -> None:
    seed_hypothesis(isolated_engine)
    tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: NOW)
    with isolated_engine.begin() as connection:
        set_finalist(connection, "history_revenge", True)
    day3 = NOW + CADENCE + timedelta(minutes=1)
    assert (
        tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: day3)[
            "status"
        ]
        == "idle"
    )
    day8 = NOW + timedelta(days=8)
    out = tick_subniche(live(), isolated_engine, reader=scripted_reader(), clock=lambda: day8)
    assert out["status"] == "complete" and out["measured"] == 1
