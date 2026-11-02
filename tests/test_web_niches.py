# tests/test_web_niches.py
import html
import json
import re

import httpx
from fastapi.testclient import TestClient
from markupsafe import escape

from nicheradar.web.app import create_app
from tests.web_helpers import (
    HOSTILE,
    Api,
    csrf_of,
    flow_item,
    make_client,
    niche_item,
    settings,
)

NICHES = ("GET", "/api/v1/market/niches")
FLOW = ("GET", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")
DECIDE_UNO = ("POST", "/api/v1/market/niches/uno/decisions")
TENTATIVE = {"decision": "tentativo", "note": None, "decided_at": "x"}


def api_with(*niches: dict[str, object], flows: list[dict[str, object]] | None = None) -> Api:
    return Api(
        {
            NICHES: (200, {"items": list(niches), "total": len(niches), "limit": 200, "offset": 0}),
            FLOW: (200, {"items": flows or []}),
            STATUS: (200, {"radar_paused": True}),
        }
    )


def cards_of(text: str) -> dict[str, str]:
    """Card markup keyed by niche name, so each assertion looks only at its own card."""
    blocks = re.findall(r'<article class="card">.*?</article>', text, re.S)
    named = {}
    for block in blocks:
        found = re.search(r'<span class="card__name">([^<]*)</span>', block)
        assert found, block
        named[html.unescape(found.group(1))] = block
    return named


def names_of(text: str) -> list[str]:
    return list(cards_of(text))


def niche_calls(api: Api) -> list[httpx.Request]:
    return [c for c in api.calls if (c.method, c.url.path) == NICHES]


def test_the_list_needs_a_session() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    response = web.get("/nichos")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fnichos"
    posted = web.post("/nichos/decidir", data={"etiqueta": "uno"})
    assert posted.status_code == 303 and posted.headers["location"].startswith("/login")


def test_the_page_shows_the_title_the_count_and_one_card_per_niche() -> None:
    api = api_with(niche_item("a uno"), niche_item("b dos", "shorts"))
    text = make_client(api).get("/nichos").text
    assert '<h1 class="h1">Nichos</h1>' in text
    assert '<p class="caption">De mayor a menor por Opportunity (0 a 100).</p>' in text
    assert names_of(text) == ["a uno", "b dos"]
    assert "<strong>2</strong> nichos" in text
    assert (
        '<a class="segmented__item segmented__item--on" href="/nichos" '
        'aria-current="page">Nichos</a>' in text
    )
    assert '<a class="segmented__item" href="/subnichos">Subnichos</a>' in text


def test_a_card_shows_the_real_scores_and_never_the_missing_ones() -> None:
    text = make_client(api_with(niche_item())).get("/nichos").text
    card = cards_of(text)["historia militar explicada"]
    assert "<dt>Opportunity</dt><dd>78</dd>" in card
    assert "<dt>Automat.</dt><dd>64</dd>" in card
    assert "<dt>Confianza</dt><dd>Media</dd>" in card
    assert re.findall(r"<dt>([^<]*)</dt>", card) == ["Opportunity", "Automat.", "Confianza"]


def test_a_niche_without_score_shows_its_missing_values_and_no_rank() -> None:
    unscored = niche_item(
        "sin puntaje",
        opportunity={
            "version": "v1",
            "value": None,
            "state": "insufficient_evidence",
            "components": {},
            "components_used": [],
        },
        automation={"version": "v1", "value": None, "components": {}, "policy_risk": None},
    )
    text = make_client(api_with(niche_item("con puntaje"), unscored)).get("/nichos").text
    cards = cards_of(text)
    assert '<span class="rank">1</span>' in cards["con puntaje"]
    assert '<span class="rank">—</span>' in cards["sin puntaje"]
    assert "<dt>Opportunity</dt><dd>sin puntaje</dd>" in cards["sin puntaje"]
    assert "<dt>Automat.</dt><dd>—</dd>" in cards["sin puntaje"]


def test_the_navigation_points_the_nichos_tab_to_the_niche_list() -> None:
    text = make_client(api_with(niche_item())).get("/nichos").text
    assert '<a class="tab tab--on" href="/nichos" aria-current="page">' in text
    assert 'href="/subnichos"><span class="tab__icon"' not in text


def test_the_primary_button_follows_decision_and_research_state() -> None:
    api = api_with(
        niche_item("sin decidir"),
        niche_item("tentativo", decision=TENTATIVE),
        niche_item("con dossier", decision=TENTATIVE),
        niche_item("investigando", decision=TENTATIVE),
        niche_item(
            "sin puntaje",
            opportunity={
                "version": "v1",
                "value": None,
                "state": "insufficient_evidence",
                "components": {},
                "components_used": [],
            },
        ),
        flows=[
            flow_item(
                "listo", niche_label="con dossier", id="11111111-1111-1111-1111-111111111111"
            ),
            flow_item(
                "en_curso", niche_label="investigando", id="22222222-2222-2222-2222-222222222222"
            ),
        ],
    )
    cards = cards_of(make_client(api).get("/nichos").text)
    assert (
        '<button class="btn btn--secondary" type="submit">Marcar tentativo</button>'
        in cards["sin decidir"]
    )
    assert (
        '<a class="btn btn--primary" href="/nichos/investigar?etiqueta=tentativo&amp;formato=long">'
        "Investigar</a>" in cards["tentativo"]
    )
    assert (
        '<a class="btn btn--secondary" href="/informes/11111111-1111-1111-1111-111111111111">'
        "Ver dossier</a>" in cards["con dossier"]
    )
    assert (
        '<a class="btn btn--secondary" href="/informes/22222222-2222-2222-2222-222222222222">'
        "Ver estado</a>" in cards["investigando"]
    )
    assert (
        '<button class="btn btn--secondary" type="button" disabled>Falta puntaje</button>'
        in cards["sin puntaje"]
    )
    for name in ("tentativo", "con dossier", "investigando", "sin puntaje"):
        assert "Marcar tentativo" not in cards[name]


def test_the_research_state_chip_comes_from_the_matching_label_and_format() -> None:
    api = api_with(
        niche_item("mismo", "long"),
        niche_item("mismo", "shorts"),
        flows=[flow_item("listo", niche_label="mismo", format="long")],
    )
    blocks = re.findall(
        r'<article class="card">.*?</article>', make_client(api).get("/nichos").text, re.S
    )
    assert len(blocks) == 2
    long_card, shorts_card = blocks
    assert '<span class="chip chip--green">Dossier listo</span>' in long_card
    assert "Dossier" not in shorts_card


def test_the_newest_research_wins_for_the_same_niche_and_format() -> None:
    api = api_with(
        niche_item("mismo"),
        flows=[
            flow_item("en_curso", niche_label="mismo", id="22222222-2222-2222-2222-222222222222"),
            flow_item("listo", niche_label="mismo", id="11111111-1111-1111-1111-111111111111"),
        ],
    )
    card = cards_of(make_client(api).get("/nichos").text)["mismo"]
    assert "Investigando" in card and "Dossier listo" not in card


def test_format_chips_count_the_whole_list_and_filter_in_the_web_layer() -> None:
    api = api_with(niche_item("l1"), niche_item("l2"), niche_item("s1", "shorts"))
    web = make_client(api)
    full = web.get("/nichos").text
    assert 'value="" checked>Todos 3</label>' in full
    assert 'value="long">Largos 2</label>' in full
    assert 'value="shorts">Shorts 1</label>' in full
    shorts = web.get("/nichos", params={"formato": "shorts"}).text
    assert names_of(shorts) == ["s1"]
    assert 'value="shorts" checked>Shorts 1</label>' in shorts
    assert 'value="" checked>Todos 3</label>' not in shorts
    assert "<strong>1</strong> nichos" in shorts


def test_filters_confianza_alta_and_con_ingresos() -> None:
    api = api_with(
        niche_item("alta con", confidence="alta"),
        niche_item("media", confidence="media"),
        niche_item("alta sin", confidence="alta", metrics={"n_income": 0, "n_listings": 3}),
    )
    web = make_client(api)
    assert names_of(web.get("/nichos", params={"alta": "1"}).text) == ["alta con", "alta sin"]
    assert names_of(web.get("/nichos", params={"ingresos": "1"}).text) == ["alta con", "media"]
    both = web.get("/nichos", params={"alta": "1", "ingresos": "1"}).text
    assert names_of(both) == ["alta con"]
    assert (
        "Ningún nicho coincide con los filtros."
        in web.get("/nichos", params={"formato": "shorts"}).text
    )


def test_the_order_is_passed_to_the_api_and_junk_is_ignored() -> None:
    api = api_with(niche_item())
    web = make_client(api)
    web.get("/nichos", params={"orden": "automation"})
    assert niche_calls(api)[-1].url.params["order"] == "automation"
    assert niche_calls(api)[-1].url.params["limit"] == "200"
    for params in ({"orden": "zzz"}, {"formato": "<script>"}, {"alta": "9"}):
        response = web.get("/nichos", params=params)
        assert response.status_code == 200 and "<script>" not in response.text
        assert niche_calls(api)[-1].url.params["order"] == "opportunity"
    web.get("/nichos")
    assert niche_calls(api)[-1].url.params["order"] == "opportunity"


def test_hostile_labels_are_escaped_and_the_link_is_encoded() -> None:
    label = "a/b:c&d " + HOSTILE
    api = api_with(
        niche_item(label, decision=TENTATIVE),
        niche_item(label + " dos"),
    )
    text = make_client(api).get("/nichos").text
    assert "<script>alert(1)</script>" not in text
    assert f'<span class="card__name">{escape(label)}</span>' in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert 'href="/nichos/investigar?etiqueta=a%2Fb%3Ac%26d%20' in text
    assert f'<input type="hidden" name="etiqueta" value="{escape(label + " dos")}">' in text
    assert "https://evil.test" not in cards_of(text)[label].split("</span>")[-1]  # link part


def test_an_htmx_request_gets_the_fragment_and_vary() -> None:
    api = api_with(niche_item("uno"))
    web = make_client(api)
    response = web.get("/nichos", headers={"hx-request": "true"})
    assert response.status_code == 200
    assert names_of(response.text) == ["uno"]
    assert "<html" not in response.text and "<h1" not in response.text
    assert response.headers["vary"] == "HX-Request, HX-History-Restore-Request"
    assert web.get("/nichos").headers["vary"] == "HX-Request, HX-History-Restore-Request"


def test_a_history_restore_request_gets_the_whole_page() -> None:
    web = make_client(api_with(niche_item("uno")))
    response = web.get(
        "/nichos", headers={"hx-request": "true", "hx-history-restore-request": "true"}
    )
    assert response.status_code == 200 and "<html" in response.text
    assert response.headers["vary"] == "HX-Request, HX-History-Restore-Request"


def test_an_unavailable_api_gives_a_clear_503_without_a_second_status_call() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({NICHES: boom, FLOW: (200, {"items": []}), STATUS: (200, {"radar_paused": False})})
    web = make_client(api)
    before = api.count(*STATUS)
    response = web.get("/nichos")
    assert response.status_code == 503 and "API no disponible" in response.text
    assert api.count(*STATUS) == before
    assert response.headers["vary"] == "HX-Request, HX-History-Restore-Request"


def test_an_unavailable_api_answers_an_htmx_request_with_a_200_error_fragment() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({NICHES: boom, FLOW: (200, {"items": []}), STATUS: (200, {"radar_paused": False})})
    response = make_client(api).get("/nichos", headers={"hx-request": "true"})
    assert response.status_code == 200
    assert '<div class="note note--rose" role="alert">' in response.text
    assert "<html" not in response.text


def test_when_only_the_research_list_fails_the_niches_still_show_without_research_chips() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api(
        {
            NICHES: (200, {"items": [niche_item("uno")], "total": 1, "limit": 200, "offset": 0}),
            FLOW: boom,
            STATUS: (200, {"radar_paused": True}),
        }
    )
    response = make_client(api).get("/nichos")
    assert response.status_code == 200 and names_of(response.text) == ["uno"]
    assert (
        '<div class="note note--amber">La lista de investigaciones no está disponible: '
        "no se muestra su estado.</div>" in response.text
    )


def test_an_empty_list_has_its_own_message() -> None:
    text = make_client(api_with()).get("/nichos").text
    assert '<p class="lead">Todavía no hay nichos. Los crea el radar de mercado.</p>' in text
    assert names_of(text) == []


def post_decide(web: TestClient, token: str, **over: str) -> httpx.Response:
    data = {
        "csrf": token,
        "etiqueta": "uno",
        "formato": "long",
        "decision": "tentativo",
        "volver": "/nichos",
    }
    response: httpx.Response = web.post("/nichos/decidir", data=data | over)
    return response


def test_the_decide_form_carries_the_csrf_and_the_fixed_fields() -> None:
    card = cards_of(make_client(api_with(niche_item("uno"))).get("/nichos").text)["uno"]
    assert '<form method="post" action="/nichos/decidir">' in card
    assert re.search(r'<input type="hidden" name="csrf" value="[^"]+">', card)
    assert '<input type="hidden" name="decision" value="tentativo">' in card
    assert '<input type="hidden" name="formato" value="long">' in card
    assert '<input type="hidden" name="volver" value="/nichos">' in card


def test_marking_tentative_posts_the_decision_and_redirects_with_a_notice() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(
            201, json={"niche_label": "uno", "format": "long", "decision": "tentativo"}
        )

    api = api_with(niche_item("uno"))
    api.routes[DECIDE_UNO] = accept
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    response = post_decide(web, token)
    assert response.status_code == 303
    assert response.headers["location"] == "/nichos?aviso=marcado"
    assert len(bodies) == 1
    assert json.loads(bodies[0]) == {"format": "long", "decision": "tentativo"}


def test_the_decision_label_is_quoted_in_the_api_path() -> None:
    seen: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path)
        return httpx.Response(201, json={})

    api = api_with(niche_item("a/b"))
    # Api matches on the decoded path, which is what the API handler would see for a%2Fb.
    api.routes[("POST", "/api/v1/market/niches/a/b/decisions")] = accept
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    response = post_decide(web, token, etiqueta="a/b")
    assert response.headers["location"] == "/nichos?aviso=marcado"
    assert seen == [b"/api/v1/market/niches/a%2Fb/decisions"]


