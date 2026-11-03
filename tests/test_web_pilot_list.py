# tests/test_web_pilot_list.py
import html
import re
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from tests.web_helpers import HOSTILE, Api, make_client, pilot_item, settings

PILOTS = ("GET", "/api/v1/pilots")
STATUS = ("GET", "/api/v1/status")
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
TRUNCATION = "Se cargan como máximo 100 pilotos: puede haber más que no se ven en esta pantalla."
EMPTY = "Todavía no hay pilotos. Se crean al autorizar un informe de investigación."


def api_with(*items: object, body: object | None = None) -> Api:
    payload = body if body is not None else {"items": list(items)}
    return Api({PILOTS: (200, payload), STATUS: (200, {"radar_paused": False})})


def client(api: Api) -> TestClient:
    return make_client(api, clock=lambda: NOW.timestamp())


def pilot(n: int, **over: object) -> dict[str, object]:
    return pilot_item(f"pil_20261102_p{n}", niche_label=f"nicho {n}", **over)


def cards_of(text: str) -> dict[str, str]:
    """Card markup keyed by niche name, so each assertion looks only at its own card."""
    blocks = re.findall(r'<article class="card">.*?</article>', text, re.S)
    named = {}
    for block in blocks:
        found = re.search(r'<span class="card__name">([^<]*)</span>', block)
        assert found, block
        named[html.unescape(found.group(1))] = block
    return named


def pill(key: str, label: str, count: int, checked: bool) -> str:
    mark = " checked" if checked else ""
    return (
        f'<label class="pill"><input type="radio" name="filtro" value="{key}"{mark}>'
        f"{label} {count}</label>"
    )


def test_the_list_needs_a_session_and_shows_title_filters_and_one_card_per_pilot() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    response = web.get("/pilotos")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fpilotos"
    api = api_with(pilot(1), pilot(2, status="en_ejecucion"))
    text = client(api).get("/pilotos").text
    assert '<h1 class="h1">Pilotos</h1>' in text
    assert (
        '<p class="caption">Dónde está cada uno, qué lo frena y cuándo hay decisión. '
        "Fechas tentativas.</p>" in text
    )
    assert list(cards_of(text)) == ["nicho 1", "nicho 2"]
    assert pill("todos", "Todos", 2, True) in text
    assert pill("activos", "Activos", 2, False) in text
    assert pill("bloqueo", "Con bloqueo", 0, False) in text
    assert pill("cerrados", "Cerrados", 0, False) in text
    listed = [c for c in api.calls if c.url.path == PILOTS[1]]
    assert len(listed) == 1 and dict(listed[0].url.params) == {"limit": "100"}


def test_status_chips_use_the_spanish_names() -> None:
    items = [
        pilot(1, status="entregado"),
        pilot(2, status="en_ejecucion"),
        pilot(3, status="decision_pendiente"),
        pilot(4, status="cerrado"),
        pilot(5, status="cancelado"),
        pilot(6, status="autorizado"),
    ]
    cards = cards_of(client(api_with(*items)).get("/pilotos").text)
    assert '<span class="chip chip--amber">Preparando</span>' in cards["nicho 1"]
    assert '<span class="chip chip--green">En ejecución</span>' in cards["nicho 2"]
    assert '<span class="chip chip--rose">Decisión pendiente</span>' in cards["nicho 3"]
    assert '<span class="chip chip--neutral">Cerrado</span>' in cards["nicho 4"]
    assert '<span class="chip chip--neutral">Cancelado</span>' in cards["nicho 5"]
    assert '<span class="chip chip--neutral">Autorizado</span>' in cards["nicho 6"]
    assert '<span class="chip chip--neutral">Largo</span>' in cards["nicho 1"]
    assert "Cerrado" not in cards["nicho 1"] and "Preparando" not in cards["nicho 4"]


def _mixed_api() -> Api:
    return api_with(
        pilot(1, status="en_ejecucion"),
        pilot(2, status="decision_pendiente", needs_decision=True),
        pilot(3, status="cerrado"),
        pilot(4, status="cancelado", needs_decision=True),
    )


@pytest.mark.parametrize(
    ("key", "names"),
    [
        ("", ["nicho 1", "nicho 2", "nicho 3", "nicho 4"]),
        ("todos", ["nicho 1", "nicho 2", "nicho 3", "nicho 4"]),
        ("activos", ["nicho 1", "nicho 2"]),
        ("bloqueo", ["nicho 2"]),
        ("cerrados", ["nicho 3", "nicho 4"]),
    ],
)
def test_filters_todos_activos_con_bloqueo_cerrados_and_their_counts(
    key: str, names: list[str]
) -> None:
    text = client(_mixed_api()).get("/pilotos", params={"filtro": key}).text
    assert list(cards_of(text)) == names
    selected = key or "todos"
    assert pill("todos", "Todos", 4, selected == "todos") in text
    assert pill("activos", "Activos", 2, selected == "activos") in text
    assert pill("bloqueo", "Con bloqueo", 1, selected == "bloqueo") in text
    assert pill("cerrados", "Cerrados", 2, selected == "cerrados") in text
    assert text.count(" checked>") == 1


