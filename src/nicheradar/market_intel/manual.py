# src/nicheradar/market_intel/manual.py
"""Manual, bounded run for the live pilot: ignores the schedule pause, never the live gate."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.market_intel.context import RunContext, utcnow
from nicheradar.market_intel.runs import claim_run, ensure_run, get_run
from nicheradar.market_intel.sources.base import ListingSource
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.market_intel.stages import execute_run
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.database import database_engine


def run_once(
    config: Settings,
    engine: Engine | None = None,
    *,
    source: ListingSource | None = None,
    selector: OpenAISelector | None = None,
    clock: Callable[[], datetime] = utcnow,
    label: str = "pilot",
    owner: str | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {"service": "market_intel", "status": "not_ready", "mode": config.mode}
    if config.database_url is None and engine is None:
        return status | {"database": "not_configured"}
    if config.mode == "live" and not config.market_intel_live_enabled:
        return status | {"status": "live_not_enabled"}
    database = engine or database_engine(config)
    worker = owner or f"market-pilot-{uuid4()}"
    now = clock()
    key = f"market_scrape:{label}-{now.strftime('%Y%m%dT%H%M%S')}"
    try:
        with database.begin() as connection:
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            run_id = ensure_run(connection, key, now, mode=config.mode, profile_id=profile_id)
            claimed = claim_run(connection, run_id, worker, now)
            if claimed is None:
                return status | {"status": "busy"}
            analysis = {
                "id": claimed["analysis_run_id"],
                "profile_id": profile_id,
                "mode": config.mode,
            }
        built = build_source(config) if source is None else None
        active = source if source is not None else built
        assert active is not None
        ctx = RunContext(
            engine=database,
            config=config,
            source=active,
            run_id=run_id,
            analysis_run=analysis,
            owner=worker,
            started_at=claimed["started_at"],
            checkpoints=dict(claimed["checkpoints"]),
            selector=selector,
            clock=clock,
        )
        try:
            outcome = execute_run(ctx)
        finally:
            if built is not None:
                built.close()
        with database.connect() as connection:
            run = get_run(connection, run_id)
        return status | {
            "status": outcome,
            "run_key": key,
            "error_code": run["error_code"],
            "stats": run["stats"],
        }
    except SQLAlchemyError:
        return status | {"status": "error", "error_code": "database_unavailable"}
    finally:
        if engine is None:
            database.dispose()
