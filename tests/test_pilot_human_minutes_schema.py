# tests/test_pilot_human_minutes_schema.py
"""Minutos humanos por video (migración 0021): columnas, restricción y reversibilidad."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.repositories.schema import pilot_videos as videos
from nicheradar.repositories.schema import pilots
from tests.test_flow_research_language import _legacy_engine
from tests.test_pilots_schema import NOW, add_pilot

pytestmark = pytest.mark.postgres


def insert_video(db: Connection, pilot_pk: UUID, **extra: object) -> UUID:
    video_pk = uuid4()
    db.execute(
        sa.insert(videos).values(
            id=video_pk,
            pilot_pk=pilot_pk,
            video_id=f"v{uuid4().hex[:8]}",
            source_state="PROGRAMADO",
            stage="uploaded",
            visibility="unknown",
            cost_usd=0,
            reported_at=NOW,
            **extra,
        )
    )
    return video_pk


def test_the_schema_matches_the_migrated_database(db: Connection) -> None:
    columns = {c["name"]: c for c in inspect(db).get_columns("pilot_videos")}
    assert {c.name for c in videos.c} == set(columns)
    assert columns["human_minutes"]["nullable"] is True
    assert isinstance(columns["human_minutes"]["type"], sa.Integer)
    assert columns["human_minutes_method"]["nullable"] is True
    assert getattr(columns["human_minutes_method"]["type"], "length", None) == 60
    checks = {c["name"] for c in inspect(db).get_check_constraints("pilot_videos")}
    assert "ck_pilot_videos_pilot_videos_human_minutes_nonneg" in checks  # convención ck_<tabla>_


def test_the_constraint_refuses_negative_minutes_and_accepts_zero_and_null(db: Connection) -> None:
    pilot = add_pilot(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        insert_video(db, pilot, human_minutes=-1)
    insert_video(db, pilot, human_minutes=0, human_minutes_method="manual")
    insert_video(db, pilot, human_minutes=None)


def test_the_migration_is_additive_and_reversible(postgres_engine: Engine) -> None:
    engine, schema = _legacy_engine(postgres_engine)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0020")
            pilot = uuid4()
            connection.execute(
                sa.insert(pilots).values(
                    id=pilot,
                    pilot_id="pil_20261101_previo",
                    niche_label="n",
                    format="long",
                    language="en",
                    status="autorizado",
                    package={},
                    package_sha256="0" * 64,
                    authorized_by="david",
                    authorized_at=NOW,
                    valid_until=NOW + timedelta(days=14),
                    acknowledged=[],
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            insert_video(connection, pilot, machine_minutes=7)
            names = {c["name"] for c in inspect(connection).get_columns("pilot_videos")}
            assert "human_minutes" not in names and "human_minutes_method" not in names
            command.upgrade(config, "head")
            row = connection.execute(
                sa.select(
                    videos.c.machine_minutes, videos.c.human_minutes, videos.c.human_minutes_method
                )
            ).one()
            assert tuple(row) == (7, None, None)  # lo existente se conserva
            command.downgrade(config, "0020")
            names = {c["name"] for c in inspect(connection).get_columns("pilot_videos")}
            assert "human_minutes" not in names and "human_minutes_method" not in names
            kept = connection.execute(
                sa.text("select machine_minutes from pilot_videos")
            ).scalar_one()
            assert kept == 7
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
