"""Execute one real vidIQ research call in a disposable PostgreSQL cluster."""

import argparse
import asyncio
import json
import subprocess
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, update
from sqlalchemy.engine import URL

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Batch
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.pilot import preflight
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim, enqueue


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def prepare(engine: Any, config: Settings, evidence: str, now: datetime) -> tuple[Any, Any]:
    profile = CreatorProfile(
        paid_limits_confirmed=True,
        credits_per_run=5,
        credits_per_week=5,
        credits_per_cycle=5,
    )
    with engine.begin() as connection:
        if any(
            connection.execute(select(func.count()).select_from(table)).scalar_one()
            for table in (s.creator_profiles, s.analysis_runs, s.provider_requests)
        ):
            raise RuntimeError("pilot database must be empty")
        profile_id = seed_profile(connection, profile, initial_catalog())
        connection.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == profile_id)
            .values(configuration=profile.model_dump(mode="json"))
        )
        for usage in ("query", "storage", "history", "derived"):
            insert_record(
                connection,
                "provider_policies",
                {
                    "provider": "vidiq",
                    "operation": "*",
                    "data_type": "metadata",
                    "usage": usage,
                    "version": "personal-pilot-2026-09-22",
                    "status": "enabled",
                    "effective_at": now,
                    "evidence_source": evidence,
                    "retention_seconds": 7 * 86400,
                },
            )
        readiness = preflight(connection, config, now)
        if not readiness["ready"]:
            raise RuntimeError("pilot preflight blocked: " + ",".join(readiness["blockers"]))
        job_id = enqueue(
            connection,
            profile_id,
            "isolated-vidiq-pilot-20260922",
            now,
            {"maximum_paid_credits": 5, "retention_days": 7},
            mode="live",
        )
        job = claim(connection, "isolated-pilot", now, maximum_attempts=1)
        if job is None or job["id"] != job_id:
            raise RuntimeError("pilot job could not be claimed")
    return profile_id, job_id


def report(
    engine: Any,
    job_id: Any,
    started_at: datetime,
    elapsed: float,
    config: Settings,
    cycle_start_basis: str,
) -> dict[str, Any]:
    with engine.connect() as connection:
        job = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
        run = (
            connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == job["run_id"]))
            .mappings()
            .one()
        )
        requests = (
            connection.execute(
                select(s.provider_requests)
                .where(s.provider_requests.c.run_id == run["id"])
                .order_by(s.provider_requests.c.created_at, s.provider_requests.c.id)
            )
            .mappings()
            .all()
        )
        observations = (
            connection.execute(
                select(s.provider_requests.c.operation, s.raw_observations.c.payload)
                .join(
                    s.raw_observations,
                    s.raw_observations.c.request_id == s.provider_requests.c.id,
                )
                .where(s.provider_requests.c.run_id == run["id"])
                .order_by(s.raw_observations.c.fetched_at, s.raw_observations.c.id)
            )
            .mappings()
            .all()
        )
        confirmed = connection.execute(
            select(func.coalesce(func.sum(s.cost_ledger.c.amount), 0)).where(
                s.cost_ledger.c.request_id.in_(
                    select(s.provider_requests.c.id).where(
                        s.provider_requests.c.run_id == run["id"]
                    )
                ),
                s.cost_ledger.c.unit == "vidiq_credit",
            )
        ).scalar_one()
        unresolved = connection.execute(
            select(func.count())
            .select_from(s.cost_reservations)
            .where(
                s.cost_reservations.c.request_id.in_(
                    select(s.provider_requests.c.id).where(
                        s.provider_requests.c.run_id == run["id"]
                    )
                ),
                s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
            )
        ).scalar_one()

    batches = [(row["operation"], Batch.model_validate(row["payload"])) for row in observations]
    balances = [batch.balance for operation, batch in batches if operation == "balance"]
    balance_report = [
        {
            "renewable": decimal_text(balance.renewable),
            "additional": decimal_text(balance.additional),
            "total": decimal_text(balance.renewable + balance.additional),
            "recurring_allocation": decimal_text(balance.recurring_allocation),
            "renews_at": iso(balance.renews_at),
        }
        for balance in balances
        if balance is not None
    ]
    research = [batch for operation, batch in batches if operation == "channel_search"]
    channels = tuple(channel for batch in research for channel in batch.channels)
    planning = job["checkpoints"].get("planning", {})
    query = job["checkpoints"].get("query", {})
    durations = [
        (row["completed_at"] - row["sent_at"]).total_seconds()
        if row["completed_at"] and row["sent_at"]
        else None
        for row in requests
    ]
    return {
        "pilot": "vidiq-personal-isolated-v1",
        "started_at": iso(started_at),
        "elapsed_seconds": round(elapsed, 3),
        "job_status": job["status"],
        "error_code": job["error_code"],
        "pending_reason": query.get("reason"),
        "provider_calls": len([row for row in requests if row["sent_at"]]),
        "operations": dict(Counter(row["operation"] for row in requests)),
        "request_states": dict(Counter(row["state"] for row in requests)),
        "request_seconds": durations,
        "credits": {
            "confirmed": decimal_text(confirmed),
            "maximum": "5",
            "unresolved_reservations": unresolved,
            "cycle_started_at": iso(config.vidiq_credit_cycle_started_at),
            "cycle_start_basis": cycle_start_basis,
        },
        "cost": {
            "vidiq_credits": decimal_text(confirmed),
            "incremental_usd_purchase": "0",
            "subscription_cost_attribution": "not_measured",
        },
        "balance_snapshots": balance_report,
        "coverage": {
            "family": planning.get("family_key"),
            "channels_returned": sum(batch.coverage.returned for batch in research),
            "channels_reported_total": sum(
                batch.coverage.reported_total or 0 for batch in research
            ),
            "provider_category_matches_family": sum(
                channel.category == planning.get("family_key") for channel in channels
            ),
            "provider_claims_english": sum(
                "en" in channel.content_languages for channel in channels
            ),
            "formats": {
                "long": "not_queried_budget_cap",
                "shorts": "not_queried_budget_cap",
            },
            "analysis": run["coverage"],
        },
        "calibration": {
            "state": "uncalibrated",
            "reason": "no_video_or_cohort_evidence_within_5_credit_cap",
            "references_frozen": False,
        },
        "privacy": {
            "raw_channel_names_in_report": False,
            "raw_channel_ids_in_report": False,
            "raw_query_text_in_report": False,
            "temporary_database": True,
            "retention_days": 7,
        },
    }


