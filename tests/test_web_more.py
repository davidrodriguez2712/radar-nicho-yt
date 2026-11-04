# tests/test_web_more.py
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from tests.web_helpers import Api, csrf_of, make_client, settings


def test_mas_requires_a_session() -> None:
    web = TestClient(create_app(settings()), follow_redirects=False)
    response = web.get("/mas")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_mas_lists_operation_and_a_logout_form() -> None:
    text = make_client(Api()).get("/mas").text
    assert "Más" in text and "Operación" in text
    assert 'href="/operacion"' in text
    assert "Scraper de mercado y subnichos" in text
    assert '<form method="post" action="/salir">' in text
    assert csrf_of(text)
    assert "Análisis de canal" not in text


def test_the_bottom_nav_has_no_disabled_tab_and_mas_links_to_mas() -> None:
    web = make_client(Api())
    for path in ("/mas", "/"):
        text = web.get(path).text
        assert "Próximamente" not in text and "tab--soon" not in text
        assert 'href="/mas"' in text


def test_the_mas_tab_is_active_on_mas_and_operacion() -> None:
    web = make_client(Api())
    active = (
        '<a class="tab tab--on" href="/mas" aria-current="page"><span class="tab__icon" '
        'aria-hidden="true">⋯</span><span class="tab__label">Más</span></a>'
    )
    assert active in web.get("/mas").text
    assert active in web.get("/operacion").text


def test_logout_from_mas_works() -> None:
    web = make_client(Api())
    token = csrf_of(web.get("/mas").text)
    response = web.post("/salir", data={"csrf": token})
    assert response.status_code == 303 and response.headers["location"] == "/login"