@pytest.mark.parametrize("junk", ["x", "TODOS", "activos&x=1", "<script>", "%00", "bloqueo\n"])
def test_junk_filter_values_fall_back_to_todos(junk: str) -> None:
    text = client(_mixed_api()).get("/pilotos", params={"filtro": junk}).text
    assert len(cards_of(text)) == 4
    assert pill("todos", "Todos", 4, True) in text and text.count(" checked>") == 1


def test_each_card_shows_blockers_next_action_progress_and_the_panel_link() -> None:
    blocked = pilot(
        1,
        status="en_ejecucion",
        needs_decision=True,
        channel_last_contact_at="2026-10-30T00:00:00Z",
        totals={
            "videos": 4,
            "published": 3,
            "measured": 1,
            "by_stage": {"unknown": 1, "awaiting_human": 2},
            "spent_usd": 1,
            "equivalent_usd": 2,
            "machine_minutes": 10,
            "machine_minutes_complete": True,
        },
    )
    clean = pilot(2, status="entregado")
    cards = cards_of(client(api_with(blocked, clean)).get("/pilotos").text)
    card = cards["nicho 1"]
    assert re.findall(r'<li class="blocker blocker--(\w+)">([^<]*)</li>', card) == [
        ("contacto", "Tu Mac está sin contacto hace 108 h"),
        ("desconocido", "1 video con estado desconocido"),
        ("decision", "Hay una decisión pendiente"),
    ]
    assert '<p class="pilot__next"><strong>Siguiente:</strong> Decide si sigue o cierra</p>' in card
    assert '<p class="caption pilot__progress">3 videos</p>' in card
    assert '<a class="btn btn--secondary" href="/pilotos/pil_20261102_p1">Abrir</a>' in card
    assert 'Canal: <span class="pilot__channel">canal-historias</span>' in card
    assert "Sin bloqueos" not in card
    other = cards["nicho 2"]
    assert '<p class="caption pilot__ok">Sin bloqueos</p>' in other and "blocker" not in other
    assert "pilot__next" not in other
    assert '<p class="caption pilot__progress">0 videos</p>' in other


def test_the_next_action_for_waiting_videos_and_an_undelivered_package() -> None:
    waiting = pilot(
        1,
        status="en_ejecucion",
        totals={
            "videos": 1,
            "published": 0,
            "measured": 0,
            "by_stage": {"awaiting_human": 1},
            "spent_usd": 0,
            "equivalent_usd": 0,
            "machine_minutes": 0,
            "machine_minutes_complete": True,
        },
    )
    undelivered = pilot(2, status="autorizado", delivered_at=None)
    cards = cards_of(client(api_with(waiting, undelivered)).get("/pilotos").text)
    assert (
        "<strong>Siguiente:</strong> 1 video espera tu veredicto en el canal</p>"
        in cards["nicho 1"]
    )
    assert "<strong>Siguiente:</strong> Falta que tu Mac baje el paquete</p>" in cards["nicho 2"]


def test_a_missing_channel_reads_to_be_defined() -> None:
    card = cards_of(client(api_with(pilot(1, target_channel=None))).get("/pilotos").text)["nicho 1"]
    assert 'Canal: <span class="pilot__channel">canal por definir</span>' in card


@pytest.mark.parametrize(
    "bad_id",
    [
        "pil_20261102_a\n",
        "",
        "x&y=1",
        "pil_٢٠٢٦١١٠٢_x",
        "pil_20261102_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "pil_20261102_a_b",
    ],
)
def test_the_panel_link_is_only_emitted_for_a_valid_pilot_id(bad_id: str) -> None:
    text = client(api_with(pilot_item(bad_id, niche_label="roto"))).get("/pilotos").text
    card = cards_of(text)["roto"]
    assert "/pilotos/" not in card and "Abrir" not in card and "<a " not in card
    assert "/pilotos/" not in text.replace('href="/pilotos"', "")


def _contact_line(text: str) -> str:
    found = re.search(r'<p class="caption pilot__contact">([^<]*)</p>', text)
    assert found, text
    return found.group(1)


