# tests/test_flow_research_schema.py
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.integrations.retention import expire
from nicheradar.repositories.schema import flow_research_dossiers as dossiers
from nicheradar.repositories.schema import flow_research_requests as requests
from scripts.backup_snapshot import inspect_snapshot

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 20, 15, tzinfo=UTC)


def add_request(db: Connection, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "niche_label": "personal_finance",
        "format": "long",
        "status": "pendiente",
        "evidence": {},
        "created_at": NOW,
        "updated_at": NOW,
        "retain_until": NOW + timedelta(days=183),
    } | overrides
    db.execute(sa.insert(requests).values(**values))
    request_id: UUID = values["id"]
    return request_id


def add_dossier(db: Connection, request_id: UUID, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "id": uuid4(),
        "request_id": request_id,
        "niche_label": "personal_finance",
        "format": "long",
        "schema_version": "dossier-v1",
        "content": {},
        "created_at": NOW,
        "retain_until": NOW + timedelta(days=183),
    } | overrides
    db.execute(sa.insert(dossiers).values(**values))


def test_both_tables_exist(db: Connection) -> None:
    tables = set(inspect(db).get_table_names())
    assert {"flow_research_requests", "flow_research_dossiers"} <= tables


@pytest.mark.parametrize(
    "overrides", [{"status": "cancelado"}, {"format": "reels"}], ids=["status", "format"]
)
def test_check_constraints_reject_unknown_values(db: Connection, overrides: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        add_request(db, **overrides)


def test_only_one_request_is_active_per_niche_and_format(db: Connection) -> None:
    first = add_request(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_request(db, status="en_curso")
    add_request(db, format="shorts")  # another format is another niche
    db.execute(sa.update(requests).where(requests.c.id == first).values(status="listo"))
    add_request(db)  # a finished request no longer blocks a new one
    add_request(db, status="rechazado")


def test_a_request_has_at_most_one_dossier(db: Connection) -> None:
    request_id = add_request(db, status="listo")
    add_dossier(db, request_id)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_dossier(db, request_id)
    with pytest.raises(IntegrityError), db.begin_nested():
        add_dossier(db, uuid4())  # a dossier needs its request


def test_expire_purges_old_dossiers_with_their_requests_and_keeps_the_rest(
    db: Connection,
) -> None:
    past, future = NOW - timedelta(days=1), NOW + timedelta(days=10)
    old = add_request(db, status="listo", retain_until=past)
    add_dossier(db, old, retain_until=past)
    fresh = add_request(db, niche_label="gaming_general", retain_until=future)
    # A request whose deadline passed but whose dossier is still retained must stay (FK safety).
    parent = add_request(db, niche_label="cooking_recipes", status="listo", retain_until=past)
    add_dossier(db, parent, niche_label="cooking_recipes", retain_until=future)
    expire(db, NOW)
    kept = set(db.execute(sa.select(requests.c.id)).scalars())
    assert kept == {fresh, parent}
    assert db.execute(sa.select(sa.func.count()).select_from(dossiers)).scalar_one() == 1


def test_the_backup_guard_treats_flow_research_as_research_data(db: Connection) -> None:
    add_request(db)
    with pytest.raises(ValueError, match="research_data_backup_not_enabled"):
        inspect_snapshot(db)
