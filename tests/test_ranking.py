from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, func, select, update

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.retention import expire
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import metadata, ranking_entries, ranking_snapshots
from nicheradar.services.backlog import append_evaluation, decide, opportunity_identity
from nicheradar.services.comparison import compare_evaluations
from nicheradar.services.console import opportunity_detail
from nicheradar.services.ranking import capture, history
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW, seed_evidence


def snapshot() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "method_version": "opportunity-v2",
        "reference_version": "fixture-v1",
        "source_mode": "synthetic",
        "market_score": 60.0,
        "creator_fit": 75.0,
        "final_score": 65.25,
        "state": "provisional",
        "confidence": "provisional",
        "explanation": {
            "metrics": {"method_version": "metrics-v2", "videos": 10, "views": 100},
            "market": {
                "method_version": "market-v2",
                "components": {"D": 60, "B": 70, "C": 50, "M": None},
            },
            "production": {
                "rubric_version": "creator-fit-v2",
                "profile": {"weekly_hours": "15"},
                "plan": {"videos": 4},
            },
            "combined": {
                "method_version": "opportunity-v2",
                "weights": {"market": 0.65, "creator_fit": 0.35},
            },
        },
    }


def evaluation(
    db: Connection,
    ids: dict[str, UUID],
    *,
    run: UUID | None = None,
    opportunity: UUID | None = None,
    score: float | None = 65.25,
    method: str = "opportunity-v2",
    views: int = 100,
) -> UUID:
    values = snapshot()
    values.pop("id")
    values.pop("source_mode")
    values["explanation"]["metrics"]["views"] = views
    return append_evaluation(
        db,
        opportunity or ids["opportunity"],
        values
        | {
            "run_id": run or ids["run"],
            "cohort_id": ids["cohort"],
            "final_score": score,
            "method_version": method,
            "created_at": NOW,
            "retain_until": NOW + timedelta(days=10),
        },
    )


def new_run(db: Connection, ids: dict[str, UUID], *, mode: str = "synthetic") -> UUID:
    return insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": ids["profile"],
            "mode": mode,
            "trigger": "manual",
            "status": "running",
            "configuration": {},
        },
    )


def candidate(
    db: Connection,
    ids: dict[str, UUID],
    name: str,
    *,
    format: VideoFormat = VideoFormat.LONG,
    language: str = "en",
) -> UUID:
    return opportunity_identity(db, ids["topic"], name, language, format)


def test_comparison_tracks_data_and_method_simultaneously() -> None:
    before = snapshot()
    after = deepcopy(before)
    after["method_version"] = "opportunity-v3"
    after["explanation"]["metrics"]["views"] = 130
    after["final_score"] = 70
    result = compare_evaluations(before, after)
    assert result["changes"] == ["method_changed", "data_changed"]
    assert not result["comparable"]
    assert all(delta["delta"] is None for delta in result["deltas"])
    after["method_version"] = before["method_version"]
    result = compare_evaluations(before, after)
    assert result["changes"] == ["data_changed"]
    assert (
        next(item for item in result["deltas"] if item["field"] == "metrics.views")["delta"] == 30
    )


def test_comparison_separates_assumptions_coverage_and_generated_text() -> None:
    before = snapshot()
    after = deepcopy(before)
    after["explanation"]["narrative"] = {"llm": "A new emphasis, not new evidence"}
    assert compare_evaluations(before, after)["changes"] == ["unchanged"]
    after["explanation"]["production"]["plan"]["videos"] = 6
    assert compare_evaluations(before, after)["changes"] == ["assumptions_changed"]
    after["explanation"]["market"]["components"]["M"] = 0
    result = compare_evaluations(before, after)
    assert "component_coverage_changed" in result["changes"]
    assert not result["comparable"]


@pytest.mark.parametrize("field", ["expired_at", "evidence_available"])
def test_comparison_never_returns_expired_values(field: str) -> None:
    before = snapshot()
    before[field] = NOW if field == "expired_at" else False
    result = compare_evaluations(before, snapshot())
    assert result["changes"] == ["evidence_unavailable"]
    assert result["deltas"] == []


