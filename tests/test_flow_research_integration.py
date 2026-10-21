# tests/test_flow_research_integration.py
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import market_niche_decisions
from tests.flow_research_samples import valid_dossier
from tests.test_flow_research_api import BASE, create, tentative_api
from tests.test_market_api import AUTH
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            "providers": connection.execute(
                sa.select(sa.func.count()).select_from(s.provider_requests)
            ).scalar_one(),
            "runs": connection.execute(
                sa.select(sa.func.count()).select_from(s.analysis_runs)
            ).scalar_one(),
            "decisions": connection.execute(
                sa.select(sa.func.count()).select_from(market_niche_decisions)
            ).scalar_one(),
        }


def test_a_request_never_touches_budget_providers_or_status(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    before = counts(isolated_engine)
    status_before = api.get("/api/v1/status", headers=AUTH).json()
    request_id = create(api)["id"]
    claim = api.post(f"{BASE}/{request_id}/claim", json={"owner": "w1"}, headers=AUTH)
    owner = claim.json()["lease_owner"]
    dossier = valid_dossier(UUID(request_id), NOW)
    assert api.post(
        f"{BASE}/{request_id}/dossier", json={"owner": owner, "dossier": dossier}, headers=AUTH
    ).json()["accepted"]
    after = counts(isolated_engine)
    assert (after["providers"], after["runs"]) == (before["providers"], before["runs"])
    status_after = api.get("/api/v1/status", headers=AUTH).json()
    assert status_after["last_success_at"] == status_before["last_success_at"] is None


def test_a_request_leaves_the_owner_decision_untouched(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    before = counts(isolated_engine)["decisions"]
    request_id = create(api)["id"]
    claim = api.post(f"{BASE}/{request_id}/claim", json={"owner": "w1"}, headers=AUTH)
    owner = claim.json()["lease_owner"]
    api.post(
        f"{BASE}/{request_id}/dossier",
        json={"owner": owner, "dossier": valid_dossier(UUID(request_id), NOW)},
        headers=AUTH,
    )
    assert counts(isolated_engine)["decisions"] == before
    listed = api.get("/api/v1/market/niches?format=long", headers=AUTH).json()["items"][0]
    assert listed["decision"]["decision"] == "tentativo"


def test_a_new_investigation_keeps_the_previous_dossier(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    first = create(api)["id"]
    claim = api.post(f"{BASE}/{first}/claim", json={"owner": "w1"}, headers=AUTH)
    owner = claim.json()["lease_owner"]
    api.post(
        f"{BASE}/{first}/dossier",
        json={"owner": owner, "dossier": valid_dossier(UUID(first), NOW)},
        headers=AUTH,
    )
    second = create(api)["id"]  # the first is `listo`, so a new version can be ordered
    assert second != first
    api.get(f"{BASE}/{uuid4()}", headers=AUTH)
    old = api.get(f"{BASE}/{first}", headers=AUTH).json()
    assert old["status"] == "listo" and old["dossier"] is not None
