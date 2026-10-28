"""DealBaron adapter. Pages are server-rendered HTML; parsing uses only the stdlib."""

import re
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Literal

import httpx

from nicheradar.market_intel.contracts import (
    CrawlResult,
    ListingCard,
    ListingDetail,
    SourceError,
)

USER_AGENT = "NicheRadar-MarketIntel/1.0 (+personal research)"
CARD_MARKER = 'class="post__more"'
LIST_CONTAINER = '<div class="posts group">'
_TAGS = re.compile(r"<[^>]+>")
_CARD_SPLIT = re.compile(r'<div class="post[ "]')
_ATTACHMENT = re.compile(r"https://media\.dealbaron\.com/listing-attachments/[A-Za-z0-9_./-]+")


def text(fragment: str) -> str:
    plain = unescape(_TAGS.sub(" ", fragment)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", plain).strip()


def number(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    digits = re.sub(r"[^\d.]", "", raw.replace(",", "").replace("\xa0", "").replace(" ", ""))
    if not digits or digits == ".":
        return None
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _integer(value: Decimal | None) -> int | None:
    return int(value) if value is not None else None


def parse_cards(html: str, base_url: str) -> list[ListingCard]:
    container = html.split(LIST_CONTAINER, 1)
    if len(container) != 2:
        return []
    cards: list[ListingCard] = []
    for block in _CARD_SPLIT.split(container[1])[1:]:
        link = re.search(r'class="post__title">.*?<a href="/listing/(\d+)">(.*?)</a>', block, re.S)
        if link is None:
            continue
        category = re.search(r'class="post__type">(.*?)</div>', block, re.S)
        price = re.search(r'class="post__price">(.*?)</div>', block, re.S)
        data = re.search(r'class="post__data">(.*?)</div>', block, re.S)
        subscribers = income = None
        if data is not None:
            subs = re.search(r"<p><span>([^<]*)</span>\s*—\s*subscribers", data.group(1))
            earn = re.search(r"<p><span>([^<]*)</span>\s*—\s*income", data.group(1))
            subscribers = number(subs.group(1)) if subs else None
            income = number(earn.group(1)) if earn else None
        cards.append(
            ListingCard(
                external_id=link.group(1),
                url=f"{base_url}/listing/{link.group(1)}",
                title=text(link.group(2)),
                category=text(category.group(1)) if category else None,
                price_usd=number(text(price.group(1))) if price else None,
                subscribers=_integer(subscribers),
                income_monthly_usd=income,
            )
        )
    return cards


def _monetization(raw: str | None) -> Literal["yes", "no", "unknown"]:
    value = (raw or "").strip().lower()
    if value.startswith("yes"):
        return "yes"
    if value == "no" or value.startswith("no "):
        return "no"
    return "unknown"


def parse_detail(html: str, external_id: str) -> ListingDetail:
    title = re.search(r"<h1>\s*<span[^>]*>(.*?)</span>", html, re.S)
    if title is None or not text(title.group(1)):
        raise SourceError("listing_parse_error")
    kind = re.search(r'<p class="type">(.*?)</p>', html, re.S)
    category = channel_url = None
    if kind is not None:
        category = text(kind.group(1).split("|")[0]) or None
        link = re.search(r'<a href="([^"]+)"', kind.group(1))
        channel_url = unescape(link.group(1)) if link else None
    stats = re.search(r'<div class="asset-stats">(.*?)</div>', html, re.S)
    subscribers = income = expense = None
    if stats is not None:
        flat = text(stats.group(1))
        subs = re.search(r"([\d\s,.]+)\s*—\s*subscribers", flat)
        earn = re.search(r"([$\d\s,.]+)\s*—\s*income", flat)
        spend = re.search(r"([$\d\s,.]+)\s*—\s*expense", flat)
        subscribers = number(subs.group(1)) if subs else None
        income = number(earn.group(1)) if earn else None
        expense = number(spend.group(1)) if spend else None
    price = re.search(r'class="asset-price">(.*?)</div>', html, re.S)
    description = re.search(
        r'<div class="listing-desc">\s*<p class="title">.*?</p>(.*?)</div>', html, re.S
    )
    monetization = re.search(r"<span>Monetization enabled:</span>\s*([^<]*)", html)
    content = re.search(r"<span>Content:</span>\s*([^<]*)", html)
    published = re.search(r"<span>Published:\s*([^<]*)</span>", html)
    return ListingDetail(
        external_id=external_id,
        title=text(title.group(1)),
        category=category,
        channel_url=channel_url,
        price_usd=number(text(price.group(1))) if price else None,
        subscribers=_integer(subscribers),
        income_monthly_usd=income,
        expense_monthly_usd=expense,
        description=(text(description.group(1))[:2000] or None) if description else None,
        monetization=_monetization(monetization.group(1) if monetization else None),
        content_type=(text(content.group(1)) or None) if content else None,
        published_text=(published.group(1).strip() or None) if published else None,
        attachment_urls=tuple(dict.fromkeys(_ATTACHMENT.findall(html))),
    )


class DealBaronSource:
    name = "dealbaron"

    def __init__(
        self,
        client: httpx.Client,
        *,
        base_url: str,
        max_pages: int,
        delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client, self.base_url = client, base_url.rstrip("/")
        self.max_pages, self.delay, self.sleep = max_pages, delay_seconds, sleep

    def close(self) -> None:
        self.client.close()

    def _get(self, path: str) -> httpx.Response:
        for attempt in range(3):
            response = self.client.get(self.base_url + path)
            if response.status_code == 403:
                raise SourceError("blocked")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    blocked = response.status_code == 429
                    raise SourceError("blocked" if blocked else "source_unavailable")
                self.sleep(self.delay * 2 ** (attempt + 2))
                continue
            return response
        raise SourceError("source_unavailable")  # pragma: no cover

    def crawl(self) -> CrawlResult:
        cards: dict[str, ListingCard] = {}
        pages = 0
        for page in range(1, self.max_pages + 1):
            if page > 1:
                self.sleep(self.delay)
            response = self._get(f"/youtube?created_at=0&page={page}")
            if response.status_code != 200:
                raise SourceError("source_unavailable")
            markers = response.text.count(CARD_MARKER)
            if markers == 0:
                if page == 1:
                    raise SourceError("layout_changed")
                if LIST_CONTAINER not in response.text:
                    # A maintenance or soft rate-limit page is not the end of the list:
                    # treating it as complete would mark thousands of listings as missed.
                    raise SourceError("source_unavailable")
                return CrawlResult(cards=tuple(cards.values()), pages=pages, complete=True)
            parsed = parse_cards(response.text, self.base_url)
            if len(parsed) < markers * 0.8:
                raise SourceError("layout_changed")
            pages += 1
            for card in parsed:
                cards.setdefault(card.external_id, card)
        return CrawlResult(cards=tuple(cards.values()), pages=pages, complete=False)

    def fetch_detail(self, external_id: str) -> ListingDetail | None:
        self.sleep(self.delay)
        response = self._get(f"/listing/{external_id}")
        if response.status_code in (404, 410):
            return None
        if response.status_code != 200:
            raise SourceError("source_unavailable")
        return parse_detail(response.text, external_id)
