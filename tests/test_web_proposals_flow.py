# tests/test_web_proposals_flow.py
"""Recorrido completo de Proponer y Compartir con un transporte falso de httpx."""

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient

from nicheradar.web.client import CODE_MESSAGES
from tests.web_helpers import (
    Api,
    csrf_of,
    hypothesis_of,
    make_client,
    subniche_card,
    subniche_item,
)

PID = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d"
SLUG = "ancient-rome"
V1 = "/api/v1/subniches"
CHANNEL = "https://www.youtube.com/@nombredelcanal"


class Backend(Api):
    """API de propuestas con estado: la propuesta avanza y aprobar activa el subnicho."""

    def __init__(self) -> None:
        super().__init__()
        self.stage = 0  # 0 en cola, 1 preparando, 2 lista, 3 fallida
        self.status = "proposed"
        self.error: dict[str, str] | None = None
        self.input = ""

    def hypothesis(self) -> dict[str, Any]:
        return {
            "slug": SLUG,
            "label": "Ancient Rome",
            "family": "history",
            "parent_niche": "Historia militar explicada",
            "queries": ["ancient rome facts", "how rome fell"],
            "seed_channels": ["@nombredelcanal"],
            "status": "proposed",
        }

    def proposal(self) -> dict[str, Any]:
        status = ["queued", "running", "succeeded", "failed"][self.stage]
        return {
            "id": PID,
            "status": status,
            "kind": "channel",
            "input": self.input,
            "created_at": "2026-11-05T11:00:00Z",
            "finished_at": None if self.stage < 2 else "2026-11-05T11:02:00Z",
            "error": self.error if self.stage == 3 else None,
            "hypothesis": self.hypothesis() if self.stage == 2 else None,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path.removeprefix("/api/v1")
        if (request.method, path) == ("POST", "/subniches/proposals"):
            self.input = json.loads(request.content)["input"]
            return httpx.Response(202, json={"id": PID, "status": "queued", "created": True})
        if path == f"/subniches/proposals/{PID}":
            return httpx.Response(200, json=self.proposal())
        if path == f"/subniches/{SLUG}/approval":
            return httpx.Response(
                200,
                json={
                    "slug": SLUG,
                    "status": self.status,
                    "queries": 2,
                    "pages": 1,
                    "search_units_needed": 200,
                    "daily_cap": 100,
                    "fits": False,
                    "cadence_days": 3,
                },
            )
        if (request.method, path) == ("POST", f"/subniches/{SLUG}/approve"):
            self.status = "active"
            return httpx.Response(200, json={"slug": SLUG, "status": "active"})
        if path == f"/subniches/{SLUG}":
            item = subniche_item(SLUG, status=self.status, label="Ancient Rome")
            return httpx.Response(200, json=subniche_card(SLUG, hypothesis=hypothesis_of(item)))
        if path == "/pilots":
            return httpx.Response(200, json={"items": []})
        if path == "/status":
            return httpx.Response(200, json={"radar_paused": True})
        return httpx.Response(404, json={"detail": "not found"})


def field(html: str, name: str) -> str:
    found = re.search(rf'name="{name}" value="([^"]*)"', html)
    assert found, (name, html)
    return found.group(1)


def posts(api: Api) -> list[httpx.Request]:
    return [c for c in api.calls if c.method == "POST"]


def approve_and_check(web: TestClient, api: Backend) -> None:
    api.stage = 2
    ready = web.get(f"/subnichos/propuestas/{PID}", headers={"HX-Request": "true"})
    assert "hx-trigger" not in ready.text and "Revisar y aprobar" in ready.text
    page = web.get(f"/subnichos/{SLUG}/aprobar")
    assert "Aprobar subnicho" in page.text and "200 unidades" in page.text
    assert "Con la cuota actual la medición se saltará hasta que haya cupo" in page.text
    done = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": csrf_of(page.text)})
    assert done.status_code == 303
    assert done.headers["location"] == f"/subnichos/{SLUG}?aviso=aprobado"
    card = web.get(done.headers["location"]).text
    assert "Hipótesis aprobada" in card and "Pausar" in card
    assert f'action="/subnichos/{SLUG}/pausar"' in card
    assert "Revisar y aprobar" not in card


def test_share_a_channel_then_propose_then_approve() -> None:
    api = Backend()
    web = make_client(api)
    shared = web.get("/compartir", params={"title": "Un canal", "text": "", "url": CHANNEL})
    assert "Compartido contigo" in shared.text and "Canal de YouTube" in shared.text
    href = re.search(r'href="(/subnichos/proponer\?q=[^"]+)"', shared.text)
    assert href and "Proponer" in shared.text
    q = parse_qs(urlsplit(href.group(1).replace("&amp;", "&")).query)["q"]
    form = web.get(href.group(1).replace("&amp;", "&"))
    assert form.status_code == 200 and f'value="{q[0]}"' in form.text
    sent = web.post(
        "/subnichos/proponer",
        data={"csrf": field(form.text, "csrf"), "nonce": field(form.text, "nonce"), "input": q[0]},
    )
    assert sent.status_code == 303
    assert sent.headers["location"] == f"/subnichos/propuestas/{PID}"
    (call,) = posts(api)
    assert json.loads(call.content) == {"input": q[0]}
    assert re.fullmatch(r"nr-[0-9a-f]{40}", call.headers["idempotency-key"])
    queued = web.get(sent.headers["location"])
    assert "En cola" in queued.text and 'hx-trigger="every 5s"' in queued.text
    api.stage = 1
    running = web.get(sent.headers["location"], headers={"HX-Request": "true"})
    assert "Preparando" in running.text and 'hx-trigger="every 5s"' in running.text
    approve_and_check(web, api)
    assert len(posts(api)) == 2  # la propuesta y la aprobación: nada más escribe


def test_manual_mode_flow() -> None:
    api = Backend()
    web = make_client(api)
    form = web.get("/subnichos/proponer")
    sent = web.post(
        "/subnichos/proponer",
        data={
            "csrf": field(form.text, "csrf"),
            "nonce": field(form.text, "nonce"),
            "input": "ancient rome facts",
            "modo": "manual",
            "label": "Ancient Rome",
            "family": "history",
            "parent": "Historia militar explicada",
        },
    )
    assert sent.status_code == 303
    assert json.loads(posts(api)[0].content) == {
        "input": "ancient rome facts",
        "manual": {
            "label": "Ancient Rome",
            "family": "history",
            "parent": "Historia militar explicada",
        },
    }
    approve_and_check(web, api)


def test_a_failure_shows_the_fixed_text_and_no_hypothesis() -> None:
    api = Backend()
    api.error = {"code": "youtube_unreachable", "message": "RAW <b>detalle</b>"}
    web = make_client(api)
    form = web.get("/subnichos/proponer", params={"q": CHANNEL})
    sent = web.post(
        "/subnichos/proponer",
        data={
            "csrf": field(form.text, "csrf"),
            "nonce": field(form.text, "nonce"),
            "input": CHANNEL,
        },
    )
    api.stage = 3
    page = web.get(sent.headers["location"])
    assert CODE_MESSAGES["youtube_unreachable"] in page.text
    assert "RAW" not in page.text and "detalle" not in page.text
    assert "Volver a intentar" in page.text
    assert "Hipótesis" not in page.text and "Revisar y aprobar" not in page.text
    assert "hx-trigger" not in page.text
