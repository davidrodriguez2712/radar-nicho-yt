# tests/test_web_report.py
import html
import re
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from nicheradar.flow_research.contracts import DossierV3, calibration_total_hours
from nicheradar.web.report import RECOMMENDATION, safe_url, subject_label
from tests.web_helpers import (
    HOSTILE,
    Api,
    csrf_of,
    dossier_v1,
    dossier_v2,
    dossier_v3,
    make_client,
    report_detail,
)

ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
GET = ("GET", f"/api/v1/flow-research/{ID}")
STATUS = ("GET", "/api/v1/status")
ESCAPED = html.escape(HOSTILE)


def api_with(detail: dict[str, Any]) -> Api:
    return Api({GET: (200, detail), STATUS: (200, {"radar_paused": True})})


def page(detail: dict[str, Any], **params: str) -> str:
    response = make_client(api_with(detail)).get(f"/informes/{ID}", params=params)
    assert response.status_code == 200, response.text
    text: str = response.text
    return text


def block(text: str, element_id: str) -> str:
    """The inner HTML of the one element with this id (no same-tag nesting in the templates)."""
    found = re.search(rf"<(\w+)[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>(.*?)</\1>", text, re.S)
    assert found, f"no #{element_id} in the page"
    return found.group(2)


def rows(section: str) -> list[tuple[str, str]]:
    pairs = re.findall(
        r'<span class="row__label">(.*?)</span>\s*<span class="row__value">(.*?)</span>',
        section,
        re.S,
    )
    return [(html.unescape(a).strip(), html.unescape(b).strip()) for a, b in pairs]


def gate_rows(section: str) -> list[tuple[str, str]]:
    pairs = re.findall(
        r'<span class="row__label">(.*?)</span>\s*<span class="chip chip--(\w+)">(.*?)</span>',
        section,
        re.S,
    )
    return [(html.unescape(a).strip(), f"{kind}:{b}") for a, kind, b in pairs]


def test_the_helper_dossiers_are_valid() -> None:
    DossierV3.model_validate(dossier_v3())
    assert dossier_v2()["schema_version"] == "dossier-v2"
    assert "rights" not in dossier_v1()


def test_safe_url_only_allows_https() -> None:
    assert safe_url("https://example.com/a") == "https://example.com/a"
    bad = (
        "http://x.test",
        "javascript:alert(1)",
        "//x.test",
        "data:text/html,x",
        "",
        None,
        5,
        "https://x.test/a b",
        "https://x.test/\n",
        "https://x.test/\x00",
        " https://x.test",
    )
    for value in bad:
        assert safe_url(value) is None


def test_subject_label_humanizes_subniches_only() -> None:
    assert subject_label("subniche:prehistoric_creatures") == ("Prehistoric Creatures", True)
    assert subject_label("historia militar explicada") == ("historia militar explicada", False)


def test_a_v3_report_shows_verdict_and_thesis() -> None:
    dossier = dossier_v3()
    text = page(report_detail(dossier=dossier))
    assert block(text, "eyebrow").strip() == "Informe · Listo"
    expected = RECOMMENDATION["go_with_conditions"][0]
    assert block(text, "titulo").strip() == f"historia militar explicada: {expected}"
    assert block(text, "tesis").strip() == dossier["verdict"]["thesis"]
    assert 'class="chip chip--amber">Recomendación: sí, con condiciones<' in block(
        text, "veredicto"
    )
    assert ("Confianza del informe", "Media") in rows(block(text, "veredicto"))


def test_time_rows_come_from_the_domain_helper() -> None:
    dossier = dossier_v3()
    model = DossierV3.model_validate(dossier)
    calibration = dossier["calibration"]
    per_video = sum(item["minutes_per_video"] for item in calibration["minutes_by_step"])
    total = calibration_total_hours(calibration["setup_hours"], calibration["videos"], per_video)
    assert total == model.calibration_hours
    expected_total = f"{total:g}".replace(".", ",")  # 17,5
    time = rows(block(page(report_detail(dossier=dossier)), "tiempo"))
    assert time == [
        ("Tu tiempo por video", f"{per_video} min"),
        ("Total de los 6 videos", "9,5 h"),
        ("Preparación del canal (una vez)", "8 h"),
        ("Horas de calibración", f"{expected_total} h"),
        ("Tu tiempo por video", f"{model.human_minutes_per_video} min"),
    ]


