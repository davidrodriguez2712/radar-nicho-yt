import re
from typing import Any
from uuid import uuid4

import httpx
import pytest

from nicheradar.web.leads import error_text, parse_candidate_ids, read_view
from tests.web_helpers import HOSTILE, Api, csrf_of, make_client

READ_ID = "0b6f3a52-1c1e-4c39-9b0e-2f6a7c1d0001"
CAND_A, CAND_B, CAND_C = (str(uuid4()) for _ in range(3))
TWEET = "https://x.com/autor_x/status/1850000000000000000?s=20"


def candidate(cid: str, value: str, resolution: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": cid,
        "kind": "handle",
        "value": value,
        "found_in": "image",
        "resolution": resolution,
        "channel": None,
        "proposal": None,
    }
    return base | over


def lead(status: str = "ready", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": READ_ID,
        "kind": "tweet",
        "status": status,
        "stage": None,
        "closed": False,
        "created_at": "2026-11-05T12:00:00Z",
        "finished_at": None,
        "tweet": {"author": "autor_x", "url": "https://x.com/autor_x/status/1850000000000000000"},
        "untrusted_text": HOSTILE,
        "error": None,
        "warning": None,
        "candidates": [
            candidate(
                CAND_A,
                "@canal_historia_uno",
                "resolved",
                channel={"id": "UC" + "a" * 22, "title": "Historia", "subscribers": 38000},
            ),
            candidate(CAND_B, "Batallas Olvidadas", "name_only", kind="name", found_in="text"),
            candidate(CAND_C, "@no_existe_123", "not_found"),
        ],
    }
    return base | over


def test_read_view_marks_only_resolved_channels_checkable() -> None:
    view = read_view(lead())
    assert view["state"] == "lista"
    a, b, c = view["candidates"]
    assert (a["checkable"], a["checked"], a["chips"]) == (
        True,
        True,
        ["en la imagen", "resuelto en YouTube"],
    )
    assert a["detail"] == "Historia · 38,0 mil suscriptores"
    assert (b["checkable"], b["can_search"], b["chips"]) == (
        False,
        True,
        ["en el texto", "buscar por nombre (100 u.)"],
    )
    assert (c["checkable"], c["chips"][-1]) == (False, "no encontrado")


def test_read_view_steps_follow_the_stage() -> None:
    view = read_view(lead("running", stage="mentions", candidates=[]))
    assert view["state"] == "leyendo"
    assert view["steps"] == [
        ("Texto del tweet", "hecho"),
        ("Imagen del tweet", "hecho"),
        ("Canales mencionados", "en_curso"),
    ]
    assert read_view(lead("queued", candidates=[]))["state"] == "en_cola"


def test_read_view_survives_odd_payloads() -> None:
    view = read_view({"id": READ_ID, "status": "rarísimo", "candidates": [{"id": "x"}] * 50})
    assert view["state"] == "fallida" and len(view["candidates"]) <= 10


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([CAND_A], [CAND_A]),
        ([CAND_A, CAND_A], [CAND_A]),
        ([], None),
        (["no-uuid"], None),
        ([str(uuid4()) for _ in range(11)], None),
    ],
)
def test_parse_candidate_ids(values: list[str], expected: list[str] | None) -> None:
    assert parse_candidate_ids(values) == expected


def test_error_text_is_fixed() -> None:
    assert "borrado" in error_text("tweet_unavailable")
    assert error_text("boom: secreto") == error_text(None) == "No se pudo leer."


def api_for(read: dict[str, Any]) -> Api:
    return Api(
        {
            ("POST", "/api/v1/leads/tweets"): (
                202,
                {"id": READ_ID, "status": "queued", "created": True},
            ),
            ("GET", f"/api/v1/leads/{READ_ID}"): (200, read),
            ("POST", f"/api/v1/leads/{READ_ID}/names"): (202, {"queued": 1}),
            ("POST", f"/api/v1/leads/{READ_ID}/proposals"): (
                200,
                {
                    "items": [
                        {"candidate_id": CAND_A, "outcome": "queued", "proposal_id": str(uuid4())}
                    ]
                },
            ),
            ("POST", f"/api/v1/leads/{READ_ID}/close"): (200, {"id": READ_ID, "closed": True}),
        }
    )


