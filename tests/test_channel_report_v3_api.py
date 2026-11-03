# tests/test_channel_report_v3_api.py
"""channel-report-v3 de punta a punta: minutos humanos por video, totales y API."""

from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nicheradar.repositories.schema import pilot_videos
from tests.pilot_samples import iso
from tests.shorts_report_samples import (
    shorts_report,
    shorts_report_v3,
    shorts_video,
    shorts_video_v3,
)
from tests.test_channel_report_v2_api import shorts_pilot
from tests.test_market_api import AUTH
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE, bearer, deliver, issue_token, launched, send
from tests.test_pilots_api import report as long_report
from tests.test_pilots_api import video as long_video

pytestmark = pytest.mark.postgres


def long_v3(pilot_id: str, videos: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    body = long_report(pilot_id, videos, contract="channel-report-v3", format="long")
    body["human_minutes_method"] = "gate_waits"
    body.update(over)
    return body


def v3_video(n: int, human: int | None = 25, **over: Any) -> dict[str, Any]:
    return long_video(n, human_minutes=human, **over)


def rows(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        found = connection.execute(sa.select(pilot_videos)).mappings()
        return {r["video_id"]: r for r in found}


def totals_of(api: TestClient, pilot_id: str) -> dict[str, Any]:
    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    totals: dict[str, Any] = detail["evaluation"]["totals"]
    return totals


def test_a_v3_long_report_is_stored_listed_and_totalled(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    body = long_v3(pilot_id, [v3_video(1, 25), v3_video(2, 35)])
    ok = send(api, token, pilot_id, body)
    assert ok.status_code == 200, ok.text
    assert ok.json()["videos_upserted"] == 2
    stored = rows(isolated_engine)
    assert stored["v_01"]["human_minutes"] == 25
    assert stored["v_02"]["human_minutes_method"] == "gate_waits"
    items = api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json()["items"]
    assert [(i["human_minutes"], i["human_minutes_method"]) for i in items] == [
        (25, "gate_waits"),
        (35, "gate_waits"),
    ]
    totals = totals_of(api, pilot_id)
    assert totals["human_minutes"] == 60 and totals["human_minutes_complete"] is True


def test_a_v3_shorts_report_is_stored_and_listed(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    body = shorts_report_v3([shorts_video_v3(1, human_minutes=7)], pilot_id)
    ok = send(api, token, pilot_id, body)
    assert ok.status_code == 200, ok.text
    assert rows(isolated_engine)["s_01"]["human_minutes"] == 7
    items = api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json()["items"]
    assert items[0]["human_minutes"] == 7 and items[0]["human_minutes_method"] == "gate_waits"
    assert totals_of(api, pilot_id)["human_minutes"] == 7


def test_an_unmeasured_video_makes_the_total_incomplete_and_is_not_summed_as_zero(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25), v3_video(2, None)]))
    assert rows(isolated_engine)["v_02"]["human_minutes"] is None
    totals = totals_of(api, pilot_id)
    assert totals["human_minutes"] == 25 and totals["human_minutes_complete"] is False
    items = api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json()["items"]
    assert items[1]["human_minutes"] is None


def test_with_no_videos_the_human_minutes_pattern_matches_machine_minutes(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, _ = launched(isolated_engine)
    totals = totals_of(api, pilot_id)
    assert totals["human_minutes"] == 0 and totals["machine_minutes"] == 0
    assert totals["human_minutes_complete"] is totals["machine_minutes_complete"] is True


def test_a_v3_report_with_the_wrong_format_is_refused(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)  # piloto largo
    deliver(api, pilot_id, token)
    body = shorts_report_v3([shorts_video_v3(1)], pilot_id)
    refused = send(api, token, pilot_id, body)
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert refused.json()["problems"][0]["path"] == "contract"
    assert "formato del piloto" in refused.json()["problems"][0]["message"]
    assert rows(isolated_engine) == {}


def test_an_invalid_v3_report_is_refused_and_nothing_is_stored(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    body = long_v3(pilot_id, [v3_video(1, 25), v3_video(2, -3)])
    refused = send(api, token, pilot_id, body)
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert refused.json()["problems"]
    assert rows(isolated_engine) == {}


def test_the_newest_report_wins_for_human_minutes_and_a_tie_keeps_the_stored(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25)]))
    older = long_v3(pilot_id, [v3_video(1, 99)], reported_at=iso(NOW - timedelta(minutes=5)))
    assert send(api, token, pilot_id, older).json()["videos_ignored"] == 1
    tie = long_v3(pilot_id, [v3_video(1, 88)], human_minutes_method="other_method")
    assert send(api, token, pilot_id, tie).json()["videos_ignored"] == 1
    assert rows(isolated_engine)["v_01"]["human_minutes"] == 25
    newer = long_v3(
        pilot_id,
        [v3_video(1, 40)],
        reported_at=iso(NOW + timedelta(minutes=1)),
        human_minutes_method="stopwatch",
    )
    assert send(api, token, pilot_id, newer).json()["videos_upserted"] == 1
    stored = rows(isolated_engine)["v_01"]
    assert stored["human_minutes"] == 40 and stored["human_minutes_method"] == "stopwatch"


