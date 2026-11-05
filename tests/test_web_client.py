# tests/test_web_client.py
from collections.abc import Iterator

import httpx
import pytest

from nicheradar.web.client import ApiClient, ApiError
from tests.web_helpers import TOKEN, Api, settings


def client_for(api: Api) -> ApiClient:
    return ApiClient(settings(), transport=httpx.MockTransport(api))


def test_a_request_goes_to_the_private_api_with_the_bearer_token() -> None:
    api = Api({("GET", "/api/v1/subniches"): (200, {"items": []})})
    assert client_for(api).request("GET", "/subniches", params={"include_inactive": "false"}) == {
        "items": []
    }
    call = api.calls[0]
    assert call.headers["authorization"] == f"Bearer {TOKEN}"
    assert call.url.params["include_inactive"] == "false"


def test_a_post_sends_the_json_body() -> None:
    seen: list[bytes] = []

    def echo(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(201, json={"id": "x", "created": True})

    api = Api({("POST", "/api/v1/flow-research"): echo})
    result = client_for(api).request("POST", "/flow-research", body={"niche_label": "subniche:a"})
    assert result["created"] is True and b'"niche_label"' in seen[0]


def test_an_empty_or_204_response_is_an_empty_dict() -> None:
    api = Api({("GET", "/api/v1/x"): lambda request: httpx.Response(204)})
    assert client_for(api).request("GET", "/x") == {}


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "unauthorized"),
        (403, "unauthorized"),
        (404, "not_found"),
        (409, "conflict"),
        (422, "invalid"),
        (500, "error"),
        (503, "error"),
    ],
)
def test_error_statuses_become_typed_errors_with_a_spanish_message(status: int, kind: str) -> None:
    api = Api({("GET", "/api/v1/x"): (status, {"detail": {"code": "c", "message": "m"}})})
    with pytest.raises(ApiError) as error:
        client_for(api).request("GET", "/x")
    assert error.value.kind == kind and error.value.status == status
    assert error.value.message and "Traceback" not in error.value.message


def test_a_conflict_carries_the_api_detail() -> None:
    api = Api(
        {
            ("POST", "/api/v1/x"): (
                409,
                {"detail": {"code": "subniche_not_ready", "message": "Falta algo."}},
            )
        }
    )
    with pytest.raises(ApiError) as error:
        client_for(api).request("POST", "/x", body={})
    assert error.value.detail == {"code": "subniche_not_ready", "message": "Falta algo."}
    assert error.value.message == "Falta algo."


def test_an_unreachable_api_is_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ApiError) as error:
        client_for(Api({("GET", "/api/v1/x"): boom})).request("GET", "/x")
    assert error.value.kind == "unavailable" and "API no disponible" in error.value.message


def test_a_missing_service_token_is_reported_without_calling_the_api() -> None:
    api = Api()
    client = ApiClient(settings(service_token=None), transport=httpx.MockTransport(api))
    with pytest.raises(ApiError) as error:
        client.request("GET", "/x")
    assert error.value.kind == "not_configured" and api.calls == []


def test_a_2xx_with_a_non_json_body_is_a_typed_error() -> None:
    api = Api({("GET", "/api/v1/x"): lambda request: httpx.Response(200, text="<html>hi</html>")})
    with pytest.raises(ApiError) as error:
        client_for(api).request("GET", "/x")
    assert error.value.kind == "error" and error.value.status == 200


def test_a_2xx_with_a_json_list_is_a_typed_error() -> None:
    api = Api({("GET", "/api/v1/x"): (200, [1, 2])})
    with pytest.raises(ApiError) as error:
        client_for(api).request("GET", "/x")
    assert error.value.kind == "error" and error.value.status == 200


def test_an_error_status_with_a_json_list_body_keeps_its_kind_and_has_no_detail() -> None:
    api = Api({("GET", "/api/v1/x"): (409, [1])})
    with pytest.raises(ApiError) as error:
        client_for(api).request("GET", "/x")
    assert error.value.kind == "conflict" and error.value.detail is None


