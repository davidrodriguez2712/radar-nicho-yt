import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.integrations.tweets import ImageData, TweetRef
from nicheradar.repositories.schema import lead_read_requests as reads
from nicheradar.subniche_discovery import leads, proposals
from nicheradar.subniche_discovery.mentions import Mention
from nicheradar.subniche_discovery.resolve import Candidate, pick_by_name, resolve_mentions
from nicheradar.subniche_discovery.store import create_proposed
from tests.lead_samples import PNG, TWEET_ID, FakeResolver
from tests.subniche_samples import NOW, channel, draft, video

REF = TweetRef("autor_x", TWEET_ID)
UC_A, UC_B = "UC" + "a" * 22, "UC" + "b" * 22


def test_resolution_uses_cheap_lookups_and_never_searches_names() -> None:
    resolver = FakeResolver(channels={UC_A: channel("a"), UC_B: channel("b")})
    resolver.handles["@historia_uno"] = channel("a")
    resolver.videos_by_id["dQw4w9WgXcQ"] = video(1, channel_letter="b")
    mentions = [
        Mention("handle", "@historia_uno", "image"),
        Mention("channel_id", UC_A, "text"),  # mismo canal que el handle: se funde
        Mention("video", "dQw4w9WgXcQ", "text"),
        Mention("name", "Batallas Olvidadas", "text"),
        Mention("handle", "@no_existe_123", "image"),
    ]
    found = asyncio.run(resolve_mentions(mentions, resolver))
    assert [(c.value, c.resolution, c.channel_id, c.found_in) for c in found] == [
        ("@historia_uno", "resolved", UC_A, "both"),
        ("dQw4w9WgXcQ", "resolved", UC_B, "text"),
        ("Batallas Olvidadas", "name_only", None, "text"),
        ("@no_existe_123", "not_found", None, "image"),
    ]
    assert resolver.name_searches == [] and resolver.search_calls == 0


def test_pick_by_name_is_exact_or_ambiguous() -> None:
    exact = channel("a").model_copy(update={"title": "Batallas Olvidadas"})
    other = channel("b").model_copy(update={"title": "Batallas Olvidadas TV"})
    assert pick_by_name("batallas  olvidadas", [other, exact]) == ("resolved", exact)
    assert pick_by_name("Batallas Olvidadas", [other]) == ("ambiguous", other)
    assert pick_by_name("Batallas Olvidadas", []) == ("not_found", None)


@pytest.mark.postgres
def test_enqueue_is_idempotent_and_capped_per_day(db: Connection) -> None:
    first, created = leads.enqueue_tweet(db, REF, key="clave-lectura-01", now=NOW, per_day=2)
    again, created_again = leads.enqueue_tweet(db, REF, key="clave-lectura-01", now=NOW, per_day=2)
    assert created and not created_again and first == again
    leads.enqueue_image(db, ImageData("image/png", PNG), key="clave-lectura-02", now=NOW, per_day=2)
    with pytest.raises(leads.LeadRejected) as caught:
        leads.enqueue_tweet(db, REF, key="clave-lectura-03", now=NOW, per_day=2)
    assert caught.value.code == "daily_limit"
    replay, _ = leads.enqueue_tweet(db, REF, key="clave-lectura-01", now=NOW, per_day=2)
    assert replay == first  # la repetición no cuenta contra el tope
    later, _ = leads.enqueue_tweet(
        db, REF, key="clave-lectura-04", now=NOW + timedelta(hours=25), per_day=2
    )
    assert later != first


@pytest.mark.postgres
def test_enqueue_image_refuses_bad_bytes(db: Connection) -> None:
    for image in (
        ImageData("image/png", b"GIF89a" + b"\x00" * 10),
        ImageData("image/jpeg", PNG),
        ImageData("image/png", PNG + b"\x00" * 5_242_880),
    ):
        with pytest.raises(leads.LeadRejected) as caught:
            leads.enqueue_image(db, image, key=f"clave-{uuid4().hex}", now=NOW, per_day=50)
        assert caught.value.code in ("invalid_image", "image_too_large")


