# tests/web_helpers.py
"""Shared helpers for the mobile web tests."""

from pydantic import SecretStr

from nicheradar.config import Settings

TOKEN = "t" * 32
PASSWORD = "p" * 32


def settings(**over: object) -> Settings:
    values: dict[str, object] = {
        "service_token": SecretStr(TOKEN),
        "dashboard_password": SecretStr(PASSWORD),
        "api_url": "http://api.test",
        "dashboard_ui": "web",
    }
    return Settings(**(values | over))  # type: ignore[arg-type]
