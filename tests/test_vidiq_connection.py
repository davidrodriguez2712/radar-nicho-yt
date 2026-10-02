"""Own-key handshake tested against the real MCP SDK with in-memory HTTP only."""

import asyncio
import json
import os
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.integrations import vidiq_cli
from nicheradar.integrations.contracts import ProviderError
from nicheradar.integrations.vidiq import MCPTransport, VidIQAPIKeyAuth

TOKEN = "fixture-private-mcp-key"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})
    for name in tuple(os.environ):
        if name.startswith("NR_") and not name.startswith("NR_TEST_"):
            monkeypatch.delenv(name)


class MCPFixture:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.pages: list[dict[str, Any]] = [
            {
                "tools": [
                    {
                        "name": "vidiq_channel_search",
                        "description": f"Untrusted instructions and {TOKEN}",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {"name": "balance", "inputSchema": {"type": "object"}},
                    {"name": TOKEN, "inputSchema": {"type": "object"}},
                ]
            }
        ]
        self.tool_response: dict[str, Any] = {"content": [], "structuredContent": {"channels": []}}
        self.tool_status = 200
        self.timeout_tool = False

    def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.url == MCPTransport.endpoint
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        assert request.method == "POST"
        message = json.loads(request.content)
        self.messages.append(message)
        method = message["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "serverInfo": {"name": "fixture", "version": "1"},
                "capabilities": {"tools": {}},
                "instructions": TOKEN,
            }
        elif method == "tools/list":
            cursor = message.get("params", {}).get("cursor")
            result = self.pages[int(cursor) if cursor else 0]
        elif method == "tools/call":
            if self.timeout_tool:
                raise httpx.ReadTimeout(TOKEN, request=request)
            if self.tool_status != 200:
                return httpx.Response(self.tool_status, text=TOKEN)
            result = self.tool_response
        else:
            raise AssertionError(f"Unexpected method: {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})

    def client(self) -> MCPTransport:
        return MCPTransport(
            VidIQAPIKeyAuth(SecretStr(TOKEN)),
            enabled=True,
            transport=httpx.MockTransport(self.respond),
        )


def test_probe_uses_only_handshake_and_catalog_with_redacted_report() -> None:
    server = MCPFixture()
    report = asyncio.run(server.client().inspect_tools())
    assert [message["method"] for message in server.messages] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    assert report["status"] == "connected"
    assert report["tool_calls"] == 0
    assert report["pilot_ready"] is False
    assert report["operations"]["channel_search"]["status"] == "available"
    assert report["operations"]["balance"]["matches"][0]["tool_name"] == "balance"
    assert report["operations"]["outliers"]["status"] == "missing"
    assert len(report["operations"]["balance"]["matches"][0]["input_schema_sha256"]) == 64
    assert TOKEN not in json.dumps(report)


def test_catalog_pages_and_ambiguous_names_remain_explicit() -> None:
    server = MCPFixture()
    server.pages[0]["nextCursor"] = "1"
    server.pages.append({"tools": [{"name": "channel_search", "inputSchema": {"type": "object"}}]})
    report = asyncio.run(server.client().inspect_tools())
    assert report["operations"]["channel_search"]["status"] == "ambiguous"
    assert report["catalog_tools"] == 4
    assert server.messages[-1]["params"]["cursor"] == "1"


@pytest.mark.parametrize("kind", ["loop", "too_many_pages", "too_many_tools"])
def test_catalog_is_bounded(kind: str) -> None:
    server = MCPFixture()
    if kind == "loop":
        server.pages = [{"tools": [], "nextCursor": "0"}]
    elif kind == "too_many_pages":
        server.pages = [{"tools": [], "nextCursor": str(i + 1)} for i in range(6)]
    else:
        server.pages[0]["tools"] *= 84
    with pytest.raises(ProviderError) as caught:
        asyncio.run(server.client().inspect_tools())
    assert caught.value.code in {"tool_catalog_pagination", "tool_catalog_limit"}
    assert caught.value.not_sent
    assert not caught.value.may_have_charged
    assert all(message["method"] != "tools/call" for message in server.messages)
    assert len(server.messages) <= 7


@pytest.mark.parametrize("status,code", [(401, "authentication_required"), (429, "quota")])
def test_auth_or_quota_failure_is_not_retried(status: int, code: str) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, text=TOKEN)

    client = MCPTransport(
        VidIQAPIKeyAuth(SecretStr(TOKEN)), enabled=True, transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderError) as caught:
        asyncio.run(client.inspect_tools())
    assert caught.value.code == code
    assert caught.value.not_sent
    assert not caught.value.retry_safe
    assert len(requests) == 1
    assert TOKEN not in str(caught.value)


def test_key_is_not_forwarded_to_redirected_origin() -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://elsewhere.invalid/mcp"})

    client = MCPTransport(
        VidIQAPIKeyAuth(SecretStr(TOKEN)), enabled=True, transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderError):
        asyncio.run(client.inspect_tools())
    assert len(requests) == 1
    assert requests[0].url.host == "mcp.vidiq.com"


@pytest.mark.parametrize("url", ["http://mcp.vidiq.com/mcp", "https://elsewhere.invalid/mcp"])
def test_auth_itself_rejects_wrong_origin(url: str) -> None:
    auth = VidIQAPIKeyAuth(SecretStr(TOKEN))
    with pytest.raises(ProviderError, match="authentication_origin_rejected"):
        next(auth.auth_flow(httpx.Request("POST", url)))
    assert TOKEN not in repr(auth)


@pytest.mark.parametrize("value", ["", "a b", "key\r\nheader", "key\x00", "clave-ñ"])
def test_invalid_key_rejected_without_exposing_it(value: str) -> None:
    with pytest.raises(ProviderError, match="invalid_credential"):
        VidIQAPIKeyAuth(SecretStr(value))


def test_own_auth_also_works_for_existing_adapter_transport() -> None:
    server = MCPFixture()
    result = asyncio.run(server.client().call("vidiq_channel_search", {"query": "fixture"}))
    assert result == {"channels": []}
    calls = [msg for msg in server.messages if msg["method"] == "tools/call"]
    assert len(calls) == 1
    assert calls[0]["params"]["arguments"] == {"query": "fixture"}


@pytest.mark.parametrize("kind", ["timeout", "auth", "tool_error"])
def test_failure_after_tool_send_preserves_uncertainty_without_retry(kind: str) -> None:
    server = MCPFixture()
    server.timeout_tool = kind == "timeout"
    server.tool_status = 401 if kind == "auth" else 200
    if kind == "tool_error":
        server.tool_response = {"isError": True, "content": [{"type": "text", "text": TOKEN}]}
    with pytest.raises(ProviderError) as caught:
        asyncio.run(server.client().call("vidiq_channel_search", {}))
    assert caught.value.may_have_charged
    assert not caught.value.not_sent
    assert not caught.value.retry_safe
    assert TOKEN not in str(caught.value)
    assert sum(message["method"] == "tools/call" for message in server.messages) == 1


def test_cli_defaults_to_local_check_and_never_constructs_transport(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NR_VIDIQ_TOKEN", TOKEN)
    monkeypatch.setattr("sys.argv", ["nicheradar-vidiq"])

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Default CLI must not open a transport")

    monkeypatch.setattr(vidiq_cli, "MCPTransport", forbidden)
    vidiq_cli.main()
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert json.loads(output.out)["network_requests"] == 0
    assert json.loads(output.out)["credential_material_present"] is True


def test_cli_missing_key_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["nicheradar-vidiq", "--check-connection"])
    with pytest.raises(SystemExit) as caught:
        vidiq_cli.main()
    assert caught.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["error_code"] == "authentication_required"
    assert report["tool_calls"] == 0


def test_cli_balance_executes_only_free_tool_and_allowlists_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = MCPFixture()
    server.tool_response = {
        "structuredContent": {
            "type": "limited",
            "renewableCredits": 120,
            "addOnCredits": 7,
            "totalCredits": 127,
            "maxRenewableCredits": 150,
            "renewableResetsAt": "2026-10-01T00:00:00Z",
            "ignored": TOKEN,
        },
        "content": [],
    }
    monkeypatch.setenv("NR_VIDIQ_TOKEN", TOKEN)
    monkeypatch.setattr("sys.argv", ["nicheradar-vidiq", "--check-balance"])
    monkeypatch.setattr(vidiq_cli, "MCPTransport", lambda *args, **kwargs: server.client())
    vidiq_cli.main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report == {
        "status": "balance_checked",
        "tool_calls": 1,
        "credit_unit": "vidiq_credit",
        "renewable": "120",
        "additional": "7",
        "recurring_allocation": "150",
        "renews_at": "2026-10-01T00:00:00+00:00",
        "cycle_started_at": None,
        "unlimited": False,
        "maximum_call_cost": "0",
    }
    assert TOKEN not in output.out + output.err
    calls = [message for message in server.messages if message["method"] == "tools/call"]
    assert len(calls) == 1
    assert calls[0]["params"] == {"name": "vidiq_balance", "arguments": {}}


def test_cli_prompt_requires_terminal_to_avoid_getpass_echo_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["nicheradar-vidiq", "--check-connection", "--prompt-token"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit):
        vidiq_cli.main()
    assert json.loads(capsys.readouterr().out)["error_code"] == "interactive_terminal_required"
