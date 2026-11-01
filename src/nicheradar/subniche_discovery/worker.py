# src/nicheradar/subniche_discovery/worker.py
"""One discovery tick: every 3 days measure new hypotheses and refresh stale finalists."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import ProviderError
from nicheradar.market_intel.context import utcnow
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import discovery_runs as runs
from nicheradar.repositories.schema_v1 import analysis_runs
from nicheradar.subniche_discovery.measure import measure_hypothesis
from nicheradar.subniche_discovery.reader import (
    YouTubeReader,
    build_reader,
    search_units_needed,
)
from nicheradar.subniche_discovery.store import due_hypotheses

CADENCE = timedelta(days=3)
STALE_RUN = timedelta(hours=6)
SUBNICHE_LOCK = 9_320_031


def cadence_open(connection: Connection, now: datetime, timezone: str) -> bool:
    last = (
        connection.execute(select(runs).order_by(runs.c.started_at.desc()).limit(1))
        .mappings()
        .first()
    )
    if last is None:
        return True
    status: str = last["status"]
    started: datetime = last["started_at"]
    zone = ZoneInfo(timezone)
    new_local_day = now.astimezone(zone).date() > started.astimezone(zone).date()
    if status == "running":
        # A young run belongs to a live worker; a stale one died and counts as partial.
        return now - started >= STALE_RUN and new_local_day
    if status == "complete":
        return now - started >= CADENCE
    return new_local_day  # partial or failed: continue the next quota day (daily cap resets)


async def _measure_all(
    engine: Engine,
    reader: YouTubeReader,
    hypotheses: list[dict[str, Any]],
    run_id: Any,
    config: Settings,
    clock: Callable[[], datetime],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    measured = 0
    stats: dict[str, Any] = {"measured": 0, "slugs": []}
    if skipped:
        stats["skipped"] = skipped
    for hypothesis in hypotheses:
        result = await measure_hypothesis(engine, reader, hypothesis, run_id, config, clock())
        if result.get("partial"):
            stats["stopped_reason"] = result["stopped_reason"]
            stats["stopped_slug"] = result["slug"]
            break
        measured += 1
        stats["slugs"].append(result["slug"])
    stats["measured"] = measured
    return stats


def tick_subniche(
    config: Settings,
    engine: Engine | None = None,
    *,
    reader: YouTubeReader | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> dict[str, Any]:
    status: dict[str, Any] = {"service": "subniche", "status": "idle", "mode": config.mode}
    if not config.subniche_enabled:
        return status | {"status": "disabled"}
    if config.mode != "live":
        return status | {"status": "synthetic_mode"}
    if not config.youtube_live_enabled:
        return status | {"status": "youtube_not_enabled"}
    if config.youtube_api_key is None or config.youtube_auth_scope is None:
        return status | {"status": "youtube_not_configured"}
    if config.database_url is None and engine is None:
        return status | {"status": "not_configured"}
    database = engine or database_engine(config)
    now = clock()
    try:
        with database.begin() as connection:
            connection.execute(select(func.pg_advisory_xact_lock(SUBNICHE_LOCK)))
            if not cadence_open(connection, now, config.subniche_quota_timezone):
                return status
            due = due_hypotheses(connection, now)
            if not due:
                return status
            cap = min(config.subniche_search_units_per_day, config.subniche_search_quota_per_run)
            fitting: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for hypothesis in due:
                needed = search_units_needed(hypothesis["queries"], config)
                if needed > cap:
                    skipped.append(
                        {
                            "slug": hypothesis["slug"],
                            "reason": "insufficient_search_cap",
                            "needed": needed,
                            "cap": cap,
                        }
                    )
                else:
                    fitting.append(hypothesis)
            if not fitting:
                # Never fits, however many days pass: do not open a run or reserve anything.
                return status | {
                    "status": "insufficient_search_cap",
                    "needed": min(item["needed"] for item in skipped),
                    "cap": cap,
                }
            due = fitting
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            analysis_id = insert_record(
                connection,
                "analysis_runs",
                {
                    "profile_id": profile_id,
                    "mode": config.mode,
                    "trigger": "subniche",
                    "status": "queued",
                    "configuration": {},
                },
            )
            run_id = insert_record(
                connection,
                "discovery_runs",
                {
                    "analysis_run_id": analysis_id,
                    "status": "running",
                    "started_at": now,
                    "stats": {},
                },
            )
        run = {"id": analysis_id, "profile_id": profile_id, "mode": config.mode}
        try:
            active = reader or build_reader(database, config, run, clock)
        except ProviderError as error:
            _finish(database, run_id, analysis_id, "failed", {"error": error.code}, clock())
            return status | {"status": "failed", "error_code": error.code}
        try:
            stats = asyncio.run(_measure_all(database, active, due, run_id, config, clock, skipped))
        except Exception as error:
            _finish_best_effort(
                database, run_id, analysis_id, "failed", {"error": type(error).__name__}, clock()
            )
            raise
        outcome = "partial" if "stopped_reason" in stats else "complete"
        _finish(database, run_id, analysis_id, outcome, stats, clock())
        return (
            status
            | {"status": outcome}
            | {key: value for key, value in stats.items() if key != "slugs"}
        )
    except SQLAlchemyError:
        return status | {"status": "error", "error_code": "database_unavailable"}
    finally:
        if engine is None:
            database.dispose()


def _finish_best_effort(
    engine: Engine,
    run_id: Any,
    analysis_id: Any,
    outcome: str,
    stats: dict[str, Any],
    now: datetime,
) -> None:
    """Close the run rows; a failure here must not mask the error that got us here."""
    try:
        _finish(engine, run_id, analysis_id, outcome, stats, now)
    except Exception:  # noqa: BLE001
        pass


def _finish(
    engine: Engine,
    run_id: Any,
    analysis_id: Any,
    outcome: str,
    stats: dict[str, Any],
    now: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(status=outcome, finished_at=now, stats=stats)
        )
        connection.execute(
            update(analysis_runs)
            .where(analysis_runs.c.id == analysis_id)
            .values(status="completed" if outcome == "complete" else outcome, finished_at=now)
        )