def test_an_invalid_api_url_is_unavailable() -> None:
    def bad(request: httpx.Request) -> httpx.Response:
        raise httpx.InvalidURL("bad")

    with pytest.raises(ApiError) as error:
        client_for(Api({("GET", "/api/v1/x"): bad})).request("GET", "/x")
    assert error.value.kind == "unavailable"


LIMIT = 256 * 1024


def text_api(response: httpx.Response) -> Api:
    return Api({("GET", "/api/v1/t"): lambda request: response})


def test_request_text_returns_the_plain_text_and_maps_errors_like_request() -> None:
    api = Api(
        {
            ("GET", "/api/v1/t"): lambda request: httpx.Response(
                200, text="# Resumen\nñandú ✓", headers={"content-type": "text/plain"}
            )
        }
    )
    assert client_for(api).request_text("GET", "/t", params={"a": "b"}) == "# Resumen\nñandú ✓"
    call = api.calls[0]
    assert call.headers["authorization"] == f"Bearer {TOKEN}"
    assert call.url.params["a"] == "b" and TOKEN not in str(call.url)
    for status, kind in ((401, "unauthorized"), (403, "unauthorized"), (404, "not_found")):
        failing = Api({("GET", "/api/v1/t"): (status, {"detail": {"code": "c", "message": "m"}})})
        with pytest.raises(ApiError) as error:
            client_for(failing).request_text("GET", "/t")
        assert (error.value.kind, error.value.status) == (kind, status)
    conflict = Api({("GET", "/api/v1/t"): (409, {"detail": {"code": "bad_transition"}})})
    with pytest.raises(ApiError) as error:
        client_for(conflict).request_text("GET", "/t")
    assert error.value.kind == "conflict" and error.value.detail == {"code": "bad_transition"}
    for status, kind in ((422, "invalid"), (500, "error"), (503, "error")):
        with pytest.raises(ApiError) as error:
            client_for(text_api(httpx.Response(status, text="plain failure"))).request_text(
                "GET", "/t"
            )
        assert (error.value.kind, error.value.status, error.value.detail) == (kind, status, None)


def test_request_text_handles_empty_odd_and_unreachable_responses() -> None:
    assert client_for(text_api(httpx.Response(200, content=b""))).request_text("GET", "/t") == ""
    assert client_for(text_api(httpx.Response(204))).request_text("GET", "/t") == ""
    for odd in (b"\xff\xfe\x00bad", b"ok \xc3"):
        with pytest.raises(ApiError) as error:
            client_for(text_api(httpx.Response(200, content=odd))).request_text("GET", "/t")
        assert error.value.kind == "error"

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ApiError) as error:
        client_for(Api({("GET", "/api/v1/t"): boom})).request_text("GET", "/t")
    assert error.value.kind == "unavailable"
    missing = Api({("GET", "/api/v1/t"): (200, {})})
    with pytest.raises(ApiError) as error:
        ApiClient(
            settings(service_token=None), transport=httpx.MockTransport(missing)
        ).request_text("GET", "/t")
    assert error.value.kind == "not_configured" and missing.calls == []

    def bad(request: httpx.Request) -> httpx.Response:
        raise httpx.InvalidURL("bad")

    with pytest.raises(ApiError) as error:
        client_for(Api({("GET", "/api/v1/t"): bad})).request_text("GET", "/t")
    assert error.value.kind == "unavailable"


