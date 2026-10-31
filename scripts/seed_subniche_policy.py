# scripts/seed_subniche_policy.py
"""One-time, idempotent seed: enable the Anthropic policies the hypothesis proposer needs.

Same as scripts/seed_market_evidence_policy.py for the `subniche_hypothesis` data type and the
`hypothesis_proposal` operation. Does not touch budgets, credits or schedules.
"""

import json
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery.propose import POLICY_DATA_TYPE

EVIDENCE = "owner_attested_personal_use_2026-10-31"
RETENTION_SECONDS = 183 * 86400


def main() -> None:
    config = Settings()
    if not config.anthropic_enabled:
        raise SystemExit("NR_ANTHROPIC_ENABLED must be true before seeding the policy")
    if config.mode != "live" or not config.radar_paused:
        raise SystemExit("policy activation requires NR_MODE=live and NR_RADAR_PAUSED=true")
    engine = database_engine(config)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        for usage in ("query", "storage", "derived", "llm_processing"):
            statement = insert(s.provider_policies).values(
                provider="anthropic",
                operation="hypothesis_proposal",
                data_type=POLICY_DATA_TYPE,
                usage=usage,
                version="owner-personal-use-2026-10-31",
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
