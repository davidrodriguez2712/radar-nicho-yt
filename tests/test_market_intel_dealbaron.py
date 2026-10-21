# tests/test_market_intel_dealbaron.py
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from nicheradar.config import Settings
from nicheradar.market_intel.contracts import SourceError, channel_id_from_url
from nicheradar.market_intel.sources.dealbaron import (
    USER_AGENT,
    DealBaronSource,
    number,
    parse_cards,
    parse_detail,
)
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.market_intel.sources.synthetic import (
    PER_PAGE,
    load_synthetic_listings,
    render_detail_page,
    render_list_page,
    synthetic_transport,
)

FIXTURES = Path(__file__).parent / "fixtures" / "market_intel"
BASE = "https://dealbaron.test"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,399", Decimal("1399")),
        ("517 000", Decimal("517000")),
        ("4\xa0370\xa0000", Decimal("4370000")),
        ("$ 1 990", Decimal("1990")),
        ("$500 / mo", Decimal("500")),
        ("$1,399.50", Decimal("1399.50")),
        ("", None),
        ("—", None),
        ("Contact the seller", None),
        (None, None),
    ],
)
def test_number_normalization(raw: str | None, expected: Decimal | None) -> None:
    assert number(raw) == expected


def test_channel_id_from_url() -> None:
    url = "https://www.youtube.com/channel/UCFRH2mp_OPkmStP7Z9JBBFw"
    assert channel_id_from_url(url) == "UCFRH2mp_OPkmStP7Z9JBBFw"
    assert channel_id_from_url("https://youtube.com/@handle?si=x") is None
    assert channel_id_from_url(None) is None


def test_parse_real_card_markup() -> None:
    cards = parse_cards((FIXTURES / "real_list_snippet.html").read_text(), BASE)
    assert [card.external_id for card in cards] == ["569798", "543126", "540001"]
    first, second, third = cards
    assert first.title == "CinemaSoulForHer" and first.category == "Movies & Music"
    assert first.price_usd == Decimal("1399") and first.subscribers == 517000
    assert first.income_monthly_usd is None
    assert first.url == f"{BASE}/listing/569798"
    assert second.category == "YouTube shorts & Facebook reels"
    assert second.subscribers == 4_370_000 and second.income_monthly_usd == Decimal("500")


def test_parse_card_with_missing_fields_does_not_fail() -> None:
    third = parse_cards((FIXTURES / "real_list_snippet.html").read_text(), BASE)[2]
    assert third.price_usd is None and third.subscribers is None
    assert third.income_monthly_usd is None and third.title == "Contact Seller Channel"


def test_parse_real_detail_markup() -> None:
    detail = parse_detail((FIXTURES / "real_detail_snippet.html").read_text(), "569798")
    assert detail.title == "CinemaSoulForHer" and detail.category == "Movies & Music"
    assert detail.channel_url == "https://www.youtube.com/channel/UCFRH2mp_OPkmStP7Z9JBBFw"
    assert detail.subscribers == 517000 and detail.price_usd == Decimal("1399")
    assert detail.income_monthly_usd == Decimal("0") and detail.expense_monthly_usd == Decimal("0")
    assert detail.monetization == "unknown" and detail.content_type == "Unique content"
    assert detail.published_text == "5 days ago"
    assert detail.description is not None and "515 000 subscribers" in detail.description


def test_parse_detail_without_title_is_layout_change() -> None:
    with pytest.raises(SourceError) as error:
        parse_detail("<html><body>nothing here</body></html>", "1")
    assert error.value.code == "listing_parse_error"


def test_synthetic_pages_round_trip_through_the_parser() -> None:
    listings = load_synthetic_listings()
    page_one = parse_cards(render_list_page(listings, 1, PER_PAGE), BASE)
    page_two = parse_cards(render_list_page(listings, 2, PER_PAGE), BASE)
    assert len(page_one) == PER_PAGE and len(page_two) == len(listings) - PER_PAGE
    assert parse_cards(render_list_page(listings, 3, PER_PAGE), BASE) == []
    income_card = next(card for card in page_one if card.external_id == "570976")
    assert income_card.income_monthly_usd == Decimal("900")
    detail = parse_detail(render_detail_page(listings[0]), "570976")
    assert detail.expense_monthly_usd == Decimal("100") and detail.monetization == "yes"
    assert detail.channel_url == listings[0]["channel_url"]


