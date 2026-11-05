import re

import pytest
from fastapi.testclient import TestClient

from tests.web_helpers import (
    HOSTILE,
    Api,
    Route,
    csrf_of,
    hypothesis_of,
    make_client,
    subniche_card,
    subniche_item,
)

SLUG = "ancient-rome"
BASE = f"/api/v1/subniches/{SLUG}"
CARD = ("GET", BASE)
APPROVAL = ("GET", f"{BASE}/approval")
ACTIONS = {"aprobar": "approve", "pausar": "pause", "reanudar": "resume", "archivar": "archive"}
NOTICE_OF = {
    "aprobar": "aprobado",
    "pausar": "pausado",
    "reanudar": "reanudado",
    "archivar": "archivado",
}


def preview(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "slug": SLUG,
        "status": "proposed",
        "queries": 3,
        "pages": 1,
        "search_units_needed": 300,
        "daily_cap": 100,
        "fits": False,
        "cadence_days": 3,
    }
    return base | over


def card(status: str = "proposed") -> dict[str, object]:
    item = subniche_item(SLUG, status=status, label="Ancient Rome")
    return subniche_card(SLUG, hypothesis=hypothesis_of(item))


def api(status: str = "proposed", pre: Route | None = None, **posts: Route) -> Api:
    routes: dict[tuple[str, str], Route] = {
        CARD: (200, card(status)),
        APPROVAL: pre or (200, preview(status=status)),
        ("GET", "/api/v1/pilots"): (200, {"items": []}),
        ("GET", "/api/v1/status"): (200, {"radar_paused": True}),
    }
    for action in ACTIONS.values():
        routes[("POST", f"{BASE}/{action}")] = posts.get(
            action, (200, {"slug": SLUG, "status": "active"})
        )
    return Api(routes)


def token(web: TestClient) -> str:
    return csrf_of(web.get(f"/subnichos/{SLUG}").text)


def post_count(a: Api) -> int:
    return sum(1 for c in a.calls if c.method == "POST")


def test_m28_shows_the_exact_figures_and_the_warning_when_it_does_not_fit() -> None:
    text = make_client(api()).get(f"/subnichos/{SLUG}/aprobar").text
    for expected in (
        "Aprobar subnicho",
        "Ancient Rome",
        "Consultas",
        "Búsqueda por medición",
        "300 unidades",
        "Tope diario de búsqueda",
        "100 unidades",
        "Con la cuota actual la medición se saltará hasta que haya cupo",
        "Aprobar no mide al instante: la primera medición ocurre en la próxima ronda con cupo.",
        "Confirmar y aprobar",
        "Volver sin cambios",
    ):
        assert expected in text, expected
    assert re.search(r'name="csrf" value="[^"]+"', text)
    assert f'action="/subnichos/{SLUG}/aprobar"' in text


def test_m28_has_no_warning_when_it_fits_and_uses_the_cadence_of_the_api() -> None:
    pre = (200, preview(fits=True, search_units_needed=100, queries=1, cadence_days=7))
    text = make_client(api(pre=pre)).get(f"/subnichos/{SLUG}/aprobar").text
    assert "se saltará" not in text
    assert "100 unidades" in text
    assert "a más tardar en 7 días" in text and "en 3 días" not in text


def test_m28_without_proposed_status_has_a_message_and_no_button() -> None:
    for status in ("active", "paused", "archived"):
        text = make_client(api(status)).get(f"/subnichos/{SLUG}/aprobar").text
        assert "Esta hipótesis ya no está propuesta, así que no se puede aprobar." in text
        assert "Confirmar y aprobar" not in text and "<form" not in text.split("<main")[-1]


def test_m28_unknown_or_malformed_slug_is_404_without_calls() -> None:
    a = api(pre=(404, {"code": "not_found", "message": HOSTILE}))
    web = make_client(a)
    response = web.get(f"/subnichos/{SLUG}/aprobar")
    assert response.status_code == 404 and "HOSTILE" not in response.text
    assert "<script>alert" not in response.text
    before = len(a.calls)
    for bad in ("x" * 61, "Ancient", "a%20b", "-a"):
        assert web.get(f"/subnichos/{bad}/aprobar").status_code == 404, bad
    assert len(a.calls) == before


