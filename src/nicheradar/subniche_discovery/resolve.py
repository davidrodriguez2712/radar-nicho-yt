"""Menciones -> canales de YouTube con las búsquedas baratas; un nombre nunca se busca solo."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from nicheradar.integrations.contracts import Channel, Video
from nicheradar.subniche_discovery.mentions import Mention


class ChannelResolver(Protocol):
    async def channels(self, ids: list[str]) -> dict[str, Channel]: ...

    async def channel_by_handle(self, handle: str) -> Channel | None: ...

    async def video(self, video_id: str) -> Video | None: ...

    async def search_channels(self, name: str, limit: int = 5) -> list[Channel]: ...


@dataclass(frozen=True)
class Candidate:
    kind: str
    value: str
    found_in: str
    resolution: str
    channel_id: str | None = None
    channel_title: str | None = None
    subscribers: int | None = None


def _found(mention: Mention, channel: Channel | None) -> Candidate:
    if channel is None:
        return Candidate(mention.kind, mention.value, mention.found_in, "not_found")
    return Candidate(
        mention.kind,
        mention.value,
        mention.found_in,
        "resolved",
        channel.id,
        channel.title[:120],
        channel.subscribers,
    )


async def resolve_mentions(
    mentions: Sequence[Mention], resolver: ChannelResolver
) -> list[Candidate]:
    ids = [m.value for m in mentions if m.kind == "channel_id"]
    by_id = await resolver.channels(ids) if ids else {}
    out: list[Candidate] = []
    for mention in mentions:
        if mention.kind == "name":
            candidate = Candidate("name", mention.value, mention.found_in, "name_only")
        elif mention.kind == "channel_id":
            candidate = _found(mention, by_id.get(mention.value))
        elif mention.kind == "handle":
            candidate = _found(mention, await resolver.channel_by_handle(mention.value))
        else:
            video = await resolver.video(mention.value)
            owner = (
                (await resolver.channels([video.channel_id])).get(video.channel_id)
                if video
                else None
            )
            candidate = _found(mention, owner)
        twin = next(
            (
                i
                for i, c in enumerate(out)
                if candidate.channel_id and c.channel_id == candidate.channel_id
            ),
            None,
        )
        if twin is None:
            out.append(candidate)
        elif out[twin].found_in != candidate.found_in:
            out[twin] = replace(out[twin], found_in="both")
    return out


def pick_by_name(name: str, channels: Sequence[Channel]) -> tuple[str, Channel | None]:
    wanted = " ".join(name.casefold().split())
    exact = [c for c in channels if " ".join(c.title.casefold().split()) == wanted]
    if len(exact) == 1:
        return "resolved", exact[0]
    if channels:
        return "ambiguous", channels[0]
    return "not_found", None
