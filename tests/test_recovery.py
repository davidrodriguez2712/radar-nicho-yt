import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, func, select, update

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import opportunity_scoring_configs, ranking_snapshots
from nicheradar.services.budget import reserve
from nicheradar.services.recovery import backup_deadline, prepare_restore
from nicheradar.services.requests import mark_sent
from nicheradar.workers.queue import claim, create_schedule, enqueue
from tests.test_execution import CAPS, COST, request_with_balance
from tests.test_persistence import NOW, seed_evidence

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("table_name", ["opportunity_scoring_configs", "ranking_snapshots"])
def test_backup_deadline_includes_scoring_and_ranking(db: Connection, table_name: str) -> None:
    ids = seed_evidence(db)
    deadline = NOW + timedelta(hours=1)
    if table_name == "opportunity_scoring_configs":
        db.execute(
            opportunity_scoring_configs.insert().values(
                opportunity_id=ids["opportunity"],
                profile_id=ids["profile"],
                version=1,
                configuration={},
                created_at=NOW,
                retain_until=deadline,
            )
        )
    else:
        db.execute(
            ranking_snapshots.insert().values(
                profile_id=ids["profile"],
                run_id=ids["run"],
                sequence=1,
                mode="synthetic",
                method_version="fixture",
                created_at=NOW,
                retain_until=deadline,
            )
        )
    assert backup_deadline(db) == deadline


def restore_fixture(db: Connection) -> None:
    ids, request = request_with_balance(db)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    mark_sent(db, request, NOW)
    create_schedule(db, ids["profile"], NOW, {})
    db.execute(update(s.radar_schedules).values(paused=False))
    enqueue(db, ids["profile"], "restore-fixture", NOW, {})
    assert claim(db, "original-worker", NOW) is not None
    insert_record(
        db,
        "opportunity_decisions",
        {
            "opportunity_id": ids["opportunity"],
            "version": 1,
            "state": "dismissed",
            "note": "Personal workflow decision",
        },
    )


def assert_restored(db: Connection) -> None:
    assert db.execute(select(s.radar_schedules.c.paused)).scalar_one() is True
    assert db.execute(select(s.jobs.c.status)).scalar_one() == "deferred"
    assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "unknown_charge"
    assert db.execute(select(s.opportunity_decisions.c.state)).scalar_one() == "dismissed"
    assert db.execute(select(func.count()).select_from(s.raw_observations)).scalar_one() == 0
    assert claim(db, "restored-worker", NOW + timedelta(days=2)) is None


def test_restore_pauses_expires_and_preserves_payment_liabilities(db: Connection) -> None:
    restore_fixture(db)
    assert backup_deadline(db) == NOW + timedelta(days=1)
    result = prepare_restore(db, NOW + timedelta(days=2))
    assert result["uncertain_requests"] == 1
    assert result["expired_observations"] == 1
    assert_restored(db)


def test_dump_and_restore_into_new_isolated_database(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    binary_dir = os.environ.get("NR_TEST_POSTGRES_BIN")
    dump = str(Path(binary_dir) / "pg_dump") if binary_dir else shutil.which("pg_dump")
    restore = str(Path(binary_dir) / "pg_restore") if binary_dir else shutil.which("pg_restore")
    if not dump or not restore:
        pytest.skip("pg_dump and pg_restore are required for the backup round-trip")
    with isolated_engine.begin() as db:
        restore_fixture(db)
        schema_name = db.exec_driver_sql("SELECT current_schema()").scalar_one()
    url = isolated_engine.url
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update(
        PGHOST=str(url.query.get("host", url.host or "localhost")),
        PGPORT=str(url.query.get("port", url.port or 5432)),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
    )
    archive = tmp_path / "synthetic-backup.dump"
    subprocess.run(
        [
            dump,
            "--dbname",
            url.database or "",
            "--schema",
            schema_name,
            "--format=custom",
            "--file",
            str(archive),
        ],
        env=env,
        check=True,
        capture_output=True,
    )
    target = "nicheradar_test_restore_" + uuid4().hex
    restored = create_engine(
        url.set(database=target),
        hide_parameters=True,
        connect_args={"options": f"-c search_path={schema_name}"},
    )
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{target}"')
        subprocess.run(
            [
                restore,
                "--dbname",
                target,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                str(archive),
            ],
            env=env,
            check=True,
            capture_output=True,
        )
        with restored.begin() as db:
            prepare_restore(db, NOW + timedelta(days=2))
            assert_restored(db)
        # The original remains untouched and is still paused only by its own operator.
        with isolated_engine.connect() as db:
            assert db.execute(select(s.radar_schedules.c.paused)).scalar_one() is False
            assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "reserved"
    finally:
        restored.dispose()
        with admin.connect() as connection:
            # Only the unique database generated by this test, never the source database.
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{target}"')
        admin.dispose()
