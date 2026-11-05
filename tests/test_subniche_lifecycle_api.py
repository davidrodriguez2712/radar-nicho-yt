# tests/test_subniche_lifecycle_api.py
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.repositories import schema, schema_v1
from nicheradar.subniche_discovery import store
from tests.subniche_samples import NOW, draft
from tests.test_market_api import AUTH, client

pytestmark = pytest.mark.postgres
BASE = "/api/v1/subniches"
ACTIONS = ("approve", "pause", "resume", "archive")
NOT_FOUND = {"code": "not_found", "message": "Hipótesis no encontrada."}
INVALID = {
    "code": "invalid_transition",
    "message": "Esa hipótesis no puede pasar a ese estado.",
}


def seed(
    engine: Engine, status: str = "proposed", slug: str = "history_revenge", **kw: Any
) -> None:
    with engine.begin() as connection:
        store.create_proposed(connection, draft(slug=slug, **kw), NOW)
        if status != "proposed":
            store.approve(connection, slug, NOW)
        if status == "paused":
            store.set_status(connection, slug, "paused")
        if status == "archived":
            store.set_status(connection, slug, "archived")


def row(engine: Engine, slug: str = "history_revenge") -> Any:
    with engine.connect() as connection:
        return (
            connection.execute(
                sa.select(schema.niche_hypotheses).where(schema.niche_hypotheses.c.slug == slug)
            )
            .mappings()
            .one()
        )


def act(api: Any, action: str, slug: str = "history_revenge") -> Any:
    return api.post(f"{BASE}/{slug}/{action}", headers=AUTH)


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    for bad in ({}, {"Authorization": "Bearer wrong"}):
        for action in ACTIONS:
            assert api.post(f"{BASE}/history_revenge/{action}", headers=bad).status_code == 401
        assert api.get(f"{BASE}/history_revenge/approval", headers=bad).status_code == 401
    assert row(isolated_engine)["status"] == "proposed"


