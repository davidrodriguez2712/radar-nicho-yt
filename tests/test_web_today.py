# tests/test_web_today.py
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from nicheradar.web.today import (
    attention_cards,
    calibration_candidates,
    open_pilot_keys,
    ready_reports,
    top_niches,
    top_subniches,
)
from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    dossier_v3,
    flow_item,
    make_client,
    niche_item,
    pilot_detail,
    pilot_item,
    pilot_video,
    report_detail,
    settings,
    subniche_item,
)
from tests.web_helpers import REPORT_ID as DOSSIER_ID

NICHES = ("GET", "/api/v1/market/niches")
FLOW = ("GET", "/api/v1/flow-research")
PILOTS = ("GET", "/api/v1/pilots")
SUBS = ("GET", "/api/v1/subniches")
STATUS = ("GET", "/api/v1/status")
REPORT_ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
OLDER = "Puede haber registros más antiguos que no se ven"


def scored(value: float | None) -> dict[str, Any]:
    state = "scored" if value is not None else "insufficient_evidence"
    return {
        "version": "v1",
        "value": value,
        "state": state,
        "components": {},
        "components_used": [],
    }


def full_api(extra: dict[tuple[str, str], Route] | None = None) -> Api:
    """Every source healthy: one pilot needing a decision, one ready report, 5 scored niches."""
    routes: dict[tuple[str, str], Route] = {
        STATUS: (200, {"radar_paused": True, "timezone": "America/Lima"}),
        NICHES: (
            200,
            {
                "items": [niche_item(f"n{i}", opportunity=scored(90.0 - i)) for i in range(5)],
                "total": 5,
                "limit": 10,
                "offset": 0,
            },
        ),
        FLOW: (200, {"items": [flow_item("listo", id=REPORT_ID, niche_label="rep-label")]}),
        PILOTS: (
            200,
            {
                "items": [
                    pilot_item(
                        "pil_20261102_a",
                        niche_label="pil-label",
                        needs_decision=True,
                        status="decision_pendiente",
                    )
                ]
            },
        ),
        SUBS: (200, {"items": [subniche_item("uno"), subniche_item("dos", finalist=False)]}),
        # The active pilot is read for its calibration: its package has no dossier-v3, so no card.
        ("GET", "/api/v1/pilots/pil_20261102_a"): (200, pilot_detail("pil_20261102_a", package={})),
    }
    return Api(routes | (extra or {}))


def boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def section(html: str, name: str) -> str:
    found = re.search(rf'<section class="card" id="hoy-{name}">(.*?)</section>', html, re.S)
    assert found, f"no section {name}"
    return found.group(1)


def ids() -> list[str]:
    return [f"{i:08x}-1111-4111-8111-111111111111" for i in range(1, 6)]


# ---- pure functions -------------------------------------------------------------------------


def test_ready_reports_exclude_those_with_an_open_pilot_and_cap_at_three() -> None:
    flows = [flow_item("listo", id=ids()[i], niche_label=f"n{i}") for i in range(5)] + [
        flow_item("pendiente", id=ids()[0], niche_label="n9")
    ]
    pilots = [
        pilot_item(niche_label="n0", status="en_ejecucion"),
        pilot_item("pil_20261102_b", niche_label="n1", status="cerrado"),
        pilot_item("pil_20261102_c", niche_label="n2", status="cancelado"),
        pilot_item("pil_20261102_d", niche_label="n3", format="shorts", status="en_ejecucion"),
    ]
    result = ready_reports(flows, pilots)
    # n0 is blocked; closed/cancelled pilots and a pilot of another format do not block.
    assert [r["label"] for r in result] == ["n1", "n2", "n3"]
    assert [r["href"] for r in result] == [f"/informes/{i}" for i in ids()[1:4]]


def test_ready_reports_skip_ids_that_are_not_a_whole_uuid() -> None:
    bad = [
        "../x",
        REPORT_ID + "\n",
        REPORT_ID.upper(),
        "a/b",
        "",
    ]
    flows = [flow_item("listo", id=i, niche_label="x") for i in bad]
    assert ready_reports(flows, []) == []


