"""Solicitudes de propuesta de subnicho (migración 0022): esquema y reversibilidad."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.repositories.schema import subniche_proposal_requests as requests
from tests.test_flow_research_language import _legacy_engine

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def request_row(**extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid4(),
        "idempotency_key": f"key-{uuid4().hex}",
        "input_text": "cozy mystery audiobooks",
        "kind": "query",
        "created_at": NOW,
    }
    row.update(extra)
    return row


def test_the_schema_matches_the_migrated_database(db: Connection) -> None:
    columns = {c["name"]: c for c in inspect(db).get_columns("subniche_proposal_requests")}
    assert {c.name for c in requests.c} == set(columns)
    expected = {
        "id": (False, None),
        "idempotency_key": (False, 100),
        "input_text": (False, 500),
        "kind": (False, 10),
        "manual": (True, None),
        "origin": (False, 12),
        "status": (False, 10),
        "error_code": (True, 80),
        "hypothesis_slug": (True, 60),
        "created_at": (False, None),
        "started_at": (True, None),
        "finished_at": (True, None),
    }
    assert set(expected) == set(columns)
    for name, (nullable, length) in expected.items():
        assert columns[name]["nullable"] is nullable, name
        assert getattr(columns[name]["type"], "length", None) == length, name
    assert isinstance(columns["manual"]["type"], sa.dialects.postgresql.JSONB)
    for name in ("created_at", "started_at", "finished_at"):
        assert getattr(columns[name]["type"], "timezone", False) is True, name
    assert str(columns["origin"]["default"]).startswith("'manual'")
    assert str(columns["status"]["default"]).startswith("'queued'")
    indexes = {
        i["name"]: i["column_names"] for i in inspect(db).get_indexes("subniche_proposal_requests")
    }
    assert indexes["ix_subniche_proposal_status_created"] == ["status", "created_at"]
    uniques = inspect(db).get_unique_constraints("subniche_proposal_requests")
    assert any(u["column_names"] == ["idempotency_key"] for u in uniques)


def test_defaults_apply_on_insert(db: Connection) -> None:
    db.execute(sa.insert(requests).values(**request_row()))
    row = db.execute(sa.select(requests.c.origin, requests.c.status)).one()
    assert tuple(row) == ("manual", "queued")


@pytest.mark.parametrize(
    ("column", "bad", "good"),
    [
        ("kind", "tweet", ["query", "video", "channel"]),
        ("status", "x", ["queued", "running", "ready", "failed"]),
        ("origin", "x", ["manual", "catalog", "marketplace", "lead"]),
    ],
)
def test_each_check_refuses_invalid_values_and_accepts_valid_ones(
    db: Connection, column: str, bad: str, good: list[str]
) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(requests).values(**request_row(**{column: bad})))
    for value in good:
        db.execute(sa.insert(requests).values(**request_row(**{column: value})))


def test_a_repeated_idempotency_key_is_refused(db: Connection) -> None:
    db.execute(sa.insert(requests).values(**request_row(idempotency_key="same-key-1")))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(requests).values(**request_row(idempotency_key="same-key-1")))


def test_the_migration_is_additive_and_reversible(postgres_engine: Engine) -> None:
    engine, schema = _legacy_engine(postgres_engine)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0021")
            assert "subniche_proposal_requests" not in inspect(connection).get_table_names()
            connection.execute(
                sa.text(
                    "insert into niche_hypotheses (id, slug, label, family, queries, origin, "
                    "created_at) values (:id, 'previa', 'Previa', 'f', '[]'::jsonb, 'manual', "
                    "now())"
                ),
                {"id": uuid4()},
            )
            command.upgrade(config, "0022")
            assert "subniche_proposal_requests" in inspect(connection).get_table_names()
            kept = connection.execute(sa.text("select slug from niche_hypotheses")).scalar_one()
            assert kept == "previa"  # lo previo se conserva
            command.downgrade(config, "0021")
            assert "subniche_proposal_requests" not in inspect(connection).get_table_names()
            kept = connection.execute(sa.text("select slug from niche_hypotheses")).scalar_one()
            assert kept == "previa"
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