def read_of(db: Connection, read_id: UUID) -> dict[str, Any]:
    read = leads.get_read(db, read_id)
    assert read is not None
    return read


def ready_read(db: Connection, candidates: list[Candidate]) -> UUID:
    read_id, _ = leads.enqueue_tweet(db, REF, key=f"clave-{uuid4().hex}", now=NOW, per_day=50)
    assert leads.claim_next(db, NOW) is not None
    assert leads.finish_ready(
        db,
        read_id,
        author="autor_x",
        text="Texto <b>hostil</b>",
        candidates=candidates,
        photos_read=1,
        warning=None,
        now=NOW,
    )
    return read_id


RESOLVED = Candidate("handle", "@historia_uno", "image", "resolved", UC_A, "Historia Uno", 38000)
NAME = Candidate("name", "Batallas Olvidadas", "text", "name_only")


@pytest.mark.postgres
def test_claim_finish_and_read_back(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED, NAME])
    read = leads.get_read(db, read_id)
    assert read is not None and read["status"] == "ready"
    assert read["tweet_author"] == "autor_x" and read["untrusted_text"] == "Texto <b>hostil</b>"
    assert "idempotency_key" not in read and "image_data" not in read
    assert [c["value"] for c in read["candidates"]] == ["@historia_uno", "Batallas Olvidadas"]
    assert read["candidates"][0]["proposal"] is None
    assert leads.claim_next(db, NOW) is None  # nunca se reclama dos veces


@pytest.mark.postgres
def test_claim_next_skips_closed_reads(db: Connection) -> None:
    read_id, _ = leads.enqueue_tweet(db, REF, key="clave-cerrada-01", now=NOW, per_day=50)
    leads.close(db, read_id, NOW)
    assert leads.claim_next(db, NOW) is None
    status = db.execute(sa.select(reads.c.status).where(reads.c.id == read_id)).scalar_one()
    assert status == "queued"


@pytest.mark.postgres
def test_image_bytes_are_purged_when_the_read_finishes(db: Connection) -> None:
    read_id, _ = leads.enqueue_image(
        db, ImageData("image/png", PNG), key="clave-imagen-01", now=NOW, per_day=50
    )
    claimed = leads.claim_next(db, NOW)
    assert claimed is not None and claimed["image_data"] == PNG
    leads.finish_failed(db, read_id, "llm_disabled", NOW)
    stored = db.execute(
        sa.select(reads.c.image_data, reads.c.status).where(reads.c.id == read_id)
    ).one()
    assert tuple(stored) == (None, "failed")


@pytest.mark.postgres
def test_release_stale_and_purge(db: Connection) -> None:
    stale, _ = leads.enqueue_tweet(db, REF, key="clave-vieja-01", now=NOW, per_day=50)
    leads.claim_next(db, NOW)
    assert leads.release_stale(db, NOW + timedelta(minutes=31)) == 1
    assert read_of(db, stale)["error_code"] == "abandoned"
    done = ready_read(db, [RESOLVED])
    assert leads.purge(db, NOW + timedelta(hours=23)) == 0
    assert leads.purge(db, NOW + timedelta(hours=25)) >= 1
    assert read_of(db, done)["untrusted_text"] is None


@pytest.mark.postgres
def test_names_are_searched_only_on_request(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED, NAME])
    ids = {c["value"]: UUID(c["id"]) for c in read_of(db, read_id)["candidates"]}
    with pytest.raises(leads.LeadRejected) as caught:
        leads.queue_names(db, read_id, [ids["@historia_uno"]], NOW)
    assert caught.value.code == "invalid_candidates"
    assert leads.queue_names(db, read_id, [ids["Batallas Olvidadas"]], NOW) == 1
    claimed = leads.claim_name_search(db, NOW)
    assert claimed is not None and claimed["value"] == "Batallas Olvidadas"
    assert leads.claim_name_search(db, NOW) is None
    leads.finish_name_search(db, UUID(str(claimed["id"])), "resolved", channel("b"), NOW)
    after = {c["value"]: c for c in read_of(db, read_id)["candidates"]}
    assert after["Batallas Olvidadas"]["resolution"] == "resolved"
    assert after["Batallas Olvidadas"]["channel_id"] == UC_B


