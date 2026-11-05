# tests/test_web_pilot_authorize.py
import html
import json
import re
from typing import Any

import httpx
import pytest

from nicheradar.web.pilots_form import PILOT_ID_RE, budget_body, busy_channels, parse_form
from tests.web_helpers import (
    HOSTILE,
    Api,
    csrf_of,
    dossier_v1,
    dossier_v2,
    dossier_v3,
    make_client,
    pilot_item,
    report_detail,
)

ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
GET = ("GET", f"/api/v1/flow-research/{ID}")
PILOTS = ("GET", "/api/v1/pilots")
AUTH = ("POST", "/api/v1/pilots")
STATUS = ("GET", "/api/v1/status")
URL = f"/pilotos/autorizar?informe={ID}"
CREATED = {"pilot_id": "pil_20261102_historia", "status": "autorizado", "package": {}}
ESCAPED = html.escape(HOSTILE)


def api_with(
    detail: dict[str, Any] | None = None,
    pilots: list[dict[str, object]] | None = None,
    extra: dict[tuple[str, str], Any] | None = None,
) -> Api:
    routes: dict[tuple[str, str], Any] = {
        GET: (200, detail or report_detail(dossier=dossier_v3())),
        PILOTS: (200, {"items": pilots or []}),
        STATUS: (200, {"radar_paused": True}),
    }
    routes.update(extra or {})
    return Api(routes)


def block(text: str, element_id: str) -> str:
    found = re.search(rf"<(\w+)[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>(.*?)</\1>", text, re.S)
    assert found, f"no #{element_id} in the page"
    return found.group(2)


def post(web: Any, token: str, **over: str) -> Any:
    data = {
        "csrf": token,
        "informe": ID,
        "max_videos": "10",
        "valid_days": "14",
        "close_after": "2",
        "canal": "",
    }
    return web.post("/pilotos/autorizar", data=data | over)


def recorder(bodies: list[dict[str, Any]], status: int = 201, body: Any = CREATED) -> Any:
    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(status, json=body)

    return accept


def boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def test_busy_channels_ignore_closed_and_cancelled_pilots() -> None:
    items = [
        pilot_item(target_channel="canal-a", status="en_ejecucion"),
        pilot_item(target_channel="canal-b", status="cerrado"),
        pilot_item(target_channel="canal-c", status="cancelado"),
        pilot_item(target_channel=None, status="autorizado"),
    ]
    assert busy_channels(items) == {"canal-a"}


def test_parse_form_enforces_the_api_ranges_and_reports_field_errors() -> None:
    good = {"max_videos": "10", "valid_days": "14", "close_after": "2", "canal": ""}
    ok, errors = parse_form(good)
    assert errors == {}
    assert ok == {"max_videos": 10, "valid_days": 14, "close_after": 2, "canal": None}
    ok, errors = parse_form(good | {"canal": "canal-nuevo", "max_videos": "50", "close_after": "5"})
    assert errors == {} and ok is not None and ok["canal"] == "canal-nuevo"
    for field, bad in (
        ("max_videos", "0"),
        ("max_videos", "51"),
        ("valid_days", "0"),
        ("valid_days", "61"),
        ("close_after", "0"),
        ("close_after", "6"),
        ("max_videos", "x"),
        ("max_videos", ""),
        ("max_videos", "1.5"),
        ("canal", "Canal Uno"),
        ("canal", "canal-" + "a" * 41),
        ("canal", "canal-o\nk"),
    ):
        ok, errors = parse_form(good | {field: bad})
        assert ok is None and set(errors) == {field}, (field, bad)
    assert parse_form(good | {"max_videos": "0"})[1]["max_videos"] == "1 a 50"
    assert parse_form(good | {"valid_days": "0"})[1]["valid_days"] == "1 a 60"
    assert parse_form(good | {"close_after": "0"})[1]["close_after"] == "1 a 5"
    assert parse_form(good | {"canal": "X"})[1]["canal"] == "Usa el formato canal-nombre"


def test_pilot_id_regex_is_anchored_for_fullmatch() -> None:
    assert PILOT_ID_RE.fullmatch("pil_20261102_historia-1")
    assert not PILOT_ID_RE.fullmatch("pil_٢٠٢٦١١٠٢_x")
    assert not PILOT_ID_RE.fullmatch("pil_20261102_" + "a" * 41)
    assert PILOT_ID_RE.fullmatch("pil_20261102_" + "a" * 40)
    assert not PILOT_ID_RE.fullmatch("pil_20261102_x\n")
    assert not PILOT_ID_RE.fullmatch("pil_2026_x")


