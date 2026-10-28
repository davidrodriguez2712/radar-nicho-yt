"""Change the weekly USD ceiling of the radar (the only value this script touches).

Usage: set_radar_weekly_budget.py <usd>     (owner decision; run it again to restore the old value)
The profile's monthly ceiling still applies, so the weekly value cannot exceed it.
"""

import json
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, select, update

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

MAXIMUM_WEEKLY_USD = Decimal(20)


def set_weekly_usd(engine: Engine, value: Decimal) -> dict[str, str]:
    if not Decimal(1) <= value <= MAXIMUM_WEEKLY_USD:
        raise SystemExit(f"weekly USD must be between 1 and {MAXIMUM_WEEKLY_USD}")
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(s.creator_profiles).where(s.creator_profiles.c.profile_key == "personal")
            )
            .mappings()
            .one()
        )
        profile = CreatorProfile.model_validate(row["configuration"])
        if value > profile.radar_usd_per_month:
            raise SystemExit("weekly USD cannot exceed the monthly ceiling")
        updated = profile.model_copy(update={"radar_usd_per_week": value})
        connection.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == row["id"])
            .values(configuration=updated.model_dump(mode="json"), version=row["version"] + 1)
        )
    return {"before": str(profile.radar_usd_per_week), "after": str(value)}


def main() -> None:
    config = Settings()
    if config.mode != "live" or not config.radar_paused:
        raise SystemExit("requires NR_MODE=live and NR_RADAR_PAUSED=true")
    try:
        value = Decimal(sys.argv[1])
    except (IndexError, InvalidOperation):
        raise SystemExit("usage: set_radar_weekly_budget.py <usd>") from None
    print(json.dumps(set_weekly_usd(database_engine(config), value)))


if __name__ == "__main__":
    main()