@pytest.mark.postgres
def test_propose_is_idempotent_reports_duplicates_and_purges_text(db: Connection) -> None:
    create_proposed(db, draft("ya_existe", queries=("ya existe",), seeds=(UC_B,)), NOW)
    dup = Candidate("channel_id", UC_B, "text", "resolved", UC_B, "Ya existe", 10)
    read_id = ready_read(db, [RESOLVED, NAME, dup])
    ids = [UUID(c["id"]) for c in read_of(db, read_id)["candidates"]]
    first = leads.propose(db, read_id, ids, now=NOW, per_day=100)
    assert [item["outcome"] for item in first] == ["queued", "not_resolved", "duplicate"]
    again = leads.propose(db, read_id, ids[:1], now=NOW, per_day=100)
    assert again[0]["proposal_id"] == first[0]["proposal_id"]  # doble toque: la misma propuesta
    proposal = proposals.get_request(db, UUID(first[0]["proposal_id"]))
    assert proposal is not None and proposal["origin"] == "lead"
    assert (proposal["input_text"], proposal["kind"]) == (UC_A, "channel")
    assert (proposal["lead_author"], proposal["lead_tweet_id"]) == ("autor_x", TWEET_ID)
    assert read_of(db, read_id)["untrusted_text"] is None


@pytest.mark.postgres
def test_propose_refuses_foreign_or_unready_candidates(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED])
    other = ready_read(db, [RESOLVED])
    foreign = UUID(read_of(db, other)["candidates"][0]["id"])
    with pytest.raises(leads.LeadRejected) as caught:
        leads.propose(db, read_id, [foreign], now=NOW, per_day=100)
    assert caught.value.code == "invalid_candidates"
    queued, _ = leads.enqueue_tweet(db, REF, key="clave-en-cola-1", now=NOW, per_day=50)
    with pytest.raises(leads.LeadRejected) as caught:
        leads.propose(db, queued, [foreign], now=NOW, per_day=100)
    assert caught.value.code == "not_ready"


@pytest.mark.postgres
def test_propose_reports_the_daily_proposal_limit_per_candidate(db: Connection) -> None:
    second = Candidate("channel_id", UC_B, "text", "resolved", UC_B, "B", 5)
    read_id = ready_read(db, [RESOLVED, second])
    ids = [UUID(c["id"]) for c in read_of(db, read_id)["candidates"]]
    out = leads.propose(db, read_id, ids, now=NOW, per_day=1)
    assert [item["outcome"] for item in out] == ["queued", "daily_limit"]


@pytest.mark.postgres
def test_close_purges_the_text(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED])
    assert leads.close(db, read_id, NOW)
    read = read_of(db, read_id)
    assert read["untrusted_text"] is None and read["closed_at"] is not None


@pytest.mark.postgres
def test_finishing_only_acts_on_a_running_read(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED])
    assert not leads.finish_failed(db, read_id, "unexpected", NOW)
    assert not leads.finish_ready(
        db, read_id, author=None, text="otro", candidates=[], photos_read=0, warning=None, now=NOW
    )
    read = leads.get_read(db, read_id)
    assert read is not None and read["status"] == "ready" and read["error_code"] is None
    assert len(read["candidates"]) == 1 and read["untrusted_text"] == "Texto <b>hostil</b>"
    queued, _ = leads.enqueue_tweet(db, REF, key="clave-sin-reclamar", now=NOW, per_day=50)
    assert not leads.finish_failed(db, queued, "unexpected", NOW)  # aún no está running