def make_source(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_pages: int = 10,
    sleeps: list[float] | None = None,
) -> DealBaronSource:
    record = sleeps if sleeps is not None else []
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)
    return DealBaronSource(
        client, base_url=BASE, max_pages=max_pages, delay_seconds=1.0, sleep=record.append
    )


def test_crawl_is_complete_and_polite() -> None:
    sleeps: list[float] = []
    agents: list[str] = []
    listings = load_synthetic_listings()

    def handler(request: httpx.Request) -> httpx.Response:
        agents.append(request.headers.get("user-agent", ""))
        page = int(request.url.params["page"])
        return httpx.Response(200, text=render_list_page(listings, page, PER_PAGE))

    source = make_source(handler, sleeps=sleeps)
    result = source.crawl()
    assert result.complete and result.pages == 2 and len(result.cards) == len(listings)
    assert sleeps == [1.0, 1.0]
    assert len(agents) == 3  # pages 1, 2 and the empty page 3


def test_crawl_hitting_page_cap_is_incomplete() -> None:
    listings = load_synthetic_listings()

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, text=render_list_page(listings, page, PER_PAGE))

    result = make_source(handler, max_pages=1).crawl()
    assert not result.complete and result.pages == 1 and len(result.cards) == PER_PAGE


@pytest.mark.parametrize(
    ("status", "code"), [(403, "blocked"), (429, "blocked"), (500, "source_unavailable")]
)
def test_crawl_error_codes(status: int, code: str) -> None:
    source = make_source(lambda request: httpx.Response(status, text="no"))
    with pytest.raises(SourceError) as error:
        source.crawl()
    assert error.value.code == code


def test_crawl_layout_change_detection() -> None:
    empty_first_page = make_source(lambda r: httpx.Response(200, text="<html>changed</html>"))
    with pytest.raises(SourceError) as error:
        empty_first_page.crawl()
    assert error.value.code == "layout_changed"
    broken = (
        '<div class="posts group"><div class="post  "><div class="post__more"></div></div></div>'
    )
    with pytest.raises(SourceError) as error:
        make_source(lambda r: httpx.Response(200, text=broken)).crawl()
    assert error.value.code == "layout_changed"


def test_fetch_detail_404_is_none_and_200_parses() -> None:
    listings = load_synthetic_listings()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/listing/570976":
            return httpx.Response(200, text=render_detail_page(listings[0]))
        return httpx.Response(404, text="Not Found")

    source = make_source(handler)
    assert source.fetch_detail("999") is None
    detail = source.fetch_detail("570976")
    assert detail is not None and detail.title == "Calm Money Stories"


def test_synthetic_source_never_leaves_the_process() -> None:
    source = build_source(Settings(mode="synthetic"), sleep=lambda seconds: None)
    result = source.crawl()
    assert result.complete and len(result.cards) == len(load_synthetic_listings())
    assert source.fetch_detail("570976") is not None and source.fetch_detail("1") is None
    assert synthetic_transport() is not None


def test_close_releases_the_http_client() -> None:
    source = build_source(Settings(mode="synthetic"))
    assert not source.client.is_closed
    source.close()
    assert source.client.is_closed


def test_live_client_identifies_itself_without_requests() -> None:
    source = build_source(Settings(mode="live"))
    assert source.client.headers["user-agent"] == USER_AGENT
    assert source.delay == 1.0 and source.base_url == "https://dealbaron.com"


def test_blank_middle_page_without_the_list_container_is_not_the_end() -> None:
    listings = load_synthetic_listings()

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 2:
            return httpx.Response(200, text="<html>Down for maintenance</html>")
        return httpx.Response(200, text=render_list_page(listings, page, PER_PAGE))

    with pytest.raises(SourceError) as error:
        make_source(handler).crawl()
    assert error.value.code == "source_unavailable"
