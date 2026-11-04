# tests/test_web_smoke_screens.py
"""Cross-screen safety net: hostile text, API down, bad shapes, origins, CSRF."""

import copy
import json
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.web_helpers import (
    HOSTILE,
    REPORT_ID,
    Api,
    csrf_of,
    dossier_v3,
    flow_item,
    make_client,
    niche_detail,
    niche_item,
    pilot_detail,
    pilot_item,
    pilot_video,
    report_detail,
    research,
    schedule,
    scrape_run,
    subniche_card,
    subniche_item,
)

PID = "pil_20261102_historia"
ROUTES = [
    "/",
    "/nichos",
    "/nichos/investigar?etiqueta=x&formato=long",
    "/subnichos",
    "/subnichos/uno",
    "/operacion",
    "/operacion/ejecuciones",
    "/mas",
    "/operacion/scraper/pausar",
    "/operacion/scraper/reanudar",
    f"/informes/{REPORT_ID}",
    f"/pilotos/autorizar?informe={REPORT_ID}",
    "/pilotos",
    "/pilotos?filtro=bloqueo",
    f"/pilotos/{PID}",
    f"/pilotos/{PID}?pestana=preparacion",
    f"/pilotos/{PID}?pestana=videos",
    f"/pilotos/{PID}?pestana=calibracion",
    f"/pilotos/{PID}?pestana=reglas",
    f"/pilotos/{PID}?pestana=historial",
    f"/pilotos/{PID}/decidir?accion=seguir",
    f"/pilotos/{PID}/decidir?accion=cerrar",
    f"/pilotos/{PID}/cancelar",
    f"/pilotos/{PID}/cierre",
]
STRUCTURAL = {
    "status", "format", "language", "decision", "recommendation", "schema_version", "id",
    "slug", "state", "kind", "confidence", "comparator", "metric", "level", "verdict", "basis",
    "origin", "stage", "stages", "source", "version", "signal", "rpm_source", "rpm_state",
    "family", "parent_niche_slug", "visibility", "source_state", "channel_status",
    "channel_id", "pilot_id", "report_id", "action", "code",
    "path", "unit", "currency", "kind_of", "classification", "rights", "automation", "mode",
}  # fmt: skip
STATIC_ROUTES = {"/mas"}  # the menu reads no API at all
ECHO_FREE = STATIC_ROUTES | {"/operacion/scraper/pausar", "/operacion/scraper/reanudar"}
SCRIPT = "<script>alert(1)</script>"


