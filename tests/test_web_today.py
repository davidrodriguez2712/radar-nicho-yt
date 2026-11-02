# tests/test_web_today.py
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from nicheradar.web.today import attention_cards, ready_reports, top_niches, top_subniches
from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    flow_item,
    make_client,
    niche_item,
    pilot_item,
    settings,
    subniche_item,
)

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


def test_attention_cards_cover_decisions_and_authorized_pilots_only() -> None:
    pilots = [
        pilot_item(
            "pil_20261102_a", niche_label="A", needs_decision=True, status="decision_pendiente"
        ),
        pilot_item("pil_20261102_b", niche_label="B", status="autorizado", target_channel=None),
        pilot_item("pil_20261102_c", niche_label="C", status="en_ejecucion"),
        pilot_item("pil_20261102_d", niche_label="D", status="autorizado", needs_decision=True),
    ]
    cards = attention_cards(pilots)
    assert [(c["label"], c["channel"], c["text"]) for c in cards] == [
        ("A", "canal-historias", "Decide si sigue o cierra"),
        ("B", "Canal nuevo", "Falta entregar el paquete al canal"),
        ("D", "canal-historias", "Decide si sigue o cierra"),
    ]


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


def test_the_home_asks_the_status_once_per_request() -> None:
    api = full_api()
    web = make_client(api)
    web.get("/")
    assert api.count("GET", "/api/v1/status") == 1
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


def test_pilots_needing_something_are_listed_as_text_with_a_disabled_pilots_link() -> None:
    pilots = [
        pilot_item("pil_20261102_a", needs_decision=True, status="decision_pendiente"),
        pilot_item("pil_20261102_b", status="autorizado", target_channel="canal-b"),
    ]
    text = make_client(full_api({PILOTS: (200, {"items": pilots})})).get("/").text
    card = section(text, "pilotos")
    assert "2 pilotos necesitan algo de ti" in card
    assert "Decide si sigue o cierra" in card and "Falta entregar el paquete al canal" in card
    assert "canal-b" in card
    assert "Próximamente" in card
    assert re.search(r"<a[^>]*>[^<]*Ver pilotos", card) is None
    assert re.search(r"<button[^>]*disabled[^>]*>Ver pilotos</button>", card)
    assert "/pilotos" not in card


def test_one_pilot_uses_the_singular() -> None:
    card = section(make_client(full_api()).get("/").text, "pilotos")
    assert "1 piloto necesita algo de ti" in card and "pilotos necesitan" not in card


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
