# tests/test_web_subniche_card.py
import json
import re

import httpx

from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    channel,
    csrf_of,
    hypothesis_of,
    make_client,
    measurement,
    pilot_item,
    research,
    subniche_card,
    subniche_item,
)

SLUG = "prehistoric_creatures"
CARD = ("GET", f"/api/v1/subniches/{SLUG}")
ORDER = ("POST", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


def api_with(card: dict[str, object], **extra: object) -> Api:
    routes: dict[tuple[str, str], Route] = {
        CARD: (200, card),
        STATUS: (200, {"radar_paused": True}),
    }
    routes.update({("POST", path): order for path, order in extra.items()})  # type: ignore[misc]
    return Api(routes)


def page(card: dict[str, object], **params: str) -> str:
    return str(make_client(api_with(card)).get(f"/subnichos/{SLUG}", params=params).text)


PILOTS = ("GET", "/api/v1/pilots")
REPORT_ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"


def journey_of(text: str) -> list[tuple[str, str, str]]:
    return re.findall(
        r'journey__mark journey__mark--(\w+)".*?journey__name">([^<]*)</span>'
        r'<span class="journey__detail">([^<]*)<',
        text,
        re.S,
    )


def with_pilots(card: dict[str, object], pilots: Route) -> str:
    api = Api({CARD: (200, card), PILOTS: pilots, STATUS: (200, {"radar_paused": True})})
    return str(make_client(api).get(f"/subnichos/{SLUG}").text)


def start_form(text: str) -> re.Match[str] | None:
    return re.search(
        rf'<form method="post" action="/subnichos/{SLUG}/investigar">.*?'
        r'<button class="btn btn--primary" type="submit">([^<]+)</button>',
        text,
        re.S,
    )


def test_the_card_shows_the_measurement_channels_and_the_start_button() -> None:
    text = page(subniche_card())
    assert '<h1 class="h1 h1--md">Prehistoric Creatures</h1>' in text
    assert re.search(r'<span class="income__value[^"]*">US\$ 673 – 1\.682</span>', text)
    assert "mediana" in text.lower()
    assert "Medimos 29 canales de YouTube el 31/10/2026" in text
    assert (
        '<span class="row__label">Pequeños que despegaron</span><span class="row__value">19</span>'
        in text
    )
    assert (
        '<span class="row__label">Excluidos por idioma</span><span class="row__value">1</span>'
        in text
    )
    assert re.search(
        r'<span class="list__name">WUFO TV[^<]*'
        r'(<span class="chip chip--rose">Despegó</span>)?</span>'
        r'<span class="caption">39,6 mil suscriptores · 5,6 M de vistas al mes · '
        r"US\$ 11\.161 – 27\.902</span>",
        text,
    )
    match = start_form(text)
    assert match and match.group(1) == "Iniciar investigación en inglés"
    assert re.search(r'<input type="hidden" name="csrf" value="[^"]+">', text)


def test_the_measurement_time_uses_the_configured_timezone() -> None:
    assert "31/10/2026 07:00" in page(subniche_card())  # 12:00 UTC in America/Lima


def test_expired_channel_data_is_declared_not_hidden() -> None:
    text = page(subniche_card(channels=[], channels_available=False))
    assert '<p class="muted">Los datos de los canales vencieron' in text
    assert "WUFO TV" not in text


def test_an_unmeasured_subniche_has_no_start_form() -> None:
    text = page(subniche_card(measurement=None))
    assert '<div class="note note--amber">Todavía no medimos este subnicho.</div>' in text
    assert start_form(text) is None and "Iniciar investigación" not in text


def test_a_non_active_subniche_disables_the_button_with_the_reason() -> None:
    item = subniche_item(SLUG, status="paused")
    text = page(subniche_card(hypothesis=hypothesis_of(item)))
    assert start_form(text) is None
    assert re.search(
        r'<button class="btn btn--primary" type="button" disabled>'
        r"Iniciar investigación en inglés</button>"
        r'\s*<p class="caption">La hipótesis debe estar activa y tener al menos una medición\.</p>',
        text,
    )


def test_a_running_investigation_disables_the_button() -> None:
    text = page(subniche_card(research=research("en_curso")))
    assert start_form(text) is None
    assert re.search(r'<button class="btn btn--primary" type="button" disabled>', text)
    assert '<span class="chip chip--blue">Investigando</span>' in text


def test_a_finished_investigation_shows_its_state_without_a_start_button() -> None:
    text = page(subniche_card(research=research("listo")))
    assert '<span class="chip chip--green">Dossier listo</span>' in text
    assert start_form(text) is None and "<button" not in text.split("Investigación de flujo")[1]


def test_a_rejected_investigation_can_be_retried() -> None:
    match = start_form(page(subniche_card(research=research("rechazado"))))
    assert match and match.group(1) == "Reintentar investigación en inglés"


def test_the_notice_comes_only_from_a_fixed_set_of_keys() -> None:
    card = subniche_card()
    assert (
        '<div class="note note--green" role="status">'
        "Investigación creada. Claude Code la atenderá en la próxima sesión.</div>"
    ) in page(card, aviso="creada")
    assert 'role="status"' not in page(card)
    hostile = page(card, aviso=HOSTILE)
    assert 'role="status"' not in hostile
    assert "<script>" not in hostile and "evil.test" not in hostile and "negrita" not in hostile


def test_an_unknown_subniche_is_a_404_page() -> None:
    api = Api(
        {
            CARD: (404, {"detail": {"code": "not_found", "message": "Hipótesis no encontrada."}}),
            STATUS: (200, {"radar_paused": True}),
        }
    )
    response = make_client(api).get(f"/subnichos/{SLUG}")
    assert response.status_code == 404
    assert '<p class="lead">No se encontró lo que buscabas.</p>' in response.text


def test_weird_slugs_never_cause_a_500() -> None:
    web = make_client(Api({STATUS: (200, {"radar_paused": True})}))
    for path in (
        "/subnichos/mi%20slug",
        "/subnichos/a%2Fb",
        "/subnichos/" + "x" * 200,
        "/subnichos/%E2%98%83",
    ):
        assert web.get(path).status_code == 404, path


def test_the_slug_is_percent_encoded_towards_the_api() -> None:
    api = Api({STATUS: (200, {"radar_paused": True})})
    make_client(api).get("/subnichos/mi%20slug")
    assert [c.url.raw_path for c in api.calls if "subniches" in c.url.path] == [
        b"/api/v1/subniches/mi%20slug"
    ]


def test_an_overlong_slug_rejected_by_the_api_is_a_404_not_a_503() -> None:
    long = "x" * 200
    api = Api({("GET", f"/api/v1/subniches/{long}"): (422, {"detail": []}), STATUS: (200, {})})
    assert make_client(api).get(f"/subnichos/{long}").status_code == 404


def test_an_unavailable_api_shows_a_clear_message_with_503() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    response = make_client(Api({CARD: boom, STATUS: (200, {"radar_paused": True})})).get(
        f"/subnichos/{SLUG}"
    )
    assert response.status_code == 503 and "API no disponible" in response.text


def test_null_fields_from_the_real_api_do_not_break_the_card() -> None:
    card = subniche_card(
        measurement=measurement(income_low=None, income_high=None, rpm_source=None, excluded={}),
        channels=[channel(None, income_low=None, income_high=None, traction=False)],
    )
    text = page(card)
    assert "income__value" not in text and "UC" + "a" * 22 in text


def test_hostile_text_is_escaped_in_the_card() -> None:
    item = subniche_item(SLUG, label=HOSTILE, family=HOSTILE, queries=[HOSTILE])
    card = subniche_card(
        hypothesis=hypothesis_of(item),
        channels=[channel(HOSTILE)],
        measurement=measurement(rpm_source=HOSTILE, excluded={HOSTILE: 3}),
    )
    text = page(card)
    assert "<script>alert(1)</script>" not in text
    assert text.count(ESCAPED) >= 5  # title, h1, family chip, query, rpm source, channel, exclusion


def post_research(
    card: dict[str, object], order: object, **form: str
) -> tuple[httpx.Response, Api]:
    api = api_with(card, **{"/api/v1/flow-research": order})
    web = make_client(api)
    token = csrf_of(web.get(f"/subnichos/{SLUG}").text)
    return web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": token} | form), api


def test_starting_the_research_posts_the_hypothesis_own_format_and_language() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"id": "r1", "created": True})

    response, _ = post_research(
        subniche_card(), accept, language="es", format="shorts", niche_label="x"
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=creada"
    assert json.loads(bodies[0]) == {
        "niche_label": f"subniche:{SLUG}",
        "format": "long",
        "language": "en",
    }


def test_a_shorts_spanish_hypothesis_posts_its_own_values() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"id": "r1", "created": True})

    item = subniche_item(SLUG, language="es", format="shorts")
    post_research(subniche_card(hypothesis=hypothesis_of(item)), accept, language="en")
    assert json.loads(bodies[0])["language"] == "es" and json.loads(bodies[0])["format"] == "shorts"


