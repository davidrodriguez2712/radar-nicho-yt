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
from nicheradar.flow_research.contracts import DossierV2
from nicheradar.flow_research_dashboard import (
    budget_rows,
    flow_rows,
    language_options,
    milestone_rows,
    rights_rows,
    roadmap_rows,
    stage_rows,
    suggested_language,
)
from tests.flow_research_samples import valid_dossier
from tests.test_foundation import TOKEN
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW

HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def stored_shape() -> dict[str, Any]:
    dossier = DossierV2.model_validate(valid_dossier(UUID(int=1), NOW))
    return dossier.model_dump(mode="json")


def test_dossier_rows_expose_money_as_numbers_and_keep_the_price_date() -> None:
    content = stored_shape()
    first = budget_rows(content)[0]
    assert first["Subtotal (US$)"] == 40.0 and first["Recurrencia"] == "mensual"
    assert first["Precio verificado el"] == content["budget"]["lines"][0]["price_checked_on"]
    assert roadmap_rows(content)[0]["Costo (US$)"] == 49.0
    assert flow_rows(content)[1]["Automatización"] == "automático"


def test_the_v2_sections_render_rights_and_the_automation_plan() -> None:
    content = stored_shape()
    assert rights_rows(content)[1]["Origen"] == "con licencia"
    assert rights_rows(content)[0]["Requiere permiso"] == "no"
    stage = stage_rows(content)[0]
    assert stage["Minutos humanos"] == 20 and "Voz sintética (API" in stage["Herramientas"]
    assert [row["Hito"] for row in milestone_rows(content)] == [1, 2]
    assert milestone_rows(content)[1]["Depende de"] == "1"


def _render(content):  # type: ignore[no-untyped-def]  # AppTest runs it as a standalone script
    from nicheradar.flow_research_dashboard import render_dossier as render

    render(content)


def test_a_stored_v1_dossier_still_renders_with_a_notice() -> None:
    legacy = {k: v for k, v in stored_shape().items() if k not in ("rights", "automation_plan")}
    legacy["schema_version"] = "dossier-v1"
    app = AppTest.from_function(_render, kwargs={"content": legacy}).run()
    assert not app.exception
    assert any("no evalúa derechos" in item.value for item in app.caption)


def test_a_v2_dossier_renders_its_rights_and_plan_sections() -> None:
    app = AppTest.from_function(_render, kwargs={"content": stored_shape()}).run()
    assert not app.exception
    titles = [item.value for item in app.markdown]
    assert "**Derechos del material**" in titles
    assert "**Plan de automatización por etapa**" in titles
    assert "**Hitos de implementación**" in titles


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
        "/api/v1/flow-research",
        json={"niche_label": "personal_finance", "format": "long", "language": "en"},
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


def test_the_dominant_language_is_suggested_only_when_it_is_clear() -> None:
    clear = [{"language": "en", "share_pct": 80.0}, {"language": "es", "share_pct": 20.0}]
    assert suggested_language(clear) == "en"
    tie = [{"language": "en", "share_pct": 50.0}, {"language": "es", "share_pct": 50.0}]
    assert suggested_language(tie) is None
    mostly_unknown = [
        {"language": "unknown", "share_pct": 70.0},
        {"language": "en", "share_pct": 30.0},
    ]
    assert suggested_language(mostly_unknown) is None
    assert suggested_language([]) is None
    assert "unknown" not in language_options(mostly_unknown)
    assert language_options(clear)[:2] == ["en", "es"]


@pytest.mark.postgres
def test_without_a_dominant_language_nothing_is_preselected_and_the_button_waits(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    with isolated_engine.begin() as connection:
        seed_niche(connection, "personal_finance", (1500, 2000), price=67_500)
        seed_niche(connection, "personal_finance", (2500, 3000), price=67_500, language="es")
    app, backend = open_market(monkeypatch, isolated_engine)
    decision = {"format": "long", "decision": "tentativo"}
    path = "/api/v1/market/niches/personal_finance/decisions"
    assert backend.post(path, json=decision).status_code == 201
    app.run()
    chooser = next(box for box in app.selectbox if box.label == "Idioma de la investigación")
    assert chooser.value is None
    order = next(b for b in app.button if b.label == "Iniciar investigación de flujo")
    assert order.disabled
    chooser.set_value("es").run()
    order = next(b for b in app.button if b.label == "Iniciar investigación de flujo")
    assert not order.disabled
    order.click().run()
    items = backend.get("/api/v1/flow-research?niche_label=personal_finance").json()["items"]
    assert [(item["status"], item["language"]) for item in items] == [("pendiente", "es")]


@pytest.mark.postgres
def test_the_scope_banner_does_not_claim_english_only(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    app, _ = open_market(monkeypatch, isolated_engine)
    banner = " ".join(markdown.value for markdown in app.markdown if "nr-scope" in markdown.value)
    assert "Idioma elegido por investigación" in banner
    assert "Contenido en inglés" not in banner
