import pytest
from sqlalchemy import Engine

from nicheradar.integrations.tweets import Tweet
from nicheradar.subniche_discovery.lead_worker import tick_leads
from nicheradar.subniche_discovery.store import get_hypothesis
from nicheradar.subniche_discovery.worker import tick_proposals
from tests.lead_samples import (
    TWEET_ID,
    FakeResolver,
    FakeTweetReader,
    mentions_client,
    seed_lead_policies,
    vision_settings,
)
from tests.subniche_samples import channel, video
from tests.test_lead_api import client
from tests.test_market_api import AUTH
from tests.test_persistence import NOW as LLM_NOW
from tests.test_subniche_intake import client_answering
from tests.test_subniche_propose import GOOD, seed_policies, seed_run

pytestmark = pytest.mark.postgres
UC_A = "UC" + "a" * 22


def test_a_shared_tweet_ends_as_a_lead_proposal(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
        seed_lead_policies(connection)
    api = client(isolated_engine)
    created = api.post(
        "/api/v1/leads/tweets",
        json={"url": f"https://x.com/autor_x/status/{TWEET_ID}"},
        headers=AUTH | {"Idempotency-Key": "clave-flujo-0001"},
    ).json()
    resolver = FakeResolver(channels={UC_A: channel("a")}, uploads={UC_A: (video(1),)})
    resolver.handles["@historia_uno"] = channel("a")
    reader = FakeTweetReader(
        Tweet("autor_x", TWEET_ID, "Mira https://www.youtube.com/@historia_uno", ())
    )
    tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver,
        client=mentions_client(
            [{"kind": "name", "value": "Batallas Olvidadas", "found_in": "text"}]
        ),
        clock=lambda: LLM_NOW,
    )
    read = api.get(f"/api/v1/leads/{created['id']}", headers=AUTH).json()
    assert [c["resolution"] for c in read["candidates"]] == ["resolved", "name_only"]
    item = api.post(
        f"/api/v1/leads/{created['id']}/proposals",
        json={"candidate_ids": [read["candidates"][0]["id"]]},
        headers=AUTH,
    ).json()["items"][0]
    tick_proposals(
        vision_settings(anthropic_configuration=vision_settings().anthropic_vision_configuration),
        isolated_engine,
        reader=resolver,
        client=client_answering(GOOD),
        clock=lambda: LLM_NOW,
    )
    proposal = api.get(f"/api/v1/subniches/proposals/{item['proposal_id']}", headers=AUTH).json()
    assert proposal["status"] == "ready" and proposal["origin"]["tweet_author"] == "autor_x"
    assert proposal["hypothesis"]["seed_channels"] == [UC_A]
    with isolated_engine.connect() as connection:
        assert get_hypothesis(connection, proposal["hypothesis"]["slug"])["origin"] == "lead"
    assert resolver.name_searches == []  # el nombre nunca se buscó solo