def test_an_existing_order_is_reported_as_such() -> None:
    response, _ = post_research(subniche_card(), (200, {"id": "r1", "created": False}))
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=existente"


def test_an_api_conflict_and_an_api_failure_map_to_clear_notices() -> None:
    not_ready = {"detail": {"code": "subniche_not_ready", "message": "x"}}
    response, _ = post_research(subniche_card(), (409, not_ready))
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=no-lista"
    response, _ = post_research(subniche_card(), (500, {"detail": "x"}))
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=error"
    response, _ = post_research(subniche_card(), (404, {"detail": {"code": "not_found"}}))
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=error"


def test_a_post_without_or_with_a_foreign_csrf_token_never_reaches_the_api() -> None:
    api = api_with(
        subniche_card(), **{"/api/v1/flow-research": (201, {"id": "r1", "created": True})}
    )
    web = make_client(api)
    assert web.post(f"/subnichos/{SLUG}/investigar").status_code == 403
    assert web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": "wrong"}).status_code == 403
    assert api.count("POST", "/api/v1/flow-research") == 0


def test_posting_to_a_weird_slug_never_500s() -> None:
    web = make_client(api_with(subniche_card()))
    token = csrf_of(web.get(f"/subnichos/{SLUG}").text)
    for path in ("mi%20slug", "x" * 200):
        response = web.post(f"/subnichos/{path}/investigar", data={"csrf": token})
        assert response.status_code == 303 and response.headers["location"].endswith("?aviso=error")


