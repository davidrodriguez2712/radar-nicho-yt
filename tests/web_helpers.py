# tests/web_helpers.py
"""Shared helpers for the mobile web tests."""

import copy
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.web.app import create_app
from tests.flow_research_samples import valid_dossier, valid_dossier_v2

TOKEN = "t" * 32
PASSWORD = "p" * 32


def settings(**over: object) -> Settings:
    values: dict[str, object] = {
        "service_token": SecretStr(TOKEN),
        "dashboard_password": SecretStr(PASSWORD),
        "api_url": "http://api.test",
        "dashboard_ui": "web",
    }
    return Settings(**(values | over))  # type: ignore[arg-type]


Route = tuple[int, object] | Callable[[httpx.Request], httpx.Response]


class Api:
    """Fake private API: a dict of (method, path) -> (status, json) or a callable."""

    def __init__(self, routes: dict[tuple[str, str], Route] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"detail": "not found"})
        if callable(route):
            return route(request)
        status, body = route
        return httpx.Response(status, json=body)

    def count(self, method: str, path: str) -> int:
        return sum(1 for c in self.calls if (c.method, c.url.path) == (method, path))


def make_client(api: Api, clock: Callable[[], float] | None = None, **over: object) -> TestClient:
    app = create_app(
        settings(**over), transport=httpx.MockTransport(api), **({"clock": clock} if clock else {})
    )
    web = TestClient(app, follow_redirects=False)
    response = web.post("/login", data={"password": PASSWORD})
    assert response.status_code == 303, response.text
    return web


def csrf_of(html: str) -> str:
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, html
    return found.group(1)


HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def measurement(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "measured_at": "2026-10-31T12:00:00Z",
        "included": 29,
        "stable_channels": 18,
        "volatile_channels": 11,
        "traction_channels": 19,
        "large_channels": 4,
        "excluded": {"language": 1},
        "income_low": "672.80",
        "income_high": "1681.99",
        "rpm_source": "inherited:wildlife_documentaries",
        "signal": "estimable",
    }
    return base | over


def research(status: str = "listo", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "status": status,
        "language": "en",
        "created_at": "2026-11-02T02:05:45Z",
    }
    return base | over


def subniche_item(slug: str = "prehistoric_creatures", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "slug": slug,
        "label": slug.replace("_", " ").title(),
        "family": "nature_science",
        "parent_niche_slug": "wildlife_documentaries",
        "status": "active",
        "finalist": True,
        "language": "en",
        "format": "long",
        "queries": ["prehistoric creatures documentary", "extinct animals that once ruled earth"],
        "measurement": measurement(),
        "research": None,
    }
    return base | over


def channel(title: str | None = "WUFO TV", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "channel_id": "UC" + "a" * 22,
        "title": title,
        "subscribers": 39600,
        "monthly_long_views": 5580483,
        "income_low": "11160.97",
        "income_high": "27902.42",
        "traction": True,
        "flags": [],
    }
    return base | over


def hypothesis_of(item: dict[str, object]) -> dict[str, object]:
    return {k: item[k] for k in item if k not in ("measurement", "research")}


def subniche_card(slug: str = "prehistoric_creatures", **over: object) -> dict[str, object]:
    item = subniche_item(slug)
    base: dict[str, object] = {
        "hypothesis": hypothesis_of(item),
        "measurement": item["measurement"],
        "channels": [
            channel(),
            channel("Curious Fing", subscribers=16800, monthly_long_views=1376974, traction=False),
        ],
        "channels_available": True,
        "research": None,
    }
    return base | over


def niche_item(
    label: str = "historia militar explicada", fmt: str = "long", **over: object
) -> dict[str, object]:
    base: dict[str, object] = {
        "niche_label": label,
        "format": fmt,
        "opportunity": {
            "version": "v1",
            "value": 78.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "nuevo", "note": None, "decided_at": None},
        "trend": 3.0,
    }
    return base | over


def flow_item(status: str = "listo", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "niche_label": "historia militar explicada",
        "format": "long",
        "language": "en",
        "status": status,
        "attempts": 1,
        "lease_until": None,
        "rejection": None,
        "created_at": "2026-11-02T02:05:45Z",
        "updated_at": "2026-11-02T03:00:00Z",
    }
    return base | over


def niche_detail(
    label: str = "historia militar explicada",
    fmt: str = "long",
    mix: list[tuple[str, float]] | None = None,
) -> dict[str, object]:
    mix = mix if mix is not None else [("en", 80.0), ("es", 15.0), ("unknown", 5.0)]
    return {
        "niche": niche_item(label, fmt),
        "listings": [],
        "language_mix": [{"language": code, "share_pct": share} for code, share in mix],
        "history": [],
    }


REPORT_ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"


