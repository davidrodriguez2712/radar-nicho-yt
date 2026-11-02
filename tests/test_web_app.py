# tests/test_web_app.py
import subprocess
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nicheradar import entrypoints
from nicheradar.config import Settings
from nicheradar.web.app import create_app
from tests.web_helpers import settings


def test_the_dashboard_ui_defaults_to_streamlit_and_can_be_switched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NR_DASHBOARD_UI", raising=False)
    assert Settings(_env_file=None).dashboard_ui == "streamlit"  # type: ignore[call-arg]
    monkeypatch.setenv("NR_DASHBOARD_UI", "web")
    assert Settings(_env_file=None).dashboard_ui == "web"  # type: ignore[call-arg]


def test_the_dashboard_entry_point_launches_the_web_app_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setenv("NR_DASHBOARD_UI", "web")
    monkeypatch.setattr("nicheradar.entrypoints.uvicorn.run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(
        "nicheradar.entrypoints.subprocess.call",
        lambda *a, **k: pytest.fail("streamlit must not start"),
    )
    entrypoints.dashboard()
    (args, kwargs) = calls[0]
    assert args == ("nicheradar.web.app:create_app",)
    assert kwargs["factory"] is True and kwargs["port"] == 8501 and kwargs["access_log"] is False


def test_the_dashboard_entry_point_still_launches_streamlit_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.delenv("NR_DASHBOARD_UI", raising=False)
    monkeypatch.setattr(
        "nicheradar.entrypoints.uvicorn.run", lambda *a, **k: pytest.fail("web must not start")
    )

    def fake_call(command: list[str], **_: object) -> int:
        commands.append(command)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    with pytest.raises(SystemExit) as exit_info:
        entrypoints.dashboard()
    assert exit_info.value.code == 0 and "streamlit" in commands[0]


def test_the_health_endpoint_answers_without_a_session() -> None:
    client = TestClient(create_app(settings()))
    response = client.get("/_stcore/health")
    assert response.status_code == 200 and response.text == "ok"


def test_the_health_endpoint_also_answers_head() -> None:
    assert TestClient(create_app(settings())).head("/_stcore/health").status_code == 200


def test_every_response_carries_the_security_headers() -> None:
    response = TestClient(create_app(settings())).get("/_stcore/health")
    policy = response.headers["content-security-policy"]
    for needle in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "frame-ancestors 'none'",
    ):
        assert needle in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_the_api_docs_are_not_exposed() -> None:
    client = TestClient(create_app(settings()))
    assert [client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")] == [
        404
    ] * 3
