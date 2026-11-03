# tests/test_web_pilot_actions.py
import html
import json
import re
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from nicheradar.web.client import MESSAGES
from nicheradar.web.pilot_actions import allowed, validate_note
from tests.web_helpers import HOSTILE, Api, csrf_of, make_client, pilot_detail

PID = "pil_20261102_historia"
DETAIL = ("GET", f"/api/v1/pilots/{PID}")
DECISION = ("POST", f"/api/v1/pilots/{PID}/decision")
CANCEL = ("POST", f"/api/v1/pilots/{PID}/cancel")
SUMMARY = ("GET", f"/api/v1/pilots/{PID}/closing-summary")
STATUS = ("GET", "/api/v1/status")
ESCAPED = html.escape(HOSTILE)
CONSEQUENCE = {
    "seguir": "El piloto continúa hasta el siguiente hito.",
    "cerrar": "Esto cierra el piloto y no se puede deshacer. Se genera el resumen de cierre.",
    "cancelar": "Esto cancela el piloto antes de producir. El canal queda libre.",
}
PATHS = {
    "seguir": f"/pilotos/{PID}/decidir?accion=seguir",
    "cerrar": f"/pilotos/{PID}/decidir?accion=cerrar",
    "cancelar": f"/pilotos/{PID}/cancelar",
}
OPEN_STATE = {"seguir": "decision_pendiente", "cerrar": "en_ejecucion", "cancelar": "autorizado"}
ALREADY_CLOSED = "Este piloto ya está cerrado."
LIMIT = 1500


def boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def recorder(bodies: list[dict[str, Any]], status: int = 200, body: Any = None) -> Any:
    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(status, json=body if body is not None else {"pilot_id": PID})

    return accept


def switchable(status: str, extra: dict[tuple[str, str], Any]) -> tuple[Api, dict[str, Any]]:
    """An API whose pilot can change state or go down after the confirmation page was served."""
    state: dict[str, Any] = {"status": status, "down": False}

    def detail(request: httpx.Request) -> httpx.Response:
        if state["down"]:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=pilot_detail(status=state["status"]))

    routes: dict[tuple[str, str], Any] = {
        DETAIL: detail,
        STATUS: (200, {"radar_paused": False}),
    } | extra
    return Api(routes), state


def api_with(status: str, extra: dict[tuple[str, str], Any]) -> Api:
    return Api(
        {DETAIL: (200, pilot_detail(status=status)), STATUS: (200, {"radar_paused": False})} | extra
    )


def block(text: str, element_id: str) -> str:
    found = re.search(rf"<(\w+)[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>(.*?)</\1>", text, re.S)
    assert found, f"no #{element_id} in the page"
    return str(found.group(2))