def test_budget_body_rounds_money_to_two_decimals_and_keeps_order() -> None:
    dossier = dossier_v3()
    dossier["budget"]["totals"] = {"low": 2.994, "likely": 9.294, "high": 40.999}
    body = budget_body(dossier, 10, ID)
    assert body is not None
    assert (body["low"], body["likely"], body["high"]) == (2.99, 9.29, 41.0)
    assert body["currency"] == "USD" and body["max_videos"] == 10
    assert body["basis"] == f"Presupuesto del informe {ID}: probable US$ 9,29."


def test_budget_body_accepts_strings_and_repairs_order_after_rounding() -> None:
    dossier = dossier_v3()
    dossier["budget"]["totals"] = {"low": "5.006", "likely": "5.004", "high": "5.001"}
    body = budget_body(dossier, 3, ID)
    assert body is not None
    assert (body["low"], body["likely"], body["high"]) == (5.01, 5.01, 5.01)


@pytest.mark.parametrize(
    "totals",
    [
        None,
        {},
        {"low": 1, "likely": 2},
        {"low": "x", "likely": 2, "high": 3},
        {"low": -1, "likely": 2, "high": 3},
        {"low": 1, "likely": 2, "high": 1000001},
        {"low": True, "likely": 2, "high": 3},
        {"low": float("nan"), "likely": 2, "high": 3},
    ],
)
def test_budget_body_is_none_when_the_dossier_has_no_usable_budget(totals: object) -> None:
    dossier = dossier_v3()
    dossier["budget"]["totals"] = totals
    assert budget_body(dossier, 10, ID) is None
    del dossier["budget"]
    assert budget_body(dossier, 10, ID) is None


def test_the_form_shows_what_is_fixed_the_budget_and_the_time_summary() -> None:
    text = make_client(api_with()).get(URL).text
    assert "Antes de lanzar, fija las reglas" in text
    assert "Lo que fijes aquí no cambia después." in text
    form = block(text, "autorizar")
    for name, value in (("max_videos", "10"), ("valid_days", "14"), ("close_after", "2")):
        assert f'name="{name}" ' in form and f'value="{value}"' in form
    assert 'method="post" action="/pilotos/autorizar" id="autorizar"' in text
    assert 'name="csrf"' in form
    assert f'name="informe" value="{ID}"' in form
    assert "Idioma (fijado en la investigación)" in text and "Inglés" in block(text, "idioma")
    assert "Presupuesto del informe (tope: 10 videos)" in block(text, "presupuesto")
    assert "Tu tiempo" in block(text, "tiempo")
    assert "Minutos por video" in block(text, "compuertas")
    assert "Reglas de parada" in text
    assert "Se usan las reglas por defecto del formato" in block(text, "reglas")
    assert "Cadencia" not in text and "Preparación (días)" not in text
    assert "Receta del método" not in text
    assert "historia militar explicada · Nicho · Largo" in " ".join(block(text, "nicho").split())
    assert 'href="/informes/' + ID + '"' in text and ">Cancelar<" in text
    assert text.count(">Autorizar piloto<") == 1


def test_a_busy_channel_is_listed_as_taken_and_cannot_be_chosen() -> None:
    api = api_with(pilots=[pilot_item(target_channel="canal-historias", status="en_ejecucion")])
    text = make_client(api).get(URL).text
    channels = block(text, "canal")
    assert 'value="canal-historias"' not in channels  # listed, but not offered as a radio
    assert "canal-historias" in channels and "Ocupado: ya tiene un piloto activo" in channels
    assert "Canal nuevo (sin nombre todavía" in channels
    free = make_client(api_with(pilots=[pilot_item(status="cerrado")])).get(URL).text
    assert "Ocupado" not in free and "disabled" not in block(free, "canal")


