"""Lecturas de tweets e imágenes (migración 0023): esquema, CHECK y reversibilidad."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Operation
from nicheradar.repositories.schema import lead_candidates as candidates
from nicheradar.repositories.schema import lead_read_requests as reads
from scripts.backup_snapshot import DISCOVERY_TABLES, PROVIDER_EVIDENCE_TABLES
from tests.test_flow_research_language import _legacy_engine

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def read_row(**extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid4(),
        "idempotency_key": f"key-{uuid4().hex}",
        "kind": "tweet",
        "tweet_id": "1850000000000000000",
        "created_at": NOW,
    }
    row.update(extra)
    return row


def candidate_row(read_id: object, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid4(),
        "read_id": read_id,
        "position": 0,
        "kind": "handle",
        "value": "@historia_uno",
        "found_in": "image",
        "resolution": "name_only",
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(extra)
    return row


def test_settings_defaults_and_bounds() -> None:
    assert Settings().lead_reads_per_day == 50
    assert Settings().anthropic_vision_configuration is None
    with pytest.raises(ValueError):
        Settings(lead_reads_per_day=0)
    assert Operation.LEAD_MENTIONS.value == "lead_mentions"


def test_new_tables_are_schema_only_in_backups() -> None:
    assert {"lead_read_requests", "lead_candidates"} <= set(PROVIDER_EVIDENCE_TABLES)
    assert not {"lead_read_requests", "lead_candidates"} & DISCOVERY_TABLES


@pytest.mark.postgres
def test_the_schema_matches_the_migrated_database(db: Connection) -> None:
    for table in (reads, candidates):
        columns = {c["name"]: c for c in inspect(db).get_columns(table.name)}
        assert {c.name for c in table.c} == set(columns), table.name
    columns = {c["name"]: c for c in inspect(db).get_columns("lead_read_requests")}
    assert getattr(columns["untrusted_text"]["type"], "length", None) == 1000
    assert getattr(columns["tweet_author"]["type"], "length", None) == 15
    assert isinstance(columns["image_data"]["type"], sa.LargeBinary)
    proposal = {c["name"]: c for c in inspect(db).get_columns("subniche_proposal_requests")}
    assert proposal["lead_author"]["nullable"] and proposal["lead_tweet_id"]["nullable"]
    indexes = {i["name"]: i["column_names"] for i in inspect(db).get_indexes("lead_read_requests")}
    assert indexes["ix_lead_read_status_created"] == ["status", "created_at"]


@pytest.mark.postgres
@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "video"},
        {"status": "x"},
        {"stage": "x"},
        {"kind": "tweet", "tweet_id": None},
        {"kind": "image", "tweet_id": "1"},
        {"kind": "tweet", "image_data": PNG, "image_type": "image/png"},
        {"kind": "image", "tweet_id": None, "image_type": "image/gif", "image_data": PNG},
        {
            "kind": "image",
            "tweet_id": None,
            "image_type": "image/png",
            "image_data": b"x" * 5_242_881,
        },
        {"photos_read": 5},
    ],
)
def test_read_checks_refuse_invalid_rows(db: Connection, bad: dict[str, object]) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(reads).values(**read_row(**bad)))


@pytest.mark.postgres
def test_valid_reads_and_candidates_are_accepted(db: Connection) -> None:
    tweet = read_row()
    image = read_row(kind="image", tweet_id=None, image_type="image/png", image_data=PNG)
    db.execute(sa.insert(reads).values(**tweet))
    db.execute(sa.insert(reads).values(**image))
    db.execute(sa.insert(candidates).values(**candidate_row(tweet["id"])))
    db.execute(
        sa.insert(candidates).values(
            **candidate_row(
                tweet["id"],
                position=1,
                kind="channel_id",
                value="UC" + "a" * 22,
                resolution="resolved",
                channel_id="UC" + "a" * 22,
                found_in="both",
            )
        )
    )


@pytest.mark.postgres
@pytest.mark.parametrize(
    "bad",
    [
        {"position": 10},
        {"kind": "url"},
        {"found_in": "x"},
        {"resolution": "maybe"},
        {"resolution": "resolved", "channel_id": None},
    ],
)
def test_candidate_checks_refuse_invalid_rows(db: Connection, bad: dict[str, object]) -> None:
    parent = read_row()
    db.execute(sa.insert(reads).values(**parent))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(candidates).values(**candidate_row(parent["id"], **bad)))


@pytest.mark.postgres
def test_a_mention_is_stored_once_per_read(db: Connection) -> None:
    parent = read_row()
    db.execute(sa.insert(reads).values(**parent))
    db.execute(sa.insert(candidates).values(**candidate_row(parent["id"])))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(candidates).values(**candidate_row(parent["id"], position=1)))


@pytest.mark.postgres
def test_the_migration_is_additive_and_reversible(postgres_engine: Engine) -> None:
    engine, schema = _legacy_engine(postgres_engine)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0022")
            connection.execute(
                sa.text(
                    "insert into subniche_proposal_requests (id, idempotency_key, input_text, "
                    "kind, created_at) values (:id, 'previa-0001', 'cozy mystery', 'query', now())"
                ),
                {"id": uuid4()},
            )
            command.upgrade(config, "0023")
            tables = set(inspect(connection).get_table_names())
            assert {"lead_read_requests", "lead_candidates"} <= tables
            kept = connection.execute(
                sa.text("select input_text, lead_author from subniche_proposal_requests")
            ).one()
            assert tuple(kept) == ("cozy mystery", None)
            command.downgrade(config, "0022")
            tables = set(inspect(connection).get_table_names())
            assert not {"lead_read_requests", "lead_candidates"} & tables
            columns = {
                c["name"] for c in inspect(connection).get_columns("subniche_proposal_requests")
            }
            assert "lead_author" not in columns
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.mark.postgres
def test_deleting_a_read_deletes_its_candidates(db: Connection) -> None:
    parent, other = read_row(), read_row()
    db.execute(sa.insert(reads).values(**parent))
    db.execute(sa.insert(reads).values(**other))
    db.execute(sa.insert(candidates).values(**candidate_row(parent["id"])))
    db.execute(sa.insert(candidates).values(**candidate_row(other["id"])))
    db.execute(sa.delete(reads).where(reads.c.id == parent["id"]))
    left = db.execute(sa.select(candidates.c.read_id)).scalars().all()
    assert left == [other["id"]]


@pytest.mark.postgres
def test_deleting_a_proposal_leaves_the_candidate_with_a_null_link(db: Connection) -> None:
    from nicheradar.repositories.schema import subniche_proposal_requests as proposals

    parent, proposal_id = read_row(), uuid4()
    db.execute(sa.insert(reads).values(**parent))
    db.execute(
        sa.insert(proposals).values(
            id=proposal_id,
            idempotency_key=f"k-{uuid4().hex}",
            input_text="UC" + "a" * 22,
            kind="channel",
            origin="lead",
            status="queued",
            created_at=NOW,
        )
    )
    row = candidate_row(parent["id"], proposal_request_id=proposal_id)
    db.execute(sa.insert(candidates).values(**row))
    db.execute(sa.delete(proposals).where(proposals.c.id == proposal_id))
    link = db.execute(
        sa.select(candidates.c.proposal_request_id).where(candidates.c.id == row["id"])
    ).one()
    assert tuple(link) == (None,)


@pytest.mark.postgres
def test_a_position_is_used_once_per_read(db: Connection) -> None:
    parent = read_row()
    db.execute(sa.insert(reads).values(**parent))
    db.execute(sa.insert(candidates).values(**candidate_row(parent["id"])))
    with pytest.raises(IntegrityError, match="uq_lead_candidate_position"), db.begin_nested():
        db.execute(sa.insert(candidates).values(**candidate_row(parent["id"], value="@otro_canal")))
    db.execute(
        sa.insert(candidates).values(**candidate_row(parent["id"], value="@otro_canal", position=1))
    )
