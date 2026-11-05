# tests/test_web_niche_decision.py
"""Decision card of the niche detail (M19): POST /nichos/decidir with a note and a safe return."""

import json
import re
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.niche_decision import safe_target
from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    csrf_of,
    flow_item,
    make_client,
    niche_page,
)

LABEL = "historia militar explicada"
DETAIL = ("GET", f"/api/v1/market/niches/{LABEL}")
DECIDE = ("POST", f"/api/v1/market/niches/{LABEL}/decisions")
VIEW = f"/nichos/ver?etiqueta={quote(LABEL)}&formato=long"
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


def api_for(decide: Route | None = None, detail: object = None) -> Api:
    return Api(
        {
            DETAIL: (200, niche_page() if detail is None else detail),
            ("GET", "/api/v1/flow-research"): (200, {"items": [flow_item()]}),
            ("GET", "/api/v1/pilots"): (200, {"items": []}),
            ("GET", "/api/v1/status"): (200, {"radar_paused": True}),
            DECIDE: decide if decide is not None else (201, {}),
        }
    )


def post(web: TestClient, **over: str) -> httpx.Response:
    token = csrf_of(web.get(VIEW).text)
    data = {
        "csrf": token,
        "etiqueta": LABEL,
        "formato": "long",
        "decision": "tentativo",
        "nota": "",
        "volver": VIEW,
    }
    response: httpx.Response = web.post("/nichos/decidir", data=data | over)
    return response


def writes(api: Api) -> list[httpx.Request]:
    return [c for c in api.calls if c.method == "POST"]


def test_the_detail_shows_the_decision_card() -> None:
    text = make_client(api_for()).get(VIEW).text
    assert "Decisión del nicho" in text
    assert re.search(r'<form[^>]*method="post"[^>]*action="/nichos/decidir"', text)
    assert re.search(r'name="decision" value="tentativo"[^>]*checked', text)
    for value in ("nuevo", "descartado"):
        assert f'name="decision" value="{value}"' in text
    assert "Tentativo: lo quieres investigar. Descartado: se oculta de la lista." in text
    assert "Solo un nicho tentativo y con puntajes se puede investigar." in text
    assert "Nota (opcional)" in text and "Hasta 1000 caracteres." in text
    assert "Guardar decisión" in text
    assert f'name="volver" value="{VIEW}"' in text.replace("&amp;", "&")
    assert "<textarea" in text and 'maxlength="1000"' in text


def test_the_note_is_prefilled_and_escaped() -> None:
    detail = niche_page()
    detail["niche"]["decision"] = {  # type: ignore[index]
        "decision": "tentativo",
        "note": HOSTILE,
        "decided_at": "2026-11-02T00:00:00Z",
    }
    text = make_client(api_for(detail=detail)).get(VIEW).text
    assert ESCAPED in text and "<script>alert(1)" not in text


def test_without_csrf_nothing_reaches_the_api() -> None:
    api = api_for()
    web = make_client(api)
    response = web.post(
        "/nichos/decidir",
        data={"csrf": "x", "etiqueta": LABEL, "formato": "long", "decision": "tentativo"},
    )
    assert response.status_code == 403
    assert writes(api) == []


def test_a_valid_decision_with_a_note_posts_once_and_redirects_to_the_detail() -> None:
    api = api_for()
    response = post(make_client(api), nota="  Me gusta el nicho  ")
    assert response.status_code == 303
    assert response.headers["location"] == f"{VIEW}&aviso=decidido"
    sent = writes(api)
    assert len(sent) == 1
    assert json.loads(sent[0].content) == {
        "format": "long",
        "decision": "tentativo",
        "note": "Me gusta el nicho",
    }


def test_without_a_note_the_body_has_no_note() -> None:
    api = api_for()
    post(make_client(api))
    assert json.loads(writes(api)[0].content) == {"format": "long", "decision": "tentativo"}
    api = api_for()
    post(make_client(api), nota="   ")
    assert "note" not in json.loads(writes(api)[0].content)