def flat(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def token_of(web: TestClient, path: str) -> str:
    response = web.get(path)
    assert response.status_code == 200, response.text
    return csrf_of(response.text)


def post_decision(
    web: TestClient, csrf: str, action: str = "seguir", **fields: str
) -> httpx.Response:
    data = {"csrf": csrf, "note": "Va bien"} | fields
    response: httpx.Response = web.post(f"/pilotos/{PID}/decidir?accion={action}", data=data)
    return response


def post_cancel(web: TestClient, csrf: str, **fields: str) -> httpx.Response:
    data = {"csrf": csrf, "reason": "Ya no"} | fields
    response: httpx.Response = web.post(f"/pilotos/{PID}/cancelar", data=data)
    return response


def writes(api: Api) -> int:
    return sum(1 for c in api.calls if c.method == "POST")


@pytest.mark.parametrize("action", ["seguir", "cerrar", "cancelar"])
def test_the_confirmation_page_states_the_consequence_and_has_a_note_field_and_csrf(
    action: str,
) -> None:
    pilot = pilot_detail(
        status=OPEN_STATE[action], niche_label=HOSTILE, target_channel="canal <b>x</b>"
    )
    api = Api({DETAIL: (200, pilot), STATUS: (200, {"radar_paused": False})})
    response = make_client(api).get(PATHS[action])
    assert response.status_code == 200
    text = response.text
    assert flat(block(text, "consecuencia")) == CONSEQUENCE[action]
    form = block(text, "confirmar-form")
    field = "reason" if action == "cancelar" else "note"
    assert re.search(r'<textarea[^>]*\bname="' + field + '"', form)
    assert re.search(r"<textarea[^>]*\brequired\b", form)
    assert f'maxlength="{LIMIT}"' in form
    assert re.search(r'<input type="hidden" name="csrf" value="[^"]+"', form)
    target = f"/pilotos/{PID}/cancelar" if action == "cancelar" else PATHS[action]
    assert f'action="{target}"' in text
    summary = block(text, "piloto")
    assert ESCAPED in summary and "canal &lt;b&gt;x&lt;/b&gt;" in summary
    assert "<script>" not in text and "<b>x</b>" not in text
    assert api.count("GET", f"/api/v1/pilots/{PID}") == 1 and writes(api) == 0


@pytest.mark.parametrize(
    ("action", "status", "reason"),
    [
        ("seguir", "en_ejecucion", "Solo se puede seguir una decisión pendiente."),
        ("seguir", "autorizado", "Solo se puede seguir una decisión pendiente."),
        ("cerrar", "autorizado", "Un piloto en preparación se cancela, no se cierra."),
        ("cerrar", "entregado", "Un piloto en preparación se cancela, no se cierra."),
        ("cerrar", "cerrado", ALREADY_CLOSED),
        ("cancelar", "cerrado", ALREADY_CLOSED),
        ("seguir", "cerrado", ALREADY_CLOSED),
        ("cerrar", "cancelado", "Este piloto ya está cancelado."),
        ("cancelar", "en_ejecucion", "Solo se cancela un piloto antes de que se ejecute."),
        ("cancelar", "decision_pendiente", "Solo se cancela un piloto antes de que se ejecute."),
    ],
)
def test_a_disallowed_state_never_shows_the_form(action: str, status: str, reason: str) -> None:
    assert not allowed(action, status)
    api = api_with(status, {})
    response = make_client(api).get(PATHS[action])
    assert response.status_code == 409
    assert flat(block(response.text, "bloqueo")) == reason
    assert "<textarea" not in response.text and 'id="confirmar-form"' not in response.text
    assert writes(api) == 0


@pytest.mark.parametrize(
    "query", ["", "?accion=", "?accion=abrir", "?accion=SEGUIR", "?accion=cancelar", "?accion=%00"]
)
def test_an_unknown_action_is_404_and_never_shows_the_form(query: str) -> None:
    api = api_with("decision_pendiente", {})
    response = make_client(api).get(f"/pilotos/{PID}/decidir{query}")
    assert response.status_code == 404
    assert "<textarea" not in response.text and api.count("POST", DECISION[1]) == 0


def test_allowed_matches_the_api_transitions() -> None:
    states = (
        "autorizado",
        "entregado",
        "en_ejecucion",
        "decision_pendiente",
        "cerrado",
        "cancelado",
    )
    assert [s for s in states if allowed("seguir", s)] == ["decision_pendiente"]
    assert [s for s in states if allowed("cerrar", s)] == ["en_ejecucion", "decision_pendiente"]
    assert [s for s in states if allowed("cancelar", s)] == ["autorizado", "entregado"]
    assert not allowed("abrir", "autorizado") and not allowed("seguir", "")


def test_a_missing_pilot_or_an_outage_on_the_confirmation_page_has_no_form() -> None:
    missing = Api({DETAIL: (404, {"detail": {"code": "not_found", "message": "x"}})})
    response = make_client(missing).get(PATHS["seguir"])
    assert response.status_code == 404 and "<textarea" not in response.text
    down = Api({DETAIL: boom})
    response = make_client(down).get(PATHS["cancelar"])
    assert response.status_code == 503 and MESSAGES["unavailable"] in response.text
    assert "<textarea" not in response.text


@pytest.mark.parametrize(("action", "key"), [("seguir", "seguido"), ("cerrar", "cerrado")])
def test_posting_a_decision_sends_the_pilot_id_decision_and_note_and_redirects_with_a_notice(
    action: str, key: str
) -> None:
    bodies: list[dict[str, Any]] = []
    api = api_with(OPEN_STATE[action], {DECISION: recorder(bodies)})
    web = make_client(api)
    response = post_decision(web, token_of(web, PATHS[action]), action, note="  Va bien\n ")
    assert response.status_code == 303
    assert response.headers["location"] == f"/pilotos/{PID}?aviso={key}"
    assert bodies == [{"decision": action, "note": "Va bien", "actor": "humano"}]
    assert api.count("POST", f"/api/v1/pilots/{PID}/decision") == 1


def test_the_actor_and_decision_come_from_the_server_not_the_form() -> None:
    bodies: list[dict[str, Any]] = []
    api = api_with("decision_pendiente", {DECISION: recorder(bodies), CANCEL: recorder(bodies)})
    web = make_client(api)
    csrf = token_of(web, PATHS["seguir"])
    hostile = {
        "actor": "root",
        "decision": "cerrar",
        "accion": "cerrar",
        "status": "cerrado",
        "pilot_id": "pil_20261102_otro",
        "note": "ok",
    }
    response = post_decision(web, csrf, "seguir", **hostile)
    assert response.status_code == 303
    assert bodies == [{"decision": "seguir", "note": "ok", "actor": "humano"}]
    assert api.calls[-1].url.path.endswith(f"/pilots/{PID}/decision")
    api2 = api_with("autorizado", {CANCEL: recorder(bodies)})
    web2 = make_client(api2)
    bodies.clear()
    response = post_cancel(
        web2, token_of(web2, PATHS["cancelar"]), actor="root", note="x", status="cerrado"
    )
    assert response.status_code == 303
    assert bodies == [{"reason": "Ya no", "actor": "humano"}]


@pytest.mark.parametrize("action", ["seguir", "cerrar", "cancelar"])
def test_the_note_must_be_1_to_1500_characters_and_blank_notes_are_rejected_before_the_api(
    action: str,
) -> None:
    bodies: list[dict[str, Any]] = []
    route = CANCEL if action == "cancelar" else DECISION
    api = api_with(OPEN_STATE[action], {route: recorder(bodies)})
    web = make_client(api)
    csrf = token_of(web, PATHS[action])
    field = "reason" if action == "cancelar" else "note"

    def send(value: str) -> httpx.Response:
        if action == "cancelar":
            return post_cancel(web, csrf, reason=value)
        return post_decision(web, csrf, action, note=value)

    for bad in ("", "   ", "\n\n", " \r\n \t\r\n", "x" * (LIMIT + 1), "  " + "x" * LIMIT + "é"):
        response = send(bad)
        assert response.status_code == 422, repr(bad)
        assert str(LIMIT) in block(response.text, "error"), repr(bad)
        assert 'id="confirmar-form"' in response.text
        if bad.strip():
            assert bad.strip().replace("\r\n", "\n") in html.unescape(response.text)
    assert bodies == [] and writes(api) == 0
    assert send("x" * LIMIT).status_code == 303
    assert bodies[-1][field if action == "cancelar" else "note"] == "x" * LIMIT
    assert send(" " + "y" * LIMIT + " ").status_code == 303  # stripped length counts
    assert send("línea 1\r\nlínea 2").status_code == 303
    assert bodies[-1][field if action == "cancelar" else "note"] == "línea 1\nlínea 2"
    assert len(bodies) == 3


def test_bad_or_missing_csrf_is_403_with_zero_api_calls_for_all_three_posts() -> None:
    api = api_with("decision_pendiente", {DECISION: (200, {}), CANCEL: (200, {})})
    web = make_client(api)
    targets = [
        f"/pilotos/{PID}/decidir?accion=seguir",
        f"/pilotos/{PID}/decidir?accion=cerrar",
        f"/pilotos/{PID}/cancelar",
    ]
    for target in targets:
        for data in (
            {"note": "x", "reason": "x"},
            {"csrf": "mal", "note": "x", "reason": "x"},
            {"csrf": "", "note": "x", "reason": "x"},
        ):
            assert web.post(target, data=data).status_code == 403
    assert api.calls == []


@pytest.mark.parametrize(
    "bad_id",
    [
        "pil_2026_x",
        "PIL_20261102_x",
        "pil_20261102_x%0A",
        "pil_20261102_" + "a" * 41,
        "pil_٢٠٢٦١١٠٢_x",
        "pil_20261102_x%2Fy",
        "..",
    ],
)
def test_a_malformed_pilot_id_is_404_without_api_calls(bad_id: str) -> None:
    api = api_with(
        "decision_pendiente", {DECISION: (200, {}), CANCEL: (200, {}), SUMMARY: (200, {})}
    )
    web = make_client(api)
    csrf = token_of(web, PATHS["seguir"])
    api.calls.clear()
    quoted = quote(bad_id, safe="%")
    for method, path in (
        ("get", f"/pilotos/{quoted}/decidir?accion=seguir"),
        ("get", f"/pilotos/{quoted}/cancelar"),
        ("get", f"/pilotos/{quoted}/cierre"),
        ("post", f"/pilotos/{quoted}/decidir?accion=seguir"),
        ("post", f"/pilotos/{quoted}/cancelar"),
    ):
        response = getattr(web, method)(
            path,
            **({"data": {"csrf": csrf, "note": "x", "reason": "x"}} if method == "post" else {}),
        )
        assert response.status_code == 404, (method, path)
    assert api.calls == []


@pytest.mark.parametrize(
    ("status", "code", "shown"),
    [
        (409, "bad_transition", "El piloto no está en un estado que permita esa acción."),
        (409, "closed", "El piloto ya está cerrado o cancelado."),
        (404, "not_found", "No se encontró el piloto."),
        (409, "algo_nuevo", "No se pudo aplicar la acción. Revisa el estado del piloto."),
        (422, "invalid", "No se pudo aplicar la acción. Revisa el estado del piloto."),
    ],
)
@pytest.mark.parametrize("action", ["cerrar", "cancelar"])
def test_api_conflicts_are_shown_with_clear_messages_and_the_note_is_kept(
    action: str, status: int, code: str, shown: str
) -> None:
    route = CANCEL if action == "cancelar" else DECISION
    detail = {"code": code, "message": "RAW-API-TEXT <i>"}
    api = api_with(OPEN_STATE[action], {route: (status, {"detail": detail})})
    web = make_client(api)
    csrf = token_of(web, PATHS[action])
    if action == "cancelar":
        response = post_cancel(web, csrf, reason=HOSTILE)
    else:
        response = post_decision(web, csrf, action, note=HOSTILE)
    assert response.status_code == status
    assert flat(block(response.text, "error")) == shown
    assert "RAW-API-TEXT" not in response.text
    assert ESCAPED in response.text and "<script>" not in response.text
    assert writes(api) == 1


@pytest.mark.parametrize("action", ["seguir", "cancelar"])
def test_an_api_outage_on_post_keeps_the_form_with_a_message(action: str) -> None:
    route = CANCEL if action == "cancelar" else DECISION
    api = api_with(OPEN_STATE[action], {route: boom})
    web = make_client(api)
    csrf = token_of(web, PATHS[action])
    if action == "cancelar":
        response = post_cancel(web, csrf, reason=HOSTILE)
    else:
        response = post_decision(web, csrf, action, note=HOSTILE)
    assert response.status_code == 503
    assert MESSAGES["unavailable"] in flat(block(response.text, "error"))
    assert ESCAPED in response.text and 'id="confirmar-form"' in response.text


def test_an_outage_on_the_pilot_lookup_during_post_writes_nothing() -> None:
    api, state = switchable("decision_pendiente", {DECISION: (200, {})})
    web = make_client(api)
    csrf = token_of(web, PATHS["seguir"])
    state["down"] = True
    response = post_decision(web, csrf, "seguir")
    assert response.status_code == 503 and MESSAGES["unavailable"] in flat(response.text)
    assert writes(api) == 0


def test_malformed_api_payloads_never_produce_a_500() -> None:
    odd_pilots: list[Any] = [
        pilot_detail(status="decision_pendiente", niche_label=5, target_channel={"a": 1}),
        pilot_detail(status="decision_pendiente", niche_label=None, target_channel=None),
    ]
    for pilot in odd_pilots:
        api = Api({DETAIL: (200, pilot), DECISION: (200, ["not", "an", "object"])})
        web = make_client(api)
        assert web.get(PATHS["seguir"]).status_code == 200
        response = post_decision(web, token_of(web, PATHS["seguir"]), "seguir")
        assert response.status_code in (303, 503), response.text
    for broken in (["x"], {"status": 7}, {"status": {"a": 1}}, {}):
        api = Api({DETAIL: (200, broken), DECISION: (200, {})})
        web = make_client(api)
        get = web.get(PATHS["seguir"])
        assert get.status_code in (409, 503) and "<textarea" not in get.text
        assert writes(api) == 0


def test_a_malformed_post_payload_redraws_with_503_not_500() -> None:
    api = Api({DETAIL: (200, pilot_detail(status="decision_pendiente")), DECISION: (200, [])})
    web = make_client(api)
    csrf = token_of(web, PATHS["seguir"])
    response = post_decision(web, csrf, "seguir", note=HOSTILE)
    assert response.status_code == 503
    assert ESCAPED in response.text and writes(api) == 1


def test_a_double_submit_of_the_same_decision_is_reported_not_repeated() -> None:
    state = {"status": "en_ejecucion"}
    bodies: list[dict[str, Any]] = []

    def detail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pilot_detail(status=state["status"]))

    def decide(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        state["status"] = "cerrado"
        return httpx.Response(200, json={"pilot_id": PID, "status": "cerrado"})

    api = Api({DETAIL: detail, DECISION: decide, STATUS: (200, {"radar_paused": False})})
    web = make_client(api)
    csrf = token_of(web, PATHS["cerrar"])
    first = post_decision(web, csrf, "cerrar", note="Cierro")
    second = post_decision(web, csrf, "cerrar", note="Cierro")
    assert first.status_code == 303
    assert second.status_code == 409
    assert ALREADY_CLOSED in flat(block(second.text, "bloqueo"))
    assert "Cierro" not in flat(block(second.text, "bloqueo"))
    assert len(bodies) == 1 and writes(api) == 1
    # The race where the pilot looked open but the API says closed is a clear message too.
    raced = api_with(
        "en_ejecucion",
        {DECISION: (409, {"detail": {"code": "closed", "message": "x"}})},
    )
    other = make_client(raced)
    response = post_decision(other, token_of(other, PATHS["cerrar"]), "cerrar")
    assert response.status_code == 409
    assert "ya está cerrado o cancelado" in flat(block(response.text, "error"))


@pytest.mark.parametrize("status", ["autorizado", "entregado"])
def test_cancel_posts_the_reason_and_redirects_with_the_cancelled_notice(status: str) -> None:
    bodies: list[dict[str, Any]] = []
    api = api_with(status, {CANCEL: recorder(bodies)})
    web = make_client(api)
    response = post_cancel(web, token_of(web, PATHS["cancelar"]), reason="  Cambió el plan ")
    assert response.status_code == 303
    assert response.headers["location"] == f"/pilotos/{PID}?aviso=cancelado"
    assert bodies == [{"reason": "Cambió el plan", "actor": "humano"}]


@pytest.mark.parametrize(
    ("action", "open_state", "now_state", "expected"),
    [
        ("seguir", "decision_pendiente", "en_ejecucion", "Solo se puede seguir"),
        ("cerrar", "en_ejecucion", "autorizado", "se cancela, no se cierra"),
        ("cerrar", "en_ejecucion", "cancelado", "ya está cancelado"),
        ("cancelar", "autorizado", "cerrado", ALREADY_CLOSED),
        ("cancelar", "autorizado", "en_ejecucion", "antes de que se ejecute"),
    ],
)
def test_a_post_on_a_state_that_changed_is_a_message_and_no_write(
    action: str, open_state: str, now_state: str, expected: str
) -> None:
    api, state = switchable(open_state, {DECISION: (200, {}), CANCEL: (200, {})})
    web = make_client(api)
    csrf = token_of(web, PATHS[action])
    state["status"] = now_state
    response = post_cancel(web, csrf) if action == "cancelar" else post_decision(web, csrf, action)
    assert response.status_code == 409
    assert expected in flat(block(response.text, "bloqueo"))
    assert "<textarea" not in response.text and writes(api) == 0


def test_the_closing_summary_page_shows_the_text_escaped_in_a_pre_and_handles_409() -> None:
    summary = f"# EVD-canal\n\n- **fuerte** {HOSTILE}\n  sangría   y  espacios\n"

    def text(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=summary, headers={"content-type": "text/plain"})

    api = api_with("cerrado", {SUMMARY: text})
    response = make_client(api).get(f"/pilotos/{PID}/cierre")
    assert response.status_code == 200
    pre = re.search(
        r'<pre class="resumen-cierre" id="resumen-cierre">(.*?)</pre>', response.text, re.S
    )
    assert pre, response.text
    assert html.unescape(pre.group(1)) == summary
    assert "&lt;script&gt;" in pre.group(1) and "<script>" not in response.text
    assert "<strong>" not in response.text and "<h1>EVD" not in response.text
    assert api.calls[-1].headers["authorization"].startswith("Bearer ")
    for status, body, shown, code in (
        (
            409,
            {"detail": {"code": "bad_transition", "message": "x"}},
            "El resumen existe solo cuando el piloto está cerrado.",
            409,
        ),
        (
            404,
            {"detail": {"code": "not_found", "message": "x"}},
            "No se encontró lo que buscabas.",
            404,
        ),
    ):
        failing = api_with("autorizado", {SUMMARY: (status, body)})
        page = make_client(failing).get(f"/pilotos/{PID}/cierre")
        assert page.status_code == code and shown in flat(page.text)
        assert "<pre" not in page.text
    down = make_client(api_with("cerrado", {SUMMARY: boom})).get(f"/pilotos/{PID}/cierre")
    assert down.status_code == 503 and MESSAGES["unavailable"] in flat(down.text)


def test_a_big_closing_summary_is_shown_and_an_oversized_one_is_refused() -> None:
    big = ("línea larga " + "x" * 200 + "\n") * 1000
    assert len(big.encode()) < 256 * 1024
    ok = api_with("cerrado", {SUMMARY: lambda r: httpx.Response(200, text=big)})
    page = make_client(ok).get(f"/pilotos/{PID}/cierre")
    assert page.status_code == 200 and page.text.count("línea larga") == 1000
    over = api_with(
        "cerrado", {SUMMARY: lambda r: httpx.Response(200, text="a" * (256 * 1024 + 1))}
    )
    page = make_client(over).get(f"/pilotos/{PID}/cierre")
    assert page.status_code == 503 and "<pre" not in page.text


def test_the_closing_summary_has_a_wrapping_rule_in_the_stylesheet() -> None:
    css = open("src/nicheradar/web/static/css/app.css", encoding="utf-8").read()
    rule = re.search(r"\.resumen-cierre\s*\{([^}]*)\}", css)
    assert rule, "missing .resumen-cierre rule"
    assert "white-space:pre-wrap" in rule.group(1).replace(" ", "")
    assert "overflow-wrap:anywhere" in rule.group(1).replace(" ", "")


def test_every_new_template_class_has_a_rule_in_the_stylesheet() -> None:
    css = open("src/nicheradar/web/static/css/app.css", encoding="utf-8").read()
    for name in ("confirmar", "cierre"):
        source = open(f"src/nicheradar/web/templates/pilotos/{name}.html", encoding="utf-8").read()
        for attribute in re.findall(r'class="([^"{]+)"', source):
            for cls in attribute.split():
                assert re.search(rf"\.{re.escape(cls)}(?![\w-])", css), f"{cls} has no CSS rule"


def test_hostile_text_in_the_note_the_reason_and_the_summary_is_escaped() -> None:
    api = api_with("autorizado", {CANCEL: (409, {"detail": {"code": "closed", "message": "x"}})})
    web = make_client(api)
    response = post_cancel(web, token_of(web, PATHS["cancelar"]), reason=HOSTILE)
    area = re.search(r"<textarea[^>]*>(.*?)</textarea>", response.text, re.S)
    assert area and area.group(1).strip() == ESCAPED
    assert "<script>alert" not in response.text
    bad = api_with(
        "cerrado", {SUMMARY: lambda r: httpx.Response(200, text="</pre><script>1</script>")}
    )
    page = make_client(bad).get(f"/pilotos/{PID}/cierre")
    assert "<script>1</script>" not in page.text and "&lt;/pre&gt;&lt;script&gt;" in page.text


def test_the_notice_after_an_action_comes_only_from_fixed_keys() -> None:
    api = api_with("cerrado", {})
    web = make_client(api)
    for key, text in (
        ("seguido", "Decidiste seguir: el piloto continúa."),
        ("cerrado", "Piloto cerrado. Ver resumen de cierre"),  # the pilot is cerrado
        ("cancelado", "Piloto cancelado."),
    ):
        page = web.get(f"/pilotos/{PID}?aviso={key}")
        assert flat(block(page.text, "aviso")) == text
    for hostile in ("<script>alert(1)</script>", "otro", "%00", "seguido%0A"):
        page = web.get(f"/pilotos/{PID}?aviso={hostile}")
        assert 'id="aviso"' not in page.text and "<script>alert" not in page.text


@pytest.mark.parametrize(
    ("status", "needles"),
    [
        ("decision_pendiente", ["decidir?accion=seguir", "decidir?accion=cerrar"]),
        ("en_ejecucion", ["decidir?accion=cerrar"]),
        ("autorizado", ["/cancelar"]),
        ("entregado", ["/cancelar"]),
        ("cerrado", ["/cierre"]),
    ],
)
def test_the_panel_links_resolve_to_the_new_screens(status: str, needles: list[str]) -> None:
    api = api_with(status, {SUMMARY: (200, "Resumen\n")} if status == "cerrado" else {})
    web = make_client(api)
    page = web.get(f"/pilotos/{PID}")
    links = [
        html.unescape(h)
        for h in re.findall(r'href="(/pilotos/[^"]+)"', page.text)
        if re.search(r"/(decidir|cancelar|cierre)", h)
    ]
    assert len(links) == len(needles), links
    for needle in needles:
        assert any(needle in link for link in links), (needle, links)
    for link in links:
        response = web.get(link)
        assert response.status_code == 200, (link, response.text)
        assert "<textarea" in response.text or "<pre" in response.text


@pytest.mark.parametrize(
    "value",
    [
        "\u00a0",
        "\u200b",
        "\u2060",
        "\ufeff",
        "\u200b \u00a0\n\t",
        "\u3000",
        "\u202f",
        "\x07",
        "\u200e",
    ],
)
def test_a_note_with_only_invisible_characters_is_rejected(value: str) -> None:
    assert validate_note(value) is None


def test_a_note_needs_one_visible_character_and_keeps_its_inner_newlines() -> None:
    assert validate_note("x") == "x"
    assert validate_note("\u200b ok \u200b") == "\u200b ok \u200b"  # visible text inside is kept
    assert validate_note("  uno\r\ndos\r\n\r\ntres  ") == "uno\ndos\n\ntres"
    assert validate_note("") is None and validate_note(" \n ") is None


def test_the_note_limit_is_1500_characters() -> None:
    assert validate_note("a" * 1500) == "a" * 1500
    assert validate_note("a" * 1501) is None
