# tests/test_subniche_schema.py
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from nicheradar.integrations.retention import expire
from nicheradar.repositories import schema
from tests.subniche_samples import NOW, make_run


def hypothesis_row(slug: str = "history_revenge", **over: object) -> dict[str, object]:
    return {
        "id": uuid4(),
        "slug": slug,
        "label": "History Revenge",
        "family": "history",
        "queries": ["history revenge"],
        "origin": "manual",
        "created_at": NOW,
    } | over


@pytest.mark.postgres
def test_hypothesis_defaults_and_slug_uniqueness(db: Connection) -> None:
    db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis_row()))
    row = db.execute(sa.select(schema.niche_hypotheses)).mappings().one()
    assert (row["status"], row["language"], row["format"], row["finalist"]) == (
        "proposed",
        "en",
        "long",
        False,
    )
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis_row()))


@pytest.mark.postgres
@pytest.mark.parametrize("column,value", [("status", "bogus"), ("origin", "bogus")])
def test_hypothesis_check_constraints(db: Connection, column: str, value: str) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis_row(**{column: value})))


@pytest.mark.postgres
def test_expire_drops_api_data_but_keeps_hypothesis_snapshots(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    hypothesis = hypothesis_row()
    db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis))
    old = NOW - timedelta(days=31)
    db.execute(
        sa.insert(schema.discovery_channel_snapshots).values(
            id=uuid4(),
            run_id=run_id,
            channel_id="UC" + "a" * 22,
            fetched_at=old,
            retain_until=old + timedelta(days=30),
        )
    )
    db.execute(
        sa.insert(schema.hypothesis_channel_hits).values(
            id=uuid4(),
            hypothesis_id=hypothesis["id"],
            run_id=run_id,
            channel_id="UC" + "a" * 22,
            source="search",
            monthly_long_views=1000,
            small_channel=True,
            traction=False,
            retain_until=old + timedelta(days=30),
        )
    )
    db.execute(
        sa.insert(schema.hypothesis_snapshots).values(
            id=uuid4(),
            hypothesis_id=hypothesis["id"],
            run_id=run_id,
            measured_at=old,
            stable_channels=1,
            traction_channels=0,
            median_income_low=Decimal("10"),
            median_income_high=Decimal("20"),
            profile={"estimate": True},
        )
    )
    expire(db, NOW)
    for table, expected in (
        (schema.discovery_channel_snapshots, 0),
        (schema.hypothesis_channel_hits, 0),
        (schema.hypothesis_snapshots, 1),
    ):
        assert db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == expected


@pytest.mark.postgres
def test_seed_channel_primary_key_is_hypothesis_and_channel(db: Connection) -> None:
    hypothesis = hypothesis_row()
    db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis))
    seed = {"hypothesis_id": hypothesis["id"], "channel_id": "UC" + "b" * 22, "added_at": NOW}
    db.execute(sa.insert(schema.hypothesis_seed_channels).values(**seed))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(schema.hypothesis_seed_channels).values(**seed))