def test_share_page_offers_read_tweet_with_csrf_and_nonce() -> None:
    web = make_client(api_for(lead()))
    page = web.get("/compartir", params={"url": TWEET})
    assert page.status_code == 200 and "Leer tweet" in page.text
    assert 'action="/compartir/tweet"' in page.text and re.search(
        r'name="nonce" value="[0-9a-f]{32}"', page.text
    )
    assert "todavía no se leen" not in page.text


def test_read_tweet_posts_once_per_nonce_and_redirects() -> None:
    api = api_for(lead())
    web = make_client(api)
    page = web.get("/compartir", params={"url": TWEET})
    form = {"csrf": csrf_of(page.text), "nonce": "a" * 32, "url": TWEET}
    first = web.post("/compartir/tweet", data=form)
    second = web.post("/compartir/tweet", data=form)
    assert first.status_code == second.status_code == 303
    assert first.headers["location"] == f"/lecturas/{READ_ID}"
    keys = [c.headers["idempotency-key"] for c in api.calls if c.url.path == "/api/v1/leads/tweets"]
    assert len(keys) == 2 and keys[0] == keys[1]


def test_read_tweet_without_csrf_is_403_and_sends_nothing() -> None:
    api = api_for(lead())
    web = make_client(api)
    response = web.post("/compartir/tweet", data={"csrf": "x", "nonce": "a" * 32, "url": TWEET})
    assert response.status_code == 403 and api.count("POST", "/api/v1/leads/tweets") == 0


def test_daily_limit_is_shown_with_the_fixed_text() -> None:
    api = api_for(lead())
    api.routes[("POST", "/api/v1/leads/tweets")] = (
        429,
        {"code": "daily_limit", "message": "texto de la API"},
    )
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    response = web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "b" * 32, "url": TWEET})
    assert "Se llegó al tope diario de lecturas de tweets." in response.text
    assert "texto de la API" not in response.text


def test_queued_read_polls_and_shows_the_fallback_help() -> None:
    page = make_client(api_for(lead("queued", candidates=[]))).get(f"/lecturas/{READ_ID}")
    assert page.status_code == 200 and "Leyendo el tweet" in page.text and "En cola" in page.text
    assert 'hx-trigger="every 5s"' in page.text
    assert "Mantén pulsada la imagen del tweet y compártela con NicheRadar." in page.text
    assert 'href="https://x.com/autor_x/status/1850000000000000000"' in page.text


def test_an_image_read_says_image_not_tweet() -> None:
    queued = lead("queued", kind="image", tweet=None, candidates=[], untrusted_text=None)
    page = make_client(api_for(queued)).get(f"/lecturas/{READ_ID}")
    assert "Leyendo la imagen" in page.text and "Leyendo el tweet" not in page.text
    assert "Abrir el tweet en X" not in page.text
    failed = lead(
        "failed",
        kind="image",
        tweet=None,
        candidates=[],
        untrusted_text=None,
        error={"code": "abandoned", "message": "x"},
    )
    page = make_client(api_for(failed)).get(f"/lecturas/{READ_ID}")
    assert "No se pudo leer la imagen" in page.text


def test_an_image_without_the_vision_model_says_so_in_image_terms() -> None:
    failed = lead(
        "failed",
        kind="image",
        tweet=None,
        candidates=[],
        untrusted_text=None,
        error={"code": "vision_not_configured", "message": "x"},
    )
    page = make_client(api_for(failed)).get(f"/lecturas/{READ_ID}")
    assert "No se pudo leer la imagen: el modelo de visión no está configurado." in page.text
    assert "solo se leyeron los enlaces del texto" not in page.text