def test_the_card_shows_the_journey_after_the_header_chips() -> None:
    text = with_pilots(subniche_card(), (200, {"items": []}))
    steps = journey_of(text)
    assert [s[:2] for s in steps] == [
        ("done", "Candidato"),
        ("done", "Decisión"),
        ("done", "Listo para investigar"),
        ("now", "Investigación de flujo"),
        ("pending", "Informe"),
        ("pending", "Piloto"),
    ]
    assert steps[1][2] == "Aprobada: activa" and steps[2][2] == "Medido el 31/10/2026"
    assert steps[3][2] == "Falta iniciarla (abajo)" and steps[5][2] == "Autorizas y se produce"
    assert text.index('class="tags"') < text.index("Recorrido hasta el piloto")
    assert text.index("Recorrido hasta el piloto") < text.index("Medimos 29 canales")


def test_an_open_pilot_of_the_subniche_changes_the_last_step() -> None:
    mine = pilot_item(niche_label=f"subniche:{SLUG}", format="long", status="en_ejecucion")
    other = pilot_item("pil_x", niche_label="subniche:otro", format="long")
    wrong_format = pilot_item("pil_y", niche_label=f"subniche:{SLUG}", format="shorts")
    items = {"items": [other, wrong_format, mine]}
    text = with_pilots(subniche_card(research=research("listo")), (200, items))
    assert journey_of(text)[-1] == ("now", "Piloto", "Piloto en ejecución")
    closed = pilot_item(niche_label=f"subniche:{SLUG}", status="cerrado")
    text = with_pilots(subniche_card(research=research("listo")), (200, {"items": [closed]}))
    assert journey_of(text)[-1] == ("now", "Piloto", "Decide si lo lanzas")


def test_the_pilots_are_read_with_a_limit() -> None:
    api = Api({CARD: (200, subniche_card()), PILOTS: (200, {"items": []}), STATUS: (200, {})})
    make_client(api).get(f"/subnichos/{SLUG}")
    calls = [c for c in api.calls if c.url.path == "/api/v1/pilots"]
    assert [c.url.params["limit"] for c in calls] == ["100"]


def test_a_failing_pilot_read_still_paints_the_card_with_a_notice() -> None:
    for pilots in ((500, {"detail": "x"}), (200, {"items": "roto"}), (200, [1]), (200, {})):
        text = with_pilots(subniche_card(), pilots)
        assert "No se pudo leer el estado del piloto" in text, pilots
        assert "Medimos 29 canales" in text and "Qué encontramos" in text