STEPS = ("Guion", "Voz", "Visuales", "Edición", "Publicación")


def five_step_dossier(
    calibration: Sequence[Any] = (20, 10, 30, 25, 10), regime: Sequence[Any] = (10, 2, 4, 2, 2)
) -> dict[str, Any]:
    dossier = dossier_v3()
    template = dossier["production_flow"][0]
    dossier["production_flow"] = [
        {**template, "order": i + 1, "name": name, "human_minutes_per_video": minutes}
        for i, (name, minutes) in enumerate(zip(STEPS, regime, strict=True))
    ]
    dossier["calibration"]["minutes_by_step"] = [
        {"step": name, "minutes_per_video": minutes}
        for name, minutes in zip(STEPS, calibration, strict=True)
    ]
    return dossier


def segments(section: str) -> list[list[tuple[str, int]]]:
    """For each bar: its (colour class, width in %) per segment, in order."""
    result = []
    pattern = r'<div class="bar"[^>]*>((?:<div class="bar__seg[^"]*"></div>\s*)*)</div>'
    for bar in re.findall(pattern, section):
        found = re.findall(r'class="bar__seg bar__seg--(c\d) bar--p(\d+)"', bar)
        result.append([(colour, int(width)) for colour, width in found])
    return result


def test_the_time_card_has_two_bars_with_five_steps_the_same_colours_and_one_scale() -> None:
    section = block(page(report_detail(dossier=five_step_dossier())), "tiempo")
    assert [label for label, _ in rows(section)] == [
        "Tu tiempo por video",
        "Total de los 6 videos",
        "Preparación del canal (una vez)",
        "Horas de calibración",
        "Tu tiempo por video",
    ]
    assert "Primeros 6 videos (calibración)" in section
    assert "Cuando ya está en marcha (régimen)" in section
    calibration, regime = segments(section)
    colours = ["c0", "c1", "c2", "c3", "c4"]
    assert [c for c, _ in calibration] == colours and [c for c, _ in regime] == colours
    assert calibration == [("c0", 20), ("c1", 10), ("c2", 35), ("c3", 25), ("c4", 10)]
    assert sum(w for _, w in calibration) == 100  # the longest row takes the whole scale
    assert regime == [("c0", 10), ("c1", 5), ("c2", 5), ("c3", 5), ("c4", 5)]
    assert sum(w for _, w in regime) < sum(w for _, w in calibration)
    for name in STEPS:
        assert name in section
    assert "mismos colores en las dos barras, a la misma escala" in section
    assert "style" not in section


def test_invalid_step_minutes_leave_an_empty_bar_and_say_sin_dato() -> None:
    dossier = five_step_dossier(calibration=[None, -5, "x", None, True])
    section = block(page(report_detail(dossier=dossier)), "tiempo")
    calibration, regime = segments(section)
    assert all(width == 0 for _, width in calibration)
    assert ("Tu tiempo por video", "sin dato") in rows(section)
    assert sum(w for _, w in regime) == 100  # the only bar with data fills the scale
    mixed = five_step_dossier(calibration=[20, -10, 30, None, 10])
    only_valid = segments(block(page(report_detail(dossier=mixed)), "tiempo"))[0]
    assert [w for _, w in only_valid][1] == 0 and [w for _, w in only_valid][3] == 0