def test_top_niches_skip_unscored_and_take_three() -> None:
    items = [
        niche_item("a"),
        niche_item("b", opportunity=scored(None)),
        niche_item("c"),
        niche_item("d"),
        niche_item("e"),
    ]
    cards = top_niches(items, [])
    assert [c["label"] for c in cards] == ["a", "c", "d"]
    assert [c["rank"] for c in cards] == [1, 2, 3]


def test_top_niches_skip_nan_and_non_numeric_scores() -> None:
    items = [
        niche_item("a", opportunity=scored(float("nan"))),
        niche_item("b", opportunity=scored(float("inf"))),
        niche_item("c", opportunity=None),
        niche_item("d", opportunity={"value": "78"}),
        niche_item("e", opportunity={"value": True}),
        niche_item("ok"),
    ]
    assert [c["label"] for c in top_niches(items, [])] == ["ok"]


def test_top_niches_use_the_research_of_the_same_niche_and_format() -> None:
    research = [flow_item("listo", id=REPORT_ID, niche_label="a", format="long")]
    card = top_niches([niche_item("a")], research)[0]
    assert card["action"]["href"] == f"/informes/{REPORT_ID}"


def test_top_subniches_list_finalists_with_a_measurement_first() -> None:
    items = [
        subniche_item("sin-med", measurement=None),
        subniche_item("no-final", finalist=False),
        subniche_item("m1"),
        subniche_item("m2"),
        subniche_item("m3"),
    ]
    assert [c["label"] for c in top_subniches(items)] == ["M1", "M2", "M3"]
    assert [c["label"] for c in top_subniches(items[:3])] == ["M1", "Sin-Med"]


NOW = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)


def test_attention_cards_cover_decisions_and_authorized_pilots_only() -> None:
    pilots = [
        pilot_item(
            "pil_20261102_a", niche_label="A", needs_decision=True, status="decision_pendiente"
        ),
        pilot_item(
            "pil_20261102_b",
            niche_label="B",
            status="autorizado",
            target_channel=None,
            delivered_at=None,
        ),
        pilot_item("pil_20261102_c", niche_label="C", status="en_ejecucion"),
        pilot_item("pil_20261102_d", niche_label="D", status="autorizado", needs_decision=True),
    ]
    cards = attention_cards(pilots, NOW)
    assert [(c["label"], c["channel"], c["text"], c["href"]) for c in cards] == [
        ("A", "canal-historias", "Decide si sigue o cierra", "/pilotos/pil_20261102_a"),
        ("B", "Canal nuevo", "Falta que tu Mac baje el paquete", "/pilotos/pil_20261102_b"),
        ("D", "canal-historias", "Decide si sigue o cierra", "/pilotos/pil_20261102_d"),
    ]


def test_attention_cards_skip_what_is_not_a_pilot_dict() -> None:
    assert attention_cards([1, "x", None, ["a"]], NOW) == []  # type: ignore[list-item]


# ---- the page -------------------------------------------------------------------------------


def test_the_home_needs_a_session_and_is_the_landing_page() -> None:
    response = TestClient(create_app(settings()), follow_redirects=False).get("/")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    page = make_client(full_api()).get("/")
    assert page.status_code == 200 and '<h1 class="h1">Hoy</h1>' in page.text


def test_the_home_shows_the_local_date() -> None:
    sunday_evening_in_lima = datetime(2026, 11, 2, 3, 0, tzinfo=UTC).timestamp()
    text = make_client(full_api(), clock=lambda: sunday_evening_in_lima).get("/").text
    assert "Domingo 1 de noviembre" in text
    other = make_client(full_api(), clock=lambda: sunday_evening_in_lima, timezone="UTC").get("/")
    assert "Lunes 2 de noviembre" in other.text


def test_the_home_no_longer_asks_the_status_and_asks_the_rest_once() -> None:
    api = full_api()
    web = make_client(api)
    web.get("/")
    assert api.count("GET", "/api/v1/status") == 0
    for path in (NICHES, FLOW, PILOTS, SUBS):
        assert api.count(*path) == 1, path


