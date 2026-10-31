# tests/test_subniche_measure.py
import asyncio
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Channel, ProviderError, Video
from nicheradar.repositories import schema
from nicheradar.repositories.core import insert_record
from nicheradar.subniche_discovery.measure import measure_hypothesis
from nicheradar.subniche_discovery.store import approve, create_proposed, get_hypothesis
from tests.subniche_samples import NOW, FakeReader, channel, draft, make_run, video

A, B, C = "a", "b", "c"


def settings(**over: Any) -> Settings:
    return Settings(
        mode="live", subniche_search_pages=2, subniche_channels_per_hypothesis=2, **over
    )


def prepare(engine: Engine, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    with engine.begin() as connection:
        run_id, _, _ = make_run(connection)
        create_proposed(connection, draft(**kwargs), NOW)
        approve(connection, "history_revenge", NOW)
        return run_id, get_hypothesis(connection, "history_revenge")


def scripted_reader() -> FakeReader:
    pages = {
        "history revenge": [
            [video(1, channel_letter=A), video(2, channel_letter=B), video(3, channel_letter=A)],
            [video(4, channel_letter=C)],
        ]
    }
    uploads = {
        "UC" + A * 22: tuple(
            video(i, channel_letter=A, days_ago=3 + i * 7, views=30_000) for i in range(8)
        ),
        "UC" + B * 22: tuple(
            video(i, channel_letter=B, days_ago=3 + i * 7, views=3_000) for i in range(8)
        ),
        "UC" + C * 22: tuple(
            video(i, channel_letter=C, days_ago=3 + i * 7, views=1_000) for i in range(8)
        ),
    }
    channels = {
        "UC" + A * 22: channel(A, subscribers=2_000),
        "UC" + B * 22: channel(B, subscribers=400_000),
        "UC" + C * 22: channel(C, subscribers=50_000),
    }
    return FakeReader(pages=pages, channels=channels, uploads=uploads)


@pytest.mark.postgres
def test_measure_picks_top_channels_by_appearances_and_stores_the_profile(
    isolated_engine: Engine,
) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    result = asyncio.run(
        measure_hypothesis(isolated_engine, scripted_reader(), hypothesis, run_id, settings(), NOW)
    )
    assert result["channels_seen"] == 2  # channel A (2 hits) and B (1 hit, first rank 2); C is cut
    with isolated_engine.connect() as connection:
        hits = connection.execute(sa.select(schema.hypothesis_channel_hits)).mappings().all()
        assert {hit["channel_id"] for hit in hits} == {"UC" + A * 22, "UC" + B * 22}
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] == NOW
        profile = connection.execute(sa.select(schema.hypothesis_snapshots.c.profile)).scalar_one()
    assert profile["estimate"] is True and profile["rpm_source"] is None
    traction = [hit for hit in hits if hit["traction"]]
    assert [hit["channel_id"] for hit in traction] == ["UC" + A * 22]  # small channel, ratio 15


@pytest.mark.postgres
def test_seed_channels_are_always_measured_even_if_search_misses_them(
    isolated_engine: Engine,
) -> None:
    seed = "UC" + C * 22
    run_id, hypothesis = prepare(isolated_engine, seeds=(seed,))
    asyncio.run(
        measure_hypothesis(isolated_engine, scripted_reader(), hypothesis, run_id, settings(), NOW)
    )
    with isolated_engine.connect() as connection:
        rows = connection.execute(
            sa.select(
                schema.hypothesis_channel_hits.c.channel_id,
                schema.hypothesis_channel_hits.c.source,
            )
        ).all()
    sources = {row.channel_id: row.source for row in rows}
    assert sources[seed] == "seed"


@pytest.mark.postgres
def test_empty_search_is_sin_senal_not_an_error(isolated_engine: Engine) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    result = asyncio.run(
        measure_hypothesis(isolated_engine, FakeReader(), hypothesis, run_id, settings(), NOW)
    )
    assert result["signal"] == "sin_senal" and result["channels_seen"] == 0
    with isolated_engine.connect() as connection:
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] == NOW