def hostile(value: Any, key: str | None = None) -> Any:
    """Replace every string leaf by HOSTILE, except structural keys, ids, dates and URLs."""
    if isinstance(value, dict):
        return {k: hostile(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [hostile(v, key) for v in value]
    if isinstance(value, str):
        keep = key in STRUCTURAL or (key or "").endswith(("_at", "_id", "_until", "_low", "_high"))
        return value if keep else HOSTILE
    return value


def pilot_fixture(status: str = "decision_pendiente") -> dict[str, Any]:
    rule = {"id": "r1", "text": "t", "milestone": "video:3", "status": "no_cumple", "detail": "d"}
    event = {"kind": "decision_seguir", "actor": "humano", "at": "2026-11-04T10:00:00Z"}
    return pilot_detail(
        PID,
        status=status,
        evaluation={
            "rules": [rule],
            "milestones": [],
            "totals": {},
            "warnings": ["w"],
            "close_after": 2,
        },
        events=[event | {"detail": {"note": "n"}}, event | {"kind": "authorized"}],
        acknowledged=["a"],
    ) | {"proposal": {"action": "cerrar", "reason": "r"}}


def fixtures(route: str = "") -> dict[str, Any]:
    pilot_status = "entregado" if route.endswith("/cancelar") else "decision_pendiente"
    return {
        "status": {"radar_paused": True, "timezone": "America/Lima"},
        "niches": {"items": [niche_item()], "total": 1, "limit": 200, "offset": 0},
        "niche": niche_detail(),
        "flows": {"items": [flow_item("listo", id=REPORT_ID), flow_item("en_curso")]},
        "report": report_detail(dossier=dossier_v3()),
        "pilots": {"items": [pilot_item(PID, status="decision_pendiente", needs_decision=True)]},
        "pilot": pilot_fixture(pilot_status),
        "videos": {
            "items": [
                pilot_video("v1", human_minutes=0, human_minutes_method="cronometro"),
                pilot_video("v2", stage="measuring", human_minutes=45),
                pilot_video("v3", human_minutes=None),
            ]
        },
        "closing": "Resumen de cierre\n\n- una linea",
        "subniches": {"items": [subniche_item(research=research())]},
        "card": subniche_card(research=research()),
        "schedule": schedule(),
        "runs": {
            "items": [
                scrape_run("partial", error_code="blocked_by_site"),
                scrape_run("succeeded"),
                scrape_run("failed", error_code="timeout", stage="detail"),
            ]
        },
    }


def dump(value: Any) -> bytes:
    return json.dumps(value, allow_nan=True).encode()  # NaN/Infinity come out as bare tokens


class SmokeApi(Api):
    """Fake API serving `data` by resource, read on every call so tests can mutate it in place."""

    def __init__(self, data: dict[str, Any] | None, error: Exception | None = None) -> None:
        super().__init__()
        self.data, self.error = data, error
        self.write_status = 500

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.data is not None
        path = request.url.path.removeprefix("/api/v1")
        if request.method != "GET":
            return httpx.Response(self.write_status, json={"detail": {"code": "bad_transition"}})
        if path == f"/pilots/{PID}/closing-summary":
            return httpx.Response(
                200,
                content=str(self.data["closing"]).encode(),
                headers={"content-type": "text/plain"},
            )
        if path == f"/pilots/{PID}/videos":
            return httpx.Response(
                200, content=dump(self.data["videos"]), headers={"content-type": "application/json"}
            )
        if path == f"/pilots/{PID}":
            return httpx.Response(
                200, content=dump(self.data["pilot"]), headers={"content-type": "application/json"}
            )
        key = next(
            (k for prefix, k in RESOURCES if path == prefix or path.startswith(prefix + "/")), None
        )
        if key is None:
            return httpx.Response(404, json={"detail": "not found"})
        if prefix_is_item(path, key):
            key = ITEM_KEYS[key]
        return httpx.Response(
            200, content=dump(self.data[key]), headers={"content-type": "application/json"}
        )


RESOURCES = [
    ("/status", "status"),
    ("/market/niches", "niches"),
    ("/flow-research", "flows"),
    ("/pilots", "pilots"),
    ("/subniches", "subniches"),
    ("/market/schedule", "schedule"),
    ("/market/runs", "runs"),
]
ITEM_KEYS = {"niches": "niche", "flows": "report", "subniches": "card"}


def prefix_is_item(path: str, key: str) -> bool:
    return key in ITEM_KEYS and path.count("/") > (2 if key == "niches" else 1)


def api_for(data: dict[str, Any] | None, error: Exception | None = None) -> SmokeApi:
    return SmokeApi(data, error)


def client_for(
    data: dict[str, Any] | None, error: Exception | None = None
) -> tuple[TestClient, SmokeApi]:
    api = api_for(data, error)
    web = make_client(api)
    api.calls.clear()
    return web, api


def check_safe(response: httpx.Response, route: str) -> None:
    assert response.status_code < 500 or response.status_code == 503, (route, response.status_code)
    assert "Traceback" not in response.text, route


@pytest.mark.parametrize("route", ROUTES)
def test_hostile_text_is_escaped_on_every_screen(route: str) -> None:
    web, _ = client_for(hostile(fixtures(route)))
    response = web.get(route)
    check_safe(response, route)
    body = response.text
    assert SCRIPT not in body
    assert not re.search(r"""href\s*=\s*["']\s*javascript:""", body, re.I)
    assert not re.search(r"""href\s*=\s*["']https?://[^"']*evil""", body, re.I)
    if not route.startswith("/nichos/investigar") and route not in ECHO_FREE:
        # that form only echoes the query label; the menu shows no API text
        assert "&lt;script&gt;" in body or response.status_code != 200, route


def test_a_hostile_label_in_the_investigate_query_is_escaped() -> None:
    web, _ = client_for(hostile(fixtures()))
    response = web.get("/nichos/investigar", params={"etiqueta": HOSTILE, "formato": "long"})
    check_safe(response, "investigar")
    assert SCRIPT not in response.text


@pytest.mark.parametrize("route", ROUTES)
def test_an_unreachable_api_gives_a_spanish_message_never_a_500(route: str) -> None:
    web, _ = client_for(None, httpx.ConnectError("down"))
    response = web.get(route)
    check_safe(response, route)
    assert response.status_code in (200, 503), (route, response.status_code)
    if route in STATIC_ROUTES:
        assert response.status_code == 200, route
        return
    assert re.search(
        r"no disponible|No se pudo|No se encontr|Sin datos|sin conexi", response.text, re.I
    ), route


def paths(value: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    yield prefix
    if isinstance(value, dict):
        for k, v in value.items():
            yield from paths(v, (*prefix, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from paths(v, (*prefix, i))


def replaced(data: Any, path: tuple[Any, ...], new: Any) -> Any:
    copied = copy.deepcopy(data)
    if not path:
        return new
    node = copied
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = new
    return copied


BAD: list[Any] = [None, "x", 7, [], {}, float("nan"), float("inf")]


@pytest.mark.parametrize("route", ROUTES)
def test_malformed_shapes_never_give_a_500(route: str) -> None:
    base = fixtures(route)
    data = copy.deepcopy(base)
    web, api = client_for(data)  # the fake API reads `data` on every call
    failures: list[str] = []
    for key in base:
        for path in paths(base[key]):
            for bad in BAD:
                data[key] = replaced(base[key], path, bad)
                api.calls.clear()
                where = f"{key}{list(path)} <- {bad!r}"
                try:
                    response = web.get(route)
                except Exception as error:  # an unhandled error is a 500 for the user
                    failures.append(f"{where}: {type(error).__name__}: {error}")
                    continue
                if response.status_code >= 500 and response.status_code != 503:
                    failures.append(f"{where}: {response.status_code}")
            data[key] = base[key]
    assert not failures, (
        len(failures),
        sorted({f.split(": ", 1)[1][:90] for f in failures}),
        failures[:6],
    )


def _naive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _naive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_naive(v) for v in value]
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:]+Z", value):
        return value.removesuffix("Z")
    return value


@pytest.mark.parametrize("route", ROUTES)
def test_timezone_naive_datetimes_never_give_a_500(route: str) -> None:
    web, _ = client_for(_naive(fixtures(route)))
    check_safe(web.get(route), route)


def raw_nan_api() -> Api:
    nan = httpx.Response(200, content=b'{"x": NaN, "items": [{"y": Infinity}]}')
    return Api({("GET", p): lambda _r: nan for p in NAN_PATHS})


NAN_PATHS = [
    "/api/v1/status",
    "/api/v1/market/niches",
    "/api/v1/market/niches/x",
    "/api/v1/flow-research",
    f"/api/v1/flow-research/{REPORT_ID}",
    "/api/v1/pilots",
    "/api/v1/subniches",
    "/api/v1/subniches/uno",
    "/api/v1/market/schedule",
    "/api/v1/market/runs",
    f"/api/v1/pilots/{PID}",
    f"/api/v1/pilots/{PID}/videos",
    f"/api/v1/pilots/{PID}/closing-summary",
]


@pytest.mark.parametrize("route", ROUTES)
def test_bare_nan_in_the_json_body_never_gives_a_500(route: str) -> None:
    web = make_client(raw_nan_api())
    check_safe(web.get(route), route)


THIRD_PARTY = re.compile(
    r"""(?:src|href|action|poster|srcset)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?(?:https?:)?//""",
    re.I,
)
INLINE = re.compile(r"<style|\sstyle\s*=|<script(?![^>]*\ssrc=)|\son[a-z]+\s*=", re.I)


def good_clients() -> Iterator[tuple[str, TestClient]]:
    for route in ROUTES:
        web, _ = client_for(fixtures(route))
        yield route, web


def test_no_screen_loads_third_party_origins_or_inline_code() -> None:
    csps: set[str | None] = set()
    for route, web in good_clients():
        response = web.get(route)
        assert response.status_code == 200, route
        csps.add(response.headers.get("content-security-policy"))
        body = response.text
        assert not INLINE.search(body), (route, INLINE.search(body))
        for found in re.finditer(r"""<a\s[^>]*href\s*=\s*["']https?://[^>]*>""", body, re.I):
            assert route.startswith("/informes/"), (route, found.group(0))
            assert "noopener" in found.group(0) and "noreferrer" in found.group(0), found.group(0)
            assert "nofollow" in found.group(0), found.group(0)
        stripped = re.sub(r"""<a\s[^>]*href\s*=\s*["']https?://[^>]*>""", "", body, flags=re.I)
        assert not THIRD_PARTY.search(stripped), (route, THIRD_PARTY.search(stripped))
    assert len(csps) == 1 and None not in csps


POSTS: list[tuple[str, dict[str, str]]] = [
    ("/nichos/decidir", {"etiqueta": "x", "formato": "long", "decision": "descartado"}),
    ("/nichos/investigar", {"etiqueta": "x", "formato": "long", "idioma": "en"}),
    ("/pilotos/autorizar", {"informe": REPORT_ID, "canal": "c"}),
    (f"/pilotos/{PID}/decidir?accion=seguir", {"note": "ok"}),
    (f"/pilotos/{PID}/decidir?accion=cerrar", {"note": "ok"}),
    (f"/pilotos/{PID}/cancelar", {"reason": "ok"}),
    ("/subnichos/uno/investigar", {"idioma": "en"}),
    ("/salir", {}),
    ("/operacion/scraper/pausar", {}),
    ("/operacion/scraper/reanudar", {}),
]


@pytest.mark.parametrize(("path", "form"), POSTS)
def test_every_post_without_csrf_is_refused_and_touches_no_api(
    path: str, form: dict[str, str]
) -> None:
    web, api = client_for(fixtures())
    response = web.post(path, data=form)
    assert response.status_code in (302, 303, 400, 403), (path, response.status_code)
    # the layout may read the cached radar badge; nothing else (no data read, no write)
    assert [c.url.path for c in api.calls if c.url.path != "/api/v1/status"] == [], path
    assert all(c.method == "GET" for c in api.calls), path
    assert web.get("/nichos").status_code == 200  # the session is intact: nothing was applied


def test_login_is_the_only_post_outside_csrf() -> None:
    web, api = client_for(fixtures())
    bare = TestClient(web.app, follow_redirects=False)
    assert bare.post("/login", data={"password": "bad"}).status_code in (200, 303, 401, 429)
    assert api.calls == []


PILOT_POSTS = [
    (f"/pilotos/{PID}/decidir?accion=seguir", "note"),
    (f"/pilotos/{PID}/decidir?accion=cerrar", "note"),
    (f"/pilotos/{PID}/cancelar", "reason"),
]


def _writes(api: SmokeApi) -> list[str]:
    return [f"{c.method} {c.url.path}" for c in api.calls if c.method != "GET"]


@pytest.mark.parametrize(("path", "field"), PILOT_POSTS)
def test_a_pilot_post_with_csrf_in_a_disallowed_state_writes_nothing(path: str, field: str) -> None:
    for status in ("cerrado", "cancelado", "autorizado", "en_ejecucion", "inventado"):
        data = fixtures()
        data["pilot"]["status"] = status
        web, api = client_for(data)
        token = csrf_of(web.get("/pilotos").text)
        disallowed = (
            (path.endswith("seguir") and status != "decision_pendiente")
            or (path.endswith("cerrar") and status not in ("en_ejecucion", "decision_pendiente"))
            or (path.endswith("cancelar") and status not in ("autorizado", "entregado"))
        )
        if not disallowed:
            continue
        response = web.post(path, data={"csrf": token, field: "una nota"})
        check_safe(response, path)
        assert response.status_code in (409, 503), (path, status, response.status_code)
        assert _writes(api) == [], (path, status)


@pytest.mark.parametrize(("path", "field"), PILOT_POSTS)
def test_malformed_pilot_shapes_never_give_a_500_on_the_post_paths(path: str, field: str) -> None:
    base = fixtures("/cancelar" if path.endswith("cancelar") else "")
    data = copy.deepcopy(base)
    web, api = client_for(data)
    api.write_status = 409
    token = csrf_of(web.get("/pilotos").text)
    failures: list[str] = []
    for path_in_pilot in paths(base["pilot"]):
        for bad in BAD:
            data["pilot"] = replaced(base["pilot"], path_in_pilot, bad)
            for note in ("una nota", ""):
                where = f"pilot{list(path_in_pilot)} <- {bad!r} note={note!r}"
                try:
                    response = web.post(path, data={"csrf": token, field: note})
                except Exception as error:
                    failures.append(f"{where}: {type(error).__name__}: {error}")
                    continue
                if response.status_code >= 500 and response.status_code != 503:
                    failures.append(f"{where}: {response.status_code}")
                assert "Traceback" not in response.text
        data["pilot"] = base["pilot"]
    assert not failures, (len(failures), failures[:6])


def test_the_pilot_preparation_address_redirects_and_never_loads_third_parties() -> None:
    web, _ = client_for(fixtures())
    response = web.get(f"/pilotos/{PID}/preparacion")
    assert response.status_code == 303
    assert response.headers["location"] == f"/pilotos/{PID}?pestana=preparacion"


def test_unknown_pilot_statuses_stages_and_event_kinds_render() -> None:
    data = fixtures()
    data["pilot"]["status"] = "inventado"
    data["pilot"]["events"] = [{"kind": "inventado", "actor": "x", "at": "2026-11-04T10:00:00Z"}]
    data["videos"] = {"items": [pilot_video("v1", stage="inventado", source_state="X")]}
    data["pilots"] = {"items": [pilot_item(PID, status="inventado")]}
    web, _ = client_for(data)
    for route in ROUTES:
        if route.startswith("/pilotos"):
            check_safe(web.get(route), route)


def test_huge_numbers_in_the_pilot_payload_never_give_a_500() -> None:
    data = fixtures()
    huge = 10**400
    data["pilot"]["totals"] = {"spent_usd": huge, "published": huge, "machine_minutes": huge}
    data["pilot"]["package"]["budget"]["max_videos"] = huge
    data["pilot"]["package"]["budget"]["high"] = huge
    data["videos"] = {"items": [pilot_video("v1", cost_usd=huge, machine_minutes=huge)]}
    data["pilots"] = {"items": [pilot_item(PID, totals={"videos": huge, "spent_usd": huge})]}
    web, _ = client_for(data)
    for route in ROUTES:
        if route.startswith("/pilotos"):
            check_safe(web.get(route), route)


CALIBRATION = f"/pilotos/{PID}?pestana=calibracion"
BAD_MINUTES: list[Any] = ["45", [45], {"a": 1}, True, -3, 4.5, 10**400, None]


def test_hostile_human_minutes_shapes_never_give_a_500_on_calibration_and_today() -> None:
    for bad in BAD_MINUTES:
        data = fixtures()
        data["videos"] = {
            "items": [
                pilot_video("v1", human_minutes=bad, human_minutes_method=bad),
                pilot_video("v2", human_minutes=bad),
            ]
        }
        web, _ = client_for(data)
        for route in (CALIBRATION, "/"):
            response = web.get(route)
            check_safe(response, f"{route} <- {bad!r}")
            assert response.status_code == 200, (route, bad, response.status_code)


def test_raw_nan_human_minutes_in_the_videos_body_never_gives_a_500() -> None:
    class NanVideos(SmokeApi):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == f"/api/v1/pilots/{PID}/videos":
                body = (
                    b'{"items": [{"video_id": "v1", "human_minutes": NaN, "stage": "published"}]}'
                )
                return httpx.Response(200, content=body)
            return super().__call__(request)

    web = make_client(NanVideos(fixtures()))
    for route in (CALIBRATION, f"/pilotos/{PID}?pestana=videos", "/"):
        check_safe(web.get(route), route)


def test_a_calibration_block_of_another_type_degrades_the_tab_without_a_500() -> None:
    for bad in (None, "x", 7, [], [1], {}, {"videos": "x", "exit_criterion": []}):
        data = fixtures()
        data["report"]["dossier"]["calibration"] = bad
        web, _ = client_for(data)
        response = web.get(CALIBRATION)
        check_safe(response, repr(bad))
        assert response.status_code == 200, (bad, response.status_code)
        assert "Traceback" not in response.text


def test_measured_zero_counts_and_unmeasured_never_reads_as_zero_minutes() -> None:
    data = fixtures()
    data["videos"] = {"items": [pilot_video("v1", human_minutes=0, human_minutes_method="x")]}
    web, _ = client_for(data)
    assert re.search(r"(?<!\d)0 min\b", web.get(CALIBRATION).text)
    data["videos"] = {"items": [pilot_video("v1"), pilot_video("v2")]}
    web, _ = client_for(data)
    body = web.get(CALIBRATION).text
    assert "Aún sin minutos medidos" in body
    assert not re.search(r"(?<!\d)0 min\b", body)


SCRAPER_POSTS = ["/operacion/scraper/pausar", "/operacion/scraper/reanudar"]


@pytest.mark.parametrize("path", SCRAPER_POSTS)
def test_a_scraper_post_in_a_disallowed_state_writes_nothing(path: str) -> None:
    live_off = schedule(paused=True, mode="live", live_enabled=False)
    odd_values: list[Any] = ["x", 1, None, [], {}]
    odd_paused = [schedule(paused=value) for value in odd_values]
    cases = [live_off, *odd_paused, "x", [1], None]
    for case in cases:
        data = fixtures()
        data["schedule"] = case
        web, api = client_for(data)
        token = csrf_of(web.get("/mas").text)
        response = web.post(path, data={"csrf": token})
        check_safe(response, path)
        if path.endswith("reanudar") and case is live_off:
            assert response.status_code == 409, (path, case, response.status_code)
        elif case is not live_off:
            assert response.status_code in (409, 503), (path, case, response.status_code)
        assert _writes(api) == [], (path, case)


@pytest.mark.parametrize("route", ["/operacion", "/operacion/ejecuciones"])
def test_runs_and_schedule_of_the_wrong_type_never_give_a_500(route: str) -> None:
    junk_items: list[Any] = ["x", [1, 2, 3], 7, None, {}, [None], ["a", {"status": 1}]]
    odd_runs: list[Any] = [
        scrape_run() | {"status": 5},
        scrape_run(stage=[1], error_code=7),
        scrape_run(started_at="2026-11-03T11:00:00", finished_at="x"),
        scrape_run(started_at=3, finished_at=float("nan")),
    ]
    odd_schedules: list[Any] = [
        schedule(interval_seconds=float("nan")),
        schedule(interval_seconds=float("inf")),
        schedule(interval_seconds="x", next_due_at="2026-11-05T11:00:00"),
        schedule(next_due_at=7, mode=[1]),
    ]
    for items in [*junk_items, odd_runs]:
        for sched in [schedule(), *odd_schedules]:
            data = fixtures()
            data["runs"] = {"items": items}
            data["schedule"] = sched
            data["subniches"] = {"items": items}
            web, _ = client_for(data)
            response = web.get(route)
            check_safe(response, f"{route} <- {items!r} {sched!r}")
            assert response.status_code in (200, 503), (route, items, sched)
