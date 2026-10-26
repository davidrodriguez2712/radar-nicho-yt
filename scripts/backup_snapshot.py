"""Read-only, exported snapshot guard: bootstrap, pilot, market and flow-research data.

Sent to the existing API container over SSH, never installed in the application.
The caller holds stdin open until pg_dump has consumed this exact snapshot.
"""

import json
import sys

from sqlalchemy import Connection, func, inspect, select

from nicheradar.config import Settings
from nicheradar.repositories import schema as s
from nicheradar.repositories.database import database_engine
from nicheradar.services.recovery import backup_deadline

BOOTSTRAP_TABLES = {
    "alembic_version",
    "creator_profiles",
    "budget_policies",
    "provider_policies",
    "seed_families",
    "production_recipes",
    "production_recipe_defaults",
    "radar_schedules",
    "market_intel_schedule",
    "advertising_benchmarks",
}

# Datos propios del usuario (no datos retenidos de proveedores): se respaldan cuando existen.
# `channel_tokens` solo guarda el SHA-256 de cada token, nunca el token.
PILOT_TABLES = {
    "pilots",
    "pilot_videos",
    "pilot_shorts_measurements",
    "pilot_events",
    "channel_tokens",
}

# Datos de investigación de mercado y de flujo (decisión del propietario, tarea 9.4, opción A):
# se respaldan cifrados en el Mac con retención acotada (ver docs/backup-restore.md).
# La evidencia de proveedores (raw_observations, provider_requests, topics, rankings...) NO está
# revisada y sigue fallando cerrada.
MARKET_TABLES = {
    "market_scrape_runs",
    "marketplace_listings",
    "listing_observations",
    "listing_classifications",
    "listing_verifications",
    "niche_automation_priors",
    "market_niche_snapshots",
    "market_niche_decisions",
}
FLOW_TABLES = {"flow_research_requests", "flow_research_dossiers"}
RESEARCH_TABLES = MARKET_TABLES | FLOW_TABLES
REVIEWED_TABLES = BOOTSTRAP_TABLES | PILOT_TABLES | RESEARCH_TABLES


def inspect_snapshot(connection: Connection) -> dict[str, object]:
    """Fail closed: only reviewed tables may hold rows; provider evidence is not reviewed."""
    tables = set(inspect(connection).get_table_names())
    if tables != set(s.metadata.tables) | {"alembic_version"}:
        raise ValueError("unexpected_schema")
    counts = {}
    for name in sorted(tables):
        quoted = connection.dialect.identifier_preparer.quote(name)
        count = connection.exec_driver_sql(f"SELECT count(*) FROM {quoted}").scalar_one()
        if name not in REVIEWED_TABLES and count:
            raise ValueError("research_data_backup_not_enabled")
        counts[name] = count
    schedules = s.metadata.tables["radar_schedules"]
    policies = s.metadata.tables["provider_policies"]
    if connection.execute(
        select(func.count()).select_from(schedules).where(schedules.c.paused.is_(False))
    ).scalar_one():
        raise ValueError("radar_not_paused")
    if connection.execute(
        select(func.count())
        .select_from(policies)
        .where(policies.c.provider != "synthetic", policies.c.status == "enabled")
    ).scalar_one():
        raise ValueError("real_provider_enabled")
    market_schedule = s.metadata.tables["market_intel_schedule"]
    if connection.execute(
        select(func.count()).select_from(market_schedule).where(market_schedule.c.paused.is_(False))
    ).scalar_one():
        raise ValueError("market_intel_not_paused")
    revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision != "0017":
        raise ValueError("unreviewed_schema_revision")
    has_pilots = any(counts[name] for name in PILOT_TABLES)
    has_research = any(counts[name] for name in RESEARCH_TABLES)
    scope = "bootstrap" + ("+pilots" if has_pilots else "") + ("+research" if has_research else "")
    if scope == "bootstrap":
        scope = "bootstrap-only"
    # Una copia inmutable no puede conservar evidencia después de su primer vencimiento.
    deadline = backup_deadline(connection)
    return {
        "scope": scope,
        "revision": revision,
        "counts": counts,
        "delete_after": deadline.isoformat() if deadline else None,
    }


def main() -> None:
    config = Settings()
    if config.mode not in {"synthetic", "live"} or not config.radar_paused:
        raise ValueError("unsafe_runtime")
    engine = database_engine(config)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL idle_in_transaction_session_timeout = '150s'")
            report = inspect_snapshot(connection)
            report["snapshot"] = connection.exec_driver_sql(
                "SELECT pg_export_snapshot()"
            ).scalar_one()
            print(json.dumps(report), flush=True)
            if sys.stdin.readline().strip() != "release":
                raise ValueError("snapshot_cancelled")
            connection.rollback()
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Neither SQL errors nor Settings validation input may expose credentials.
        print("snapshot_guard_failed", file=sys.stderr)
        sys.exit(1)
