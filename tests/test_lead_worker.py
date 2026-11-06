from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from nicheradar.config import Settings
from nicheradar.integrations.tweets import ImageData, Tweet, TweetRef
from nicheradar.repositories.schema import lead_read_requests as reads
from nicheradar.subniche_discovery import leads
from nicheradar.subniche_discovery.lead_worker import tick_leads
from tests.lead_samples import (
    PNG,
    TWEET_ID,
    FakeResolver,
    FakeTweetReader,
    mentions_client,
    seed_lead_policies,
    vision_settings,
)
from tests.subniche_samples import channel
from tests.test_persistence import NOW as LLM_NOW
from tests.test_subniche_propose import seed_run

pytestmark = pytest.mark.postgres
REF = TweetRef("autor_x", TWEET_ID)
PHOTO = "https://pbs.twimg.com/media/foto1.png?name=large"
UC_A = "UC" + "a" * 22


def put_tweet(engine: Engine, key: str = "clave-worker-01", second: int = 0) -> UUID:
    created = LLM_NOW - timedelta(minutes=5) + timedelta(seconds=second)  # orden de cola estable
    with engine.begin() as connection:
        read_id, _ = leads.enqueue_tweet(connection, REF, key=key, now=created, per_day=50)
    return read_id


def get(engine: Engine, read_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        read = leads.get_read(connection, read_id)
    assert read is not None
    return read


def ready_world(engine: Engine) -> None:
    with engine.begin() as connection:
        seed_run(connection)
        seed_lead_policies(connection)


def tweet(
    text: str = "Mira https://www.youtube.com/@historia_uno", photos: tuple[str, ...] = (PHOTO,)
) -> Tweet:
    return Tweet("autor_x", TWEET_ID, text, photos)


def resolver() -> FakeResolver:
    found = FakeResolver(channels={UC_A: channel("a")})
    found.handles["@historia_uno"] = channel("a")
    return found


def test_switches_and_configuration() -> None:
    assert tick_leads(Settings(mode="live"), clock=lambda: LLM_NOW)["status"] == "disabled"
    assert (
        tick_leads(Settings(subniche_enabled=True), clock=lambda: LLM_NOW)["status"]
        == "synthetic_mode"
    )
    assert tick_leads(vision_settings(), clock=lambda: LLM_NOW)["status"] == "not_configured"


def test_idle_without_reads(isolated_engine: Engine) -> None:
    out = tick_leads(vision_settings(), isolated_engine, clock=lambda: LLM_NOW)
    assert (out["status"], out["processed"]) == ("idle", 0)


def test_a_tweet_becomes_candidates_with_text_and_image_mentions(isolated_engine: Engine) -> None:
    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    reader = FakeTweetReader(tweet(), photos={PHOTO: ImageData("image/png", PNG)})
    client = mentions_client([{"kind": "name", "value": "Batallas Olvidadas", "found_in": "image"}])
    out = tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver(),
        client=client,
        clock=lambda: LLM_NOW,
    )
    assert (out["processed"], out["ready"]) == (1, 1)
    read = get(isolated_engine, read_id)
    assert read["status"] == "ready" and read["photos_read"] == 1 and read["error_code"] is None
    assert [(c["value"], c["found_in"], c["resolution"]) for c in read["candidates"]] == [
        ("@historia_uno", "text", "resolved"),
        ("Batallas Olvidadas", "image", "name_only"),
    ]


def test_without_the_vision_model_the_text_links_still_work(isolated_engine: Engine) -> None:
    read_id = put_tweet(isolated_engine)
    reader = FakeTweetReader(tweet(photos=()))
    out = tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert out["ready"] == 1
    read = get(isolated_engine, read_id)
    assert read["error_code"] == "llm_disabled"  # aviso, no fallo
    assert [c["value"] for c in read["candidates"]] == ["@historia_uno"]


def test_an_unreadable_tweet_fails_with_its_code(isolated_engine: Engine) -> None:
    read_id = put_tweet(isolated_engine)
    out = tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(error="tweet_unavailable"),
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert out["failed"] == 1
    assert get(isolated_engine, read_id)["error_code"] == "tweet_unavailable"


def test_a_failed_photo_is_skipped_not_fatal(isolated_engine: Engine) -> None:
    read_id = put_tweet(isolated_engine)
    out = tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet()),
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert out["ready"] == 1 and get(isolated_engine, read_id)["photos_read"] == 0


def test_a_shared_image_is_read_and_its_bytes_are_purged(isolated_engine: Engine) -> None:
    ready_world(isolated_engine)
    with isolated_engine.begin() as connection:
        read_id, _ = leads.enqueue_image(
            connection, ImageData("image/png", PNG), key="clave-img-01", now=LLM_NOW, per_day=50
        )
    client = mentions_client([{"kind": "handle", "value": "@historia_uno", "found_in": "image"}])
    reader = FakeTweetReader()
    out = tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver(),
        client=client,
        clock=lambda: LLM_NOW,
    )
    assert out["ready"] == 1 and reader.reads == []
    read = get(isolated_engine, read_id)
    assert [c["channel_id"] for c in read["candidates"]] == [UC_A]
    with isolated_engine.connect() as connection:
        left = connection.execute(
            sa.select(reads.c.image_data).where(reads.c.id == read_id)
        ).scalar_one()
    assert left is None
    with isolated_engine.connect() as connection:
        assert leads.claim_next(connection, LLM_NOW) is None


