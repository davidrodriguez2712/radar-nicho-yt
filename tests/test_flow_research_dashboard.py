# tests/test_flow_research_dashboard.py
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from streamlit.testing.v1 import AppTest

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.flow_research.contracts import Dossier
from nicheradar.flow_research_dashboard import budget_rows, flow_rows, roadmap_rows
from tests.flow_research_samples import valid_dossier
from tests.test_foundation import TOKEN
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW

HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def stored_shape() -> dict[str, Any]:
    dossier = Dossier.model_validate(valid_dossier(UUID(int=1), NOW))
    return dossier.model_dump(mode="json")


def test_dossier_rows_expose_money_as_numbers_and_keep_the_price_date() -> None:
    content = stored_shape()
    first = budget_rows(content)[0]
    assert first["Subtotal (US$)"] == 40.0 and first["Recurrencia"] == "mensual"
    assert first["Precio verificado el"] == content["budget"]["lines"][0]["price_checked_on"]
    assert roadmap_rows(content)[0]["Costo (US$)"] == 49.0
    assert flow_rows(content)[1]["Automatización"] == "automático"


def backend_for(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> TestClient:
    config = Settings(service_token=SecretStr(TOKEN))
    backend = TestClient(create_app(config, engine=engine, clock=lambda: NOW))
    backend.headers["Authorization"] = f"Bearer {TOKEN}"

    class LocalClient:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def __enter__(self) -> "LocalClient":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def get(self, path: str) -> httpx.Response:
            response: httpx.Response = backend.get(path)
            return response

        def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
            response: httpx.Response = backend.request(method, path, **kwargs)
            return response

    monkeypatch.setattr("nicheradar.dashboard.httpx.Client", LocalClient)
    monkeypatch.setenv("NR_DASHBOARD_PASSWORD", TOKEN)
    monkeypatch.setenv("NR_SERVICE_TOKEN", TOKEN)
    return backend


def open_market(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> tuple[AppTest, TestClient]:
    backend = backend_for(monkeypatch, engine)
    app = AppTest.from_file("../apps/dashboard/main.py", default_timeout=30).run()
    app.text_input[0].set_value(TOKEN)
    app.button[0].click().run()
    app.radio[0].set_value("Mercado").run()
    assert not app.exception
    return app, backend


@pytest.mark.postgres
def test_the_button_is_disabled_until_tentative_then_orders_the_research(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    with isolated_engine.begin() as connection:
        seed_niche(connection, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
    app, backend = open_market(monkeypatch, isolated_engine)
    order = next(b for b in app.button if b.label == "Iniciar investigación de flujo")
    assert order.disabled
    assert any("tentativo" in caption.value for caption in app.caption)

    next(box for box in app.selectbox if box.label == "Decisión del nicho").set_value("tentativo")
    next(button for button in app.button if button.label == "Guardar decisión").click().run()
    order = next(b for b in app.button if b.label == "Iniciar investigación de flujo")
    assert not order.disabled
    order.click().run()
    assert not app.exception
    items = backend.get("/api/v1/flow-research?niche_label=personal_finance").json()["items"]
    assert [item["status"] for item in items] == ["pendiente"]
    waiting = next(b for b in app.button if b.label == "Iniciar investigación de flujo")
    assert waiting.disabled  # an active request blocks a second one
    assert any("pendiente" in caption.value for caption in app.caption)


@pytest.mark.postgres
def test_dossier_text_is_rendered_as_plain_text(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    with isolated_engine.begin() as connection:
        seed_niche(connection, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
    app, backend = open_market(monkeypatch, isolated_engine)
    decision = {"format": "long", "decision": "tentativo"}
    path = "/api/v1/market/niches/personal_finance/decisions"
    assert backend.post(path, json=decision).status_code == 201
    created = backend.post(
        "/api/v1/flow-research", json={"niche_label": "personal_finance", "format": "long"}
    ).json()
    claim = backend.post(f"/api/v1/flow-research/{created['id']}/claim", json={"owner": "w1"})
    owner = claim.json()["lease_owner"]
    payload = valid_dossier(UUID(created["id"]), NOW)
    payload["verdict"]["thesis"] = HOSTILE
    accepted = backend.post(
        f"/api/v1/flow-research/{created['id']}/dossier", json={"owner": owner, "dossier": payload}
    )
    assert accepted.status_code == 200
    app.run()
    assert not app.exception
    assert any(text.value == HOSTILE for text in app.text)
    assert not any(HOSTILE in markdown.value for markdown in app.markdown)
    assert any("133" in text.value for text in app.text)  # the likely total is visible