def test_the_four_cards_and_their_links() -> None:
    text = make_client(full_api()).get("/").text
    assert "3 nichos que merecen tu atención" in section(text, "nichos")
    assert "Subnichos medidos" in section(text, "subnichos")
    assert "Informes listos" in section(text, "informes")
    assert "pilotos" in section(text, "pilotos").lower()
    assert '<a class="btn btn--secondary" href="/nichos">Ver todos los nichos</a>' in section(
        text, "nichos"
    )
    assert '<a class="btn btn--secondary" href="/subnichos">Ver subnichos</a>' in section(
        text, "subnichos"
    )
    for name in ("n0", "n1", "n2"):
        assert name in section(text, "nichos")
    assert "n3" not in section(text, "nichos")
    assert ">Uno<" in section(text, "subnichos") and "Dos" not in section(text, "subnichos")


def attention_items(card: str) -> list[str]:
    """The entries of the pilots card, each one a whole `list__item` block."""
    return re.findall(r'<div class="list__item">.*?</div>', card, re.S)


def test_a_pilot_needing_something_links_to_its_panel_with_the_derived_reason() -> None:
    pilots = [
        pilot_item(
            "pil_20261102_a",
            niche_label="niche-a",
            needs_decision=True,
            status="decision_pendiente",
        ),
        pilot_item(
            "pil_20261102_b",
            niche_label="niche-b",
            status="autorizado",
            target_channel="canal-b",
            delivered_at=None,
        ),
    ]
    text = make_client(full_api({PILOTS: (200, {"items": pilots})})).get("/").text
    card = section(text, "pilotos")
    assert "2 pilotos necesitan algo de ti" in card
    first, second = attention_items(card)
    assert '<a class="list__name" href="/pilotos/pil_20261102_a">niche-a</a>' in first
    assert "Decide si sigue o cierra" in first and "canal-historias" in first
    assert '<a class="list__name" href="/pilotos/pil_20261102_b">niche-b</a>' in second
    assert "Falta que tu Mac baje el paquete" in second and "canal-b" in second


def test_a_pilot_with_a_blocker_but_no_decision_is_listed_with_that_blocker() -> None:
    blocked = pilot_item(
        "pil_20261102_x",
        niche_label="bloqueado",
        status="en_ejecucion",
        channel={
            "checks": [
                {
                    "id": "youtube_oauth",
                    "label": "Autorizar YouTube",
                    "ok": False,
                    "detail": "Falta el permiso",
                    "expires_at": None,
                }
            ]
        },
    )
    quiet = pilot_item("pil_20261102_y", niche_label="tranquilo", status="en_ejecucion")
    text = make_client(full_api({PILOTS: (200, {"items": [blocked, quiet]})})).get("/").text
    card = section(text, "pilotos")
    assert "1 piloto necesita algo de ti" in card
    (entry,) = attention_items(card)
    assert 'href="/pilotos/pil_20261102_x">bloqueado</a>' in entry
    assert "Falta: Autorizar YouTube. Falta el permiso" in entry
    assert "tranquilo" not in card


def test_blockers_use_the_configured_timezone() -> None:
    late = pilot_item(
        "pil_20261102_x",
        status="en_ejecucion",
        channel={
            "checks": [
                {"id": "k", "label": "Clave", "ok": True, "expires_at": "2026-11-05T03:00:00Z"}
            ]
        },
    )
    api: dict[tuple[str, str], Route] = {PILOTS: (200, {"items": [late]})}
    moment = datetime(2026, 11, 3, 15, 0, tzinfo=UTC).timestamp()
    lima = make_client(full_api(api), clock=lambda: moment).get("/").text
    assert "Clave vence el 4 nov" in section(lima, "pilotos")
    utc = make_client(full_api(api), clock=lambda: moment, timezone="UTC").get("/").text
    assert "Clave vence el 5 nov" in section(utc, "pilotos")


def test_the_pilots_link_is_a_real_link_now() -> None:
    card = section(make_client(full_api()).get("/").text, "pilotos")
    assert '<a class="btn btn--secondary" href="/pilotos">Ver pilotos</a>' in card
    assert "Próximamente" not in card
    assert "disabled" not in card


@pytest.mark.parametrize(
    "bad_id",
    ["../x", "pil_20261102_a\n", "PIL_20261102_A", "pil_2026110_a", "a/b", "", "pil_20261102_é", 7],
)
def test_an_invalid_pilot_id_never_becomes_a_link(bad_id: object) -> None:
    pilot = pilot_item(bad_id, niche_label="sin-enlace", needs_decision=True)  # type: ignore[arg-type]
    card = section(
        make_client(full_api({PILOTS: (200, {"items": [pilot]})})).get("/").text, "pilotos"
    )
    (entry,) = attention_items(card)
    assert '<span class="list__name">sin-enlace</span>' in entry
    assert "<a" not in entry
    assert card.count("/pilotos/") == 0
    assert "1 piloto necesita algo de ti" in card


