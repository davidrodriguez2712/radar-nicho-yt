"""Blocks written by the vision model (contract §4.3-§4.14) and the code-owned `api` block.

Unknown keys are rejected, so a model that sends `derived`, `api` or `meta` fails (V1).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from nicheradar.integrations.contracts import Contract

SCHEMA_VERSION = "listing-evidence-v1"
MAX_IMAGES = 12

Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Note = Annotated[str, StringConstraints(max_length=200)]
RawText = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Percent = Annotated[float, Field(ge=0, le=100)]

Scope = Literal["all", "long", "shorts", "live", "other"]
Legibility = Literal["clear", "partial"]
PeriodKind = Literal[
    "last_7d", "last_28d", "last_90d", "last_365d", "calendar_month", "lifetime", "custom"
]
RiskCode = Literal[
    "identity_mismatch",
    "niche_mismatch",
    "text_contradiction",
    "edited_or_inconsistent_numbers",
    "third_party_watermark",
    "foreign_currency",
    "stale_capture",
    "payments_not_configured",
    "ypp_suspended",
    "limited_ads",
    "recently_monetized",
    "new_channel",
    "declining_traffic",
    "single_video_dependence",
    "declared_income_unsupported",
    "audience_concentrated",
    "shorts_dominant",
    "reused_or_inauthentic_risk",
    "copyright_risk",
    "manager_not_owner",
    "low_sample_period",
]


class Money(Contract):
    value: Decimal = Field(ge=0)
    currency: Currency


# Windows measured back from the capture («Last 28 days»). Studio's mobile dashboard shows no dates
# for them, so their dates may be absent (decision D8); calendar months and custom ranges cannot.
RELATIVE_DAYS: dict[str, int] = {"last_7d": 7, "last_28d": 28, "last_90d": 90, "last_365d": 365}


class Period(Contract):
    kind: PeriodKind
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def coherent(self) -> "Period":
        if (self.start is None) != (self.end is None):
            raise ValueError("period_dates_incomplete")
        if self.start is None and self.kind != "lifetime" and self.kind not in RELATIVE_DAYS:
            raise ValueError("period_dates_required")
        if self.start and self.end and self.start > self.end:
            raise ValueError("period_start_after_end")
        return self

    @property
    def dated(self) -> bool:
        return self.start is not None

    @property
    def days(self) -> int | None:
        if self.kind == "lifetime":
            return None
        if self.start is not None and self.end is not None:
            return (self.end - self.start).days + 1
        return RELATIVE_DAYS.get(self.kind)


class Claim(Contract):
    kind: Literal[
        "income",
        "revenue",
        "views",
        "watch_hours",
        "rpm",
        "cpm",
        "subscribers",
        "audience",
        "growth",
        "other",
    ]
    value: float | None = None
    unit: Literal["usd", "eur", "views", "hours", "percent", "count", "other"]
    period_text: Note | None = None
    snippet: Note


class Image(Contract):
    index: int = Field(ge=0)
    kind: Literal[
        "studio_overview",
        "studio_revenue",
        "studio_analytics_content",
        "studio_audience",
        "studio_traffic",
        "studio_earn_status",
        "adsense_payments",
        "video_detail",
        "other_channel_or_account",
        "chat_or_listing_screenshot",
        "unrelated",
        "unreadable",
    ]
    captured_on: date | None = None
    captured_on_basis: Literal["visible_in_image", "inferred_from_period_end", "unknown"]
    channel_name_visible: Annotated[str, StringConstraints(max_length=120)] | None = None
    currency_visible: Currency | None = None
    ui_language: Annotated[str, StringConstraints(max_length=16)] | None = None
    third_party_watermark: bool = False
    partially_obscured: bool = False
    duplicate_of: int | None = Field(default=None, ge=0)


class IdentityCheck(Contract):
    channel_name_in_images: Annotated[str, StringConstraints(max_length=120)] | None = None
    matches_listing_title: Literal["yes", "no", "cannot_tell"]
    matches_api_channel: Literal["yes", "no", "cannot_tell"]
    manager_not_owner_seen: bool = False
    notes: Note | None = None


class Restriction(Contract):
    kind: Literal[
        "ypp_suspended",
        "limited_ads",
        "demonetized_videos",
        "copyright_claim",
        "strike",
        "reused_content_notice",
        "invalid_traffic",
        "other",
    ]
    detail: Note
    image_index: int = Field(ge=0)


class Monetization(Contract):
    ypp_status: Literal[
        "active", "applied_pending", "base_terms_only", "not_eligible", "suspended", "unknown"
    ]
    adsense_linked: bool | None = None
    payments_status: Literal["configured", "setup_in_progress", "disabled", "unknown"]
    monetized_since: date | None = None
    monetized_since_basis: Literal["visible_in_image", "inferred_first_revenue_day", "unknown"] = (
        "unknown"
    )
    restrictions: tuple[Restriction, ...] = Field(default=(), max_length=10)
    evidence_images: tuple[int, ...] = ()


class Earning(Contract):
    image_index: int = Field(ge=0)
    scope: Scope
    metric: Literal[
        "estimated_revenue",
        "ad_revenue",
        "premium_revenue",
        "membership_revenue",
        "supers_revenue",
        "shopping_revenue",
        "adsense_payment_received",
        "other",
    ]
    period: Period
    amount: Money
    raw_text: RawText
    legibility: Legibility


class ViewMetric(Contract):
    image_index: int = Field(ge=0)
    scope: Scope
    metric: Literal[
        "views",
        "engaged_views",
        "watch_hours",
        "impressions",
        "unique_viewers",
        "subscribers_net",
        "subscribers_gained",
        "subscribers_lost",
    ]
    period: Period
    value: float
    previous_value: float | None = None
    raw_text: RawText
    legibility: Legibility

    @model_validator(mode="after")
    def non_negative(self) -> "ViewMetric":
        if self.metric != "subscribers_net" and self.value < 0:
            raise ValueError("negative_metric")
        return self


class Rate(Contract):
    image_index: int = Field(ge=0)
    metric: Literal[
        "rpm",
        "playback_cpm",
        "cpm",
        "ctr_pct",
        "avg_view_duration_seconds",
        "avg_percentage_viewed",
    ]
    scope: Scope
    period: Period
    value: float = Field(ge=0)
    currency: Currency | None = None
    raw_text: RawText
    legibility: Legibility


class TopContent(Contract):
    rank: int = Field(ge=1)
    title: Annotated[str, StringConstraints(max_length=120)]
    published_on: date | None = None
    views: float | None = Field(default=None, ge=0)
    revenue: Money | None = None
    period: Period
    image_index: int = Field(ge=0)


class CountryShare(Contract):
    code: Country
    pct: Percent


class AgeShare(Contract):
    range: Annotated[str, StringConstraints(max_length=20)]
    pct: Percent


class Gender(Contract):
    male_pct: Percent | None = None
    female_pct: Percent | None = None
    other_pct: Percent | None = None


class Audience(Contract):
    scope: Literal["channel", "video", "unknown"]
    period: Period | None = None
    countries: tuple[CountryShare, ...] = Field(default=(), max_length=10)
    age_groups: tuple[AgeShare, ...] = Field(default=(), max_length=12)
    gender: Gender | None = None
    returning_viewers_pct: Percent | None = None
    image_index: int = Field(ge=0)

    @model_validator(mode="after")
    def shares_fit(self) -> "Audience":
        if sum(item.pct for item in self.countries) > 100.5:
            raise ValueError("country_shares_exceed_100")
        return self


class TrafficSource(Contract):
    source: Literal[
        "browse",
        "suggested",
        "search",
        "external",
        "direct",
        "shorts_feed",
        "notifications",
        "playlists",
        "channel_pages",
        "other",
    ]
    pct: Percent
    scope: Scope
    period: Period
    image_index: int = Field(ge=0)


class Unresolved(Contract):
    topic: Literal[
        "revenue", "views", "rpm", "audience", "monetization", "identity", "dates", "currency"
    ]
    reason: Literal[
        "not_in_images",
        "unreadable",
        "cropped",
        "watermark",
        "ambiguous_currency",
        "ambiguous_period",
        "contradictory",
    ]
    image_index: int | None = Field(default=None, ge=0)
    note: Note | None = None


class RiskFlag(Contract):
    code: RiskCode
    severity: Literal["low", "medium", "high"]
    origin: Literal["model", "code"]
    evidence: tuple[int | Literal["api", "listing_text"], ...] = ()
    note: Note | None = None


class ModelRiskFlag(Contract):
    """A flag the vision model may raise; the code-computed ones live in `derived`."""

    code: Literal[
        "niche_mismatch",
        "text_contradiction",
        "edited_or_inconsistent_numbers",
        "limited_ads",
        "reused_or_inauthentic_risk",
        "copyright_risk",
    ]
    severity: Literal["low", "medium", "high"]
    origin: Literal["model"] = "model"
    evidence: tuple[int | Literal["api", "listing_text"], ...] = ()
    note: Note | None = None


class ModelEvidence(Contract):
    """Everything the vision model is allowed to write."""

    claims: tuple[Claim, ...] = Field(default=(), max_length=30)
    images: tuple[Image, ...] = Field(max_length=MAX_IMAGES)
    identity_check: IdentityCheck
    monetization: Monetization
    earnings: tuple[Earning, ...] = Field(default=(), max_length=20)
    views: tuple[ViewMetric, ...] = Field(default=(), max_length=24)
    rates: tuple[Rate, ...] = Field(default=(), max_length=12)
    top_content: tuple[TopContent, ...] = Field(default=(), max_length=20)
    audience: Audience | None = None
    traffic_sources: tuple[TrafficSource, ...] = Field(default=(), max_length=12)
    unresolved: tuple[Unresolved, ...] = Field(default=(), max_length=20)
    risk_flags: tuple[ModelRiskFlag, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def references_resolve(self) -> "ModelEvidence":
        known = {image.index for image in self.images}
        if len(known) != len(self.images):
            raise ValueError("duplicate_image_index")
        used: list[int | None] = [
            *(e.image_index for e in self.earnings),
            *(v.image_index for v in self.views),
            *(r.image_index for r in self.rates),
            *(t.image_index for t in self.top_content),
            *(t.image_index for t in self.traffic_sources),
            *(r.image_index for r in self.monetization.restrictions),
            *self.monetization.evidence_images,
            *(u.image_index for u in self.unresolved),
            *(image.duplicate_of for image in self.images),
            self.audience.image_index if self.audience else None,
        ]
        for flag in self.risk_flags:
            used.extend(item for item in flag.evidence if isinstance(item, int))
        if any(index is not None and index not in known for index in used):
            raise ValueError("unknown_image_index")
        return self


class RecentVideo(Contract):
    video_id: Annotated[str, StringConstraints(max_length=20)]
    title: Annotated[str, StringConstraints(max_length=120)]
    published_at: datetime
    duration_seconds: int = Field(ge=0)
    views: int = Field(ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)

    @property
    def is_short(self) -> bool:
        return self.duration_seconds <= 180


class ApiEvidence(Contract):
    """From the YouTube Data API; written by the code, never by the model."""

    fetched_at: datetime
    channel_id: str
    title: Annotated[str, StringConstraints(max_length=120)] | None = None
    handle: str | None = None
    country: Country | None = None
    created_at: datetime
    subscribers: int | None = Field(default=None, ge=0)
    total_views: int = Field(ge=0)
    video_count: int = Field(ge=0)
    recent_videos: tuple[RecentVideo, ...] = Field(default=(), max_length=30)