def test_a_full_pilot_list_warns_that_older_pilots_may_be_hidden() -> None:
    items = [pilot_item(f"pil_20261102_p{i}", target_channel=None) for i in range(100)]
    api = api_with(pilots=items)
    text = make_client(api).get(URL).text
    assert "Puede haber pilotos más antiguos que no se muestran" in text
    request = next(c for c in api.calls if c.url.path == PILOTS[1])
    assert request.url.params["limit"] == "100"
    few = make_client(api_with(pilots=items[:99])).get(URL).text
    assert "Puede haber pilotos más antiguos" not in few


def subniche_detail(**evidence: Any) -> dict[str, Any]:
    detail = report_detail(
        dossier=dossier_v3(niche_label="subniche:prehistoric_creatures"),
        niche_label="subniche:prehistoric_creatures",
    )
    detail["evidence"]["source"] = "subniche"
    detail["evidence"]["measurement"] = {"measured_at": "2026-10-31T12:00:00Z"}
    detail["evidence"]["gate"] = {"max_human_minutes": 60, "max_calibration_hours": 40}
    detail["evidence"].update(evidence)
    return detail


def test_a_subniche_report_shows_the_single_evidence_card_and_the_subniche_mark() -> None:
    detail = subniche_detail(subniche={"label": "Prehistoric Creatures Real"})
    text = make_client(api_with(detail)).get(URL).text
    card = " ".join(block(text, "nicho").split())
    assert "Prehistoric Creatures Real · Subnicho · Largo" in card
    evidence = " ".join(block(text, "evidencia").split())
    assert "Evidencia" in text and "Subnicho:" in evidence
    assert "viene de la medición de YouTube del 31/10/2026" in evidence
    assert "con confianza Media" in evidence
    assert (
        "no hay puntajes, así que esa compuerta no aplica (sí las de tiempo y derechos)" in evidence
    )
    assert "Opportunity" not in evidence
    assert text.count('id="evidencia"') == 1 and "evidencia-subnicho" not in text


def test_a_niche_report_shows_the_niche_branch_without_the_subniche_mark() -> None:
    text = make_client(api_with()).get(URL).text
    evidence = " ".join(block(text, "evidencia").split())
    assert (
        "vienen las fichas verificadas, y se aplican las compuertas de Opportunity y de "
        "automatización, además de las de tiempo y derechos" in evidence
    )
    assert "medición de YouTube" not in evidence
    assert "Subnicho" not in block(text, "nicho")


def test_the_title_uses_the_real_subniche_name_and_falls_back_to_the_slug() -> None:
    named = make_client(api_with(subniche_detail(subniche={"label": "Criaturas del Jurásico"})))
    assert "Criaturas del Jurásico" in block(named.get(URL).text, "nicho")
    slug = make_client(api_with(subniche_detail())).get(URL).text
    assert "Prehistoric Creatures · Subnicho · Largo" in " ".join(block(slug, "nicho").split())


def test_hostile_names_are_escaped_in_the_nicho_card() -> None:
    text = make_client(api_with(subniche_detail(subniche={"label": HOSTILE}))).get(URL).text
    assert HOSTILE not in text and ESCAPED in block(text, "nicho")


def test_your_time_card_matches_the_report_labels_without_bars() -> None:
    text = make_client(api_with()).get(URL).text
    card = " ".join(block(text, "tiempo").split())
    assert "Tu tiempo" in card and "(calibración)" in card
    assert "Preparación del canal (una vez)" in card
    assert "Cuando ya está en marcha (régimen)" in card
    assert "min por video" in card and " h<" in block(text, "tiempo") + "<"
    assert 'class="bar' not in block(text, "tiempo") and "legend" not in block(text, "tiempo")
    assert "Cuánto tarda cada video" not in text


@pytest.mark.parametrize("old", [dossier_v2, lambda: dossier_v1()])
def test_old_dossiers_show_no_calibration_time_and_do_not_crash(old: Any) -> None:
    web = make_client(api_with(report_detail(dossier=old())))
    page = web.get(URL)
    assert page.status_code == 200
    assert "(calibración)" not in block(page.text, "tiempo")
    assert "Cuando ya está en marcha (régimen)" in block(page.text, "tiempo")


def test_the_default_stop_rules_are_shown_as_read_only_text_for_long() -> None:
    text = make_client(api_with()).get(URL).text
    rules = " ".join(block(text, "reglas").split())
    assert "Retención ≥ 18 % en 3 de los primeros 10 videos" in rules
    assert "Exploración ≥ 30 % al video 20" in rules
    assert "Ingresos ≥ costos al mes 6" in rules
    assert rules.count("se compara sola") == 3 and "la juzgas tú" in rules
    assert "<input" not in block(text, "reglas")
    assert "Receta" not in text and "faceless-storytelling" not in text


