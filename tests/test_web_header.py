"""La cabecera ya no habla del radar ni llama a /status."""

import pytest

from tests.web_helpers import Api, make_client

STATUS = ("GET", "/api/v1/status")


def test_no_page_shows_a_radar_chip_or_calls_status() -> None:
    api = Api(
        {STATUS: (200, {"radar_paused": True}), ("GET", "/api/v1/subniches"): (200, {"items": []})}
    )
    client = make_client(api)
    page = client.get("/subnichos")
    assert page.status_code == 200
    assert "Radar pausado" not in page.text and "Radar activo" not in page.text
    assert api.count("GET", "/api/v1/status") == 0


def test_the_header_keeps_the_brand_and_the_logout_button() -> None:
    api = Api({("GET", "/api/v1/subniches"): (200, {"items": []})})
    html = make_client(api).get("/subnichos").text
    assert "NicheRadar" in html and "Salir" in html


@pytest.mark.parametrize("path", ["/", "/nichos", "/pilotos", "/subnichos"])
def test_no_screen_calls_status_any_more(path: str) -> None:
    api = Api({})
    make_client(api).get(path)
    assert api.count("GET", "/api/v1/status") == 0