def test_approve_a_proposed_hypothesis_activates_it(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    response = act(client(isolated_engine), "approve")
    assert response.status_code == 200
    assert response.json() == {"slug": "history_revenge", "status": "active"}
    stored = row(isolated_engine)
    assert stored["status"] == "active" and stored["approved_at"] is not None


def test_approve_an_active_hypothesis_is_a_conflict_without_changes(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine, "active")
    before = row(isolated_engine)
    response = act(client(isolated_engine), "approve")
    assert response.status_code == 409
    assert response.json() == INVALID
    assert dict(row(isolated_engine)) == dict(before)


def test_pause_and_resume_move_between_active_and_paused(isolated_engine: Engine) -> None:
    seed(isolated_engine, "active")
    api = client(isolated_engine)
    assert act(api, "pause").json() == {"slug": "history_revenge", "status": "paused"}
    assert row(isolated_engine)["status"] == "paused"
    assert act(api, "resume").json() == {"slug": "history_revenge", "status": "active"}
    assert row(isolated_engine)["status"] == "active"


@pytest.mark.parametrize(("status", "action"), [("proposed", "pause"), ("proposed", "resume")])
def test_pausing_or_resuming_a_proposal_is_a_conflict(
    isolated_engine: Engine, status: str, action: str
) -> None:
    seed(isolated_engine, status)
    response = act(client(isolated_engine), action)
    assert response.status_code == 409 and response.json() == INVALID
    assert row(isolated_engine)["status"] == "proposed"


@pytest.mark.parametrize("status", ["proposed", "active", "paused"])
def test_archive_works_from_every_live_state_and_clears_finalist(
    isolated_engine: Engine, status: str
) -> None:
    seed(isolated_engine, status)
    if status == "active":
        with isolated_engine.begin() as connection:
            store.set_finalist(connection, "history_revenge", True)
    response = act(client(isolated_engine), "archive")
    assert response.status_code == 200
    assert response.json() == {"slug": "history_revenge", "status": "archived"}
    assert row(isolated_engine)["finalist"] is False


@pytest.mark.parametrize("action", ACTIONS)
def test_nothing_leaves_archived(isolated_engine: Engine, action: str) -> None:
    seed(isolated_engine, "archived")
    response = act(client(isolated_engine), action)
    assert response.status_code == 409 and response.json() == INVALID
    assert row(isolated_engine)["status"] == "archived"


def test_unknown_slug_is_404_everywhere(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    for action in ACTIONS:
        response = act(api, action, "nope")
        assert response.status_code == 404
        assert response.json() == NOT_FOUND
    response = api.get(f"{BASE}/nope/approval", headers=AUTH)
    assert response.status_code == 404 and response.json() == NOT_FOUND


def test_a_61_character_slug_is_rejected(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    long = "a" * 61
    for action in ACTIONS:
        assert act(api, action, long).status_code == 422
    assert api.get(f"{BASE}/{long}/approval", headers=AUTH).status_code == 422


def test_error_messages_never_carry_the_exception_text(isolated_engine: Engine) -> None:
    seed(isolated_engine, "active")
    response = act(client(isolated_engine), "approve")
    text = response.text
    assert "history_revenge" not in text and "only proposed" not in text and "->" not in text


def test_lifecycle_posts_never_call_the_worker_or_youtube(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nicheradar.subniche_discovery.reader as reader
    import nicheradar.subniche_discovery.worker as worker

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no debe llamarse")

    monkeypatch.setattr(reader, "build_reader", boom)
    monkeypatch.setattr(worker, "build_reader", boom)
    seed(isolated_engine)
    api = client(isolated_engine)
    for action in ("approve", "pause", "resume", "archive"):
        act(api, action)
    assert row(isolated_engine)["status"] == "archived"
    with isolated_engine.connect() as connection:
        calls = connection.execute(
            sa.select(sa.func.count()).select_from(schema_v1.cost_reservations)
        ).scalar_one()
    assert calls == 0


def test_approval_preview_that_does_not_fit_the_daily_cap(isolated_engine: Engine) -> None:
    seed(isolated_engine, queries=("uno dos", "tres cuatro"))
    api = client(
        isolated_engine,
        subniche_search_pages=2,
        subniche_search_units_per_day=100,
        subniche_search_quota_per_run=100,
    )
    response = api.get(f"{BASE}/history_revenge/approval", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "slug": "history_revenge",
        "status": "proposed",
        "queries": 2,
        "pages": 2,
        "search_units_needed": 400,
        "daily_cap": 100,
        "fits": False,
        "cadence_days": 3,
    }
    assert row(isolated_engine)["status"] == "proposed"
    assert act(api, "approve").status_code == 200


def test_approval_preview_that_fits_and_uses_the_smaller_cap(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(
        isolated_engine,
        subniche_search_pages=1,
        subniche_search_units_per_day=1000,
        subniche_search_quota_per_run=1000,
    )
    body = api.get(f"{BASE}/history_revenge/approval", headers=AUTH).json()
    assert body["search_units_needed"] == 100 and body["daily_cap"] == 1000 and body["fits"] is True
    small = client(
        isolated_engine,
        subniche_search_pages=1,
        subniche_search_units_per_day=1000,
        subniche_search_quota_per_run=50,
    )
    body = small.get(f"{BASE}/history_revenge/approval", headers=AUTH).json()
    assert body["daily_cap"] == 50 and body["fits"] is False


def test_approval_preview_reads_without_locking_rows(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    statements: list[str] = []

    def capture(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    sa.event.listen(isolated_engine, "before_cursor_execute", capture)
    try:
        response = api.get(f"{BASE}/history_revenge/approval", headers=AUTH)
    finally:
        sa.event.remove(isolated_engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert any("niche_hypotheses" in statement for statement in statements)
    assert not any("FOR UPDATE" in statement.upper() for statement in statements)


def test_cadence_days_comes_from_the_worker_constant(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    import nicheradar.subniche_discovery.worker as worker

    monkeypatch.setattr(worker, "CADENCE", timedelta(days=5))
    seed(isolated_engine)
    body = client(isolated_engine).get(f"{BASE}/history_revenge/approval", headers=AUTH).json()
    assert body["cadence_days"] == 5
