# tests/test_subniche_api.py
import pytest
from sqlalchemy import Engine

from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed
from tests.subniche_samples import NOW as MEASURED
from tests.subniche_samples import channel, draft, make_run, video
from tests.test_market_api import AUTH, client
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
BASE = "/api/v1/subniches"


def seed(engine: Engine) -> None:
    with engine.begin() as connection:
        run_id, _, _ = make_run(connection)
        rows = [hit("a", traction=True, low="100", high="900")]
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
        create_proposed(connection, draft(slug="fresh_one", queries=("fresh words",)), MEASURED)


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    assert api.get(BASE).status_code == 401
    assert api.get(BASE + "/history_revenge").status_code == 401
    assert api.get(BASE, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_the_listing_returns_measurements_and_hides_inactive_by_default(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    items = api.get(BASE, headers=AUTH).json()["items"]
    assert [item["slug"] for item in items] == ["history_revenge", "fresh_one"]
    assert items[0]["measurement"]["traction_channels"] == 1
    assert items[1]["measurement"] is None


def test_the_listing_can_include_inactive_hypotheses(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    assert api.get(BASE + "?include_inactive=true", headers=AUTH).status_code == 200


def test_the_detail_returns_the_card_and_unknown_slugs_are_404(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    card = api.get(BASE + "/history_revenge", headers=AUTH).json()
    assert card["hypothesis"]["slug"] == "history_revenge" and card["research"] is None
    assert card["measurement"]["income_high"] == "900.00"
    missing = api.get(BASE + "/nope_nope", headers=AUTH)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"
