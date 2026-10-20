# tests/test_market_dashboard.py
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from streamlit.testing.v1 import AppTest

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.market_dashboard import INSUFFICIENT, backlog_rows, listing_rows
from tests.test_foundation import TOKEN
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW


def item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "niche_label": "personal_finance",
        "format": "long",
        "opportunity": {"value": 71.5, "state": "scored"},
        "automation": {"value": 83.0, "policy_risk": {"mean": 1.0, "level": "medio"}},
        "confidence": "media",
        "metrics": {
            "n_listings": 12,
            "n_income": 7,
            "income_median": 1400.0,
            "multiple_median": 2.4,
        },
        "rpm_mid": 10.0,
        "trend": 3.5,
        "decision": {"decision": "tentativo"},
    }
    return base | overrides


def test_backlog_rows_keep_scores_confidence_and_missing_evidence_visible() -> None:
    rows = backlog_rows(
        [
            item(),
            item(
                niche_label="cooking_recipes",
                opportunity={"value": None, "state": "insufficient_evidence"},
                automation={"value": None, "policy_risk": {"mean": None, "level": None}},
                rpm_mid=None,
                trend=None,
                confidence="baja",
            ),
        ]
    )
    first, second = rows
    assert first["Opportunity"] == 71.5 and first["Automatización"] == 83.0
    assert first["Riesgo de política"] == "medio" and first["Confianza"] == "media"
    assert first["Ingreso mediano (US$/mes)"] == 1400.0 and first["RPM referencia"] == 10.0
    assert second["Opportunity"] == INSUFFICIENT and second["Automatización"] == INSUFFICIENT
    assert second["RPM referencia"] == "sin calibrar" and second["Riesgo de política"] == "sin dato"
    assert second["Decisión"] == "tentativo" and first["Fichas"] == 12


def test_listing_rows_label_every_figure_as_declared() -> None:
    rows = listing_rows(
        [
            {
                "title": "Calm Money",
                "url": "https://dealbaron.test/listing/1",
                "status": "active",
                "price_usd": 4500.0,
                "subscribers": 120_000,
                "income_monthly_usd": 900.0,
                "expense_monthly_usd": None,
                "verification": "mismatch",
                "real_subscribers": 30_000,
            }
        ]
    )
    row = rows[0]
    assert row["Suscriptores declarados"] == 120_000 and row["Suscriptores en YouTube"] == 30_000
    assert row["Ingreso declarado (US$/mes)"] == 900.0 and row["Gasto declarado (US$/mes)"] is None
    assert row["Verificación"] == "no coincide"


@pytest.mark.postgres
def test_market_tab_decisions_prefill_and_scraper_controls(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    with isolated_engine.begin() as connection:
        seed_niche(connection, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
        seed_niche(connection, "cooking_recipes", (400, 500))
    config = Settings(service_token=SecretStr(TOKEN))
    backend = TestClient(create_app(config, engine=isolated_engine, clock=lambda: NOW))
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

    app.radio[0].set_value("Mercado").run()
    assert not app.exception
    frame = app.dataframe[0].value
    assert list(frame["Nicho"]) == ["personal_finance", "cooking_recipes"]
    assert frame.loc[1, "Opportunity"] == INSUFFICIENT
    assert any("no son ingresos verificados" in caption.value for caption in app.caption)

    next(box for box in app.selectbox if box.label == "Decisión del nicho").set_value("tentativo")
    next(field for field in app.text_input if field.label == "Nota").set_value("investigar")
    next(button for button in app.button if button.label == "Guardar decisión").click().run()
    assert not app.exception
    stored = backend.get("/api/v1/market/niches?format=long").json()["items"][0]["decision"]
    assert stored["decision"] == "tentativo" and stored["note"] == "investigar"

    analyze = next(button for button in app.button if button.label == "Analizar canal")
    assert not analyze.help  # a seller title must never reach a Markdown-rendered tooltip
    analyze.click().run()
    assert not app.exception
    assert app.radio[0].value == "Análisis de canal"
    prefilled = next(f for f in app.text_input if f.label == "URL, handle o ID del canal")
    assert str(prefilled.value).startswith("https://www.youtube.com/@channel")

    app.radio[0].set_value("Operación").run()
    assert not app.exception
    assert any(h.value == "Operación del scraper de mercado" for h in app.subheader)
    next(button for button in app.button if button.label == "Reanudar scraper").click().run()
    assert backend.get("/api/v1/market/schedule").json()["paused"] is False
    next(button for button in app.button if button.label == "Pausar scraper").click().run()
    assert backend.get("/api/v1/market/schedule").json()["paused"] is True