def test_a_shared_image_without_the_model_fails_clearly(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        read_id, _ = leads.enqueue_image(
            connection, ImageData("image/png", PNG), key="clave-img-02", now=LLM_NOW, per_day=50
        )
    tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert get(isolated_engine, read_id)["error_code"] == "llm_disabled"


def test_a_shared_image_without_the_vision_configuration_has_its_own_code(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as connection:
        read_id, _ = leads.enqueue_image(
            connection, ImageData("image/png", PNG), key="clave-img-03", now=LLM_NOW, per_day=50
        )
    tick_leads(
        vision_settings(anthropic_vision_configuration=None),
        isolated_engine,
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert get(isolated_engine, read_id)["error_code"] == "vision_not_configured"


def test_name_searches_run_only_when_queued(isolated_engine: Engine) -> None:
    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    found = resolver()
    named = channel("b").model_copy(update={"title": "Batallas Olvidadas"})
    found.by_name["Batallas Olvidadas"] = [named]
    client = mentions_client([{"kind": "name", "value": "Batallas Olvidadas", "found_in": "image"}])
    tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        resolver=found,
        client=client,
        clock=lambda: LLM_NOW,
    )
    assert found.name_searches == []
    name = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    with isolated_engine.begin() as connection:
        leads.queue_names(connection, read_id, [UUID(name["id"])], LLM_NOW)
    out = tick_leads(vision_settings(), isolated_engine, resolver=found, clock=lambda: LLM_NOW)
    assert out["names"] == 1 and found.name_searches == ["Batallas Olvidadas"]
    after = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    assert (after["resolution"], after["channel_id"]) == ("resolved", named.id)


def test_stale_reads_are_abandoned_and_the_batch_is_respected(isolated_engine: Engine) -> None:
    ids = [put_tweet(isolated_engine, f"clave-lote-{n:02d}", n) for n in range(3)]
    reader = FakeTweetReader(tweet(text="sin canales", photos=()))
    out = tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver(),
        clock=lambda: LLM_NOW,
        batch=2,
    )
    assert out["processed"] == 2
    assert get(isolated_engine, ids[2])["status"] == "queued"
    with isolated_engine.begin() as connection:
        leads.claim_next(connection, LLM_NOW)
    later = LLM_NOW + timedelta(minutes=31)
    tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=reader,
        resolver=resolver(),
        clock=lambda: later,
    )
    assert get(isolated_engine, ids[2])["error_code"] == "abandoned"


def test_an_unexpected_exception_fails_that_read_and_continues(isolated_engine: Engine) -> None:
    first, second = (
        put_tweet(isolated_engine, "clave-boom-01", 0),
        put_tweet(isolated_engine, "clave-boom-02", 1),
    )

    class Exploding(FakeTweetReader):
        async def read(self, ref: TweetRef) -> Tweet:
            if not self.reads:
                self.reads.append(ref)
                raise RuntimeError("boom con detalle secreto")
            return tweet(text="nada", photos=())

    out = tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=Exploding(),
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    assert (out["ready"], out["failed"]) == (1, 1)
    assert get(isolated_engine, first)["error_code"] == "unexpected"
    assert get(isolated_engine, second)["status"] == "ready"


def test_database_error_is_reported_not_raised(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> int:
        raise OperationalError("select", {}, Exception("down"))

    monkeypatch.setattr(leads, "release_stale", broken)
    out = tick_leads(vision_settings(), isolated_engine, clock=lambda: LLM_NOW)
    assert (out["status"], out["error_code"]) == ("error", "database_unavailable")


def status_of(engine: Engine, read_id: UUID) -> tuple[str, str | None]:
    read = get(engine, read_id)
    return read["status"], read["error_code"]


def test_a_cancelled_read_is_failed_not_left_running(isolated_engine: Engine) -> None:
    import asyncio

    read_id = put_tweet(isolated_engine)

    class Cancelled(FakeTweetReader):
        async def read(self, ref: TweetRef) -> Tweet:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        tick_leads(
            vision_settings(),
            isolated_engine,
            tweet_reader=Cancelled(),
            resolver=resolver(),
            clock=lambda: LLM_NOW,
        )
    assert status_of(isolated_engine, read_id) == ("failed", "cancelled")


def test_a_failed_read_purges_its_image_bytes(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        read_id, _ = leads.enqueue_image(
            connection, ImageData("image/png", PNG), key="clave-img-03", now=LLM_NOW, per_day=50
        )
    tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        resolver=resolver(),
        clock=lambda: LLM_NOW,
    )
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(reads.c.image_data).where(reads.c.id == read_id)
            ).scalar_one()
            is None
        )


