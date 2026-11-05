# tests/test_web_niche_detail.py
import json
import re
from typing import Any

import httpx
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    flow_item,
    make_client,
    market_listing,
    niche_page,
    pilot_item,
    settings,
)

LABEL = "historia militar explicada"
PATH = f"/api/v1/market/niches/{LABEL}"
FLOW = ("GET", "/api/v1/flow-research")
PILOTS = ("GET", "/api/v1/pilots")
STATUS = ("GET", "/api/v1/status")
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"
URL = "/nichos/ver"


def api_for(
    detail: object,
    label: str = LABEL,
    flows: Route | None = None,
    pilots: Route | None = None,
) -> Api:
    return Api(
        {
            ("GET", f"/api/v1/market/niches/{label}"): (200, detail),
            FLOW: flows if flows is not None else (200, {"items": [flow_item()]}),
            PILOTS: pilots if pilots is not None else (200, {"items": []}),
            STATUS: (200, {"radar_paused": True}),
        }
    )


def get(api: Api, label: str = LABEL, fmt: str = "long") -> httpx.Response:
    return make_client(api).get(URL, params={"etiqueta": label, "formato": fmt})  # type: ignore[no-any-return]


def page(detail: object = None, **kwargs: Any) -> str:
    return get(api_for(niche_page() if detail is None else detail, **kwargs)).text


def niche_with(**over: object) -> dict[str, object]:
    detail = niche_page()
    detail["niche"] = {**detail["niche"], **over}  # type: ignore[dict-item]
    return detail


def test_the_detail_needs_a_session() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    response = web.get(URL, params={"etiqueta": LABEL, "formato": "long"})
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_the_detail_shows_the_figma_texts() -> None:
    text = page()
    assert f'<h1 class="h1 h1--md">{LABEL}</h1>' in text
    assert 'href="/nichos"' in text and "‹ Nichos" in text
    for expected in (
        "Puntajes",
        "Opportunity (0 a 100)",
        "Automatización (0 a 100)",
        "Riesgo de política",
        "Tendencia",
        "Investigación de flujo",
        "Mercado",
        "Ingreso mediano",
        "US$ 1.350 al mes",
        "2,4×",
        "RPM de referencia",
        "US$ 3,10",
        "Inglés 80 % · Español 15 % · Sin dato 5 %",
        "Cómo se calculó",
        "Rentabilidad 30 · Eficiencia 30 · Validación 25 · Dinámica 15",
        "Sin rostro 30 · Guionable 25 · Visuales automatizables 20",
        "Un puntaje necesita al menos 3 fichas con ingreso; sin eso se muestra «sin evidencia».",
        "Las cifras salen de fichas de canales en venta y las declaran los vendedores: "
        "no son ingresos verificados.",
        "Fichas del nicho (2)",
        "Largo",
        "Tentativo",
        "Dossier listo",
    ):
        assert expected in text, expected
    scores = re.findall(r'<span class="row__value">([^<]*)</span>', text)
    for value in ("72", "64", "alta", "bajo", "sube", "24", "18"):
        assert value in scores, value


def test_the_first_listing_is_verified_and_links_to_the_ad() -> None:
    text = page()
    first = re.search(r'<article class="listing">.*?</article>', text, re.S)
    assert first
    block = first.group(0)
    assert "Canal «Guerras al detalle»" in block
    assert "Activa" in block and "US$ 18.000" in block
    assert "120 mil suscriptores declarados" in block and "118 mil en YouTube" in block
    assert ">verificado<" in block
    assert "US$ 1.900 al mes" in block and "US$ 300 al mes" in block
    assert 'href="https://marketplace.test/anuncio/1"' in block and "Ver anuncio" in block
    second = re.findall(r'<article class="listing">.*?</article>', text, re.S)[1]
    assert "Desapareció" in second and ">no coincide<" in second


def test_the_journey_shows_the_real_steps() -> None:
    text = page()
    assert "Recorrido hasta el piloto" in text
    assert "Marcado «Tentativo»" in text
    assert "Hecha por Claude Code en inglés" in text
    assert "Decide si lo lanzas" in text
    pilot = pilot_item(status="en_ejecucion")
    assert "Piloto en ejecución" in page(pilots=(200, {"items": [pilot]}))


