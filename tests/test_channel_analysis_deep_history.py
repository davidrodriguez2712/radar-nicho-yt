import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import (
    Batch,
    Channel,
    Coverage,
    Operation,
    Provenance,
    Video,
)
from nicheradar.services.channel_analysis_deep_history import (
    estimate_deep_history_cost,
    fetch_deep_history,
)
from nicheradar.services.gateway import Gateway

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_estimate_cost_matches_real_example() -> None:
    # Same real channel used live this session: 184 videos -> 4 playlistItems.list pages
    # (ceil(184/50) = 4) + 4 videos.list batches = 8 real quota units.
    assert estimate_deep_history_cost(184) == 8


def test_estimate_cost_none_when_unknown() -> None:
    assert estimate_deep_history_cost(None) is None


class _SequentialUploadsGateway:
    """Fakes `Gateway.fetch` for deep-history pagination. Follows the style of
    `_FakeGateway`/`_MultiOpFakeGateway` in tests/test_channel_analysis_discovery.py, but
    neither of those supports stateful sequential pagination (several calls to the SAME
    operation returning successive pages chained by `coverage.next_page`) or serving
    `videos` -- this is a purpose-built double for that.

    UPLOADS calls are served strictly in order, one pre-built page per call (ignoring the
    actual `pageToken` value -- call order alone determines which page comes back, which is
    sufficient to exercise the real pagination loop without re-implementing YouTube's token
    scheme). VIDEOS calls are served by id lookup against a flat registry built from all
    pages, mirroring a real videos.list batch call.
    """

    def __init__(self, pages: list[tuple[Video, ...]]):
        self._pages = pages
        self._videos_by_id = {video.id: video for page in pages for video in page}
        self.uploads_calls = 0
        self.videos_calls = 0

    async def fetch(
        self, operation: Any, parameters: dict[str, Any], now: datetime
    ) -> tuple[Batch, str, datetime]:
        if operation == Operation.UPLOADS:
            index = self.uploads_calls
            self.uploads_calls += 1
            page = self._pages[index]
            next_page = str(index + 1) if index + 1 < len(self._pages) else None
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(
                        returned=len(page), selection_method="fake", next_page=next_page
                    ),
                    costs=(),
                    videos=page,
                ),
                "fake-request-id",
                now,
            )
        if operation == Operation.VIDEOS:
            self.videos_calls += 1
            ids = parameters["id"].split(",")
            found = tuple(self._videos_by_id[video_id] for video_id in ids)
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(returned=len(found), selection_method="fake"),
                    costs=(),
                    videos=found,
                ),
                "fake-request-id",
                now,
            )
        raise AssertionError(f"unexpected operation in deep-history fake: {operation}")


def _video(video_id: str, *, days_ago: int, views: int) -> Video:
    return Video(
        id=video_id,
        channel_id="UC1",
        title=video_id,
        published_at=NOW - timedelta(days=days_ago),
        views=views,
        format=VideoFormat.LONG,
    )


@pytest.fixture
def fake_gateway_with_history() -> Gateway:
    # Two pages (50 total videos) -> 2 UPLOADS + 1 VIDEOS (fits in one 50-id batch) = 3
    # quota units, comfortably within the default max_quota_units=100 cap. Every video has
    # views=100 except one unambiguous outlier (views=5000, 50x the median), so the breakout
    # threshold (3x median = 300) is cleared by exactly one video -- no borderline case.
    newest_page = tuple(_video(f"v{i}", days_ago=i + 1, views=100) for i in range(25))
    older_videos = [_video(f"v{25 + i}", days_ago=40 + i, views=100) for i in range(25)]
    older_videos[5] = _video("v30", days_ago=45, views=5000)  # the sole breakout
    return cast(Gateway, _SequentialUploadsGateway([newest_page, tuple(older_videos)]))


@pytest.fixture
def fake_gateway_with_huge_history() -> Gateway:
    # 50 pages of 50 videos each (2,500 videos) -- far more than max_quota_units=8 (which
    # only permits 7 UPLOADS calls, see assertion math in the test) can ever page through,
    # so the cap genuinely has to bite rather than the history just happening to end first.
    pages = [
        tuple(_video(f"p{p}-v{i}", days_ago=p * 50 + i + 1, views=100) for i in range(50))
        for p in range(50)
    ]
    return cast(Gateway, _SequentialUploadsGateway(pages))


def test_fetch_deep_history_finds_breakout_within_cap(fake_gateway_with_history: Gateway) -> None:
    channel = Channel(
        id="UC1",
        title="T",
        uploads_playlist="UU1",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        subscribers=1000,
    )
    result = asyncio.run(fetch_deep_history(fake_gateway_with_history, channel, NOW))
    assert result["status"] == "computed"
    assert result["days_to_first_breakout"] is not None
    assert result["quota_units_spent"] == 3


def test_fetch_deep_history_stops_at_cap(fake_gateway_with_huge_history: Gateway) -> None:
    channel = Channel(
        id="UC1",
        title="T",
        uploads_playlist="UU1",
        published_at=datetime(2020, 1, 1, tzinfo=UTC),
        subscribers=1_000_000,
    )
    result = asyncio.run(
        fetch_deep_history(fake_gateway_with_huge_history, channel, NOW, max_quota_units=8)
    )
    assert result["status"] == "partial_by_cap"
    assert result["quota_units_spent"] <= 8
    # Proves the cap actually bit: only a small fraction of the 50 available pages were
    # ever fetched.
    assert cast(_SequentialUploadsGateway, fake_gateway_with_huge_history).uploads_calls < 10


def test_fetch_deep_history_no_uploads_playlist(fake_gateway_with_history: Gateway) -> None:
    channel = Channel(id="UC1", title="T", uploads_playlist=None, published_at=NOW, subscribers=10)
    result = asyncio.run(fetch_deep_history(fake_gateway_with_history, channel, NOW))
    assert result == {
        "status": "no_breakout_found",
        "days_to_first_breakout": None,
        "quota_units_spent": 0,
    }
