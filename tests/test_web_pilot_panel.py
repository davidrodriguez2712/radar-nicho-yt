# tests/test_web_pilot_panel.py
import html
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from nicheradar.web.pilot_panel import TABS, panel_view, parse_tab
from tests.web_helpers import HOSTILE, Api, make_client, pilot_detail, pilot_video, settings

PID = "pil_20261102_historia"
DETAIL = ("GET", f"/api/v1/pilots/{PID}")
VIDEOS = ("GET", f"/api/v1/pilots/{PID}/videos")
STATUS = ("GET", "/api/v1/status")
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
ESCAPED = html.escape(HOSTILE)
NO_REPORT = "El canal todavía no informó pasos de preparación."


def api_with(detail: object | None = None, videos: object | None = None) -> Api:
    return Api(
        {
            DETAIL: (200, detail if detail is not None else pilot_detail()),
            VIDEOS: (200, {"items": videos if videos is not None else []}),
            STATUS: (200, {"radar_paused": False}),
        }
    )


def client(api: Api) -> TestClient:
    return make_client(api, clock=lambda: NOW.timestamp())


def page(api: Api, tab: str | None = None, extra: str = "") -> str:
    query = f"?pestana={tab}" if tab else ""
    if extra:
        query += ("&" if query else "?") + extra
    response = client(api).get(f"/pilotos/{PID}{query}")
    assert response.status_code == 200, response.text
    return str(response.text)


def block(text: str, element_id: str) -> str:
    """Inner markup of the element with that id; ids sit on elements that never nest their tag."""
    found = re.search(rf"<(\w+)[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>(.*?)</\1>", text, re.S)
    assert found, f"no #{element_id} in the page"
    return str(found.group(2))