@pytest.mark.parametrize(
    ("moment", "line"),
    [
        ("2026-11-03T06:00:00Z", "Tu Mac: último contacto hace 6 h"),
        ("2026-11-03T06:00:00", "Tu Mac: último contacto hace 6 h"),  # naive means UTC
        ("2026-11-03T01:00:00-05:00", "Tu Mac: último contacto hace 6 h"),
        ("2026-12-01T00:00:00Z", "Tu Mac: último contacto hace menos de 1 min"),  # future
        (None, "Tu Mac: sin contacto todavía"),
        ("garbage", "Tu Mac: sin contacto todavía"),
        (12345, "Tu Mac: sin contacto todavía"),
    ],
)
def test_the_last_contact_line_is_spanish_and_tz_safe(moment: object, line: str) -> None:
    text = (
        client(api_with(pilot(1, status="en_ejecucion", channel_last_contact_at=moment)))
        .get("/pilotos")
        .text
    )
    assert _contact_line(text) == line


def test_the_contact_line_is_computed_over_all_active_pilots_even_when_filtered() -> None:
    api = api_with(
        pilot(1, status="en_ejecucion", channel_last_contact_at="2026-11-03T06:00:00Z"),
        pilot(2, status="cerrado", channel_last_contact_at="2026-11-03T11:30:00Z"),
    )
    text = client(api).get("/pilotos", params={"filtro": "cerrados"}).text
    assert _contact_line(text) == "Tu Mac: último contacto hace 6 h"


def test_hostile_text_in_channel_check_labels_and_niche_is_escaped() -> None:
    hostile = pilot_item(
        "pil_20261102_p1",
        niche_label=HOSTILE,
        target_channel=HOSTILE,
        channel={
            "reported_at": "x",
            "channel_status": "active",
            "note": HOSTILE,
            "checks": [
                {"id": "a", "label": HOSTILE, "ok": False, "detail": HOSTILE, "expires_at": None}
            ],
        },
    )
    text = client(api_with(hostile)).get("/pilotos").text
    assert "<script>alert(1)" not in text
    card = cards_of(text)[HOSTILE]
    assert html.escape(HOSTILE) in card.split('<li class="blocker')[1]
    assert card.count("&lt;script&gt;") == 4  # niche, channel, label and detail; the note is unused
    assert card.count("<a ") == 1 and "<script" not in card  # only the Abrir button
    assert "evil.test" not in card.replace(html.escape("[x](https://evil.test)"), "")


def test_a_list_of_exactly_100_pilots_shows_the_truncation_warning() -> None:
    full = [pilot(n) for n in range(100)]
    text = client(api_with(*full)).get("/pilotos").text
    assert f'<div class="note note--amber">{TRUNCATION}</div>' in text
    assert pill("todos", "Todos", 100, True) in text
    below = client(api_with(*full[:99])).get("/pilotos").text
    assert TRUNCATION not in below and pill("todos", "Todos", 99, True) in below


def test_the_counts_cover_the_full_list_even_when_the_filter_hides_most_cards() -> None:
    items = [pilot(n, status="cerrado") for n in range(99)] + [pilot(99)]
    text = client(api_with(*items)).get("/pilotos", params={"filtro": "activos"}).text
    assert list(cards_of(text)) == ["nicho 99"]
    assert (
        pill("cerrados", "Cerrados", 99, False) in text
        and pill("activos", "Activos", 1, True) in text
    )


def test_an_empty_list_has_its_own_message() -> None:
    text = client(api_with()).get("/pilotos").text
    assert f'<p class="lead">{EMPTY}</p>' in text
    assert cards_of(text) == {}
    assert pill("todos", "Todos", 0, True) in text
    assert "Tu Mac" not in text


def test_a_filter_with_no_matches_says_so_instead_of_the_empty_message() -> None:
    text = client(api_with(pilot(1))).get("/pilotos", params={"filtro": "cerrados"}).text
    assert '<p class="lead">Ningún piloto coincide con este filtro.</p>' in text
    assert EMPTY not in text


def _down() -> Api:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    return Api({PILOTS: boom, STATUS: (200, {"radar_paused": False})})


def test_an_unavailable_api_gives_a_clear_503_without_a_second_status_call() -> None:
    api = _down()
    web = client(api)
    before = api.count(*STATUS)
    response = web.get("/pilotos")
    assert response.status_code == 503 and "API no disponible" in response.text
    assert '<div class="note note--rose" role="alert">' in response.text
    assert api.count(*STATUS) == before
    assert response.headers["vary"] == "HX-Request, HX-History-Restore-Request"
    assert (
        '<label class="pill"><input type="radio" name="filtro" value="todos" checked>Todos</label>'
        in (response.text)
    )


