# tests/test_pilots_schema.py
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.repositories.schema import channel_tokens as tokens
from nicheradar.repositories.schema import pilot_events as events
from nicheradar.repositories.schema import pilot_videos as videos
from nicheradar.repositories.schema import pilots
from scripts.backup_snapshot import inspect_snapshot

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def add_pilot(db: Connection, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "pilot_id": f"pil_20261101_{uuid4().hex[:8]}",
        "niche_label": "n",
        "format": "long",
        "language": "en",
        "status": "autorizado",
        "target_channel": "canal-historias",
        "package": {},
        "package_sha256": "0" * 64,
        "authorized_by": "david",
        "authorized_at": NOW,
        "valid_until": NOW + timedelta(days=14),
        "acknowledged": [],
        "created_at": NOW,
        "updated_at": NOW,
    } | overrides
    db.execute(sa.insert(pilots).values(**values))
    pk: UUID = values["id"]
    return pk


def add_video(db: Connection, pk: UUID, video_id: str = "v1") -> None:
    db.execute(
        sa.insert(videos).values(
            id=uuid4(),
            pilot_pk=pk,
            video_id=video_id,
            source_state="PROGRAMADO",
            stage="uploaded",
            visibility="unknown",
            cost_usd=0,
            reported_at=NOW,
        )
    )


def test_the_four_tables_exist(db: Connection) -> None:
    names = set(inspect(db).get_table_names())
    assert {"pilots", "pilot_videos", "pilot_events", "channel_tokens"} <= names


def test_status_and_format_are_constrained(db: Connection) -> None:
    for bad in ({"status": "inventado"}, {"format": "x"}):
        with pytest.raises(IntegrityError), db.begin_nested():
            add_pilot(db, **bad)


def test_a_channel_has_at_most_one_open_pilot_but_closed_ones_do_not_block(
    db: Connection,
) -> None:
    add_pilot(db, status="cerrado")
    add_pilot(db, status="cancelado")
    add_pilot(db)  # el primero abierto
    with pytest.raises(IntegrityError), db.begin_nested():
        add_pilot(db, status="en_ejecucion")  # otro abierto en el mismo canal
    add_pilot(db, target_channel="canal-otro")
    add_pilot(db, target_channel=None)
    add_pilot(db, target_channel=None)  # sin canal asignado: sin límite


def test_a_video_is_unique_per_pilot_and_cascades_with_it(db: Connection) -> None:
    pk = add_pilot(db)
    add_video(db, pk)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_video(db, pk)
    add_video(db, pk, "v2")
    db.execute(
        sa.insert(events).values(id=uuid4(), pilot_pk=pk, at=NOW, actor="x", kind="authorized")
    )
    db.execute(sa.delete(pilots).where(pilots.c.id == pk))
    assert db.execute(sa.select(sa.func.count()).select_from(videos)).scalar_one() == 0
    assert db.execute(sa.select(sa.func.count()).select_from(events)).scalar_one() == 0


def test_a_token_hash_cannot_repeat_and_pilot_ids_are_unique(db: Connection) -> None:
    row = {
        "channel_id": "canal-historias",
        "token_hash": "a" * 64,
        "label": "mac",
        "created_at": NOW,
    }
    db.execute(sa.insert(tokens).values(id=uuid4(), **row))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(tokens).values(id=uuid4(), **row))
    add_pilot(db, pilot_id="pil_20261101_igual", target_channel=None)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_pilot(db, pilot_id="pil_20261101_igual", target_channel=None)


def test_the_backup_guard_treats_pilots_as_research_data(db: Connection) -> None:
    add_pilot(db)
    with pytest.raises(ValueError, match="research_data_backup_not_enabled"):
        inspect_snapshot(db)