@pytest.mark.postgres
def test_deleted_channel_and_channel_without_uploads_do_not_break_the_run(
    isolated_engine: Engine,
) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    reader = scripted_reader()
    reader.uploads.pop("UC" + A * 22)  # no uploads for A
    del reader._channels["UC" + B * 22]  # B was deleted between search and lookup
    result = asyncio.run(
        measure_hypothesis(isolated_engine, reader, hypothesis, run_id, settings(), NOW)
    )
    assert result["channels_seen"] == 1


@pytest.mark.postgres
def test_a_provider_stop_writes_nothing_and_leaves_the_hypothesis_unmeasured(
    isolated_engine: Engine,
) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    reader = scripted_reader()
    reader.fail_search_after = 1  # first page ok, second page hits the daily cap
    result = asyncio.run(
        measure_hypothesis(isolated_engine, reader, hypothesis, run_id, settings(), NOW)
    )
    assert result == {
        "slug": "history_revenge",
        "stopped_reason": "subniche_daily_search_cap",
        "partial": True,
    }
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(schema.hypothesis_snapshots)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(schema.hypothesis_channel_hits)
            ).scalar_one()
            == 0
        )
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] is None


@pytest.mark.postgres
def test_parent_niche_rpm_produces_an_income_range_marked_inherited(
    isolated_engine: Engine,
) -> None:
    label = "test_subniche_measure_long_rpm"
    with isolated_engine.begin() as connection:
        insert_record(
            connection,
            "advertising_benchmarks",
            {
                "niche_label": label,
                "niche_description": "fixture",
                "format": "long",
                "rate_low": Decimal("3.5"),
                "rate_high": Decimal("8"),
                "source": "fixture",
                "assumptions": "fixture",
                "created_at": NOW,
            },
        )
    run_id, hypothesis = prepare(isolated_engine, parent=label)
    asyncio.run(
        measure_hypothesis(isolated_engine, scripted_reader(), hypothesis, run_id, settings(), NOW)
    )
    with isolated_engine.connect() as connection:
        profile = connection.execute(sa.select(schema.hypothesis_snapshots.c.profile)).scalar_one()
        hits = connection.execute(sa.select(schema.hypothesis_channel_hits)).mappings().all()
    assert profile["rpm_source"] == f"inherited:{label}"
    income = {hit["channel_id"]: (hit["income_low"], hit["income_high"]) for hit in hits}
    # A: 8 long videos x 30_000 views = 240_000 in 90 days -> 80_000/month -> 80 x 3.5 / 80 x 8
    assert income["UC" + A * 22] == (Decimal("280.00"), Decimal("640.00"))
    # B: 8 x 3_000 = 24_000 -> 8_000/month -> 8 x 3.5 / 8 x 8
    assert income["UC" + B * 22] == (Decimal("28.00"), Decimal("64.00"))