def test_the_decision_card_is_read_only_with_the_current_state_marked() -> None:
    expected = {
        "active": "Activa",
        "proposed": "Propuesta",
        "paused": "Pausada",
        "archived": "Archivada",
    }
    for status, name in expected.items():
        item = subniche_item(SLUG, status=status)
        text = page(subniche_card(hypothesis=hypothesis_of(item)))
        block = text.split("Decisión de la hipótesis")[1].split("</section>")[0]
        assert re.findall(r"<span[^>]*pill[^>]*>([^<]+)</span>", block) == [
            "Propuesta",
            "Activa",
            "Pausada",
            "Archivada",
        ]
        assert re.findall(r'<span class="pill pill--on"[^>]*>([^<]+)</span>', block) == [name]
        assert "<button" not in block and "<form" not in block and "<input" not in block
        assert (
            "Activa: se mide sola y se puede investigar. Pausada: deja de medirse. "
            "Archivada: se descarta. Solo una hipótesis activa y con al menos una medición "
            "se puede investigar." in block
        )
        assert "Aprobar, pausar o archivar se hará desde aquí cuando esté disponible." in block


def test_a_paused_or_archived_subniche_follows_the_journey_rulings() -> None:
    paused = subniche_item(SLUG, status="paused")
    steps = journey_of(page(subniche_card(hypothesis=hypothesis_of(paused))))
    assert steps[1] == ("done", "Decisión", "Pausada")
    assert steps[2] == ("now", "Listo para investigar", "Reanúdala para medirla")
    archived = subniche_item(SLUG, status="archived")
    steps = journey_of(page(subniche_card(hypothesis=hypothesis_of(archived))))
    assert steps[1] == ("now", "Decisión", "Archivada: se descarta")


def test_a_ready_dossier_links_to_the_report_and_drops_the_obsolete_note() -> None:
    text = page(subniche_card(research=research("listo")))
    assert f'<a class="btn btn--secondary" href="/informes/{REPORT_ID}">Ver dossier</a>' in text
    assert "siguiente corte" not in text
    assert "<button" not in text.split("Investigación de flujo")[-1]


def test_a_ready_dossier_with_a_bad_id_has_no_link() -> None:
    for bad in ("../x", "javascript:1", REPORT_ID + "\n", None):
        text = page(subniche_card(research=research("listo", id=bad)))
        assert "Ver dossier" not in text and "siguiente corte" not in text, bad
        assert '<p class="caption">El informe no está disponible.</p>' in text, bad
        assert "javascript:" not in text


def test_the_footer_back_link_is_gone() -> None:
    assert "Volver a Subnichos" not in page(subniche_card())


def test_broken_shapes_never_cause_a_500() -> None:
    for over in (
        {"research": "roto"},
        {"research": {"status": ["x"], "id": 3}},
        {"measurement": {"measured_at": "no-fecha"}},
    ):
        api = Api(
            {
                CARD: (200, subniche_card(**over)),
                PILOTS: (200, {"items": [None, 3]}),
                STATUS: (200, {}),
            }
        )
        response = make_client(api).get(f"/subnichos/{SLUG}")
        assert response.status_code in (200, 503), over


def test_a_non_string_hypothesis_status_is_a_shape_error() -> None:
    broken = {**hypothesis_of(subniche_item(SLUG)), "status": ["x"]}
    api = Api(
        {
            CARD: (200, subniche_card(hypothesis=broken)),
            PILOTS: (200, {"items": []}),
            STATUS: (200, {}),
        }
    )
    assert make_client(api).get(f"/subnichos/{SLUG}").status_code == 503


def test_a_shorts_subniche_crosses_only_shorts_pilots() -> None:
    item = subniche_item(SLUG, format="shorts")
    card = subniche_card(hypothesis=hypothesis_of(item), research=research("listo"))
    short = pilot_item(
        "pil_s", niche_label=f"subniche:{SLUG}", format="shorts", status="en_ejecucion"
    )
    long = pilot_item("pil_l", niche_label=f"subniche:{SLUG}", format="long", status="entregado")
    text = with_pilots(card, (200, {"items": [long, short]}))
    assert journey_of(text)[-1] == ("now", "Piloto", "Piloto en ejecución")
    text = with_pilots(card, (200, {"items": [long]}))
    assert journey_of(text)[-1] == ("now", "Piloto", "Decide si lo lanzas")


def test_hostile_pilot_text_is_escaped_in_the_journey() -> None:
    mine = pilot_item(niche_label=f"subniche:{SLUG}", format="long", status=HOSTILE)
    text = with_pilots(subniche_card(), (200, {"items": [mine]}))
    assert "<script>alert(1)</script>" not in text


def test_the_card_has_a_back_link_to_the_subniche_list() -> None:
    text = page(subniche_card())
    assert re.search(r'<a class="backlink" href="/subnichos">‹ Subnichos</a>', text)
