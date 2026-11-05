# tests/test_web_segmented.py
"""Enlace de cada nicho al detalle y conteos del control Nichos | Subnichos (M2 y M9)."""

import html
import re
from urllib.parse import parse_qs, urlsplit

from tests.web_helpers import Api, make_client, niche_item, subniche_item

NICHES = ("GET", "/api/v1/market/niches")
SUBNICHES = ("GET", "/api/v1/subniches")
FLOW = ("GET", "/api/v1/flow-research")


def niches_body(n: int, total: int | None = None) -> tuple[int, dict[str, object]]:
    items = [niche_item(f"nicho {i}") for i in range(n)]
    return 200, {"items": items, "total": n if total is None else total, "limit": 200, "offset": 0}


def subs_body(n: int) -> tuple[int, dict[str, object]]:
    return 200, {"items": [subniche_item(f"sub_{i}") for i in range(n)]}


def api(niches: object, subs: object) -> Api:
    return Api({NICHES: niches, SUBNICHES: subs, FLOW: (200, {"items": []})})  # type: ignore[dict-item]


def control(text: str) -> list[str]:
    found = re.search(r'<div class="segmented">.*?</div>', text, re.S)
    assert found, text
    return re.sub(r"<[^>]+>", "", found.group(0)).split()


def words(text: str) -> str:
    return " ".join(control(text))


def test_niches_screen_shows_both_counts() -> None:
    web = make_client(api(niches_body(6), subs_body(60)))
    assert words(web.get("/nichos").text) == "Nichos 6 Subnichos 60"


def test_subniches_screen_shows_both_counts() -> None:
    web = make_client(api(niches_body(6), subs_body(60)))
    assert words(web.get("/subnichos").text) == "Nichos 6 Subnichos 60"


def test_niches_count_uses_the_api_total_not_the_page() -> None:
    web = make_client(api(niches_body(3, total=250), subs_body(2)))
    assert words(web.get("/subnichos").text) == "Nichos 250 Subnichos 2"


def test_subniches_count_only_active_and_proposed_even_with_inactive_shown() -> None:
    items = [
        subniche_item("a_1"),
        subniche_item("a_2", status="proposed"),
        subniche_item("a_3", status="paused"),
        subniche_item("a_4", status="archived"),
    ]
    web = make_client(api(niches_body(6), (200, {"items": items})))
    assert words(web.get("/subnichos", params={"inactivos": "1"}).text) == "Nichos 6 Subnichos 2"


def test_niches_screen_survives_subniches_down() -> None:
    web = make_client(api(niches_body(6), (503, {"detail": "x"})))
    page = web.get("/nichos")
    assert page.status_code == 200 and page.text.count('class="card"') == 6
    assert words(page.text) == "Nichos 6 Subnichos —"


def test_niches_screen_survives_subniches_malformed() -> None:
    web = make_client(api(niches_body(6), (200, {"items": "mal"})))
    page = web.get("/nichos")
    assert page.status_code == 200 and words(page.text) == "Nichos 6 Subnichos —"


def test_subniches_screen_survives_niches_down() -> None:
    web = make_client(api((503, {"detail": "x"}), subs_body(60)))
    page = web.get("/subnichos")
    assert page.status_code == 200 and page.text.count('class="card"') == 60
    assert words(page.text) == "Nichos — Subnichos 60"


def test_subniches_screen_survives_niches_total_malformed() -> None:
    web = make_client(api((200, {"items": [], "total": "x"}), subs_body(3)))
    page = web.get("/subnichos")
    assert page.status_code == 200 and words(page.text) == "Nichos — Subnichos 3"


def test_htmx_fragments_keep_the_counts() -> None:
    web = make_client(api(niches_body(6), subs_body(60)))
    for path in ("/nichos", "/subnichos"):
        fragment = web.get(path, headers={"HX-Request": "true"}).text
        assert 'hx-swap-oob="true"' in fragment, path
        assert words(fragment) == "Nichos 6 Subnichos 60", path
        assert "<html" not in fragment
    full = web.get("/nichos").text
    assert full.count('class="segmented"') == 1 and "hx-swap-oob" not in full


def test_segment_buttons_are_unchanged() -> None:
    text = make_client(api(niches_body(6), subs_body(60))).get("/nichos").text
    assert 'class="segmented__item segmented__item--on" href="/nichos" aria-current="page"' in text
    assert 'class="segmented__item" href="/subnichos"' in text


def test_niche_name_links_to_the_detail_with_encoded_label() -> None:
    labels = ["a/b", "x&y=z", "other:x", "<script>alert(1)</script>", "ñandú % raro"]
    items = [niche_item(label, "shorts") for label in labels]
    web = make_client(
        api((200, {"items": items, "total": 5, "limit": 200, "offset": 0}), subs_body(1))
    )
    text = web.get("/nichos").text
    assert "<script>alert(1)</script>" not in text
    hrefs = re.findall(r'<a class="card__name" href="([^"]+)">', text)
    assert len(hrefs) == 5
    got = []
    for href in hrefs:
        parts = urlsplit(html.unescape(href))
        assert parts.path == "/nichos/ver" and "<" not in href and " " not in href
        query = parse_qs(parts.query)
        assert query["formato"] == ["shorts"]
        got.append(query["etiqueta"][0])
    assert got == labels
