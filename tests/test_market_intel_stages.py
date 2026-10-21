# tests/test_market_intel_stages.py
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import (
    CrawlResult,
    ListingCard,
    ListingDetail,
    SourceError,
)
from nicheradar.market_intel.manual import run_once
from nicheradar.market_intel.runs import (
    LEASE_SECONDS,
    STAGES,
    advance,
    claim_run,
    ensure_run,
    get_run,
    get_schedule,
    run_key,
    set_paused,
)
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.market_intel.stages import stage_list
from nicheradar.market_intel.worker import tick_market
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.schema import (
    listing_classifications,
    listing_observations,
    market_intel_schedule,
    market_niche_snapshots,
    market_scrape_runs,
    marketplace_listings,
)
from nicheradar.workers.main import main

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 20, 15, tzinfo=UTC)
DAY = timedelta(days=1)
SYNTHETIC = Settings(
    mode="synthetic", market_intel_detail_cap_per_run=50, market_intel_classify_cap_per_run=50
)


def card(external_id: str) -> ListingCard:
    return ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title=f"Channel {external_id}",
        category="Games",
        price_usd=Decimal("1000"),
        subscribers=10_000,
        income_monthly_usd=Decimal("300"),
    )


def crawl_of(*ids: str, complete: bool = True) -> CrawlResult:
    return CrawlResult(cards=tuple(card(i) for i in ids), pages=1, complete=complete)


class ScriptedSource:
    name = "dealbaron"

    def __init__(
        self,
        *crawls: CrawlResult | SourceError,
        details: dict[str, ListingDetail | SourceError | None] | None = None,
    ) -> None:
        self.crawls = list(crawls)
        self.details = details or {}
        self.crawled = 0
        self.detail_calls: list[str] = []

    def crawl(self) -> CrawlResult:
        self.crawled += 1
        item = self.crawls.pop(0)
        if isinstance(item, SourceError):
            raise item
        return item

    def fetch_detail(self, external_id: str) -> ListingDetail | None:
        self.detail_calls.append(external_id)
        item = (
            self.details[external_id]
            if external_id in self.details
            else ListingDetail(
                external_id=external_id,
                title=f"Channel {external_id}",
                channel_url="https://youtube.com/@x",
            )
        )
        if isinstance(item, SourceError):
            raise item
        return item


def resume(engine: Engine) -> None:
    with engine.begin() as connection:
        set_paused(connection, False, NOW)


def tick(
    engine: Engine,
    source: ScriptedSource | None,
    *,
    days: int = 0,
    config: Settings = SYNTHETIC,
) -> dict[str, Any]:
    return tick_market(
        config, engine, source=source, clock=lambda: NOW + days * DAY, owner="test-worker"
    )


