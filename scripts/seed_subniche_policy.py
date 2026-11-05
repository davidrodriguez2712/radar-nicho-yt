# scripts/seed_subniche_policy.py
"""One-time, idempotent seed: enable the Anthropic policies the hypothesis proposer needs.

Same as scripts/seed_market_evidence_policy.py for the `subniche_hypothesis` data type and the
`hypothesis_proposal` operation. The reading of tweet mentions (`lead_mentions`) is seeded only
with `--include-lead-mentions`: it opens model spending on third-party text and images under the
owner's attestation, which the owner has not made for this use. Does not touch budgets, credits
or schedules.
"""

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery import mentions, propose

EVIDENCE = "owner_attested_personal_use_2026-10-31"
RETENTION_SECONDS = 183 * 86400
OPERATIONS = (("hypothesis_proposal", propose.POLICY_DATA_TYPE),)
LEAD_OPERATIONS = (("lead_mentions", mentions.POLICY_DATA_TYPE),)
USAGES = ("query", "storage", "derived", "llm_processing")


def seed_policies(
    connection: Connection, now: datetime, *, include_lead_mentions: bool = False
) -> int:
    seeded = 0
    operations = OPERATIONS + (LEAD_OPERATIONS if include_lead_mentions else ())
    for operation, data_type in operations:
        for usage in USAGES:
            statement = insert(s.provider_policies).values(
                provider="anthropic",
                operation=operation,
                data_type=data_type,
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
            seeded += 1
    return seeded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-lead-mentions",
        action="store_true",
        help="also seed `lead_mentions` (needs the owner's decision on the attestation)",
    )
    args = parser.parse_args()
    config = Settings()
    if not config.anthropic_enabled:
        raise SystemExit("NR_ANTHROPIC_ENABLED must be true before seeding the policy")
    if config.mode != "live" or not config.radar_paused:
        raise SystemExit("policy activation requires NR_MODE=live and NR_RADAR_PAUSED=true")
    engine = database_engine(config)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        seeded = seed_policies(connection, now, include_lead_mentions=args.include_lead_mentions)
    operations = len(OPERATIONS) + (len(LEAD_OPERATIONS) if args.include_lead_mentions else 0)
    print(json.dumps({"seeded": True, "operations": operations, "usages": seeded}))
    if not args.include_lead_mentions:
        print("lead_mentions NO sembrada: requiere la decisión del propietario sobre la atestación")


if __name__ == "__main__":
    main()
