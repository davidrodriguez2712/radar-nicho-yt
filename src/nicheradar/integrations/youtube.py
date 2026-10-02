"""Complementary public metadata adapter; one quota-bearing page per fetch."""

import re
import shlex
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import SecretStr

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import (
    Batch,
    Channel,
    Cost,
    Coverage,
    Operation,
    Provenance,
    ProviderError,
    Video,
)

_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def _duration_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    parts = {key: float(raw or 0) for key, raw in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _embed_dimensions(player: dict[str, Any]) -> tuple[float, float] | None:
    # Unlike snippet.thumbnails (fixed-size tiers, not representative of the source
    # video's real orientation), videos.list's player.embedWidth/embedHeight are scaled
    # to the video's REAL aspect ratio by YouTube itself -- but only returned at all
    # when the request specifies maxHeight and/or maxWidth (see fetch(), which sets
    # maxHeight for every VIDEOS call), and only when YouTube knows the real aspect
    # ratio in the first place -- when it doesn't, these two numeric fields are simply
    # omitted (the documented 4:3 fallback only affects the embedHtml iframe markup,
    # not embedWidth/embedHeight), so whenever both fields are present here they are
    # already a confirmed, real signal. Confirmed via a real live call: like viewCount
    # (also int64), these arrive as JSON strings (e.g. "640"), Google's standard
    # int64-as-string encoding -- parse defensively, accepting either a string or a
    # number, same as Video.views already does via pydantic coercion.
    width, height = player.get("embedWidth"), player.get("embedHeight")
    try:
        return float(width), float(height)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _classify_format(
    duration_seconds: float | None, player: dict[str, Any]
) -> tuple[VideoFormat, str | None]:
    """Classify format from two real, already-fetched signals: duration (contentDetails)
    and the video's real embed aspect ratio (player.embedWidth/embedHeight) -- never
    duration alone, since a 90-second landscape video is not a Short."""
    if duration_seconds is None:
        return VideoFormat.UNKNOWN, None
    if duration_seconds > 180:
        return VideoFormat.LONG, "duration > 180s"
    dimensions = _embed_dimensions(player)
    if dimensions is None:
        return VideoFormat.UNKNOWN, "duration <= 180s but no embed dimensions to confirm aspect"
    width, height = dimensions
    if height >= width:
        return VideoFormat.SHORTS, "duration <= 180s and portrait/square embed dimensions"
    return VideoFormat.LONG, "duration <= 180s but landscape embed dimensions"


def _parse_keywords(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        return tuple(shlex.split(raw))
    except ValueError:
        # Unbalanced quotes in a creator-supplied field — fail soft, not loud.
        return tuple(raw.split())


class YouTubeProvider:
    name = "youtube"
    operations = frozenset(
        {
            Operation.CHANNELS,
            Operation.UPLOADS,
            Operation.VIDEOS,
            Operation.SEARCH,
            Operation.COMMENT_THREADS,
            Operation.VIDEO_CATEGORIES,
        }
    )
    endpoint = "https://www.googleapis.com/youtube/v3/"

    def __init__(
        self,
        api_key: SecretStr | None,
        auth_scope: str,
        *,
        enabled: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.auth_scope = auth_scope
        self.enabled = enabled
        self.transport = transport
        self.calls = 0

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if operation not in self.operations:
            raise ProviderError("unsupported_operation")
        if not self.enabled:
            raise ProviderError("integration_disabled")
        if self.api_key is None:
            raise ProviderError("authentication_required")
        resource = {
            Operation.CHANNELS: "channels",
            Operation.UPLOADS: "playlistItems",
            Operation.VIDEOS: "videos",
            Operation.SEARCH: "search",
            Operation.COMMENT_THREADS: "commentThreads",
            Operation.VIDEO_CATEGORIES: "videoCategories",
        }[operation]
        params = {
            key: value
            for key, value in parameters.items()
            if key
            in {
                "id",
                "forHandle",
                "playlistId",
                "pageToken",
                "maxResults",
                "q",
                "type",
                "order",
                "videoId",
                "regionCode",
            }
        }
        if operation == Operation.UPLOADS:
            params["part"] = "snippet,contentDetails"
        elif operation in {Operation.SEARCH, Operation.COMMENT_THREADS, Operation.VIDEO_CATEGORIES}:
            params["part"] = "snippet"
        elif operation == Operation.CHANNELS:
            params["part"] = "snippet,contentDetails,statistics,brandingSettings"
        else:
            params["part"] = "snippet,contentDetails,statistics,player"
            # player.embedWidth/embedHeight are only returned at all when maxHeight
            # and/or maxWidth is requested -- 360 is a reasonable fixed value (the
            # documented valid range is 72-8192; YouTube's docs don't name a specific
            # default), kept as an internal constant of this VIDEOS request, not
            # caller-configurable, same as `part` above.
            params["maxHeight"] = 360
        if operation == Operation.UPLOADS:
            params.setdefault("maxResults", 50)
        if operation != Operation.UPLOADS and len(str(params.get("id", "")).split(",")) > 50:
            raise ProviderError("batch_too_large")
        self.calls += 1
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=20,
                headers={"X-Goog-Api-Key": self.api_key.get_secret_value()},
            ) as client:
                response = await client.get(self.endpoint + resource, params=params)
            if response.status_code in {401, 403}:
                reasons = response.json().get("error", {}).get("errors", [])
                quota = any(
                    row.get("reason") in {"quotaExceeded", "dailyLimitExceeded"} for row in reasons
                )
                raise ProviderError(
                    "quota" if quota else "authentication_required", may_have_charged=True
                )
            if response.status_code == 429:
                raise ProviderError("quota", may_have_charged=True)
            response.raise_for_status()
            return self.normalize(operation, response.json(), now)
        except ProviderError:
            raise
        except httpx.ConnectError:
            raise ProviderError("connection_failed", retry_safe=True, not_sent=True) from None
        except Exception:
            raise ProviderError("provider_response_failed", may_have_charged=True) from None

    def normalize(self, operation: Operation, payload: dict[str, Any], now: datetime) -> Batch:
        if operation == Operation.SEARCH:
            return self._normalize_search(payload, now)
        if operation == Operation.COMMENT_THREADS:
            return self._normalize_comment_threads(payload, now)
        if operation == Operation.VIDEO_CATEGORIES:
            return self._normalize_video_categories(payload, now)
        # Deduplicate only by stable IDs, preserving first observed order.
        rows = list({row["id"]: row for row in payload.get("items", [])}.values())
        common: dict[str, Any] = {
            "provenance": Provenance(
                provider=self.name, operation=operation, auth_scope=self.auth_scope, fetched_at=now
            ),
            "coverage": Coverage(
                returned=len(rows),
                reported_total=payload.get("pageInfo", {}).get("totalResults"),
                next_page=payload.get("nextPageToken"),
                complete=False,
                selection_method="uploads" if operation == Operation.UPLOADS else "id_lookup",
                limitations=("Resource omissions and actual audio/Shorts classification unknown.",),
            ),
            "costs": (
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(1),
                    actual=Decimal(1),
                    source="YouTube videos.list quota verified 2026-09-23",
                ),
            ),
        }
        if operation == Operation.CHANNELS:
            channels = tuple(
                Channel(
                    id=row["id"],
                    title=row["snippet"]["title"],
                    description=row["snippet"].get("description"),
                    subscribers=None
                    if row.get("statistics", {}).get("hiddenSubscriberCount")
                    else row.get("statistics", {}).get("subscriberCount"),
                    country=row["snippet"].get("country"),
                    uploads_playlist=row.get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads"),
                    keywords=_parse_keywords(
                        row.get("brandingSettings", {}).get("channel", {}).get("keywords")
                    ),
                )
                for row in rows
            )
            return Batch(**common, channels=channels)
        videos: dict[str, Video] = {}
        for row in rows:
            snippet = row.get("snippet", {})
            content = row.get("contentDetails", {})
            if operation == Operation.UPLOADS:
                video_id = content.get("videoId") or snippet.get("resourceId", {}).get("videoId")
                # playlist owner can differ from the video's channel; do not substitute it.
                channel_id = snippet.get("videoOwnerChannelId")
                published = content.get("videoPublishedAt")
            else:
                video_id, channel_id = row["id"], snippet.get("channelId")
                published = snippet.get("publishedAt")
            if not video_id or not channel_id:
                continue
            duration_seconds = _duration_seconds(content.get("duration"))
            video_format, format_evidence = _classify_format(
                duration_seconds, row.get("player", {})
            )
            videos[video_id] = Video(
                id=video_id,
                channel_id=channel_id,
                title=snippet.get("title", ""),
                description=snippet.get("description"),
                published_at=published,
                views=row.get("statistics", {}).get("viewCount"),
                format=video_format,
                format_evidence=format_evidence,
                language=snippet.get("defaultAudioLanguage"),
                language_evidence="declared defaultAudioLanguage"
                if snippet.get("defaultAudioLanguage")
                else None,
                category=snippet.get("categoryId"),
                duration_seconds=duration_seconds,
            )
        return Batch(**common, videos=tuple(videos.values()))

    def _normalize_search(self, payload: dict[str, Any], now: datetime) -> Batch:
        items = payload.get("items", [])
        channels = tuple(
            Channel(id=item["id"]["channelId"], title=item["snippet"]["title"])
            for item in items
            if "channelId" in item.get("id", {})
        )
        videos = tuple(
            Video(
                id=item["id"]["videoId"],
                channel_id=item["snippet"].get("channelId", ""),
                title=item["snippet"]["title"],
                published_at=None,
            )
            for item in items
            if "videoId" in item.get("id", {})
        )
        return Batch(
            provenance=Provenance(
                provider=self.name,
                operation=Operation.SEARCH,
                auth_scope=self.auth_scope,
                fetched_at=now,
            ),
            coverage=Coverage(
                returned=len(items),
                reported_total=payload.get("pageInfo", {}).get("totalResults"),
                next_page=payload.get("nextPageToken"),
                complete=False,
                selection_method="search",
            ),
            costs=(
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(100),
                    actual=Decimal(100),
                    source="YouTube search.list quota verified 2026-10-01",
                ),
            ),
            channels=channels,
            videos=videos,
        )

    def _normalize_comment_threads(self, payload: dict[str, Any], now: datetime) -> Batch:
        items = payload.get("items", [])
        comments = tuple(
            {
                "text": item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                "like_count": item["snippet"]["topLevelComment"]["snippet"]["likeCount"],
            }
            for item in items
        )
        return Batch(
            provenance=Provenance(
                provider=self.name,
                operation=Operation.COMMENT_THREADS,
                auth_scope=self.auth_scope,
                fetched_at=now,
            ),
            coverage=Coverage(
                returned=len(comments),
                reported_total=payload.get("pageInfo", {}).get("totalResults"),
                next_page=payload.get("nextPageToken"),
                complete=False,
                selection_method="comment_threads",
            ),
            costs=(
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(1),
                    actual=Decimal(1),
                    source="YouTube commentThreads.list quota verified 2026-10-01",
                ),
            ),
            comments=comments,
        )

    def _normalize_video_categories(self, payload: dict[str, Any], now: datetime) -> Batch:
        items = payload.get("items", [])
        labels = {item["id"]: item["snippet"]["title"] for item in items}
        return Batch(
            provenance=Provenance(
                provider=self.name,
                operation=Operation.VIDEO_CATEGORIES,
                auth_scope=self.auth_scope,
                fetched_at=now,
            ),
            coverage=Coverage(
                returned=len(labels),
                selection_method="video_categories",
            ),
            costs=(
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(1),
                    actual=Decimal(1),
                    source="YouTube videoCategories.list quota verified 2026-10-01",
                ),
            ),
            category_labels=labels,
        )
