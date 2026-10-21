# tests/test_flow_research_service.py
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.flow_research.service import (
    LEASE,
    FlowResearchError,
    claim_request,
    create_request,
    get_request,
    list_requests,
    pending_requests,
    submit_dossier,
)
from nicheradar.market_intel.niches import save_decision
from nicheradar.repositories.schema import (
    flow_research_dossiers,
    flow_research_requests,
    listing_classifications,
    listing_observations,
    listing_verifications,
    marketplace_listings,
)
from tests.flow_research_samples import valid_dossier
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def tentative(db: Connection, label: str = "personal_finance") -> None:
    seed_niche(db, label, (1500, 2000, 2500, 3000), price=67_500)
    save_decision(db, label, "long", "tentativo", None, NOW)


def fresh_request(db: Connection) -> dict[str, Any]:
    tentative(db)
    request, created = create_request(db, "personal_finance", "long", NOW)
    assert created
    return request


def test_a_tentative_niche_creates_a_pending_request_with_frozen_evidence(db: Connection) -> None:
    request = fresh_request(db)
    assert request["status"] == "pendiente" and request["attempts"] == 0
    evidence = request["evidence"]
    assert evidence["niche"]["niche_label"] == "personal_finance"
    assert evidence["listing_count"] == 4 and isinstance(evidence["verified_count"], int)
    assert len(evidence["verified_listings"]) <= 10 and "history" in evidence
    assert request["dossier"] is None


def test_a_niche_that_is_not_tentative_cannot_be_researched(db: Connection) -> None:
    seed_niche(db, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "personal_finance", "long", NOW)
    assert error.value.code == "not_tentative"


def test_a_niche_without_scores_cannot_be_researched(db: Connection) -> None:
    seed_niche(db, "cooking_recipes", (400, 500))
    save_decision(db, "cooking_recipes", "long", "tentativo", None, NOW)
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "cooking_recipes", "long", NOW)
    assert error.value.code == "no_evidence"


def test_an_unknown_niche_is_not_found(db: Connection) -> None:
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "nope", "long", NOW)
    assert error.value.code == "not_found"


def test_creating_twice_returns_the_active_request(db: Connection) -> None:
    first = fresh_request(db)
    again, created = create_request(db, "personal_finance", "long", NOW)
    assert created is False and again["id"] == first["id"]
    claim_request(db, first["id"], "worker", NOW)
    while_running, created = create_request(db, "personal_finance", "long", NOW)
    assert created is False and while_running["id"] == first["id"]