@pytest.mark.parametrize(
    "calibration",
    [None, "texto", [], {"videos": "x"}, {"videos": 6, "setup_hours": 8, "minutes_by_step": "x"}],
)
def test_a_v3_dossier_with_an_unusable_calibration_shows_no_bars_and_never_breaks(
    calibration: Any,
) -> None:
    dossier = dossier_v3()
    if calibration is None:
        del dossier["calibration"]
    else:
        dossier["calibration"] = calibration
    text = page(report_detail(dossier=dossier))
    assert "bar__seg" not in text and 'id="regimen"' not in text
    assert "Cuándo pasas a régimen" not in text
    assert "Dossier anterior" not in block(text, "aviso-dossier")
    assert "no trae la calibración completa" in block(text, "aviso-dossier")
    assert dict(rows(block(text, "tiempo"))) == {
        "Cuando ya está en marcha (régimen)": "55 min por video"
    }


def test_the_report_title_of_a_subniche_uses_the_real_name_of_the_hypothesis() -> None:
    def detail(evidence: dict[str, Any]) -> dict[str, Any]:
        return report_detail(
            dossier=dossier_v3(), niche_label="subniche:prehistoric_creatures", evidence=evidence
        )

    named = {
        "source": "subniche",
        "subniche": {"label": "Criaturas prehistóricas: la era del hielo"},
    }
    assert block(page(detail(named)), "titulo").strip() == (
        "Criaturas prehistóricas: la era del hielo: sí, con condiciones"
    )
    for evidence in ({}, {"source": "subniche", "subniche": {"label": 7}}, {"subniche": "x"}):
        assert block(page(detail(evidence)), "titulo").strip() == (
            "Prehistoric Creatures: sí, con condiciones"
        )
    hostile = {"source": "subniche", "subniche": {"label": HOSTILE}}
    text = page(detail(hostile))
    assert ESCAPED in block(text, "titulo") and HOSTILE not in text


def test_a_niche_report_keeps_the_label_of_the_niche_as_title() -> None:
    evidence = {"subniche": {"label": "No debe usarse"}, "source": "niche"}
    text = page(report_detail(dossier=dossier_v3(), evidence=evidence))
    assert block(text, "titulo").strip() == "historia militar explicada: sí, con condiciones"


def test_the_firm_card_counts_the_measured_channels_with_their_date() -> None:
    def firm(measurement: object) -> str:
        detail = report_detail(
            dossier=dossier_v3(),
            niche_label="subniche:prehistoric_creatures",
            evidence={"source": "subniche", "confidence": "media", "measurement": measurement},
        )
        return block(page(detail), "firme")

    assert "29 canales medidos el 31/10/2026" in firm(
        {"measured_at": "2026-10-31T12:00:00Z", "included": 29}
    )
    assert "canales medidos" not in firm({"measured_at": "2026-10-31T12:00:00Z"})
    for bad in (True, "7", -1, 2.5, None):
        assert "canales medidos" not in firm(
            {"measured_at": "2026-10-31T12:00:00Z", "included": bad}
        )
    assert "1 canal medido el 31/10/2026" in firm(
        {"measured_at": "2026-10-31T12:00:00Z", "included": 1}
    )
    assert "canales medidos" not in firm("texto")
    assert "canales medidos" not in block(page(report_detail(dossier=dossier_v3())), "firme")


def test_the_regime_section_states_exit_criterion_and_evidence() -> None:
    dossier = dossier_v3()
    section = block(page(report_detail(dossier=dossier)), "regimen")
    assert dossier["calibration"]["exit_criterion"]["statement"] in section
    assert "Medido en canal-historias: 10 videos" in section
    assert dossier["steady_state_evidence"]["format_match"] in section


@pytest.mark.parametrize(
    ("basis", "expected"),
    [("mapped_flow_equivalent", "Equivalente a un flujo ya mapeado"), ("estimate", "Estimación")],
)
def test_null_steady_state_fields_do_not_break_the_report(basis: str, expected: str) -> None:
    dossier = dossier_v3()
    dossier["steady_state_evidence"] = {
        "basis": basis,
        "reference_channel": None,
        "reference_minutes_per_video": None,
        "reference_sample_videos": None,
        "format_match": None,
    }
    section = block(page(report_detail(dossier=dossier)), "regimen")
    assert expected in section
    assert "None" not in section


