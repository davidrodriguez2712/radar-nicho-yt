import pytest
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.channel_analysis import (
    channel_analysis_detail,
    list_channel_analyses,
    save_channel_analysis,
)
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
