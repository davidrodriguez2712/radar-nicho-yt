# tests/test_web_final_fixes.py
"""Final-review fixes: POST shape safety, fragments, ids, budgets and the channel choice."""

import json
import math
from decimal import Decimal
from typing import Any

import httpx
import pytest

from nicheradar.web import today
from nicheradar.web.format import compact, local_datetime
from nicheradar.web.pilots_form import budget_body, parse_form
from nicheradar.web.report import _number
from tests.web_helpers import (
    Api,
    csrf_of,
    dossier_v3,
    make_client,
    niche_detail,
    niche_item,
    report_detail,
)

ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
GET = ("GET", f"/api/v1/flow-research/{ID}")
PILOTS = ("GET", "/api/v1/pilots")
AUTH = ("POST", "/api/v1/pilots")
STATUS = ("GET", "/api/v1/status")
URL = f"/pilotos/autorizar?informe={ID}"
DETAIL = ("GET", "/api/v1/market/niches/historia militar explicada")
ORDER = ("POST", "/api/v1/flow-research")
SHAPE = "formato inesperado"


def pilot_api(detail: dict[str, Any] | None = None, extra: dict[Any, Any] | None = None) -> Api:
    routes: dict[tuple[str, str], Any] = {
        GET: (200, detail or report_detail(dossier=dossier_v3())),
        PILOTS: (200, {"items": []}),
        STATUS: (200, {"radar_paused": True}),
    }
    return Api(routes | (extra or {}))


def post_auth(web: Any, **over: str) -> Any:
    token = csrf_of(web.get(URL).text)
    data = {
        "csrf": token,
        "informe": ID,
        "max_videos": "10",
        "valid_days": "14",
        "close_after": "2",
        "canal": "",
    }
    return web.post("/pilotos/autorizar", data=data | over)


# --- I1 ---------------------------------------------------------------------------------------
def test_a_huge_number_in_the_form_is_a_field_error_not_a_crash() -> None:
    values, errors = parse_form(
        {"max_videos": "9" * 5000, "valid_days": "14", "close_after": "2", "canal": ""}
    )
    assert values is None and errors == {"max_videos": "1 a 50"}
    web = make_client(pilot_api())
    response = post_auth(web, max_videos="9" * 5000)
    assert response.status_code == 422 and "1 a 50" in response.text


def test_post_investigar_without_language_mix_is_a_503_with_the_form() -> None:
    detail = niche_detail()
    del detail["language_mix"]
    api = Api(
        {DETAIL: (200, detail), STATUS: (200, {"radar_paused": True}), ORDER: (201, {"id": ID})}
    )
    web = make_client(api)
    url = "/nichos/investigar?etiqueta=historia%20militar%20explicada&formato=long"
    token = csrf_of(web.get(url).text)
    response = web.post(
        "/nichos/investigar",
        data={
            "csrf": token,
            "etiqueta": "historia militar explicada",
            "formato": "long",
            "idioma": "en",
        },
    )
    assert response.status_code == 503 and SHAPE in response.text
    assert api.count("POST", "/api/v1/flow-research") == 0


def subniche_report(measured_at: str) -> dict[str, Any]:
    detail = report_detail(dossier=dossier_v3())
    detail["evidence"] = {
        "source": "subniche",
        "confidence": "media",
        "measurement": {"measured_at": measured_at},
        "gate": detail["evidence"]["gate"],
    }
    return detail


def test_a_naive_measurement_date_is_read_as_utc_on_get_and_post() -> None:
    web = make_client(pilot_api(subniche_report("2026-10-31T12:00:00")))
    page = web.get(URL)
    assert page.status_code == 200 and "31/10/2026" in page.text
    assert post_auth(web, max_videos="0").status_code == 422
    assert local_datetime("2026-10-31T12:00:00", "America/Lima") == "31/10/2026 07:00"


def test_an_unparsable_measurement_date_only_omits_its_line() -> None:
    web = make_client(pilot_api(subniche_report("not a date")))
    page = web.get(URL)
    assert page.status_code == 200 and "hace" not in page.text
    assert post_auth(web, max_videos="0").status_code == 422


def test_a_malformed_report_on_post_is_a_503_not_a_500() -> None:
    good = report_detail(dossier=dossier_v3())
    bad = good | {"format": []}
    reads: list[int] = []

    def flaky(_request: httpx.Request) -> httpx.Response:
        reads.append(1)
        return httpx.Response(200, json=good if len(reads) == 1 else bad)

    web = make_client(pilot_api(extra={GET: flaky}))
    response = post_auth(web)
    assert response.status_code == 503 and SHAPE in response.text
    assert "Traceback" not in response.text


# --- I2 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path", "route", "body"),
    [
        ("/nichos", ("GET", "/api/v1/market/niches"), {"items": [{"x": 1}], "total": 1}),
        ("/subnichos", ("GET", "/api/v1/subniches"), {"items": [{"x": 1}]}),
    ],
)
def test_a_shape_error_in_a_fragment_request_is_a_small_note(
    path: str, route: tuple[str, str], body: object
) -> None:
    api = Api(
        {
            route: (200, body),
            ("GET", "/api/v1/flow-research"): (200, {"items": []}),
            STATUS: (200, {"radar_paused": True}),
        }
    )
    response = make_client(api).get(path, headers={"HX-Request": "true"})
    assert response.status_code == 200 and SHAPE in response.text
    assert "<html" not in response.text and "topbar" not in response.text
    assert "HX-Request" in response.headers["vary"]


