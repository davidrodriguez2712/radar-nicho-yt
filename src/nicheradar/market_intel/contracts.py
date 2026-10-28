"""Normalized marketplace data. Every figure is seller-declared and may be missing."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import Field

from nicheradar.integrations.contracts import Contract

_CHANNEL_ID = re.compile(r"/channel/(UC[A-Za-z0-9_-]{22})")


class SourceError(Exception):
    """Stable error codes: blocked, source_unavailable, layout_changed, listing_parse_error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ListingCard(Contract):
    external_id: str
    url: str
    title: str
    category: str | None = None
    price_usd: Decimal | None = Field(default=None, ge=0)
    subscribers: int | None = Field(default=None, ge=0)
    income_monthly_usd: Decimal | None = Field(default=None, ge=0)


class ListingDetail(Contract):
    external_id: str
    title: str
    category: str | None = None
    channel_url: str | None = None
    price_usd: Decimal | None = Field(default=None, ge=0)
    subscribers: int | None = Field(default=None, ge=0)
    income_monthly_usd: Decimal | None = Field(default=None, ge=0)
    expense_monthly_usd: Decimal | None = Field(default=None, ge=0)
    description: str | None = None
    monetization: Literal["yes", "no", "unknown"] = "unknown"
    content_type: str | None = None
    published_text: str | None = None
    attachment_urls: tuple[str, ...] = ()


class CrawlResult(Contract):
    cards: tuple[ListingCard, ...]
    pages: int
    complete: bool


def channel_id_from_url(url: str | None) -> str | None:
    match = _CHANNEL_ID.search(url or "")
    return match.group(1) if match else None
