# tests/test_web_research.py
import json

import httpx
import pytest

from nicheradar.web.research import language_options
from tests.web_helpers import HOSTILE, Api, csrf_of, make_client, niche_detail

LABEL = "historia militar explicada"
# httpx exposes the decoded path, so the label is written with its spaces.
DETAIL = ("GET", "/api/v1/market/niches/historia militar explicada")
ORDER = ("POST", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")
URL = "/nichos/investigar?etiqueta=historia%20militar%20explicada&formato=long"
ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"


def api_with(detail: dict[str, object] | None = None, order: object = None) -> Api:
    routes: dict[tuple[str, str], object] = {
        DETAIL: (200, detail or niche_detail()),
        STATUS: (200, {"radar_paused": True}),
        ORDER: order if order is not None else (201, {"id": ID, "created": True}),
    }
    return Api(routes)  # type: ignore[arg-type]


def test_language_options_suggest_the_clear_leader_only() -> None:
    clear = language_options(
        [
            {"language": "en", "share_pct": 80.0},
            {"language": "es", "share_pct": 15.0},
            {"language": "unknown", "share_pct": 5.0},
        ]
    )
    assert clear["suggested"] == "en" and clear["unknown_share"] == 5 and not clear["no_choice"]
    assert [(o["code"], o["share"], o["suggested"]) for o in clear["options"]] == [
        ("en", 80, True),
        ("es", 15, False),
    ]
    tie = language_options(
        [
            {"language": "en", "share_pct": 45.0},
            {"language": "es", "share_pct": 45.0},
            {"language": "unknown", "share_pct": 10.0},
        ]
    )
    assert tie["suggested"] is None and not any(o["suggested"] for o in tie["options"])
    unknown_leads = language_options(
        [{"language": "unknown", "share_pct": 60.0}, {"language": "en", "share_pct": 40.0}]
    )
    assert unknown_leads["suggested"] is None
    only_unknown = language_options([{"language": "unknown", "share_pct": 100.0}])
    assert only_unknown["no_choice"] is True and only_unknown["options"] == []
    assert language_options([])["no_choice"] is True


def test_the_page_lists_languages_with_the_suggestion_and_the_explanations() -> None:
    text = make_client(api_with()).get(URL).text
    assert "<title>Iniciar investigación · NicheRadar</title>" in text
    assert "Iniciar investigación de flujo" in text
    assert 'name="idioma" value="en" checked' in text and 'name="idioma" value="es"' in text
    assert 'value="es" checked' not in text
    assert "Sugerido" in text and "80%" in text and "15%" in text
    assert "Sin dato" in text and "no se puede elegir" in text
    assert "Qué pasa al iniciar" in text and 'name="csrf"' in text
    assert "Iniciar investigación en inglés" in text


def test_with_no_clear_leader_nothing_is_preselected_and_the_button_waits() -> None:
    detail = niche_detail(mix=[("en", 45.0), ("es", 45.0), ("unknown", 10.0)])
    text = make_client(api_with(detail)).get(URL).text
    assert " checked" not in text.split('name="idioma"', 1)[1].split("</form>")[0]
    assert "Elige un idioma para continuar" in text
    assert "Iniciar investigación en" not in text


def test_a_niche_without_known_language_cannot_be_started() -> None:
    text = make_client(api_with(niche_detail(mix=[("unknown", 100.0)]))).get(URL).text
    assert "no se puede iniciar la investigación todavía" in text
    assert " disabled" in text.split('class="btn btn--primary"', 1)[1].split(">", 1)[0]


@pytest.mark.parametrize(
    "qs", ["etiqueta=x&formato=zzz", "", "etiqueta=..&formato=long", "etiqueta=.&formato=long"]
)
def test_junk_queries_are_404_and_never_reach_the_api(qs: str) -> None:
    api = api_with()
    assert make_client(api).get("/nichos/investigar?" + qs).status_code == 404
    assert api.count(*DETAIL) == 0


def test_an_unknown_niche_is_a_404() -> None:
    api = Api(
        {DETAIL: (404, {"detail": "Nicho no encontrado"}), STATUS: (200, {"radar_paused": True})}
    )
    response = make_client(api).get(URL)
    assert response.status_code == 404 and "No se encontró lo que buscabas" in response.text
    assert api.count(*STATUS) == 0


def test_an_unavailable_api_gives_503() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({DETAIL: boom, STATUS: (200, {"radar_paused": False})})
    response = make_client(api).get(URL)
    assert response.status_code == 503 and "API no disponible" in response.text
    assert api.count(*STATUS) == 0


def test_the_label_is_escaped_in_the_page() -> None:
    label = "a:b " + HOSTILE
    api = Api(
        {
            ("GET", f"/api/v1/market/niches/{label}"): (200, niche_detail(label)),
            STATUS: (200, {"radar_paused": True}),
        }
    )
    text = (
        make_client(api)
        .get("/nichos/investigar", params={"etiqueta": label, "formato": "long"})
        .text
    )
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text
    assert api.count("GET", f"/api/v1/market/niches/{label}") == 1


def post(web, token: str, **over: str):  # type: ignore[no-untyped-def]
    data = {"csrf": token, "etiqueta": LABEL, "formato": "long", "idioma": "en"}
    return web.post("/nichos/investigar", data=data | over)


def test_starting_posts_the_chosen_language_and_redirects_to_the_report() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"id": ID, "created": True})

    web = make_client(api_with(order=accept))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 303
    assert response.headers["location"] == f"/informes/{ID}?aviso=creada"
    assert len(bodies) == 1
    assert json.loads(bodies[0]) == {"niche_label": LABEL, "format": "long", "language": "en"}


