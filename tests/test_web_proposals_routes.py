# tests/test_web_proposals_routes.py
import json
import re
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from nicheradar.web.client import CODE_MESSAGES
from tests.web_helpers import HOSTILE, Api, csrf_of, make_client, settings

PID = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d"
POST = ("POST", "/api/v1/subniches/proposals")
GET = ("GET", f"/api/v1/subniches/proposals/{PID}")
FORM = "/subnichos/proponer"
NONCE = "a" * 32


def nonce_of(html: str) -> str:
    found = re.search(r'name="nonce" value="([^"]+)"', html)
    assert found, html
    return found.group(1)


def item(**over: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": PID,
        "status": "queued",
        "kind": "channel",
        "input": "@nombredelcanal",
        "created_at": "2026-11-05T11:00:00Z",
        "finished_at": None,
        "error": None,
        "hypothesis": None,
    }
    base.update(over)
    return base


def ready() -> dict[str, Any]:
    return item(
        status="succeeded",
        finished_at="2026-11-05T11:02:00Z",
        hypothesis={
            "slug": "ancient-rome",
            "label": "Ancient Rome",
            "family": "history",
            "parent_niche": "Historia militar explicada",
            "queries": ["ancient rome facts", "how rome fell"],
            "seed_channels": ["@nombredelcanal"],
            "status": "candidate",
        },
    )


def accepted(request: httpx.Request) -> httpx.Response:
    return httpx.Response(202, json={"id": PID, "status": "queued", "created": True})


def form(web: TestClient, **over: str) -> dict[str, str]:
    page = web.get(FORM).text
    data = {"csrf": csrf_of(page), "nonce": nonce_of(page), "input": "@nombredelcanal"}
    data.update(over)
    return data


def posts(api: Api) -> list[httpx.Request]:
    return [c for c in api.calls if c.method == "POST"]


def test_form_requires_a_session() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    response = web.get(FORM)
    assert response.status_code == 303 and response.headers["location"].startswith("/login")
    assert web.post(FORM, data={}).status_code == 303


def test_form_shows_figma_texts_and_a_valid_nonce() -> None:
    page = make_client(Api()).get(FORM)
    assert page.status_code == 200
    for text in (
        "Proponer subnicho",
        "Consulta, video o canal",
        "Los enlaces de X (tweets) todavía no se leen.",
        "Cuánto gasta proponer",
        "Una consulta no gasta nada.",
        "Sin modelo de lenguaje (manual)",
        "Propuesta manual",
        "Etiqueta",
        "Familia",
        "Nicho padre (opcional)",
        "Crear propuesta manual",
        'href="/subnichos"',
    ):
        assert text in page.text
    assert re.fullmatch(r"[0-9a-f]{32}", nonce_of(page.text))
    assert 'name="csrf"' in page.text


def test_form_prefills_from_q_escaped() -> None:
    page = make_client(Api()).get(FORM, params={"q": HOSTILE})
    assert "&lt;script&gt;" in page.text and "<script>alert" not in page.text
    assert "@canal" in make_client(Api()).get(FORM, params={"q": "@canal"}).text


def test_post_without_csrf_is_403_and_calls_nothing() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    response = web.post(FORM, data={"nonce": NONCE, "input": "dinosaurios"})
    assert response.status_code == 403 and api.calls == []


def test_post_sends_the_exact_body_and_redirects() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    response = web.post(FORM, data=form(web, input="  dinosaurios  "))
    assert response.status_code == 303
    assert response.headers["location"] == f"/subnichos/propuestas/{PID}"
    (call,) = posts(api)
    assert json.loads(call.content) == {"input": "dinosaurios"}
    assert call.headers["authorization"].startswith("Bearer ")
    assert re.fullmatch(r"nr-[0-9a-f]{40}", call.headers["idempotency-key"])


def test_same_nonce_gives_the_same_key_and_a_new_nonce_another() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    data = form(web)
    web.post(FORM, data=data)
    web.post(FORM, data=data)
    other = form(web)
    web.post(FORM, data=other)
    first, second, third = (c.headers["idempotency-key"] for c in posts(api))
    assert first == second != third


@pytest.mark.parametrize("nonce", ["", "zz", "A" * 32, "a" * 31, "a" * 33, "a" * 31 + "\n"])
def test_invalid_nonce_is_rejected_without_calling_the_api(nonce: str) -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    response = web.post(FORM, data=form(web, nonce=nonce))
    assert response.status_code == 422 and posts(api) == []
    assert "La solicitud no es válida." in response.text
    assert "@nombredelcanal" in response.text


def test_missing_nonce_is_rejected() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    data = form(web)
    del data["nonce"]
    assert web.post(FORM, data=data).status_code == 422 and posts(api) == []


