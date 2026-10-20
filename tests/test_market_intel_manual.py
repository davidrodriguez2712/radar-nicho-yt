# tests/test_market_intel_manual.py
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.market_intel.manual import run_once
from nicheradar.market_intel.runs import ensure_schedule, get_schedule
from nicheradar.repositories.schema import market_scrape_runs, marketplace_listings

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 20, 15, 30, 5, tzinfo=UTC)


def test_manual_run_ignores_the_schedule_pause_and_leaves_it_paused(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as connection:
        ensure_schedule(connection, NOW)
    outcome = run_once(Settings(mode="synthetic"), isolated_engine, clock=lambda: NOW)
    assert outcome["status"] == "succeeded"
    assert outcome["run_key"] == "market_scrape:pilot-20261020T153005"
    assert outcome["stats"]["listings_seen"] == 6
    with isolated_engine.connect() as connection:
        assert get_schedule(connection)["paused"] is True
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(marketplace_listings)
            ).scalar_one()
            == 6
        )
        assert (
            connection.execute(sa.select(market_scrape_runs.c.status)).scalar_one() == "succeeded"
        )


def test_manual_run_still_needs_the_live_terms_gate(isolated_engine: Engine) -> None:
    outcome = run_once(Settings(mode="live"), isolated_engine, clock=lambda: NOW)
    assert outcome["status"] == "live_not_enabled"
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(market_scrape_runs)
            ).scalar_one()
            == 0
        )


def test_manual_run_without_a_database_reports_it() -> None:
    assert run_once(Settings())["database"] == "not_configured"
