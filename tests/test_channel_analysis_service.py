from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.discovery.channel_analysis import compute_panorama
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.integrations.contracts import Channel, Operation, Video
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.budget import reserve, settle
from nicheradar.services.channel_analysis import (
    channel_analysis_detail,
    expire_now,
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


@pytest.mark.postgres
def test_list_channel_analyses_includes_score(db: Connection) -> None:
    # Builds a real snapshot the same way the pipeline's "metrics" stage does: a real
    # compute_panorama() result (pure function, no DB/network needed) embedded under
    # snapshot["metrics"]["panorama"], so compute_score (Task 9) sees genuine computed
    # metrics rather than a hand-rolled stand-in dict.
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
    comparable_videos: dict[str, tuple[Video, ...]] = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    panorama = compute_panorama(
        comparable_videos,
        (Channel(id="UC_a", title="A"), Channel(id="UC_b", title="B")),
        50_000,
        NOW,
    )
    assert panorama["status"] == "computed"  # sanity: the fixture must exercise the real path
    checkpoints = {
        "resolve": {"channel": {"id": "UC_target", "title": "Target"}},
        "metrics": {"panorama": panorama},
    }
    save_channel_analysis(db, run_id, profile_id, checkpoints, NOW)

    result = list_channel_analyses(db, limit=20, offset=0, now=NOW)
    item = result["items"][0]
    # Pin the actual compute_score() outcome for this fixture's real numbers (2 channels,
    # 1 video each -> hhi=0.5556, top5_share=1.0 -> concentration-only score of 22.2), not
    # just "a value in range" -- a regression that silently stopped calling compute_score
    # and always fell through to the None-score default would still satisfy a looser
    # assertion here, so this must pin the real, specific result.
    assert item["score"] == {
        "value": 22.2,
        "components": {
            "concentration": pytest.approx(22.22222222222222),
            "breakout": None,
            "demand": None,
            "rpm": None,
            "growth": None,
        },
        "components_used": ["concentration"],
    }


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
        "confirmed": {"youtube_quota": 2.0, "youtube_search_quota": 100.0},
        "reservations": [{"unit": "youtube_quota", "status": "unknown_charge", "amount": 1.0}],
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
    # _view() must never call compute_score(None) once the snapshot is withheld -- it
    # has to fall back to the default null-score shape instead of crashing or silently
    # scoring stale/partial data.
    assert expired["score"] == {"value": None, "components": {}, "components_used": []}
    # Small audit trail survives: what was asked and what it cost.
    assert expired["configuration"] == {"a": 1}
    assert expired["status"] == "completed"

    kept = channel_analysis_detail(db, fresh, now=later)
    assert kept is not None
    assert kept["snapshot"] == checkpoints
    assert kept["expired_at"] is None
    assert kept["evidence_available"] is True

    # Task 11: expired reports are now hidden from the default list entirely (not just
    # flagged unavailable, as channel_analysis_detail still does above) -- but remain
    # reachable with include_expired=True, still flagged unavailable there.
    listed = {row["id"]: row for row in list_channel_analyses(db, now=later)["items"]}
    assert due not in listed
    assert listed[fresh]["evidence_available"] is True

    listed_all = {
        row["id"]: row
        for row in list_channel_analyses(db, now=later, include_expired=True)["items"]
    }
    assert listed_all[due]["evidence_available"] is False
    assert listed_all[due]["snapshot"] is None
    assert listed_all[fresh]["evidence_available"] is True


@pytest.mark.postgres
def test_detail_hides_snapshot_past_retention_before_expire_runs(db: Connection) -> None:
    from datetime import timedelta

    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    analysis_id = save_channel_analysis(db, _run(db, profile_id), profile_id, {"resolve": {}}, NOW)
    detail = channel_analysis_detail(db, analysis_id, now=NOW + timedelta(days=181))
    assert detail is not None
    assert detail["snapshot"] is None
    assert detail["evidence_available"] is False


@pytest.mark.postgres
def test_expire_now_hides_snapshot_immediately(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    checkpoints = {"resolve": {"channel": {"id": "UC1", "title": "Science"}}}
    analysis_id = save_channel_analysis(
        db, _run(db, profile_id), profile_id, checkpoints, NOW, configuration={"a": 1}
    )

    # Immediate soft-delete, well before the 180-day retain_until -- must not depend on
    # retention.expire()'s due-date sweep at all.
    assert expire_now(db, analysis_id, NOW) is True

    row = channel_analysis_detail(db, analysis_id, now=NOW)
    assert row is not None
    assert row["snapshot"] is None
    assert row["evidence_available"] is False
    assert row["expired_at"] == NOW
    # Small audit trail survives, same as the bulk retention.expire() convention.
    assert row["configuration"] == {"a": 1}
    assert row["score"] == {"value": None, "components": {}, "components_used": []}

    # Idempotency guard: a second call against an already-expired row must not report
    # success again (mirrors the WHERE expired_at IS NULL guard in retention.expire()).
    assert expire_now(db, analysis_id, NOW) is False

    # A nonexistent id must also report False, not raise.
    assert expire_now(db, UUID("00000000-0000-0000-0000-000000000000"), NOW) is False


@pytest.mark.postgres
def test_list_excludes_expired_by_default(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    checkpoints = {"resolve": {"channel": {"id": "UC1", "title": "Science"}}}
    expired_id = save_channel_analysis(db, _run(db, profile_id), profile_id, checkpoints, NOW)
    kept_id = save_channel_analysis(
        db, _run(db, profile_id), profile_id, checkpoints, NOW + timedelta(seconds=1)
    )
    assert expire_now(db, expired_id, NOW) is True

    result = list_channel_analyses(db, limit=20, offset=0, now=NOW)
    ids = {item["id"] for item in result["items"]}
    assert expired_id not in ids
    assert kept_id in ids
    # total must reflect the same default filtering as the returned rows, not just the
    # page -- a regression that filtered `rows` but not `total` would still pass a
    # looser assertion here.
    assert result["total"] == 1

    result_all = list_channel_analyses(db, limit=20, offset=0, now=NOW, include_expired=True)
    ids_all = {item["id"] for item in result_all["items"]}
    assert expired_id in ids_all
    assert kept_id in ids_all
    assert result_all["total"] == 2