def test_m28_malformed_payload_is_503_not_500() -> None:
    for body in ({"queries": "x"}, {**preview(), "fits": "si"}, {**preview(), "daily_cap": -1}):
        web = make_client(api(pre=(200, body)))
        assert web.get(f"/subnichos/{SLUG}/aprobar").status_code == 503, body


def test_m28_escapes_the_label_and_survives_a_failed_card_read() -> None:
    item = subniche_item(SLUG, label=HOSTILE, status="proposed")
    a = api()
    a.routes[CARD] = (200, subniche_card(SLUG, hypothesis=hypothesis_of(item)))
    text = make_client(a).get(f"/subnichos/{SLUG}/aprobar").text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text
    a.routes[CARD] = (500, {"detail": "x"})
    page = make_client(a).get(f"/subnichos/{SLUG}/aprobar")
    assert page.status_code == 200 and "300 unidades" in page.text


@pytest.mark.parametrize("action", list(ACTIONS))
def test_every_post_needs_csrf_before_calling_the_api(action: str) -> None:
    a = api()
    web = make_client(a)
    url = f"/subnichos/{SLUG}/{action}"
    data = {"confirmar": "1"}
    assert web.post(url, data=data).status_code == 403
    response = web.post(url, data={**data, "csrf": "wrong"})
    assert response.status_code == 403 and "La solicitud no es válida." in response.text
    assert post_count(a) == 0


@pytest.mark.parametrize("action", list(ACTIONS))
def test_each_post_calls_the_api_and_redirects_with_a_fixed_notice(action: str) -> None:
    a = api()
    web = make_client(a)
    response = web.post(f"/subnichos/{SLUG}/{action}", data={"csrf": token(web), "confirmar": "1"})
    assert response.status_code == 303
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso={NOTICE_OF[action]}"
    assert a.count("POST", f"{BASE}/{ACTIONS[action]}") == 1 and post_count(a) == 1


def test_archiving_without_the_checkbox_returns_to_the_confirmation_without_calling() -> None:
    a = api("active")
    web = make_client(a)
    response = web.post(f"/subnichos/{SLUG}/archivar", data={"csrf": token(web)})
    assert response.status_code == 422
    assert "Entiendo que no se puede deshacer" in response.text
    assert "Marca la casilla para confirmar." in response.text
    assert post_count(a) == 0
    other = web.post(f"/subnichos/{SLUG}/archivar", data={"csrf": token(web), "confirmar": "si"})
    assert other.status_code == 422 and post_count(a) == 0


def test_the_archive_confirmation_screen_has_the_checkbox_and_back_link() -> None:
    text = make_client(api("active")).get(f"/subnichos/{SLUG}/archivar").text
    assert "Entiendo que no se puede deshacer" in text
    assert re.search(r'<input[^>]*type="checkbox"[^>]*name="confirmar"', text)
    assert f'action="/subnichos/{SLUG}/archivar"' in text
    assert "Volver sin cambios" in text and f'href="/subnichos/{SLUG}"' in text
    archived = make_client(api("archived")).get(f"/subnichos/{SLUG}/archivar").text
    assert 'type="checkbox"' not in archived and "ya está archivada" in archived


def test_an_invalid_transition_409_becomes_the_fixed_notice() -> None:
    body = {"code": "invalid_transition", "message": HOSTILE}
    a = api("archived", approve=(409, body))
    web = make_client(a)
    response = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": token(web)})
    assert response.status_code == 303
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=transicion_invalida"
    page = web.get(response.headers["location"]).text
    assert "Esa hipótesis no puede pasar a ese estado." in page
    assert "negrita" not in page and "evil.test" not in page