def test_the_research_card_links_the_dossier_or_offers_to_investigate() -> None:
    ready = page()
    assert 'href="/informes/f0c90924-295a-4136-a0fb-d3fb2c3eacc6"' in ready
    assert "Ver dossier" in ready
    none = page(flows=(200, {"items": []}))
    assert "Investigar</a>" in none
    assert f"/nichos/investigar?etiqueta={LABEL.replace(' ', '%20')}&amp;formato=long" in none
    undecided = page(
        niche_with(decision={"decision": "nuevo", "note": None}), flows=(200, {"items": []})
    )
    assert "Investigar</a>" not in undecided


def test_the_trend_is_translated() -> None:
    for trend, word in (
        (5.0, "sube"),
        (-3, "baja"),
        (0, "estable"),
        (None, "sin dato"),
        ("x", "sin dato"),
    ):
        text = page(niche_with(trend=trend))
        assert (
            f'<span class="row__label">Tendencia</span><span class="row__value">{word}</span>'
            in text
        )


def test_shorts_have_no_calibrated_rpm() -> None:
    api = api_for(niche_page(fmt="shorts"))
    text = get(api, fmt="shorts").text
    assert "sin calibrar" in text and "US$ 3,10" not in text
    assert dict(api.calls[0].url.params)["format"] == "shorts"


def test_an_unknown_niche_is_a_spanish_404() -> None:
    api = Api({FLOW: (200, {"items": []}), PILOTS: (200, {"items": []})})
    response = get(api)
    assert response.status_code == 404
    assert "No se encontró" in response.text and "Traceback" not in response.text


def test_an_api_outage_is_a_503() -> None:
    api = Api({("GET", PATH): (500, {"detail": "boom"})})
    response = get(api)
    assert response.status_code == 503
    assert "no disponible" in response.text.lower() or "No se pudo" in response.text
    assert "Traceback" not in response.text


def test_an_invalid_format_or_a_long_label_is_404_without_calling_the_api() -> None:
    api = api_for(niche_page())
    web = make_client(api)
    assert web.get(URL, params={"etiqueta": LABEL, "formato": "otro"}).status_code == 404
    assert web.get(URL, params={"etiqueta": "x" * 141, "formato": "long"}).status_code == 404
    assert web.get(URL, params={"formato": "long"}).status_code == 404
    assert web.get(URL, params={"etiqueta": "..", "formato": "long"}).status_code == 404
    for blank in (" ", ".", "   ", "\t\n"):
        assert web.get(URL, params={"etiqueta": blank, "formato": "long"}).status_code == 404
    assert api.calls == []


def test_hostile_labels_are_requested_exactly_and_escaped() -> None:
    for label, raw in (
        ("other:xyz", "other%3Axyz"),
        ("a/b", "a%2Fb"),
        ("a%2Fb", "a%252Fb"),
        ("<script>alert(1)</script>", "%3Cscript%3Ealert%281%29%3C%2Fscript%3E"),
    ):
        api = api_for(niche_page(label), label=label)
        response = get(api, label)
        assert response.status_code == 200, label
        detail_call = api.calls[0]
        assert detail_call.url.raw_path.decode().split("?")[0].endswith("/" + raw), label
        assert "<script>" not in response.text
    escaped = get(
        api_for(niche_page("<script>alert(1)</script>"), label="<script>alert(1)</script>"),
        "<script>alert(1)</script>",
    ).text
    assert ESCAPED in escaped


def test_a_listing_url_that_is_not_https_makes_no_link() -> None:
    listings = [
        market_listing("uno", url="javascript:alert(1)"),
        market_listing("dos", url="http://insecure.test/x"),
        market_listing("tres", url=None),
    ]
    text = page(niche_page(listings=listings))
    assert "javascript:" not in text and "insecure.test" not in text
    assert "Ver anuncio" not in text


def test_more_than_100_listings_are_capped_with_a_notice() -> None:
    listings = [market_listing(f"Ficha {i}") for i in range(101)]
    text = page(niche_page(listings=listings))
    assert len(re.findall(r'<article class="listing"', text)) == 100
    assert "Se muestran 100 de 101 fichas" in text