@pytest.mark.postgres
def test_finish_ready_caps_candidates_and_text(db: Connection) -> None:
    many = [Candidate("name", f"Canal numero {n}", "text", "name_only") for n in range(12)]
    read_id, _ = leads.enqueue_tweet(db, REF, key="clave-muchos-01", now=NOW, per_day=50)
    leads.claim_next(db, NOW)
    assert leads.finish_ready(
        db,
        read_id,
        author="autor_x",
        text="x" * 2000,
        candidates=many,
        photos_read=0,
        warning="llm_disabled",
        now=NOW,
    )
    read = leads.get_read(db, read_id)
    assert read is not None and len(read["candidates"]) == 10
    assert len(read["untrusted_text"]) == 1000 and read["error_code"] == "llm_disabled"


@pytest.mark.postgres
def test_release_stale_returns_searching_names_to_name_only(db: Connection) -> None:
    read_id = ready_read(db, [NAME])
    cid = UUID(read_of(db, read_id)["candidates"][0]["id"])
    leads.queue_names(db, read_id, [cid], NOW)
    assert leads.claim_name_search(db, NOW) is not None
    leads.release_stale(db, NOW + timedelta(minutes=10))
    assert read_of(db, read_id)["candidates"][0]["resolution"] == "searching"
    leads.release_stale(db, NOW + timedelta(minutes=31))
    assert read_of(db, read_id)["candidates"][0]["resolution"] == "name_only"


@pytest.mark.postgres
def test_finish_name_search_only_acts_on_a_searching_candidate(db: Connection) -> None:
    read_id = ready_read(db, [NAME])
    cid = UUID(read_of(db, read_id)["candidates"][0]["id"])
    leads.finish_name_search(db, cid, "resolved", channel("b"), NOW)
    assert read_of(db, read_id)["candidates"][0]["resolution"] == "name_only"


@pytest.mark.postgres
def test_propose_after_the_proposal_became_a_hypothesis_returns_the_same_proposal(
    db: Connection,
) -> None:
    read_id = ready_read(db, [RESOLVED])
    cid = UUID(read_of(db, read_id)["candidates"][0]["id"])
    first = leads.propose(db, read_id, [cid], now=NOW, per_day=100)
    create_proposed(db, draft("ya_listo", queries=("ya listo",), seeds=(UC_A,)), NOW)
    again = leads.propose(db, read_id, [cid], now=NOW, per_day=100)
    assert again[0]["outcome"] == "queued" and again[0]["proposal_id"] == first[0]["proposal_id"]


@pytest.mark.postgres
def test_propose_rejects_empty_or_oversized_selections(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED])
    for ids in ([], [uuid4() for _ in range(11)]):
        with pytest.raises(leads.LeadRejected) as caught:
            leads.propose(db, read_id, ids, now=NOW, per_day=100)
        assert caught.value.code == "invalid_candidates"


@pytest.mark.postgres
def test_close_of_an_unknown_read_is_false(db: Connection) -> None:
    assert leads.close(db, uuid4(), NOW) is False


@pytest.mark.postgres
@pytest.mark.parametrize(
    "extra",
    [
        {"lead_author": "x" * 16},
        {"lead_author": "a b"},
        {"lead_tweet_id": "12a"},
        {"lead_tweet_id": "1" * 21},
        {"lead_author": "autor_x"},
    ],
)
def test_proposal_lead_fields_are_validated(db: Connection, extra: dict[str, str]) -> None:
    origin = "manual" if extra.get("lead_author") == "autor_x" else "lead"
    with pytest.raises(proposals.ProposalRejected) as caught:
        proposals.enqueue(
            db,
            UC_A,
            manual=None,
            origin=origin,
            key=f"k-{uuid4().hex}",
            now=NOW,
            per_day=100,
            **extra,
        )
    assert caught.value.code == "invalid_input"