def test_shorts_show_only_the_shorts_default_rules() -> None:
    text = make_client(api_with(report_detail(dossier=dossier_v3(), format="shorts"))).get(URL).text
    rules = " ".join(block(text, "reglas").split())
    assert "Ingresos ≥ costos al mes 6" in rules
    assert "Retención" not in rules and "Exploración" not in rules


def test_the_post_body_is_unchanged_and_carries_neither_rules_nor_recipe() -> None:
    bodies: list[dict[str, Any]] = []
    api = api_with(extra={AUTH: recorder(bodies)})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, token, stop_rules="x", recipe="y", cadencia="3").status_code == 303
    (body,) = bodies
    assert "stop_rules" not in body and "recipe" not in body and "cadence" not in body
    form = block(web.get(URL).text, "autorizar")
    assert 'name="stop_rules"' not in form and 'name="recipe"' not in form


def test_the_gate_acceptance_note_explains_the_explicit_acceptance() -> None:
    text = make_client(api_with()).get(URL).text
    assert "se pide aceptarlo de forma explícita y queda registrado en el piloto" in text


def test_the_language_caption_explains_how_to_change_it() -> None:
    text = make_client(api_with()).get(URL).text
    assert "Para otro idioma, una investigación nueva." in block(text, "idioma")
    sub = make_client(api_with(subniche_detail())).get(URL).text
    assert "Es el idioma de la hipótesis." in block(sub, "idioma")


def test_only_finished_reports_can_be_authorized_and_ids_are_validated() -> None:
    web = make_client(api_with(report_detail("en_curso")))
    page = web.get(URL)
    assert page.status_code == 409 and "El informe todavía no está listo" in page.text
    assert web.get("/pilotos/autorizar").status_code == 404
    assert web.get("/pilotos/autorizar?informe=../x").status_code == 404
    assert web.get(URL + "%0A").status_code == 404
    gone = make_client(Api({GET: (404, {"detail": "x"}), STATUS: (200, {"radar_paused": True})}))
    assert gone.get(URL).status_code == 404


def test_a_report_without_a_usable_budget_is_a_clear_error_not_a_500() -> None:
    dossier = dossier_v3()
    del dossier["budget"]
    api = api_with(extra={AUTH: (201, CREATED)})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    api.routes[GET] = (200, report_detail(dossier=dossier))
    page = web.get(URL)
    assert page.status_code == 422 and "no trae un presupuesto" in page.text
    response = post(web, token)
    assert response.status_code == 422 and "no trae un presupuesto" in response.text
    assert api.count(*AUTH) == 0


def test_the_no_go_and_failed_gate_checkboxes_appear_only_when_needed() -> None:
    clean = make_client(api_with()).get(URL).text
    assert 'name="accept_no_go"' not in clean and 'name="accept_gate_failure"' not in clean
    dossier = dossier_v3()
    dossier["verdict"]["recommendation"] = "no_go"
    nogo = make_client(api_with(report_detail(dossier=dossier))).get(URL).text
    assert 'name="accept_no_go"' in nogo and 'name="accept_gate_failure"' not in nogo
    assert "Acepto lanzarlo aunque" in nogo
    failing = report_detail(dossier=dossier_v3())
    failing["evidence"]["gate"]["passed"] = False
    failed = make_client(api_with(failing)).get(URL).text
    assert 'name="accept_gate_failure"' in failed and 'name="accept_no_go"' not in failed


def test_a_failing_computed_gate_row_also_needs_the_gate_checkbox() -> None:
    dossier = dossier_v3()
    for step in dossier["production_flow"]:
        step["human_minutes_per_video"] = 500
    text = make_client(api_with(report_detail(dossier=dossier))).get(URL).text
    assert "no pasa" in block(text, "compuertas")
    assert 'name="accept_gate_failure"' in text


