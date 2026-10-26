# tests/test_channel_report_v2_api.py
"""channel-report-v2 de punta a punta: el mismo POST, el `contract` decide el validador."""

from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nicheradar.repositories.schema import pilot_shorts_measurements as shorts
from nicheradar.repositories.schema import pilots
from tests.pilot_samples import iso
from tests.shorts_report_samples import shorts_measurement, shorts_report, shorts_video
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE, deliver, launched, send
from tests.test_pilots_api import report as long_report
from tests.test_pilots_api import video as long_video

pytestmark = pytest.mark.postgres

SHORTS_RULE = {
    "id": "enganche-v10",
    "text": "Vistas atractivas >= 50% en al menos 3 de los primeros 10 Shorts",
    "metric": "engaged_view_ratio_pct",
    "comparator": ">=",
    "threshold": 50,
    "min_cases": 3,
    "milestone": {"kind": "video", "value": 10},
}


def shorts_pilot(engine: Engine) -> tuple[TestClient, str, str]:
    """Un piloto entregado cuyo formato (y reglas) es Shorts, listo para recibir v2."""
    api, pilot_id, token = launched(engine)
    deliver(api, pilot_id, token)
    with engine.begin() as connection:
        package = connection.execute(
            sa.select(pilots.c.package).where(pilots.c.pilot_id == pilot_id)
        ).scalar_one()
        package["niche"]["format"] = "shorts"
        package["stop_rules"] = [SHORTS_RULE]
        connection.execute(
            sa.update(pilots)
            .where(pilots.c.pilot_id == pilot_id)
            .values(format="shorts", package=package)
        )
    return api, pilot_id, token


def stored(engine: Engine) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(sa.select(shorts)).mappings())


def test_a_v2_report_is_accepted_stored_and_counted(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    body = shorts_report([shorts_video(1), shorts_video(2, measured=False)], pilot_id)
    ok = send(api, token, pilot_id, body)
    assert ok.status_code == 200, ok.text
    assert ok.json()["accepted"] is True and ok.json()["videos_upserted"] == 2
    assert ok.json()["pilot_status"] == "en_ejecucion"
    rows = stored(isolated_engine)
    assert len(rows) == 1 and rows[0]["engaged_views"] == 1560
    assert float(rows[0]["engaged_view_ratio_pct"]) == 65.0
    totals = api.get(f"{BASE}/{pilot_id}", headers=_auth(token)).json()["evaluation"]["totals"]
    assert totals["videos"] == 2 and totals["measured"] == 1


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_v2_report_to_a_long_pilot_is_refused_without_echoing_values(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    refused = send(api, token, pilot_id, shorts_report([shorts_video(1)], pilot_id))
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert refused.json()["problems"][0]["path"] == "contract"
    assert stored(isolated_engine) == []


def test_a_v1_report_to_a_shorts_pilot_is_refused(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    refused = send(api, token, pilot_id, long_report(pilot_id, [long_video(1)]))
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert refused.json()["problems"][0]["path"] == "contract"


def test_the_newest_v2_report_wins_and_a_missing_measurement_clears_the_old_one(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    send(api, token, pilot_id, shorts_report([shorts_video(1)], pilot_id))
    same_time = shorts_video(1, measurement=shorts_measurement(shares=999))
    again = send(api, token, pilot_id, shorts_report([same_time], pilot_id))
    assert again.json()["videos_ignored"] == 1  # empate: se conserva lo guardado
    assert stored(isolated_engine)[0]["shares"] == 14
    later = iso(NOW + timedelta(minutes=1))
    newer = shorts_video(1, measurement=shorts_measurement(shares=20))
    send(api, token, pilot_id, shorts_report([newer], pilot_id, reported_at=later))
    assert stored(isolated_engine)[0]["shares"] == 20
    unmeasured = shorts_video(1, measured=False)
    latest = iso(NOW + timedelta(minutes=2))
    send(api, token, pilot_id, shorts_report([unmeasured], pilot_id, reported_at=latest))
    assert stored(isolated_engine) == []


def test_enough_engaging_shorts_meet_the_rule_and_ask_the_human(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    body = shorts_report([shorts_video(n) for n in range(1, 11)], pilot_id)
    response = send(api, token, pilot_id, body)
    assert response.json()["pilot_status"] == "decision_pendiente"
    detail = api.get(f"{BASE}/{pilot_id}", headers=_auth(token)).json()
    assert detail["evaluation"]["rules"][0]["status"] == "cumple"
    assert detail["proposal"]["action"] == "seguir"


def test_shorts_with_too_few_views_do_not_count(isolated_engine: Engine) -> None:
    api, pilot_id, token = shorts_pilot(isolated_engine)
    thin = shorts_measurement(views=50, engaged_views=40, engaged_view_ratio_pct=80)
    videos = [shorts_video(n, measurement=thin) for n in range(1, 11)]
    response = send(api, token, pilot_id, shorts_report(videos, pilot_id))
    assert response.status_code == 200
    detail = api.get(f"{BASE}/{pilot_id}", headers=_auth(token)).json()
    assert detail["evaluation"]["rules"][0]["status"] == "sin_datos_suficientes"
    assert len(stored(isolated_engine)) == 10  # se guardan igual
