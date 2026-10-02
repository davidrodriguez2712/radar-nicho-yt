"""Pilot preparation is local/read-only, not an account validation or pilot run."""

import json
import os
from datetime import timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, func, select, update
from streamlit.testing.v1 import AppTest

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Operation
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.pilot import preflight
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW, seed_evidence


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})
    for name in tuple(os.environ):
        if name.startswith("NR_") and not name.startswith("NR_TEST_"):
            monkeypatch.delenv(name)


@pytest.mark.postgres
def test_preflight_without_profile_is_private_and_never_seeds(isolated_engine: Engine) -> None:
    config = Settings(service_token=SecretStr(TOKEN))
    client = TestClient(create_app(config, engine=isolated_engine))
    assert client.get("/api/v1/pilot/preflight").status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    for _ in range(2):
        response = client.get("/api/v1/pilot/preflight")
        assert response.status_code == 200
        report = response.json()
        assert report["read_only"] is True
        assert report["provider_calls"] == 0
        assert report["ready"] is False
        assert report["budget"] is None
        assert "profile_configured" in report["blockers"]
    with isolated_engine.connect() as db:
        for table in s.metadata.tables.values():
            assert db.execute(select(func.count()).select_from(table)).scalar_one() == 0


@pytest.mark.postgres
def test_preflight_does_not_expire_old_evidence_or_expose_secrets(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        seed_evidence(db)
        db.execute(
            update(s.raw_observations).values(
                fetched_at=NOW - timedelta(days=400), retain_until=NOW - timedelta(days=399)
            )
        )
    sentinel = "fixture-private-provider-token"
    config = Settings(service_token=SecretStr(TOKEN), vidiq_token=SecretStr(sentinel))
    client = TestClient(create_app(config, engine=isolated_engine))
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.get("/api/v1/pilot/preflight")
    assert response.status_code == 200
    assert sentinel not in response.text
    assert TOKEN not in response.text
    report = response.json()
    assert report["credential_material_present"] is True
    assert "provider_connection_validated" in report["blockers"]
    assert report["budget"]["credits_per_run"] == 5
    assert report["budget"]["usd_per_run"] == "0"
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(s.raw_observations)).scalar_one() == 1


@pytest.mark.postgres
def test_registered_policies_do_not_enable_live_runtime_or_spending(db: Connection) -> None:
    seed_profile(db, CreatorProfile(paid_limits_confirmed=True), initial_catalog())
    for usage in ("query", "storage", "history", "derived"):
        insert_record(
            db,
            "provider_policies",
            {
                "provider": "vidiq",
                "operation": "*",
                "data_type": "metadata",
                "usage": usage,
                "version": "fixture-only",
                "status": "enabled",
                "effective_at": NOW,
                "evidence_source": "fixture-not-an-actual-permission",
                "retention_seconds": 86400,
            },
        )
    config = Settings(mode="live", vidiq_token=SecretStr("fixture-token"))
    report = preflight(db, config, NOW)
    assert len(report["policies"]) == 15
    assert all(policy["status"] == "enabled" for policy in report["policies"])
    assert "provider_policies_incomplete" not in report["blockers"]
    assert "paid_budget_confirmed" not in report["blockers"]
    assert "live_pipeline_connected" not in report["blockers"]
    assert "provider_account_scope_configured" in report["blockers"]
    assert "pilot_authorization_required" in report["blockers"]
    assert report["ready"] is False
    scheduled = preflight(db, config, NOW, scheduled=True)
    assert scheduled["scope"] == "scheduled"
    assert sum(policy["status"] == "policy_pending" for policy in scheduled["policies"]) == 4
    assert "provider_policies_incomplete" in scheduled["blockers"]


@pytest.mark.postgres
def test_complete_manual_preflight_is_ready_but_scheduling_needs_its_policy(
    db: Connection,
) -> None:
    seed_profile(db, CreatorProfile(paid_limits_confirmed=True), initial_catalog())
    for usage in ("query", "storage", "history", "derived"):
        insert_record(
            db,
            "provider_policies",
            {
                "provider": "vidiq",
                "operation": "*",
                "data_type": "metadata",
                "usage": usage,
                "version": "fixture-only",
                "status": "enabled",
                "effective_at": NOW,
                "evidence_source": "fixture-not-an-actual-permission",
                "retention_seconds": 86400,
            },
        )
    config = Settings(
        mode="live",
        vidiq_token=SecretStr("fixture-token"),
        vidiq_auth_scope="personal-primary",
        vidiq_connection_validated_at=NOW,
        vidiq_credit_cycle_started_at=NOW - timedelta(days=10),
        vidiq_live_enabled=True,
        vidiq_pilot_authorized=True,
    )
    manual = preflight(db, config, NOW)
    assert manual["ready"] is True
    assert manual["blockers"] == []
    future_dated = preflight(
        db,
        config.model_copy(
            update={
                "vidiq_connection_validated_at": NOW + timedelta(seconds=1),
                "vidiq_credit_cycle_started_at": NOW + timedelta(seconds=1),
            }
        ),
        NOW,
    )
    assert "provider_connection_validated" in future_dated["blockers"]
    assert "credit_cycle_start_configured" in future_dated["blockers"]
    scheduled = preflight(db, config, NOW, scheduled=True)
    assert scheduled["ready"] is False
    assert scheduled["blockers"] == ["provider_policies_incomplete"]