def test_request_text_refuses_bodies_over_the_limit() -> None:
    exact = httpx.Response(200, content=b"a" * LIMIT)
    assert len(client_for(text_api(exact)).request_text("GET", "/t")) == LIMIT
    over = httpx.Response(200, content=b"a" * (LIMIT + 1))  # declares its content-length
    with pytest.raises(ApiError) as error:
        client_for(text_api(over)).request_text("GET", "/t")
    assert error.value.kind == "error"

    def chunks() -> Iterator[bytes]:
        for _ in range(LIMIT // 1024 + 1):
            yield b"a" * 1024

    streamed = httpx.Response(200, content=chunks())  # chunked: no content-length to check
    assert "content-length" not in streamed.headers
    with pytest.raises(ApiError) as error:
        client_for(text_api(streamed)).request_text("GET", "/t")
    assert error.value.kind == "error"
    huge_error = httpx.Response(500, content=b"a" * (LIMIT + 1))
    with pytest.raises(ApiError) as error:
        client_for(text_api(huge_error)).request_text("GET", "/t")
    assert error.value.kind == "error" and error.value.detail is None


@pytest.mark.parametrize("declared", ["\u00b2", "\u0663", "\u0661\u0662"])
def test_request_text_ignores_a_non_ascii_content_length(declared: str) -> None:
    response = httpx.Response(
        200, content=b"hola", headers=[(b"content-length", declared.encode())]
    )
    assert client_for(text_api(response)).request_text("GET", "/t") == "hola"


def test_extra_headers_reach_the_api_but_never_replace_authorization() -> None:
    api = Api({("POST", "/api/v1/x"): (202, {"ok": True})})
    client_for(api).request(
        "POST",
        "/x",
        body={},
        headers={"Idempotency-Key": "nr-abc12345", "Authorization": "Bearer otro"},
    )
    call = api.calls[0]
    assert call.headers["idempotency-key"] == "nr-abc12345"
    assert call.headers["authorization"] == f"Bearer {TOKEN}"


def test_a_domain_rejection_with_code_and_message_at_the_root_exposes_its_code() -> None:
    api = Api(
        {
            ("POST", "/api/v1/x"): (
                429,
                {"code": "daily_limit", "message": "Texto arbitrario del servidor."},
            )
        }
    )
    with pytest.raises(ApiError) as error:
        client_for(api).request("POST", "/x", body={})
    assert error.value.kind == "error" and error.value.status == 429
    assert error.value.code == "daily_limit"
    assert error.value.message == "Se llegó al tope diario de propuestas."
    assert "arbitrario" not in error.value.message


def test_a_lifecycle_conflict_at_the_root_keeps_kind_and_uses_the_fixed_text() -> None:
    api = Api({("POST", "/api/v1/x"): (409, {"code": "invalid_transition", "message": "<b>x</b>"})})
    with pytest.raises(ApiError) as error:
        client_for(api).request("POST", "/x", body={})
    assert error.value.kind == "conflict" and error.value.code == "invalid_transition"
    assert error.value.message == "Esa hipótesis no puede pasar a ese estado."


def test_a_detail_wrapped_code_is_also_exposed_and_unknown_codes_never_show_their_text() -> None:
    api = Api(
        {
            ("GET", "/api/v1/x"): (404, {"detail": {"code": "not_found", "message": "Hola"}}),
            ("POST", "/api/v1/y"): (422, {"code": "algo_raro", "message": "Texto del servidor"}),
        }
    )
    with pytest.raises(ApiError) as missing:
        client_for(api).request("GET", "/x")
    assert missing.value.kind == "not_found" and missing.value.code == "not_found"
    with pytest.raises(ApiError) as odd:
        client_for(api).request("POST", "/y", body={})
    assert odd.value.kind == "invalid" and odd.value.code == "algo_raro"
    assert "Texto del servidor" not in odd.value.message


def test_code_is_none_without_a_code_or_with_a_hostile_one() -> None:
    api = Api(
        {
            ("GET", "/api/v1/a"): (500, {"detail": "boom"}),
            ("GET", "/api/v1/b"): (500, {"code": 7, "message": "m"}),
            ("GET", "/api/v1/c"): (500, {"code": "x" * 500, "message": "m"}),
        }
    )
    for path in ("/a", "/b", "/c"):
        with pytest.raises(ApiError) as error:
            client_for(api).request("GET", path)
        assert error.value.code is None
