import os
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, insert

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import credit_balances
from nicheradar.services.channel_analysis import save_channel_analysis
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW

VIDIQ_AUTH_SCOPE = "personal-primary"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})
    for name in tuple(os.environ):
        if name.startswith("NR_") and not name.startswith("NR_TEST_"):
            monkeypatch.delenv(name)


def _live_ready_settings() -> Settings:
    # Mirrors tests/test_pilot_preflight.py::test_complete_manual_preflight_is_ready_...,
    # the established pattern for a preflight report with ready=True in manual scope.
    return Settings(
        service_token=SecretStr(TOKEN),
        mode="live",
        vidiq_token=SecretStr("fixture-token"),
        vidiq_auth_scope=VIDIQ_AUTH_SCOPE,
        vidiq_connection_validated_at=NOW,
        vidiq_credit_cycle_started_at=NOW - timedelta(days=10),
        vidiq_live_enabled=True,
        vidiq_pilot_authorized=True,
    )


def _seed_live_ready(
    engine: Engine,
    *,
    available_credits: Decimal | None,
    confirmed_usage: Decimal = Decimal(0),
    stale: bool = False,
) -> None:
    with engine.begin() as db:
        seed_profile(
            db,
            CreatorProfile(paid_limits_confirmed=True, channel_analysis_credits_per_run=50),
            initial_catalog(),
        )
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
        if available_credits is not None:
            db.execute(
                insert(credit_balances).values(
                    provider="vidiq",
                    auth_scope=VIDIQ_AUTH_SCOPE,
                    unit="vidiq_credit",
                    renewable_remaining=available_credits,
                    renewable_allocation=available_credits,
                    additional_remaining=Decimal(0),
                    cycle_started_at=NOW,
                    renews_at=NOW + timedelta(days=30),
                    observed_at=NOW,
                    # A stale row (expired per balance_needs_refresh()) must be treated
                    # the same as no row at all: fail open, never a permanent block.
                    retain_until=NOW - timedelta(days=1) if stale else NOW + timedelta(days=7),
                    refresh_required=False,
                    confirmed_usage=confirmed_usage,
                )
            )


@pytest.mark.postgres
def test_post_requires_real_vidiq_balance_headroom_in_live_mode(isolated_engine: Engine) -> None:
    # Below the declared channel_analysis_credits_per_run cap (50): must not enqueue.
    _seed_live_ready(isolated_engine, available_credits=Decimal(10))
    client = TestClient(
        create_app(_live_ready_settings(), engine=isolated_engine, clock=lambda: NOW)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "@x"},
        headers={"Idempotency-Key": "c" * 10},
    )
    assert response.status_code == 409
    assert "insuficiente" in response.json()["detail"]


@pytest.mark.postgres
def test_post_enqueues_when_real_vidiq_balance_covers_the_declared_cap(
    isolated_engine: Engine,
) -> None:
    # At the declared cap (50): must enqueue.
    _seed_live_ready(isolated_engine, available_credits=Decimal(50))
    client = TestClient(
        create_app(_live_ready_settings(), engine=isolated_engine, clock=lambda: NOW)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "@x"},
        headers={"Idempotency-Key": "d" * 10},
    )
    assert response.status_code == 202
    assert "job_id" in response.json()


@pytest.mark.postgres
def test_post_balance_check_ignores_confirmed_usage_lifetime_counter(
    isolated_engine: Engine,
) -> None:
    # confirmed_usage is a separate lifetime counter (used only for balance-
    # reconciliation deltas elsewhere, see services/budget.py::credit_usage()) -- it
    # must play NO role in this check. renewable_remaining/additional_remaining are
    # already net of past spend by vidIQ's own API semantics. A large lifetime
    # confirmed_usage alongside a healthy current balance must still enqueue.
    _seed_live_ready(
        isolated_engine, available_credits=Decimal(50), confirmed_usage=Decimal(1_000_000)
    )
    client = TestClient(
        create_app(_live_ready_settings(), engine=isolated_engine, clock=lambda: NOW)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "@x"},
        headers={"Idempotency-Key": "e" * 10},
    )
    assert response.status_code == 202
    assert "job_id" in response.json()


@pytest.mark.postgres
def test_post_allows_enqueue_when_no_balance_row_exists_yet(isolated_engine: Engine) -> None:
    # This pre-flight check is an early, advisory signal only -- Gateway/reserve()
    # remains the real enforcement point (with its own live balance refresh). A
    # missing credit_balances row (e.g. a fresh install that never ran a pilot job,
    # or one that expired after 7 idle days via retention.expire()) must fail OPEN,
    # never permanently block live channel analyses.
    _seed_live_ready(isolated_engine, available_credits=None)
    client = TestClient(
        create_app(_live_ready_settings(), engine=isolated_engine, clock=lambda: NOW)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "@x"},
        headers={"Idempotency-Key": "f" * 10},
    )
    assert response.status_code == 202
    assert "job_id" in response.json()


@pytest.mark.postgres
def test_post_allows_enqueue_when_balance_row_is_stale(isolated_engine: Engine) -> None:
    # A stale row (per the existing balance_needs_refresh() helper) must be treated
    # the same as a missing row: fail open, even though its own numbers would read
    # as insufficient if taken at face value.
    _seed_live_ready(isolated_engine, available_credits=Decimal(0), stale=True)
    client = TestClient(
        create_app(_live_ready_settings(), engine=isolated_engine, clock=lambda: NOW)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "@x"},
        headers={"Idempotency-Key": "g" * 10},
    )
    assert response.status_code == 202
    assert "job_id" in response.json()


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


