# src/nicheradar/market_intel/stages.py
"""The scrape stages and their executor. A failed source never half-applies a crawl."""

import asyncio
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import Connection, func, select

from nicheradar.market_intel.classify import (
    classify_listing,
    format_from_category,
    niche_labels,
    pending_classification,
    save_classification,
    synthetic_classification,
)
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import SourceError
from nicheradar.market_intel.ingest import (
    apply_detail,
    mark_detail_failed,
    mark_detail_gone,
    pending_detail,
    reconcile,
    upsert_cards,
)
from nicheradar.market_intel.niches import build_snapshots
from nicheradar.market_intel.runs import (
    LeaseLost,
    advance,
    advance_schedule,
    finish,
    get_run,
    local_date,
    set_paused,
)
from nicheradar.market_intel.verification import stage_verify
from nicheradar.repositories.schema import market_scrape_runs

MAXIMUM_PARSE_ERROR_SHARE = 0.2
MINIMUM_PARSE_ERRORS = 3
# Soft declines of the LLM that only mean "nothing to do here", not a degraded run.
INFORMATIONAL_STOPS = {"llm_disabled"}


def stage_list(ctx: RunContext) -> dict[str, Any]:
    result = ctx.source.crawl()  # a SourceError leaves the database untouched
    observed_on = local_date(ctx.started_at, ctx.config.timezone)
    with ctx.engine.begin() as connection:
        upserted = upsert_cards(
            connection, ctx.source.name, result.cards, ctx.started_at, observed_on
        )
    checkpoint: dict[str, Any] = {
        "pages": result.pages,
        "cards": len(result.cards),
        "new": upserted.new,
        "price_changed": upserted.price_changed,
        "complete": result.complete,
        "started_at": ctx.started_at.isoformat(),
    }
    if not result.complete:
        checkpoint["partial"] = True
    return checkpoint


def stage_detail(ctx: RunContext) -> dict[str, Any]:
    name = ctx.source.name
    observed_on = local_date(ctx.started_at, ctx.config.timezone)
    with ctx.engine.connect() as connection:
        pending = pending_detail(connection, name, ctx.config.market_intel_detail_cap_per_run)
    fetched = gone = failed = 0
    last_error = "layout_changed"
    for external_id in pending:
        try:
            detail = ctx.source.fetch_detail(external_id)
        except SourceError as error:
            # A single bad listing must not freeze the backlog: it is marked as attempted and
            # retried only if its price changes. A block (403/429) always stops the run.
            if error.code not in ("listing_parse_error", "source_unavailable"):
                raise
            last_error = "layout_changed" if error.code == "listing_parse_error" else error.code
            failed += 1
            with ctx.engine.begin() as connection:
                mark_detail_failed(connection, name, external_id, ctx.clock())
            continue
        with ctx.engine.begin() as connection:
            if detail is None:
                mark_detail_gone(connection, name, external_id, ctx.clock())
                gone += 1
            else:
                apply_detail(connection, name, detail, ctx.clock(), observed_on)
                fetched += 1
    if failed > max(MINIMUM_PARSE_ERRORS, len(pending) * MAXIMUM_PARSE_ERROR_SHARE):
        raise SourceError(last_error)
    return {"requested": len(pending), "fetched": fetched, "gone": gone, "parse_errors": failed}


def stage_reconcile(ctx: RunContext, connection: Connection) -> dict[str, Any]:
    listed = ctx.checkpoints["list"]
    if not listed.get("complete"):
        # Never infer a sale or removal from a crawl that did not reach the end of the list.
        return {"skipped": "crawl_incomplete", "disappeared": 0, "partial": True}
    day = local_date(ctx.started_at, ctx.config.timezone)
    zone = ZoneInfo(ctx.config.timezone)
    day_start = datetime.combine(day, time.min, tzinfo=zone)
    already = connection.execute(
        select(func.count())
        .select_from(market_scrape_runs)
        .where(
            market_scrape_runs.c.id != ctx.run_id,
            market_scrape_runs.c.started_at >= day_start,
            market_scrape_runs.c.started_at < day_start + timedelta(days=1),
            market_scrape_runs.c.checkpoints.has_key("reconcile"),
        )
    ).scalar_one()
    if already:
        # One absence is one day: a second complete crawl the same local day never counts again.
        return {"skipped": "already_reconciled_today", "disappeared": 0}
    started = ctx.started_at.fromisoformat(listed["started_at"])
    return {"disappeared": reconcile(connection, ctx.source.name, started)}


