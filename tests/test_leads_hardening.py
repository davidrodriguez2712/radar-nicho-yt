"""Retención de colas, concurrencia, lecturas cerradas y motivos de rechazo de las lecturas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.integrations.tweets import ImageData
from nicheradar.repositories.schema import lead_candidates as cands
from nicheradar.repositories.schema import lead_read_requests as reads
from nicheradar.subniche_discovery import leads
from nicheradar.subniche_discovery.resolve import Candidate
from tests.lead_samples import PNG, TWEET_ID
from tests.subniche_samples import NOW
from tests.test_leads_queue import NAME, REF, RESOLVED, UC_A, read_of, ready_read

pytestmark = pytest.mark.postgres


def queued_image(conn: Connection, key: str, now: Any = NOW) -> UUID:
    read_id, _ = leads.enqueue_image(
        conn, ImageData("image/png", PNG), key=key, now=now, per_day=50
    )
    return read_id


def stored(conn: Connection, read_id: UUID) -> tuple[Any, ...]:
    row = conn.execute(
        sa.select(reads.c.status, reads.c.error_code, reads.c.image_data).where(
            reads.c.id == read_id
        )
    ).one()
    return tuple(row)


def test_expire_queued_purges_old_images_only(db: Connection) -> None:
    old = queued_image(db, "clave-vieja-img")
    recent = queued_image(db, "clave-reciente-img", NOW + timedelta(hours=23))
    assert leads.expire_queued(db, NOW + timedelta(hours=25)) == 1
    assert stored(db, old) == ("failed", "expired", None)
    assert stored(db, recent)[0] == "queued" and stored(db, recent)[2] is not None


def test_enqueue_expires_old_queued_reads(db: Connection) -> None:
    old = queued_image(db, "clave-vieja-img")
    queued_image(db, "clave-nueva-img", NOW + timedelta(hours=25))
    assert stored(db, old) == ("failed", "expired", None)


def test_ready_read_leaves_no_image_bytes(db: Connection) -> None:
    read_id = queued_image(db, "clave-listo-img")
    assert leads.claim_next(db, NOW) is not None
    assert leads.finish_ready(
        db, read_id, author=None, text="", candidates=[], photos_read=0, warning=None, now=NOW
    )
    assert stored(db, read_id) == ("ready", None, None)


def test_concurrent_proposals_of_one_candidate_make_one_proposal(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as conn:
        read_id = ready_read(conn, [RESOLVED])
        cid = UUID(read_of(conn, read_id)["candidates"][0]["id"])

    def attempt(_: int) -> list[dict[str, Any]]:
        with isolated_engine.begin() as conn:
            return leads.propose(conn, read_id, [cid], now=NOW, per_day=100)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert len({r[0]["proposal_id"] for r in results}) == 1
    with isolated_engine.connect() as conn:
        n = conn.execute(sa.text("select count(*) from subniche_proposal_requests")).scalar_one()
    assert n == 1


def test_concurrent_enqueues_respect_the_daily_cap(isolated_engine: Engine) -> None:
    def attempt(n: int) -> str:
        try:
            with isolated_engine.begin() as conn:
                leads.enqueue_tweet(conn, REF, key=f"clave-conc-{n:02d}-xx", now=NOW, per_day=1)
        except leads.LeadRejected as error:
            return error.code
        return "created"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sorted(results) == ["created", "daily_limit", "daily_limit", "daily_limit"]
    with isolated_engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(reads)).scalar_one() == 1


def test_concurrent_enqueues_with_the_same_key_make_one_row(isolated_engine: Engine) -> None:
    def attempt(_: int) -> tuple[UUID, bool]:
        with isolated_engine.begin() as conn:
            return leads.enqueue_tweet(conn, REF, key="clave-misma-xx01", now=NOW, per_day=1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert len({r for r, _ in results}) == 1
    assert sorted(c for _, c in results) == [False, False, False, True]


def test_a_closed_read_cannot_be_proposed_or_searched(db: Connection) -> None:
    read_id = ready_read(db, [RESOLVED, NAME])
    ids = {c["value"]: UUID(c["id"]) for c in read_of(db, read_id)["candidates"]}
    leads.queue_names(db, read_id, [ids["Batallas Olvidadas"]], NOW)
    assert leads.close(db, read_id, NOW)
    for call in (
        lambda: leads.propose(db, read_id, [ids["@historia_uno"]], now=NOW, per_day=100),
        lambda: leads.queue_names(db, read_id, [ids["Batallas Olvidadas"]], NOW),
    ):
        with pytest.raises(leads.LeadRejected) as caught:
            call()
        assert caught.value.code == "not_ready"
    assert leads.claim_name_search(db, NOW) is None
    assert (
        db.execute(
            sa.select(cands.c.resolution).where(cands.c.id == ids["Batallas Olvidadas"])
        ).scalar_one()
        == "name_queued"
    )


def test_propose_keeps_the_reason_of_each_rejection(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nicheradar.subniche_discovery import proposals

    read_id = ready_read(db, [Candidate("channel_id", UC_A, "text", "resolved", UC_A, "A", 1)])
    cid = UUID(read_of(db, read_id)["candidates"][0]["id"])

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise proposals.ProposalRejected("invalid_input")

    monkeypatch.setattr(proposals, "enqueue", refuse)
    out = leads.propose(db, read_id, [cid], now=NOW, per_day=100)
    assert out[0]["outcome"] == "invalid_input" and out[0]["proposal_id"] is None


def test_unused_names() -> None:
    assert TWEET_ID and uuid4()