def test_gate_rows_pass_and_fail_with_their_limits() -> None:
    detail = report_detail(dossier=dossier_v3())
    assert gate_rows(block(page(detail), "compuertas")) == [
        ("Minutos por video, ya en marcha: 55 de 60 permitidos", "green:pasa"),
        ("Horas de calibración: 17,5 de 40 permitidas", "green:pasa"),
        ("Derechos del material: resueltos", "green:pasa"),
    ]
    detail["evidence"]["gate"]["max_human_minutes"] = 54  # 55 > 54 fails; 55 <= 55 would pass
    detail["evidence"]["gate"]["max_calibration_hours"] = 10
    detail["dossier"]["rights"]["verdict"] = "blocked"
    assert gate_rows(block(page(detail), "compuertas")) == [
        ("Minutos por video, ya en marcha: 55 de 54 permitidos", "rose:no pasa"),
        ("Horas de calibración: 17,5 de 10 permitidas", "rose:no pasa"),
        ("Derechos del material: bloqueados", "rose:no pasa"),
    ]


def test_the_limit_itself_passes_and_conditional_rights_pass_with_a_note() -> None:
    detail = report_detail(dossier=dossier_v3())
    detail["evidence"]["gate"]["max_human_minutes"] = 55
    detail["dossier"]["rights"]["verdict"] = "conditional"
    rows_ = gate_rows(block(page(detail), "compuertas"))
    assert rows_[0] == ("Minutos por video, ya en marcha: 55 de 55 permitidos", "green:pasa")
    assert rows_[2] == ("Derechos del material: con condiciones", "green:pasa")


def test_old_dossiers_open_with_the_notice_and_only_the_gates_they_support() -> None:
    for old, rights_row in (
        (dossier_v2(), ("Derechos del material: resueltos", "green:pasa")),
        (dossier_v1(), ("Derechos del material: sin evaluar", "neutral:sin evaluar")),
        ({**dossier_v2(), "schema_version": "dossier-v9"}, None),
    ):
        text = page(report_detail(dossier=old))
        notice = block(text, "aviso-dossier")
        assert "Dossier anterior: no separa calibración de régimen." in notice
        assert 'id="regimen"' not in text and "bar__seg" not in text
        assert "Cuándo pasas a régimen" not in text
        assert dict(rows(block(text, "tiempo"))) == {
            "Cuando ya está en marcha (régimen)": "55 min por video"
        }
        gates = gate_rows(block(text, "compuertas"))
        assert gates[0] == ("Minutos por video, ya en marcha: 55 de 60 permitidos", "green:pasa")
        assert all("Horas de calibración" not in label for label, _ in gates)
        if rights_row:
            assert gates[-1] == rights_row
    assert 'id="aviso-dossier"' not in page(report_detail(dossier=dossier_v3()))


def test_budget_shows_three_scenarios_and_tolerates_string_money() -> None:
    section = block(page(report_detail(dossier=dossier_v3())), "gasto")
    assert rows(section) == [
        ("Bajo", "US$ 100"),
        ("Probable", "US$ 133"),
        ("Peor caso (tope)", "US$ 180"),
    ]
    assert "Cifras del informe; no incluyen tu tiempo." in section
    odd = dossier_v3()
    odd["budget"]["totals"] = {"low": "100.00", "likely": "oops", "high": None}
    assert rows(block(page(report_detail(dossier=odd)), "gasto")) == [
        ("Bajo", "US$ 100"),
        ("Probable", "—"),
        ("Peor caso (tope)", "—"),
    ]


def test_detail_accordions_count_their_contents() -> None:
    dossier = dossier_v3()
    text = page(report_detail(dossier=dossier))
    assert "Detalle (toca para abrir)" in text
    assert "3 herramientas" in block(text, "acc-herramientas")
    assert "Editor de video" in block(text, "acc-herramientas")
    risks = dossier["verdict"]["main_risks"] + dossier["verdict"]["unknowns"]
    risks += dossier["verdict"]["conditions"] + [dossier["policy_risk"]["summary"]]
    risks += dossier["rights"]["conditions"]
    warnings = block(text, "acc-avisos")
    assert f"{len(risks)} avisos" in warnings
    assert all(html.escape(item) in warnings for item in risks)
    assert "3 canales · 3 enlaces" in block(text, "acc-fuentes")


