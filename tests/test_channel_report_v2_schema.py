# tests/test_channel_report_v2_schema.py
"""Tabla propia de mediciones de Shorts (migración 0017) y su lugar en el respaldo."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.repositories.schema import pilot_shorts_measurements as shorts
from nicheradar.repositories.schema import pilot_videos as videos
from nicheradar.repositories.schema import pilots
from scripts.backup_snapshot import PILOT_TABLES, inspect_snapshot
from tests.test_flow_research_language import _legacy_engine
from tests.test_pilots_schema import NOW, add_pilot

pytestmark = pytest.mark.postgres


def add_video(db: Connection, pilot_pk: UUID) -> UUID:
    video_pk = uuid4()
    db.execute(
        sa.insert(videos).values(
            id=video_pk,
            pilot_pk=pilot_pk,
            video_id="s1",
            source_state="EN_MEDICION",
            stage="measuring",
            visibility="public",
            cost_usd=0,
            reported_at=NOW,
        )
    )
    return video_pk


def add_measurement(db: Connection, video_pk: UUID, **over: Any) -> None:
    values: dict[str, Any] = {
        "pilot_video_id": video_pk,
        "engaged_views": 10,
        "engaged_view_ratio_pct": 50,
    } | over
    db.execute(sa.insert(shorts).values(**values))


def test_the_table_is_registered_in_the_guard_as_pilot_data(db: Connection) -> None:
    assert "pilot_shorts_measurements" in set(inspect(db).get_table_names())
    assert "pilot_shorts_measurements" in PILOT_TABLES


def test_a_measurement_hangs_from_its_video_and_cascades(db: Connection) -> None:
    video_pk = add_video(db, add_pilot(db))
    add_measurement(db, video_pk)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_measurement(db, video_pk)  # una medición por video
    with pytest.raises(IntegrityError), db.begin_nested():
        add_measurement(db, uuid4())  # sin video no hay medición
    db.execute(sa.delete(videos).where(videos.c.id == video_pk))
    assert db.execute(sa.select(sa.func.count()).select_from(shorts)).scalar_one() == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"engaged_views": -1},
        {"engaged_view_ratio_pct": 100.5},
        {"avg_view_pct": -1},
        {"shorts_feed_share_pct": 101},
        {"stayed_to_watch_pct": 101},
        {"early_retention_pct": 80},  # sin segundo
        {"early_retention_second": 3},  # sin porcentaje
        {"shares": -1},
    ],
)
def test_the_database_refuses_incoherent_measurements(db: Connection, bad: dict[str, Any]) -> None:
    video_pk = add_video(db, add_pilot(db))
    with pytest.raises(IntegrityError), db.begin_nested():
        add_measurement(db, video_pk, **bad)


def test_the_backup_guard_reviews_the_new_table_and_pins_revision_0018(db: Connection) -> None:
    video_pk = add_video(db, add_pilot(db))
    add_measurement(db, video_pk, early_retention_pct=80, early_retention_second=3)
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap+pilots" and report["revision"] == "0018"
    assert report["counts"]["pilot_shorts_measurements"] == 1  # type: ignore[index]


def test_the_migration_is_additive_and_reversible(postgres_engine: Engine) -> None:
    engine, schema = _legacy_engine(postgres_engine)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0016")
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
            add_video(connection, pilot)
            assert "pilot_shorts_measurements" not in inspect(connection).get_table_names()
            command.upgrade(config, "head")
            assert "pilot_shorts_measurements" in inspect(connection).get_table_names()
            kept = connection.execute(sa.select(sa.func.count()).select_from(videos)).scalar_one()
            assert kept == 1  # lo existente no se toca
            command.downgrade(config, "0016")
            assert "pilot_shorts_measurements" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