def flat(markup: str) -> str:
    """Visible text of a fragment, tags dropped and whitespace collapsed, entities decoded."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def visible(markup: str) -> str:
    """Text a sighted user reads: the visually hidden spans are dropped."""
    return flat(re.sub(r'<span class="sr-only">.*?</span>', "", markup, flags=re.S))


def items(markup: str) -> list[str]:
    return re.findall(r"<li\b[^>]*>(.*?)</li>", markup, re.S)


def detail_with(**over: Any) -> dict[str, object]:
    return pilot_detail(**over)


def totals(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "videos": 3,
        "published": 2,
        "measured": 0,
        "by_stage": {"awaiting_human": 2},
        "spent_usd": 12.5,
        "equivalent_usd": 30,
        "machine_minutes": 130,
        "machine_minutes_complete": True,
    }
    return base | over


def test_a_valid_panel_shows_title_status_line_and_the_five_tabs() -> None:
    text = page(api_with(detail_with(status="en_ejecucion")))
    assert "<h1" in text and "Piloto · historia militar explicada</h1>" in text
    head = block(text, "cabecera")
    for chip in ("En ejecución", "Largo", "Inglés"):
        assert f">{chip}</span>" in head
    assert '<span class="pilot__channel">canal-historias</span>' in head
    assert "youtube.com" not in text
    tabs = block(text, "pestanas")
    links = re.findall(r"<a\b([^>]*)>([^<]*)</a>", tabs)
    assert [label for _, label in links] == [
        "Resumen",
        "Preparación",
        "Videos",
        "Reglas",
        "Historial",
    ]
    for (attrs, _), key in zip(links, TABS, strict=True):
        assert f'href="/pilotos/{PID}?pestana={key}"' in attrs
    assert [a for a, _ in links if "aria-current" in a] == [links[0][0]]
    assert 'aria-current="page"' in links[0][0]
    line = block(text, "linea-estados")
    assert re.findall(
        r'<li class="step step--current" aria-current="step">(.*?)</li>', line, re.S
    ) == ['<span class="sr-only">actual: </span>En ejecución']
    assert line.count('<span class="sr-only">hecho: </span>') == 3


@pytest.mark.parametrize(
    ("status", "current"),
    [
        ("autorizado", "Autorizado"),
        ("entregado", "Preparando"),
        ("en_ejecucion", "En ejecución"),
        ("decision_pendiente", "Decisión pendiente"),
        ("cerrado", "Cerrado"),
        ("cancelado", None),
    ],
)
def test_the_state_line_marks_exactly_the_current_state_for_each_status(
    status: str, current: str | None
) -> None:
    text = page(api_with(detail_with(status=status)))
    steps = items(block(text, "linea-estados"))
    labels = ["Autorizado", "Entregado", "Preparando", "En ejecución", "Decisión pendiente"]
    labels.append("Cerrado")
    assert [visible(s) for s in steps] == labels
    marked = re.findall(
        r'<li class="step step--current"[^>]*aria-current="step"[^>]*>(.*?)</li>',
        block(text, "linea-estados"),
        re.S,
    )
    assert [visible(m) for m in marked] == ([current] if current else [])
    assert len(re.findall("step--current", block(text, "linea-estados"))) == len(marked)
    done = re.findall(
        r'<li class="step step--done"[^>]*>(.*?)</li>', block(text, "linea-estados"), re.S
    )
    if current:
        assert [visible(d) for d in done] == labels[: labels.index(current)]
    else:
        assert done == []


def test_summary_shows_blockers_next_action_dates_proposal_rules_and_costs() -> None:
    detail = detail_with(
        status="en_ejecucion",
        first_report_at="2026-11-01T12:00:00Z",
        last_report_at="2026-11-03T09:00:00Z",
        totals=totals(),
        proposal={"action": "seguir", "reason": "hito cumplido (video 10)"},
        channel={
            "reported_at": "2026-11-03T11:00:00Z",
            "checks": [
                {"id": "a", "label": "Subir a YouTube", "ok": False, "detail": "falta permiso"}
            ],
        },
        evaluation={
            "rules": [
                {"id": "r1", "text": "Regla uno", "milestone": "video:10", "status": "cumple"},
                {"id": "r2", "text": "Regla dos", "milestone": "week:6", "status": "pendiente"},
            ],
            "milestones": [],
            "close_after": 2,
        },
    )
    text = page(api_with(detail))
    resumen = block(text, "tab-resumen")
    state = flat(block(text, "res-estado"))
    assert "Estado actual" in state and "Día 3" in state and "2 de 10 publicados" in state
    blockers = block(text, "res-bloqueos")
    assert "Bloqueos y avisos (1)" in flat(blockers)
    assert [flat(i) for i in items(blockers)] == ["Falta: Subir a YouTube. falta permiso El canal"]
    assert "Siguiente acción tuya" in flat(block(text, "res-siguiente"))
    assert "2 videos esperan tu veredicto en el canal" in flat(block(text, "res-siguiente"))
    dates = flat(block(text, "res-fechas"))
    assert "Fechas (tentativas)" in dates
    assert "Autorizado 1 nov" in dates and "Entregado 3 nov" in dates
    proposal = flat(block(text, "res-propuesta"))
    assert "Propuesta de NicheRadar" in proposal and "Seguir" in proposal
    assert "hito cumplido (video 10)" in proposal
    rules = flat(block(text, "res-reglas"))
    assert "Reglas de parada" in rules and "2 reglas" in rules and "1 cumple" in rules
    assert "Costos y tiempos" in flat(block(text, "res-costos"))
    assert resumen.count('id="res-') == 8


def test_summary_without_blockers_says_so_and_closed_pilots_have_none() -> None:
    quiet = {"checks": [check("A", True)]}
    text = page(api_with(detail_with(status="en_ejecucion", delivered_at=None, channel=quiet)))
    assert "Bloqueos y avisos (0)" in flat(block(text, "res-bloqueos"))
    assert items(block(text, "res-bloqueos")) == []
    assert "Sin bloqueos" in flat(block(text, "res-bloqueos"))
    assert 'id="res-siguiente"' in text  # always present, says nothing is waiting
    assert "Nada te espera por ahora" in flat(block(text, "res-siguiente"))


def test_costs_show_spent_against_the_package_budget_and_flag_incomplete_machine_minutes() -> None:
    detail = detail_with(
        status="en_ejecucion", last_report_at="2026-11-03T09:00:00Z", totals=totals()
    )
    costs = flat(block(page(api_with(detail)), "res-costos"))
    assert "Dinero gastado: US$ 12,50 de US$ 41" in costs
    assert "Equivalente de Claude: US$ 30 (no se suma)" in costs
    assert "Minutos de máquina: 2 h 10 min" in costs and "(incompleto)" not in costs
    assert "Último reporte: hace 3 h" in costs
    detail = detail_with(
        totals=totals(machine_minutes_complete=False, machine_minutes=45, spent_usd=0.32)
    )
    costs = flat(block(page(api_with(detail)), "res-costos"))
    assert "Minutos de máquina: 0 h 45 min (incompleto)" in costs
    assert "Dinero gastado: US$ 0,32 de US$ 41" in costs
    assert "Último reporte: todavía no hay" in costs
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    package["budget"] = {"currency": "USD", "low": 3}
    costs = flat(block(page(api_with(detail_with(package=package, totals=totals()))), "res-costos"))
    assert "Dinero gastado: US$ 12,50" in costs and " de US$" not in costs.split("Equivalente")[0]
    bad = totals(spent_usd="nan", machine_minutes=True, equivalent_usd=None)
    costs = flat(block(page(api_with(detail_with(totals=bad))), "res-costos"))
    assert "Dinero gastado: —" in costs and "Minutos de máquina: —" in costs
    assert "Equivalente de Claude: — (no se suma)" in costs
    for amount, shown in (
        (-1, "—"),
        (2e9, "—"),
        (250.4, "US$ 250"),
        (0, "US$ 0"),
        (0.96, "US$ 0,96"),
    ):
        view = panel_view(detail_with(totals=totals(spent_usd=amount)), None, NOW, "UTC", "resumen")
        assert view["summary"]["costs"]["spent"].startswith(shown), amount
    negative = totals(machine_minutes=-5)
    view = panel_view(detail_with(totals=negative), None, NOW, "UTC", "resumen")
    assert view["summary"]["costs"]["minutes"] == "—"
    # JSON cannot carry NaN or infinity, so the view model is checked directly.
    nan = detail_with(totals=totals(spent_usd=float("nan"), machine_minutes=float("inf")))
    summary = panel_view(nan, None, NOW, "UTC", "resumen")["summary"]["costs"]
    assert summary["spent"].startswith("—") and summary["minutes"] == "—"


def check(label: str, ok: bool, **over: object) -> dict[str, object]:
    base: dict[str, object] = {"id": label[:5], "label": label, "ok": ok, "detail": None}
    return base | over


def test_preparation_tab_lists_the_channel_checks_as_steps_with_status_and_detail() -> None:
    channel = {
        "reported_at": "2026-11-03T11:00:00Z",
        "note": "nota del canal",
        "checks": [
            check("Paso uno", True, expires_at="2026-11-10T12:00:00Z"),
            check("Paso dos", False, detail="falta algo"),
        ],
    }
    text = page(api_with(detail_with(status="entregado", channel=channel)), "preparacion")
    steps = block(text, "prep-pasos")
    rows = items(steps)
    assert [flat(r) for r in rows] == [
        "✓ hecho Paso uno caduca el 10 nov",
        "! pendiente Paso dos falta algo",
    ]
    assert "mark--ok" in rows[0] and "mark--todo" in rows[1]
    assert "aria-label" not in steps  # hidden text instead, which every reader announces
    assert '<span class="sr-only">hecho</span>' in rows[0]
    assert '<span class="sr-only">pendiente</span>' in rows[1]
    assert "nota del canal" in flat(block(text, "prep-pasos"))
    assert 'id="tab-resumen"' not in text and 'id="tab-preparacion"' in text
    tabs = block(text, "pestanas")
    assert re.search(r'<a[^>]*aria-current="page"[^>]*>Preparación</a>', tabs)


def test_preparation_counts_missing_steps_and_the_deadline_with_preparation_days() -> None:
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    package["preparation_days"] = 14
    channel = {"checks": [check("A", True), check("B", False), check("C", False)]}
    detail = detail_with(status="entregado", package=package, channel=channel)
    text = page(api_with(detail), "preparacion")
    assert "Plazo de preparación: vence el 17 nov (tentativa)" in flat(block(text, "prep-plazo"))
    assert "0 días desde la entrega. Faltan 2 de 3 pasos." in flat(block(text, "prep-cuenta"))
    # Without the field in the package the deadline is not invented.
    text = page(api_with(detail_with(status="entregado", channel=channel)), "preparacion")
    assert "vence el" not in flat(block(text, "prep-plazo"))
    assert "Plazo de preparación:" not in text
    assert "depende del paquete" in flat(block(text, "prep-plazo"))
    assert "Faltan 2 de 3 pasos." in flat(block(text, "prep-cuenta"))


def test_preparation_without_channel_report_says_the_channel_has_not_reported_yet() -> None:
    channels: list[object] = [None, {}, {"checks": []}, {"checks": "x"}, "texto", ["a"]]
    for channel in channels:
        text = page(api_with(detail_with(status="entregado", channel=channel)), "preparacion")
        assert NO_REPORT in flat(block(text, "prep-pasos"))
        assert items(block(text, "prep-pasos")) == []
        assert "Faltan" not in flat(block(text, "prep-cuenta"))


def test_preparation_says_nothing_secret_is_stored_and_tokens_are_issued_in_the_cli() -> None:
    text = page(api_with(), tab="preparacion")
    stored = flat(block(text, "prep-guarda"))
    assert "Qué guarda NicheRadar" in stored
    assert "Ninguna clave ni token: viven solo en tu Mac" in stored
    assert "El estado de cada paso que informa el canal" in stored
    cli = flat(block(text, "prep-cli"))
    assert "scripts/pilots.py token-issue" in cli
    assert "no desde la web" in cli


def test_videos_tab_lists_each_video_with_stage_visibility_cost_and_machine_minutes() -> None:
    videos = [
        pilot_video("v1"),
        pilot_video("v2", stage="awaiting_human", visibility="private", published_at=None),
        pilot_video("v3", stage="weird", cost_usd=None, machine_minutes=None),
    ]
    api = api_with(videos=videos)
    text = page(api, "videos")
    rows = items(block(text, "videos-lista"))
    assert len(rows) == 3
    first = flat(rows[0])
    for part in ("v1", "Publicado", "public", "5 nov", "US$ 0,32", "1 h 10 min"):
        assert part in first, (part, first)
    second = flat(rows[1])
    assert "v2" in second and "Espera tu veredicto" in second and "private" in second
    assert "weird" in flat(rows[2]) and "—" in flat(rows[2])
    assert api.count("GET", f"/api/v1/pilots/{PID}/videos") == 1
    empty = page(api_with(videos=[]), "videos")
    assert "Todavía no hay videos reportados." in flat(block(empty, "tab-videos"))


def test_videos_are_only_requested_for_the_videos_tab() -> None:
    api = api_with(videos=[pilot_video()])
    for tab in (None, "resumen", "preparacion", "reglas", "historial"):
        page(api, tab)
    assert api.count("GET", f"/api/v1/pilots/{PID}/videos") == 0
    page(api, "videos")
    assert api.count("GET", f"/api/v1/pilots/{PID}/videos") == 1


def test_videos_tab_when_the_videos_call_fails_shows_a_note_and_the_rest_still_renders() -> None:
    for broken in ((503, {"detail": "x"}), (200, {"items": "no"}), (200, {})):
        api = Api(
            {DETAIL: (200, pilot_detail()), VIDEOS: broken, STATUS: (200, {"radar_paused": False})}
        )
        text = page(api, "videos")
        assert "No se pudieron cargar los videos" in flat(block(text, "tab-videos"))
        assert "Piloto · historia militar explicada" in text
        assert block(text, "linea-estados") and block(text, "pestanas")


def rule(text: str, status: str = "cumple", **over: object) -> dict[str, object]:
    base = {"id": "r", "text": text, "milestone": "video:10", "status": status, "detail": "d"}
    return base | over


def test_rules_tab_lists_each_rule_with_its_milestone_status_and_detail_escaped() -> None:
    evaluation = {
        "rules": [
            rule("Regla A", "cumple", detail="3 de 3 videos"),
            rule("Regla B", "no_cumple", milestone="week:6"),
            rule("Regla C", "pendiente", milestone="month:6"),
            rule("Regla D", "sin_datos_suficientes"),
            rule("Regla E", "revision_manual"),
            rule("Regla F", "no_evaluable"),
            rule(HOSTILE, "otra", milestone=HOSTILE, detail=HOSTILE),
        ],
        "milestones": [],
        "close_after": 2,
    }
    text = page(api_with(detail_with(evaluation=evaluation)), "reglas")
    rows = [flat(r) for r in items(block(text, "reglas-lista"))]
    assert rows[0] == "Regla A video 10 Cumple 3 de 3 videos"
    assert rows[1].startswith("Regla B semana 6 No cumple")
    assert rows[2].startswith("Regla C mes 6 Pendiente")
    assert rows[3].startswith("Regla D video 10 Sin datos suficientes")
    assert rows[4].startswith("Regla E video 10 Revisión manual")
    assert rows[5].startswith("Regla F video 10 No evaluable")
    assert HOSTILE in rows[6]
    assert ESCAPED in text and "<script>" not in text


def test_rules_tab_without_rules_says_so() -> None:
    for evaluation in ({}, {"rules": "x"}, None, {"rules": [None, 3]}):
        text = page(api_with(detail_with(evaluation=evaluation)), "reglas")
        assert "Todavía no hay reglas evaluadas." in flat(block(text, "tab-reglas"))


def event(kind: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "at": "2026-11-03T10:00:00Z",
        "actor": "propietario (web)",
        "kind": kind,
        "detail": {},
    }
    return base | over


def test_history_tab_translates_event_kinds_and_escapes_details() -> None:
    kinds = {
        "authorized": "Autorizado",
        "delivered": "Entregado al canal",
        "first_report": "Primer reporte",
        "decision_pending": "Decisión pendiente",
        "decision_seguir": "Decidiste seguir",
        "decision_cerrar": "Decidiste cerrar",
        "cancelled": "Cancelado",
        "superseded": "Reemplazado",
        "gate_failure_accepted": "Aceptaste una compuerta no cumplida",
    }
    events = [event(k, at=f"2026-11-0{i + 1}T10:00:00Z") for i, k in enumerate(kinds)]
    text = page(api_with(detail_with(events=events)), "historial")
    rows = [flat(r) for r in items(block(text, "historial-lista"))]
    assert len(rows) == 9
    # Most recent first: the list is the reverse of the order the API gives.
    assert [r.split(" · ")[0] for r in rows] == list(reversed(list(kinds.values())))
    assert "09/11/2026 05:00" in rows[0]
    assert "propietario (web)" in rows[0]
    hostile = [
        event("raro_" + HOSTILE, actor=HOSTILE, detail={"note": HOSTILE}),
        event("decision_seguir", detail={"note": "ok <b>x</b>"}),
    ]
    text = page(api_with(detail_with(events=hostile)), "historial")
    assert "<script>" not in text and "<b>x</b>" not in text
    assert "ok &lt;b&gt;x&lt;/b&gt;" in text and ESCAPED in text
    empty = page(api_with(detail_with(events=[])), "historial")
    assert "Todavía no hay eventos." in flat(block(empty, "tab-historial"))
    for junk in (None, "x", {"a": 1}, [None, 3, {"kind": 3, "at": 4}]):
        page(api_with(detail_with(events=junk)), "historial")


def test_an_unknown_tab_falls_back_to_summary() -> None:
    assert parse_tab("videos") == "videos"
    for junk in (None, "", "x", "RESUMEN", "videos\n", 3, ["videos"]):
        assert parse_tab(junk) == "resumen"
    for junk in ("zzz", "%0A", "videos%0A", ""):
        response = client(api_with()).get(f"/pilotos/{PID}?pestana={junk}")
        assert response.status_code == 200
        assert 'id="tab-resumen"' in response.text


def test_the_preparation_route_redirects_to_the_tab() -> None:
    api = api_with()
    web = client(api)
    response = web.get(f"/pilotos/{PID}/preparacion")
    assert response.status_code == 303
    assert response.headers["location"] == f"/pilotos/{PID}?pestana=preparacion"
    assert api.count("GET", f"/api/v1/pilots/{PID}") == 0
    anonymous = TestClient(create_app(settings()), follow_redirects=False)
    assert anonymous.get(f"/pilotos/{PID}").status_code == 303
    assert anonymous.get(f"/pilotos/{PID}").headers["location"].startswith("/login?next=")
    assert "/login" in anonymous.get(f"/pilotos/{PID}/preparacion").headers["location"]


@pytest.mark.parametrize(
    "bad",
    [
        "pil_20261102_x%0A",
        "..%2Fpilots",
        "pil_2026_x",
        "x" * 300,
        "PIL_20261102_x",
        "%20",
        "pil_%D9%A2%D9%A0%D9%A2%D9%A6%D9%A1%D9%A1%D9%A0%D9%A2_x",
        "pil_20261102_" + "a" * 200,
        "pil_20261102_a_b",
    ],
)
def test_a_malformed_pilot_id_is_404_and_never_reaches_the_api(bad: str) -> None:
    api = api_with()
    web = client(api)
    for suffix in ("", "/preparacion", "?pestana=videos"):
        path = f"/pilotos/{bad}{suffix}"
        response = web.get(path)
        assert response.status_code == 404, path
        if "%2F" not in bad:  # an encoded slash never even matches the route: plain 404
            assert "No se encontró lo que buscabas." in response.text
    assert web.get("/pilotos/pil_20261102_x%0A").status_code == 404
    assert [c for c in api.calls if "/pilots" in c.url.path] == []
    assert api.count("GET", "/api/v1/status") == 0


def test_unknown_pilot_is_404_and_api_down_is_503_without_status_call() -> None:
    api = Api({DETAIL: (404, {"detail": "x"}), STATUS: (200, {"radar_paused": False})})
    response = client(api).get(f"/pilotos/{PID}")
    assert response.status_code == 404 and "No se encontró lo que buscabas." in response.text
    assert api.count("GET", "/api/v1/status") == 0

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({DETAIL: boom, STATUS: (200, {"radar_paused": False})})
    response = client(api).get(f"/pilotos/{PID}")
    assert response.status_code == 503
    assert "API no disponible" in response.text
    assert api.count("GET", "/api/v1/status") == 0
    assert api.count("GET", f"/api/v1/pilots/{PID}/videos") == 0


def test_hostile_text_everywhere_is_escaped() -> None:
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    channel = {
        "note": HOSTILE,
        "checks": [check(HOSTILE, False, detail=HOSTILE, expires_at="2026-11-04T00:00:00Z")],
    }
    detail = detail_with(
        status="en_ejecucion",
        niche_label=HOSTILE,
        target_channel=HOSTILE,
        close_reason=HOSTILE,
        channel=channel,
        package=package,
        proposal={"action": "cerrar", "reason": HOSTILE},
        evaluation={"rules": [rule(HOSTILE, detail=HOSTILE, milestone=HOSTILE)], "close_after": 2},
        events=[event(HOSTILE, actor=HOSTILE, detail={"note": HOSTILE})],
    )
    for tab in (None, "preparacion", "videos", "reglas", "historial"):
        videos = [pilot_video(HOSTILE, visibility=HOSTILE, stage=HOSTILE)]
        text = page(api_with(detail, videos=videos), tab)
        assert "<script>" not in text, tab
        assert "[x](https://evil.test)" not in text.replace(ESCAPED, ""), tab
        assert ESCAPED in text, tab
        section = {
            None: "res-bloqueos",
            "preparacion": "prep-pasos",
            "videos": "videos-lista",
            "reglas": "reglas-lista",
            "historial": "historial-lista",
        }[tab]
        assert ESCAPED in block(text, section), (tab, section)
    summary = page(api_with(detail))
    assert ESCAPED in block(summary, "res-propuesta")
    assert ESCAPED in block(summary, "res-bloqueos")
    assert ESCAPED in block(summary, "cabecera")
    closed = page(api_with(detail_with(status="cerrado", close_reason=HOSTILE)))
    assert ESCAPED in block(closed, "res-estado")


def test_package_without_optional_fields_and_null_channel_do_not_500() -> None:
    nasty: list[dict[str, object]] = [
        {"package": {}},
        {"package": None},
        {"package": "x"},
        {"package": {"budget": "x", "stop_rules": "x"}},
        {"channel": None},
        {"channel": "x"},
        {"channel": {"checks": [None, "x", {"ok": "yes"}]}},
        {"evaluation": {}},
        {"evaluation": None},
        {"evaluation": {"rules": [{}], "totals": None}},
        {"totals": None},
        {"totals": {}},
        {"totals": "x"},
        {"events": None},
        {"events": [{"detail": "x"}, {"kind": "authorized", "at": "mal", "detail": None}]},
        {"proposal": None},
        {"proposal": {"action": 3, "reason": None}},
        {
            "authorized_at": "no es fecha",
            "delivered_at": "2026-11-03T10:00:00",
            "last_report_at": 5,
        },
        {"first_report_at": "9999-12-31T23:59:59Z"},
        {"niche_label": None, "format": None, "language": None, "target_channel": None},
        {"status": None},
        {"status": "inventado"},
    ]
    for over in nasty:
        for tab in TABS:
            api = api_with(detail_with(**over), videos=[{}, None, "x", pilot_video()])
            response = client(api).get(f"/pilotos/{PID}?pestana={tab}")
            assert response.status_code == 200, (over, tab, response.text[:300])
    # a detail that is not even an object is a controlled error, never an unhandled 500
    response = client(api_with(["x"])).get(f"/pilotos/{PID}")
    assert response.status_code == 503


def test_the_action_buttons_are_links_only_when_the_status_allows_them() -> None:
    def actions(status: str) -> str:
        return block(page(api_with(detail_with(status=status))), "res-acciones")

    pending = actions("decision_pendiente")
    assert f'href="/pilotos/{PID}/decidir?accion=seguir"' in pending
    assert f'href="/pilotos/{PID}/decidir?accion=cerrar"' in pending
    assert "/cancelar" not in pending and "/cierre" not in pending
    running = actions("en_ejecucion")
    assert "/cancelar" not in running
    assert f'href="/pilotos/{PID}/decidir?accion=cerrar"' in running
    assert "accion=seguir" not in running and "disabled" in running
    assert "Solo cuando hay una decisión pendiente" in flat(running)
    for status in ("autorizado", "entregado"):
        text = actions(status)
        assert f'href="/pilotos/{PID}/cancelar"' in text
        assert "decidir?accion" not in text
    for status in ("cerrado", "cancelado"):
        text = actions(status)
        assert "decidir?accion" not in text and "/cancelar" not in text
    assert f'href="/pilotos/{PID}/cierre"' in actions("cerrado")
    assert "/cierre" not in actions("en_ejecucion")
    assert "disabled" in actions("cancelado")


def test_the_authorize_success_redirect_goes_to_the_panel() -> None:
    from tests.test_web_pilot_authorize import AUTH, ID, URL, post
    from tests.test_web_pilot_authorize import api_with as authorize_api
    from tests.web_helpers import csrf_of

    created = {"pilot_id": PID, "status": "autorizado", "package": {}}
    web = make_client(authorize_api(extra={AUTH: (201, created)}))
    response = post(web, csrf_of(web.get(URL).text))
    assert response.status_code == 303
    assert response.headers["location"] == f"/pilotos/{PID}?aviso=autorizado"
    assert ID not in response.headers["location"]


def test_the_notice_comes_only_from_fixed_keys() -> None:
    expected = {
        "autorizado": "Piloto autorizado",
        "seguido": "Decidiste seguir",
        "cerrado": "Piloto cerrado",
        "cancelado": "Piloto cancelado",
    }
    for key, message in expected.items():
        text = page(api_with(), extra=f"aviso={key}")
        assert message in flat(block(text, "aviso")), key
    for junk in ("otro", "", "AUTORIZADO", "autorizado%0A", "autorizado%20", "%3Cscript%3E"):
        response = client(api_with()).get(f"/pilotos/{PID}?aviso={junk}")
        assert response.status_code == 200
        assert 'id="aviso"' not in response.text
        assert "<script>" not in response.text


def test_thousands_of_items_are_capped_and_rendered() -> None:
    rules = [rule(f"Regla {i}") for i in range(3000)]
    events = [event("authorized", detail={"note": f"n{i}"}) for i in range(3000)]
    checks = [check(f"Paso {i}", i % 2 == 0) for i in range(3000)]
    videos = [pilot_video(f"v{i}") for i in range(3000)]
    detail = detail_with(
        evaluation={"rules": rules, "close_after": 2},
        events=events,
        channel={"checks": checks},
    )
    api = api_with(detail, videos=videos)
    assert len(items(block(page(api, "reglas"), "reglas-lista"))) == 100
    assert len(items(block(page(api, "historial"), "historial-lista"))) == 100
    assert len(items(block(page(api, "preparacion"), "prep-pasos"))) == 100
    assert len(items(block(page(api, "videos"), "videos-lista"))) == 100
    text = page(api, "preparacion")
    assert "Faltan 1500 de 3000 pasos." in flat(block(text, "prep-cuenta"))
    assert "Se muestran los primeros 100" in flat(block(text, "prep-pasos"))


def test_a_negative_published_count_is_read_as_zero() -> None:
    detail = detail_with(
        status="en_ejecucion",
        first_report_at="2026-11-01T12:00:00Z",
        totals=totals(published=-5),
    )
    assert "Día 3 · 0 de 10 publicados" in flat(block(page(api_with(detail)), "res-estado"))


def test_accessibility_hooks_for_disabled_actions_and_touch_targets() -> None:
    text = page(api_with(detail_with(status="en_ejecucion")))
    acciones = block(text, "res-acciones")
    disabled = re.findall(r'<button[^>]*disabled[^>]*aria-describedby="([^"]+)"', acciones)
    assert len(disabled) == 3
    for target in disabled:
        assert re.search(rf'<span[^>]*id="{target}"[^>]*>[^<]+</span>', acciones)
    assert re.search(r'<a class="tap"[^>]*>Ver las reglas</a>', block(text, "res-reglas"))
    assert '<a class="tap" href="/pilotos">← Volver a Pilotos</a>' in text
    css = open("src/nicheradar/web/static/css/app.css", encoding="utf-8").read()
    assert ".sr-only{" in css and ".tap{" in css and "min-height:44px" in css.split(".tap{")[1]


def test_the_closed_notice_links_to_the_closing_summary_only_for_a_closed_pilot() -> None:
    closed = page(api_with(pilot_detail(status="cerrado")), extra="aviso=cerrado")
    notice = block(closed, "aviso")
    assert f'href="/pilotos/{PID}/cierre"' in notice and "Ver resumen de cierre" in flat(notice)
    other = page(api_with(pilot_detail(status="en_ejecucion")), extra="aviso=cerrado")
    assert "Ver resumen de cierre" not in block(other, "aviso")
    for key in ("seguido", "cancelado", "autorizado"):
        text = page(api_with(pilot_detail(status="cerrado")), extra=f"aviso={key}")
        assert f"/pilotos/{PID}/cierre?" not in text
        assert "Ver resumen de cierre" not in block(text, "aviso")