def _seed_saved_analysis(engine: Engine, *, channel: dict[str, Any] | None = None) -> str:
    """Persist a completed channel-analysis row directly (bypassing the async worker
    pipeline, which this API test suite never runs), so DELETE/deep-history have a real
    row to act on."""
    channel = channel if channel is not None else {"id": "UC1", "title": "Science"}
    with engine.begin() as db:
        profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
        run_id = insert_record(
            db,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": "synthetic",
                "trigger": "channel_analysis",
                "status": "succeeded",
                "configuration": {"channel_input": "@scienceexplained"},
            },
        )
        analysis_id = save_channel_analysis(
            db,
            run_id,
            profile_id,
            {"resolve": {"channel": channel}},
            NOW,
        )
    return str(analysis_id)


@pytest.mark.postgres
def test_delete_endpoint_returns_204_then_404(isolated_engine: Engine) -> None:
    analysis_id = _seed_saved_analysis(isolated_engine)
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    path = f"/api/v1/channel-analyses/{analysis_id}"

    assert client.delete(path).status_code == 401

    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.delete(path)
    assert response.status_code == 204
    assert response.content == b""

    # The now-expired row's content must be withheld (same convention as retention.expire()
    # -- detail endpoint stays 200 but snapshot is gone) and it must drop out of the
    # default list, not just become un-deletable again -- proves this is the service's
    # real expire_now(), not a stub that only flips a status code.
    detail = client.get(path)
    assert detail.status_code == 200
    assert detail.json()["snapshot"] is None
    assert detail.json()["evidence_available"] is False

    listing = client.get("/api/v1/channel-analyses")
    assert analysis_id not in {item["id"] for item in listing.json()["items"]}
    listing_all = client.get("/api/v1/channel-analyses", params={"include_expired": True})
    assert analysis_id in {item["id"] for item in listing_all.json()["items"]}

    # A second delete of the same (now-expired) row must 404, not succeed again.
    response_again = client.delete(path)
    assert response_again.status_code == 404


@pytest.mark.postgres
def test_delete_endpoint_404s_for_unknown_id(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.delete("/api/v1/channel-analyses/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.postgres
def test_deep_history_estimate_endpoint_returns_real_quota_units(isolated_engine: Engine) -> None:
    analysis_id = _seed_saved_analysis(
        isolated_engine, channel={"id": "UC1", "title": "Science", "video_count": 184}
    )
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.get(f"/api/v1/channel-analyses/{analysis_id}/deep-history/estimate")
    assert response.status_code == 200
    # ceil(184/50) = 4 pages * 2 real quota units per page (playlistItems.list +
    # videos.list) = 8 -- same real example as
    # tests/test_channel_analysis_deep_history.py::test_estimate_cost_matches_real_example.
    assert response.json() == {"quota_units": 8}


@pytest.mark.postgres
def test_deep_history_estimate_endpoint_returns_none_when_video_count_unknown(
    isolated_engine: Engine,
) -> None:
    analysis_id = _seed_saved_analysis(isolated_engine)  # no video_count on this channel
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.get(f"/api/v1/channel-analyses/{analysis_id}/deep-history/estimate")
    assert response.status_code == 200
    assert response.json() == {"quota_units": None}


@pytest.mark.postgres
def test_deep_history_estimate_endpoint_404s_for_unknown_analysis(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.get(
        "/api/v1/channel-analyses/00000000-0000-0000-0000-000000000000/deep-history/estimate"
    )
    assert response.status_code == 404


@pytest.mark.postgres
def test_deep_history_execute_endpoint_runs_synthetic_fetch_and_merges_into_snapshot(
    isolated_engine: Engine,
) -> None:
    # published_at far enough before the videos' synthetic published_at (NOW - 10 days,
    # see SyntheticProvider.fetch's generic video fixture) for a real, unambiguous
    # days_to_first_breakout.
    channel = {
        "id": "UC1",
        "title": "Science",
        "uploads_playlist": "UU1",
        "published_at": (NOW - timedelta(days=365)).isoformat(),
        "subscribers": 1000,
    }
    analysis_id = _seed_saved_analysis(isolated_engine, channel=channel)
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"

    response = client.post(f"/api/v1/channel-analyses/{analysis_id}/deep-history")
    assert response.status_code == 200
    body = response.json()
    # One SyntheticProvider UPLOADS page (no next_page) + one VIDEOS batch for its ids.
    assert body == {
        "status": "computed",
        "days_to_first_breakout": 355,
        "quota_units_spent": 2,
    }

    detail = client.get(f"/api/v1/channel-analyses/{analysis_id}").json()
    assert detail["snapshot"]["deep_history"] == body
    # The pre-existing resolve.channel snapshot must survive untouched -- proves a real
    # read-then-merge (`snapshot | {"deep_history": ...}`), not an overwrite that would
    # have dropped it.
    assert detail["snapshot"]["resolve"]["channel"]["id"] == "UC1"


@pytest.mark.postgres
def test_deep_history_execute_endpoint_404s_for_unknown_analysis(isolated_engine: Engine) -> None:
    client = TestClient(
        create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine)
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses/00000000-0000-0000-0000-000000000000/deep-history"
    )
    assert response.status_code == 404