def test_a_bad_csrf_or_decision_never_reaches_the_api() -> None:
    api = api_with(niche_item("uno"))
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    assert post_decide(web, "wrong").status_code == 403
    assert web.post("/nichos/decidir").status_code == 403
    invalid = (
        {"decision": "borrar"},
        {"formato": "otro"},
        {"etiqueta": ""},
        {"etiqueta": "x" * 141},
    )
    for over in invalid:
        response = post_decide(web, token, **over)
        assert response.status_code == 303
        assert response.headers["location"] == "/nichos?aviso=invalida"
    assert api.count(*DECIDE_UNO) == 0
    assert [c for c in api.calls if c.method == "POST" and "/decisions" in c.url.path] == []


def test_the_return_path_must_stay_inside_the_niche_list() -> None:
    api = api_with(niche_item("uno"))
    api.routes[DECIDE_UNO] = (201, {})
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    hostile = ("//evil.test", "https://evil.test", "/\\evil", "/subnichos", "/nichosevil", "")
    for target in hostile:
        response = post_decide(web, token, volver=target)
        assert response.headers["location"] == "/nichos?aviso=marcado"
    kept = post_decide(web, token, volver="/nichos?formato=shorts&aviso=error")
    assert kept.headers["location"] == "/nichos?formato=shorts&aviso=marcado"


def test_an_api_failure_on_decide_redirects_with_an_error_notice() -> None:
    api = api_with(niche_item("uno"))
    api.routes[DECIDE_UNO] = (404, {"detail": "Nicho no encontrado"})
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    assert post_decide(web, token).headers["location"] == "/nichos?aviso=error"
    api.routes[DECIDE_UNO] = lambda request: (_ for _ in ()).throw(httpx.ConnectError("down"))
    assert post_decide(web, token).headers["location"] == "/nichos?aviso=error"


def test_the_notice_comes_only_from_fixed_keys() -> None:
    web = make_client(api_with(niche_item("uno")))
    marked = web.get("/nichos", params={"aviso": "marcado"}).text
    assert '<div class="note note--green" role="status">Marcado como tentativo.</div>' in marked
    failed = web.get("/nichos", params={"aviso": "error"}).text
    assert 'class="note note--rose" role="status">No se pudo guardar la decisión.' in failed
    page = web.get("/nichos", params={"aviso": HOSTILE})
    assert page.status_code == 200
    assert 'role="status"' not in page.text and "evil.test" not in page.text
