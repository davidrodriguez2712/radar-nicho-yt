# src/nicheradar/web/segment.py
"""Counts for the Nichos | Subnichos control: each one degrades alone to a dash."""

from collections.abc import Iterable
from typing import Any

from nicheradar.web.client import ApiClient, ApiError
from nicheradar.web.deps import SHAPE_ERRORS

COUNT_TIMEOUT = 3.0
UNKNOWN = "—"
COUNTED_STATUSES = ("active", "proposed")


def _count(value: Any) -> int | str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return UNKNOWN
    return int(value)


def niche_total(api: ApiClient) -> int | str:
    """Total of market niches (one item is enough: only `total` is read)."""
    try:
        data = api.request("GET", "/market/niches", params={"limit": "1"}, timeout=COUNT_TIMEOUT)
        return _count(data["total"])
    except (ApiError, *SHAPE_ERRORS):
        return UNKNOWN


def active_subniches(items: Iterable[dict[str, Any]]) -> int | str:
    """Active and proposed hypotheses; paused and archived ones never count."""
    try:
        return sum(1 for item in items if item["status"] in COUNTED_STATUSES)
    except SHAPE_ERRORS:
        return UNKNOWN


def subniche_total(api: ApiClient) -> int | str:
    try:
        data = api.request(
            "GET", "/subniches", params={"include_inactive": "false"}, timeout=COUNT_TIMEOUT
        )
        items = data["items"]
        if not isinstance(items, list):
            return UNKNOWN
        return len(items)
    except (ApiError, *SHAPE_ERRORS):
        return UNKNOWN


def counts(niches: int | str, subniches: int | str) -> dict[str, int | str]:
    return {"nichos": niches, "subnichos": subniches}
