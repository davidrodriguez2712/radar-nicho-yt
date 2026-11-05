# tests/test_subniche_proposals.py
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.repositories import schema
from nicheradar.subniche_discovery import proposals
from nicheradar.subniche_discovery.intake import ManualFields
from nicheradar.subniche_discovery.proposals import ProposalRejected
from tests.subniche_samples import NOW

pytestmark = pytest.mark.postgres

MANUAL = ManualFields(label="Historias de venganza", family="history", parent=None)


def put(
    conn: Connection, raw: str, key: str, now: datetime = NOW, **over: object
) -> tuple[UUID, bool]:
    options: dict[str, object] = {
        "manual": None,
        "origin": "manual",
        "key": key,
        "now": now,
        "per_day": 100,
    } | over
    return proposals.enqueue(conn, raw, **options)  # type: ignore[arg-type]


def rows(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sa.select(schema.subniche_proposal_requests)).mappings()]


def test_enqueue_each_kind_starts_queued(db: Connection) -> None:
    cases = [
        ("historias de venganza", "query", None),
        ("https://youtu.be/dQw4w9WgXcQ", "video", None),
        ("@canal_de_prueba", "channel", None),
        ("historias manuales", "query", MANUAL),
    ]
    for index, (raw, kind, manual) in enumerate(cases):
        request_id, created = put(db, raw, f"clave-{index:04d}-xx", manual=manual)
        assert created is True
        found = proposals.get_request(db, request_id)
        assert found is not None
        assert (found["status"], found["kind"]) == ("queued", kind)
    stored = {r["input_text"]: r for r in rows(db)}
    assert stored["historias manuales"]["manual"] == {
        "label": "Historias de venganza",
        "family": "history",
        "parent": None,
    }
    assert stored["@canal_de_prueba"]["manual"] is None


def test_origin_is_stored_and_validated(db: Connection) -> None:
    request_id, _ = put(db, "historias de venganza", "clave-origen-1", origin="catalog")
    assert proposals.get_request(db, request_id)["origin"] == "catalog"  # type: ignore[index]
    with pytest.raises(ProposalRejected) as caught:
        put(db, "otra consulta", "clave-origen-2", origin="bogus")
    assert caught.value.code == "invalid_input"


def test_same_key_returns_same_row(db: Connection) -> None:
    first, created_first = put(db, "historias de venganza", "clave-repetida")
    second, created_second = put(db, "historias de venganza", "clave-repetida")
    assert (created_first, created_second) == (True, False)
    assert first == second
    assert len(rows(db)) == 1


@pytest.mark.parametrize(
    "raw,code",
    [
        ("https://x.com/alguien/status/1234567890", "tweet_not_supported_yet"),
        ("ab", "invalid_input"),
        ("https://www.youtube.com/playlist?list=PL1234", "invalid_input"),
        ("mira http algo", "invalid_input"),
        ("hola\x00mundo", "invalid_input"),
        ("a" * 501, "invalid_input"),
        ("https://youtu.be/dQw4w9WgXcQ?" + "x" * 500, "invalid_input"),
    ],
)
def test_rejections(db: Connection, raw: str, code: str) -> None:
    with pytest.raises(ProposalRejected) as caught:
        put(db, raw, "clave-rechazo-1")
    assert caught.value.code == code
    assert rows(db) == []


def test_manual_with_non_query_is_rejected(db: Connection) -> None:
    with pytest.raises(ProposalRejected) as caught:
        put(db, "@canal_de_prueba", "clave-manual-1", manual=MANUAL)
    assert caught.value.code == "manual_needs_a_query"


def test_daily_limit_and_idempotent_repeat(db: Connection) -> None:
    first, _ = put(db, "primera consulta", "clave-tope-001", per_day=2)
    put(db, "segunda consulta", "clave-tope-002", per_day=2)
    with pytest.raises(ProposalRejected) as caught:
        put(db, "tercera consulta", "clave-tope-003", per_day=2)
    assert caught.value.code == "daily_limit"
    again, created = put(db, "primera consulta", "clave-tope-001", per_day=2)
    assert (again, created) == (first, False)
    assert len(rows(db)) == 2
    # Fuera de la ventana de 24 h ya no cuentan.
    later = NOW + timedelta(hours=25)
    _, created = put(db, "tercera consulta", "clave-tope-003", now=later, per_day=2)
    assert created is True


def test_claim_next_is_oldest_first_and_never_repeats(db: Connection) -> None:
    older, _ = put(db, "consulta antigua", "clave-claim-001", now=NOW)
    newer, _ = put(db, "consulta nueva", "clave-claim-002", now=NOW + timedelta(minutes=1))
    later = NOW + timedelta(minutes=5)
    first = proposals.claim_next(db, later)
    assert first is not None
    assert first["id"] == older
    assert (first["status"], first["started_at"]) == ("running", later)
    assert "idempotency_key" not in first
    second = proposals.claim_next(db, later)
    assert second is not None
    assert second["id"] == newer
    assert proposals.claim_next(db, later) is None


