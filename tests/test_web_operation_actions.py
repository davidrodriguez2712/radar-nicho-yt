from typing import Any

import httpx
import pytest

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
    c = make_client(a)
    assert c.get("/operacion/scraper/borrar").status_code == 404
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    a.calls.clear()
    assert c.get("/operacion/scraper/borrar").status_code == 404
    assert c.post("/operacion/scraper/borrar", data={"csrf": token}).status_code == 404
    assert a.calls == []


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


@pytest.mark.parametrize("paused", ["MISSING", "false", "true", 1, 0, None])
def test_a_schedule_with_a_malformed_paused_is_a_503_and_never_writes(paused: object) -> None:
    sched = schedule()
    if paused == "MISSING":
        del sched["paused"]
    else:
        sched["paused"] = paused
    routes: dict[tuple[str, str], Any] = {
        SCHEDULE: (200, sched),
        PUT: (200, schedule()),
        RUNS: (200, {"items": []}),
    }
    a = Api(routes)
    c = make_client(a)
    for action in ("reanudar", "pausar"):
        assert c.get(f"/operacion/scraper/{action}").status_code == 503
        token = csrf_of(c.get("/operacion").text)
        r = c.post(f"/operacion/scraper/{action}", data={"csrf": token}, follow_redirects=False)
        assert r.status_code == 503 and "location" not in r.headers
    assert writes(a) == []


def test_a_409_on_pause_shows_the_generic_failure_not_the_live_text() -> None:
    a = api(False, put=(409, {"detail": "texto del servidor"}))
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/pausar").text)
    r = c.post("/operacion/scraper/pausar", data={"csrf": token})
    assert "scraper en vivo debe estar habilitado" not in r.text
    assert "texto del servidor" not in r.text and "No se pudo aplicar el cambio" in r.text


def test_the_live_block_text_appears_once_after_a_resume_409() -> None:
    a = api(True, put=(409, {"detail": "x"}))
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.text.count("scraper en vivo debe estar habilitado") == 1


def test_runs_screen_empty_state() -> None:
    page = make_client(Api({RUNS: (200, {"items": []})})).get("/operacion/ejecuciones")
    assert page.status_code == 200 and "Todavía no hay ejecuciones" in page.text


def test_runs_screen_escapes_hostile_text() -> None:
    items = [scrape_run("failed", error_code="<script>alert(1)</script>")]
    page = make_client(Api({RUNS: (200, {"items": items})})).get("/operacion/ejecuciones")
    assert "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text


def test_a_shape_failure_on_post_is_a_503_without_a_write() -> None:
    a = Api({SCHEDULE: (200, ["no es un objeto"]), PUT: (200, schedule())})
    c = make_client(a)
    token = csrf_of(c.get("/operacion").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 503 and "Traceback" not in r.text and writes(a) == []