def test_two_simultaneous_creations_leave_one_active_request(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        tentative(connection)
    first = isolated_engine.connect()
    transaction = first.begin()
    created, was_created = create_request(first, "personal_finance", "long", NOW)
    assert was_created

    def second() -> tuple[dict[str, Any], bool]:
        with isolated_engine.begin() as connection:
            return create_request(connection, "personal_finance", "long", NOW)

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(second)
        time.sleep(0.5)  # usually enough for the second insert to wait on the unique index
        transaction.commit()
        first.close()
        other, other_created = future.result(timeout=10)
    assert other_created is False and other["id"] == created["id"]
    with isolated_engine.connect() as connection:
        assert len(list_requests(connection, status="pendiente")) == 1


def test_claiming_sets_a_sixty_minute_lease_and_blocks_a_second_claim(db: Connection) -> None:
    request = fresh_request(db)
    claimed = claim_request(db, request["id"], "worker-a", NOW)
    assert claimed["status"] == "en_curso" and claimed["lease_until"] == NOW + LEASE
    assert claimed["evidence"]["niche"]["niche_label"] == "personal_finance"
    with pytest.raises(FlowResearchError) as error:
        claim_request(db, request["id"], "worker-b", NOW)
    assert error.value.code == "not_claimable"
    with pytest.raises(FlowResearchError) as missing:
        claim_request(db, uuid4(), "worker-a", NOW)
    assert missing.value.code == "not_found"


def test_an_expired_lease_returns_the_request_to_pending(db: Connection) -> None:
    request = fresh_request(db)
    claim_request(db, request["id"], "worker-a", NOW)
    assert pending_requests(db, NOW + LEASE - timedelta(minutes=1)) == []
    later = NOW + LEASE + timedelta(minutes=1)
    assert [item["id"] for item in pending_requests(db, later)] == [request["id"]]
    again = claim_request(db, request["id"], "worker-b", later)
    assert again["status"] == "en_curso"


def test_listing_filters_by_niche_format_and_status(db: Connection) -> None:
    request = fresh_request(db)
    assert [i["id"] for i in list_requests(db, niche_label="personal_finance", format="long")] == [
        request["id"]
    ]
    assert list_requests(db, niche_label="personal_finance", format="shorts") == []
    assert list_requests(db, status="listo") == []
    assert "evidence" not in list_requests(db)[0]


def test_the_frozen_evidence_survives_the_niche_disappearing(db: Connection) -> None:
    request = fresh_request(db)
    for table in (
        listing_verifications,
        listing_classifications,
        listing_observations,
        marketplace_listings,
    ):
        db.execute(sa.delete(table))
    stored = get_request(db, request["id"])
    assert stored is not None and stored["evidence"]["listing_count"] == 4


def test_discarding_the_niche_keeps_the_request(db: Connection) -> None:
    request = fresh_request(db)
    save_decision(db, "personal_finance", "long", "descartado", None, NOW + timedelta(minutes=1))
    assert [item["id"] for item in list_requests(db)] == [request["id"]]
    again, created = create_request(db, "personal_finance", "long", NOW)
    assert created is False and again["id"] == request["id"]


def claimed(db: Connection, owner: str = "worker-a") -> dict[str, Any]:
    request = fresh_request(db)
    return claim_request(db, request["id"], owner, NOW)


def test_a_valid_dossier_completes_the_request_and_is_stored(db: Connection) -> None:
    request = claimed(db)
    result = submit_dossier(
        db, request["id"], request["lease_owner"], valid_dossier(request["id"], NOW), NOW
    )
    assert result["accepted"] is True and result["status"] == "listo"
    stored = get_request(db, request["id"])
    assert stored is not None and stored["status"] == "listo" and stored["rejection"] is None
    assert stored["dossier"]["verdict"]["recommendation"] == "go_with_conditions"
    assert stored["dossier"]["request_id"] == str(request["id"])
    retained = db.execute(
        sa.select(flow_research_requests.c.retain_until, flow_research_dossiers.c.retain_until)
        .select_from(flow_research_requests.join(flow_research_dossiers))
        .where(flow_research_requests.c.id == request["id"])
    ).one()
    assert retained[0] == retained[1]  # the request never expires before its dossier
    with pytest.raises(FlowResearchError) as error:
        submit_dossier(
            db, request["id"], request["lease_owner"], valid_dossier(request["id"], NOW), NOW
        )
    assert error.value.code == "lease_lost"  # a finished request accepts nothing more


def test_a_stale_owner_cannot_submit_after_another_claimed(db: Connection) -> None:
    first = claimed(db, "worker-a")
    later = NOW + LEASE + timedelta(minutes=1)
    second = claim_request(db, first["id"], "worker-b", later)
    payload = valid_dossier(first["id"], later)
    with pytest.raises(FlowResearchError) as lost:
        submit_dossier(db, first["id"], first["lease_owner"], payload, later)
    assert lost.value.code == "lease_lost"
    assert (
        submit_dossier(db, first["id"], second["lease_owner"], payload, later)["accepted"] is True
    )


def test_an_expired_lease_rejects_a_late_dossier(db: Connection) -> None:
    request = claimed(db)
    later = NOW + LEASE + timedelta(minutes=1)
    with pytest.raises(FlowResearchError) as lost:
        submit_dossier(
            db, request["id"], request["lease_owner"], valid_dossier(request["id"], later), later
        )
    assert lost.value.code == "lease_lost"


def test_unknown_requests_are_not_found(db: Connection) -> None:
    with pytest.raises(FlowResearchError) as error:
        submit_dossier(db, uuid4(), "worker-a#x", {}, NOW)
    assert error.value.code == "not_found"


def test_the_first_invalid_dossier_allows_one_retry_and_the_second_rejects(
    db: Connection,
) -> None:
    request = claimed(db)
    bad = valid_dossier(request["id"], NOW)
    bad["budget"]["totals"]["likely"] = 999.0
    bad["budget"]["totals"]["high"] = 1000.0
    first = submit_dossier(db, request["id"], request["lease_owner"], bad, NOW)
    assert first["accepted"] is False and first["status"] == "en_curso"
    assert first["remaining_attempts"] == 1
    assert "budget.totals.likely" in {problem["path"] for problem in first["problems"]}
    second = submit_dossier(db, request["id"], request["lease_owner"], bad, NOW)
    assert second["status"] == "rechazado" and second["remaining_attempts"] == 0
    stored = get_request(db, request["id"])
    assert stored is not None and stored["attempts"] == 2 and stored["dossier"] is None
    assert stored["rejection"]["problems"]
    with pytest.raises(FlowResearchError) as error:
        claim_request(db, request["id"], "worker-c", NOW)
    assert error.value.code == "not_claimable"
    retry, created = create_request(db, "personal_finance", "long", NOW)
    assert created is True and retry["id"] != request["id"]  # "retry" is a new request


def test_a_dossier_for_another_request_or_niche_is_rejected(db: Connection) -> None:
    request = claimed(db)
    other = valid_dossier(uuid4(), NOW)
    other["niche_label"] = "gaming_general"
    result = submit_dossier(db, request["id"], request["lease_owner"], other, NOW)
    paths = {problem["path"] for problem in result["problems"]}
    assert result["accepted"] is False and {"request_id", "niche_label"} <= paths


def test_a_low_confidence_niche_requires_declared_unknowns(db: Connection) -> None:
    request = claimed(db)
    evidence = request["evidence"]
    evidence["niche"]["confidence"] = "baja"
    db.execute(
        sa.update(flow_research_requests)
        .where(flow_research_requests.c.id == request["id"])
        .values(evidence=evidence)
    )
    payload = valid_dossier(request["id"], NOW)
    payload["verdict"]["unknowns"] = []
    result = submit_dossier(db, request["id"], request["lease_owner"], payload, NOW)
    assert "verdict.unknowns" in {problem["path"] for problem in result["problems"]}
    payload["verdict"]["unknowns"] = ["No se pudo verificar el RPM real"]
    assert (
        submit_dossier(db, request["id"], request["lease_owner"], payload, NOW)["accepted"] is True
    )


def test_a_stale_claim_with_the_same_owner_label_cannot_submit(db: Connection) -> None:
    first = claimed(db, "claude-code-1")
    later = NOW + LEASE + timedelta(minutes=1)
    second = claim_request(db, first["id"], "claude-code-1", later)
    assert first["lease_owner"] != second["lease_owner"]
    payload = valid_dossier(first["id"], later)
    with pytest.raises(FlowResearchError) as lost:
        submit_dossier(db, first["id"], first["lease_owner"], payload, later)
    assert lost.value.code == "lease_lost"
    assert submit_dossier(db, first["id"], second["lease_owner"], payload, later)["accepted"]


def test_an_unknown_field_name_is_never_echoed_back(db: Connection) -> None:
    request = claimed(db)
    payload = valid_dossier(request["id"], NOW) | {"sk-SECRET123": 1}
    result = submit_dossier(db, request["id"], request["lease_owner"], payload, NOW)
    assert result["accepted"] is False
    assert "SECRET" not in str(result["problems"])
    stored = get_request(db, request["id"])
    assert stored is not None and "SECRET" not in str(stored["rejection"])
