"""Run inside only the NicheRadar dashboard container; never print credentials."""

import os
import sys
from decimal import Decimal

import httpx


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    url = os.environ["NR_API_URL"]
    assert url == "http://proy1-credito-riesgo_nicheradar-api:8000"
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as anonymous:
        assert anonymous.get("/health/live").status_code == 200
        assert anonymous.get("/api/v1/status").status_code == 401
    with httpx.Client(
        base_url=url,
        timeout=10,
        trust_env=False,
        headers={"Authorization": "Bearer " + os.environ["NR_SERVICE_TOKEN"]},
    ) as client:
        response = client.get("/api/v1/status")
        response.raise_for_status()
        status = response.json()
        assert status["mode"] == "live" and status["radar_paused"] is True
        assert status["database_configured"] is True
        assert status["providers"]["vidiq"]["credentials_configured"] is True
        assert status["providers"]["vidiq"]["live_enabled"] is True
        assert status["providers"]["youtube"]["credentials_configured"] is True
        assert status["providers"]["youtube"]["live_enabled"] is True
        assert status["explanations"]["enabled"] is True
        cost = client.get("/api/v1/consumption")
        cost.raise_for_status()
        assert set(cost.json()) >= {"confirmed", "reservations"}
        profile = client.get("/api/v1/profile").json()
        if mode in {"set-marker", "verify-restore"}:
            assert Decimal(profile["weekly_hours"]) == (15 if mode == "set-marker" else 17)
            version = profile.pop("version_number")
            profile["weekly_hours"] = "17" if mode == "set-marker" else "15"
            client.put(
                "/api/v1/profile", json={"profile": profile, "expected_version": version}
            ).raise_for_status()
            print(
                "profile_marker_saved"
                if mode == "set-marker"
                else "persistence_verified_profile_restored"
            )
        print(
            "api_auth_ok internal_database_ok live_paused vidiq_configured "
            "youtube_configured llm_configured"
        )
    assert httpx.get("http://127.0.0.1:8501/_stcore/health", timeout=5).status_code == 200
    if mode in {"ui", "monitoring"}:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_string(
            "from nicheradar.dashboard import render\nrender()", default_timeout=30
        ).run()
        assert not app.exception and len(app.radio) == 0 and len(app.json) == 0
        app.text_input[0].set_value("incorrect-password")
        app.button[0].click().run()
        assert not app.exception and len(app.radio) == 0 and len(app.json) == 0
        app.text_input[0].set_value(os.environ["NR_DASHBOARD_PASSWORD"])
        app.button[0].click().run()
        assert not app.exception and len(app.radio) == 1
        for page in ("Resumen", "Backlog", "Escenarios", "Configuración", "Operación"):
            app.radio[0].set_value(page).run()
            assert not app.exception
            print("dashboard_view_ok", page)
        print("dashboard_login_verified")
    if mode == "monitoring":
        # Exercise the installed UI with invented responses only. Never seed the VPS DB.
        fixture = AppTest.from_string(
            """
from unittest.mock import patch
from nicheradar.config import Settings
from nicheradar.dashboard import render_operations, render_research_status
status = {"radar_paused": True, "mode": "synthetic",
          "last_success_at": "2026-09-14T01:00:00Z",
          "research": {"reasons": ["technical_error"],
                       "last_observed_at": "2026-09-14T01:00:00Z",
                       "observation_age_hours": 6}}
cost = {"confirmed": [{"unit": "USD", "amount": "1.25"}],
        "reservations": [{"unit": "fixture:credits", "amount": "5", "status": "unknown_charge"}]}
def fake_api(config, method, path, **kwargs):
    assert method == "GET"
    if path.startswith("/providers"):
        return {
            "configuration": {"synthetic": {"credentials_configured": True, "policy": "enabled"}},
            "policies": [],
            "total": 0,
        }
    assert path.startswith("/jobs")
    return {"total": 1, "items": [{"id": "synthetic-ui-probe", "status": "failed",
        "source_mode": "synthetic", "error_code": "timeout", "consumption": cost,
        "coverage": {"complete": False, "work_kind": "catalog",
                     "catalog_pending": ["history"], "pending_reason": "timeout"}}]}
with patch("nicheradar.dashboard.api_request", side_effect=fake_api):
    render_research_status(Settings(), status)
    render_operations(Settings(), status)
""",
            default_timeout=30,
        ).run()
        assert not fixture.exception
        assert any("error técnico" in item.value for item in fixture.warning)
        assert any("Lote parcial: timeout" in item.value for item in fixture.warning)
        assert any("6.0 horas" in item.value for item in fixture.caption)
        assert any("13/09/2026 20:00" in item.value for item in fixture.caption)
        assert any(e.label.startswith("Consumo de ejecución") for e in fixture.expander)
        reservation_index = next(
            index
            for index, item in enumerate(fixture.dataframe)
            if "status" in item.value.columns and "unknown_charge" in item.value["status"].tolist()
        )
        assert fixture.dataframe[reservation_index].value.to_dict("records")[0]["unit"] == (
            "fixture:credits"
        )
        assert fixture.dataframe[reservation_index - 1].value.to_dict("records") == [
            {"unit": "USD", "amount": "1.25"}
        ]
        print("monitoring_fixture_verified no_database_writes")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception repr/tracebacks can contain configuration or HTTP headers.
        print("probe_failed", type(exc).__name__)
        raise SystemExit(1) from None