def test_a_hostile_note_is_saved_as_is_and_painted_escaped_on_reload() -> None:
    api = api_for()
    web = make_client(api)
    post(web, nota=HOSTILE)
    assert json.loads(writes(api)[0].content)["note"] == HOSTILE
    detail = niche_page()
    detail["niche"]["decision"] = {"decision": "tentativo", "note": HOSTILE}  # type: ignore[index]
    text = make_client(api_for(detail=detail)).get(VIEW).text
    assert ESCAPED in text and "<script>alert(1)" not in text


def test_a_note_over_1000_characters_is_refused_and_kept() -> None:
    api = api_for()
    note = "a" * 1000 + "b"
    response = post(make_client(api), nota=note)
    assert response.status_code == 422
    assert writes(api) == []
    assert "La nota admite hasta 1000 caracteres." in response.text
    assert note in response.text


def test_a_note_of_exactly_1000_is_accepted() -> None:
    api = api_for()
    assert post(make_client(api), nota="a" * 1000).status_code == 303
    assert len(writes(api)) == 1


def test_a_note_with_control_characters_is_refused() -> None:
    api = api_for()
    response = post(make_client(api), nota="hola\x00mundo")
    assert response.status_code == 422 and writes(api) == []
    assert "La nota contiene caracteres no válidos." in response.text
    assert "La nota admite hasta 1000 caracteres." not in response.text


@pytest.mark.parametrize("decision", ["x", "", "TENTATIVO", "borrar"])
def test_a_decision_outside_the_list_is_refused_without_a_call(decision: str) -> None:
    api = api_for()
    response = post(make_client(api), decision=decision, nota="conservar")
    assert response.status_code == 422
    assert writes(api) == []
    assert "conservar" in response.text


@pytest.mark.parametrize(
    "volver",
    [
        "https://evil.test",
        "//evil.test",
        "javascript:alert(1)",
        "/nichos/../x",
        "/pilotos",
        "/nichos/ver/../x?etiqueta=a&formato=long",
        "/nichos/ver?etiqueta=a&formato=otro",
        "/nichos/ver?etiqueta=&formato=long",
        "/nichos/ver?etiqueta=a&formato=long&x=https://evil.test",
        "/nichos\\evil",
        "/nichos\nSet-Cookie: x=1",
        "/nichos ",
        "/nichos/ver?etiqueta=a b&formato=long",
        "/nichos/ver?etiqueta=%0a&formato=long",
        "/nichos/ver?etiqueta=%2e%2e&formato=long",
        "/nichos?formato=otro",
        "/nichos?next=https://evil.test",
        "/nichosevil",
        "",
    ],
)
def test_a_hostile_return_goes_to_the_niche_list(volver: str) -> None:
    api = api_for()
    response = post(make_client(api), volver=volver)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/nichos?aviso=")
    assert "evil" not in response.headers["location"]


def test_a_valid_return_is_kept() -> None:
    api = api_for()
    api.routes[("POST", "/api/v1/market/niches/otro/nicho/decisions")] = (201, {})
    web = make_client(api)
    assert post(web, volver="/nichos").headers["location"] == "/nichos?aviso=marcado"
    discarded = post(web, volver="/nichos", decision="descartado")
    assert discarded.headers["location"] == "/nichos?aviso=guardada"
    other = "/nichos/ver?etiqueta=otro%2Fnicho&formato=shorts&aviso=error"
    kept = post(web, volver=other, etiqueta="otro/nicho", formato="shorts").headers["location"]
    assert kept == "/nichos/ver?etiqueta=otro%2Fnicho&formato=shorts&aviso=decidido"


def test_safe_target_accepts_only_the_whitelist() -> None:
    assert safe_target("/nichos") == ("list", [])
    assert safe_target("/nichos/ver?etiqueta=a&formato=long") == (
        "detail",
        [("etiqueta", "a"), ("formato", "long")],
    )
    assert safe_target("/nichos/ver?etiqueta=a&etiqueta=b&formato=long") is None
    assert safe_target("/nichos/ver?etiqueta=" + "x" * 141 + "&formato=long") is None