@pytest.mark.postgres
def test_rank_snapshot_idempotency_groups_ties_and_missing(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids, score=70)
    peers = {}
    for name, score, format, language, method in [
        ("tie", 70, VideoFormat.LONG, "en", "opportunity-v2"),
        ("lower", 60, VideoFormat.LONG, "en", "opportunity-v2"),
        ("short", 90, VideoFormat.SHORTS, "en", "opportunity-v2"),
        ("spanish", 90, VideoFormat.LONG, "es", "opportunity-v2"),
        ("method", 90, VideoFormat.LONG, "en", "opportunity-v3"),
        ("missing", None, VideoFormat.LONG, "en", "opportunity-v2"),
        ("zero", 0, VideoFormat.LONG, "en", "opportunity-v2"),
    ]:
        peer = candidate(db, ids, name, format=format, language=language)
        evaluation(db, ids, opportunity=peer, score=score, method=method)
        peers[name] = peer
    first = capture(db, ids["run"], NOW)
    assert capture(db, ids["run"], NOW + timedelta(hours=1)) == first
    rows = {row["opportunity_id"]: row for row in db.execute(select(ranking_entries)).mappings()}
    assert rows[ids["opportunity"]]["position"] == rows[peers["tie"]]["position"] == 1
    assert rows[peers["lower"]]["position"] == 3
    assert rows[peers["zero"]]["position"] == 4
    for name in ("short", "spanish", "method"):
        assert rows[peers[name]]["position"] == 1
        assert rows[peers[name]]["group_key"] != rows[ids["opportunity"]]["group_key"]
    assert rows[peers["missing"]]["position"] is None
    assert db.execute(select(func.count()).select_from(ranking_snapshots)).scalar_one() == 1


@pytest.mark.postgres
def test_other_candidates_displace_unchanged_evaluation(db: Connection) -> None:
    ids = seed_evidence(db)
    original = evaluation(db, ids)
    capture(db, ids["run"], NOW)
    run = new_run(db, ids)
    peer = candidate(db, ids, "new-contender")
    evaluation(db, ids, run=run, opportunity=peer, score=90)
    capture(db, run, NOW + timedelta(hours=1))
    ranks = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)
    assert [row["position"] for row in ranks] == [2, 1]
    assert ranks[0]["evaluation_id"] == original
    assert ranks[0]["change"]["kind"] == "other_candidates_changed"
    assert ranks[0]["change"]["position_delta"] == 1
    # A new identical evaluation is also an unchanged candidate, not a score decline.
    run = new_run(db, ids)
    evaluation(db, ids, run=run)
    decide(db, peer, "dismissed", "not suitable", 0, NOW)
    capture(db, run, NOW)
    ranks = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)
    assert ranks[0]["position"] == 1
    assert ranks[0]["change"]["kind"] == "other_candidates_changed"
    assert ranks[1]["position"] == 2  # No historical rewrite by the decision.


@pytest.mark.postgres
def test_own_data_change_is_not_attributed_only_to_peers(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids, score=70)
    peer = candidate(db, ids, "peer")
    evaluation(db, ids, opportunity=peer, score=60)
    capture(db, ids["run"], NOW)
    run = new_run(db, ids)
    evaluation(db, ids, run=run, score=50, views=90)
    capture(db, run, NOW)
    latest = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)[0]
    assert latest["change"]["kind"] == "relative_rank_and_own_evaluation_changed"
    assert "data_changed" in latest["change"]["own_evaluation_changes"]
    run = new_run(db, ids)
    evaluation(db, ids, run=run, score=95, method="opportunity-v3")
    capture(db, run, NOW)
    latest = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)[0]
    assert latest["change"] == {"kind": "comparison_scope_changed", "position_delta": None}


@pytest.mark.postgres
def test_unscored_or_expired_latest_never_reuses_old_score(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids, score=99)
    capture(db, ids["run"], NOW)
    run = new_run(db, ids)
    latest = evaluation(db, ids, run=run, score=None)
    capture(db, run, NOW)
    ranks = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)
    assert ranks[0]["position"] is None
    assert ranks[0]["reason"] == "unscored"
    db.execute(
        update(s.evaluation_versions)
        .where(s.evaluation_versions.c.id == latest)
        .values(expired_at=NOW)
    )
    run = new_run(db, ids)
    capture(db, run, NOW)
    assert (
        history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)[0]["reason"]
        == "not_present"
    )


