from typing import Any

import httpx

from tests.web_helpers import Api, csrf_of, make_client, schedule, scrape_run

SCHEDULE = ("GET", "/api/v1/market/schedule")
PUT = ("PUT", "/api/v1/market/schedule")
RUNS = ("GET", "/api/v1/market/runs")


def api(paused: bool, put: object = None, **sched: object) -> Api:
    routes: dict[tuple[str, str], Any] = {
        SCHEDULE: (200, schedule(paused=paused, **sched)),
        PUT: put or (200, schedule(paused=not paused)),
        RUNS: (200, {"items": [scrape_run()]}),
    }
    return Api(routes)


def writes(a: Api) -> list[httpx.Request]:
    return [c for c in a.calls if c.method == "PUT"]


def test_confirmation_page_for_resume_states_the_consequence() -> None:
    page = make_client(api(True)).get("/operacion/scraper/reanudar")
    assert page.status_code == 200
    for t in (
        "Reanudar el scraper",
        "volverá a recorrer los anuncios",
        "Confirmar y reanudar",
        "Volver sin cambios",
    ):
        assert t in page.text


def test_confirmation_page_for_pause() -> None:
    page = make_client(api(False)).get("/operacion/scraper/pausar")
    assert "Confirmar y pausar" in page.text and "No borra nada" in page.text


def test_unknown_action_is_a_404_and_calls_nothing() -> None:
    a = api(True)
    assert make_client(a).get("/operacion/scraper/borrar").status_code == 404
    assert writes(a) == []


def test_resume_in_live_mode_without_live_enabled_is_blocked_without_a_form() -> None:
    page = make_client(api(True, mode="live", live_enabled=False)).get(
        "/operacion/scraper/reanudar"
    )
    assert page.status_code == 409
    assert "scraper en vivo debe estar habilitado" in page.text
    assert "Confirmar y reanudar" not in page.text


def test_post_without_csrf_is_rejected_and_writes_nothing() -> None:
    a = api(True)
    r = make_client(a).post("/operacion/scraper/reanudar", data={})
    assert r.status_code in (400, 403) and writes(a) == []


def test_post_resumes_and_redirects_with_a_notice_key() -> None:
    a = api(True)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 303 and r.headers["location"] == "/operacion?aviso=reanudado"
    assert len(writes(a)) == 1 and writes(a)[0].content == b'{"paused":false}'


def test_a_second_post_when_already_active_writes_nothing() -> None:
    a = api(False)  # ya activo
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 303 and r.headers["location"] == "/operacion?aviso=sin-cambio"
    assert writes(a) == []


def test_post_pauses() -> None:
    a = api(False)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/pausar").text)
    r = c.post("/operacion/scraper/pausar", data={"csrf": token})
    assert r.headers["location"] == "/operacion?aviso=pausado" and len(writes(a)) == 1


def test_a_409_from_the_api_shows_a_fixed_text_and_does_not_retry() -> None:
    gate = (409, {"detail": "texto del servidor que no se debe mostrar"})
    a = api(True, put=gate)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 409
    assert "texto del servidor" not in r.text and "scraper en vivo debe estar habilitado" in r.text
    assert len(writes(a)) == 1


def test_api_down_on_post_shows_a_message_not_a_trace() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    a = api(True, put=boom)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code in (503, 200) and "Traceback" not in r.text


def test_runs_screen_lists_up_to_20_with_labels() -> None:
    items = [
        scrape_run("partial"),
        scrape_run("failed", error_code="timeout"),
        scrape_run("blocked"),
    ]
    a = Api({RUNS: (200, {"items": items})})
    page = make_client(a).get("/operacion/ejecuciones")
    assert page.status_code == 200
    for t in ("Ejecuciones del scraper", "parcial", "falló", "bloqueada", "Las últimas 20"):
        assert t in page.text
    call = next(c for c in a.calls if c.url.path.endswith("/market/runs"))
    assert call.url.params["limit"] == "20"


def test_runs_screen_with_the_api_down_is_a_503_with_a_spanish_message() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    page = make_client(Api({RUNS: boom})).get("/operacion/ejecuciones")
    assert page.status_code == 503 and "Traceback" not in page.text
