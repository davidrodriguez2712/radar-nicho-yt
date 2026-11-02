# tests/test_web_client.py
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