def test_ready_read_lists_channels_escaped_and_without_polling() -> None:
    page = make_client(api_for(lead())).get(f"/lecturas/{READ_ID}")
    assert "Canales encontrados (3)" in page.text and 'hx-trigger="every 5s"' not in page.text
    assert "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text
    assert "Texto del tweet (de un tercero, sin verificar)" in page.text
    assert "Proponer los canales marcados" in page.text  # rótulo neutro: no cuenta nada
    assert f'name="candidate" value="{CAND_A}" checked' in page.text
    boxes = re.findall(r'<input type="checkbox" name="candidate" value="([^"]+)"', page.text)
    assert boxes == [CAND_A]  # ni el nombre ni el no encontrado tienen casilla
    assert f'name="buscar" value="{CAND_B}"' in page.text


def test_failed_read_shows_the_fixed_message_and_the_fallback() -> None:
    failed = lead(
        "failed",
        candidates=[],
        untrusted_text=None,
        error={"code": "tweet_unavailable", "message": "texto de la API"},
    )
    page = make_client(api_for(failed)).get(f"/lecturas/{READ_ID}")
    assert "puede estar borrado" in page.text and "texto de la API" not in page.text


def test_name_search_and_proposals_are_separate_posts() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    named = web.post(
        f"/lecturas/{READ_ID}/nombre", data={"csrf": csrf, "candidate": CAND_A, "buscar": CAND_B}
    )
    assert (
        named.status_code == 303
        and named.headers["location"] == f"/lecturas/{READ_ID}?aviso=buscando"
    )
    assert named.status_code == 303 and api.count("POST", f"/api/v1/leads/{READ_ID}/names") == 1
    assert api.count("POST", f"/api/v1/leads/{READ_ID}/proposals") == 0
    names = next(c for c in api.calls if c.url.path.endswith("/names"))
    assert names.content == b'{"candidate_ids":["' + CAND_B.encode() + b'"]}'
    proposed = web.post(f"/lecturas/{READ_ID}/proponer", data={"csrf": csrf, "candidate": [CAND_A]})
    assert (
        proposed.status_code == 303
        and proposed.headers["location"] == f"/lecturas/{READ_ID}/propuestas?creadas=1&omitidas=0"
    )
    sent = next(c for c in api.calls if c.url.path.endswith("/proposals"))
    assert sent.content == b'{"candidate_ids":["' + CAND_A.encode() + b'"]}'


def test_propose_without_selection_or_with_bad_ids_sends_nothing() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    for data in ({"csrf": csrf}, {"csrf": csrf, "candidate": ["no-uuid"]}):
        response = web.post(f"/lecturas/{READ_ID}/proponer", data=data)
        assert response.status_code == 303 and "aviso=sin_seleccion" in response.headers["location"]
    assert api.count("POST", f"/api/v1/leads/{READ_ID}/proposals") == 0


def test_proposals_screen_lists_states() -> None:
    with_proposals = lead(
        candidates=[
            candidate(
                CAND_A,
                "@canal_historia_uno",
                "resolved",
                channel={"id": "UC" + "a" * 22, "title": "Historia", "subscribers": 1},
                proposal={"id": str(uuid4()), "status": "queued"},
            ),
            candidate(
                CAND_B,
                "Batallas Olvidadas",
                "resolved",
                kind="name",
                channel={"id": "UC" + "b" * 22, "title": "Batallas", "subscribers": 1},
                proposal={"id": str(uuid4()), "status": "succeeded"},
            ),
        ]
    )
    page = make_client(api_for(with_proposals)).get(f"/lecturas/{READ_ID}/propuestas")
    assert "1 propuesta en preparación" in page.text  # solo cuenta las que siguen en preparación
    assert "En cola" in page.text and "Lista" in page.text and "Ver propuestas" in page.text
    assert "Aprobar es lo que gasta cuota de búsqueda." in page.text
    assert 'href="/subnichos"' in page.text  # no hay lista en /subnichos/propuestas
    assert 'href="/subnichos/propuestas/' in page.text


def test_cancel_closes_and_bad_ids_are_404() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    assert (
        web.post(f"/lecturas/{READ_ID}/cancelar", data={"csrf": csrf}).headers["location"]
        == "/subnichos"
    )
    assert web.get("/lecturas/no-es-uuid").status_code == 404
    assert web.get(f"/lecturas/{READ_ID}/../../x").status_code == 404


