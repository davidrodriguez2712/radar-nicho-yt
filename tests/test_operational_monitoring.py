"""Operational acceptance with invented accounting, never production credentials."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Connection, Engine, select, update
from sqlalchemy.exc import SQLAlchemyError
from streamlit.testing.v1 import AppTest

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.operations import jobs
from nicheradar.workers.main import tick
from tests.test_api_contracts import client_for
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW, seed_evidence


@pytest.mark.postgres
def test_run_accounting_separates_units_statuses_and_pages(db: Connection) -> None:
    ids = seed_evidence(db)
    job_ids = []
    for index in range(2):
        run = (
            ids["run"]
            if index == 0
            else insert_record(
                db,
                "analysis_runs",
                {
                    "profile_id": ids["profile"],
                    "mode": "synthetic",
                    "trigger": "manual",
                    "status": "failed",
                    "configuration": {},
                },
            )
        )
        job_ids.append(
            insert_record(
                db,
                "jobs",
                {
                    "run_id": run,
                    "occurrence_key": str(uuid4()),
                    "status": "failed",
                    "stage": "query",
                    "available_at": NOW,
                    "created_at": NOW + timedelta(seconds=index),
                    "checkpoints": {"query": {"private": "fixture-hidden-checkpoint"}},
                    "lease_owner": "fixture-hidden-worker",
                    "error_code": "unknown_charge",
                },
            )
        )
        for status, amount in (
            ("confirmed", "2"),
            ("reserved", "3"),
            ("unknown_charge", "4"),
            ("released", "99"),
        ):
            request = insert_record(
                db,
                "provider_requests",
                {
                    "run_id": run,
                    "provider": "synthetic",
                    "operation": "recent",
                    "auth_scope": "fixture-hidden-scope",
                    "cache_key": "b" * 64,
                    "idempotency_key": str(uuid4()),
                    "state": "completed",
                },
            )
            for unit in ("USD", "fixture:credits"):
                insert_record(
                    db,
                    "cost_reservations",
                    {
                        "request_id": request,
                        "profile_id": ids["profile"],
                        "unit": unit,
                        "amount": Decimal(amount),
                        "status": status,
                        "period_start": NOW,
                        "period_end": NOW + timedelta(days=30),
                    },
                )
                if status == "confirmed":
                    # Two ledger entries prove aggregation, without a cartesian join.
                    for _ in range(2):
                        insert_record(
                            db,
                            "cost_ledger",
                            {
                                "profile_id": ids["profile"],
                                "request_id": request,
                                "unit": unit,
                                "amount": Decimal(1),
                                "kind": "provider_call",
                                "external_reference": str(uuid4()),
                                "occurred_at": NOW,
                            },
                        )
    insert_record(
        db,
        "cost_ledger",
        {
            "profile_id": ids["profile"],
            "request_id": None,
            "unit": "USD",
            "amount": Decimal(100),
            "kind": "subscription",
            "external_reference": "fixture-hidden-reference",
            "occurred_at": NOW,
        },
    )
    for offset, expected_job in enumerate(reversed(job_ids)):
        page = jobs(db, limit=1, offset=offset)
        assert page["total"] == 2
        row = page["items"][0]
        assert row["id"] == expected_job
        assert row["consumption"]["confirmed"] == [
            {"unit": "USD", "amount": Decimal(2)},
            {"unit": "fixture:credits", "amount": Decimal(2)},
        ]
        assert {
            (r["unit"], r["status"], r["amount"]) for r in row["consumption"]["reservations"]
        } == {
            (unit, status, Decimal(amount))
            for unit in ("USD", "fixture:credits")
            for status, amount in (("reserved", "3"), ("unknown_charge", "4"))
        }
        assert "fixture-hidden" not in json.dumps(page, default=str)
        assert jobs(db, job_id=expected_job)["items"][0] == row
    assert jobs(db, offset=2)["items"] == []


@pytest.mark.postgres
def test_dashboard_monitoring_keeps_last_success_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    isolated_engine: Engine,
) -> None:
    backend = client_for(isolated_engine)
    backend.put("/api/v1/radar", json={"paused": False}).raise_for_status()
    assert tick(Settings(), isolated_engine)["status"] == "succeeded"
    backend.put("/api/v1/radar", json={"paused": True}).raise_for_status()
    earlier = NOW - timedelta(hours=6)
    with isolated_engine.begin() as db:
        db.execute(update(s.analysis_runs).values(finished_at=earlier))
        db.execute(update(s.video_observations).values(observed_at=earlier))
        profile = db.execute(select(s.creator_profiles.c.id)).scalar_one()
        failed_run = insert_record(
            db,
            "analysis_runs",
            {
                "profile_id": profile,
                "mode": "synthetic",
                "trigger": "manual",
                "status": "failed",
                "configuration": {},
                "finished_at": datetime.now(UTC),
                "coverage": {
                    "complete": False,
                    "pending_reason": "timeout",
                    "work_kind": "catalog",
                    "catalog_pending": ["history"],
                },
            },
        )
        insert_record(
            db,
            "jobs",
            {
                "run_id": failed_run,
                "occurrence_key": str(uuid4()),
                "status": "failed",
                "stage": "query",
                "available_at": datetime.now(UTC),
                "checkpoints": {},
                "error_code": "timeout",
            },
        )
        request = insert_record(
            db,
            "provider_requests",
            {
                "run_id": failed_run,
                "provider": "synthetic",
                "operation": "recent",
                "auth_scope": "invented",
                "cache_key": "c" * 64,
                "idempotency_key": str(uuid4()),
                "state": "completed",
            },
        )
        insert_record(
            db,
            "cost_ledger",
            {
                "profile_id": profile,
                "request_id": request,
                "unit": "USD",
                "amount": Decimal("1.25"),
                "kind": "provider_call",
                "external_reference": str(uuid4()),
                "occurred_at": datetime.now(UTC),
            },
        )
        insert_record(
            db,
            "cost_reservations",
            {
                "profile_id": profile,
                "request_id": request,
                "unit": "fixture:credits",
                "amount": Decimal(5),
                "status": "unknown_charge",
                "period_start": earlier,
                "period_end": earlier + timedelta(days=30),
            },
        )
    status = backend.get("/api/v1/status").json()
    assert datetime.fromisoformat(status["last_success_at"]) == earlier
    assert status["research"]["observation_age_hours"] >= 6
    assert "technical_error" in status["research"]["reasons"]

    class LocalClient:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def __enter__(self) -> "LocalClient":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def get(self, path: str) -> httpx.Response:
            response: httpx.Response = backend.get(path)
            return response

        def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
            response: httpx.Response = backend.request(method, path, **kwargs)
            return response

    monkeypatch.setattr("nicheradar.dashboard.httpx.Client", LocalClient)
    monkeypatch.setenv("NR_DASHBOARD_PASSWORD", TOKEN)
    monkeypatch.setenv("NR_SERVICE_TOKEN", TOKEN)
    app = AppTest.from_file("../apps/dashboard/main.py", default_timeout=30).run()
    app.text_input[0].set_value(TOKEN)
    app.button[0].click().run()
    app.radio[0].set_value("Operación").run()
    assert not app.exception
    assert any("error técnico" in item.value for item in app.warning)
    assert any("6.0 horas" in item.value for item in app.caption)
    assert any("Última ejecución satisfactoria:" in item.value for item in app.caption)
    assert any("Lote parcial: timeout" in item.value for item in app.warning)
    assert len([e for e in app.expander if e.label.startswith("Consumo de ejecución")]) == 2
    reservation_index = next(
        index
        for index, item in enumerate(app.dataframe)
        if "status" in item.value.columns and "unknown_charge" in item.value["status"].tolist()
    )
    assert app.dataframe[reservation_index].value.to_dict("records") == [
        {"unit": "fixture:credits", "amount": "5.000000", "status": "unknown_charge"}
    ]
    assert app.dataframe[reservation_index - 1].value.to_dict("records") == [
        {"unit": "USD", "amount": "1.250000"}
    ]
    table = app.dataframe[0].value
    assert "timeout" in table["error_code"].tolist()
    assert TOKEN not in table.to_json()
    assert backend.get("/api/v1/status").json()["radar_paused"] is True


def test_runtime_limits_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NR_EXTERNAL_CONCURRENCY", "2")
    monkeypatch.setenv("NR_BATCH_SIZE", "7")
    monkeypatch.setenv("NR_WORKER_MAXIMUM_ATTEMPTS", "2")
    settings = Settings()
    assert settings.external_concurrency == 2
    assert settings.batch_size == 7
    assert settings.worker_maximum_attempts == 2


def test_database_failure_diagnostic_does_not_include_exception_secrets() -> None:
    engine = Mock(spec=Engine)
    engine.begin.side_effect = SQLAlchemyError("fixture-private-database-password")
    diagnostic = tick(Settings(), engine)
    assert diagnostic["error_code"] == "database_unavailable"
    assert diagnostic["provider_calls"] == 0
    assert "fixture-private" not in json.dumps(diagnostic)


@pytest.mark.postgres
def test_run_without_accounting_reports_empty_not_a_fabricated_zero(db: Connection) -> None:
    ids = seed_evidence(db)
    insert_record(
        db,
        "jobs",
        {
            "run_id": ids["run"],
            "occurrence_key": str(uuid4()),
            "status": "queued",
            "stage": "query",
            "available_at": NOW,
            "checkpoints": {},
        },
    )
    assert jobs(db)["items"][0]["consumption"] == {"confirmed": [], "reservations": []}
