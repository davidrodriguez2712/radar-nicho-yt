import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from streamlit.testing.v1 import AppTest

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.workers.main import tick

TOKEN = "synthetic-test-token-never-use-in-production"


def test_default_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir("tests")
    config = Settings()
    assert config.mode == "synthetic"
    assert config.radar_paused
    assert tick(config)["provider_calls"] == 0
    assert tick(config)["status"] == "paused"


def test_private_api() -> None:
    client = TestClient(create_app(Settings(service_token=SecretStr(TOKEN))))
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/api/v1/profile").status_code == 401
    assert (
        client.get("/api/v1/profile", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/api/v1/profile", headers=headers).json()["formats"] == ["long", "shorts"]
    assert TOKEN not in client.get("/api/v1/status", headers=headers).text
    assert client.get("/openapi.json").status_code == 404


def test_unconfigured_api_fails_closed() -> None:
    client = TestClient(create_app(Settings(service_token=None)))
    assert client.get("/api/v1/status").status_code == 503


def test_secret_redaction() -> None:
    config = Settings(vidiq_token=SecretStr(TOKEN))
    assert TOKEN not in repr(config)
    assert TOKEN not in json.dumps(config.public_status())
    secret = "short-secret"
    with pytest.raises(ValidationError) as exc:
        Settings(service_token=SecretStr(secret))
    assert secret not in str(exc.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timezone", "Invalid/Zone"),
        ("api_port", 0),
        ("external_concurrency", 0),
        ("api_host", "0.0.0.0"),
        ("dashboard_host", "0.0.0.0"),
        ("database_url", "sqlite:///not-postgres"),
    ],
)
def test_invalid_configuration(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


def test_profile_and_catalog() -> None:
    profile = CreatorProfile()
    assert profile.monthly_target_usd == Decimal(100)
    assert profile.monthly_ceiling_usd == Decimal(150)
    assert profile.weekly_hours == 15
    assert profile.language == "en"
    assert set(profile.formats) == {VideoFormat.LONG, VideoFormat.SHORTS}
    assert set(profile.excluded_subscriptions) == {"Claude", "ChatGPT", "Google AI Pro"}
    assert not profile.paid_limits_confirmed
    catalog = initial_catalog()
    assert len(catalog.families) == 7
    assert catalog.version == "families-v1"
    assert all(family.queries for family in catalog.families)
    with pytest.raises(ValidationError):
        CreatorProfile(monthly_target_usd=Decimal(200))


def test_dashboard_unconfigured_does_not_expose_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NR_DASHBOARD_PASSWORD", raising=False)
    app = AppTest.from_file("../apps/dashboard/main.py").run()
    assert not app.exception
    assert "NR_DASHBOARD_PASSWORD" in app.warning[0].value
    assert not app.json


def test_dashboard_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NR_DASHBOARD_PASSWORD", TOKEN)
    monkeypatch.delenv("NR_SERVICE_TOKEN", raising=False)
    app = AppTest.from_file("../apps/dashboard/main.py").run()
    app.text_input[0].set_value("wrong")
    app.button[0].click().run()
    assert app.error[0].value == "Contraseña incorrecta."
    app.text_input[0].set_value(TOKEN)
    app.button[0].click().run()
    assert not app.exception
    assert "NR_SERVICE_TOKEN" in app.warning[0].value
    assert not app.json