def test_api_down_is_503_with_notice() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("caída", request=request)

    page = make_client(Api({("GET", f"/api/v1/leads/{READ_ID}"): down})).get(f"/lecturas/{READ_ID}")
    assert page.status_code == 503 and "API no disponible" in page.text


# --- casos hostiles y de borde ---------------------------------------------------------------


def post_api(**routes: Any) -> Api:
    api = api_for(lead())
    for path, route in routes.items():
        api.routes[("POST", f"/api/v1/leads/{path}")] = route
    return api


def test_hostile_tweet_text_and_channel_names_are_escaped_and_cleaned() -> None:
    hostile = lead(
        untrusted_text="hola <img src=x onerror=alert(1)>\x00\u202eoculto\u202c fin",
        candidates=[
            candidate(
                CAND_A,
                "@x<b>y</b>\u202e",
                "resolved",
                channel={"id": "UC" + "a" * 22, "title": "<script>t</script>", "subscribers": 5},
            )
        ],
    )
    page = make_client(api_for(hostile)).get(f"/lecturas/{READ_ID}")
    assert "<img" not in page.text and "<script>t" not in page.text and "<b>y" not in page.text
    assert "\x00" not in page.text and "\u202e" not in page.text and "\u202c" not in page.text
    assert "&lt;img" in page.text


def test_ten_candidates_at_most_and_ambiguous_is_checkable_but_unchecked() -> None:
    many = [candidate(str(uuid4()), f"@canal_{i}_xx", "not_found") for i in range(14)]
    ambiguous = candidate(
        CAND_A,
        "@raro_canal",
        "ambiguous",
        channel={"id": "UC" + "c" * 22, "title": "Raro", "subscribers": 10},
    )
    view = read_view(lead(candidates=[ambiguous, *many]))
    assert len(view["candidates"]) == 10
    first = view["candidates"][0]
    assert (first["checkable"], first["checked"]) == (True, False) and "ambiguo" in first["chips"][
        -1
    ]
    assert view["selected"] == 0


def test_searching_candidate_never_polls_the_form() -> None:
    searching = lead(
        candidates=[
            candidate(
                CAND_A,
                "@canal_historia_uno",
                "resolved",
                channel={"id": "UC" + "a" * 22, "title": "Historia", "subscribers": 5},
            ),
            candidate(CAND_B, "Batallas", "name_queued", kind="name"),
        ]
    )
    web = make_client(api_for(searching))
    page = web.get(f"/lecturas/{READ_ID}")
    assert "buscando por nombre" in page.text and "Actualizar" in page.text
    assert 'hx-trigger="every 5s"' not in page.text and "hx-get" not in page.text
    fragment = web.get(f"/lecturas/{READ_ID}", headers={"HX-Request": "true"})
    assert "hx-get" not in fragment.text


def test_polled_element_never_contains_the_form_or_checkboxes() -> None:
    web = make_client(api_for(lead("queued", candidates=[])))
    html = web.get(f"/lecturas/{READ_ID}").text
    polled = html[html.index("hx-get") :]
    assert "<form" not in polled and 'type="checkbox"' not in polled
    fragment = web.get(f"/lecturas/{READ_ID}", headers={"HX-Request": "true"})
    assert 'type="checkbox"' not in fragment.text and "<form" not in fragment.text


def test_failed_read_with_unknown_code_shows_generic_text() -> None:
    failed = lead(
        "failed",
        candidates=[],
        untrusted_text=None,
        error={"code": "boom_secreto", "message": "texto de la API"},
    )
    page = make_client(api_for(failed)).get(f"/lecturas/{READ_ID}")
    assert "No se pudo leer." in page.text and "boom_secreto" not in page.text
    assert 'hx-trigger="every 5s"' not in page.text
    assert "/compartir?url=" in page.text  # volver a intentar


def test_polling_is_bounded_and_carries_a_counter() -> None:
    web = make_client(api_for(lead("queued", candidates=[])))
    assert "?n=1" in web.get(f"/lecturas/{READ_ID}").text
    assert "?n=6" in web.get(f"/lecturas/{READ_ID}", params={"n": "5"}).text
    spent = web.get(f"/lecturas/{READ_ID}", params={"n": "120"})
    assert 'hx-trigger="every 5s"' not in spent.text and "sondeo-agotado" in spent.text
    assert (
        'hx-trigger="every 5s"' not in web.get(f"/lecturas/{READ_ID}", params={"n": "9" * 40}).text
    )