def test_an_unexpected_error_in_a_name_search_returns_the_name_to_name_only(
    isolated_engine: Engine,
) -> None:
    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    found = resolver()
    client = mentions_client([{"kind": "name", "value": "Batallas Olvidadas", "found_in": "text"}])
    tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        resolver=found,
        client=client,
        clock=lambda: LLM_NOW,
    )
    name = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    with isolated_engine.begin() as connection:
        leads.queue_names(connection, read_id, [UUID(name["id"])], LLM_NOW)

    class Exploding(FakeResolver):
        async def search_channels(self, name: str, limit: int = 5) -> list[Any]:
            raise RuntimeError("boom con detalle secreto")

    out = tick_leads(
        vision_settings(), isolated_engine, resolver=Exploding(), clock=lambda: LLM_NOW
    )
    assert out["names"] == 1
    after = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    assert after["resolution"] == "name_only"


def test_a_cancelled_name_search_is_returned_to_name_only(isolated_engine: Engine) -> None:
    import asyncio

    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    client = mentions_client([{"kind": "name", "value": "Batallas Olvidadas", "found_in": "text"}])
    tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        resolver=resolver(),
        client=client,
        clock=lambda: LLM_NOW,
    )
    name = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    with isolated_engine.begin() as connection:
        leads.queue_names(connection, read_id, [UUID(name["id"])], LLM_NOW)

    class Cancelled(FakeResolver):
        async def search_channels(self, name: str, limit: int = 5) -> list[Any]:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        tick_leads(vision_settings(), isolated_engine, resolver=Cancelled(), clock=lambda: LLM_NOW)
    after = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    assert after["resolution"] == "name_only"


def test_the_daily_search_cap_leaves_the_name_unresolved_without_spending(
    isolated_engine: Engine,
) -> None:
    from nicheradar.integrations.contracts import ProviderError

    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    client = mentions_client([{"kind": "name", "value": "Batallas Olvidadas", "found_in": "text"}])
    tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        resolver=resolver(),
        client=client,
        clock=lambda: LLM_NOW,
    )
    name = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    with isolated_engine.begin() as connection:
        leads.queue_names(connection, read_id, [UUID(name["id"])], LLM_NOW)

    class Capped(FakeResolver):
        async def search_channels(self, name: str, limit: int = 5) -> list[Any]:
            raise ProviderError("subniche_daily_search_cap", not_sent=True)

    out = tick_leads(vision_settings(), isolated_engine, resolver=Capped(), clock=lambda: LLM_NOW)
    assert out["names"] == 1
    after = next(c for c in get(isolated_engine, read_id)["candidates"] if c["kind"] == "name")
    assert after["resolution"] == "name_only"


def test_stale_queued_images_are_expired_by_the_tick(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        read_id, _ = leads.enqueue_image(
            connection,
            ImageData("image/png", PNG),
            key="clave-img-vieja",
            now=LLM_NOW - timedelta(hours=25),
            per_day=50,
        )
    tick_leads(vision_settings(), isolated_engine, resolver=resolver(), clock=lambda: LLM_NOW)
    assert get(isolated_engine, read_id)["error_code"] == "expired"
    with isolated_engine.connect() as connection:
        data = connection.execute(
            sa.select(reads.c.image_data).where(reads.c.id == read_id)
        ).scalar_one()
    assert data is None


def test_youtube_not_configured_fails_before_spending_the_model(isolated_engine: Engine) -> None:
    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    seen: list[Any] = []
    client = mentions_client(
        [{"kind": "handle", "value": "@historia_uno", "found_in": "image"}], seen
    )
    out = tick_leads(
        vision_settings(),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        client=client,
        clock=lambda: LLM_NOW,
    )
    assert out["failed"] == 1 and seen == []
    assert get(isolated_engine, read_id)["status"] == "failed"


def test_a_provider_error_while_resolving_stores_only_its_code(isolated_engine: Engine) -> None:
    from nicheradar.integrations.contracts import ProviderError

    read_id = put_tweet(isolated_engine)

    class Down(FakeResolver):
        async def channel_by_handle(self, handle: str) -> Any:
            raise ProviderError("youtube_quota_exceeded")

    out = tick_leads(
        vision_settings(anthropic_enabled=False),
        isolated_engine,
        tweet_reader=FakeTweetReader(tweet(photos=())),
        resolver=Down(),
        clock=lambda: LLM_NOW,
    )
    assert out["failed"] == 1
    assert get(isolated_engine, read_id)["error_code"] == "youtube_quota_exceeded"


def test_xapi_without_token_fails_without_spending_anything(isolated_engine: Engine) -> None:
    ready_world(isolated_engine)
    read_id = put_tweet(isolated_engine)
    seen: list[Any] = []
    found = resolver()
    out = tick_leads(
        vision_settings(tweet_reader="xapi"),
        isolated_engine,
        resolver=found,
        client=mentions_client([], seen),
        clock=lambda: LLM_NOW,
    )
    assert (out["processed"], out["ready"], out["failed"]) == (1, 0, 1)
    read = get(isolated_engine, read_id)
    assert read["status"] == "failed" and read["error_code"] == "reader_not_configured"
    assert seen == [] and found.search_calls == 0 and found.name_searches == []
    assert "xapi" not in str(out) and "token" not in str(out).lower()
