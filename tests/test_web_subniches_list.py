# tests/test_web_subniches_list.py
import re

from tests.web_helpers import HOSTILE, Api, make_client, measurement, research, subniche_item

LIST = ("GET", "/api/v1/subniches")


def api_with(*items: dict[str, object]) -> Api:
    return Api(
        {
            LIST: (200, {"items": list(items)}),
            ("GET", "/api/v1/status"): (200, {"radar_paused": True}),
        }
    )


def test_the_list_requires_a_session() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    response = TestClient(create_app(settings()), follow_redirects=False).get("/subnichos")
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_the_list_renders_one_card_per_subniche_with_the_figma_content() -> None:
    api = api_with(
        subniche_item("prehistoric_creatures", research=research("listo")),
        subniche_item(
            "forgotten_history",
            label="Forgotten History Events",
            family="history",
            measurement=measurement(
                income_low="1629.23",
                income_high="3723.96",
                traction_channels=11,
                stable_channels=10,
                large_channels=9,
            ),
        ),
    )
    page = make_client(api).get("/subnichos")
    assert page.status_code == 200
    text = page.text
    assert "Subnichos" in text and "Ingreso típico por canal al mes" in text
    assert "US$ 673 – 1.682" in text and "US$ 1.629 – 3.724" in text
    assert "Ciencia y naturaleza" in text and "Historia" in text
    assert "Dossier listo" in text and "Sin investigar" in text
    assert "<dt>Despegaron</dt><dd>19</dd>" in text and "<dt>Constantes</dt><dd>18</dd>" in text
    assert "<dt>Grandes</dt><dd>4</dd>" in text and "<dt>Despegaron</dt><dd>11</dd>" in text
    assert 'chip chip--rose">Finalista<' in text
    assert text.count('class="card"') == 2
    listing = [c for c in api.calls if c.url.path == "/api/v1/subniches"]
    assert [c.url.params["include_inactive"] for c in listing] == ["false"]


def test_the_buttons_follow_the_research_state() -> None:
    api = api_with(
        subniche_item("a_new", research=None),
        subniche_item("a_running", research=research("en_curso")),
        subniche_item("a_done", research=research("listo")),
        subniche_item("a_paused", status="paused", research=None),
        subniche_item("a_unmeasured", measurement=None, research=None),
    )
    text = make_client(api).get("/subnichos").text
    assert text.count("Investigar</a>") == 1
    assert "Ver estado" in text and text.count("Ver subnicho") == 3
    assert 'href="/subnichos/a_new"' in text


def test_an_unmeasured_subniche_says_so_instead_of_showing_numbers() -> None:
    text = make_client(api_with(subniche_item("x_one", measurement=None))).get("/subnichos").text
    assert "Todavía sin medición" in text and "Ingreso típico" not in text


def test_the_count_line_and_the_segmented_selector() -> None:
    api = api_with(subniche_item("a_one"), subniche_item("b_two", finalist=False))
    text = make_client(api).get("/subnichos").text
    assert "1</strong> finalistas de 2" in text
    assert "Nichos" in text
    assert re.search(r'<a[^>]*aria-current="page"[^>]*>Subnichos', text)


def test_filters_narrow_the_cards_in_the_web_layer() -> None:
    api = api_with(
        subniche_item("a_one", label="Alpha", family="history", finalist=True),
        subniche_item("b_two", label="Beta", family="scifi", finalist=False),
        subniche_item(
            "c_three", label="Gamma", family="history", finalist=False, status="proposed"
        ),
    )
    web = make_client(api)
    by_family = web.get("/subnichos", params={"familia": "history"}).text
    assert "Alpha" in by_family and "Gamma" in by_family and "Beta" not in by_family
    only = web.get("/subnichos", params={"finalistas": "1"}).text
    assert "Alpha" in only and "Beta" not in only and "Gamma" not in only
    state = web.get("/subnichos", params={"estado": "proposed"}).text
    assert "Gamma" in state and "Alpha" not in state


def test_the_inactive_toggle_asks_the_api_for_inactive_hypotheses() -> None:
    api = api_with(subniche_item("a_one"))
    make_client(api).get("/subnichos", params={"inactivos": "1"})
    listing = [c for c in api.calls if c.url.path == "/api/v1/subniches"]
    assert [c.url.params["include_inactive"] for c in listing] == ["true"]


def test_junk_filter_values_are_ignored_without_an_error() -> None:
    api = api_with(subniche_item("a_one", label="Alpha"))
    web = make_client(api)
    for params in (
        {"familia": "<script>alert(1)</script>"},
        {"estado": "zzz"},
        {"finalistas": "2"},
        {"inactivos": "yes", "familia": "x" * 500},
    ):
        response = web.get("/subnichos", params=params)
        assert response.status_code == 200 and "Alpha" in response.text, params
        assert "<script>alert(1)</script>" not in response.text