@pytest.mark.postgres
def test_modes_and_in_progress_evaluations_do_not_contaminate_rank(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids, score=70)
    capture(db, ids["run"], NOW)
    unfinished = new_run(db, ids)
    evaluation(db, ids, run=unfinished, score=None)
    live = new_run(db, ids, mode="live")
    evaluation(db, ids, run=live, score=10)
    capture(db, live, NOW)
    run = new_run(db, ids)
    capture(db, run, NOW)
    ranks = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)
    assert len(ranks) == 2
    assert ranks[0]["evaluation_id"] == ranks[1]["evaluation_id"]
    assert ranks[0]["position"] == 1


@pytest.mark.postgres
def test_peer_expiration_invalidates_and_deletes_entire_snapshot(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids)
    peer = candidate(db, ids, "short-retention-peer")
    peer_evaluation = evaluation(db, ids, opportunity=peer, score=90)
    capture(db, ids["run"], NOW)
    # A shortened policy may invalidate a source before the saved snapshot deadline.
    db.execute(
        update(s.evaluation_versions)
        .where(s.evaluation_versions.c.id == peer_evaluation)
        .values(retain_until=NOW)
    )
    ranks = history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)
    assert ranks[0]["reason"] == "evidence_unavailable"
    assert ranks[0]["position"] is None
    expire(db, NOW)
    assert db.execute(select(func.count()).select_from(ranking_entries)).scalar_one() == 0
    assert db.execute(select(ranking_snapshots.c.expired_at)).scalar_one() == NOW
    detail = opportunity_detail(db, ids["opportunity"], NOW)
    assert detail is not None
    assert detail["evaluations"][0]["evidence_available"]


@pytest.mark.postgres
def test_comparison_api_auth_validation_and_history(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        evaluation(db, ids)
        capture(db, ids["run"], NOW)
        run = new_run(db, ids)
        evaluation(db, ids, run=run, score=70, views=200)
        capture(db, run, NOW)
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    path = f"/api/v1/opportunities/{ids['opportunity']}/comparison"
    params = {"previous_version": 1, "current_version": 2}
    assert client.get(path, params=params).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.get(path, params=params)
    assert response.status_code == 200
    assert response.json()["changes"] == ["data_changed"]
    assert client.get(path, params={"previous_version": 2, "current_version": 1}).status_code == 422
    assert (
        client.get(path, params={"previous_version": 1, "current_version": 99}).status_code == 404
    )
    assert client.get(path, params={"previous_version": 0, "current_version": 2}).status_code == 422
    detail = client.get(f"/api/v1/opportunities/{ids['opportunity']}").json()
    assert detail["comparison"]["changes"] == ["data_changed"]
    assert len(detail["ranking_history"]) == 2


@pytest.mark.postgres
def test_ranking_migration_matches_metadata(db: Connection) -> None:
    context = MigrationContext.configure(db)
    assert compare_metadata(context, metadata) == []


@pytest.mark.postgres
def test_concurrent_snapshot_retry_is_idempotent(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        evaluation(db, ids)

    def record() -> UUID:
        with isolated_engine.begin() as db:
            return capture(db, ids["run"], NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: record(), range(2)))
    assert results[0] == results[1]
    with isolated_engine.connect() as db:
        assert db.execute(select(func.count()).select_from(ranking_snapshots)).scalar_one() == 1


@pytest.mark.postgres
def test_ranking_isolates_profiles_and_component_coverage(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids)
    peer = candidate(db, ids, "advertising-covered")
    other_evaluation = evaluation(db, ids, opportunity=peer, score=90)
    details = snapshot()["explanation"]
    details["market"]["components"]["M"] = 80
    db.execute(
        update(s.evaluation_versions)
        .where(s.evaluation_versions.c.id == other_evaluation)
        .values(explanation=details)
    )
    capture(db, ids["run"], NOW)
    assert history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)[0]["position"] == 1
    other_profile = insert_record(
        db, "creator_profiles", {"profile_key": "separate", "configuration": {}}
    )
    other_run = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": other_profile,
            "mode": "synthetic",
            "trigger": "manual",
            "status": "running",
            "configuration": {},
        },
    )
    other = evaluation(db, ids, run=other_run, score=10)
    capture(db, other_run, NOW)
    assert (
        history(db, ids["opportunity"], other_profile, "synthetic", NOW)[0]["evaluation_id"]
        == other
    )
    assert len(history(db, ids["opportunity"], ids["profile"], "synthetic", NOW)) == 1
