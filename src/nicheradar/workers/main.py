import argparse
import asyncio
import json
import signal
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.retention import expire
from nicheradar.market_intel.worker import tick_market
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.database import database_engine
from nicheradar.workers.health import record
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import QUEUE_LOCK, claim, create_schedule, schedule_due


def provider_calls(pipeline: Pipeline | None) -> int:
    if pipeline is None:
        return 0
    return int(getattr(pipeline.provider, "calls", 0)) + int(getattr(pipeline.youtube, "calls", 0))


def tick(config: Settings, engine: Engine | None = None) -> dict[str, object]:
    status: dict[str, object] = {
        "service": "worker",
        "status": "paused" if config.radar_paused else "not_ready",
        "mode": config.mode,
        "provider_calls": 0,
    }
    if config.database_url is None and engine is None:
        return status | {"database": "not_configured"}
    database = engine or database_engine(config)
    owner = f"worker-{uuid4()}"
    now = datetime.now(UTC)
    pipeline: Pipeline | None = None
    try:
        with database.begin() as connection:
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            create_schedule(connection, profile_id, now, {"mode": config.mode})
            expire(connection, now)
            # Serialize pause, scheduling and claim; do not act on a stale pause read.
            connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
            paused = connection.execute(
                select(s.radar_schedules.c.paused).where(
                    s.radar_schedules.c.schedule_key == "radar"
                )
            ).scalar_one()
            if paused:
                return status | {"status": "paused", "database": "ready"}
            schedule_due(connection, now, globally_paused=False)
            job = claim(
                connection,
                owner,
                now,
                concurrency=config.external_concurrency,
                maximum_attempts=config.worker_maximum_attempts,
            )
        if job:
            pipeline = Pipeline(database, maximum_calls=config.batch_size, settings=config)
            asyncio.run(pipeline.process(job["id"], owner))
            with database.connect() as connection:
                outcome = connection.execute(
                    select(s.jobs.c.status).where(s.jobs.c.id == job["id"])
                ).scalar_one()
            return status | {
                "status": outcome,
                "job_id": str(job["id"]),
                "provider_calls": provider_calls(pipeline),
                "database": "ready",
            }
        return status | {"status": "idle", "database": "ready"}
    except SQLAlchemyError:
        # Attempts in this process, not confirmed charges; settlement may have rolled back.
        return status | {
            "status": "error",
            "error_code": "database_unavailable",
            "provider_calls": provider_calls(pipeline),
        }
    finally:
        if engine is None:
            database.dispose()


MARKET_HEARTBEAT_SECONDS = 60.0


def run_market_tick(config: Settings, status: dict[str, Any], poll_seconds: int) -> dict[str, Any]:
    """Run the scraper tick while keeping the worker heartbeat fresh.

    A full scrape takes far longer than the heartbeat's maximum age; without this the
    orchestrator would see an unhealthy worker and restart it in the middle of a stage.
    """
    result: dict[str, Any] = {}

    def work() -> None:
        try:
            result.update(tick_market(config))
        except Exception:
            result.update(
                {"service": "market_intel", "status": "error", "error_code": "unexpected"}
            )

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(MARKET_HEARTBEAT_SECONDS)
        record(status, poll_seconds)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="NicheRadar worker")
    parser.add_argument(
        "--once", action="store_true", help="Process one tick, respecting persisted pause"
    )
    args = parser.parse_args()
    config = Settings()
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    while not stopped.is_set():
        status = tick(config)
        record(status, config.worker_poll_seconds)
        print(json.dumps(status), flush=True)
        market = run_market_tick(config, status, config.worker_poll_seconds)
        print(json.dumps(market), flush=True)
        if args.once:
            break
        stopped.wait(config.worker_poll_seconds)


if __name__ == "__main__":
    main()
