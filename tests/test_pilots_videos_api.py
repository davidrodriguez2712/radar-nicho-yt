# tests/test_pilots_videos_api.py
"""GET /pilots/{id}/videos y los campos aditivos de GET /pilots (corte 2a)."""

from datetime import datetime
from urllib.parse import quote

import pytest
from sqlalchemy import Engine

from tests.pilot_samples import iso
from tests.shorts_report_samples import shorts_report, shorts_video
from tests.test_channel_report_v2_api import shorts_pilot
from tests.test_market_api import AUTH
from tests.test_persistence import NOW
from tests.test_pilots_api import (
    BASE,
    bearer,
    deliver,
    issue_token,
    launched,
    report,
    send,
    video,
)

pytestmark = pytest.mark.postgres

ITEM_KEYS = {
    "video_id",
    "source_state",
    "stage",
    "visibility",
    "published_at",
    "cost_usd",
    "cost_equivalent_usd",
    "machine_minutes",
    "human_minutes",
    "human_minutes_method",
    "failure_code",
    "measurement",
}


def at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_videos_lists_the_reported_videos_in_publication_order(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    early = video(1)  # v_01
    tie = video(4, published_at=early["published_at"])  # mismo instante: desempata video_id
    later = video(3)  # v_03, publicado después
    unpublished_b = video(
        5,
        avd=None,
        published_at=None,
        source_state="FALLO_QA",
        visibility="private",
        failure_code="tts_error",
    )
    unpublished_a = video(
        2, avd=None, published_at=None, source_state="GUION_FINAL", visibility="private"
    )
    shuffled = [unpublished_b, later, tie, unpublished_a, early]
    assert send(api, token, pilot_id, report(pilot_id, shuffled)).status_code == 200

    response = api.get(f"{BASE}/{pilot_id}/videos", headers=bearer(token))

    assert response.status_code == 200
    items = response.json()["items"]
    assert list(response.json()) == ["items"]
    assert [i["video_id"] for i in items] == ["v_01", "v_04", "v_03", "v_02", "v_05"]
    assert all(set(i) == ITEM_KEYS for i in items)
    first, _, third, fourth, fifth = items
    assert first["source_state"] == "EN_MEDICION" and first["stage"] == "measuring"
    assert first["visibility"] == "public"
    assert at(first["published_at"]) == at(early["published_at"])
    assert first["cost_usd"] == 0.3 and first["cost_equivalent_usd"] == 1.5
    assert first["machine_minutes"] == 60 and first["failure_code"] is None
    # Sin NaN ni Decimal: los números salen como números JSON.
    assert type(first["cost_usd"]) is float and type(first["machine_minutes"]) is int
    # La medición larga trae solo los campos con valor (browse_share_pct es null y se omite).
    assert set(first["measurement"]) == {
        "measured_at",
        "window_days",
        "views",
        "avd_pct",
        "subscribers_gained",
    }
    assert at(first["measurement"]["measured_at"]) == at(early["measurement"]["measured_at"])
    assert first["measurement"]["window_days"] == 7 and first["measurement"]["views"] == 100
    assert first["measurement"]["avd_pct"] == 25 and first["measurement"]["subscribers_gained"] == 0
    assert third["video_id"] == "v_03" and third["measurement"] is not None
    assert fourth["published_at"] is None and fourth["measurement"] is None
    assert fourth["stage"] == "in_production" and fourth["failure_code"] is None
    assert fifth["published_at"] is None and fifth["measurement"] is None
    assert fifth["stage"] == "blocked" and fifth["failure_code"] == "tts_error"
    # El humano (token de servicio) ve exactamente lo mismo.
    assert api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json() == response.json()


def test_videos_of_a_pilot_without_reports_is_an_empty_list(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    assert api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json() == {"items": []}
    deliver(api, pilot_id, token)
    assert api.get(f"{BASE}/{pilot_id}/videos", headers=bearer(token)).json() == {"items": []}


def test_videos_follow_the_same_visibility_rules_as_the_detail(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, report(pilot_id, [video(1)]))
    stranger = bearer(issue_token(api, "canal-otro"))

    hidden = api.get(f"{BASE}/{pilot_id}/videos", headers=stranger)
    assert hidden.status_code == 404
    assert hidden.json() == api.get(f"{BASE}/{pilot_id}", headers=stranger).json()
    assert hidden.json()["detail"]["code"] == "not_found"
    assert "v_01" not in hidden.text

    own = api.get(f"{BASE}/{pilot_id}/videos", headers=bearer(token))
    assert own.status_code == 200 and [i["video_id"] for i in own.json()["items"]] == ["v_01"]

    assert api.get(f"{BASE}/{pilot_id}/videos").status_code == 401
    assert api.get(f"{BASE}/{pilot_id}/videos", headers=bearer("wrong")).status_code == 401

    missing = api.get(f"{BASE}/pil_20260913_no-existe/videos", headers=AUTH)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"
    for weird in ("x y", "x" * 200, "pil_1\nx", "'; drop table pilots; --", "%00"):
        path = f"{BASE}/{quote(weird, safe='')}/videos"
        for headers in (AUTH, stranger):
            got = api.get(path, headers=headers)
            assert got.status_code == 404, (weird, got.status_code)
            assert got.json() == missing.json(), weird


def test_the_videos_route_is_not_shadowed_by_pending_or_the_detail(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    # `pending` es una ruta propia: aquí es un pilot_id que no existe, no la lista de pendientes.
    pending = api.get(f"{BASE}/pending/videos", headers=AUTH)
    assert pending.status_code == 404 and pending.json()["detail"]["code"] == "not_found"
    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    listed = api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json()
    assert "pilot_id" not in listed and listed == {"items": []}
    assert detail["pilot_id"] == pilot_id


def test_a_shorts_video_includes_its_measurement_fields(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    measured = shorts_video(1)
    body = shorts_report([measured, shorts_video(2, measured=False)], pilot_id)
    assert send(api, token, pilot_id, body).status_code == 200

    items = api.get(f"{BASE}/{pilot_id}/videos", headers=bearer(token)).json()["items"]

    assert [i["video_id"] for i in items] == ["s_01", "s_02"]
    assert all(set(i) == ITEM_KEYS for i in items)
    measurement = items[0]["measurement"]
    # avd/browse no existen en Shorts y los None del contrato no se emiten.
    assert set(measurement) == {
        "measured_at",
        "window_days",
        "views",
        "subscribers_gained",
        "engaged_views",
        "engaged_view_ratio_pct",
        "avg_view_pct",
        "shorts_feed_share_pct",
        "shares",
    }
    assert at(measurement["measured_at"]) == at(measured["measurement"]["measured_at"])
    assert {k: v for k, v in measurement.items() if k != "measured_at"} == {
        "window_days": 7,
        "views": 2400,
        "subscribers_gained": 6,
        "engaged_views": 1560,
        "engaged_view_ratio_pct": 65,
        "avg_view_pct": 71.5,
        "shorts_feed_share_pct": 88,
        "shares": 14,
    }
    assert items[0]["cost_usd"] == 0.1 and items[0]["stage"] == "measuring"
    assert items[1]["measurement"] is None


def test_a_shorts_measurement_with_the_optional_fields_present(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    fuller = shorts_video(1)
    fuller["measurement"].update(
        stayed_to_watch_pct=80.5, early_retention_pct=62.25, early_retention_second=3
    )
    assert send(api, token, pilot_id, shorts_report([fuller], pilot_id)).status_code == 200
    measurement = api.get(f"{BASE}/{pilot_id}/videos", headers=AUTH).json()["items"][0][
        "measurement"
    ]
    assert measurement["stayed_to_watch_pct"] == 80.5
    assert measurement["early_retention_pct"] == 62.25
    assert measurement["early_retention_second"] == 3


def test_the_pilot_list_exposes_valid_until_delivered_at_and_channel(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    old_keys = {
        "pilot_id",
        "status",
        "niche_label",
        "format",
        "target_channel",
        "authorized_at",
        "last_report_at",
        "channel_last_contact_at",
        "totals",
        "proposal",
        "needs_decision",
    }
    new_keys = {"valid_until", "delivered_at", "channel"}

    before = api.get(BASE, headers=AUTH).json()["items"]
    assert len(before) == 1 and set(before[0]) == old_keys | new_keys
    undelivered = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    assert before[0]["delivered_at"] is None and before[0]["channel"] is None
    assert before[0]["valid_until"] == undelivered["valid_until"] is not None

    deliver(api, pilot_id, token)
    check = {"id": "voice_ref", "label": "Voz", "ok": False, "detail": "falta", "expires_at": None}
    sent = send(api, token, pilot_id, report(pilot_id, [video(1)], checks=[check]))
    assert sent.status_code == 200

    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    after = api.get(BASE, headers=AUTH).json()["items"][0]
    assert set(after) == old_keys | new_keys
    assert after["valid_until"] == detail["valid_until"]
    assert after["delivered_at"] == detail["delivered_at"] is not None
    assert after["channel"] == detail["channel"]
    assert after["channel"]["checks"][0]["id"] == "voice_ref"
    assert after["channel"]["channel_status"] == "active"
    assert at(after["channel"]["reported_at"]) == at(iso(NOW))