def test_closed_and_cancelled_pilots_never_appear_in_the_attention_card() -> None:
    pilots = [
        pilot_item("pil_20261102_a", status="cerrado", needs_decision=True, niche_label="cer"),
        pilot_item(
            "pil_20261102_b",
            status="cancelado",
            needs_decision=True,
            niche_label="can",
            delivered_at=None,
        ),
    ]
    card = section(
        make_client(full_api({PILOTS: (200, {"items": pilots})})).get("/").text, "pilotos"
    )
    assert "Ningún piloto necesita algo de ti" in card
    assert attention_items(card) == []
    assert "/pilotos/pil_" not in card


def test_one_pilot_uses_the_singular() -> None:
    card = section(make_client(full_api()).get("/").text, "pilotos")
    assert "1 piloto necesita algo de ti" in card and "pilotos necesitan" not in card


def test_the_counting_text_stays_correct_in_singular_and_plural() -> None:
    def card_for(count: int) -> str:
        pilots = [
            pilot_item(f"pil_20261102_p{i}", needs_decision=True, niche_label=f"p{i}")
            for i in range(count)
        ]
        page = make_client(full_api({PILOTS: (200, {"items": pilots})})).get("/").text
        return section(page, "pilotos")

    assert '<h2 class="h2">Ningún piloto necesita algo de ti</h2>' in card_for(0)
    assert '<h2 class="h2">1 piloto necesita algo de ti</h2>' in card_for(1)
    assert '<h2 class="h2">2 pilotos necesitan algo de ti</h2>' in card_for(2)
    assert '<h2 class="h2">4 pilotos necesitan algo de ti</h2>' in card_for(4)


def test_a_malformed_pilot_item_only_degrades_its_own_card() -> None:
    weird = pilot_item(
        "pil_20261102_w",
        niche_label=["unhashable"],
        format={"a": 1},
        status="en_ejecucion",
        totals="x",
        channel={"checks": "x"},
        channel_last_contact_at=-12345.5,
        valid_until=[1],
    )
    broken = {"pilot_id": None}  # missing nearly every key
    raw = json.dumps({"items": [weird, broken]}).replace("-12345.5", "NaN")
    assert "NaN" in raw

    def nan_pilots(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=raw.encode(), headers={"content-type": "application/json"}
        )

    page = make_client(full_api({PILOTS: nan_pilots})).get("/")
    assert page.status_code == 200
    text = page.text
    for name in ("nichos", "subnichos"):
        assert "no disponible" not in section(text, name)
    assert "Pilotos: no disponible" not in section(text, "pilotos")
    assert ">n0<" in section(text, "nichos") and ">Uno<" in section(text, "subnichos")


def test_a_pilot_item_that_breaks_the_reports_crossing_does_not_hide_either_card() -> None:
    weird = pilot_item("pil_20261102_w", niche_label=["unhashable"], needs_decision=True)
    text = make_client(full_api({PILOTS: (200, {"items": [weird]})})).get("/").text
    assert "1 piloto necesita algo de ti" in section(text, "pilotos")
    reports = section(text, "informes")
    assert "no disponible" not in reports
    assert "No se pudo comprobar si algunos informes ya tienen piloto" in reports
    assert 'class="list__name"' in reports  # the ready report is still listed


@pytest.mark.parametrize(
    "weird",
    [
        {"niche_label": ["u"], "format": "long", "status": "en_ejecucion"},
        {"niche_label": "rep-label", "format": {"a": 1}, "status": "en_ejecucion"},
        {"niche_label": "rep-label", "format": "long", "status": ["x"]},
    ],
)
def test_ready_reports_cross_only_well_formed_pilots_and_flag_the_rest(weird: object) -> None:
    flows = [flow_item("listo", id=REPORT_ID, niche_label="rep-label")]
    api = full_api({PILOTS: (200, {"items": [weird]})})
    text = make_client(api).get("/").text
    reports = section(text, "informes")
    assert "no disponible" not in reports and 'class="list__name"' in reports
    assert "algunos informes ya tienen piloto" in reports
    assert flows  # the flow list itself is the one served by full_api