async def execute(
    engine: Any, config: Settings, evidence: str, cycle_start_basis: str
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    _, job_id = prepare(engine, config, evidence, started_at)
    started = time.monotonic()
    await Pipeline(engine, settings=config, maximum_calls=4).process(job_id, "isolated-pilot")
    return report(engine, job_id, started_at, time.monotonic() - started, config, cycle_start_basis)


def main() -> None:
    parser = argparse.ArgumentParser(description="Piloto vidIQ aislado de una llamada pagada")
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--cycle-start", required=True)
    parser.add_argument("--cycle-start-basis", required=True)
    parser.add_argument("--auth-scope", default="personal-primary")
    parser.add_argument("--policy-evidence", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    base = Settings()
    config = base.model_copy(
        update={
            "mode": "live",
            "radar_paused": False,
            "vidiq_auth_scope": args.auth_scope,
            "vidiq_connection_validated_at": datetime.now(UTC),
            "vidiq_credit_cycle_started_at": datetime.fromisoformat(
                args.cycle_start.replace("Z", "+00:00")
            ),
            "vidiq_live_enabled": True,
            "vidiq_pilot_authorized": True,
        }
    )
    if config.vidiq_token is None:
        raise SystemExit("NR_VIDIQ_TOKEN is required")
    binary = args.postgres_bin
    with tempfile.TemporaryDirectory(prefix="nr-vidiq-pilot-", dir="/private/tmp") as temporary:
        root = Path(temporary)
        data = root / "data"
        started = False
        engine = None
        try:
            subprocess.run(
                [
                    str(binary / "initdb"),
                    "-D",
                    str(data),
                    "-U",
                    "nicheradar_pilot",
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--encoding=UTF8",
                    "--no-locale",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(binary / "pg_ctl"),
                    "-D",
                    str(data),
                    "-l",
                    str(root / "postgres.log"),
                    "-o",
                    f"-k {root} -h '' -p 55441 -c max_connections=10",
                    "-w",
                    "start",
                ],
                check=True,
                capture_output=True,
            )
            started = True
            url = URL.create(
                "postgresql+psycopg",
                username="nicheradar_pilot",
                database="postgres",
                query={"host": str(root), "port": "55441"},
            )
            engine = create_engine(
                url,
                hide_parameters=True,
                connect_args={"options": "-c timezone=UTC -c statement_timeout=15000"},
            )
            with engine.begin() as connection:
                if inspect(connection).get_table_names():
                    raise RuntimeError("temporary pilot database is not empty")
                migrations = Config("alembic.ini")
                migrations.attributes["connection"] = connection
                command.upgrade(migrations, "head")
            result = asyncio.run(
                execute(engine, config, args.policy_evidence, args.cycle_start_basis)
            )
            args.report.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n"
            )
            print(
                json.dumps(
                    {
                        "status": result["job_status"],
                        "report": str(args.report),
                        "provider_calls": result["provider_calls"],
                        "credits_confirmed": result["credits"]["confirmed"],
                    }
                )
            )
            if (
                result["job_status"] != "partial"
                or result["pending_reason"] != "run_budget_exhausted"
                or result["credits"]["confirmed"] != "5.000000"
                or result["credits"]["unresolved_reservations"] != 0
                or result["operations"].get("channel_search") != 1
            ):
                raise SystemExit("pilot result did not satisfy the bounded-run contract")
        finally:
            if engine is not None:
                engine.dispose()
            if started:
                subprocess.run(
                    [str(binary / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                    check=True,
                    capture_output=True,
                )


if __name__ == "__main__":
    main()
