# tests/test_subniche_inputs.py
import asyncio

import pytest

from nicheradar.subniche_discovery.inputs import parse_input, resolve_source
from tests.subniche_samples import FakeReader, channel, video

CHANNEL_ID = "UC" + "a" * 22


@pytest.mark.parametrize(
    "raw,kind,value",
    [
        ("History Revenge!", "query", "history revenge"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", "video", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
        (f"https://www.youtube.com/channel/{CHANNEL_ID}", "channel", CHANNEL_ID),
        ("https://www.youtube.com/@oceanversefrance", "channel", "@oceanversefrance"),
        ("@oceanversefrance", "channel", "@oceanversefrance"),
        (CHANNEL_ID, "channel", CHANNEL_ID),
        (
            "https://x.com/DailyYTNiches/status/2115826239810187511?a=b",
            "tweet",
            "2115826239810187511",
        ),
    ],
)
def test_parse_input_kinds(raw: str, kind: str, value: str) -> None:
    parsed = parse_input(raw)
    assert (parsed.kind, parsed.value) == (kind, value)


def test_too_short_query_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_input("ab")


def test_query_source_has_no_channel_and_marks_third_party_text() -> None:
    source = asyncio.run(resolve_source(parse_input("history revenge"), FakeReader()))
    assert source == {"kind": "query", "untrusted_query": "history revenge"}


def test_video_source_resolves_the_channel_and_recent_titles() -> None:
    reader = FakeReader(
        channels={CHANNEL_ID: channel("a")}, uploads={CHANNEL_ID: (video(1), video(2))}
    )
    reader.videos_by_id["dQw4w9WgXcQ"] = video(7)
    source = asyncio.run(resolve_source(parse_input("https://youtu.be/dQw4w9WgXcQ"), reader))
    assert source["kind"] == "video" and source["channel_id"] == CHANNEL_ID
    assert source["untrusted_recent_titles"] == ["Video 1", "Video 2"]
    assert source["untrusted_title"] == "Video 7"


def test_channel_by_handle_and_missing_resources() -> None:
    reader = FakeReader(uploads={CHANNEL_ID: (video(1),)})
    reader.handles["@oceanversefrance"] = channel("a")
    source = asyncio.run(resolve_source(parse_input("@oceanversefrance"), reader))
    assert source["channel_id"] == CHANNEL_ID
    with pytest.raises(LookupError):
        asyncio.run(resolve_source(parse_input("@missing_channel"), FakeReader()))
    with pytest.raises(LookupError):
        asyncio.run(resolve_source(parse_input("https://youtu.be/dQw4w9WgXcQ"), FakeReader()))