def count(engine: Engine, table: sa.Table) -> int:
    with engine.connect() as connection:
        return int(connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def listing(engine: Engine, external_id: str) -> dict[str, Any]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(marketplace_listings).where(
                    marketplace_listings.c.external_id == external_id
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


def test_full_run_with_the_packaged_synthetic_source(isolated_engine: Engine) -> None:
    assert tick_market(SYNTHETIC, isolated_engine, clock=lambda: NOW)["status"] == "paused"
    resume(isolated_engine)
    first = tick_market(SYNTHETIC, isolated_engine, clock=lambda: NOW, owner="w")
    assert first["status"] == "succeeded"
    assert count(isolated_engine, marketplace_listings) == 6
    assert count(isolated_engine, listing_classifications) == 6
    assert count(isolated_engine, market_niche_snapshots) == 5
    with isolated_engine.connect() as connection:
        fetched = connection.execute(
            sa.select(sa.func.count()).where(marketplace_listings.c.detail_fetched_at.is_not(None))
        ).scalar_one()
        run = connection.execute(sa.select(market_scrape_runs)).mappings().one()
        analysis = connection.execute(sa.select(s.analysis_runs)).mappings().one()
    assert fetched == 6 and run["stage"] == "done" and run["status"] == "succeeded"
    assert set(run["checkpoints"]) == set(STAGES) and run["stats"]["listings_seen"] == 6
    assert analysis["trigger"] == "market_scrape" and analysis["status"] == "succeeded"
    assert count(isolated_engine, s.jobs) == 0  # the radar queue is never involved
    assert tick_market(SYNTHETIC, isolated_engine, clock=lambda: NOW)["status"] == "idle"
    second = tick_market(SYNTHETIC, isolated_engine, clock=lambda: NOW + DAY, owner="w")
    assert second["status"] == "succeeded"
    assert count(isolated_engine, listing_observations) == 12


def test_an_incomplete_crawl_never_changes_disappearance_state(isolated_engine: Engine) -> None:
    source = ScriptedSource(
        crawl_of("A", "B"), crawl_of("A", complete=False), crawl_of("A"), crawl_of("A")
    )
    resume(isolated_engine)
    outcomes = []
    states = []
    for day in range(4):
        outcomes.append(tick(isolated_engine, source, days=day)["status"])
        b = listing(isolated_engine, "B")
        states.append((b["status"], b["consecutive_misses"]))
    assert outcomes == ["succeeded", "partial", "succeeded", "succeeded"]
    assert states == [("active", 0), ("active", 0), ("active", 1), ("disappeared", 2)]


def test_a_blocked_source_pauses_the_scraper(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    source = ScriptedSource(SourceError("blocked"))
    assert tick(isolated_engine, source)["status"] == "blocked"
    with isolated_engine.connect() as connection:
        assert get_schedule(connection)["paused"] is True
        run = connection.execute(sa.select(market_scrape_runs)).mappings().one()
    assert run["status"] == "blocked" and run["error_code"] == "blocked"
    assert tick(isolated_engine, source, days=1)["status"] == "paused"


def test_a_failed_day_is_not_retried_until_tomorrow(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    source = ScriptedSource(SourceError("source_unavailable"), crawl_of("A"))
    assert tick(isolated_engine, source)["status"] == "failed"
    assert tick(isolated_engine, source)["status"] == "idle"
    assert tick(isolated_engine, source, days=1)["status"] == "succeeded"
    with isolated_engine.connect() as connection:
        assert get_schedule(connection)["paused"] is False


def test_a_missing_detail_marks_the_listing_disappeared(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    source = ScriptedSource(crawl_of("A", "B"), details={"B": None})
    assert tick(isolated_engine, source)["status"] == "succeeded"
    assert listing(isolated_engine, "A")["status"] == "active"
    assert listing(isolated_engine, "B")["status"] == "disappeared"


def test_many_unparseable_details_fail_the_run_as_a_layout_change(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    broken = {str(i): SourceError("listing_parse_error") for i in range(1, 5)}
    source = ScriptedSource(crawl_of(*[str(i) for i in range(1, 6)]), details=dict(broken))
    assert tick(isolated_engine, source)["status"] == "failed"
    with isolated_engine.connect() as connection:
        run = connection.execute(sa.select(market_scrape_runs)).mappings().one()
    assert run["error_code"] == "layout_changed"


def test_an_isolated_unparseable_detail_is_tolerated_and_not_retried(
    isolated_engine: Engine,
) -> None:
    resume(isolated_engine)
    ids = [str(i) for i in range(1, 11)]
    source = ScriptedSource(crawl_of(*ids), details={"3": SourceError("listing_parse_error")})
    assert tick(isolated_engine, source)["status"] == "succeeded"
    with isolated_engine.connect() as connection:
        run = connection.execute(sa.select(market_scrape_runs)).mappings().one()
    assert run["checkpoints"]["detail"]["parse_errors"] == 1
    assert run["stats"]["parse_errors"] == 1  # visible in the Operación table
    assert listing(isolated_engine, "3")["detail_fetched_at"] is not None


def test_a_network_error_fails_the_run_instead_of_leaving_it_running(
    isolated_engine: Engine,
) -> None:
    class Unreachable(ScriptedSource):
        def crawl(self) -> CrawlResult:
            raise httpx.ConnectError("no route")

    resume(isolated_engine)
    assert tick(isolated_engine, Unreachable())["status"] == "failed"
    with isolated_engine.connect() as connection:
        run = connection.execute(sa.select(market_scrape_runs)).mappings().one()
    assert run["status"] == "failed" and run["error_code"] == "source_unavailable"


def test_one_unavailable_detail_does_not_freeze_the_run(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    ids = [str(i) for i in range(1, 11)]
    source = ScriptedSource(crawl_of(*ids), details={"3": SourceError("source_unavailable")})
    assert tick(isolated_engine, source)["status"] == "succeeded"
    assert listing(isolated_engine, "3")["detail_fetched_at"] is not None  # not retried forever


def test_a_blocked_detail_still_stops_the_run(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    source = ScriptedSource(crawl_of("1", "2"), details={"1": SourceError("blocked")})
    assert tick(isolated_engine, source)["status"] == "blocked"


def test_live_mode_degrades_without_llm_or_youtube(isolated_engine: Engine) -> None:
    config = Settings(
        mode="live",
        market_intel_live_enabled=True,
        llm_enabled=False,
        youtube_live_enabled=False,
    )
    resume(isolated_engine)
    source = ScriptedSource(crawl_of("A", "B"))
    assert tick(isolated_engine, source, config=config)["status"] == "succeeded"
    with isolated_engine.connect() as connection:
        checkpoints = connection.execute(sa.select(market_scrape_runs.c.checkpoints)).scalar_one()
    assert checkpoints["classify"]["stopped_reason"] == "llm_disabled"
    assert checkpoints["verify"] == {"skipped": "youtube_not_enabled"}
    assert count(isolated_engine, listing_classifications) == 0  # nothing is invented


def test_live_mode_needs_the_explicit_terms_of_service_gate(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    blocked = tick(isolated_engine, ScriptedSource(), config=Settings(mode="live"))
    assert blocked["status"] == "live_not_enabled"
    assert count(isolated_engine, market_scrape_runs) == 0


def test_a_crashed_run_resumes_from_its_stored_stage(isolated_engine: Engine) -> None:
    resume(isolated_engine)
    source = ScriptedSource(crawl_of("A", "B"))
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run_id = ensure_run(
            connection, run_key(NOW, "America/Lima"), NOW, mode="synthetic", profile_id=profile_id
        )
        claimed = claim_run(connection, run_id, "crashed-worker", NOW)
    assert claimed is not None
    ctx = RunContext(
        engine=isolated_engine,
        config=SYNTHETIC,
        source=source,
        run_id=run_id,
        analysis_run={
            "id": claimed["analysis_run_id"],
            "profile_id": profile_id,
            "mode": "synthetic",
        },
        owner="crashed-worker",
        started_at=NOW,
        clock=lambda: NOW,
    )
    checkpoint = stage_list(ctx)
    with isolated_engine.begin() as connection:
        advance(connection, run_id, "crashed-worker", NOW, "list", checkpoint)
    later = NOW + timedelta(seconds=LEASE_SECONDS + 60)  # the worker died; its lease expired
    outcome = tick_market(SYNTHETIC, isolated_engine, source=source, clock=lambda: later, owner="b")
    assert outcome["status"] == "succeeded" and source.crawled == 1
    with isolated_engine.connect() as connection:
        run = get_run(connection, run_id)
    assert run["attempts"] == 2 and run["stage"] == "done"


def test_worker_heartbeat_keeps_beating_while_the_scraper_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beats: list[str] = []

    def slow_scraper(config: Settings) -> dict[str, object]:
        time.sleep(0.35)
        return {"service": "market_intel", "status": "succeeded"}

    monkeypatch.chdir("tests")
    monkeypatch.setattr(
        "nicheradar.workers.main.tick", lambda config: {"status": "paused", "database": "ready"}
    )
    monkeypatch.setattr("nicheradar.workers.main.tick_market", slow_scraper)
    monkeypatch.setattr(
        "nicheradar.workers.main.record", lambda status, interval: beats.append("b")
    )
    monkeypatch.setattr("nicheradar.workers.main.MARKET_HEARTBEAT_SECONDS", 0.1)
    monkeypatch.setattr(sys, "argv", ["nicheradar-worker", "--once"])
    main()
    assert len(beats) >= 3  # one after the radar tick plus at least two during the scrape


def test_worker_main_runs_the_scraper_and_survives_its_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def radar(config: Settings) -> dict[str, object]:
        calls.append("radar")
        return {"service": "worker", "status": "paused"}

    def scraper(config: Settings) -> dict[str, object]:
        calls.append("market")
        raise RuntimeError("private detail that must not be printed")

    monkeypatch.chdir("tests")  # never read the developer's real .env
    monkeypatch.setattr("nicheradar.workers.main.tick", radar)
    monkeypatch.setattr("nicheradar.workers.main.tick_market", scraper)
    monkeypatch.setattr("nicheradar.workers.main.record", lambda status, interval: None)
    monkeypatch.setattr(sys, "argv", ["nicheradar-worker", "--once"])
    main()
    assert calls == ["radar", "market"]
    output = capsys.readouterr().out
    assert '"error_code": "unexpected"' in output and "private detail" not in output


def test_a_second_complete_crawl_the_same_local_day_is_not_a_second_miss(
    isolated_engine: Engine,
) -> None:
    resume(isolated_engine)
    assert tick(isolated_engine, ScriptedSource(crawl_of("A", "B")))["status"] == "succeeded"
    daily = ScriptedSource(crawl_of("A"), crawl_of("A"))
    assert tick(isolated_engine, daily, days=1)["status"] == "succeeded"
    assert listing(isolated_engine, "B")["consecutive_misses"] == 1
    manual = run_once(
        SYNTHETIC, isolated_engine, source=daily, clock=lambda: NOW + DAY + timedelta(hours=1)
    )
    assert manual["status"] == "succeeded"
    assert listing(isolated_engine, "B")["consecutive_misses"] == 1  # still one day of absence
    assert listing(isolated_engine, "B")["status"] == "active"


def test_next_due_counts_from_the_run_start_so_a_long_run_never_drifts(
    isolated_engine: Engine,
) -> None:
    resume(isolated_engine)
    moments = iter(NOW + timedelta(minutes=10 * step) for step in range(1000))
    tick_market(
        SYNTHETIC,
        isolated_engine,
        source=ScriptedSource(crawl_of("A")),
        clock=lambda: next(moments),
        owner="test-worker",
    )
    with isolated_engine.connect() as connection:
        started = connection.execute(sa.select(market_scrape_runs.c.started_at)).scalar_one()
        due = connection.execute(sa.select(market_intel_schedule.c.next_due_at)).scalar_one()
    assert due == started + DAY


def test_a_source_the_tick_built_is_closed_when_the_run_ends(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = build_source(SYNTHETIC)
    monkeypatch.setattr("nicheradar.market_intel.worker.build_source", lambda config: built)
    resume(isolated_engine)
    assert tick(isolated_engine, None)["status"] == "succeeded"
    assert built.client.is_closed


def test_a_source_the_caller_supplied_is_left_open(isolated_engine: Engine) -> None:
    supplied = build_source(SYNTHETIC)
    resume(isolated_engine)
    tick_market(SYNTHETIC, isolated_engine, source=supplied, clock=lambda: NOW, owner="test-worker")
    assert not supplied.client.is_closed
    supplied.close()