def test_open_pilot_keys_skip_what_is_not_a_readable_pilot_and_say_so() -> None:
    good = pilot_item("pil_20261102_a", niche_label="a", format="long", status="en_ejecucion")
    closed = pilot_item("pil_20261102_b", niche_label="b", status="cerrado")
    assert open_pilot_keys([good, closed]) == ({("a", "long")}, False)
    assert open_pilot_keys([good, None, "x", {"status": ["s"]}]) == ({("a", "long")}, True)


def test_well_formed_pilots_raise_no_crossing_warning() -> None:
    text = make_client(full_api()).get("/").text
    assert "algunos informes ya tienen piloto" not in section(text, "informes")


def test_with_no_pilots_needing_attention_the_card_says_so() -> None:
    quiet = [pilot_item("pil_20261102_z", status="en_ejecucion")]
    card = section(
        make_client(full_api({PILOTS: (200, {"items": quiet})})).get("/").text, "pilotos"
    )
    assert "Ningún piloto necesita algo de ti" in card
    assert "Decide si sigue" not in card


def test_a_ready_report_without_a_pilot_gets_a_link_to_its_report() -> None:
    card = section(make_client(full_api()).get("/").text, "informes")
    assert f'href="/informes/{REPORT_ID}"' in card and "rep-label" in card
    blocked = [pilot_item(niche_label="rep-label", status="en_ejecucion")]
    card = section(
        make_client(full_api({PILOTS: (200, {"items": blocked})})).get("/").text, "informes"
    )
    assert f"/informes/{REPORT_ID}" not in card and "Ningún informe listo" in card


def test_tentative_forms_in_the_niche_card_come_back_to_the_niche_list() -> None:
    card = section(make_client(full_api()).get("/").text, "nichos")
    assert card.count('action="/nichos/decidir"') == 3
    assert card.count('name="volver" value="/nichos"') == 3
    assert card.count('name="decision" value="tentativo"') == 3
    assert 'name="csrf" value="' in card


# One failing source, in each of the ways it can fail.
FAILURES: list[Route] = [
    boom,
    (500, {"detail": "x"}),
    (404, {"detail": "x"}),
    (200, {"total": 0}),  # no "items"
    (200, {"items": "nope"}),
    (200, {"items": [1, 2]}),
]
CARDS = {
    "pilotos": (PILOTS, "Pilotos", "Decide si sigue o cierra"),
    "informes": (FLOW, "Informes listos", f"/informes/{REPORT_ID}"),
    "nichos": (NICHES, "Nichos", ">n0<"),
    "subnichos": (SUBS, "Subnichos", ">Uno<"),
}


@pytest.mark.parametrize("failure", range(len(FAILURES)))
@pytest.mark.parametrize("name", list(CARDS))
def test_each_source_failing_degrades_only_its_own_card(name: str, failure: int) -> None:
    key, title, _ = CARDS[name]
    page = make_client(full_api({key: FAILURES[failure]})).get("/")
    assert page.status_code == 200
    assert page.text.count("no disponible") == 1
    assert f"{title}: no disponible ahora" in section(page.text, name)
    for other, (_, _, marker) in CARDS.items():
        if other == name:
            assert marker not in section(page.text, other)
        else:
            assert marker in section(page.text, other), other
            assert "no disponible" not in section(page.text, other)


def test_a_failing_flow_source_warns_in_the_niche_card_instead_of_hiding_it() -> None:
    card = section(make_client(full_api({FLOW: boom})).get("/").text, "nichos")
    assert "Marcar tentativo" in card
    assert "No se pudo leer el estado de las investigaciones" in card
    assert "no disponible" not in card


def test_when_every_source_fails_the_page_is_still_200() -> None:
    api = Api({STATUS: boom, NICHES: boom, FLOW: boom, PILOTS: boom, SUBS: boom})
    moment = datetime(2026, 11, 2, 3, 0, tzinfo=UTC).timestamp()
    page = make_client(api, clock=lambda: moment).get("/")
    assert "Domingo 1 de noviembre" in page.text
    assert page.status_code == 200 and page.text.count("no disponible") == 4
    assert page.text.count('<section class="card"') == 4
    for name, (_, title, _) in CARDS.items():
        assert f"{title}: no disponible ahora" in section(page.text, name)