def test_an_unavailable_api_answers_an_htmx_request_with_a_200_error_fragment() -> None:
    api = _down()
    web = client(api)
    before = api.count(*STATUS)
    response = web.get("/pilotos", headers={"hx-request": "true"})
    assert api.count(*STATUS) == before  # no second status call after the failed list
    assert response.status_code == 200
    assert '<div class="note note--rose" role="alert">' in response.text
    assert "<html" not in response.text


def test_an_htmx_request_gets_the_fragment_with_vary_and_history_restore_the_full_page() -> None:
    web = client(api_with(pilot(1)))
    fragment = web.get("/pilotos", headers={"hx-request": "true"})
    assert fragment.status_code == 200
    assert list(cards_of(fragment.text)) == ["nicho 1"]
    assert "<html" not in fragment.text and "<h1" not in fragment.text
    assert 'name="filtro"' not in fragment.text
    assert fragment.headers["vary"] == "HX-Request, HX-History-Restore-Request"
    page = web.get("/pilotos")
    assert "<html" in page.text and page.headers["vary"] == fragment.headers["vary"]
    restored = web.get(
        "/pilotos", headers={"hx-request": "true", "hx-history-restore-request": "true"}
    )
    assert "<html" in restored.text and '<h1 class="h1">Pilotos</h1>' in restored.text
    assert restored.headers["vary"] == fragment.headers["vary"]


def test_the_filter_form_swaps_the_fragment_and_keeps_the_url() -> None:
    text = client(api_with(pilot(1))).get("/pilotos").text
    form = re.search(r'<form class="filters".*?</form>', text, re.S)
    assert form
    for needle in (
        'action="/pilotos"',
        'hx-get="/pilotos"',
        'hx-trigger="change"',
        'hx-target="#contenido"',
        'hx-push-url="true"',
    ):
        assert needle in form.group(0)
    assert '<div id="contenido" class="stack">' in text


@pytest.mark.parametrize(
    "body",
    [
        {"items": None},
        {"items": "x"},
        {"items": {"a": 1}},
        {},
    ],
)
def test_malformed_payloads_give_a_503_not_a_500(body: object) -> None:
    response = client(api_with(body=body)).get("/pilotos")
    assert response.status_code == 503
    assert "formato inesperado" in response.text


@pytest.mark.parametrize("body", [[], "boom"])
def test_a_non_object_payload_is_an_api_error_not_a_500(body: object) -> None:
    response = client(api_with(body=body)).get("/pilotos")
    assert response.status_code == 503
    assert '<div class="note note--rose" role="alert">' in response.text


def test_malformed_items_do_not_500() -> None:
    items: list[object] = [
        {"pilot_id": "pil_20261102_ok", "niche_label": "sin totals", "status": "en_ejecucion"},
        pilot(2, status="marciano"),
        pilot(3, status=None, totals=None, channel=[], needs_decision="yes"),
        pilot(4, totals={"by_stage": []}, channel={"checks": "x"}),
        None,
        7,
        "x",
    ]
    response = client(api_with(*items)).get("/pilotos")
    assert response.status_code == 200
    cards = cards_of(response.text)
    assert {"sin totals", "nicho 2", "nicho 3", "nicho 4"} <= set(cards)
    assert '<span class="chip chip--neutral">marciano</span>' in cards["nicho 2"]
    assert "Estado desconocido" in cards["nicho 3"]
    assert pill("todos", "Todos", 4, True) in response.text  # only the four dict items count


def test_unknown_statuses_count_as_active() -> None:
    text = client(api_with(pilot(1, status="marciano"))).get("/pilotos").text
    assert pill("activos", "Activos", 1, False) in text


def test_the_pilots_tab_is_active_and_a_real_link() -> None:
    text = client(api_with(pilot(1))).get("/pilotos").text
    assert (
        '<a class="tab tab--on" href="/pilotos" aria-current="page"><span class="tab__icon" '
        'aria-hidden="true">◫</span><span class="tab__label">Pilotos</span></a>' in text
    )
    assert (
        'tab--soon" aria-disabled="true" title="Próximamente"><span class="tab__icon" '
        'aria-hidden="true">◫' not in text
    )
    assert text.count("tab--on") == 1


def test_the_pilots_tab_is_a_link_but_not_active_on_other_screens() -> None:
    web = client(api_with(pilot(1)))
    text = web.get("/").text
    assert (
        '<a class="tab" href="/pilotos"><span class="tab__icon" aria-hidden="true">◫</span>'
        '<span class="tab__label">Pilotos</span></a>' in text
    )