def test_release_stale_only_touches_old_running(db: Connection) -> None:
    old, _ = put(db, "consulta vieja", "clave-stale-001")
    recent, _ = put(db, "consulta reciente", "clave-stale-002", now=NOW + timedelta(minutes=1))
    queued, _ = put(db, "consulta en cola", "clave-stale-003", now=NOW + timedelta(hours=2))
    proposals.claim_next(db, NOW)  # old
    proposals.claim_next(db, NOW + timedelta(minutes=50))  # recent
    now = NOW + timedelta(minutes=60)
    assert proposals.release_stale(db, now, minutes=30) == 1
    stale = proposals.get_request(db, old)
    assert stale is not None
    assert (stale["status"], stale["error_code"], stale["finished_at"]) == (
        "failed",
        "abandoned",
        now,
    )
    assert proposals.get_request(db, recent)["status"] == "running"  # type: ignore[index]
    assert proposals.get_request(db, queued)["status"] == "queued"  # type: ignore[index]


def test_finish_ready_and_failed(db: Connection) -> None:
    ready, _ = put(db, "consulta lista", "clave-fin-0001")
    failed, _ = put(db, "consulta fallida", "clave-fin-0002")
    end = NOW + timedelta(minutes=1)
    proposals.claim_next(db, NOW)
    proposals.claim_next(db, NOW)
    assert proposals.finish_ready(db, ready, "consulta_lista", end) is True
    assert proposals.finish_failed(db, failed, "x" * 200, end) is True
    done = proposals.get_request(db, ready)
    broken = proposals.get_request(db, failed)
    assert done is not None and broken is not None
    assert (done["status"], done["hypothesis_slug"], done["finished_at"]) == (
        "ready",
        "consulta_lista",
        end,
    )
    assert (broken["status"], broken["error_code"], broken["finished_at"]) == (
        "failed",
        "x" * 80,
        end,
    )


def test_reads_hide_key_and_order_newest_first(db: Connection) -> None:
    ids = [
        put(
            db,
            f"consulta numero {word}",
            f"clave-lista-{index:03d}",
            now=NOW + timedelta(minutes=index),
        )[0]
        for index, word in enumerate(["uno", "dos", "tres"])
    ]
    listed = proposals.list_requests(db)
    assert [r["id"] for r in listed] == list(reversed(ids))
    assert all("idempotency_key" not in r for r in listed)
    assert len(proposals.list_requests(db, limit=2)) == 2
    assert proposals.get_request(db, UUID(int=0)) is None
    one = proposals.get_request(db, ids[0])
    assert one is not None and "idempotency_key" not in one


def test_hostile_text_is_stored_verbatim(db: Connection) -> None:
    hostile = [
        "<script>alert(1)</script>",
        "javascript:alert(1) ‮́\U0001f600 zalgo",
        "https://youtu.be/dQw4w9WgXcQ?" + "<b>&amp;</b>​" * 30,
    ]
    for index, raw in enumerate(hostile):
        assert len(raw) <= 500
        request_id, created = put(db, raw, f"clave-hostil-{index:03d}")
        assert created is True
        stored = proposals.get_request(db, request_id)
        assert stored is not None
        assert stored["input_text"] == raw.strip()


def test_concurrent_same_key_makes_one_row(isolated_engine: Engine) -> None:
    def attempt(_: int) -> tuple[UUID, bool]:
        with isolated_engine.begin() as conn:
            return put(conn, "historias de venganza", "clave-concurrente")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert len({request_id for request_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, False, False, True]
    with isolated_engine.connect() as conn:
        assert len(rows(conn)) == 1


def test_finish_only_acts_on_running_rows(db: Connection) -> None:
    queued, _ = put(db, "consulta en cola", "clave-run-0001")
    late, _ = put(db, "consulta tardia", "clave-run-0002", now=NOW + timedelta(seconds=1))
    assert proposals.finish_ready(db, queued, "x_slug", NOW) is False  # aun queued
    assert proposals.finish_failed(db, queued, "boom", NOW) is False
    assert proposals.get_request(db, queued)["status"] == "queued"  # type: ignore[index]
    proposals.claim_next(db, NOW)  # queued -> running
    proposals.claim_next(db, NOW)  # late -> running
    assert proposals.release_stale(db, NOW + timedelta(hours=2)) == 2
    assert proposals.finish_ready(db, late, "tarde", NOW + timedelta(hours=3)) is False
    assert proposals.finish_failed(db, late, "otro", NOW + timedelta(hours=3)) is False
    row = proposals.get_request(db, late)
    assert row is not None
    assert (row["status"], row["error_code"], row["hypothesis_slug"]) == (
        "failed",
        "abandoned",
        None,
    )


def test_finish_ready_trims_the_slug(db: Connection) -> None:
    request, _ = put(db, "consulta larga", "clave-slug-001")
    proposals.claim_next(db, NOW)
    assert proposals.finish_ready(db, request, "s" * 90, NOW) is True
    row = proposals.get_request(db, request)
    assert row is not None and row["hypothesis_slug"] == "s" * 60