def test_authorizing_posts_server_derived_fields_and_redirects_to_the_pilot_panel() -> None:
    bodies: list[dict[str, Any]] = []
    api = api_with(extra={AUTH: recorder(bodies)})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(
        web, token, niche_label="OTRA", format="shorts", authorized_by="otro", canal="canal-nuevo"
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/pilotos/pil_20261102_historia?aviso=autorizado"
    (body,) = bodies
    assert body["niche_label"] == "historia militar explicada" and body["format"] == "long"
    assert body["dossier_request_id"] == ID and body["authorized_by"] == "propietario (web)"
    assert body["budget"]["max_videos"] == 10 and body["budget"]["currency"] == "USD"
    totals = dossier_v3()["budget"]["totals"]
    assert body["budget"]["likely"] == round(float(totals["likely"]), 2)
    assert body["valid_days"] == 14 and body["close_after_failed_milestones"] == 2
    assert body["target_channel"] == "canal-nuevo"
    assert body["accept_no_go"] is False and body["accept_gate_failure"] is False
    assert set(body) == {
        "niche_label",
        "format",
        "dossier_request_id",
        "budget",
        "authorized_by",
        "close_after_failed_milestones",
        "valid_days",
        "accept_no_go",
        "accept_gate_failure",
        "target_channel",
    }


@pytest.mark.parametrize(
    "bad_id",
    [
        "x\nSet-Cookie: a=b",
        "pil_20261102_x\n",
        "../pilots",
        "",
        None,
        7,
        "pil_1_x",
        "pil_٢٠٢٦١١٠٢_x",
        "pil_20261102_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "pil_20261102_a_b",
    ],
)
def test_the_success_redirect_drops_a_malformed_pilot_id(bad_id: object) -> None:
    bad = {"pilot_id": bad_id, "status": "autorizado", "package": {}}
    web = make_client(api_with(extra={AUTH: (201, bad)}))
    response = post(web, csrf_of(web.get(URL).text))
    assert response.status_code == 303
    assert response.headers["location"] == f"/informes/{ID}?aviso=piloto"


def test_an_empty_channel_means_a_new_channel_and_omits_target_channel() -> None:
    bodies: list[dict[str, Any]] = []
    web = make_client(api_with(extra={AUTH: recorder(bodies)}))
    post(web, csrf_of(web.get(URL).text))
    assert len(bodies) == 1 and "target_channel" not in bodies[0]


def test_a_bad_csrf_or_out_of_range_value_never_reaches_the_api() -> None:
    api = api_with(extra={AUTH: (201, CREATED)})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, "wrong").status_code == 403
    assert web.post("/pilotos/autorizar").status_code == 403
    assert post(web, token, informe="nope").status_code == 404
    assert post(web, token, informe=ID + "\n").status_code == 404
    for field, bad in (
        ("max_videos", "99"),
        ("valid_days", "0"),
        ("close_after", "9"),
        ("canal", "NO válido"),
    ):
        assert post(web, token, **{field: bad}).status_code == 422, (field, bad)
    assert api.count(*AUTH) == 0
    # a bad token must not even fetch the report
    fresh = api_with(extra={AUTH: (201, CREATED)})
    other = make_client(fresh)
    assert post(other, "wrong").status_code == 403
    assert fresh.count(*GET) == 0 and fresh.count(*AUTH) == 0


def test_a_posted_busy_channel_is_rejected_before_calling_the_api() -> None:
    api = api_with(
        pilots=[pilot_item(target_channel="canal-historias", status="entregado")],
        extra={AUTH: (201, CREATED)},
    )
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token, canal="canal-historias")
    assert response.status_code == 409 and "Ese canal ya tiene un piloto activo." in response.text
    assert 'value="canal-historias"' in response.text
    assert api.count(*AUTH) == 0


def test_the_form_keeps_what_was_typed_when_validation_fails() -> None:
    web = make_client(api_with())
    token = csrf_of(web.get(URL).text)
    page = post(web, token, max_videos="99", valid_days="21", canal="canal-mio")
    assert page.status_code == 422
    form = block(page.text, "autorizar")
    assert re.search(r'name="max_videos"[^>]*value="99"', form)
    assert re.search(r'name="valid_days"[^>]*value="21"', form)
    assert 'value="canal-mio"' in form
    assert "1 a 50" in block(form, "error-max_videos")
    assert "error-valid_days" not in form


def test_the_form_keeps_the_typed_values_escaped() -> None:
    web = make_client(api_with())
    token = csrf_of(web.get(URL).text)
    page = post(web, token, canal=HOSTILE, max_videos="<b>")
    assert page.status_code == 422
    assert "<script>alert(1)</script>" not in page.text and "<b>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


