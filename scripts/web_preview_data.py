# scripts/web_preview_data.py
"""Sample data for the mobile web preview, in the exact shape of the private API."""

from typing import Any


def _measurement(
    included: int,
    stable: int,
    volatile: int,
    traction: int,
    large: int,
    low: str,
    high: str,
    excluded: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "measured_at": "2026-10-31T12:00:00Z",
        "included": included,
        "stable_channels": stable,
        "volatile_channels": volatile,
        "traction_channels": traction,
        "large_channels": large,
        "excluded": excluded or {},
        "income_low": low,
        "income_high": high,
        "rpm_source": "inherited:wildlife_documentaries",
        "signal": "estimable",
    }


def _item(
    slug: str,
    label: str,
    family: str,
    parent: str,
    queries: list[str],
    measurement: dict[str, Any],
    *,
    finalist: bool,
    research: str | None,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "label": label,
        "family": family,
        "parent_niche_slug": parent,
        "status": "active",
        "finalist": finalist,
        "language": "en",
        "format": "long",
        "queries": queries,
        "measurement": measurement,
        "research": (
            {
                "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
                "status": research,
                "language": "en",
                "created_at": "2026-11-02T02:05:45Z",
            }
            if research
            else None
        ),
    }


ITEMS: list[dict[str, Any]] = [
    _item(
        "prehistoric_creatures",
        "Prehistoric Creatures",
        "nature_science",
        "wildlife_documentaries",
        ["prehistoric creatures documentary", "extinct animals that once ruled earth"],
        _measurement(29, 18, 11, 19, 4, "672.80", "1681.99", {"language": 1}),
        finalist=True,
        research="listo",
    ),
    _item(
        "deep_sea_mysteries",
        "Deep Sea Mysteries",
        "nature_science",
        "nature_documentaries",
        ["deep sea creatures documentary", "mysteries of the deep ocean"],
        _measurement(24, 14, 10, 15, 3, "540.10", "1350.25"),
        finalist=True,
        research="en_curso",
    ),
    _item(
        "forgotten_history_events",
        "Forgotten History Events",
        "history",
        "history_documentaries",
        ["forgotten history documentary", "history they never taught you"],
        _measurement(27, 16, 11, 17, 5, "610.00", "1520.40"),
        finalist=True,
        research=None,
    ),
    _item(
        "history_revenge",
        "History Revenge Stories",
        "history",
        "historical_stories",
        ["history revenge", "revenge that changed history"],
        _measurement(22, 12, 10, 13, 2, "420.50", "1050.75"),
        finalist=True,
        research=None,
    ),
    _item(
        "ancient_egypt_secrets",
        "Ancient Egypt Secrets",
        "history",
        "history_documentaries",
        ["ancient egypt documentary", "secrets of the pharaohs"],
        _measurement(26, 15, 11, 16, 4, "580.30", "1450.60"),
        finalist=False,
        research=None,
    ),
]

_PREHISTORIC = ITEMS[0]

CARD: dict[str, Any] = {
    "hypothesis": {
        key: value for key, value in _PREHISTORIC.items() if key not in ("measurement", "research")
    },
    "measurement": _PREHISTORIC["measurement"],
    "channels": [
        {
            "channel_id": "UC" + "a" * 22,
            "title": "WUFO TV",
            "subscribers": 39600,
            "monthly_long_views": 5580483,
            "income_low": "11160.97",
            "income_high": "27902.42",
            "traction": True,
            "flags": [],
        },
        {
            "channel_id": "UC" + "b" * 22,
            "title": "Curious Fing",
            "subscribers": 16800,
            "monthly_long_views": 1376974,
            "income_low": "2753.95",
            "income_high": "6884.87",
            "traction": False,
            "flags": [],
        },
        {
            "channel_id": "UC" + "c" * 22,
            "title": "Extinct World",
            "subscribers": 8400,
            "monthly_long_views": 612300,
            "income_low": "1224.60",
            "income_high": "3061.50",
            "traction": True,
            "flags": [],
        },
    ],
    "channels_available": True,
    "research": _PREHISTORIC["research"],
}
