from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Operation
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.budget import reserve, settle
from nicheradar.services.channel_analysis import (
    channel_analysis_detail,
    list_channel_analyses,
    save_channel_analysis,
)
from nicheradar.services.channel_analysis_providers import (
    channel_analysis_youtube_limits,
    channel_analysis_youtube_tariffs,
)
from nicheradar.services.requests import mark_sent, prepare_request
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_save_then_list_then_detail(db: Connection) -> None:
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
    checkpoints = {
        "resolve": {"channel": {"id": "UC1", "title": "Science"}},
        "metrics": {
            "target_view_rate": 50.0,
            "comparable_best": 200.0,
            "comparable_worst": 10.0,
            "target_position": "within",
            "profit": {"status": "incomplete", "missing": ["videos_per_month"]},
        },
    }
    analysis_id = save_channel_analysis(db, run_id, profile_id, checkpoints, NOW)

    listed = list_channel_analyses(db, limit=20, offset=0)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == analysis_id
    assert listed["items"][0]["channel_external_id"] == "UC1"

    detail = channel_analysis_detail(db, analysis_id)
    assert detail is not None
    assert detail["snapshot"]["metrics"]["target_position"] == "within"

    assert channel_analysis_detail(db, "00000000-0000-0000-0000-000000000000") is None


def _run(db: Connection, profile_id: UUID) -> UUID:
    return insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": "channel_analysis",
            "status": "running",
            "configuration": {"channel_input": "@scienceexplained"},
        },
    )


def _spend(
    db: Connection,
    run_id: UUID,
    profile_id: UUID,
    operation: Operation,
    key: str,
    actual: Decimal | None,
    *,
    sent: bool = True,
) -> None:
    """Drive a request through the real reserve()/settle() lifecycle."""
    tariff = channel_analysis_youtube_tariffs()[operation]
    request_id = prepare_request(db, run_id, "youtube", operation, "scope", key, key, NOW)
    reserve(db, request_id, profile_id, tariff, channel_analysis_youtube_limits(Settings()), NOW)
    if not sent:
        settle(db, request_id, profile_id, None, NOW, not_sent=True)
        return
    mark_sent(db, request_id, NOW)
    settle(
        db,
        request_id,
        profile_id,
        None if actual is None else {tariff[0].unit: actual},
        NOW,
    )


@pytest.mark.postgres
def test_save_records_real_consumption_and_configuration(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(paid_limits_confirmed=True), initial_catalog())
    run_id = _run(db, profile_id)
    other_run_id = _run(db, profile_id)
    _spend(db, run_id, profile_id, Operation.SEARCH, "search-1", Decimal(100))
    _spend(db, run_id, profile_id, Operation.CHANNELS, "channels-1", Decimal(1))
    _spend(db, run_id, profile_id, Operation.VIDEOS, "videos-1", Decimal(1))
    # Sent, but the adapter could not prove the charge: still a liability, not spend.
    _spend(db, run_id, profile_id, Operation.UPLOADS, "uploads-1", None)
    # Certified never sent: released, must not count anywhere.
    _spend(db, run_id, profile_id, Operation.UPLOADS, "uploads-2", None, sent=False)
    # Another run's spend must not leak into this report.
    _spend(db, other_run_id, profile_id, Operation.CHANNELS, "channels-other", Decimal(1))

    configuration = {"channel_input": "@scienceexplained", "max_comparables": 8}
    analysis_id = save_channel_analysis(
        db, run_id, profile_id, {}, NOW, configuration=configuration
    )
    detail = channel_analysis_detail(db, analysis_id)
    assert detail is not None
    assert detail["consumption"] == {
        "confirmed": {"youtube_detail_quota": 2.0, "youtube_search_quota": 100.0},
        "reservations": [
            {"unit": "youtube_detail_quota", "status": "unknown_charge", "amount": 1.0}
        ],
    }
    assert detail["configuration"] == configuration


@pytest.mark.postgres
def test_expire_nulls_snapshot_only_when_retention_is_due(db: Connection) -> None:
    from datetime import timedelta

    from nicheradar.integrations.retention import expire

    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    checkpoints = {"resolve": {"channel": {"id": "UC1", "title": "Science"}}}
    due = save_channel_analysis(
        db, _run(db, profile_id), profile_id, checkpoints, NOW, configuration={"a": 1}
    )
    fresh = save_channel_analysis(
        db, _run(db, profile_id), profile_id, checkpoints, NOW + timedelta(days=30)
    )
    later = NOW + timedelta(days=181)  # past `due`'s 180-day retain_until, not `fresh`'s
    expire(db, later)

    expired = channel_analysis_detail(db, due, now=later)
    assert expired is not None
    assert expired["snapshot"] is None
    assert expired["expired_at"] == later
    assert expired["evidence_available"] is False
    # Small audit trail survives: what was asked and what it cost.
    assert expired["configuration"] == {"a": 1}
    assert expired["status"] == "completed"

    kept = channel_analysis_detail(db, fresh, now=later)
    assert kept is not None
    assert kept["snapshot"] == checkpoints
    assert kept["expired_at"] is None
    assert kept["evidence_available"] is True

    # Expired reports stay listed (same convention as the backlog), flagged unavailable.
    listed = {row["id"]: row for row in list_channel_analyses(db, now=later)["items"]}
    assert listed[due]["evidence_available"] is False
    assert listed[due]["snapshot"] is None
    assert listed[fresh]["evidence_available"] is True


@pytest.mark.postgres
def test_detail_hides_snapshot_past_retention_before_expire_runs(db: Connection) -> None:
    from datetime import timedelta

    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    analysis_id = save_channel_analysis(db, _run(db, profile_id), profile_id, {"resolve": {}}, NOW)
    detail = channel_analysis_detail(db, analysis_id, now=NOW + timedelta(days=181))
    assert detail is not None
    assert detail["snapshot"] is None
    assert detail["evidence_available"] is False
