import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.api import create_app
from nicheradar.config import Settings
from tests.test_foundation import TOKEN


@pytest.mark.postgres
def test_post_requires_auth_and_enqueues(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    path = "/api/v1/channel-analyses"
    assert client.post(path, json={"channel_input": "@x"}).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        path, json={"channel_input": "@x"}, headers={"Idempotency-Key": "a" * 10}
    )
    assert response.status_code == 202
    assert "job_id" in response.json()

    listing = client.get(path)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 0

    detail = client.get(f"{path}/00000000-0000-0000-0000-000000000000")
    assert detail.status_code == 404


@pytest.mark.postgres
def test_post_rejects_unsupported_channel_input(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "not a real channel"},
        headers={"Idempotency-Key": "b" * 10},
    )
    assert response.status_code == 422