@pytest.mark.postgres
def test_youtube_enrichment_requires_its_own_limits_policies_and_retention(
    db: Connection,
) -> None:
    seed_profile(db, CreatorProfile(paid_limits_confirmed=True), initial_catalog())
    for provider in ("vidiq", "youtube"):
        operations = ("*",) if provider == "vidiq" else (Operation.VIDEOS.value,)
        for operation in operations:
            for usage in ("query", "storage", "history", "derived"):
                insert_record(
                    db,
                    "provider_policies",
                    {
                        "provider": provider,
                        "operation": operation,
                        "data_type": "metadata",
                        "usage": usage,
                        "version": "fixture-only",
                        "status": "enabled",
                        "effective_at": NOW,
                        "evidence_source": "fixture-not-an-actual-permission",
                        "retention_seconds": 7 * 86400,
                    },
                )
    config = Settings(
        mode="live",
        vidiq_token=SecretStr("fixture-token"),
        vidiq_auth_scope="personal-primary",
        vidiq_connection_validated_at=NOW,
        vidiq_credit_cycle_started_at=NOW - timedelta(days=10),
        vidiq_live_enabled=True,
        vidiq_pilot_authorized=True,
        youtube_api_key=SecretStr("youtube-fixture-key"),
        youtube_auth_scope="youtube-fixture",
        youtube_connection_validated_at=NOW,
        youtube_live_enabled=True,
        youtube_quota_per_run=2,
        youtube_quota_per_week=10,
        youtube_quota_per_month=20,
    )
    report = preflight(db, config, NOW)
    assert report["ready"] is True
    assert report["provider"] == "vidiq+youtube"
    assert len(report["policies"]) == 19
    db.execute(
        update(s.provider_policies)
        .where(
            s.provider_policies.c.provider == "youtube",
            s.provider_policies.c.usage == "storage",
        )
        .values(retention_seconds=31 * 86400)
    )
    invalid = preflight(db, config, NOW)
    youtube_storage = next(
        policy
        for policy in invalid["policies"]
        if policy["provider"] == "youtube" and policy["usage"] == "storage"
    )
    assert youtube_storage["status"] == "retention_exceeds_youtube_limit"
    assert "provider_policies_incomplete" in invalid["blockers"]


@pytest.mark.postgres
@pytest.mark.parametrize("kind", ["missing_retention", "empty_evidence", "disabled", "future"])
def test_policy_gaps_remain_explicit(db: Connection, kind: str) -> None:
    insert_record(
        db,
        "provider_policies",
        {
            "provider": "vidiq",
            "operation": Operation.CHANNEL_SEARCH.value,
            "data_type": "metadata",
            "usage": "storage",
            "version": "fixture-only",
            "status": "disabled" if kind == "disabled" else "enabled",
            "effective_at": NOW + timedelta(days=1) if kind == "future" else NOW,
            "evidence_source": " " if kind == "empty_evidence" else "fixture-only",
            "retention_seconds": None if kind == "missing_retention" else 86400,
        },
    )
    report = preflight(db, Settings(), NOW)
    policy = next(
        p
        for p in report["policies"]
        if (p["operation"] == Operation.CHANNEL_SEARCH.value and p["usage"] == "storage")
    )
    assert (
        policy["status"]
        == {
            "missing_retention": "retention_not_configured",
            "empty_evidence": "policy_evidence_missing",
            "disabled": "policy_disabled",
            "future": "policy_pending",
        }[kind]
    )
    assert "provider_policies_incomplete" in report["blockers"]


@pytest.mark.postgres
def test_dashboard_preflight_button_only_reads(
    monkeypatch: pytest.MonkeyPatch, db: Connection
) -> None:
    from nicheradar import dashboard

    report = preflight(db, Settings(), NOW)
    request = Mock(return_value=report)
    monkeypatch.setattr(dashboard, "api_request", request)
    app = AppTest.from_string(
        "from nicheradar.config import Settings\n"
        "from nicheradar.dashboard import render_pilot_preflight\n"
        "render_pilot_preflight(Settings())\n"
    ).run()
    request.assert_not_called()
    app.button[0].click().run()
    assert not app.exception
    assert request.call_count == 1
    assert request.call_args.args[1:] == ("GET", "/pilot/preflight")
    assert "solo lectura" in app.info[0].value
    assert "pendiente" in app.warning[0].value
    assert "fixture-token" not in json.dumps([item.value for item in app.markdown])
