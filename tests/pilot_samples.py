# tests/pilot_samples.py
"""Datos de ejemplo (no reales) para los contratos de pilotos."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from nicheradar.pilots.contracts import with_sha256

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
DOSSIER_ID = "00000000-0000-4000-8000-000000000001"


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


STOP_RULES: list[dict[str, Any]] = [
    {
        "id": "retencion-v10",
        "text": "AVD >= 18% en al menos 3 de los primeros 10 videos",
        "metric": "avd_pct",
        "comparator": ">=",
        "threshold": 18,
        "min_cases": 3,
        "milestone": {"kind": "video", "value": 10},
    },
    {
        "id": "browse-v20",
        "text": "Trafico de exploracion >= 30% al video 20",
        "metric": "browse_share_pct",
        "comparator": ">=",
        "threshold": 30,
        "min_cases": None,
        "milestone": {"kind": "video", "value": 20},
    },
    {
        "id": "viabilidad-m6",
        "text": "Ingresos >= costo en efectivo al mes 6",
        "metric": "revenue_vs_cost",
        "comparator": ">=",
        "threshold": 1,
        "min_cases": None,
        "milestone": {"kind": "month", "value": 6},
    },
]


def package_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract": "pilot-package-v1",
        "pilot_id": "pil_20261101_historia-militar",
        "supersedes": None,
        "authorized_by": "david",
        "authorized_at": iso(NOW),
        "valid_until": iso(NOW + timedelta(days=14)),
        "niche": {"label": "Historia militar explicada", "format": "long", "language": "en"},
        "evidence": {
            "captured_at": iso(NOW - timedelta(minutes=5)),
            "scores": {"opportunity": 78, "automation": 64, "creator_fit": 71, "market": 69},
            "confidence": "medium",
            "listings_with_income": 5,
            "language_mix": [{"language": "en", "share_pct": 100}],
            "figures": [
                {
                    "name": "income_median",
                    "value": 1450,
                    "unit": "usd_per_month",
                    "origin": "seller_declared",
                }
            ],
        },
        "dossier": {
            "request_id": DOSSIER_ID,
            "schema": "dossier-v1",
            "recommendation": "go_with_conditions",
            "confidence": "medium",
            "thesis": "Demanda solida, ingresos solo declarados.",
            "unknowns": ["Ingresos reales del nicho"],
        },
        "budget": {
            "currency": "USD",
            "low": 3,
            "likely": 19.5,
            "high": 41,
            "max_videos": 10,
            "basis": "10 videos x costo medido en canal-historias",
        },
        "stop_rules": deepcopy(STOP_RULES),
        "close_after_failed_milestones": 2,
        "target_channel": "canal-historias",
        "recipe": {"name": "faceless-storytelling", "version": "0.1.0"},
    }
    body.update(over)
    return body


def package(**over: Any) -> dict[str, Any]:
    return with_sha256(package_body(**over))


def video(video_id: str = "v_20261103_a1b2", **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "video_id": video_id,
        "source_state": "EN_MEDICION",
        "visibility": "public",
        "published_at": iso(NOW - timedelta(days=8)),
        "cost_usd": 0.32,
        "cost_equivalent_usd": 1.53,
        "machine_minutes": 67,
        "measurement": {
            "measured_at": iso(NOW - timedelta(days=1)),
            "window_days": 7,
            "avd_pct": 22.1,
            "views": 140,
            "browse_share_pct": None,
            "subscribers_gained": 0,
        },
        "failure_code": None,
    }
    data.update(over)
    return data


def report(*videos: dict[str, Any], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract": "channel-report-v1",
        "pilot_id": "pil_20261101_historia-militar",
        "channel_id": "canal-historias",
        "reported_at": iso(NOW),
        "channel_status": "active",
        "videos": list(videos) or [video()],
        "note": None,
    }
    body.update(over)
    return body
