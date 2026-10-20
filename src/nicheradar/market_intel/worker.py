# src/nicheradar/market_intel/worker.py
"""One scraper tick: independent from the radar pause and from the radar queue."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.market_intel.context import RunContext, utcnow
from nicheradar.market_intel.runs import (
    FINISHED,
    claim_run,
    ensure_run,
    ensure_schedule,
    get_schedule,
    run_key,
)
from nicheradar.market_intel.sources.base import ListingSource
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.market_intel.stages import execute_run
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import market_scrape_runs as runs


def tick_market(
    config: Settings,
    engine: Engine | None = None,
    *,
    source: ListingSource | None = None,
    selector: OpenAISelector | None = None,
    clock: Callable[[], datetime] = utcnow,
    owner: str | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {"service": "market_intel", "status": "not_ready", "mode": config.mode}
    if config.database_url is None and engine is None:
        return status | {"database": "not_configured"}
    # Live scraping stays off until the owner reviews the source's Terms of Service.
    if config.mode == "live" and not config.market_intel_live_enabled:
        return status | {"status": "live_not_enabled"}
    database = engine or database_engine(config)
    worker = owner or f"market-worker-{uuid4()}"
    now = clock()
    try:
        with database.begin() as connection:
            ensure_schedule(connection, now)
            schedule = get_schedule(connection, lock=True)
            if schedule["paused"]:
                return status | {"status": "paused", "database": "ready"}
            key = run_key(now, config.timezone)
            existing = connection.execute(
                select(runs.c.status).where(runs.c.run_key == key)
            ).scalar_one_or_none()
            if existing in FINISHED or (existing is None and schedule["next_due_at"] > now):
                return status | {"status": "idle", "database": "ready"}
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            run_id = ensure_run(connection, key, now, mode=config.mode, profile_id=profile_id)
            claimed = claim_run(connection, run_id, worker, now)
            if claimed is None:
                return status | {"status": "busy", "database": "ready"}
            analysis = {
                "id": claimed["analysis_run_id"],
                "profile_id": profile_id,
                "mode": config.mode,
            }
        ctx = RunContext(
            engine=database,
            config=config,
            source=source or build_source(config),
            run_id=run_id,
            analysis_run=analysis,
            owner=worker,
            started_at=claimed["started_at"],
            checkpoints=dict(claimed["checkpoints"]),
            selector=selector,
            clock=clock,
        )
        return status | {"status": execute_run(ctx), "run_key": key, "database": "ready"}
    except SQLAlchemyError:
        return status | {"status": "error", "error_code": "database_unavailable"}
    finally:
        if engine is None:
            database.dispose()
