from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nicheradar.domain.profile import VideoFormat


class Operation(StrEnum):
    EXPLANATION = "explanation"
    CHANNEL_SEARCH = "channel_search"
    CHANNEL_VIDEOS = "channel_videos"
    OUTLIERS = "outliers"
    KEYWORDS = "keyword_research"
    BALANCE = "balance"
    CHANNELS = "channels"
    UPLOADS = "uploads"
    VIDEOS = "videos"
    SEARCH = "search"
    COMMENT_THREADS = "comment_threads"
    VIDEO_CATEGORIES = "video_categories"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Cost(Contract):
    unit: str
    maximum: Decimal | None = Field(default=None, ge=0)
    actual: Decimal | None = Field(default=None, ge=0)
    source: str


class Metric(Contract):
    value: float | None
    unit: str
    definition: str
    consistency: Literal["unknown", "consistent", "inconsistent"] = "unknown"


class Provenance(Contract):
    provider: str
    operation: Operation
    auth_scope: str
    fetched_at: AwareDatetime
    observed_at: AwareDatetime | None = None
    normalization_version: str = "normalized-v1"
    synthetic: bool = False


class Coverage(Contract):
    returned: int = Field(ge=0)
    reported_total: int | None = Field(default=None, ge=0)
    complete: bool = False
    next_page: str | None = None
    selection_method: str
    limitations: tuple[str, ...] = ()


class Channel(Contract):
    id: str
    title: str
    description: str | None = None
    subscribers: int | None = Field(default=None, ge=0)
    country: str | None = None
    content_languages: tuple[str, ...] = ()
    audience_countries: tuple[str, ...] = ()
    faceless: bool | None = None
    category: str | None = None
    uploads_playlist: str | None = None
    subtopics: tuple[str, ...] = ()
    metrics: dict[str, Metric] = Field(default_factory=dict)


class Video(Contract):
    id: str
    channel_id: str
    title: str
    description: str | None = None
    published_at: AwareDatetime | None
    views: int | None = Field(default=None, ge=0)
    format: VideoFormat = VideoFormat.UNKNOWN
    format_evidence: str | None = None
    language: str | None = None
    language_evidence: str | None = None
    category: str | None = None
    subscriber_count: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    metrics: dict[str, Metric] = Field(default_factory=dict)


class Balance(Contract):
    renewable: Decimal | None = Field(ge=0)
    additional: Decimal = Field(ge=0)
    recurring_allocation: Decimal | None = Field(ge=0)
    renews_at: AwareDatetime | None
    unlimited: bool = False
    cycle_started_at: AwareDatetime | None = None


class Batch(Contract):
    provenance: Provenance
    coverage: Coverage
    costs: tuple[Cost, ...]
    channels: tuple[Channel, ...] = ()
    videos: tuple[Video, ...] = ()
    keywords: tuple[dict[str, Any], ...] = ()
    balance: Balance | None = None
    comments: tuple[dict[str, Any], ...] = ()
    category_labels: dict[str, str] = Field(default_factory=dict)


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        *,
        may_have_charged: bool = False,
        retry_safe: bool = False,
        not_sent: bool = False,
    ):
        if not_sent and may_have_charged:
            raise ValueError("a request cannot be unsent and possibly charged")
        super().__init__(code)
        self.code = code
        self.may_have_charged = may_have_charged
        self.retry_safe = retry_safe
        # Only a transport can certify this; retry_safe alone is not a payment receipt.
        self.not_sent = not_sent


class Provider(Protocol):
    name: str
    operations: frozenset[Operation]

    async def fetch(
        self, operation: Operation, parameters: dict[str, Any], now: datetime
    ) -> Batch: ...
