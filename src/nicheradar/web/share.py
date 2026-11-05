# src/nicheradar/web/share.py
"""Pure helpers for «Compartir» (Android share target): find a link and classify it.

Nothing here calls a service or writes: the page only classifies and offers «Proponer».
"""

import re
import unicodedata
from typing import TypedDict
from urllib.parse import parse_qs, quote, urlsplit

from nicheradar.subniche_discovery.inputs import parse_input
from nicheradar.web.deps import UNSAFE_CATEGORIES

LINK_MAX = 500
FIELD_MAX = 8000  # a share field is cut before any scanning; the link itself is cut to LINK_MAX
_HTTP = re.compile(r"https?://\S+", re.IGNORECASE)
_BARE = re.compile(
    r"(?<![\w.@/-])(?:www\.|m\.|mobile\.)?(?:youtube\.com|youtu\.be|x\.com|twitter\.com)(?![\w.-])(?:/\S*)?",
    re.IGNORECASE,
)
_HANDLE = re.compile(r"@[A-Za-z0-9._-]{3,30}")
_TWEET_HOSTS = frozenset(
    {"x.com", "twitter.com", "mobile.twitter.com", "www.x.com", "www.twitter.com"}
)
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})


class Classified(TypedDict):
    kind: str
    link: str
    propose: str  # canonical YouTube form that «Proponer» sends; "" when nothing is proposable


def _clean(candidate: str) -> str | None:
    """The candidate cut to LINK_MAX, or None if it carries control/format characters."""
    candidate = candidate[:LINK_MAX]
    if any(unicodedata.category(c) in UNSAFE_CATEGORIES for c in candidate):
        return None
    return candidate


def _find(value: str) -> str | None:
    value = value[:FIELD_MAX].strip()
    if not value:
        return None
    if _HANDLE.fullmatch(value):
        return _clean(value)
    matches = [m for m in (_HTTP.search(value), _BARE.search(value)) if m is not None]
    if not matches:
        return None
    return _clean(min(matches, key=lambda m: m.start()).group(0))


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


def _youtube_core(link: str) -> str | None:
    """Host, path and the `v` parameter only: a tweet URL buried in the query must not count.

    A repeated `v` with different values is ambiguous (parse_input and parse_qs disagree): None.
    """
    parts = urlsplit(link if "://" in link else "https://" + link)
    values = set(parse_qs(parts.query).get("v", []))
    if len(values) > 1:
        return None
    v = next(iter(values), "")
    return f"{parts.hostname}{parts.path}" + (f"?v={quote(v, safe='')}" if v else "")


def _canonical(kind: str, value: str) -> str:
    if kind == "video":
        return f"https://www.youtube.com/watch?v={value}"
    if value.startswith("@"):
        return f"https://www.youtube.com/{value}"
    return f"https://www.youtube.com/channel/{value}"


def _unknown(link: str) -> Classified:
    return {"kind": "unknown", "link": link, "propose": ""}


def classify(link: str | None) -> Classified:
    """What the page shows is exactly what «Proponer» sends: `propose` is rebuilt from the parse."""
    if not link:
        return {"kind": "none", "link": "", "propose": ""}
    if _HANDLE.fullmatch(link):
        return {"kind": "channel", "link": link, "propose": _canonical("channel", link)}
    host = _host(link)
    if host in _TWEET_HOSTS:
        return {"kind": "tweet", "link": link, "propose": ""}
    if host in _YOUTUBE_HOSTS:
        core = _youtube_core(link)
        try:
            parsed = parse_input(core) if core is not None else None
        except ValueError:
            return _unknown(link)
        if parsed is not None and parsed.kind in ("video", "channel"):
            propose = _canonical(parsed.kind, parsed.value)
            if parse_input(propose).kind == parsed.kind:
                return {"kind": parsed.kind, "link": link, "propose": propose}
    return _unknown(link)