def test_polling_fragment_errors() -> None:
    hx = {"HX-Request": "true"}
    gone = make_client(
        Api({("GET", f"/api/v1/leads/{READ_ID}"): (404, {"detail": {"code": "not_found"}})})
    )
    assert gone.get(f"/lecturas/{READ_ID}", headers=hx).status_code == 286
    flaky = make_client(Api({("GET", f"/api/v1/leads/{READ_ID}"): (500, {"x": 1})}))
    assert flaky.get(f"/lecturas/{READ_ID}", headers=hx).status_code == 204
    ok = make_client(api_for(lead("queued", candidates=[]))).get(f"/lecturas/{READ_ID}", headers=hx)
    assert ok.status_code == 200 and "<html" not in ok.text and "Leyendo el tweet" in ok.text


def test_closed_read_offers_nothing_to_post() -> None:
    page = make_client(api_for(lead(closed=True))).get(f"/lecturas/{READ_ID}")
    assert "La lectura ya está cerrada." in page.text
    assert "/proponer" not in page.text and "/cancelar" not in page.text
    assert (
        'hx-trigger="every 5s"'
        not in make_client(api_for(lead("queued", closed=True, candidates=[])))
        .get(f"/lecturas/{READ_ID}")
        .text
    )


def test_non_uuid_ids_never_reach_the_api() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    before = len(api.calls)
    for path in ("no-es-uuid", READ_ID.upper(), "0b6f3a52-1c1e-4c39-9b0e-2f6a7c1d000%00"):
        assert web.get(f"/lecturas/{path}").status_code == 404
        assert web.get(f"/lecturas/{path}/propuestas").status_code == 404
        for action in ("nombre", "proponer", "cancelar"):
            assert web.post(f"/lecturas/{path}/{action}", data={"csrf": csrf}).status_code == 404
    assert len(api.calls) == before


def test_posts_without_csrf_are_403_and_send_nothing() -> None:
    api = api_for(lead())
    web = make_client(api)
    for action in ("nombre", "proponer", "cancelar"):
        response = web.post(
            f"/lecturas/{READ_ID}/{action}",
            data={"csrf": "x", "buscar": CAND_B, "candidate": [CAND_A]},
        )
        assert response.status_code == 403
    assert [c for c in api.calls if c.method == "POST" and "/leads/" in c.url.path] == []


def test_name_search_with_bad_buscar_sends_nothing() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    for data in (
        {"csrf": csrf},
        {"csrf": csrf, "buscar": "x"},
        {"csrf": csrf, "candidate": [CAND_A]},
    ):
        response = web.post(f"/lecturas/{READ_ID}/nombre", data=data)
        assert response.status_code == 303 and "aviso=error" in response.headers["location"]
    assert api.count("POST", f"/api/v1/leads/{READ_ID}/names") == 0


def test_propose_with_eleven_ids_sends_nothing_and_dedupes_repeats() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    eleven = [str(uuid4()) for _ in range(11)]
    assert (
        "sin_seleccion"
        in web.post(
            f"/lecturas/{READ_ID}/proponer", data={"csrf": csrf, "candidate": eleven}
        ).headers["location"]
    )
    assert api.count("POST", f"/api/v1/leads/{READ_ID}/proposals") == 0
    web.post(f"/lecturas/{READ_ID}/proponer", data={"csrf": csrf, "candidate": [CAND_A, CAND_A]})
    sent = next(c for c in api.calls if c.url.path.endswith("/proposals"))
    assert sent.content == b'{"candidate_ids":["' + CAND_A.encode() + b'"]}'


def test_propose_nothing_queued_goes_back_with_a_notice() -> None:
    api = post_api(
        **{
            f"{READ_ID}/proposals": (
                200,
                {"items": [{"candidate_id": CAND_A, "outcome": "duplicate", "proposal_id": None}]},
            )
        }
    )
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    response = web.post(f"/lecturas/{READ_ID}/proponer", data={"csrf": csrf, "candidate": [CAND_A]})
    assert response.headers["location"] == f"/lecturas/{READ_ID}?aviso=sin_propuestas"