def test_a_missing_subniche_on_post_is_a_404_page_and_other_failures_a_fixed_notice() -> None:
    gone = (404, {"code": "not_found", "message": HOSTILE})
    web = make_client(api(pause=gone))
    response = web.post(f"/subnichos/{SLUG}/pausar", data={"csrf": token(web)})
    assert response.status_code == 404 and "negrita" not in response.text
    web = make_client(api(pause=(500, {"detail": HOSTILE})))
    response = web.post(f"/subnichos/{SLUG}/pausar", data={"csrf": token(web)})
    assert response.status_code == 303
    assert response.headers["location"].endswith("?aviso=transicion_fallida")
    page = web.get(response.headers["location"]).text
    assert "No se pudo cambiar el estado" in page and "negrita" not in page


def test_weird_slugs_on_post_are_404_without_calls() -> None:
    a = api()
    web = make_client(a)
    csrf = token(web)
    before = len(a.calls)
    for bad in ("x" * 61, "Ancient", "a%20b", "é"):
        for action in ACTIONS:
            r = web.post(f"/subnichos/{bad}/{action}", data={"csrf": csrf, "confirmar": "1"})
            assert r.status_code == 404, (bad, action)
    assert len(a.calls) == before


def test_the_card_buttons_depend_on_the_state() -> None:
    expected = {
        "proposed": ("Revisar y aprobar", "Archivar"),
        "active": ("Pausar", "Archivar"),
        "paused": ("Reanudar", "Archivar"),
        "archived": (),
    }
    every = ("Revisar y aprobar", "Pausar", "Reanudar", "Archivar")
    for status, shown in expected.items():
        text = make_client(api(status)).get(f"/subnichos/{SLUG}").text
        block = text.split("Decisión de la hipótesis")[1].split("</section>")[0]
        labels = re.findall(r'<(?:a|button)[^>]*class="btn[^"]*"[^>]*>([^<]+)</', block)
        assert tuple(labels) == shown, status
        assert "se hará desde aquí cuando esté disponible" not in text
        for name in every:
            assert (name in labels) == (name in shown)
    text = make_client(api("proposed")).get(f"/subnichos/{SLUG}").text
    assert f'href="/subnichos/{SLUG}/aprobar"' in text
    assert f'href="/subnichos/{SLUG}/archivar"' in text
    active = make_client(api("active")).get(f"/subnichos/{SLUG}").text
    assert f'action="/subnichos/{SLUG}/pausar"' in active
    paused = make_client(api("paused")).get(f"/subnichos/{SLUG}").text
    assert f'action="/subnichos/{SLUG}/reanudar"' in paused


def test_the_notices_of_the_card_come_from_fixed_keys() -> None:
    web = make_client(api("active"))
    for key, text in (
        ("aprobado", "Hipótesis aprobada"),
        ("pausado", "Hipótesis pausada"),
        ("reanudado", "Hipótesis reanudada"),
        ("archivado", "Hipótesis archivada"),
        ("transicion_invalida", "Esa hipótesis no puede pasar a ese estado."),
    ):
        assert text in web.get(f"/subnichos/{SLUG}?aviso={key}").text
    page = web.get(f"/subnichos/{SLUG}", params={"aviso": "<script>x</script>"}).text
    assert "<script>x" not in page


def test_approving_does_not_say_it_measured() -> None:
    web = make_client(api())
    page = web.get(f"/subnichos/{SLUG}?aviso=aprobado").text
    assert "no mide al instante" in page.lower()


def test_m28_shows_the_pages_per_query_and_rejects_a_broken_shape() -> None:
    text = make_client(api(pre=(200, preview(pages=2)))).get(f"/subnichos/{SLUG}/aprobar").text
    assert re.search(r"Páginas por consulta</span><span[^>]*>2</span>", text)
    for pages in (0, -1, "1", None, True, 1.5):
        web = make_client(api(pre=(200, preview(pages=pages))))
        assert web.get(f"/subnichos/{SLUG}/aprobar").status_code == 503, pages


def test_m28_never_shows_the_message_of_a_failing_api() -> None:
    for status in (500, 503):
        body = {"code": "zzz", "message": HOSTILE}
        response = make_client(api(pre=(status, body))).get(f"/subnichos/{SLUG}/aprobar")
        assert response.status_code == 503
        assert "negrita" not in response.text and "evil.test" not in response.text