@pytest.mark.parametrize(
    ("code", "needle"),
    [
        ("channel_busy", "Ese canal ya tiene un piloto activo."),
        ("no_go_requires_acceptance", "El informe recomienda no-go"),
        ("dossier_not_ready", "El informe todavía no está listo."),
        ("language_unknown", "El informe no tiene un idioma conocido"),
        ("niche_mismatch", "El informe no corresponde a ese nicho."),
        ("gate_failed", "El informe no pasa una compuerta"),
        ("bad_transition", "ya no se puede reemplazar"),
    ],
)
def test_api_conflicts_map_to_clear_messages_and_keep_the_form(code: str, needle: str) -> None:
    web = make_client(api_with(extra={AUTH: (409, {"detail": {"code": code, "message": "x"}})}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token, valid_days="30")
    assert response.status_code == 409
    assert needle in block(response.text, "error")
    assert re.search(r'name="valid_days"[^>]*value="30"', response.text)


def test_an_unknown_conflict_code_falls_back_to_the_api_message() -> None:
    detail = {"code": "otra", "message": "Mensaje de la API."}
    web = make_client(api_with(extra={AUTH: (409, {"detail": detail})}))
    response = post(web, csrf_of(web.get(URL).text))
    assert response.status_code == 409 and "Mensaje de la API." in block(response.text, "error")


def test_a_failed_acceptance_shows_the_matching_checkbox_on_the_retry() -> None:
    nogo = {"detail": {"code": "no_go_requires_acceptance", "message": "x"}}
    web = make_client(api_with(extra={AUTH: (409, nogo)}))
    page = post(web, csrf_of(web.get(URL).text))
    assert 'name="accept_no_go"' in page.text and 'name="accept_gate_failure"' not in page.text
    gate = {"detail": {"code": "gate_failed", "message": "x", "reasons": []}}
    web = make_client(api_with(extra={AUTH: (409, gate)}))
    page = post(web, csrf_of(web.get(URL).text))
    assert 'name="accept_gate_failure"' in page.text and 'name="accept_no_go"' not in page.text


def test_failed_gate_reasons_from_the_api_are_listed_escaped() -> None:
    detail = {
        "code": "gate_failed",
        "message": "x",
        "reasons": [{"gate": "rights", "message": HOSTILE}],
    }
    web = make_client(api_with(extra={AUTH: (409, {"detail": detail})}))
    response = post(web, csrf_of(web.get(URL).text))
    assert response.status_code == 409
    assert f"<li>{ESCAPED}</li>" in block(response.text, "error")
    assert "<script>alert(1)</script>" not in response.text


def test_package_problems_from_a_422_are_listed_escaped() -> None:
    body = {"accepted": False, "problems": [{"path": "budget", "message": HOSTILE}]}
    web = make_client(api_with(extra={AUTH: (422, body)}))
    response = post(web, csrf_of(web.get(URL).text))
    assert response.status_code == 422
    assert f"<li>budget: {ESCAPED}</li>" in block(response.text, "error")
    assert "<script>alert(1)</script>" not in response.text


def test_the_accept_flags_are_sent_only_when_the_checkbox_is_checked() -> None:
    bodies: list[dict[str, Any]] = []
    dossier = dossier_v3()
    dossier["verdict"]["recommendation"] = "no_go"
    web = make_client(api_with(report_detail(dossier=dossier), extra={AUTH: recorder(bodies)}))
    token = csrf_of(web.get(URL).text)
    post(web, token, accept_no_go="1")
    post(web, token)
    assert bodies[0]["accept_no_go"] is True and bodies[0]["accept_gate_failure"] is False
    assert bodies[1]["accept_no_go"] is False


def test_api_outage_on_the_page_and_on_the_post() -> None:
    down = make_client(Api({GET: boom, PILOTS: (200, {"items": []}), STATUS: (200, {})}))
    page = down.get(URL)
    assert page.status_code == 503 and "API no disponible" in page.text
    web = make_client(api_with(extra={AUTH: boom}))
    page = web.get(URL)
    assert "Radar pausado" not in page.text and "Radar activo" not in page.text
    token = csrf_of(page.text)
    response = post(web, token, valid_days="9")
    assert response.status_code == 503 and "API no disponible" in block(response.text, "error")
    assert re.search(r'name="valid_days"[^>]*value="9"', response.text)
    assert (
        "Radar pausado" not in response.text and "Radar activo" not in response.text
    )  # no radar chip at all


def test_when_only_the_pilot_list_fails_the_form_still_opens_with_a_warning() -> None:
    api = Api(
        {
            GET: (200, report_detail(dossier=dossier_v3())),
            PILOTS: boom,
            STATUS: (200, {"radar_paused": True}),
        }
    )
    page = make_client(api).get(URL)
    assert page.status_code == 200
    assert "No se pudo comprobar qué canales están ocupados" in page.text


def test_a_real_niche_evidence_without_source_still_shows_the_niche_branch() -> None:
    detail = report_detail(dossier=dossier_v3())
    assert "source" not in detail["evidence"]
    text = make_client(api_with(detail)).get(URL).text
    assert text.count('id="evidencia"') == 1
    assert "vienen las fichas verificadas" in " ".join(block(text, "evidencia").split())


def test_the_origin_is_the_same_everywhere_even_with_incoherent_data() -> None:
    # niche label + source=subniche: the mark, the evidence card and the report agree
    detail = report_detail(dossier=dossier_v3())
    detail["evidence"]["source"] = "subniche"
    text = make_client(api_with(detail)).get(URL).text
    card = " ".join(block(text, "nicho").split())
    evidence = " ".join(block(text, "evidencia").split())
    assert "Subnicho" in card and "Subnicho:" in evidence
    # subniche label + source=niche: both say niche
    other = report_detail(
        dossier=dossier_v3(niche_label="subniche:prehistoric_creatures"),
        niche_label="subniche:prehistoric_creatures",
    )
    other["evidence"]["source"] = "niche"
    text = make_client(api_with(other)).get(URL).text
    assert "Subnicho" not in block(text, "nicho")
    assert "vienen las fichas verificadas" in " ".join(block(text, "evidencia").split())
    # no source, subniche label: the prefix decides
    bare = subniche_detail()
    del bare["evidence"]["source"]
    text = make_client(api_with(bare)).get(URL).text
    assert "Subnicho" in block(text, "nicho") and "Subnicho:" in block(text, "evidencia")


def test_the_gate_warning_covers_every_gate() -> None:
    text = make_client(api_with()).get(URL).text
    assert "Si una compuerta no se cumpliera" in text
    assert "Si una compuerta de tiempo o derechos" not in text


EXPECTED_RULE_TEXT = {
    "pipeline_e2e": ("Un video publicado de punta a punta a la semana", "se compara sola"),
    "avd_pct": ("Retención ≥", "se compara sola"),
    "browse_share_pct": ("Exploración ≥", "se compara sola"),
    "revenue_vs_cost": ("Ingresos ≥ costos al mes", "la juzgas tú"),
}


@pytest.mark.parametrize("fmt", ["long", "shorts"])
def test_every_default_stop_rule_has_its_expected_text_and_judge(fmt: str) -> None:
    from nicheradar.pilots.service import default_stop_rules
    from nicheradar.web.pilots_form import stop_rule_lines

    rules = default_stop_rules(fmt)
    lines = stop_rule_lines(fmt)
    assert len(rules) == len(lines) > 0
    for rule, (text, judge) in zip(rules, lines, strict=True):
        start, who = EXPECTED_RULE_TEXT[rule["metric"]]
        assert text.startswith(start) and judge == who, (rule["metric"], text, judge)


def test_an_unknown_or_manual_metric_is_judged_by_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nicheradar.web import pilots_form

    rule = {"milestone": {"value": 3}, "threshold": 1, "min_cases": 1, "text": "Mira el tono"}
    monkeypatch.setattr(
        pilots_form,
        "default_stop_rules",
        lambda _f: [rule | {"metric": "manual"}, rule | {"metric": "otra_metrica"}],
    )
    assert pilots_form.stop_rule_lines("long") == [("Mira el tono", "la juzgas tú")] * 2


def test_a_measurement_date_in_year_one_never_gives_a_503() -> None:
    for page in (URL, f"/informes/{ID}"):
        detail = subniche_detail(measurement={"measured_at": "0001-01-01T00:00:00Z"})
        response = make_client(api_with(detail)).get(page)
        assert response.status_code == 200, (page, response.status_code)