def test_actions_launch_postpone_and_discard_for_a_backlog_niche() -> None:
    web = make_client(api_with(report_detail(dossier=dossier_v3())))
    text = web.get(f"/informes/{ID}").text
    actions = block(text, "acciones")
    assert (
        f'<a class="btn btn--primary" href="/pilotos/autorizar?informe={ID}">Lanzar piloto</a>'
        in actions
    )
    assert '<a class="btn btn--secondary" href="/nichos">Posponer</a>' in actions
    form = block(text, "descartar")
    assert 'name="csrf" value="' in form and csrf_of(form)
    assert 'name="etiqueta" value="historia militar explicada"' in form
    assert 'name="formato" value="long"' in form
    assert 'name="decision" value="descartado"' in form
    assert 'name="volver" value="/nichos"' in form
    assert re.search(r'<form[^>]*method="post"[^>]*action="/nichos/decidir"', text)
    assert ">Descartar</button>" in form


def test_a_subniche_report_has_the_confidence_notice_and_no_discard() -> None:
    detail = report_detail(
        dossier=dossier_v3(), niche_label="subniche:prehistoric_creatures", evidence={}
    )
    detail["evidence"] = {
        "source": "subniche",
        "confidence": "baja",
        "measurement": {"measured_at": "2026-10-31T12:00:00Z", "included": 7},
        "gate": report_detail()["evidence"]["gate"],
    }
    text = page(detail)
    assert block(text, "titulo").strip() == "Prehistoric Creatures: sí, con condiciones"
    firm = block(text, "firme")
    assert "Qué tan firme es" in firm
    assert rows(firm) == [("Confianza de la medición", "Baja")]
    assert "7 canales medidos el 31/10/2026" in firm
    assert "El ingreso es una estimación por canal típico." in firm
    assert "Los competidores vienen de listados de terceros, sin confirmar en YouTube." in firm
    assert 'id="descartar"' not in text and "Descartar" not in text
    assert '<a class="btn btn--secondary" href="/subnichos">Posponer</a>' in block(text, "acciones")


def test_a_backlog_report_shows_the_language_mix() -> None:
    firm = block(page(report_detail(dossier=dossier_v3())), "firme")
    assert ("Confianza de la medición", "Media") in rows(firm)
    assert ("Idioma del mercado", "Inglés 80% · Español 15% · Sin dato 5%") in rows(firm)
    assert "El ingreso es una estimación" not in firm


def test_hostile_dossier_text_is_escaped_and_unsafe_links_are_plain_text() -> None:
    dossier = dossier_v3()
    dossier["verdict"]["thesis"] = HOSTILE
    dossier["verdict"]["main_risks"] = [HOSTILE]
    dossier["competitors"][0]["name"] = HOSTILE
    dossier["competitors"][1]["channel_url"] = "javascript:alert(1)"
    dossier["sources"] = [
        {"id": "s1", "url": "javascript:alert(1)", "title": HOSTILE, "accessed_on": "2026-11-01"},
        {
            "id": "s2",
            "url": "https://ok.example/x?a=1&b=2",
            "title": "ok",
            "accessed_on": "2026-11-01",
        },
        {
            "id": "s3",
            "url": "http://plain.example",
            "title": "inseguro",
            "accessed_on": "2026-11-01",
        },
    ]
    text = page(report_detail(dossier=dossier))
    assert "<script>alert(1)</script>" not in text
    assert ESCAPED in block(text, "tesis")
    assert ESCAPED in block(text, "acc-avisos")
    sources = block(text, "acc-fuentes")
    assert sources.count(ESCAPED) == 2  # competitor name and source title
    assert 'href="javascript:' not in text and 'href="http://' not in text
    assert 'href="https://evil.test' not in text
    link = (
        'href="https://ok.example/x?a=1&amp;b=2" rel="noopener noreferrer nofollow" target="_blank"'
    )
    assert link in sources
    assert sources.count('target="_blank"') == 3  # ok.example and two safe competitor links
    assert "|safe" not in open("src/nicheradar/web/templates/informes/informe.html").read()


