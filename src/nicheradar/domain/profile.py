from decimal import Decimal
from enum import StrEnum
from importlib.resources import files
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoFormat(StrEnum):
    SHORTS = "shorts"
    LONG = "long"
    UNKNOWN = "unknown"


class CreatorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "creator-v1"
    language: str = "en"
    formats: tuple[VideoFormat, ...] = (VideoFormat.LONG, VideoFormat.SHORTS)
    monthly_target_usd: Decimal = Field(default=Decimal("100"), ge=0)
    monthly_ceiling_usd: Decimal = Field(default=Decimal("150"), ge=0)
    weekly_hours: Decimal = Field(default=Decimal("15"), gt=0)
    monthly_reserve_usd: Decimal = Field(default=Decimal("0"), ge=0)
    excluded_subscriptions: tuple[str, ...] = ("Claude", "ChatGPT", "Google AI Pro")
    primary_revenue: str = "youtube_advertising"
    production_preference: str = "ai_first_semiautomatic_allowed"
    paid_limits_confirmed: bool = False
    radar_usd_per_operation: Decimal = Field(default=Decimal("0"), ge=0)
    radar_usd_per_run: Decimal = Field(default=Decimal("0"), ge=0)
    radar_usd_per_week: Decimal = Field(default=Decimal("0"), ge=0)
    radar_usd_per_month: Decimal = Field(default=Decimal("0"), ge=0)
    credits_per_run: int = Field(default=5, ge=0)
    credits_per_week: int = Field(default=25, ge=0)
    credits_per_cycle: int = Field(default=100, ge=0)
    channel_analysis_credits_per_run: int = Field(default=50, ge=0)
    channel_analysis_advertising: dict[str, Any] | None = None
    exploration_share: Decimal = Field(default=Decimal("0.25"), gt=0, le=1)
    small_channel_subscribers: int = Field(default=50_000, gt=0)
    selected_refresh_hours: int = Field(default=24, ge=1)
    watching_refresh_hours: int = Field(default=168, ge=1)
    discovery_max_channels: int = Field(default=10, ge=2, le=10)
    discovery_max_expansions: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def consistent_limits(self) -> Self:
        if self.monthly_target_usd > self.monthly_ceiling_usd:
            raise ValueError("monthly target exceeds ceiling")
        if self.monthly_reserve_usd > self.monthly_ceiling_usd:
            raise ValueError("reserve exceeds ceiling")
        if not self.formats or VideoFormat.UNKNOWN in self.formats:
            raise ValueError("at least one confirmed format is required")
        return self


class SeedFamily(BaseModel):
    id: str
    label: str
    queries: tuple[str, ...] = Field(min_length=1)


class SeedCatalog(BaseModel):
    version: str
    families: tuple[SeedFamily, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_families(self) -> Self:
        if len({family.id for family in self.families}) != len(self.families):
            raise ValueError("duplicate family identifier")
        return self


def initial_catalog() -> SeedCatalog:
    return SeedCatalog.model_validate_json(
        files("nicheradar.data").joinpath("seed_families.v1.json").read_text()
    )
