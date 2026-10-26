# tests/shorts_report_samples.py
"""Ejemplos (no reales) de channel-report-v2 (Shorts)."""

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from tests.pilot_samples import iso
from tests.test_persistence import NOW

CHANNEL = "canal-historias"  # el único canal con tabla de traducción de estados


def shorts_measurement(published: datetime | None = None, **over: Any) -> dict[str, Any]:
    start = published or NOW - timedelta(days=10)
    body: dict[str, Any] = {
        "measured_at": iso(start + timedelta(days=7)),
        "window_days": 7,
        "views": 2400,
        "engaged_views": 1560,
        "engaged_view_ratio_pct": 65.0,
        "avg_view_pct": 71.5,
        "shorts_feed_share_pct": 88.0,
        "shares": 14,
        "subscribers_gained": 6,
        "stayed_to_watch_pct": None,
        "early_retention_pct": None,
        "early_retention_second": None,
    }
    body.update(over)
    return body


def shorts_video(n: int, measured: bool = True, **over: Any) -> dict[str, Any]:
    published = NOW - timedelta(days=60 - n)
    data: dict[str, Any] = {
        "video_id": f"s_{n:02d}",
        "source_state": "EN_MEDICION" if measured else "PUBLICADO",
        "visibility": "public",
        "published_at": iso(published),
        "cost_usd": 0.1,
        "cost_equivalent_usd": 0.4,
        "machine_minutes": 20,
        "measurement": shorts_measurement(published) if measured else None,
        "failure_code": None,
    }
    data.update(over)
    return data


def shorts_report(
    videos: list[dict[str, Any]] | None = None,
    pilot_id: str = "pil_20261201_curiosidades-shorts",
    **over: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract": "channel-report-v2",
        "format": "shorts",
        "pilot_id": pilot_id,
        "channel_id": CHANNEL,
        "reported_at": iso(NOW),
        "channel_status": "active",
        "videos": deepcopy(videos) if videos is not None else [shorts_video(1)],
        "checks": [],
        "note": None,
    }
    body.update(deepcopy(over))
    return body