def measured_channel_ids(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(sa.select(schema.hypothesis_channel_hits.c.channel_id)).all()
    return {row.channel_id for row in rows}


def run_with_pages(engine: Engine, pages: list[list[Video]]) -> set[str]:
    run_id, hypothesis = prepare(engine)
    reader = scripted_reader()
    reader.pages = {"history revenge": pages}
    asyncio.run(measure_hypothesis(engine, reader, hypothesis, run_id, settings(), NOW))
    return measured_channel_ids(engine)


@pytest.mark.postgres
def test_channels_are_ranked_by_appearances_before_first_rank(isolated_engine: Engine) -> None:
    # A: 2 hits (rank 1), B: 1 hit (rank 2), C: 2 hits (ranks 4-5) -> C beats B on appearances
    chosen = run_with_pages(
        isolated_engine,
        [
            [video(1, channel_letter=A), video(2, channel_letter=B), video(3, channel_letter=A)],
            [video(4, channel_letter=C), video(5, channel_letter=C)],
        ],
    )
    assert chosen == {"UC" + A * 22, "UC" + C * 22}


@pytest.mark.postgres
def test_equal_appearances_are_decided_by_the_earlier_first_rank(isolated_engine: Engine) -> None:
    # A: 2 hits; B and C tie with 1 hit each, B appeared first -> B takes the last slot
    chosen = run_with_pages(
        isolated_engine,
        [
            [video(1, channel_letter=B), video(2, channel_letter=A), video(3, channel_letter=A)],
            [video(4, channel_letter=C)],
        ],
    )
    assert chosen == {"UC" + A * 22, "UC" + B * 22}


class FailingReader(FakeReader):
    """FakeReader that raises on the Nth call of `recent_videos` / `channels` (1-based)."""

    def __init__(
        self,
        base: FakeReader,
        *,
        code: str,
        recent_videos_on: int | None = None,
        channels_on: int | None = None,
        channels_when_batch: bool = False,
    ) -> None:
        super().__init__(base.pages, base._channels, base.uploads)
        self.code = code
        self.recent_videos_on = recent_videos_on
        self.channels_on = channels_on
        self.channels_when_batch = channels_when_batch
        self.recent_videos_calls = 0
        self.channels_calls = 0

    async def recent_videos(self, channel: Channel, limit: int) -> tuple[Video, ...]:
        self.recent_videos_calls += 1
        if self.recent_videos_calls == self.recent_videos_on:
            raise ProviderError(self.code, not_sent=True)
        return await super().recent_videos(channel, limit)

    async def channels(self, ids: list[str]) -> dict[str, Channel]:
        self.channels_calls += 1
        if self.channels_calls == self.channels_on or (self.channels_when_batch and len(ids) > 1):
            raise ProviderError(self.code, not_sent=True)
        return await super().channels(ids)


def assert_nothing_written(engine: Engine) -> None:
    with engine.connect() as connection:
        for table in (
            schema.discovery_channel_snapshots,
            schema.hypothesis_channel_hits,
            schema.hypothesis_snapshots,
        ):
            count = sa.select(sa.func.count()).select_from(table)
            assert connection.execute(count).scalar_one() == 0
        assert get_hypothesis(connection, "history_revenge")["last_measured_at"] is None


@pytest.mark.postgres
def test_a_stop_while_reading_the_second_channel_writes_nothing(isolated_engine: Engine) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    reader = FailingReader(scripted_reader(), code="quota_exhausted", recent_videos_on=2)
    result = asyncio.run(
        measure_hypothesis(isolated_engine, reader, hypothesis, run_id, settings(), NOW)
    )
    assert reader.recent_videos_calls == 2  # the first channel was already processed
    assert result == {
        "slug": "history_revenge",
        "stopped_reason": "quota_exhausted",
        "partial": True,
    }
    assert_nothing_written(isolated_engine)


@pytest.mark.postgres
def test_a_stop_while_looking_up_channels_writes_nothing(isolated_engine: Engine) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    reader = FailingReader(scripted_reader(), code="quota_exhausted", channels_on=1)
    result = asyncio.run(
        measure_hypothesis(isolated_engine, reader, hypothesis, run_id, settings(), NOW)
    )
    assert result == {
        "slug": "history_revenge",
        "stopped_reason": "quota_exhausted",
        "partial": True,
    }
    assert_nothing_written(isolated_engine)


@pytest.mark.postgres
def test_a_failed_channel_batch_is_retried_one_channel_at_a_time(isolated_engine: Engine) -> None:
    run_id, hypothesis = prepare(isolated_engine)
    reader = FailingReader(
        scripted_reader(), code="provider_response_failed", channels_when_batch=True
    )
    result = asyncio.run(
        measure_hypothesis(isolated_engine, reader, hypothesis, run_id, settings(), NOW)
    )
    assert reader.channels_calls == 3  # the failed batch plus one call per channel
    assert result["channels_seen"] == 2
    assert measured_channel_ids(isolated_engine) == {"UC" + A * 22, "UC" + B * 22}
