import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, select
from streamlit.testing.v1 import AppTest

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.backlog import append_evaluation
from nicheradar.workers.main import tick
from tests.test_foundation import TOKEN

pytestmark = pytest.mark.postgres


def test_dashboard_navigation_and_operation(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    backend = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
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
    app = AppTest.from_file("../apps/dashboard/main.py", default_timeout=30).run()
    app.text_input[0].set_value(TOKEN)
    app.button[0].click().run()
    assert not app.exception
    assert "Modo sintético" in app.info[0].value
    app.radio[0].set_value("Operación").run()
    next(
        button for button in app.button if button.label == "Reanudar radar sintético"
    ).click().run()
    assert not app.exception
    assert tick(Settings(), isolated_engine)["status"] == "succeeded"
    app.run()
    assert not app.exception
    assert any("Cobertura de ejecución" in item.label for item in app.expander)
    app.radio[0].set_value("Backlog").run()
    assert not app.exception
    assert "review_state" in app.dataframe[0].value.columns
    assert any(item.value == "Explicación de la evaluación" for item in app.subheader)
    assert any(item.label == "Trazabilidad de cada afirmación" for item in app.expander)
    assert any(item.value == "Posiciones históricas" for item in app.subheader)
    # Paging an empty slice is not the same as finding no niches. A filter change resets it.
    next(item for item in app.number_input if item.label == "Página").set_value(2).run()
    assert not app.exception
    assert any("No hay resultados en esta página" in item.value for item in app.info)
    next(item for item in app.text_input if item.label == "Buscar tema").set_value(
        "unmatched-fixture"
    ).run()
    assert not app.exception
    assert next(item for item in app.number_input if item.label == "Página").value == 1
    next(item for item in app.text_input if item.label == "Buscar tema").set_value("").run()
    assert not app.exception
    assert "review_state" in app.dataframe[0].value.columns
    selected = next(item for item in app.selectbox if item.label == "Abrir detalle").value
    raw = backend.get(f"/api/v1/opportunities/{selected}").json()["evidence"][0]["payload"]
    assert any(json.loads(item.value) == raw for item in app.json)
    # Compare two retained versions through the actual dashboard/API path.
    selected_id = backend.get("/api/v1/opportunities").json()["items"][0]["id"]
    from uuid import UUID

    with isolated_engine.begin() as connection:
        original = dict(
            connection.execute(
                select(s.evaluation_versions).where(
                    s.evaluation_versions.c.opportunity_id == UUID(selected_id)
                )
            )
            .mappings()
            .one()
        )
        for key in ("id", "opportunity_id", "version"):
            original.pop(key)
        append_evaluation(connection, UUID(selected_id), original)
    app.run()
    assert not app.exception
    assert next(item for item in app.selectbox if item.label == "Evaluación actual").value == 2
    assert next(item for item in app.selectbox if item.label == "Evaluación anterior").value == 1
    next(
        button for button in app.button if button.label == "Guardar receta y evaluar"
    ).click().run()
    assert not app.exception
    selected_opportunity = backend.get("/api/v1/opportunities").json()["items"][0]["id"]
    scoring_field = next(
        field for field in app.text_area if field.label == "Supuestos de puntuación (JSON)"
    )
    assert scoring_field.value is not None
    scoring = json.loads(scoring_field.value)
    scoring["retention_basis"] = "Original synthetic test assumptions; no external data"
    scoring["retain_until"] = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    scoring_field.set_value(json.dumps(scoring))
    next(
        button for button in app.button if button.label == "Guardar supuestos de puntuación"
    ).click().run()
    assert not app.exception
    stored_scoring = backend.get(f"/api/v1/opportunities/{selected_opportunity}/scoring").json()
    assert stored_scoring["version"] == 1
    assert stored_scoring["advertising"]["scoring_value"] is None
    # The default recipe auto-applies during the worker's evaluation stage and now
    # fully declares tool capacity, so Creator Fit resolves to a real score.
    assert (
        backend.get(f"/api/v1/opportunities/{selected_opportunity}/production").json()[
            "assessment"
        ]["score"]
        == "88.75"
    )
    next(select for select in app.selectbox if select.label == "Estado de revisión").set_value(
        "dismissed"
    )
    next(button for button in app.button if button.label == "Guardar decisión").click().run()
    assert not app.exception
    assert backend.get("/api/v1/opportunities?state=dismissed").json()["total"] == 1
    app.radio[0].set_value("Configuración").run()
    assert not app.exception
    next(
        field for field in app.number_input if field.label == "Horas disponibles por semana"
    ).set_value(18.0)
    next(
        field
        for field in app.number_input
        if field.label == "Actualizar seleccionados cada (horas)"
    ).set_value(48)
    next(button for button in app.button if button.label == "Guardar límites").click().run()
    assert not app.exception
    assert backend.get("/api/v1/profile").json()["weekly_hours"] == "18.0"
    assert backend.get("/api/v1/profile").json()["selected_refresh_hours"] == 48
    app.radio[0].set_value("Escenarios").run()
    next(
        button for button in app.button if button.label == "Calcular y guardar escenario"
    ).click().run()
    assert not app.exception
    assert (
        backend.get("/api/v1/scenarios").json()["items"][0]["result"]["status"] == "not_evaluable"
    )
    app.radio[0].set_value("Análisis de canal").run()
    assert not app.exception
    assert "URL, handle o ID" in str(app.text_input[-1].label)
    assert any("Todavía no hay análisis de canal guardados" in item.value for item in app.info)