@pytest.mark.parametrize(
    ("status", "chip", "note"),
    [
        ("pendiente", "En cola", "espera a que Claude Code la reclame"),
        (
            "en_curso",
            "Investigando",
            "Claude Code la atiende en su sesión; el encargo se reclama 60 minutos",
        ),
    ],
)
def test_a_running_order_shows_its_state_and_no_report(status: str, chip: str, note: str) -> None:
    text = page(report_detail(status))
    assert chip in block(text, "estado")
    assert note in block(text, "estado")
    assert "Lanzar piloto" not in text and 'id="titulo"' not in text


def test_a_rejected_order_lists_the_problems_escaped() -> None:
    detail = report_detail(
        "rechazado",
        rejection={
            "problems": [{"path": "budget", "message": HOSTILE}],
            "at": "2026-11-02T03:00:00Z",
        },
    )
    text = page(detail)
    assert "Rechazada" in block(text, "estado")
    assert f"<li>budget: {ESCAPED}</li>" in text
    assert "<script>alert(1)</script>" not in text


@pytest.mark.parametrize("rejection", [None, {}, {"problems": "x"}, {"problems": [5, None]}])
def test_a_rejected_order_without_usable_problems_is_generic(rejection: object) -> None:
    text = page(report_detail("rechazado", rejection=rejection))
    assert "Rechazada" in block(text, "estado") and "<li>" not in text


def test_a_listo_order_without_a_dossier_is_handled() -> None:
    text = page(report_detail("listo", dossier=None))
    assert "El dossier no está disponible" in block(text, "estado")
    assert "Lanzar piloto" not in text


@pytest.mark.parametrize("dossier", [{"schema_version": "dossier-v3"}, {}, []])
def test_a_stored_dossier_with_missing_fields_never_breaks(dossier: Any) -> None:
    response = make_client(api_with(report_detail("listo", dossier=dossier))).get(f"/informes/{ID}")
    assert response.status_code == 200


def test_a_bad_id_is_a_404_and_never_reaches_the_api() -> None:
    api = api_with(report_detail(dossier=dossier_v3()))
    web = make_client(api)
    for bad in ("../x", "abc", f"{ID}/x", "%2e%2e", ID.upper(), f"{ID}%0a"):
        assert web.get(f"/informes/{bad}").status_code == 404
    assert api.count(*GET) == 0


def test_unknown_id_and_api_outage() -> None:
    gone = {"detail": {"code": "not_found", "message": "x"}}
    api = Api({GET: (404, gone), STATUS: (200, {"radar_paused": True})})
    assert make_client(api).get(f"/informes/{ID}").status_code == 404

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({GET: boom, STATUS: (200, {"radar_paused": True})})
    web = make_client(api)
    down = web.get(f"/informes/{ID}")
    assert down.status_code == 503 and "API no disponible" in down.text
    assert api.count(*STATUS) == 0  # the failed page skips the radar badge call


def test_the_notice_comes_from_fixed_keys_and_the_pilot_id_is_validated() -> None:
    detail = report_detail(dossier=dossier_v3())
    assert "Investigación creada. Claude Code la atenderá" in page(detail, aviso="creada")
    assert "Ya había una investigación activa con esa clave." in page(detail, aviso="existente")
    assert 'class="note' not in page(detail, aviso="<script>x</script>")
    ok = page(detail, aviso="piloto", piloto="pil_20261102_historia-militar")
    assert "Piloto autorizado." in ok and "pil_20261102_historia-militar" in ok
    for bad in (HOSTILE, "pil_2026_x", "pil_20261102_X", "pil_20261102_a\n"):
        text = page(detail, aviso="piloto", piloto=bad)
        assert "Piloto autorizado." in text
        assert "evil.test" not in text and "<script>" not in text and bad.strip() not in text
    assert "Piloto autorizado." in page(report_detail("pendiente"), aviso="piloto")


