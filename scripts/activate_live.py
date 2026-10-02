"""Configure the already-paused deployment for one bounded scheduled live run."""

import json
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.policies import seed_youtube_policies
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.services.pilot import preflight

config = Settings()
if config.mode != "live" or not config.radar_paused:
    raise SystemExit("live activation requires NR_MODE=live and NR_RADAR_PAUSED=true")
if not config.vidiq_live_enabled or not config.vidiq_pilot_authorized:
    raise SystemExit("live gates are not enabled")
engine = database_engine(config)
now = datetime.now(UTC)
with engine.begin() as connection:
    row = (
        connection.execute(
            select(s.creator_profiles).where(s.creator_profiles.c.profile_key == "personal")
        )
        .mappings()
        .one()
    )
    profile_update: dict[str, object] = {
        "paid_limits_confirmed": True,
        "credits_per_run": 25,
        "credits_per_week": 175,
        "credits_per_cycle": 350,
    }
    if config.llm_enabled:
        profile_update |= {
            "radar_usd_per_operation": "1",
            "radar_usd_per_run": "2",
            "radar_usd_per_week": "5",
            "radar_usd_per_month": "20",
        }
    profile = CreatorProfile.model_validate(row["configuration"]).model_copy(update=profile_update)
    connection.execute(
        update(s.creator_profiles)
        .where(s.creator_profiles.c.id == row["id"])
        .values(configuration=profile.model_dump(mode="json"), version=row["version"] + 1)
    )
    vidiq_usages: tuple[str, ...] = ("query", "storage", "history", "derived", "scheduled")
    if config.llm_enabled:
        vidiq_usages = (*vidiq_usages, "llm_processing")
    for usage in vidiq_usages:
        statement = insert(s.provider_policies).values(
            provider="vidiq",
            operation="*",
            data_type="metadata",
            usage=usage,
            version="owner-personal-use-2026-09-22",
            status="enabled",
            evidence_source="owner_attested_personal_use_2026-09-22",
            retention_seconds=7 * 86400,
            effective_at=now,
        )
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=["provider", "data_type", "operation", "usage", "version"],
                set_={
                    "status": "enabled",
                    "evidence_source": "owner_attested_personal_use_2026-09-22",
                    "retention_seconds": 7 * 86400,
                    "effective_at": now,
                },
            )
        )
    if config.youtube_live_enabled:
        # videos (catalog enrichment) plus every operation channel analysis calls.
        seed_youtube_policies(connection, now, llm_enabled=config.llm_enabled)
    if config.llm_enabled:
        for usage in ("query", "storage", "derived", "llm_processing", "scheduled"):
            statement = insert(s.provider_policies).values(
                provider="openai",
                operation="explanation",
                data_type="explanation",
                usage=usage,
                version="owner-personal-use-2026-09-27",
                status="enabled",
                evidence_source="owner_attested_personal_use_2026-09-27",
                retention_seconds=7 * 86400,
                effective_at=now,
            )
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["provider", "data_type", "operation", "usage", "version"],
                    set_={
                        "status": "enabled",
                        "evidence_source": "owner_attested_personal_use_2026-09-27",
                        "retention_seconds": 7 * 86400,
                        "effective_at": now,
                    },
                )
            )
    schedule = connection.execute(select(s.radar_schedules.c.configuration)).scalar_one()
    connection.execute(
        update(s.radar_schedules).values(
            paused=True,
            next_due_at=now,
            configuration=schedule | {"mode": "live"},
        )
    )
    result = preflight(connection, config, now, scheduled=True)
print(
    json.dumps(
        {
            "ready": result["ready"],
            "blockers": result["blockers"],
            "policies": len(result["policies"]),
            "credits_per_run": result["budget"]["credits_per_run"],
            "credits_per_week": result["budget"]["credits_per_week"],
            "credits_per_cycle": result["budget"]["credits_per_cycle"],
            "youtube_enabled": config.youtube_live_enabled,
            "youtube_quota_per_run": config.youtube_quota_per_run,
            "youtube_quota_per_week": config.youtube_quota_per_week,
            "youtube_quota_per_month": config.youtube_quota_per_month,
            "llm_enabled": config.llm_enabled,
            "llm_model": (
                config.llm_configuration.tariff.model if config.llm_configuration else None
            ),
        }
    )
)
if not result["ready"]:
    raise SystemExit(1)
