# src/nicheradar/web/share.py
"""Pure helpers for «Compartir» (Android share target): find a link and classify it.

Nothing here calls a service or writes: the page only classifies and offers «Proponer».
"""

import re
import unicodedata
from typing import TypedDict
from urllib.parse import parse_qs, quote, urlsplit

from nicheradar.subniche_discovery.inputs import parse_input

LINK_MAX = 500
FIELD_MAX = 8000  # a share field is cut before any scanning; the link itself is cut to LINK_MAX
_HTTP = re.compile(r"https?://\S+", re.IGNORECASE)
_BARE = re.compile(
    r"(?<![\w.@/-])(?:www\.|m\.|mobile\.)?(?:youtube\.com|youtu\.be|x\.com|twitter\.com)(?:/\S*)?",
    re.IGNORECASE,
)
_HANDLE = re.compile(r"@[A-Za-z0-9._-]{3,30}")
_TWEET_HOSTS = frozenset(
    {"x.com", "twitter.com", "mobile.twitter.com", "www.x.com", "www.twitter.com"}
)
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class Classified(TypedDict):
    kind: str
    link: str


def _clean(candidate: str) -> str | None:
    """The candidate cut to LINK_MAX, or None if it carries control/format characters."""
    candidate = candidate[:LINK_MAX]
    if any(unicodedata.category(c) in _BAD_CATEGORIES for c in candidate):
        return None
    return candidate


def _find(value: str) -> str | None:
    value = value[:FIELD_MAX].strip()
    if not value:
        return None
    if _HANDLE.fullmatch(value):
        return _clean(value)
    for pattern in (_HTTP, _BARE):
        if found := pattern.search(value):
            return _clean(found.group(0))
    return None


def extract_link(title: str, text: str, url: str) -> str | None:
    """`url` first, then the first link of `text`, then of `title`; only http(s) or known hosts."""
    for value in (url, text, title):
        if (link := _find(value)) is not None:
            return link
    return None


def _host(link: str) -> str | None:
    """The lower-case host of a link whose authority is a plain host (no userinfo, no port)."""
    candidate = link if re.match(r"https?://", link, re.IGNORECASE) else None
    if candidate is None:
        if _BARE.fullmatch(link) is None:
            return None
        candidate = "https://" + link
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if host is None or port is not None or "@" in parts.netloc or ":" in parts.netloc:
        return None
    return host.lower()


def _youtube_core(link: str) -> str:
    """Host, path and the `v` parameter only: a tweet URL buried in the query must not count."""
    parts = urlsplit(link if "://" in link else "https://" + link)
    v = parse_qs(parts.query).get("v", [""])[0]
    return f"{parts.hostname}{parts.path}" + (f"?v={quote(v, safe='')}" if v else "")


def classify(link: str | None) -> Classified:
    """`{"kind": "channel|video|tweet|unknown|none", "link": ...}`; no network, no writes."""
    if not link:
        return {"kind": "none", "link": ""}
    if _HANDLE.fullmatch(link):
        return {"kind": "channel", "link": link}
    host = _host(link)
    if host in _TWEET_HOSTS:
        return {"kind": "tweet", "link": link}
    if host in _YOUTUBE_HOSTS:
        try:
            parsed = parse_input(_youtube_core(link))
        except ValueError:
            return {"kind": "unknown", "link": link}
        if parsed.kind in ("video", "channel"):
            return {"kind": parsed.kind, "link": link}
    return {"kind": "unknown", "link": link}