def test_a_report_without_the_count_still_shows_when_it_was_measured() -> None:
    detail = report_detail(
        dossier=dossier_v3(),
        niche_label="subniche:prehistoric_creatures",
        evidence={"source": "subniche", "measurement": {"measured_at": "2026-10-31T12:00:00Z"}},
    )
    assert ("Medido el", "31/10/2026 07:00") in rows(block(page(detail), "firme"))


def test_the_way_back_of_an_order_without_report_depends_on_where_it_came_from() -> None:
    niche = page(report_detail("pendiente", niche_label="historia militar explicada"))
    assert '<a href="/nichos">← Volver a Nichos</a>' in niche
    sub = page(report_detail("pendiente", niche_label="subniche:prehistoric_creatures"))
    assert '<a href="/subnichos">← Volver a Subnichos</a>' in sub
    assert "Volver a Nichos" not in sub
    named = report_detail(
        "pendiente",
        niche_label="subniche:prehistoric_creatures",
        evidence={"source": "subniche", "subniche": {"label": "Criaturas del hielo"}},
    )
    assert "Criaturas del hielo" in page(named) and "Prehistoric" not in page(named)


HUGE = (1e308, 10**400, 10_001, -1)


@pytest.mark.parametrize("huge", HUGE)
def test_huge_step_minutes_are_no_data_and_never_break_the_report(huge: Any) -> None:
    dossier = five_step_dossier(calibration=(huge, huge, 10, 10, 10), regime=(huge, huge, 1, 1, 1))
    text = page(report_detail(dossier=dossier))
    section = block(text, "tiempo")
    assert segments(section)[0][0][1] == 0 and segments(section)[0][1][1] == 0
    assert ("Tu tiempo por video", "30 min") in rows(section)
    auth = make_client(
        Api(
            {
                GET: (200, report_detail(dossier=dossier)),
                STATUS: (200, {"radar_paused": True}),
                ("GET", "/api/v1/pilots"): (200, {"items": []}),
            }
        )
    ).get(f"/pilotos/autorizar?informe={ID}")
    assert auth.status_code == 200 and 'id="tiempo"' in auth.text


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("videos", 1e308),
        ("videos", 10**400),
        ("videos", -3),
        ("videos", 0),
        ("videos", 13),
        ("videos", 10**9),
        ("videos", 2.5),
        ("videos", True),
        ("videos", "6"),
        ("setup_hours", 1e308),
        ("setup_hours", 10**400),
        ("setup_hours", -1),
        ("setup_hours", 1001),
    ],
)
def test_unusable_videos_or_setup_make_the_calibration_unusable(key: str, bad: Any) -> None:
    dossier = dossier_v3()
    dossier["calibration"][key] = bad
    text = page(report_detail(dossier=dossier))
    assert "bar__seg" not in text
    assert "no trae la calibración completa" in block(text, "aviso-dossier")


def test_more_than_fifteen_steps_show_the_first_fifteen_with_a_fixed_notice() -> None:
    names = [f"Paso largo {i} " + "x" * 150 for i in range(300)]
    dossier = dossier_v3()
    template = dossier["production_flow"][0]
    dossier["production_flow"] = [
        {**template, "order": 1, "name": n, "human_minutes_per_video": 1} for n in names
    ]
    dossier["calibration"]["minutes_by_step"] = [{"step": n, "minutes_per_video": 2} for n in names]
    section = block(page(report_detail(dossier=dossier)), "tiempo")
    first, second = segments(section)
    assert len(first) == 15 and len(second) == 15
    assert section.count('class="legend__item"') == 15
    assert "Se muestran los primeros 15 pasos." in section
    assert len(re.findall(r'aria-label="([^"]*)"', section)[0]) < 4000
    assert "Se muestran los primeros" not in block(
        page(report_detail(dossier=five_step_dossier())), "tiempo"
    )


def test_the_legend_numbers_the_steps() -> None:
    section = block(page(report_detail(dossier=five_step_dossier())), "tiempo")
    for number, name in enumerate(STEPS, start=1):
        assert f"{number}. {name}" in section
