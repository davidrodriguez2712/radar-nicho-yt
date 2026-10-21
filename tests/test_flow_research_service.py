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
)
from nicheradar.market_intel.niches import save_decision
from nicheradar.repositories.schema import (
    listing_classifications,
    listing_observations,
    listing_verifications,
    marketplace_listings,
)
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