def test_short_input_returns_the_form_with_a_fixed_text() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    response = web.post(FORM, data=form(web, input="ab"))
    assert response.status_code == 422 and posts(api) == []
    assert "Escribe entre 3 y 500 caracteres." in response.text
    assert 'value="ab"' in response.text


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (422, "invalid_input"),
        (429, "daily_limit"),
        (422, "duplicate"),
        (422, "manual_needs_a_query"),
    ],
)
def test_domain_rejection_returns_the_form_with_the_fixed_text(status: int, code: str) -> None:
    body = {"code": code, "message": "TEXTO DE LA API"}
    api = Api({POST: (status, body)})
    web = make_client(api)
    response = web.post(FORM, data=form(web, input="mi consulta"))
    assert response.status_code == status
    assert CODE_MESSAGES[code] in response.text
    assert "TEXTO DE LA API" not in response.text
    assert 'value="mi consulta"' in response.text
    assert nonce_of(response.text) != NONCE


def test_unknown_code_does_not_reflect_the_api_text() -> None:
    api = Api({POST: (422, {"code": "zzz", "message": "<b>SECRETO</b>"})})
    web = make_client(api)
    response = web.post(FORM, data=form(web))
    assert "SECRETO" not in response.text and response.status_code == 422


def test_manual_mode_with_a_query() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    data = form(
        web, input="dinosaurios", manual="1", label="Criaturas", family="animales", parent=""
    )
    assert web.post(FORM, data=data).status_code == 303
    (call,) = posts(api)
    assert json.loads(call.content) == {
        "input": "dinosaurios",
        "manual": {"label": "Criaturas", "family": "animales", "parent": None},
    }


def test_manual_button_forces_manual_mode() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    data = form(web, input="dinosaurios", modo="manual", label="Criaturas", family="animales")
    data["parent"] = "Historia"
    assert web.post(FORM, data=data).status_code == 303
    assert json.loads(posts(api)[0].content)["manual"]["parent"] == "Historia"


def test_manual_mode_with_a_channel_is_rejected_by_the_api_with_its_text() -> None:
    api = Api({POST: (422, {"code": "manual_needs_a_query", "message": "x"})})
    web = make_client(api)
    data = form(web, input="@canal", manual="1", label="Criaturas", family="animales")
    response = web.post(FORM, data=data)
    assert response.status_code == 422
    assert CODE_MESSAGES["manual_needs_a_query"] in response.text
    assert len(posts(api)) == 1


def test_manual_invalid_fields_never_reach_the_api() -> None:
    api = Api({POST: accepted})
    web = make_client(api)
    data = form(web, input="dinosaurios", manual="1", label="Criaturas", family="MAL")
    response = web.post(FORM, data=data)
    assert response.status_code == 422 and posts(api) == []
    assert "Revisa la etiqueta" in response.text
    assert 'value="Criaturas"' in response.text and 'value="MAL"' in response.text


def test_api_down_on_post_is_503_with_the_form_kept() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    web = make_client(Api({POST: down}))
    response = web.post(FORM, data=form(web, input="mi consulta"))
    assert response.status_code == 503 and "API no disponible" in response.text
    assert 'value="mi consulta"' in response.text


def test_response_without_a_valid_id_is_not_followed() -> None:
    for bad in ({"id": "../../x"}, {"id": 7}, {}):
        api = Api({POST: (202, bad)})
        web = make_client(api)
        response = web.post(FORM, data=form(web))
        assert response.status_code == 503 and "location" not in response.headers


def test_hostile_input_is_escaped_in_the_form() -> None:
    api = Api({POST: (422, {"code": "invalid_input", "message": "x"})})
    web = make_client(api)
    response = web.post(FORM, data=form(web, input=HOSTILE))
    assert "&lt;script&gt;" in response.text and "<script>alert" not in response.text


def test_queued_detail_polls_every_5s() -> None:
    web = make_client(Api({GET: (200, item())}))
    page = web.get(f"/subnichos/propuestas/{PID}")
    assert page.status_code == 200
    for text in (
        "Preparando la propuesta",
        "En cola",
        "Qué está pasando",
        "@nombredelcanal",
        "Actualizar",
        'hx-trigger="every 5s"',
        f'hx-get="/subnichos/propuestas/{PID}"',
    ):
        assert text in page.text
    assert "<style" not in page.text and " style=" not in page.text


def test_running_detail_polls_and_says_preparing() -> None:
    page = make_client(Api({GET: (200, item(status="running"))})).get(
        f"/subnichos/propuestas/{PID}"
    )
    assert "Preparando" in page.text and 'hx-trigger="every 5s"' in page.text


def test_fragment_request_returns_only_the_fragment() -> None:
    web = make_client(Api({GET: (200, item())}))
    fragment = web.get(f"/subnichos/propuestas/{PID}", headers={"HX-Request": "true"})
    assert fragment.status_code == 200 and "<html" not in fragment.text
    assert 'hx-trigger="every 5s"' in fragment.text