def dossier_v3(**over: Any) -> dict[str, Any]:
    """A valid dossier-v3 (the flow-research sample, deep-copied so tests can mutate it)."""
    now = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
    return copy.deepcopy(valid_dossier(UUID(REPORT_ID), now)) | over


def dossier_v2() -> dict[str, Any]:
    return copy.deepcopy(valid_dossier_v2(UUID(REPORT_ID), datetime(2026, 11, 2, 3, 0, tzinfo=UTC)))


def dossier_v1() -> dict[str, Any]:
    old = dossier_v2()
    old["schema_version"] = "dossier-v1"
    del old["rights"], old["automation_plan"]
    return old


def report_detail(
    status: str = "listo", dossier: dict[str, Any] | None = None, **over: Any
) -> dict[str, Any]:
    """A flow-research order as the API returns it, with the frozen evidence and the dossier."""
    base: dict[str, Any] = flow_item(status) | {
        "evidence": {
            "source": "niche",
            "confidence": "media",
            "language_mix": [
                {"language": "en", "share_pct": 80.0},
                {"language": "es", "share_pct": 15.0},
                {"language": "unknown", "share_pct": 5.0},
            ],
            "gate": {
                "min_automation": 90,
                "max_human_minutes": 60,
                "max_calibration_hours": 40,
                "block_high_policy_risk": True,
                "passed": True,
                "reasons": [],
            },
        },
        "dossier": dossier if status == "listo" else None,
        "dossier_created_at": "2026-11-02T03:00:00Z" if status == "listo" else None,
    }
    return base | over


def pilot_item(pilot_id: str = "pil_20261102_historia", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "pilot_id": pilot_id,
        "status": "autorizado",
        "niche_label": "historia militar explicada",
        "format": "long",
        "target_channel": "canal-historias",
        "authorized_at": "2026-11-02T03:00:00Z",
        "last_report_at": None,
        "channel_last_contact_at": None,
        "totals": {
            "videos": 0,
            "published": 0,
            "measured": 0,
            "by_stage": {},
            "spent_usd": 0,
            "equivalent_usd": 0,
            "machine_minutes": 0,
            "machine_minutes_complete": True,
        },
        "proposal": {"action": "sin_datos_suficientes", "reason": "x"},
        "needs_decision": False,
        "valid_until": "2026-11-16T03:00:00Z",
        "delivered_at": "2026-11-03T10:00:00Z",
        "channel": {
            "reported_at": "2026-11-03T11:00:00Z",
            "channel_status": "active",
            "note": None,
            "checks": [
                {
                    "id": "youtube_oauth",
                    "label": "Autorizar subida y medición de YouTube",
                    "ok": True,
                    "detail": None,
                    "expires_at": "2026-12-31T00:00:00Z",
                }
            ],
        },
    }
    return base | over


def pilot_detail(pilot_id: str = "pil_20261102_historia", **over: object) -> dict[str, object]:
    """A pilot as GET /pilots/{id} returns it; the real package has no preparation/cadence field."""
    base = pilot_item(pilot_id) | {
        "language": "en",
        "authorized_by": "propietario (web)",
        "first_report_at": None,
        "closed_at": None,
        "close_reason": None,
        "channel": {
            "reported_at": "2026-11-03T11:00:00Z",
            "channel_status": "active",
            "note": None,
            "checks": [
                {
                    "id": "youtube_oauth",
                    "label": "Autorizar subida y medición de YouTube",
                    "ok": True,
                    "detail": None,
                    "expires_at": "2026-11-10T00:00:00Z",
                }
            ],
        },
        "package": {
            "niche": {"label": "historia militar explicada", "format": "long", "language": "en"},
            "dossier": {
                "request_id": REPORT_ID,
                "schema": "dossier-v3",
                "recommendation": "go",
                "confidence": "medium",
                "thesis": "t",
                "unknowns": [],
            },
            "budget": {
                "currency": "USD",
                "low": 3,
                "likely": 19.5,
                "high": 41,
                "max_videos": 10,
                "basis": "x",
            },
            "stop_rules": [],
            "close_after_failed_milestones": 2,
        },
        "evaluation": {
            "rules": [],
            "milestones": [],
            "totals": {},
            "warnings": [],
            "close_after": 2,
        },
        "acknowledged": [],
        "events": [],
    }
    return base | over


def pilot_video(video_id: str = "v1", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "video_id": video_id,
        "source_state": "PUBLICADO",
        "stage": "published",
        "visibility": "public",
        "published_at": "2026-11-05T12:00:00Z",
        "cost_usd": 0.32,
        "cost_equivalent_usd": 1.5,
        "machine_minutes": 70,
        "human_minutes": None,
        "human_minutes_method": None,
        "failure_code": None,
        "measurement": None,
    }
    return base | over
