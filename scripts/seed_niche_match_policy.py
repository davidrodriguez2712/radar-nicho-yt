"""One-time, idempotent seed: enable the Operation.NICHE_MATCH provider policy so
advertising_match can place real OpenAI calls in live mode. Mirrors activate_live.py's
own "explanation" policy block (same provider, same usages, same upsert shape),
scoped to only this operation -- deliberately NOT re-running the rest of
activate_live.py's budget/credit/schedule resets, which are unrelated to this
specific activation and already applied."""

import json
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

config = Settings()
if not config.llm_enabled:
    raise SystemExit("LLM must be enabled before seeding the niche_match policy")
if config.mode != "live" or not config.radar_paused:
    raise SystemExit("niche_match policy activation requires NR_MODE=live and NR_RADAR_PAUSED=true")
engine = database_engine(config)
now = datetime.now(UTC)
with engine.begin() as connection:
    for usage in ("query", "storage", "derived", "llm_processing"):
        statement = insert(s.provider_policies).values(
            provider="openai",
            operation="niche_match",
            data_type="channel_analysis_niche_match",
            usage=usage,
            version="owner-personal-use-2026-10-03",
            status="enabled",
            evidence_source="owner_attested_personal_use_2026-10-03",
            retention_seconds=7 * 86400,
            effective_at=now,
        )
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=["provider", "data_type", "operation", "usage", "version"],
                set_={
                    "status": "enabled",
                    "evidence_source": "owner_attested_personal_use_2026-10-03",
                    "retention_seconds": 7 * 86400,
                    "effective_at": now,
                },
            )
        )
print(json.dumps({"seeded": True, "operation": "niche_match", "usages": 4}))