def test_an_htmx_request_gets_only_the_list_fragment() -> None:
    api = api_with(subniche_item("a_one", label="Alpha"))
    response = make_client(api).get("/subnichos", headers={"hx-request": "true"})
    assert response.status_code == 200 and "Alpha" in response.text
    assert "<html" not in response.text and 'class="topbar"' not in response.text


def test_hostile_api_text_is_escaped_everywhere_in_the_list() -> None:
    api = api_with(
        subniche_item("hostile_one", label=HOSTILE, family=HOSTILE, language="en"),
    )
    text = make_client(api).get("/subnichos").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert re.search(r'<option value="[^"]*&lt;script&gt;', text)


def test_an_unavailable_api_shows_a_clear_message_with_503() -> None:
    import httpx

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({LIST: boom, ("GET", "/api/v1/status"): (200, {"radar_paused": False})})
    response = make_client(api).get("/subnichos")
    assert response.status_code == 503 and "API no disponible" in response.text
    assert "Traceback" not in response.text


def test_an_empty_list_has_its_own_message() -> None:
    text = make_client(api_with()).get("/subnichos").text
    assert "Todavía no hay subnichos" in text


def test_filter_pills_do_not_hardcode_the_on_state() -> None:
    api = api_with(subniche_item("a_one"))
    text = make_client(api).get("/subnichos", params={"finalistas": "1", "inactivos": "1"}).text
    assert "pill--on" not in text and text.count(" checked") == 2


def test_an_explicit_paused_or_archived_state_asks_for_inactive_hypotheses() -> None:
    for estado in ("paused", "archived"):
        api = api_with(subniche_item("a_one", status=estado))
        make_client(api).get("/subnichos", params={"estado": estado})
        listing = [c for c in api.calls if c.url.path == "/api/v1/subniches"]
        assert [c.url.params["include_inactive"] for c in listing] == ["true"], estado
    api = api_with(subniche_item("a_one"))
    make_client(api).get("/subnichos", params={"estado": "active"})
    assert [
        c.url.params["include_inactive"] for c in api.calls if c.url.path == "/api/v1/subniches"
    ] == ["false"]


def test_history_restore_gets_the_full_page_and_responses_vary() -> None:
    web = make_client(api_with(subniche_item("a_one", label="Alpha")))
    restore = web.get(
        "/subnichos", headers={"hx-request": "true", "hx-history-restore-request": "true"}
    )
    assert "<html" in restore.text and 'class="topbar"' in restore.text
    assert restore.headers["vary"] == "HX-Request, HX-History-Restore-Request"
    fragment = web.get("/subnichos", headers={"hx-request": "true"})
    assert "<html" not in fragment.text
    assert fragment.headers["vary"] == "HX-Request, HX-History-Restore-Request"


def test_an_htmx_request_with_the_api_down_gets_a_swappable_200_fragment() -> None:
    import httpx

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({LIST: boom, ("GET", "/api/v1/status"): (200, {"radar_paused": False})})
    response = make_client(api).get("/subnichos", headers={"hx-request": "true"})
    assert response.status_code == 200 and "API no disponible" in response.text
    assert "<html" not in response.text
    assert response.headers["vary"] == "HX-Request, HX-History-Restore-Request"


def test_a_failing_page_does_not_add_a_status_call_and_status_uses_a_short_timeout() -> None:
    import httpx

    seen: list[str] = []

    def down(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        raise httpx.ConnectError("down")

    api = Api({LIST: down})
    web = make_client(api)
    response = web.get("/subnichos")
    assert response.status_code == 503
    assert api.count("GET", "/api/v1/status") == 0

    from nicheradar.web.client import STATUS_TIMEOUT_SECONDS, TIMEOUT_SECONDS

    assert STATUS_TIMEOUT_SECONDS == 3 and TIMEOUT_SECONDS == 15
    timeouts: list[object] = []

    def record(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={"radar_paused": False})

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    app = create_app(settings(), transport=httpx.MockTransport(record))
    app.state.api.request("GET", "/status", timeout=STATUS_TIMEOUT_SECONDS)
    assert timeouts[0]["read"] == 3  # type: ignore[index]
    app.state.api.request("GET", "/status")
    assert timeouts[1]["read"] == 15  # type: ignore[index]


def test_the_status_call_made_by_a_page_uses_the_short_timeout() -> None:
    import httpx

    timeouts: list[float] = []

    def status(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"radar_paused": False})

    api = Api({LIST: (200, {"items": []}), ("GET", "/api/v1/status"): status})
    assert make_client(api).get("/subnichos").status_code == 200
    assert timeouts == [3]
