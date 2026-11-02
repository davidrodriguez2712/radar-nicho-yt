# tests/test_web_shape_guard.py
"""Findings of the smoke test: a malformed API payload must never become an unhandled 500."""

import math
from typing import Any

import httpx
import pytest

from nicheradar.web.format import es_int, pct, usd, usd_range
from tests.test_web_smoke_screens import api_for, fixtures
from tests.web_helpers import REPORT_ID, make_client, niche_item

BAD_SHAPE = "formato inesperado"


def page(route: str, mutate: Any) -> httpx.Response:
    data = fixtures()
    mutate(data)
    api = api_for(data)
    web = make_client(api)
    response: httpx.Response = web.get(route)
    return response


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_money_and_counts_that_are_not_finite_render_as_missing(bad: float) -> None:
    assert es_int(bad) == "—"
    assert pct(bad) == "—"
    assert usd(bad) == "—"
    assert usd_range(str(bad), "10") is None


@pytest.mark.parametrize(
    ("route", "mutate"),
    [
        ("/nichos", lambda d: d["niches"].update(items=None)),
        ("/nichos", lambda d: d["niches"]["items"][0].pop("decision")),
        ("/nichos", lambda d: d["flows"].update(items=7)),
        ("/nichos/investigar?etiqueta=x&formato=long", lambda d: d["niche"].update(language_mix=7)),
        ("/subnichos", lambda d: d["subniches"].update(items=None)),
        ("/subnichos", lambda d: d["subniches"]["items"][0].pop("family")),
        ("/subnichos/uno", lambda d: d["card"].pop("hypothesis")),
        (f"/informes/{REPORT_ID}", lambda d: d["report"].update(format=[])),
        (f"/pilotos/autorizar?informe={REPORT_ID}", lambda d: d["report"].update(format={})),
    ],
)
def test_a_payload_with_the_wrong_shape_shows_a_spanish_503_not_a_traceback(
    route: str, mutate: Any
) -> None:
    response = page(route, mutate)
    assert response.status_code == 503, response.text[:300]
    assert BAD_SHAPE in response.text
    assert "Traceback" not in response.text


def test_the_today_screen_survives_a_non_finite_score() -> None:
    def mutate(data: dict[str, Any]) -> None:
        data["niches"]["items"] = [
            niche_item("a", automation={"value": math.inf}),
            niche_item("b", opportunity={"version": "v1", "value": math.nan, "state": "scored"}),
        ]

    assert page("/", mutate).status_code == 200