def test_polling_stops_when_the_request_is_done() -> None:
    web = make_client(Api({GET: (200, ready())}))
    fragment = web.get(f"/subnichos/propuestas/{PID}", headers={"HX-Request": "true"})
    assert "hx-trigger" not in fragment.text and "Ancient Rome" in fragment.text
    failed = make_client(
        Api({GET: (200, item(status="failed", error={"code": "abandoned", "message": "m"}))})
    ).get(f"/subnichos/propuestas/{PID}")
    assert "hx-trigger" not in failed.text


def test_ready_detail_shows_the_hypothesis_and_the_approve_button() -> None:
    page = make_client(Api({GET: (200, ready())})).get(f"/subnichos/propuestas/{PID}")
    for text in (
        "Ancient Rome",
        "Hipótesis",
        "history",
        "Historia militar explicada",
        "ancient rome facts",
        "how rome fell",
        "@nombredelcanal",
        "Revisar y aprobar",
        'href="/subnichos/ancient-rome/aprobar"',
    ):
        assert text in page.text
    assert "Origen" not in page.text and "hx-trigger" not in page.text


def test_ready_detail_with_a_hostile_slug_has_no_approve_link() -> None:
    data = ready()
    data["hypothesis"]["slug"] = '"><script>x</script>'
    data["hypothesis"]["label"] = HOSTILE
    page = make_client(Api({GET: (200, data)})).get(f"/subnichos/propuestas/{PID}")
    assert "Revisar y aprobar" not in page.text and "<script>alert" not in page.text
    assert "&lt;script&gt;" in page.text


def test_failed_detail_shows_the_fixed_text_and_retry_with_q() -> None:
    data = item(
        status="failed",
        input="mi consulta",
        error={"code": "youtube_unreachable", "message": "RAW"},
    )
    page = make_client(Api({GET: (200, data)})).get(f"/subnichos/propuestas/{PID}")
    assert CODE_MESSAGES["youtube_unreachable"] in page.text and "RAW" not in page.text
    assert "Volver a intentar" in page.text
    assert 'href="/subnichos/proponer?q=mi+consulta"' in page.text


def test_failed_duplicate_never_shows_the_detail() -> None:
    data = item(
        status="failed", error={"code": "duplicate:query:x", "message": "duplicate:query:x"}
    )
    page = make_client(Api({GET: (200, data)})).get(f"/subnichos/propuestas/{PID}")
    assert CODE_MESSAGES["duplicate"] in page.text and "query:x" not in page.text


@pytest.mark.parametrize(
    "bad", ["7", "abc", "0B1C2D3E-4F50-4A6B-8C7D-9E0F1A2B3C4D", PID + "x", "١" * 32]
)
def test_non_uuid_id_is_404_and_calls_nothing(bad: str) -> None:
    api = Api()
    response = make_client(api).get(f"/subnichos/propuestas/{bad}")
    assert response.status_code == 404 and api.calls == []


def test_unknown_proposal_is_404() -> None:
    api = Api({GET: (404, {"detail": {"code": "not_found", "message": "x"}})})
    assert make_client(api).get(f"/subnichos/propuestas/{PID}").status_code == 404


def test_api_down_on_detail_is_503_with_a_notice() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    web = make_client(Api({GET: down}))
    page = web.get(f"/subnichos/propuestas/{PID}")
    assert page.status_code == 503 and "API no disponible" in page.text
    # A polling request keeps the current screen and tries again later.
    assert (
        web.get(f"/subnichos/propuestas/{PID}", headers={"HX-Request": "true"}).status_code == 204
    )


def test_malformed_payload_degrades_to_failed_not_a_500() -> None:
    web = make_client(Api({GET: (200, {"status": ["x"], "hypothesis": 3})}))
    page = web.get(f"/subnichos/propuestas/{PID}")
    assert page.status_code == 200 and "Volver a intentar" in page.text


def test_hostile_input_in_detail_is_escaped() -> None:
    page = make_client(Api({GET: (200, item(input=HOSTILE))})).get(f"/subnichos/propuestas/{PID}")
    assert "&lt;script&gt;" in page.text and "<script>alert" not in page.text


def test_detail_requires_a_session() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    assert web.get(f"/subnichos/propuestas/{PID}").status_code == 303


def test_entry_points_link_to_the_form() -> None:
    web = make_client(Api({("GET", "/api/v1/subniches"): (200, {"items": []})}))
    assert 'href="/subnichos/proponer"' in web.get("/subnichos").text
    assert 'href="/subnichos/proponer"' in web.get("/mas").text


def test_proponer_is_not_shadowed_by_the_slug_route() -> None:
    api = Api()
    make_client(api).get(FORM)
    assert api.calls == []