def test_see_more_only_appears_with_more_than_ten_listings() -> None:
    assert "Ver más fichas" not in page()
    eleven = page(niche_page(listings=[market_listing(f"F{i}") for i in range(11)]))
    assert "Ver más fichas" in eleven
    assert len(re.findall(r'<article class="listing"', eleven)) == 11
    assert eleven.count('class="more"') == 1


def raw_api(detail: object) -> Api:
    body = json.dumps(detail, allow_nan=True)

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return Api({("GET", PATH): answer, FLOW: (200, {"items": []}), PILOTS: (200, {"items": []})})


def test_broken_shapes_never_give_500() -> None:
    broken: list[object] = [
        niche_page(listings="x"),
        {"niche": {"niche_label": LABEL}, "listings": [], "language_mix": []},
        niche_page(listings=[{"title": None, "price_usd": float("nan")}, 5, "x"]),
        {"niche": None},
        [],
        "x",
        niche_page(listings=[market_listing(price_usd=10**400, subscribers=10**400)]),
        niche_page(listings=[market_listing(price_usd=1e308, real_subscribers=10**400)]),
        niche_with(
            metrics={"n_listings": 10**400, "income_median": 10**400, "multiple_median": 10**400},
            rpm_mid=10**400,
            trend=10**400,
            opportunity={"value": 10**400},
        ),
        niche_with(metrics={"n_listings": 1e308, "income_median": 1e308, "multiple_median": 1e308}),
    ]
    for detail in broken:
        assert get(raw_api(detail)).status_code in (200, 503), detail
    nonfinite = niche_with(
        opportunity={"value": float("nan")},
        metrics={
            "n_listings": float("inf"),
            "income_median": float("-inf"),
            "multiple_median": float("nan"),
        },
        rpm_mid=float("inf"),
    )
    response = get(raw_api(nonfinite))
    assert response.status_code in (200, 503)
    assert "nan" not in response.text.lower().replace("financ", "")


def test_numbers_beyond_float_range_read_as_missing_and_the_page_still_renders() -> None:
    huge = 10**400
    cases = [
        niche_page(listings=[market_listing(price_usd=huge, subscribers=huge)]),
        niche_page(listings=[market_listing(real_subscribers=huge, income_monthly_usd=huge)]),
        niche_with(
            metrics={"n_listings": huge, "income_median": huge, "multiple_median": huge},
            rpm_mid=huge,
            trend=huge,
        ),
        niche_with(opportunity={"value": huge}),
    ]
    for detail in cases:
        response = get(raw_api(detail))
        assert response.status_code == 200, detail
    assert "—" in get(raw_api(cases[2])).text


def test_naive_dates_do_not_break_the_page() -> None:
    listings = [market_listing(first_seen_at="2026-11-01T10:00:00", last_seen_at="basura")]
    assert get(api_for(niche_page(listings=listings))).status_code == 200


def test_the_reads_use_a_limit_and_their_failure_does_not_block_the_page() -> None:
    api = api_for(niche_page())
    get(api)
    for path in ("/api/v1/flow-research", "/api/v1/pilots"):
        calls = [c for c in api.calls if c.url.path == path]
        assert calls and all("limit" in c.url.params for c in calls)
    down = api_for(niche_page(), flows=(500, {}), pilots=(500, {}))
    response = get(down)
    assert response.status_code == 200
    assert "No se pudo leer el estado de la investigación" in response.text
    assert "Puntajes" in response.text and "Mercado" in response.text


def test_the_route_does_not_shadow_the_other_niche_routes() -> None:
    web = make_client(api_for(niche_page()))
    assert web.get(
        "/nichos/investigar", params={"etiqueta": LABEL, "formato": "long"}
    ).status_code in (200, 404, 503)
    assert web.post("/nichos/decidir", data={"csrf": "x"}).status_code == 403


def test_hostile_titles_in_listings_are_escaped() -> None:
    text = page(niche_page(listings=[market_listing(HOSTILE)]))
    assert ESCAPED in text and "<script>alert(1)" not in text
