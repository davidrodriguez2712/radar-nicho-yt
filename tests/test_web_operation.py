# tests/test_web_operation.py
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web import operation as op
from nicheradar.web.app import create_app
from nicheradar.web.format import ago
from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    make_client,
    schedule,
    scrape_run,
    settings,
    subniche_item,
)

SCHEDULE = ("GET", "/api/v1/market/schedule")
RUNS = ("GET", "/api/v1/market/runs")
SUBNICHES = ("GET", "/api/v1/subniches")
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def api_with() -> Api:
    routes: dict[tuple[str, str], Route] = {
        SCHEDULE: (200, schedule()),
        RUNS: (200, {"items": [scrape_run()]}),
        SUBNICHES: (200, {"items": [subniche_item("a", status="active")]}),
    }
    return Api(routes)


# ---- format.ago
@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-11-04T11:59:30+00:00", "hace un momento"),
        ("2026-11-04T11:55:00+00:00", "hace 5 min"),
        ("2026-11-04T06:00:00+00:00", "hace 6 h"),
        ("2026-11-01T12:00:00+00:00", "hace 3 d"),
        ("2026-11-04T13:00:00+00:00", "ahora"),
        ("2026-11-04T11:55:00", "hace 5 min"),
        ("basura", "—"),
        (None, "—"),
        (7, "—"),
    ],
)
def test_ago(value: object, expected: str) -> None:
    assert ago(value, NOW) == expected


# ---- vista pura
def test_run_status_labels_and_unknown_values() -> None:
    card = op.runs_card(
        [scrape_run("partial"), scrape_run("raro", stage="inventada")], NOW, "America/Lima", 20
    )
    labels = [r["status_label"] for r in card["rows"]]
    assert labels == ["parcial", "desconocido"]
    assert "etapa: —" in card["rows"][1]["detail"]


def test_run_detail_has_stage_duration_and_error_code() -> None:
    row = op.runs_card([scrape_run("failed", stage="list", error_code="timeout")], NOW, "UTC", 20)[
        "rows"
    ][0]
    assert (
        row["detail"] == "etapa: listados · 4 min · error: timeout"
    )  # 3 min 10 s se redondea hacia arriba


def test_duration_is_omitted_when_a_date_is_missing_or_garbage() -> None:
    row = op.runs_card([scrape_run(finished_at=None)], NOW, "UTC", 20)["rows"][0]
    assert "min" not in row["detail"].replace("etapa", "")


def test_hostile_error_code_is_trimmed_and_kept_as_text() -> None:
    row = op.runs_card([scrape_run("failed", error_code="x" * 500)], NOW, "UTC", 20)["rows"][0]
    assert len(row["detail"]) < 140


def test_scraper_card_active_and_paused() -> None:
    active = op.scraper_card(schedule(), [], NOW, "UTC")
    assert (
        active["state_text"],
        active["mode_text"],
        active["frequency_text"],
        active["action"],
    ) == ("Activo", "Real", "Cada 24 h", "pausar")
    paused = op.scraper_card(schedule(paused=True), [], NOW, "UTC")
    assert (paused["state_text"], paused["action"]) == ("Pausado", "reanudar")
    assert "pausado" in paused["next_text"]


@pytest.mark.parametrize(
    "seconds,text",
    [
        (86400, "Cada 24 h"),
        (7200, "Cada 2 h"),
        (1800, "Cada 30 min"),
        (0, "—"),
        ("x", "—"),
        (-5, "—"),
    ],
)
def test_frequency_text(seconds: object, text: str) -> None:
    assert (
        op.scraper_card(schedule(interval_seconds=seconds), [], NOW, "UTC")["frequency_text"]
        == text
    )


def test_warnings_follow_the_fixed_order_and_keys() -> None:
    sc = op.scraper_card(
        schedule(paused=True, mode="live", live_enabled=False), [scrape_run("partial")], NOW, "UTC"
    )
    assert sc["warnings"] == [
        "El scraper de mercado está pausado: no trae anuncios nuevos hasta que lo reanudes.",
        "La última ejecución del scraper salió parcial.",
        "En modo real, el scraper no se activa hasta habilitar el scraper en vivo en el servidor.",
    ]


def test_no_warnings_when_everything_is_fine() -> None:
    assert op.scraper_card(schedule(), [scrape_run()], NOW, "UTC")["warnings"] == []


def test_subniche_counters_and_last_measurement() -> None:
    items = [
        subniche_item("a", status="active"),
        subniche_item("b", status="active", measurement=None),
        subniche_item("c", status="proposed", measurement=None),
        subniche_item("d", status="paused"),
        subniche_item("e", status="archived"),
        "no es un dict",
        None,
    ]
    card = op.subniches_card(items, NOW)
    assert (card["active"], card["proposed"], card["paused"], card["unmeasured"]) == (2, 1, 1, 1)
    assert (
        card["last_measured_text"].startswith("hace ")
        or card["last_measured_text"] == "sin mediciones"
    )


def test_subniche_card_degrades_on_a_wrong_shape() -> None:
    assert op.subniches_card({"x": 1}, NOW)["ok"] is False
    assert op.subniches_card(None, NOW)["ok"] is False


def test_runs_truncation_warning_at_the_limit() -> None:
    card = op.runs_card([scrape_run() for _ in range(20)], NOW, "UTC", 20)
    assert card["truncated"] is True


# ---- ruta
def test_the_screen_requires_a_session() -> None:
    r = TestClient(create_app(settings()), follow_redirects=False).get("/operacion")
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_the_screen_renders_the_three_cards() -> None:
    page = make_client(api_with()).get("/operacion")
    assert page.status_code == 200
    for text in (
        "Operación",
        "Scraper de mercado",
        "Últimas ejecuciones del scraper",
        "Subnichos",
        "Pausar scraper",
        "Ver todas las ejecuciones",
        "Ver subnichos",
    ):
        assert text in page.text
    assert "Radar" not in page.text.replace("NicheRadar", "")


def test_runs_are_requested_with_limit_20_and_subniches_with_inactive() -> None:
    api = api_with()
    make_client(api).get("/operacion")
    runs_call = next(c for c in api.calls if c.url.path.endswith("/market/runs"))
    assert runs_call.url.params["limit"] == "20"
    sub_call = next(c for c in api.calls if c.url.path.endswith("/subniches"))
    assert sub_call.url.params["include_inactive"] == "true"


@pytest.mark.parametrize("down", [SCHEDULE, RUNS, SUBNICHES])
def test_one_failing_source_degrades_only_its_card(down: tuple[str, str]) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    routes: dict[tuple[str, str], Route] = {
        SCHEDULE: (200, schedule()),
        RUNS: (200, {"items": [scrape_run()]}),
        SUBNICHES: (200, {"items": [subniche_item("a")]}),
    }
    routes[down] = boom
    page = make_client(Api(routes)).get("/operacion")
    assert page.status_code == 200
    assert "Traceback" not in page.text
    assert "no disponible" in page.text.lower()
    # las otras dos tarjetas siguen presentes
    present = sum(
        t in page.text
        for t in ("Scraper de mercado", "Últimas ejecuciones del scraper", "Subnichos")
    )
    assert present >= 2


def test_hostile_text_in_runs_is_escaped() -> None:
    api = api_with()
    api.routes[RUNS] = (200, {"items": [scrape_run("failed", error_code=HOSTILE)]})
    page = make_client(api).get("/operacion")
    assert "<script>" not in page.text and "&lt;script&gt;" in page.text