def test_a_nan_score_never_breaks_the_page() -> None:
    items = [
        niche_item("nan-niche", opportunity=scored(1.0)),
        niche_item("ok", opportunity=scored(5.0)),
    ]
    text = json.dumps({"items": items}).replace("1.0", "NaN", 1)
    assert "NaN" in text

    def nan_api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=text.encode(), headers={"content-type": "application/json"}
        )

    page = make_client(full_api({NICHES: nan_api})).get("/")
    assert page.status_code == 200
    card = section(page.text, "nichos")
    assert ">ok<" in card and "nan-niche" not in card


def test_exactly_one_hundred_records_warn_inside_the_affected_cards() -> None:
    many_flows = [flow_item("listo", id=ids()[0], niche_label="rep-label") for _ in range(100)]
    many_pilots = [pilot_item("pil_20261102_a", needs_decision=True) for _ in range(100)]
    text = (
        make_client(
            full_api({FLOW: (200, {"items": many_flows}), PILOTS: (200, {"items": many_pilots})})
        )
        .get("/")
        .text
    )
    assert OLDER in section(text, "pilotos") and OLDER in section(text, "informes")
    assert OLDER not in section(text, "subnichos")
    quiet = (
        make_client(
            full_api(
                {
                    FLOW: (200, {"items": many_flows[:99]}),
                    PILOTS: (200, {"items": many_pilots[:99]}),
                }
            )
        )
        .get("/")
        .text
    )
    assert OLDER not in quiet


def test_hostile_text_in_any_source_is_escaped() -> None:
    api = full_api(
        {
            NICHES: (
                200,
                {"items": [niche_item(HOSTILE)], "total": 1, "limit": 10, "offset": 0},
            ),
            SUBS: (200, {"items": [subniche_item("x", label=HOSTILE)]}),
            PILOTS: (
                200,
                {
                    "items": [
                        pilot_item(
                            niche_label=HOSTILE,
                            target_channel=HOSTILE,
                            needs_decision=True,
                            status="decision_pendiente",
                        )
                    ]
                },
            ),
            FLOW: (
                200,
                {"items": [flow_item("listo", id=REPORT_ID, niche_label=HOSTILE, format="shorts")]},
            ),
        }
    )
    text = make_client(api).get("/").text
    assert "<script>alert(1)</script>" not in text
    for name in ("nichos", "subnichos", "pilotos", "informes"):
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in section(text, name), name
    assert "|safe" not in text and "style=" not in text


def test_an_invalid_configured_timezone_never_breaks_the_page() -> None:
    web = make_client(full_api())
    web.app.state.config.timezone = "No/Such_Zone"  # type: ignore[attr-defined]
    response = web.get("/")
    assert response.status_code == 200, response.text
    assert "de " in response.text and "no disponible" not in section(response.text, "pilotos")


def test_hostile_html_in_the_pilot_cards_is_escaped_in_every_field() -> None:
    check = {"id": "c1", "label": HOSTILE, "ok": False, "detail": HOSTILE, "expires_at": None}
    blocked = pilot_item(
        "pil_20261102_a",
        niche_label=HOSTILE,
        target_channel=HOSTILE,
        channel={"reported_at": None, "channel_status": "active", "note": None, "checks": [check]},
    )
    decide = pilot_item(
        "pil_20261102_b",
        niche_label=HOSTILE,
        target_channel=HOSTILE,
        needs_decision=True,
        status="decision_pendiente",
    )
    text = make_client(full_api({PILOTS: (200, {"items": [blocked, decide]})})).get("/").text
    card = section(text, "pilotos")
    assert "<script>alert(1)</script>" not in text
    assert card.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 4
    assert 'href="/pilotos/pil_20261102_a"' in card and 'href="/pilotos/pil_20261102_b"' in card
    assert "javascript:" not in text


# ---- pilotos en calibración (M14) -----------------------------------------------------------


def client_page(api: Api) -> str:
    return str(make_client(api).get("/").text)