def test_a_later_v1_report_does_not_erase_stored_human_minutes(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25)]))
    later = long_report(
        pilot_id,
        [long_video(1, machine_minutes=99)],
        reported_at=iso(NOW + timedelta(minutes=1)),
    )
    assert send(api, token, pilot_id, later).json()["videos_upserted"] == 1
    stored = rows(isolated_engine)["v_01"]
    assert stored["machine_minutes"] == 99  # el v1 sí actualizó lo suyo
    assert stored["human_minutes"] == 25 and stored["human_minutes_method"] == "gate_waits"


def test_a_v2_report_leaves_human_minutes_null(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    ok = send(api, token, pilot_id, shorts_report([shorts_video(1)], pilot_id))
    assert ok.status_code == 200, ok.text
    stored = rows(isolated_engine)["s_01"]
    assert stored["human_minutes"] is None and stored["human_minutes_method"] is None


def test_a_v1_report_leaves_human_minutes_null(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    assert send(api, token, pilot_id, long_report(pilot_id, [long_video(1)])).status_code == 200
    stored = rows(isolated_engine)["v_01"]
    assert stored["human_minutes"] is None and stored["human_minutes_method"] is None
    totals = totals_of(api, pilot_id)
    assert totals["human_minutes"] == 0 and totals["human_minutes_complete"] is False


def test_the_closing_summary_shows_human_minutes_and_flags_incomplete(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25), v3_video(2, None)]))
    closed = api.post(
        f"{BASE}/{pilot_id}/decision", json={"decision": "cerrar", "note": "fin"}, headers=AUTH
    )
    assert closed.json()["status"] == "cerrado"
    text = api.get(f"{BASE}/{pilot_id}/closing-summary", headers=AUTH).text
    assert "- Minutos humanos: 25 (incompleto: faltan videos sin dato)." in text


def test_the_closing_summary_has_no_incomplete_flag_when_all_are_measured(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25), v3_video(2, 5)]))
    api.post(
        f"{BASE}/{pilot_id}/decision", json={"decision": "cerrar", "note": "fin"}, headers=AUTH
    )
    text = api.get(f"{BASE}/{pilot_id}/closing-summary", headers=AUTH).text
    assert "- Minutos humanos: 30." in text


def test_a_foreign_channel_gets_404_and_the_list_only_carries_totals(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, long_v3(pilot_id, [v3_video(1, 25)]))
    other = issue_token(api, "canal-otro")
    foreign = api.get(f"{BASE}/{pilot_id}/videos", headers=bearer(other))
    assert foreign.status_code == 404
    assert api.get(f"{BASE}/{pilot_id}", headers=bearer(other)).status_code == 404
    items = api.get(BASE, headers=AUTH).json()["items"]
    assert "human_minutes" not in {key for item in items for key in item}
    assert items[0]["totals"]["human_minutes"] == 25