def test_action_failures_redirect_with_fixed_notices() -> None:
    api = post_api(
        **{
            f"{READ_ID}/names": (409, {"code": "read_closed", "message": "secreto del servidor"}),
            f"{READ_ID}/proposals": (500, {"x": 1}),
            f"{READ_ID}/close": (500, {"x": 1}),
        }
    )
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    forms: list[tuple[str, dict[str, Any]]] = [
        ("nombre", {"buscar": CAND_B}),
        ("proponer", {"candidate": [CAND_A]}),
        ("cancelar", {}),
    ]
    for action, data in forms:
        response = web.post(f"/lecturas/{READ_ID}/{action}", data={"csrf": csrf} | data)
        assert response.status_code == 303 and response.headers["location"].startswith(
            f"/lecturas/{READ_ID}?aviso="
        )
    page = web.get(f"/lecturas/{READ_ID}", params={"aviso": "error"})
    assert "No se pudo completar la acción." in page.text
    assert "secreto" not in web.get(f"/lecturas/{READ_ID}", params={"aviso": "<script>"}).text
    assert 'role="status"' not in web.get(f"/lecturas/{READ_ID}", params={"aviso": "nope"}).text


def test_read_tweet_rejects_bad_nonce_and_non_tweet_links() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    assert (
        web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "zz", "url": TWEET}).status_code
        == 403
    )
    other = web.post(
        "/compartir/tweet", data={"csrf": csrf, "nonce": "a" * 32, "url": "https://example.com/x"}
    )
    assert other.status_code == 422 and "Ese enlace no es un tweet de X." in other.text
    assert api.count("POST", "/api/v1/leads/tweets") == 0


def test_read_tweet_key_follows_the_tweet_not_the_nonce_reuse() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "a" * 32, "url": TWEET})
    web.post(
        "/compartir/tweet",
        data={"csrf": csrf, "nonce": "a" * 32, "url": TWEET.replace("1850", "1851")},
    )
    calls = [c for c in api.calls if c.url.path == "/api/v1/leads/tweets"]
    assert calls[0].headers["idempotency-key"] != calls[1].headers["idempotency-key"]


def test_read_tweet_transient_failure_keeps_the_nonce_and_503() -> None:
    api = api_for(lead())
    api.routes[("POST", "/api/v1/leads/tweets")] = (502, {"x": 1})
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    response = web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "c" * 32, "url": TWEET})
    assert response.status_code == 503 and 'name="nonce" value="' + "c" * 32 + '"' in response.text
    assert "Leer tweet" in response.text


def test_read_tweet_domain_rejection_takes_a_fresh_nonce_and_reading_disabled_is_fixed() -> None:
    api = api_for(lead())
    api.routes[("POST", "/api/v1/leads/tweets")] = (
        503,
        {"code": "reading_disabled", "message": "interno"},
    )
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    response = web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "d" * 32, "url": TWEET})
    assert (
        response.status_code == 503
        and "no está activa" in response.text
        and "interno" not in response.text
    )
    assert "d" * 32 not in response.text


def test_read_tweet_with_a_non_uuid_id_in_the_answer_is_a_503() -> None:
    api = api_for(lead())
    api.routes[("POST", "/api/v1/leads/tweets")] = (202, {"id": "../../x", "status": "queued"})
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    response = web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "e" * 32, "url": TWEET})
    assert response.status_code == 503


