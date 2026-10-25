# tests/test_pilots_dashboard.py
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from streamlit.testing.v1 import AppTest

from nicheradar.pilots_dashboard import (
    contact_label,
    event_rows,
    portfolio_rows,
    rule_rows,
    totals_text,
)
from tests.test_flow_research_dashboard import backend_for
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE, deliver, launched, report, send, video


def item(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pilot_id": "pil_20260913_x",
        "status": "decision_pendiente",
        "niche_label": "x",
        "format": "long",
        "target_channel": "canal-historias",
        "authorized_at": "2026-09-13T00:00:00Z",
        "last_report_at": None,
        "channel_last_contact_at": None,
        "totals": {"published": 10, "measured": 8, "spent_usd": "3.10"},
        "proposal": {"action": "seguir", "reason": "r"},
        "needs_decision": True,
    }
    base.update(over)
    return base


def test_contact_label_flags_a_channel_that_went_silent() -> None:
    now = datetime(2026, 9, 13, tzinfo=UTC)
    assert contact_label(None, now) == "nunca"
    assert contact_label((now - timedelta(minutes=10)).isoformat(), now) == "hace menos de 1 h"
    assert contact_label((now - timedelta(hours=5)).isoformat(), now) == "hace 5 h"
    assert contact_label((now - timedelta(days=2)).isoformat(), now) == "hace 2 d"
    assert contact_label((now - timedelta(days=5)).isoformat(), now) == "hace 5 d (sin contacto)"


def test_portfolio_rows_show_the_proposal_and_whether_the_human_must_decide() -> None:
    row = portfolio_rows([item()], datetime(2026, 9, 13, tzinfo=UTC))[0]
    assert row["NicheRadar propone"] == "seguir" and row["¿Te toca decidir?"] == "sí"
    assert row["Videos"] == "10 publicados / 8 medidos" and row["Costo real (US$)"] == 3.1
    quiet = portfolio_rows(
        [item(needs_decision=False, proposal={"action": "sin_datos_suficientes", "reason": "r"})],
        datetime(2026, 9, 13, tzinfo=UTC),
    )[0]
    assert quiet["NicheRadar propone"] == "sin datos suficientes"


def test_detail_helpers() -> None:
    detail = {
        "evaluation": {
            "rules": [
                {"text": "t", "milestone": "video:10", "status": "no_evaluable", "detail": "d"}
            ],
            "totals": {
                "videos": 2,
                "published": 2,
                "measured": 1,
                "spent_usd": 0.6,
                "equivalent_usd": 3.0,
                "machine_minutes": 60,
                "machine_minutes_complete": False,
            },
        },
        "events": [{"at": "2026-09-13T00:00:00Z", "actor": "david", "kind": "authorized"}],
    }
    assert rule_rows(detail)[0]["Estado"].startswith("no se puede evaluar")
    assert event_rows(detail)[0]["Qué"] == "authorized"
    assert (
        "incompleto" in totals_text(detail)[1] and "no es dinero gastado" in totals_text(detail)[1]
    )


@pytest.mark.postgres
def test_the_portfolio_page_renders_without_errors_and_never_renders_markdown(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    hostile = report(pilot_id, [video(1)], note="**negrita** <script>alert(1)</script>")
    assert send(api, token, pilot_id, hostile).status_code == 200
    backend = backend_for(monkeypatch, isolated_engine)
    assert isinstance(backend, TestClient)
    app = AppTest.from_file("../apps/dashboard/main.py", default_timeout=30).run()
    app.text_input[0].set_value(TOKEN)
    app.button[0].click().run()
    app.radio[0].set_value("Portafolio").run()
    assert not app.exception
    assert any("Portafolio de pilotos" in s.value for s in app.subheader)
    text = " ".join(t.value for t in app.text)
    assert "Propuesta de NicheRadar" in text and "<script>" not in text
    assert BASE and NOW
