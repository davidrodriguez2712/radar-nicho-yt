# tests/test_web_share.py
"""Compartir desde Android (M29/M30): solo enlaces, solo lectura."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from fastapi.testclient import TestClient

from nicheradar.web import share
from nicheradar.web.app import create_app
from nicheradar.web.deps import safe_next
from tests.web_helpers import PASSWORD, Api, make_client, settings

STATIC = Path(__file__).parent.parent / "src" / "nicheradar" / "web" / "static"
VIDEO = "dQw4w9WgXcQ"
CHANNEL_ID = "UC" + "a" * 22


# --- extract_link -----------------------------------------------------------------


def test_extract_link_prefers_url_when_it_looks_like_a_link() -> None:
    assert share.extract_link("t", "https://x.com/a/status/1", "https://youtu.be/abc") == (
        "https://youtu.be/abc"
    )


def test_extract_link_takes_the_first_link_of_text_when_url_is_empty() -> None:
    text = f"mira esto https://youtu.be/{VIDEO}?si=x y también https://otro.com"
    assert share.extract_link("", text, "") == f"https://youtu.be/{VIDEO}?si=x"


def test_extract_link_falls_back_to_title() -> None:
    assert share.extract_link("https://www.youtube.com/@canal", "sin enlace", "") == (
        "https://www.youtube.com/@canal"
    )


@pytest.mark.parametrize(
    "value",
    ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://x.com/a", "file:///etc/passwd"],
)
def test_extract_link_ignores_non_http_schemes(value: str) -> None:
    assert share.extract_link(value, value, value) is None


def test_extract_link_with_a_bad_url_still_uses_text() -> None:
    assert share.extract_link("", "javascript:alert(1) https://youtu.be/abcdefghijk", "x") == (
        "https://youtu.be/abcdefghijk"
    )


def test_extract_link_clips_to_500_characters() -> None:
    link = share.extract_link("", "", "https://youtu.be/" + "a" * 5000)
    assert link is not None and len(link) == 500


def test_extract_link_empty_everywhere_is_none() -> None:
    assert share.extract_link("", "", "") is None
    assert share.extract_link("   ", "\n", "\t") is None


@pytest.mark.parametrize("bad", ["https://youtu.be/a\x00b", "https://youtu.be/a‮b"])
def test_extract_link_rejects_nul_and_bidi_controls(bad: str) -> None:
    assert share.extract_link("", "", bad) is None
    assert share.extract_link("", bad, "") is None


def test_extract_link_accepts_a_scheme_less_youtube_link_and_a_bare_handle() -> None:
    assert share.extract_link("", "youtube.com/@canal", "") == "youtube.com/@canal"
    assert share.extract_link("", "@canal", "") == "@canal"
    assert share.extract_link("", "//evil.com", "") is None


# --- classify ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("link", "kind"),
    [
        (f"https://youtu.be/{VIDEO}?si=x", "video"),
        (f"https://m.youtube.com/watch?v={VIDEO}", "video"),
        (f"https://www.youtube.com/watch?v={VIDEO}&t=3", "video"),
        (f"https://www.youtube.com/shorts/{VIDEO}", "video"),
        ("https://youtube.com/@canal", "channel"),
        ("https://www.youtube.com/@canal?si=abc", "channel"),
        (f"https://www.youtube.com/channel/{CHANNEL_ID}", "channel"),
        ("@canal", "channel"),
        ("youtube.com/@canal", "channel"),
        ("https://x.com/u/status/123?s=20", "tweet"),
        ("https://twitter.com", "tweet"),
        ("https://mobile.twitter.com/u/status/1", "tweet"),
        ("https://www.x.com/i/status/1", "tweet"),
        ("https://www.twitter.com/u/status/1", "tweet"),
        ("https://x.com/i/status/1", "tweet"),
        ("https://ejemplo.com/pagina", "unknown"),
        ("https://youtube.com.evil.com/@canal", "unknown"),
        ("https://evilx.com/u/status/1", "unknown"),
        ("https://notyoutube.com/watch?v=" + VIDEO, "unknown"),
        ("https://evil.com/?u=youtube.com/@canal", "unknown"),
        ("https://youtube.com.evil.com/youtube.com/@canal", "unknown"),
        ("https://evil.com/youtube.com/@canal", "unknown"),
        (f"https://www.youtube.com/watch?v={VIDEO}&v=AAAAAAAAAAA", "unknown"),
        ("https://evil.com/?u=x.com/a/status/1", "unknown"),
        ("https://youtube.com@evil.com/@canal", "unknown"),
        ("https://youtube.com:8080@evil.com/@canal", "unknown"),
        ("https://www.youtube.com/results?search_query=hola", "unknown"),
        ("//evil.com/@canal", "unknown"),
        ("javascript:alert(1)", "unknown"),
        ("<b>hola</b>", "unknown"),
    ],
)
def test_classify_kinds(link: str, kind: str) -> None:
    assert share.classify(link)["kind"] == kind


def test_classify_none_and_the_link_is_returned() -> None:
    assert share.classify(None) == {"kind": "none", "link": "", "propose": ""}
    assert share.classify("https://x.com/u/status/1") == {
        "kind": "tweet",
        "link": "https://x.com/u/status/1",
        "propose": "",
    }


def test_a_youtube_link_that_embeds_a_tweet_is_not_a_tweet() -> None:
    link = f"https://www.youtube.com/watch?v={VIDEO}&u=x.com/a/status/1"
    assert share.classify(link)["kind"] == "video"


def test_classify_survives_garbage() -> None:
    for junk in ["http://[::1", "https://", "http://", "\x00", "https://a b", "😀" * 600]:
        assert share.classify(junk)["kind"] in {"unknown", "none"}


# --- GET /compartir ---------------------------------------------------------------


def web(api: Api | None = None) -> tuple[TestClient, Api]:
    api = api or Api()
    return make_client(api), api


def page(client: TestClient, **params: str) -> str:
    response = client.get("/compartir", params=params)
    assert response.status_code == 200, response.text
    return str(response.text)


def test_a_video_offers_proponer_with_the_encoded_link() -> None:
    client, api = web()
    link = f"https://youtu.be/{VIDEO}?si=x&t=3"
    html = page(client, title="Un video", text="", url=link)
    assert "Compartido contigo" in html and "Video de YouTube" in html
    href = re.search(r'href="(/subnichos/proponer\?q=[^"]+)"', html)
    assert href, html
    assert parse_qs(urlsplit(href.group(1).replace("&amp;", "&")).query)["q"] == [
        f"https://www.youtube.com/watch?v={VIDEO}"
    ]
    assert "Proponer" in html
    assert api.calls == []


def test_a_channel_in_text_with_an_empty_url_is_proposable() -> None:
    client, _ = web()
    html = page(client, title="", text="Mira https://www.youtube.com/@canal ya", url="")
    assert "Canal de YouTube" in html
    assert f"/subnichos/proponer?q={quote('https://www.youtube.com/@canal', safe='')}" in html


def test_the_proponer_link_leads_to_the_existing_form_with_the_prefilled_input() -> None:
    client, _ = web()
    link = f"https://m.youtube.com/watch?v={VIDEO}"
    html = page(client, url=link)
    target = re.search(r'href="(/subnichos/proponer\?q=[^"]+)"', html)
    assert target
    form = client.get(target.group(1).replace("&amp;", "&"))
    canonical = f"https://www.youtube.com/watch?v={VIDEO}"
    assert form.status_code == 200 and f'value="{canonical}"' in form.text


def test_a_tweet_shows_the_fixed_notice_and_no_action() -> None:
    client, api = web()
    html = page(client, url="https://x.com/usuario/status/180?s=20")
    assert "Tweet de X" in html
    assert (
        "Los enlaces de X todavía no se leen. Copia el canal o el enlace de YouTube que menciona."
        in html
    )
    assert "/subnichos/proponer" not in html and "Leer tweet" not in html
    assert api.calls == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"url": "https://ejemplo.com/x"},
        {"text": "javascript:alert(1)"},
        {"url": "https://youtube.com.evil.com/@canal"},
        {"url": "https://evilx.com/u/status/1"},
        {"text": "//evil.com"},
    ],
)
def test_unknown_or_missing_links_say_so_and_offer_nothing(params: dict[str, str]) -> None:
    client, api = web()
    html = page(client, **params)
    assert "No reconocimos ese enlace." in html or "No se compartió ningún enlace." in html
    assert "/subnichos/proponer" not in html
    assert api.calls == []


def test_no_link_and_unrecognized_link_have_their_own_text() -> None:
    client, _ = web()
    empty = page(client)
    assert "No se compartió ningún enlace." in empty and "Sin enlace" in empty
    assert "No reconocimos ese enlace." not in empty
    other = page(client, url="https://ejemplo.com/x")
    assert "No reconocimos ese enlace." in other and "No se compartió" not in other


def test_the_shared_link_is_escaped_text() -> None:
    client, _ = web()
    link = 'https://ejemplo.com/"><script>alert(1)</script>'
    html = page(client, url=link)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    html = page(client, text="<b>negrita</b> <img src=x onerror=alert(1)>")
    assert "<img src=x" not in html and "<b>negrita</b>" not in html


def test_hostile_inputs_never_give_a_500() -> None:
    client, api = web()
    hostile = [
        {"url": "https://youtu.be/" + "a" * 5000},
        {"text": "x" * 5000},
        {"url": "https://youtu.be/a\x00b"},
        {"url": "https://youtu.be/a‮b", "text": "‮@canal"},
        {"url": "http://[::1", "text": "https://"},
        {"url": "😀" * 3000},
        {"title": "<script>", "text": "?si=x", "url": "?si=x"},
    ]
    for params in hostile:
        response = client.get("/compartir", params=params)
        assert response.status_code == 200, params
        assert "<script>alert" not in response.text
    assert api.calls == []


def test_a_long_link_is_clipped_in_the_page_and_in_the_proponer_query() -> None:
    client, _ = web()
    html = page(client, url="https://youtu.be/" + "a" * 5000)
    assert "a" * 501 not in html
    href = re.search(r'href="(/subnichos/proponer\?q=[^"]+)"', html)
    assert href and len(href.group(1)) < 1700


def test_compartir_does_not_write_or_call_the_api_and_is_get_only() -> None:
    client, api = web()
    page(client, url=f"https://youtu.be/{VIDEO}")
    assert api.calls == []
    assert client.post("/compartir", data={"url": "x"}).status_code == 405


def test_compartir_keeps_the_site_security_headers() -> None:
    client, _ = web()
    response = client.get("/compartir", params={"url": f"https://youtu.be/{VIDEO}"})
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


# --- sin sesión: login y regreso ----------------------------------------------------


def anonymous() -> TestClient:
    return TestClient(create_app(settings()), follow_redirects=False)


def test_without_a_session_it_goes_to_login_and_back_to_the_same_share() -> None:
    anon = anonymous()
    params = {"title": "t", "text": "", "url": f"https://youtu.be/{VIDEO}?si=x"}
    response = anon.get("/compartir", params=params)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/login?next=")
    nxt = parse_qs(urlsplit(location).query)["next"][0]
    assert nxt.startswith("/compartir?") and parse_qs(urlsplit(nxt).query)["url"] == [params["url"]]
    login = anon.post("/login", data={"password": PASSWORD, "next": nxt})
    assert login.status_code == 303 and login.headers["location"] == nxt
    assert anon.get(login.headers["location"]).status_code == 200


@pytest.mark.parametrize(
    "target",
    [
        "https://otro.com",
        "//otro.com",
        "/\\otro.com",
        "/\r\nSet-Cookie: a=b",
        "/\t/otro.com",
        "/a\x00b",
        "/" + "a" * 3000,
        "otro",
        "",
    ],
)
def test_login_return_rejects_external_or_hostile_targets(target: str) -> None:
    assert safe_next(target) == "/"
    response = anonymous().post("/login", data={"password": PASSWORD, "next": target})
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_login_return_keeps_internal_paths_and_never_adds_a_host() -> None:
    assert safe_next("/compartir?url=https%3A%2F%2Fyoutu.be%2Fabc") == (
        "/compartir?url=https%3A%2F%2Fyoutu.be%2Fabc"
    )
    assert safe_next("/compartir#frag") == "/compartir"
    assert safe_next("/a?b=https://evil.com") == "/a?b=https://evil.com"


# --- manifiesto y service worker ----------------------------------------------------


def test_the_manifest_declares_a_get_share_target_without_files() -> None:
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert manifest["share_target"] == {
        "action": "/compartir",
        "method": "GET",
        "params": {"title": "title", "text": "text", "url": "url"},
    }
    assert "files" not in manifest["share_target"].get("params", {})
    assert "enctype" not in manifest["share_target"]
    assert manifest["scope"] == "/" and manifest["start_url"] == "/"


def test_the_manifest_is_served_as_valid_json() -> None:
    response = anonymous().get("/static/manifest.webmanifest")
    assert response.status_code == 200 and "share_target" in response.json()


def test_the_service_worker_still_caches_only_static_files() -> None:
    body = (STATIC / "sw.js").read_text()
    assert "/compartir" not in body and "/api/" not in body
    assert body.count("cache.put") == 1
    branch = body.split('startsWith("/static/")', 1)[1].split('request.mode === "navigate"', 1)[0]
    assert "cache.put" in branch
    precache = re.search(r"const PRECACHE = \[(.*?)\];", body, re.S)
    assert precache
    entries = re.findall(r'"([^"]+)"', precache.group(1))
    assert all(e.startswith("/static/") or e == "/sin-conexión" for e in entries)


# --- lo clasificado es exactamente lo que se propone ---------------------------------


@pytest.mark.parametrize(
    ("link", "kind", "canonical"),
    [
        (f"https://www.youtube.com/watch?v={VIDEO}&u=x.com/a/status/1", "video", None),
        ("https://www.youtube.com/@canal?x=youtu.be/dQw4w9WgXcQ", "channel", None),
        (f"https://youtu.be/{VIDEO}?si=x", "video", f"https://www.youtube.com/watch?v={VIDEO}"),
        ("youtube.com/@canal", "channel", "https://www.youtube.com/@canal"),
        ("@canal", "channel", "https://www.youtube.com/@canal"),
        (
            f"https://youtube.com/channel/{CHANNEL_ID}?a=b",
            "channel",
            f"https://www.youtube.com/channel/{CHANNEL_ID}",
        ),
    ],
)
def test_the_proposed_q_is_canonical_and_parses_to_the_shown_kind(
    link: str, kind: str, canonical: str | None
) -> None:
    from nicheradar.subniche_discovery.inputs import parse_input

    client, _ = web()
    html = page(client, url=link)
    href = re.search(r'href="(/subnichos/proponer\?q=[^"]+)"', html)
    assert href, html
    q = parse_qs(urlsplit(href.group(1).replace("&amp;", "&")).query)["q"][0]
    assert parse_input(q).kind == kind
    assert q.startswith("https://www.youtube.com/") and "?" not in q.replace("watch?v=", "")
    if canonical:
        assert q == canonical
    assert share.classify(link)["propose"] == q


def test_repeated_v_with_different_values_is_not_proposed() -> None:
    client, _ = web()
    html = page(client, url=f"https://www.youtube.com/watch?v={VIDEO}&v=AAAAAAAAAAA")
    assert "/subnichos/proponer" not in html and "No reconocimos ese enlace." in html


# --- M2, M3, M4 -----------------------------------------------------------------------


def test_bare_hosts_need_a_right_boundary() -> None:
    assert share.extract_link("", "youtube.com.evil.com/@canal", "") is None
    assert share.extract_link("", "x.com-evil.net/a", "") is None
    assert share.extract_link("", "youtube.comx", "") is None


def test_the_first_link_is_the_leftmost_one() -> None:
    assert share.extract_link("", "youtube.com/@uno luego https://ejemplo.com/dos", "") == (
        "youtube.com/@uno"
    )
    assert share.extract_link("", "https://ejemplo.com/dos y youtube.com/@uno", "") == (
        "https://ejemplo.com/dos"
    )


@pytest.mark.parametrize("target", ["/a\u202eb", "/a\u3000b", "/a\u2028b", "/a\u200bb"])
def test_login_return_rejects_unicode_format_and_space_characters(target: str) -> None:
    assert safe_next(target) == "/"