def test_partial_result_is_passed_as_bounded_counts_and_shown() -> None:
    items = [
        {"candidate_id": CAND_A, "outcome": "queued", "proposal_id": str(uuid4())},
        {"candidate_id": CAND_B, "outcome": "duplicate", "proposal_id": None},
        {"candidate_id": CAND_C, "outcome": "daily_limit", "proposal_id": None},
    ]
    api = post_api(**{f"{READ_ID}/proposals": (200, {"items": items})})
    web = make_client(api)
    csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
    response = web.post(
        f"/lecturas/{READ_ID}/proponer", data={"csrf": csrf, "candidate": [CAND_A, CAND_B, CAND_C]}
    )
    assert response.headers["location"] == f"/lecturas/{READ_ID}/propuestas?creadas=1&omitidas=2"
    page = web.get(f"/lecturas/{READ_ID}/propuestas", params={"creadas": "1", "omitidas": "2"})
    assert "Se creó 1 propuesta; 2 se omitieron (duplicadas, sin cupo o sin resolver)." in page.text
    for bad in (
        {"creadas": "99", "omitidas": "1"},
        {"creadas": "x"},
        {"creadas": "-1", "omitidas": "0"},
    ):
        shown = web.get(f"/lecturas/{READ_ID}/propuestas", params=bad)
        assert "Se creó" not in shown.text and "Se crearon" not in shown.text
    all_ok = web.get(f"/lecturas/{READ_ID}/propuestas", params={"creadas": "3", "omitidas": "0"})
    assert "Se crearon 3 propuestas." in all_ok.text and "omitieron" not in all_ok.text


def test_error_codes_map_to_their_own_fixed_notices() -> None:
    def notice(path: str, status: int, code: str, data: dict[str, Any], action: str) -> str:
        api = post_api(
            **{f"{READ_ID}/{path}": (status, {"code": code, "message": "HOSTIL <b>x</b>"})}
        )
        web = make_client(api)
        csrf = csrf_of(web.get(f"/lecturas/{READ_ID}").text)
        location = web.post(f"/lecturas/{READ_ID}/{action}", data={"csrf": csrf} | data).headers[
            "location"
        ]
        page = web.get(location.replace("/propuestas", ""))
        assert "HOSTIL" not in page.text
        return str(page.text)

    twice = notice("names", 422, "invalid_candidates", {"buscar": CAND_B}, "nombre")
    assert "La búsqueda por nombre ya está en curso." in twice
    closed = notice("names", 409, "read_closed", {"buscar": CAND_B}, "nombre")
    assert "La lectura ya está cerrada." in closed
    wrong = notice("proposals", 422, "invalid_candidates", {"candidate": [CAND_A]}, "proponer")
    assert "no pertenecen a esta lectura" in wrong
    limit = notice("proposals", 429, "daily_limit", {"candidate": [CAND_A]}, "proponer")
    assert "Se llegó al tope diario de propuestas." in limit
    early = notice("proposals", 409, "not_ready", {"candidate": [CAND_A]}, "proponer")
    assert "La lectura todavía no terminó." in early


def test_wrapped_error_details_never_leak_their_message() -> None:
    hostile = {"detail": {"code": "x_raro", "message": "HOSTIL <script>1</script>"}}
    web = make_client(Api({("GET", f"/api/v1/leads/{READ_ID}"): (409, hostile)}))
    page = web.get(f"/lecturas/{READ_ID}")
    assert page.status_code == 503 and "HOSTIL" not in page.text
    api = api_for(lead())
    api.routes[("POST", "/api/v1/leads/tweets")] = (409, {"detail": {"message": "HOSTIL <b>"}})
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    sent = web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "f" * 32, "url": TWEET})
    assert sent.status_code == 503 and "HOSTIL" not in sent.text


def test_same_tweet_with_other_query_gives_the_same_body_and_key() -> None:
    api = api_for(lead())
    web = make_client(api)
    csrf = csrf_of(web.get("/compartir", params={"url": TWEET}).text)
    for url in (
        TWEET,
        "https://x.com/autor_x/status/1850000000000000000?s=46&t=zzz",
        "https://twitter.com/autor_x/status/1850000000000000000",
    ):
        web.post("/compartir/tweet", data={"csrf": csrf, "nonce": "a" * 32, "url": url})
    calls = [c for c in api.calls if c.url.path == "/api/v1/leads/tweets"]
    canonical = b'{"url":"https://x.com/autor_x/status/1850000000000000000"}'
    assert [c.content for c in calls] == [canonical] * 3
    assert len({c.headers["idempotency-key"] for c in calls}) == 1
