import re
from datetime import datetime
from typing import Literal

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Contract, Video


class Membership(Contract):
    video: Video
    included: bool
    reason: str
    size_stratum: Literal["small", "large", "unknown"]
    age_band: str
    selection_method: str


def selection_terms(family_key: str, query: str) -> tuple[str, ...]:
    """Return conservative lexical terms from a catalog query without generic modifiers."""
    generic = {"explained", "world"}
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.casefold()) if token not in generic]
    family = family_key.casefold()
    variants = [family, family + "s"] if family and not family.endswith("s") else [family]
    return tuple(dict.fromkeys([*variants, *tokens]))


def age_band(days: float) -> str:
    if days < 0:
        return "future"
    if days < 3:
        return "0-2"
    if days < 8:
        return "3-7"
    if days < 31:
        return "8-30"
    if days < 91:
        return "31-90"
    return "outside_window"


def relevance(video: Video, terms: tuple[str, ...]) -> Literal["confirmed", "excluded", "unknown"]:
    text = f"{video.title} {video.description or ''}".lower()
    if any(term in {"astronomy", "space", "science"} for term in terms):
        if re.search(r"\b(personal space|living space|interior decor|home decor)\b", text):
            return "excluded"
    # A conservative lexical verifier; provider category is a disclosed fallback.
    strong = [term.lower() for term in terms if term.lower() not in {"space", "explained"}]
    if any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in strong):
        return "confirmed"
    if video.category and video.category.lower() in strong:
        return "confirmed"
    return "unknown"


def sample(
    videos: tuple[Video, ...],
    *,
    now: datetime,
    format: VideoFormat,
    language: str,
    terms: tuple[str, ...],
    selection_method: str,
    small_threshold: int = 50_000,
    semantic_matches: frozenset[str] = frozenset(),
) -> tuple[Membership, ...]:
    if format == VideoFormat.UNKNOWN:
        raise ValueError("confirmed format required for a cohort")
    unique: dict[str, Video] = {}
    for video in videos:
        unique.setdefault(video.id, video)
    result = []
    for video in unique.values():
        days = (now - video.published_at).total_seconds() / 86400 if video.published_at else None
        band = age_band(days) if days is not None else "unknown"
        size: Literal["small", "large", "unknown"] = (
            "unknown"
            if video.subscriber_count is None
            else "small"
            if video.subscriber_count <= small_threshold
            else "large"
        )
        topic = relevance(video, terms)
        if topic == "unknown" and video.id in semantic_matches:
            topic = "confirmed"
        reason = "confirmed"
        if video.format == VideoFormat.UNKNOWN:
            reason = "format_unknown"
        elif video.format != format:
            reason = "different_format"
        elif video.language is None:
            reason = "language_unknown"
        elif video.language.split("-")[0] != language:
            reason = "different_language"
        elif topic != "confirmed":
            reason = "irrelevant" if topic == "excluded" else "relevance_unknown"
        elif band in {"unknown", "future", "outside_window"}:
            reason = band
        result.append(
            Membership(
                video=video,
                included=reason == "confirmed",
                reason=reason,
                size_stratum=size,
                age_band=band,
                selection_method=selection_method,
            )
        )
    return tuple(result)
