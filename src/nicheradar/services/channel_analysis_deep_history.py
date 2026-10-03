"""Manual, on-demand real upload history for one channel -- never run automatically for
every comparable (see spec: the natural order of playlistItems.list is newest-first, with
no way to request oldest-first or jump ahead, so reaching old videos always means paging
through everything in between).

Breakout here is a single-channel-relative concept (a video is a "breakout" if its views
are at least 3x the median of this same channel's own fetched views) -- deliberately NOT
the cross-channel calculate()/Membership machinery used elsewhere, which measures a
channel against a cohort of many other channels. Those are different questions.
"""

import math
from datetime import datetime
from statistics import median
from typing import Any

from nicheradar.integrations.contracts import Channel, Operation, Video
from nicheradar.services.gateway import Gateway

PAGE_SIZE = 50


def estimate_deep_history_cost(video_count: int | None) -> int | None:
    """Real quota units a full `fetch_deep_history` run would spend: one playlistItems.list
    page plus one videos.list batch per PAGE_SIZE videos."""
    if video_count is None:
        return None
    pages = math.ceil(video_count / PAGE_SIZE)
    return pages * 2


async def fetch_deep_history(
    gateway: Gateway, channel: Channel, now: datetime, *, max_quota_units: int = 100
) -> dict[str, Any]:
    if not channel.uploads_playlist:
        return {
            "status": "no_breakout_found",
            "days_to_first_breakout": None,
            "quota_units_spent": 0,
        }

    video_ids: list[str] = []
    token: str | None = None
    spent = 0
    status = "computed"

    while True:
        if spent + 2 > max_quota_units:
            status = "partial_by_cap"
            break
        params: dict[str, Any] = {
            "playlistId": channel.uploads_playlist,
            "maxResults": str(PAGE_SIZE),
        }
        if token:
            params["pageToken"] = token
        batch, _, _ = await gateway.fetch(Operation.UPLOADS, params, now)
        spent += 1
        video_ids.extend(video.id for video in batch.videos)
        token = batch.coverage.next_page
        if not token:
            break

    videos: list[Video] = []
    for i in range(0, len(video_ids), PAGE_SIZE):
        if spent + 1 > max_quota_units:
            status = "partial_by_cap"
            break
        chunk = video_ids[i : i + PAGE_SIZE]
        batch, _, _ = await gateway.fetch(Operation.VIDEOS, {"id": ",".join(chunk)}, now)
        spent += 1
        videos.extend(batch.videos)

    if not videos or channel.published_at is None:
        return {
            "status": "no_breakout_found" if status == "computed" else status,
            "days_to_first_breakout": None,
            "quota_units_spent": spent,
        }

    known_views = [v.views for v in videos if v.views is not None]
    if not known_views:
        return {
            "status": "no_breakout_found" if status == "computed" else status,
            "days_to_first_breakout": None,
            "quota_units_spent": spent,
        }

    threshold = median(known_views) * 3
    breakout_videos = sorted(
        (
            video
            for video in videos
            if video.views is not None
            and video.views >= threshold
            and video.published_at is not None
        ),
        key=lambda v: v.published_at,  # type: ignore[arg-type,return-value]
    )
    if not breakout_videos:
        # `status` already carries "partial_by_cap" when the cap was hit -- that is more
        # informative than a blanket "no_breakout_found" (which would otherwise wrongly
        # imply an exhaustive, conclusive negative search of the FULL history).
        return {
            "status": "no_breakout_found" if status == "computed" else status,
            "days_to_first_breakout": None,
            "quota_units_spent": spent,
        }

    first_published_at = breakout_videos[0].published_at
    assert first_published_at is not None  # filtered above
    days_to_first_breakout = (first_published_at - channel.published_at).days
    return {
        "status": status,
        "days_to_first_breakout": days_to_first_breakout,
        "quota_units_spent": spent,
    }
