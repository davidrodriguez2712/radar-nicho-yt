# scripts/seed_market_classification_policy.py
"""One-time, idempotent seed: enable the provider policies the market classifier needs.

Mirrors scripts/seed_niche_match_policy.py for the `market_listing_classification` data type.
Does not touch budgets, credits or schedules, and keeps the radar paused.
"""

import json
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.market_intel.classify import POLICY_DATA_TYPE
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

EVIDENCE = "owner_attested_personal_use_2026-10-20"
RETENTION_SECONDS = 183 * 86400


def main() -> None:
    config = Settings()
    if not config.llm_enabled:
        raise SystemExit("LLM must be enabled before seeding the market classification policy")
    if config.mode != "live" or not config.radar_paused:
        raise SystemExit("policy activation requires NR_MODE=live and NR_RADAR_PAUSED=true")
    engine = database_engine(config)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        for usage in ("query", "storage", "derived", "llm_processing"):
            statement = insert(s.provider_policies).values(
                provider="openai",
                operation="niche_match",
                data_type=POLICY_DATA_TYPE,
                usage=usage,
                version="owner-personal-use-2026-10-20",
                status="enabled",
                evidence_source=EVIDENCE,
                retention_seconds=RETENTION_SECONDS,
                effective_at=now,
            )
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["provider", "data_type", "operation", "usage", "version"],
                    set_={
                        "status": "enabled",
                        "evidence_source": EVIDENCE,
                        "retention_seconds": RETENTION_SECONDS,
                        "effective_at": now,
                    },
                )
            )
    print(json.dumps({"seeded": True, "data_type": POLICY_DATA_TYPE, "usages": 4}))


if __name__ == "__main__":
    main()
