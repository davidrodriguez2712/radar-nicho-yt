# tests/test_pilots_subniche.py
"""Piloto autorizado desde un dossier de subnicho."""

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed
from tests.flow_research_samples import valid_dossier
from tests.subniche_samples import NOW as MEASURED
from tests.subniche_samples import channel, draft, make_run, video
from tests.test_flow_research_api import BASE as FLOW
from tests.test_market_api import AUTH, client
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE as PILOTS
from tests.test_pilots_api import authorize_body
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
LABEL = "subniche:history_revenge"


def seed(engine: Engine, hits: int = 10) -> None:
    with engine.begin() as connection:
        run_id, _, _ = make_run(connection)
        rows = [hit("abcdefghij"[i], traction=i == 0, low="100", high="900") for i in range(hits)]
        hypothesis_id = create_proposed(
            connection, draft(slug="history_revenge", queries=("history revenge",)), MEASURED
        )
        approve(connection, "history_revenge", MEASURED)
        save_measurement(
            connection,
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            now=MEASURED,
            channels=[(channel("a"), [video(1)])],
            hits=rows,
            profile=build_profile(rows, rpm_source="inherited:x"),
        )


def ready_subniche(api: TestClient) -> str:
    body = {"niche_label": LABEL, "format": "long", "language": "en"}
    created = api.post(FLOW, json=body, headers=AUTH)
    assert created.status_code == 201, created.text
    request_id = str(created.json()["id"])
    owner = api.post(f"{FLOW}/{request_id}/claim", json={"owner": "w"}, headers=AUTH).json()[
        "lease_owner"
    ]
    dossier: dict[str, Any] = valid_dossier(UUID(request_id), NOW)
    dossier["niche_label"] = LABEL
    done = api.post(
        f"{FLOW}/{request_id}/dossier", json={"owner": owner, "dossier": dossier}, headers=AUTH
    )
    assert done.status_code == 200, done.text
    return request_id


def test_a_pilot_is_authorized_from_a_subniche_with_the_v1_package_shape(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    created = api.post(PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH)
    assert created.status_code == 201, created.text
    package = created.json()["package"]
    assert created.json()["pilot_id"].startswith("pil_")
    assert created.json()["pilot_id"].endswith("_history-revenge")
    assert package["niche"]["label"] == LABEL
    evidence = package["evidence"]
    assert evidence["scores"] == {
        "opportunity": None,
        "automation": None,
        "creator_fit": None,
        "market": None,
    }
    assert evidence["listings_with_income"] == 0 and evidence["confidence"] == "medium"
    assert evidence["language_mix"] == [{"language": "en", "share_pct": 100}]
    figures = {item["name"]: item for item in evidence["figures"]}
    assert figures["income_estimate_high"]["value"] == 900
    assert figures["income_estimate_high"]["origin"] == "estimate"
    assert figures["traction_channels"]["value"] == 1


def test_low_confidence_subniche_evidence_maps_to_low(isolated_engine: Engine) -> None:
    seed(isolated_engine, hits=3)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    created = api.post(PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH)
    assert created.status_code == 201, created.text
    assert created.json()["package"]["evidence"]["confidence"] == "low"


def test_authorization_repeats_the_minutes_gate_for_a_subniche_dossier(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    request_id = ready_subniche(client(isolated_engine))
    strict = client(isolated_engine, gate_max_human_minutes=40)
    refused = strict.post(PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_failed"
    assert [reason["gate"] for reason in detail["reasons"]] == ["human_minutes"]
    accepted = strict.post(
        PILOTS,
        json=authorize_body(
            request_id, niche_label=LABEL, accept_gate_failure=True, target_channel=None
        ),
        headers=AUTH,
    )
    assert accepted.status_code == 201, accepted.text


def test_a_niche_label_that_does_not_match_the_order_is_refused(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    wrong = api.post(
        PILOTS, json=authorize_body(request_id, niche_label="personal_finance"), headers=AUTH
    )
    assert wrong.status_code in (404, 409, 422)