def cal_pilot(index: int, **over: object) -> dict[str, object]:
    return (
        pilot_item(f"pil_20261102_c{index}", status="en_ejecucion", niche_label=f"cal-{index}")
        | over
    )


def cal_routes(
    index: int,
    minutes: list[int | None],
    schema: str = "dossier-v3",
    rid: str = DOSSIER_ID,
    method: str = "gate_waits",
) -> dict[tuple[str, str], Route]:
    pid = f"pil_20261102_c{index}"
    detail = pilot_detail(pid, status="en_ejecucion")
    package = detail["package"]
    assert isinstance(package, dict)
    detail["package"] = package | {
        "dossier": package["dossier"] | {"schema": schema, "request_id": rid}
    }
    return {
        ("GET", f"/api/v1/pilots/{pid}"): (200, detail),
        ("GET", f"/api/v1/pilots/{pid}/videos"): (
            200,
            {
                "items": [
                    pilot_video(f"v{i}", human_minutes=m, human_minutes_method=method)
                    for i, m in enumerate(minutes, 1)
                ]
            },
        ),
    }


REPORT_ROUTE = ("GET", f"/api/v1/flow-research/{DOSSIER_ID}")


def cal_api(pilots: list[dict[str, object]], extra: dict[tuple[str, str], Route]) -> Api:
    routes = {
        REPORT_ROUTE: (200, report_detail(dossier=dossier_v3())),
        PILOTS: (200, {"items": pilots}),
    }
    return full_api(routes | extra)


def test_calibration_candidates_are_active_pilots_with_a_valid_id_capped_at_five() -> None:
    pilots = [
        cal_pilot(1),
        cal_pilot(2, status="cerrado"),
        cal_pilot(3, status="cancelado"),
        cal_pilot(4, pilot_id="../x"),
        cal_pilot(5, pilot_id="pil_20261102_x\n"),
        cal_pilot(6, status="autorizado"),
        cal_pilot(7, status="entregado"),
        cal_pilot(8, status="decision_pendiente"),
        cal_pilot(9),
        cal_pilot(10),
        cal_pilot(11),
        cal_pilot(12),
        "x",
    ]
    chosen, more = calibration_candidates(pilots)
    assert [p["pilot_id"] for p in chosen] == [f"pil_20261102_c{i}" for i in (1, 7, 8, 9, 10)]
    assert more == 2


def test_the_calibration_card_lists_each_pilot_with_streak_and_last_video() -> None:
    routes = cal_routes(1, [92, 58]) | cal_routes(2, [58, 59, 55])
    api = cal_api([cal_pilot(1), cal_pilot(2)], routes)
    card = section(client_page(api), "calibracion")
    assert "2 pilotos en calibración" in card
    assert "Racha de hasta 60 minutos: 1 de 3" in card
    assert "Racha de hasta 60 minutos: 3 de 3" in card
    assert "Video 2 · 58 min" in card and "Video 3 · 55 min" in card
    assert 'href="/pilotos/pil_20261102_c1"' in card
    assert "Pasa a régimen" in card
    assert "<form" not in card and "<button" not in card


def test_the_card_says_could_pass_when_the_figures_are_a_lower_bound() -> None:
    api = cal_api(
        [cal_pilot(1)], cal_routes(1, [58, 59, 55], method="claude_sessions_plus_assumed")
    )
    card = section(client_page(api), "calibracion")
    assert "Podrías pasar a régimen" in card
    assert "Pasa a régimen" not in card
    assert "Las cifras son un mínimo estimado: confírmalo con tu propio criterio." in card
    assert "Racha de hasta 60 minutos: 3 de 3 (posible: las cifras son un mínimo)" in card
    assert "Video 3 · ≥ 55 min" in card
    assert "<form" not in card and "<button" not in card


def test_the_card_escapes_a_hostile_method_name() -> None:
    hostile = "<script>x</script>claude_sessions_plus_assumed"
    api = cal_api([cal_pilot(1)], cal_routes(1, [58, 59, 55], method=hostile))
    card = section(client_page(api), "calibracion")
    assert "<script>x" not in card
    assert "Pasa a régimen" in card  # not a lower-bound method: the text is unchanged


def test_one_pilot_in_calibration_uses_the_singular() -> None:
    api = cal_api([cal_pilot(1)], cal_routes(1, [58]))
    assert "1 piloto en calibración" in section(client_page(api), "calibracion")


