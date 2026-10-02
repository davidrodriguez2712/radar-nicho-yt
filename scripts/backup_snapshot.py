"""Read-only, exported snapshot guard for the initial deployment (no research data).

Sent to the existing API container over SSH, never installed in the application.
The caller holds stdin open until pg_dump has consumed this exact snapshot.
"""

import json
import sys

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
}


def inspect_snapshot(connection: Connection) -> dict[str, object]:
    """Fail closed: this is not yet a backup policy for retained provider data."""
    tables = set(inspect(connection).get_table_names())
    if tables != set(s.metadata.tables) | {"alembic_version"}:
        raise ValueError("unexpected_schema")
    counts = {}
    for name in sorted(tables):
        quoted = connection.dialect.identifier_preparer.quote(name)
        count = connection.exec_driver_sql(f"SELECT count(*) FROM {quoted}").scalar_one()
        if name not in BOOTSTRAP_TABLES and count:
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
    revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision != "0010":
        raise ValueError("unreviewed_schema_revision")
    return {"scope": "bootstrap-only", "revision": revision, "counts": counts}


def main() -> None:
    config = Settings()
    if config.mode != "synthetic" or not config.radar_paused:
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
