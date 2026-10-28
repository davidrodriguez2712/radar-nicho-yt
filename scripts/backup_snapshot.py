"""Read-only, exported snapshot guard: bootstrap, pilot, market and flow-research data.

Sent to the existing API container over SSH, never installed in the application.
The caller holds stdin open until pg_dump has consumed this exact snapshot.
"""

import json
import sys
from datetime import datetime

from sqlalchemy import Connection, func, inspect, select

from nicheradar.config import Settings
from nicheradar.repositories import schema as s
from nicheradar.repositories.database import database_engine

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
# Metadatos de las corridas del radar (modo, disparador, estado, configuración, cobertura): no son
# evidencia de proveedores y `market_scrape_runs` las referencia por clave foránea, así que el
# dump debe conservarlas o la restauración falla.
RUN_TABLES = {"analysis_runs"}
REVIEWED_TABLES = BOOTSTRAP_TABLES | PILOT_TABLES | RESEARCH_TABLES | RUN_TABLES

# Evidencia de proveedores y estado operativo del radar (decisión del propietario, 2026-10-26,
# opción A): su esquema se respalda pero sus FILAS NO. Los datos de vidIQ/YouTube se
# regeneran con el radar y pueden tener plazos de retención contractuales. Toda tabla nueva
# debe clasificarse en REVIEWED_TABLES o aquí; si no, el guard falla (`unclassified_table`).
PROVIDER_EVIDENCE_TABLES = frozenset(
    {
        "balance_reconciliations",
        "budget_scenarios",
        "channel_analyses",
        "channel_observations",
        "channels",
        "cohort_memberships",
        "cohorts",
        "cost_ledger",
        "cost_reservations",
        "credit_balances",
        "discovery_cursors",
        "discovery_queries",
        "evaluation_versions",
        "evidence_links",
        "feature_values",
        "jobs",
        "listing_channel_snapshots",
        "opportunities",
        "opportunity_decisions",
        "opportunity_recipe_assignments",
        "opportunity_scoring_configs",
        "provider_cache",
        "provider_requests",
        "ranking_entries",
        "ranking_snapshots",
        "raw_observations",
        "scenario_items",
        "topic_artifact_sources",
        "topic_artifacts",
        "topic_memberships",
        "topics",
        "video_observations",
        "videos",
    }
)


def copied_data_deadline(connection: Connection) -> datetime | None:
    """Earliest `retain_until` among the tables whose rows the dump keeps.

    Self-contained on purpose: this script runs inside the deployed API image, which may not
    carry newer helpers from `services.recovery`."""
    values = [
        value
        for table in s.metadata.tables.values()
        if table.name not in PROVIDER_EVIDENCE_TABLES and "retain_until" in table.c
        if (value := connection.execute(select(func.min(table.c.retain_until))).scalar_one())
        is not None
    ]
    return min(values) if values else None


def inspect_snapshot(connection: Connection) -> dict[str, object]:
    """Fail closed on unclassified tables; provider-evidence rows are reported and left out."""
    tables = set(inspect(connection).get_table_names())
    if tables != set(s.metadata.tables) | {"alembic_version"}:
        raise ValueError("unexpected_schema")
    if tables - REVIEWED_TABLES - PROVIDER_EVIDENCE_TABLES:
        raise ValueError("unclassified_table")
    counts = {}
    excluded_rows = {}
    for name in sorted(tables):
        quoted = connection.dialect.identifier_preparer.quote(name)
        count = connection.exec_driver_sql(f"SELECT count(*) FROM {quoted}").scalar_one()
        if name in PROVIDER_EVIDENCE_TABLES:
            # The dump leaves these rows out, so a restore always sees them empty.
            if count:
                excluded_rows[name] = count
            counts[name] = 0
        else:
            counts[name] = count
    schedules = s.metadata.tables["radar_schedules"]
    policies = s.metadata.tables["provider_policies"]
    if connection.execute(
        select(func.count()).select_from(schedules).where(schedules.c.paused.is_(False))
    ).scalar_one():
        raise ValueError("radar_not_paused")
    # Decision 2026-10-26: a real provider may be enabled. Its evidence rows are left out of the
    # dump and the radar must be paused, so the policy is only reported, not a blocker.
    enabled_providers = sorted(
        connection.execute(
            select(policies.c.provider)
            .where(policies.c.provider != "synthetic", policies.c.status == "enabled")
            .distinct()
        ).scalars()
    )
    market_schedule = s.metadata.tables["market_intel_schedule"]
    if connection.execute(
        select(func.count()).select_from(market_schedule).where(market_schedule.c.paused.is_(False))
    ).scalar_one():
        raise ValueError("market_intel_not_paused")
    revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision != "0018":
        raise ValueError("unreviewed_schema_revision")
    has_pilots = any(counts[name] for name in PILOT_TABLES)
    has_research = any(counts[name] for name in RESEARCH_TABLES)
    scope = "bootstrap" + ("+pilots" if has_pilots else "") + ("+research" if has_research else "")
    if scope == "bootstrap":
        scope = "bootstrap-only"
    # Una copia inmutable no puede conservar evidencia después de su primer vencimiento.
    deadline = copied_data_deadline(connection)
    return {
        "scope": scope,
        "revision": revision,
        "counts": counts,
        "excluded_rows": excluded_rows,
        "enabled_real_providers": enabled_providers,
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