def test_unmeasured_videos_never_show_zero_minutes_in_the_card() -> None:
    api = cal_api([cal_pilot(1)], cal_routes(1, [None, None]))
    card = section(client_page(api), "calibracion")
    assert "sin medir" in card and "Aún sin minutos medidos" in card
    assert "Racha de hasta 60 minutos: 0 de 3" in card
    assert not re.search(r"(?<!\d)0 min", card)


def test_without_pilots_in_calibration_the_card_is_absent() -> None:
    for pilots, extra in (
        ([], {}),
        ([cal_pilot(1, status="cerrado")], cal_routes(1, [50])),
        ([cal_pilot(1)], cal_routes(1, [50], schema="dossier-v2")),
    ):
        api = cal_api(pilots, extra)
        text = client_page(api)
        assert "hoy-calibracion" not in text and "en calibración" not in text


def test_a_dossier_without_calibration_is_skipped_silently() -> None:
    api = cal_api([cal_pilot(1)], cal_routes(1, [50]))
    api.routes[REPORT_ROUTE] = (200, report_detail(dossier=dossier_v3() | {"calibration": 3}))
    text = client_page(api)
    assert "hoy-calibracion" not in text and "no disponible" not in text


def test_a_failing_source_degrades_only_the_calibration_card() -> None:
    for broken in (
        REPORT_ROUTE,
        ("GET", "/api/v1/pilots/pil_20261102_c1"),
        ("GET", "/api/v1/pilots/pil_20261102_c1/videos"),
    ):
        api = cal_api([cal_pilot(1)], cal_routes(1, [50]))
        api.routes[broken] = (500, {"detail": "x"})
        text = client_page(api)
        assert "Pilotos en calibración: no disponible ahora" in section(text, "calibracion")
        assert text.count("no disponible") == 1
        assert "Informes listos" in text and "Subnichos medidos" in text


def test_a_readable_pilot_stays_when_another_one_fails() -> None:
    routes = cal_routes(1, [58]) | cal_routes(2, [58])
    api = cal_api([cal_pilot(1), cal_pilot(2)], routes)
    api.routes[("GET", "/api/v1/pilots/pil_20261102_c2")] = (500, {"detail": "x"})
    card = section(client_page(api), "calibracion")
    assert "1 piloto en calibración" in card and "No se pudo leer 1 piloto" in card


def test_more_than_five_pilots_are_cut_with_a_notice() -> None:
    routes: dict[tuple[str, str], Route] = {}
    for i in range(1, 8):
        routes |= cal_routes(i, [58])
    api = cal_api([cal_pilot(i) for i in range(1, 8)], routes)
    card = section(client_page(api), "calibracion")
    assert "5 pilotos en calibración" in card and "y 2 más" in card
    assert api.count("GET", "/api/v1/pilots/pil_20261102_c6") == 0
    assert api.count(*REPORT_ROUTE) == 5


def test_calibration_requests_are_only_for_active_pilots_with_calibration() -> None:
    api = cal_api(
        [cal_pilot(1, status="cerrado"), cal_pilot(2, status="autorizado")],
        cal_routes(1, [50]) | cal_routes(2, [50]),
    )
    client_page(api)
    assert api.count(*REPORT_ROUTE) == 0
    assert api.count("GET", "/api/v1/pilots/pil_20261102_c1") == 0


def test_the_calibration_card_is_absent_when_the_pilots_source_fails() -> None:
    api = cal_api([cal_pilot(1)], cal_routes(1, [50]))
    api.routes[PILOTS] = (500, {"detail": "x"})
    text = client_page(api)
    assert "hoy-calibracion" not in text and api.count(*REPORT_ROUTE) == 0


def test_hostile_text_in_the_calibration_card_is_escaped() -> None:
    dossier = dossier_v3()
    dossier["calibration"]["exit_criterion"]["statement"] = HOSTILE
    api = cal_api([cal_pilot(1, niche_label=HOSTILE, target_channel=HOSTILE)], cal_routes(1, [50]))
    api.routes[REPORT_ROUTE] = (200, report_detail(dossier=dossier))
    text = client_page(api)
    assert "<script>" not in text
    assert "&lt;script&gt;" in section(text, "calibracion")