def stage_classify(ctx: RunContext) -> dict[str, Any]:
    with ctx.engine.connect() as connection:
        pending = pending_classification(
            connection, ctx.source.name, ctx.config.market_intel_classify_cap_per_run
        )
        labels = niche_labels(connection)
    outcome: dict[str, Any] = {"pending": len(pending), "classified": 0}
    if not pending:
        return outcome
    if ctx.analysis_run["mode"] != "live":
        with ctx.engine.begin() as connection:
            for item in pending:
                guess = synthetic_classification(item["category"])
                save_classification(
                    connection, item["id"], guess, "synthetic_category_map", ctx.clock()
                )
        return outcome | {"classified": len(pending), "source": "synthetic_category_map"}

    async def classify_all() -> None:
        for item in pending:
            answer = await classify_listing(
                ctx.engine,
                ctx.analysis_run,
                ctx.config,
                item,
                labels,
                ctx.clock(),
                selector=ctx.selector,
            )
            classification = answer["classification"]
            if classification is None:
                outcome["stopped_reason"] = answer["reason"]
                return
            if classification.reason == "incomplete_response":
                outcome["transient_skips"] = outcome.get("transient_skips", 0) + 1
                continue  # a truncated answer says nothing about the listing: retry tomorrow
            if format_from_category(item["category"]) == "shorts":
                classification = classification.model_copy(update={"format": "shorts"})
            with ctx.engine.begin() as connection:
                save_classification(connection, item["id"], classification, "llm", ctx.clock())
            outcome["classified"] += 1

    asyncio.run(classify_all())
    if outcome.get("stopped_reason") not in (None, *INFORMATIONAL_STOPS):
        outcome["partial"] = True
    return outcome


def stage_snapshot(ctx: RunContext) -> dict[str, Any]:
    with ctx.engine.begin() as connection:
        return {"niches": build_snapshots(connection, ctx.clock(), ctx.config.timezone)}


STAGE_FUNCTIONS: dict[str, Callable[[RunContext], dict[str, Any]]] = {
    "list": stage_list,
    "detail": stage_detail,
    "classify": stage_classify,
    "verify": stage_verify,
    "snapshot": stage_snapshot,
}


def _summary(checkpoints: dict[str, Any]) -> dict[str, Any]:
    listed = checkpoints.get("list", {})
    return {
        "pages": listed.get("pages"),
        "listings_seen": listed.get("cards"),
        "new_listings": listed.get("new"),
        "details_fetched": checkpoints.get("detail", {}).get("fetched"),
        "parse_errors": checkpoints.get("detail", {}).get("parse_errors"),
        "disappeared": checkpoints.get("reconcile", {}).get("disappeared"),
        "classified": checkpoints.get("classify", {}).get("classified"),
        "verified": checkpoints.get("verify", {}).get("checked"),
        "niches": checkpoints.get("snapshot", {}).get("niches"),
    }


def execute_run(ctx: RunContext) -> str:
    try:
        while True:
            with ctx.engine.connect() as connection:
                run = get_run(connection, ctx.run_id)
            stage = run["stage"]
            ctx.checkpoints = dict(run["checkpoints"])
            if stage == "done":
                break
            if stage == "reconcile":
                # Not idempotent (it counts misses), so it commits together with its checkpoint.
                with ctx.engine.begin() as connection:
                    checkpoint = stage_reconcile(ctx, connection)
                    advance(connection, ctx.run_id, ctx.owner, ctx.clock(), stage, checkpoint)
                continue
            checkpoint = STAGE_FUNCTIONS[stage](ctx)
            with ctx.engine.begin() as connection:
                advance(connection, ctx.run_id, ctx.owner, ctx.clock(), stage, checkpoint)
        with ctx.engine.begin() as connection:
            final = get_run(connection, ctx.run_id)
            partial = any(item.get("partial") for item in final["checkpoints"].values())
            status = "partial" if partial else "succeeded"
            finish(
                connection,
                ctx.run_id,
                ctx.owner,
                ctx.clock(),
                status=status,
                stats=_summary(final["checkpoints"]),
            )
            advance_schedule(connection, ctx.started_at)
        return status
    except (SourceError, httpx.HTTPError) as error:
        # A network failure is a transient source outage: the day fails and tomorrow retries.
        code = error.code if isinstance(error, SourceError) else "source_unavailable"
        status = "blocked" if code == "blocked" else "failed"
        with ctx.engine.begin() as connection:
            finish(connection, ctx.run_id, ctx.owner, ctx.clock(), status=status, error_code=code)
            if status == "blocked":
                set_paused(connection, True, ctx.clock())
        return status
    except LeaseLost:
        return "lease_lost"