def test_the_list_buttons_still_return_to_the_list() -> None:
    api = api_for()
    marked = post(make_client(api), volver="/nichos")
    assert marked.headers["location"] == "/nichos?aviso=marcado"
    assert json.loads(writes(api)[0].content) == {"format": "long", "decision": "tentativo"}


def test_a_404_from_the_api_gives_a_spanish_message() -> None:
    response = post(make_client(api_for(decide=(404, {"detail": "no"}))))
    assert response.status_code == 404
    assert "No se encontró lo que buscabas." in response.text


@pytest.mark.parametrize("status", [409, 422, 500])
def test_a_conflict_or_invalid_gives_a_fixed_message_and_503_without_trace(status: int) -> None:
    body = {"detail": "Traceback secreto"}
    response = post(make_client(api_for(decide=(status, body))), nota="no perder")
    assert response.status_code == 503
    assert "No se pudo guardar la decisión." in response.text
    assert "Traceback" not in response.text and "secreto" not in response.text
    assert "no perder" in response.text


def test_the_api_down_keeps_what_was_typed() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    response = post(make_client(api_for(decide=down)), nota="no perder esto")
    assert response.status_code == 503
    assert "no perder esto" in response.text
    assert "API no disponible" in response.text


def test_the_api_down_even_for_the_reread_keeps_what_was_typed() -> None:
    api = api_for()
    web = make_client(api)
    token = csrf_of(web.get(VIEW).text)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api.routes[DECIDE] = down
    api.routes[DETAIL] = down
    response = web.post(
        "/nichos/decidir",
        data={
            "csrf": token,
            "etiqueta": LABEL,
            "formato": "long",
            "decision": "tentativo",
            "nota": "sigue aqui",
            "volver": VIEW,
        },
    )
    assert response.status_code == 503
    assert "sigue aqui" in response.text and "Guardar decisión" in response.text


def test_the_detail_notices_come_from_fixed_keys() -> None:
    web = make_client(api_for())
    ok = web.get(VIEW + "&aviso=decidido").text
    assert "Decisión guardada." in ok
    bad = web.get(VIEW + "&aviso=error").text
    assert "No se pudo guardar la decisión." in bad
    hostile = web.get(VIEW, params={"aviso": HOSTILE}).text
    assert "evil.test" not in hostile


BROKEN = [{}, {"niche": None}, {"niche": {}}, {"niche": {"niche_label": LABEL}, "listings": None}]


@pytest.mark.parametrize("broken", BROKEN)
@pytest.mark.parametrize("failure", ["conflict", "down"])
def test_a_broken_detail_after_a_failed_save_never_gives_500(broken: object, failure: str) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = api_for(decide=(409, {"detail": "x"}) if failure == "conflict" else down)
    web = make_client(api)
    token = csrf_of(web.get(VIEW).text)
    api.routes[DETAIL] = (200, broken)
    response = web.post(
        "/nichos/decidir",
        data={
            "csrf": token,
            "etiqueta": LABEL,
            "formato": "long",
            "decision": "tentativo",
            "nota": "conservar",
            "volver": VIEW,
        },
    )
    assert response.status_code == 503
    assert "conservar" in response.text and "Guardar decisión" in response.text


def test_the_detail_shows_the_invalid_notice() -> None:
    text = make_client(api_for()).get(VIEW + "&aviso=invalida").text
    assert "Revisa la decisión y la nota." in text


def test_a_form_that_does_not_match_the_return_is_invalid() -> None:
    api = api_for()
    web = make_client(api)
    for over in ({"etiqueta": "otro"}, {"formato": "shorts"}):
        response = post(web, **over)
        assert response.status_code == 303
        assert response.headers["location"] == f"{VIEW}&aviso=invalida"
    assert writes(api) == []
