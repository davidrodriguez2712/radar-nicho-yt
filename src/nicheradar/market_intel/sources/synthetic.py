"""Synthetic DealBaron pages for local mode and tests; same markup the parser reads."""

import json
from html import escape
from importlib.resources import files
from typing import Any

import httpx

PER_PAGE = 4


def load_synthetic_listings() -> list[dict[str, Any]]:
    raw = files("nicheradar.data").joinpath("market_intel/synthetic_listings.v1.json").read_text()
    listings: list[dict[str, Any]] = json.loads(raw)
    return listings


def _spaced(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _money(value: int | float) -> str:
    return f"${value:,}"


def render_list_page(listings: list[dict[str, Any]], page: int, per_page: int) -> str:
    chunk = listings[(page - 1) * per_page : page * per_page]
    cards = []
    for item in chunk:
        income = ""
        if item["income"] is not None:
            amount = f"${_spaced(item['income'])} / mo"
            income = (
                f"<p><span>{amount}</span> — income </p>"
                f'<p class="mobile"><span>{amount}</span> </p>'
            )
        link = f'<a href="/listing/{item["id"]}">'
        cards.append(
            '<div class="post  ">'
            '<div class="post__image"><div class="post__more">'
            f"{link}More</a></div></div>"
            '<div class="post__content text-center">'
            f'<div class="post__title">{link}{escape(item["title"])}</a></div>'
            f'<div class="post__type">{escape(item["category"])}</div>'
            f'<div class="post__price">{_money(item["price"])}\n</div>'
            f'<div class="post__data"><p><span>{_spaced(item["subscribers"])}</span>'
            f" —  subscribers\n</p>{income}</div>"
            "</div></div>"
        )
    return '<html><body><div class="posts group">' + "".join(cards) + "</div></body></html>"


def render_detail_page(item: dict[str, Any]) -> str:
    income = item["income"] or 0
    expense = item["expense"] or 0
    return (
        '<html><body><div class="listing-options">'
        f"<span>Published: {escape(item['published'])}</span></div>"
        f'<div class="listing-info"><h1><span >{escape(item["title"])}</span>\n</h1>'
        f'<p class="type">{escape(item["category"])}  |  '
        f'<a href="{escape(item["channel_url"])}" target="_blank">'
        f"{escape(item['channel_url'])}</a></p>"
        '<div class="asset-stats">'
        f"<p>{_spaced(item['subscribers'])} — subscribers</p>"
        f"<p>{_money(income)} — income (month)</p>"
        f"<p>{_money(expense)} — expense (month)</p></div>"
        f'<div class="asset-price">{_money(item["price"])}\n</div></div>'
        '<div class="listing-desc"><p class="title">Listing description:</p>'
        f"<p>{escape(item['description'])}</p></div>"
        '<div class="asset-data">'
        f"<p><span>Monetization enabled:</span> {escape(item['monetization'])}</p>"
        f"<p><span>Content:</span> {escape(item['content'])}</p></div>"
        "</body></html>"
    )


def synthetic_transport() -> httpx.MockTransport:
    listings = load_synthetic_listings()
    by_id = {item["id"]: item for item in listings}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/youtube":
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(200, text=render_list_page(listings, page, PER_PAGE))
        if path.startswith("/listing/"):
            item = by_id.get(path.rsplit("/", 1)[1])
            if item is None:
                return httpx.Response(404, text="Not Found")
            return httpx.Response(200, text=render_detail_page(item))
        return httpx.Response(404, text="Not Found")

    return httpx.MockTransport(handler)