def test_a_409_on_approve_of_an_already_active_subniche_is_a_benign_double_tap() -> None:
    conflict = (409, {"code": "invalid_transition", "message": HOSTILE})
    web = make_client(api("active", approve=conflict))
    response = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": token(web)})
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=aprobado"
    web = make_client(api("archived", approve=conflict))
    response = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": token(web)})
    assert response.headers["location"].endswith("?aviso=transicion_invalida")
    a = api("active", approve=conflict)
    a.routes[CARD] = (500, {"detail": "x"})
    web = make_client(a)
    response = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": "x"})
    assert response.status_code == 403
    a.routes[CARD] = (200, card("active"))
    csrf = token(web)
    a.routes[CARD] = (500, {"detail": "x"})
    response = web.post(f"/subnichos/{SLUG}/aprobar", data={"csrf": csrf})
    assert response.headers["location"].endswith("?aviso=transicion_invalida")


def test_the_archive_screen_tells_a_missing_subniche_from_an_unavailable_api() -> None:
    for status in (404, 422):
        a = api("active")
        a.routes[CARD] = (status, {"code": "not_found", "message": HOSTILE})
        web = make_client(a)
        csrf = csrf_of(make_client(api("active")).get(f"/subnichos/{SLUG}").text)
        assert web.get(f"/subnichos/{SLUG}/archivar").status_code == 404
        assert web.post(f"/subnichos/{SLUG}/archivar", data={"csrf": csrf}).status_code == 403
    for status in (500, 503):
        a = api("active")
        web = make_client(a)
        csrf = token(web)
        a.routes[CARD] = (status, {"code": "zzz", "message": HOSTILE})
        for response in (
            web.get(f"/subnichos/{SLUG}/archivar"),
            web.post(f"/subnichos/{SLUG}/archivar", data={"csrf": csrf}),
        ):
            assert response.status_code == 503, status
            assert "negrita" not in response.text and "No se encontró" not in response.text
    a = api("active")
    web = make_client(a)
    csrf = token(web)
    a.routes[CARD] = (404, {"code": "not_found", "message": HOSTILE})
    response = web.post(f"/subnichos/{SLUG}/archivar", data={"csrf": csrf})
    assert response.status_code == 404 and "No se encontró lo que buscabas." in response.text


def test_m28_does_not_promise_days_when_it_does_not_fit() -> None:
    text = make_client(api()).get(f"/subnichos/{SLUG}/aprobar").text
    assert "a más tardar" not in text
    assert "la primera medición ocurre en la próxima ronda con cupo" in text
    fits = (200, preview(fits=True, search_units_needed=100, cadence_days=3))
    assert (
        "a más tardar en 3 días"
        in make_client(api(pre=fits)).get(f"/subnichos/{SLUG}/aprobar").text
    )


def test_m28_trusts_the_figures_over_the_fits_flag() -> None:
    web = make_client(api(pre=(200, preview(fits=True))))  # 300 needed > 100 cap
    text = web.get(f"/subnichos/{SLUG}/aprobar").text
    assert "se saltará hasta que haya cupo" in text and "a más tardar" not in text
    web = make_client(api(pre=(200, preview(fits=False, search_units_needed=100))))
    assert "se saltará" not in web.get(f"/subnichos/{SLUG}/aprobar").text


def test_a_card_with_an_unknown_status_has_no_lifecycle_buttons() -> None:
    text = make_client(api("weird")).get(f"/subnichos/{SLUG}").text
    block = text.split("Decisión de la hipótesis")[1].split("</section>")[0]
    assert "btn" not in block


def test_the_checkbox_pill_has_spacing() -> None:
    css = open("src/nicheradar/web/static/css/app.css").read()
    assert re.search(r"\.confirm\{[^}]*gap:\d+px", css)
    archive = open("src/nicheradar/web/templates/subnichos/archivar.html").read()
    assert '<label class="confirm"><input type="checkbox" name="confirmar"' in archive
