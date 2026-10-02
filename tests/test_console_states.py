from datetime import timedelta

import pytest
from sqlalchemy import Connection, Engine, select, update
from streamlit.testing.v1 import AppTest

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.operations import overview
from tests.test_api_contracts import client_for
from tests.test_persistence import NOW, seed_evidence
from tests.test_ranking import evaluation


@pytest.mark.postgres
@pytest.mark.parametrize(
    "code,expected",
    [
        ("run_budget_exhausted", "budget_blocked"),
        ("shared_budget_exhausted", "budget_blocked"),
        ("unknown_charge", "budget_blocked"),
        ("authentication_required", "configuration_pending"),
        ("live_prerequisites_incomplete", "configuration_pending"),
        ("policy_pending", "configuration_pending"),
        ("unknown_cost", "configuration_pending"),
        ("timeout", "technical_error"),
        ("refresh_evidence_insufficient", "coverage_pending"),
    ],
)
def test_operational_states_are_distinct(db: Connection, code: str, expected: str) -> None:
    ids = seed_evidence(db)
    insert_record(
        db,
        "jobs",
        {
            "run_id": ids["run"],
            "occurrence_key": "fixture-state",
            "status": "deferred",
            "stage": "query",
            "checkpoints": {},
            "available_at": NOW,
            "error_code": code,
        },
    )
    result = overview(db, ids["profile"], "synthetic", NOW)
    assert expected in result["reasons"]
    assert "no_results" in result["reasons"]
    assert result["last_error_code"] == code


@pytest.mark.postgres
def test_overview_uses_original_observation_and_latest_evidence(db: Connection) -> None:
    ids = seed_evidence(db)
    evaluation(db, ids)
    latest = evaluation(db, ids, score=None)
    later = NOW + timedelta(hours=6)
    db.execute(
        update(s.evaluation_versions)
        .where(s.evaluation_versions.c.id == latest)
        .values(created_at=later)
    )
    result = overview(db, ids["profile"], "synthetic", later)
    assert result["last_observed_at"] == NOW
    assert result["last_evaluated_at"] == later
    assert result["observation_age_hours"] == 6
    assert result["evaluations"] == 1
    assert result["scored"] == 0
    assert result["reasons"] == ["evaluation_pending"]
    db.execute(
        update(s.evaluation_versions)
        .where(s.evaluation_versions.c.id == latest)
        .values(retain_until=later)
    )
    assert overview(db, ids["profile"], "synthetic", later)["reasons"] == ["evidence_expired"]
    live = overview(db, ids["profile"], "live", later)
    assert live["last_observed_at"] is None
    assert live["reasons"] == ["provider_pending", "no_results"]
    ready = overview(db, ids["profile"], "live", later, provider_ready=True)
    assert ready["reasons"] == ["no_results"]


def render_state_probe(status: dict[str, object]) -> None:
    from nicheradar.config import Settings
    from nicheradar.dashboard import render_research_status

    render_research_status(Settings(), status)


@pytest.mark.parametrize(
    "reason,fragment",
    [
        ("provider_pending", "Proveedor real pendiente"),
        ("configuration_pending", "Falta configuración"),
        ("budget_blocked", "Trabajo aplazado por presupuesto"),
        ("technical_error", "error técnico"),
        ("processing", "pendiente o en curso"),
        ("evidence_expired", "han caducado"),
        ("no_results", "Aún no hay resultados"),
        ("evaluation_pending", "falta evidencia"),
        ("coverage_pending", "fue parcial"),
    ],
)
def test_dashboard_empty_states_have_distinct_explanations(reason: str, fragment: str) -> None:
    app = AppTest.from_function(
        render_state_probe, args=({"research": {"reasons": [reason]}},)
    ).run()
    assert not app.exception
    assert any(fragment in item.value for item in [*app.info, *app.warning])
    assert not app.dataframe


def test_dashboard_observation_time_is_lima_not_evaluation_time() -> None:
    app = AppTest.from_function(
        render_state_probe,
        args=(
            {
                "research": {
                    "reasons": [],
                    "last_observed_at": "2026-09-14T01:00:00Z",
                    "observation_age_hours": 6,
                }
            },
        ),
    ).run()
    assert not app.exception
    assert "13/09/2026 20:00" in app.caption[0].value
    assert "6.0 horas" in app.caption[0].value


@pytest.mark.postgres
def test_backlog_filters_sorting_and_no_artificial_top(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as db:
        ids = seed_evidence(db)
        evaluation(db, ids, score=0)
        for label, score, gate in (("Beta", 80, "viable"), ("Gamma", 40, "not_viable")):
            topic = insert_record(
                db,
                "topics",
                {
                    "family_id": ids["family"],
                    "label": label,
                    "identity_key": label,
                    "method_version": "fixture",
                },
            )
            opportunity = insert_record(
                db,
                "opportunities",
                {"topic_id": topic, "audience_key": "en", "language": "en", "format": "long"},
            )
            key = evaluation(db, ids, opportunity=opportunity, score=score)
            original = db.execute(
                select(s.evaluation_versions.c.explanation).where(s.evaluation_versions.c.id == key)
            ).scalar_one()
            original["combined"]["resource_gate"] = gate
            db.execute(
                update(s.evaluation_versions)
                .where(s.evaluation_versions.c.id == key)
                .values(explanation=original)
            )
    client = client_for(isolated_engine)
    path = "/api/v1/opportunities"
    result = client.get(path, params={"limit": 10}).json()
    assert result["total"] == len(result["items"]) == 3
    assert [row["final_score"] for row in result["items"]] == [80, 40, 0]
    assert client.get(path, params={"descending": False}).json()["items"][0]["final_score"] == 0
    assert client.get(path, params={"query": "bEtA"}).json()["total"] == 1
    assert client.get(path, params={"query": "%"}).json()["total"] == 0
    assert client.get(path, params={"viability": "viable"}).json()["items"][0]["label"] == "Beta"
    assert client.get(path, params={"minimum_score": 0}).json()["total"] == 3
    assert client.get(path, params={"minimum_score": 50}).json()["total"] == 1
    assert client.get(path, params={"evaluated_after": "2026-09-14T00:00:00Z"}).json()["total"] == 0
    for sort in ("topic", "format", "state", "confidence", "viability", "date"):
        assert client.get(path, params={"sort_by": sort}).status_code == 200
    for params in (
        {"sort_by": "invalid"},
        {"minimum_score": "nan"},
        {"minimum_score": -1},
        {"evaluated_after": "2026-09-13T00:00:00"},
        {"viability": "yes"},
    ):
        assert client.get(path, params=params).status_code == 422