# --- I3 ---------------------------------------------------------------------------------------
def test_the_budget_card_says_the_totals_come_from_the_report() -> None:
    text = make_client(pilot_api()).get(URL).text
    assert "Presupuesto del informe (tope: 10 videos)" in text
    assert "no cambian con el tope" in text
    assert "Presupuesto de 10 videos" not in text


# --- M4 ---------------------------------------------------------------------------------------
def test_an_astronomical_budget_total_is_an_unusable_budget() -> None:
    dossier = dossier_v3()
    dossier["budget"]["totals"]["high"] = 1e30
    web = make_client(pilot_api(report_detail(dossier=dossier)))
    response = web.get(URL)
    assert response.status_code == 422 and "presupuesto utilizable" in response.text


# --- M6 / M7 ----------------------------------------------------------------------------------
@pytest.mark.parametrize("bad_id", [None, "x&y=1"])
def test_links_and_inputs_use_the_validated_report_id(bad_id: object) -> None:
    detail = report_detail(dossier=dossier_v3()) | {"id": bad_id}
    web = make_client(pilot_api(detail))
    informe = web.get(f"/informes/{ID}").text
    assert f"/pilotos/autorizar?informe={ID}" in informe and "x&amp;y=1" not in informe
    form = web.get(URL).text
    assert f'name="informe" value="{ID}"' in form and f'href="/informes/{ID}"' in form


@pytest.mark.parametrize("bad_id", [None, "x&y=1", ID + "\n"])
def test_the_niche_list_never_links_an_invalid_research_id(bad_id: object) -> None:
    flow = {"id": bad_id, "niche_label": "n0", "format": "long", "status": "listo"}
    api = Api(
        {
            ("GET", "/api/v1/market/niches"): (
                200,
                {"items": [niche_item("n0")], "total": 1},
            ),
            ("GET", "/api/v1/flow-research"): (200, {"items": [flow]}),
            STATUS: (200, {"radar_paused": True}),
        }
    )
    text = make_client(api).get("/nichos").text
    assert "/informes/" not in text and "Ver estado" in text


def test_an_order_id_with_a_trailing_newline_is_not_followed() -> None:
    api = Api(
        {
            DETAIL: (200, niche_detail()),
            STATUS: (200, {"radar_paused": True}),
            ORDER: (201, {"id": ID + "\n", "created": True}),
        }
    )
    web = make_client(api)
    token = csrf_of(
        web.get("/nichos/investigar?etiqueta=historia%20militar%20explicada&formato=long").text
    )
    response = web.post(
        "/nichos/investigar",
        data={
            "csrf": token,
            "etiqueta": "historia militar explicada",
            "formato": "long",
            "idioma": "en",
        },
    )
    assert (
        response.status_code == 303 and response.headers["location"] == "/nichos?aviso=error-creada"
    )


# --- M8 ---------------------------------------------------------------------------------------
def test_a_pilot_post_for_a_vanished_niche_is_a_404_with_the_form_kept() -> None:
    web = make_client(pilot_api(extra={AUTH: (404, {"detail": "gone"})}))
    response = post_auth(web, canal="canal-historias", max_videos="7")
    assert response.status_code == 404
    assert "El nicho ya no está en el radar. Inicia el flujo de nuevo." in response.text
    assert 'value="7"' in response.text and 'value="canal-historias"' in response.text


# --- M9 ---------------------------------------------------------------------------------------
def test_non_finite_numbers_are_not_numbers_anywhere() -> None:
    assert compact(math.inf) == "—" and compact(math.nan) == "—"
    assert _number(math.inf) is None and _number(math.nan) is None
    assert ArithmeticError in today.FAILED and IndexError in today.FAILED


# --- M10 --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "expected"),
    [("nuevo", None), ("existente", "canal-historias"), ("", "canal-historias")],
)
def test_the_channel_choice_decides_whether_the_typed_name_is_used(
    mode: str, expected: str | None
) -> None:
    bodies: list[dict[str, Any]] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(201, json={"pilot_id": "pil_20261102_x"})

    web = make_client(pilot_api(extra={AUTH: accept}))
    response = post_auth(web, canal="canal-historias", canal_modo=mode)
    assert response.status_code == 303
    assert bodies[0].get("target_channel") == expected


def test_a_new_channel_ignores_a_malformed_typed_name() -> None:
    bodies: list[dict[str, Any]] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(201, json={"pilot_id": "pil_20261102_x"})

    web = make_client(pilot_api(extra={AUTH: accept}))
    assert post_auth(web, canal="MAL NOMBRE", canal_modo="nuevo").status_code == 303
    assert "target_channel" not in bodies[0]


def test_the_form_offers_two_clear_channel_options() -> None:
    text = make_client(pilot_api()).get(URL).text
    assert 'name="canal_modo" value="nuevo"' in text
    assert 'name="canal_modo" value="existente"' in text


# --- M11 --------------------------------------------------------------------------------------
@pytest.mark.parametrize(("raw", "rounded"), [(2.675, 2.68), (0.125, 0.13)])
def test_budget_totals_round_half_up(raw: float, rounded: float) -> None:
    dossier = {"budget": {"totals": {"low": raw, "likely": raw, "high": raw}}}
    body = budget_body(dossier, 3, ID)
    assert body is not None and Decimal(str(body["likely"])) == Decimal(str(rounded))


def test_the_csrf_refusal_in_niches_skips_the_radar_badge() -> None:
    api = Api({STATUS: (200, {"radar_paused": True})})
    web = make_client(api)
    api.calls.clear()
    response = web.post("/nichos/decidir", data={"csrf": "bad", "etiqueta": "x"})
    assert response.status_code == 403 and api.calls == []
