# tests/test_subniche_catalog.py
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.repositories import schema
from nicheradar.subniche_discovery.aggregate import HitMetrics, build_profile
from nicheradar.subniche_discovery.catalog import (
    PREFIX,
    list_subniches,
    research_label,
    slug_of,
    subniche_detail,
)
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed, set_status
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres


def measured(
    db: Connection, run_id: UUID, slug: str, hits: list[HitMetrics], *, finalist: bool = False
) -> UUID:
    hypothesis_id = create_proposed(db, draft(slug=slug, queries=(f"{slug} words",)), NOW)
    approve(db, slug, NOW)
    if finalist:
        db.execute(
            sa.update(schema.niche_hypotheses)
            .where(schema.niche_hypotheses.c.id == hypothesis_id)
            .values(finalist=True)
        )
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=NOW,
        channels=[(channel("a"), [video(1)])],
        hits=hits,
        profile=build_profile(hits, rpm_source="inherited:x"),
    )
    return hypothesis_id


def request_row(db: Connection, label: str, status: str, at: object) -> UUID:
    request_id = uuid4()
    db.execute(
        sa.insert(schema.flow_research_requests).values(
            id=request_id,
            niche_label=label,
            format="long",
            language="en",
            status=status,
            evidence={},
            attempts=0,
            created_at=at,
            updated_at=at,
            retain_until=NOW + timedelta(days=90),
        )
    )
    return request_id


def test_label_helpers_round_trip_and_reject_other_labels() -> None:
    assert PREFIX == "subniche:" and research_label("a_b") == "subniche:a_b"
    assert slug_of("subniche:a_b") == "a_b" and slug_of("personal_finance") is None


def test_listing_hides_paused_and_archived_unless_asked(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a", traction=True, low="10", high="20")])
    measured(db, run_id, "paused_one", [hit("a")])
    set_status(db, "paused_one", "paused")
    create_proposed(db, draft(slug="fresh_one", queries=("fresh words",)), NOW)
    assert [r["slug"] for r in list_subniches(db)] == ["alive_one", "fresh_one"]
    everything = {r["slug"] for r in list_subniches(db, include_inactive=True)}
    assert everything == {"alive_one", "paused_one", "fresh_one"}


def test_listing_exposes_the_latest_measurement_and_orders_finalists_first(
    db: Connection,
) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "plain_one", [hit("a", traction=True, low="10", high="20")])
    measured(db, run_id, "star_one", [hit("a", low="5", high="9")], finalist=True)
    rows = list_subniches(db)
    assert [r["slug"] for r in rows] == ["star_one", "plain_one"]
    plain = rows[1]["measurement"]
    assert plain["traction_channels"] == 1 and plain["rpm_source"] == "inherited:x"
    assert plain["income_low"] == "10.00" and plain["income_high"] == "20.00"
    assert plain["included"] == 1 and rows[1]["language"] == "en" and rows[1]["format"] == "long"


def test_an_unmeasured_hypothesis_has_no_measurement_and_no_research(db: Connection) -> None:
    create_proposed(db, draft(slug="fresh_one", queries=("fresh words",)), NOW)
    row = list_subniches(db)[0]
    assert row["measurement"] is None and row["research"] is None


def test_the_latest_research_of_each_hypothesis_is_reported(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a")])
    request_row(db, research_label("alive_one"), "rechazado", NOW)
    newest = request_row(db, research_label("alive_one"), "pendiente", NOW + timedelta(hours=1))
    request_row(db, "personal_finance", "listo", NOW)  # del backlog: no cuenta
    research = list_subniches(db)[0]["research"]
    assert research["id"] == newest and research["status"] == "pendiente"


def test_detail_lists_current_channels_with_titles_and_declares_expired_ones(
    db: Connection,
) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a", traction=True, low="100", high="900")])
    detail = subniche_detail(db, "alive_one", NOW)
    assert detail is not None and detail["channels_available"] is True
    first = detail["channels"][0]
    assert (
        first["channel_id"] == "UC" + "a" * 22
        and first["title"] == "Channel a"
        and first["income_high"] == "900.00"
        and first["traction"]
    )
    assert detail["hypothesis"]["slug"] == "alive_one"
    later = subniche_detail(db, "alive_one", NOW + timedelta(days=31))
    assert later is not None and later["channels"] == []
    assert later["channels_available"] is False and later["measurement"] is not None


def test_detail_of_an_unknown_slug_is_none(db: Connection) -> None:
    assert subniche_detail(db, "nope_nope", NOW) is None
