"""Parse what the owner types and resolve it (via the API, never an LLM) into source text."""

import re
from dataclasses import dataclass
from typing import Any, Literal

from nicheradar.subniche_discovery.contracts import normalize_query
from nicheradar.subniche_discovery.reader import YouTubeReader

_VIDEO = re.compile(
    r"(?i:youtube\.com/watch\?(?:[^#\s]*&)?v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})"
)
_CHANNEL_ID = re.compile(r"(?i:youtube\.com/channel/)?(UC[A-Za-z0-9_-]{22})(?:[/?#]|$)")
_HANDLE = re.compile(r"(?:^|(?i:youtube\.com/))(@[A-Za-z0-9._-]{3,30})(?:[/?#]|$)")
_TWEET = re.compile(r"(?i:(?:x|twitter)\.com)/[^/\s]+/status/(\d+)")
_YOUTUBE_HOST = re.compile(r"youtube\.com|youtu\.be", re.IGNORECASE)
MIN_QUERY, MAX_QUERY = 3, 80  # same limits as clean_queries in contracts.py
RECENT_TITLES = 10


@dataclass(frozen=True)
class ParsedInput:
    kind: Literal["query", "video", "channel", "tweet"]
    value: str


def parse_input(raw: str) -> ParsedInput:
    text = raw.strip()
    if match := _TWEET.search(text):
        return ParsedInput("tweet", match.group(1))
    if match := _VIDEO.search(text):
        return ParsedInput("video", match.group(1))
    if "youtube.com/channel/" in text.lower() or re.fullmatch(r"UC[A-Za-z0-9_-]{22}", text):
        found = _CHANNEL_ID.search(text)
        if found:
            return ParsedInput("channel", found.group(1))
    if match := _HANDLE.search(text):
        return ParsedInput("channel", match.group(1))
    if _YOUTUBE_HOST.search(text):
        raise ValueError("unsupported YouTube URL form")
    query = normalize_query(text)
    if not MIN_QUERY <= len(query) <= MAX_QUERY:
        raise ValueError(f"a query needs {MIN_QUERY} to {MAX_QUERY} characters")
    if "http" in query or "www" in query:
        raise ValueError("a query must not be a URL")
    return ParsedInput("query", query)


async def resolve_source(parsed: ParsedInput, reader: YouTubeReader) -> dict[str, Any]:
    """Source text for the proposer. Everything under `untrusted_*` is third-party data."""
    if parsed.kind == "query":
        return {"kind": "query", "untrusted_query": parsed.value}
    title: str | None = None
    if parsed.kind == "video":
        video = await reader.video(parsed.value)
        if video is None:
            raise LookupError(f"video not found: {parsed.value}")
        title = video.title
        found = await reader.channels([video.channel_id])
        channel = found.get(video.channel_id)
    elif parsed.value.startswith("@"):
        channel = await reader.channel_by_handle(parsed.value)
    else:
        channel = (await reader.channels([parsed.value])).get(parsed.value)
    if channel is None:
        raise LookupError(f"channel not found: {parsed.value}")
    recent = await reader.recent_videos(channel, RECENT_TITLES)
    return {
        "kind": parsed.kind,
        "channel_id": channel.id,
        "untrusted_title": title,
        "untrusted_channel_title": channel.title[:120],
        "untrusted_description": (channel.description or "")[:600],
        "untrusted_recent_titles": [video.title[:120] for video in recent[:RECENT_TITLES]],
    }
