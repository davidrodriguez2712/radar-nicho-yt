# tests/test_flow_research_language.py
"""El idioma se elige al iniciar la investigación y entra en la clave del encargo."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from nicheradar.flow_research.service import (
    FlowResearchError,
    claim_request,
    create_request,
    list_requests,
    submit_dossier,
)
from nicheradar.market_intel.niches import language_mix, niche_detail, save_decision
from tests.flow_research_samples import valid_dossier
from tests.test_flow_research_api import BASE, tentative_api
from tests.test_market_api import AUTH
from tests.test_market_intel_niches import seed, seed_niche
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def mixed_niche(db: Connection) -> None:
    seed_niche(
        db, "personal_finance", (1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000), price=67_500
    )
    seed(db, "personal_finance", 2200, language="es", price=67_500)
    seed(db, "personal_finance", 2300, language="unknown", price=67_500)
    save_decision(db, "personal_finance", "long", "tentativo", None, NOW)


def test_the_mix_counts_listings_per_language_and_sums_to_one_hundred() -> None:
    mix = language_mix([{"language": "en"}] * 8 + [{"language": "es"}, {"language": "unknown"}])
    assert mix == [
        {"language": "en", "share_pct": 80.0},
        {"language": "es", "share_pct": 10.0},
        {"language": "unknown", "share_pct": 10.0},
    ]
    assert language_mix([]) == []


def test_the_niche_detail_exposes_the_language_mix(db: Connection) -> None:
    mixed_niche(db)
    detail = niche_detail(db, "personal_finance", "long", NOW)
    assert detail is not None
    assert [item["language"] for item in detail["language_mix"]] == ["en", "es", "unknown"]


def test_the_same_niche_can_be_researched_once_per_language(db: Connection) -> None:
    mixed_niche(db)
    english, created = create_request(db, "personal_finance", "long", "en", NOW)
    assert created and english["language"] == "en"
    spanish, created_es = create_request(db, "personal_finance", "long", "es", NOW)
    assert created_es and spanish["id"] != english["id"] and spanish["language"] == "es"
    again, created_again = create_request(db, "personal_finance", "long", "en", NOW)
    assert created_again is False and again["id"] == english["id"]
    assert [i["language"] for i in list_requests(db, language="es")] == ["es"]


@pytest.mark.parametrize("language", ["unknown", "english", "EN", ""])
def test_a_request_needs_a_real_language_code(db: Connection, language: str) -> None:
    mixed_niche(db)
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "personal_finance", "long", language, NOW)
    assert error.value.code == "invalid_language"


def test_the_frozen_evidence_carries_the_mix_and_the_chosen_language(db: Connection) -> None:
    mixed_niche(db)
    request, _ = create_request(db, "personal_finance", "long", "es", NOW)
    assert request["evidence"]["language"] == "es"
    assert request["evidence"]["language_mix"][0] == {"language": "en", "share_pct": 80.0}


def test_the_dossier_must_answer_in_the_language_that_was_ordered(db: Connection) -> None:
    mixed_niche(db)
    request, _ = create_request(db, "personal_finance", "long", "es", NOW)
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    wrong = valid_dossier(request["id"], NOW) | {"language": "en"}
    result = submit_dossier(db, request["id"], owner, wrong, NOW)
    assert result["accepted"] is False
    assert {"path": "language", "message": "no corresponde al idioma del encargo"} in result[
        "problems"
    ]
    right = valid_dossier(request["id"], NOW) | {"language": "es"}
    assert submit_dossier(db, request["id"], owner, right, NOW)["accepted"] is True


def test_the_dossier_contract_rejects_a_missing_or_malformed_language() -> None:
    from nicheradar.flow_research.contracts import validate_dossier

    body = valid_dossier(UUID(int=1), NOW)
    del body["language"]
    dossier, problems = validate_dossier(body, NOW)
    assert dossier is None and any(p["path"] == "language" for p in problems)
    dossier, problems = validate_dossier(body | {"language": "ingles"}, NOW)
    assert dossier is None and any(p["path"] == "language" for p in problems)


def test_the_api_requires_the_language_and_keeps_requests_apart(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    base = {"niche_label": "personal_finance", "format": "long"}
    assert api.post(BASE, json=base, headers=AUTH).status_code == 422
    assert api.post(BASE, json=base | {"language": "unknown"}, headers=AUTH).status_code == 422
    first = api.post(BASE, json=base | {"language": "en"}, headers=AUTH)
    second = api.post(BASE, json=base | {"language": "es"}, headers=AUTH)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["language"] == "en" and first.json()["id"] != second.json()["id"]
    listed = api.get(BASE + "?language=es", headers=AUTH).json()["items"]
    assert [item["language"] for item in listed] == ["es"]
    pending = api.get(BASE + "/pending", headers=AUTH).json()["items"]
    assert {item["language"] for item in pending} == {"en", "es"}


def test_the_dashboard_detail_endpoint_suggests_the_dominant_language(
    isolated_engine: Engine,
) -> None:
    api = tentative_api(isolated_engine)
    response = api.get("/api/v1/market/niches/personal_finance?format=long", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["language_mix"][0]["language"] == "en"


def _legacy_engine(postgres_engine: Engine) -> tuple[Engine, str]:
    schema = "nrtest_" + uuid4().hex
    with postgres_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        postgres_engine.url,
        hide_parameters=True,
        connect_args={"options": f"-c search_path={schema} -c timezone=UTC"},
    )
    return engine, schema


def test_the_migration_rejects_active_requests_that_have_no_language(
    postgres_engine: Engine,
) -> None:
    engine, schema = _legacy_engine(postgres_engine)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0015")
            for status in ("pendiente", "en_curso", "listo"):
                connection.execute(
                    sa.text(
                        "INSERT INTO flow_research_requests (id, niche_label, format, status, "
                        "evidence, attempts, lease_owner, lease_until, created_at, updated_at, "
                        "retain_until) VALUES (:id, :label, 'long', :status, '{}', 0, :owner, "
                        ":until, now(), now(), now() + interval '183 days')"
                    ),
                    {
                        "id": uuid4(),
                        "label": f"niche_{status}",
                        "status": status,
                        "owner": "w#1" if status == "en_curso" else None,
                        "until": NOW if status == "en_curso" else None,
                    },
                )
            command.upgrade(config, "head")
            rows = {
                row.niche_label: row
                for row in connection.execute(
                    sa.text(
                        "SELECT niche_label, status, language, rejection, lease_owner "
                        "FROM flow_research_requests"
                    )
                )
            }
        assert {row.language for row in rows.values()} == {"unknown"}
        for label in ("niche_pendiente", "niche_en_curso"):
            assert rows[label].status == "rechazado" and rows[label].lease_owner is None
            assert rows[label].rejection["problems"][0]["path"] == "language"
        assert rows["niche_listo"].status == "listo"  # lo ya entregado no se toca
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def test_a_pilot_takes_the_language_of_its_dossier(isolated_engine: Engine) -> None:
    from tests.test_pilots_api import BASE as PILOTS
    from tests.test_pilots_api import authorize_body, ready_dossier

    api: TestClient = tentative_api(isolated_engine)
    request_id = ready_dossier(api)
    created = api.post(PILOTS, json=authorize_body(request_id), headers=AUTH)
    assert created.status_code == 201
    assert created.json()["package"]["niche"]["language"] == "en"
    with_language = authorize_body(request_id) | {"language": "es"}
    assert api.post(PILOTS, json=with_language, headers=AUTH).status_code == 422


def test_a_legacy_request_without_language_cannot_become_a_pilot(db: Connection) -> None:
    from nicheradar.pilots.service import PilotError, authorize

    mixed_niche(db)
    request, _ = create_request(db, "personal_finance", "long", "en", NOW)
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    ready = valid_dossier(request["id"], NOW) | {"language": "en"}
    assert submit_dossier(db, request["id"], owner, ready, NOW)["accepted"] is True
    db.execute(
        sa.text("UPDATE flow_research_requests SET language = 'unknown' WHERE id = :id"),
        {"id": request["id"]},
    )
    with pytest.raises(PilotError) as error:
        authorize(
            db,
            niche_label="personal_finance",
            format="long",
            dossier_request_id=request["id"],
            budget={},
            stop_rules=None,
            close_after=2,
            target_channel=None,
            recipe=None,
            valid_days=14,
            authorized_by="david",
            accept_no_go=False,
            supersedes=None,
            now=NOW,
        )
    assert error.value.code == "language_unknown"