def test_an_existing_order_goes_to_its_report_with_the_existing_notice() -> None:
    api = api_with(order=(200, {"id": ID, "created": False}))
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, token).headers["location"] == f"/informes/{ID}?aviso=existente"


@pytest.mark.parametrize("bad_id", ["x", "../admin", f"{ID}/../x", ID.upper(), "", 7])
def test_a_malformed_returned_id_is_never_used_in_the_redirect(bad_id: object) -> None:
    api = api_with(order=(201, {"id": bad_id, "created": True}))
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 303 and response.headers["location"] == "/nichos?aviso=error"


@pytest.mark.parametrize("language", ["unknown", "xx1", "EN", "", "en-us", "<script>"])
def test_an_invalid_language_is_rejected_before_any_further_api_call(language: str) -> None:
    api = api_with()
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token, idioma=language)
    assert response.status_code == 422 and "Elige un idioma válido" in response.text
    assert "<script>" not in response.text
    assert api.count(*ORDER) == 0
    assert api.count(*DETAIL) == 1  # only the GET that rendered the form


def test_a_language_not_in_the_mix_is_rejected_and_the_form_is_shown_again() -> None:
    api = api_with()
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token, idioma="ru")
    assert response.status_code == 422 and "Elige un idioma válido de la lista" in response.text
    assert 'name="idioma" value="en"' in response.text
    assert api.count(*ORDER) == 0


@pytest.mark.parametrize(
    "over",
    [
        {"etiqueta": ""},
        {"etiqueta": "x" * 141},
        {"etiqueta": "."},
        {"etiqueta": ".."},
        {"formato": "zzz"},
        {"formato": ""},
    ],
)
def test_a_bad_label_or_format_on_post_never_reaches_the_api(over: dict[str, str]) -> None:
    api = api_with()
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token, **over)
    assert response.status_code == 404
    assert api.count(*ORDER) == 0 and api.count(*DETAIL) == 1


def test_bad_or_missing_csrf_is_a_403_without_api_calls() -> None:
    api = api_with()
    web = make_client(api)
    assert post(web, "wrong").status_code == 403
    assert web.post("/nichos/investigar").status_code == 403
    assert api.count(*ORDER) == 0 and api.count(*DETAIL) == 0


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("not_tentative", "Primero marca el nicho como tentativo para poder investigarlo."),
        ("no_evidence", "El nicho todavía no tiene puntaje: falta evidencia para investigarlo."),
        ("invalid_language", "El idioma no es válido: elige uno de la lista."),
        ("gate_failed", "El nicho no pasa una compuerta de selección."),
        ("not_found", "No se encontró el nicho."),
    ],
)
def test_conflicts_map_to_clear_messages(code: str, message: str) -> None:
    api = api_with(order=(409, {"detail": {"code": code, "message": "x"}}))
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and message in response.text
    assert 'name="idioma" value="en" checked' in response.text  # the choice is kept


def test_an_unknown_conflict_code_falls_back_to_the_api_message_escaped() -> None:
    detail = {"code": "other", "message": HOSTILE}
    web = make_client(api_with(order=(409, {"detail": detail})))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_a_failed_gate_lists_the_api_reasons_escaped() -> None:
    detail = {
        "code": "gate_failed",
        "message": "x",
        "reasons": [{"gate": "automation", "message": HOSTILE}],
    }
    web = make_client(api_with(order=(409, {"detail": detail})))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "<li>" in response.text


def test_an_api_outage_on_post_keeps_the_form_with_a_message() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = api_with(order=boom)
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    status_before = api.count(*STATUS)
    response = post(web, token)
    assert response.status_code == 503 and "API no disponible" in response.text
    assert 'name="idioma" value="en"' in response.text
    assert api.count(*STATUS) == status_before  # no extra badge call after a failed API call


def test_the_detail_failing_on_post_is_an_error_page_without_creating_anything() -> None:
    api = api_with()
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    api.routes[DETAIL] = (404, {"detail": "Nicho no encontrado"})
    response = post(web, token)
    assert response.status_code == 404 and api.count(*ORDER) == 0
