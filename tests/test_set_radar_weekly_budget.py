"""La acción del propietario que cambia el tope semanal toca solo ese valor y respeta el mensual."""

from decimal import Decimal

import pytest
from sqlalchemy import Engine, select

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import seed_profile
from scripts.set_radar_weekly_budget import set_weekly_usd
from tests.test_market_intel_classify import funded_profile


def stored(engine: Engine) -> tuple[CreatorProfile, int]:
    with engine.connect() as connection:
        row = connection.execute(
            select(s.creator_profiles.c.configuration, s.creator_profiles.c.version)
        ).one()
    return CreatorProfile.model_validate(row.configuration), row.version


@pytest.fixture
def seeded(isolated_engine: Engine) -> Engine:
    funded = funded_profile().model_copy(update={"radar_usd_per_month": Decimal(20)})
    with isolated_engine.begin() as connection:
        seed_profile(connection, funded, initial_catalog())
    return isolated_engine


@pytest.mark.postgres
def test_it_changes_only_the_weekly_value_and_bumps_the_version(seeded: Engine) -> None:
    before, version = stored(seeded)
    result = set_weekly_usd(seeded, Decimal(15))
    after, new_version = stored(seeded)
    assert result == {"before": "0.20", "after": "15"}
    assert after.radar_usd_per_week == Decimal(15) and new_version == version + 1
    assert after.model_copy(update={"radar_usd_per_week": before.radar_usd_per_week}) == before


@pytest.mark.postgres
@pytest.mark.parametrize("value", [Decimal("0.5"), Decimal(21), Decimal(0)])
def test_it_rejects_values_outside_the_allowed_range(seeded: Engine, value: Decimal) -> None:
    with pytest.raises(SystemExit):
        set_weekly_usd(seeded, value)
    assert stored(seeded)[0].radar_usd_per_week == Decimal("0.20")


@pytest.mark.postgres
def test_it_never_exceeds_the_monthly_ceiling(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_profile(connection, funded_profile(), initial_catalog())  # monthly ceiling is US$1
    with pytest.raises(SystemExit, match="monthly"):
        set_weekly_usd(isolated_engine, Decimal(5))
