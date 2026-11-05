"""Cola de lecturas de tweets e imágenes: la API valida y encola, el worker las atiende.

Mismo patrón que `proposals.py`. El texto y la imagen son datos de terceros: `image_data` se borra
al terminar la lectura y `untrusted_text` al proponer, cerrar o a las 24 h de terminar.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nicheradar.integrations.contracts import Channel
from nicheradar.integrations.tweets import MAX_IMAGE_BYTES, ImageData, TweetRef, sniff_image_type
from nicheradar.repositories.schema import hypothesis_seed_channels as seeds
from nicheradar.repositories.schema import lead_candidates as cands
from nicheradar.repositories.schema import lead_read_requests as reads
from nicheradar.repositories.schema import niche_hypotheses as hypotheses
from nicheradar.repositories.schema import subniche_proposal_requests as proposal_requests
from nicheradar.subniche_discovery import proposals
from nicheradar.subniche_discovery.resolve import Candidate

MAX_CANDIDATES = 10
MAX_TEXT = 1000
MAX_ERROR_CODE = 80
_LIMIT_LOCK = 7_302_202  # serializa «contar + insertar» para que el tope no se rebase en carrera
_READ_PUBLIC = [c for c in reads.c if c.name not in ("idempotency_key", "image_data")]


class LeadRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _existing(conn: Connection, key: str) -> UUID | None:
    return conn.execute(
        sa.select(reads.c.id).where(reads.c.idempotency_key == key)
    ).scalar_one_or_none()


def expire_queued(conn: Connection, now: datetime, *, hours: int = 24) -> int:
    """Lecturas que nadie atendió en `hours`: fallan y sueltan los bytes de imagen."""
    result = conn.execute(
        sa.update(reads)
        .where(reads.c.status == "queued", reads.c.created_at < now - timedelta(hours=hours))
        .values(status="failed", error_code="expired", image_data=None, finished_at=now)
    )
    return result.rowcount


def _enqueue(
    conn: Connection, values: dict[str, Any], *, key: str, now: datetime, per_day: int
) -> tuple[UUID, bool]:
    if (found := _existing(conn, key)) is not None:
        return found, False  # una repetición idempotente no cuenta contra el tope
    conn.execute(sa.select(sa.func.pg_advisory_xact_lock(_LIMIT_LOCK)))
    if (found := _existing(conn, key)) is not None:  # otra petición ganó la carrera
        return found, False
    expire_queued(conn, now)
    recent = conn.execute(
        sa.select(sa.func.count())
        .select_from(reads)
        .where(reads.c.created_at > now - timedelta(hours=24))
    ).scalar_one()
    if recent >= per_day:
        raise LeadRejected("daily_limit")
    read_id = uuid4()
    conn.execute(
        pg_insert(reads)
        .values(id=read_id, idempotency_key=key, status="queued", created_at=now, **values)
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    stored = _existing(conn, key)
    assert stored is not None
    return stored, stored == read_id


def enqueue_tweet(
    conn: Connection, ref: TweetRef, *, key: str, now: datetime, per_day: int
) -> tuple[UUID, bool]:
    values = {"kind": "tweet", "tweet_id": ref.tweet_id, "tweet_author": ref.author}
    return _enqueue(conn, values, key=key, now=now, per_day=per_day)


def enqueue_image(
    conn: Connection, image: ImageData, *, key: str, now: datetime, per_day: int
) -> tuple[UUID, bool]:
    if len(image.data) > MAX_IMAGE_BYTES:
        raise LeadRejected("image_too_large")
    if sniff_image_type(image.data) != image.media_type:
        raise LeadRejected("invalid_image")
    values = {"kind": "image", "image_type": image.media_type, "image_data": image.data}
    return _enqueue(conn, values, key=key, now=now, per_day=per_day)


def claim_next(conn: Connection, now: datetime) -> dict[str, Any] | None:
    next_id = conn.execute(
        sa.select(reads.c.id)
        .where(reads.c.status == "queued")
        .order_by(reads.c.created_at, reads.c.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if next_id is None:
        return None
    kind = conn.execute(sa.select(reads.c.kind).where(reads.c.id == next_id)).scalar_one()
    row = conn.execute(
        sa.update(reads)
        .where(reads.c.id == next_id)
        .values(status="running", started_at=now, stage="text" if kind == "tweet" else "mentions")
        .returning(
            reads.c.id,
            reads.c.kind,
            reads.c.tweet_id,
            reads.c.tweet_author,
            reads.c.image_type,
            reads.c.image_data,
        )
    ).one()
    data = dict(row._mapping)
    if data["image_data"] is not None:
        data["image_data"] = bytes(data["image_data"])
    return data


def set_stage(conn: Connection, read_id: UUID, stage: str) -> None:
    conn.execute(
        sa.update(reads)
        .where(reads.c.id == read_id, reads.c.status == "running")
        .values(stage=stage)
    )


def release_stale(conn: Connection, now: datetime, *, minutes: int = 30) -> int:
    cutoff = now - timedelta(minutes=minutes)
    result = conn.execute(
        sa.update(reads)
        .where(reads.c.status == "running", reads.c.started_at < cutoff)
        .values(
            status="failed", error_code="abandoned", stage=None, image_data=None, finished_at=now
        )
    )
    conn.execute(
        sa.update(cands)
        .where(cands.c.resolution == "searching", cands.c.updated_at < cutoff)
        .values(resolution="name_only", updated_at=now)
    )
    return result.rowcount


def finish_ready(
    conn: Connection,
    read_id: UUID,
    *,
    author: str | None,
    text: str,
    candidates: Sequence[Candidate],
    photos_read: int,
    warning: str | None,
    now: datetime,
) -> bool:
    """Marca `ready` solo si la fila sigue `running`; devuelve si actualizó."""
    result = conn.execute(
        sa.update(reads)
        .where(reads.c.id == read_id, reads.c.status == "running")
        .values(
            status="ready",
            stage=None,
            tweet_author=author,
            untrusted_text=text[:MAX_TEXT] or None,
            photos_read=photos_read,
            error_code=warning[:MAX_ERROR_CODE] if warning else None,
            image_data=None,
            finished_at=now,
        )
    )
    if result.rowcount != 1:
        return False
    for position, item in enumerate(candidates[:MAX_CANDIDATES]):
        conn.execute(
            sa.insert(cands).values(
                id=uuid4(),
                read_id=read_id,
                position=position,
                kind=item.kind,
                value=item.value[:120],
                found_in=item.found_in,
                resolution=item.resolution,
                channel_id=item.channel_id,
                channel_title=item.channel_title,
                subscribers=item.subscribers,
                created_at=now,
                updated_at=now,
            )
        )
    return True


def finish_failed(conn: Connection, read_id: UUID, code: str, now: datetime) -> bool:
    """Marca `failed` solo si la fila sigue `running`; devuelve si actualizó."""
    values: dict[str, Any] = {
        "status": "failed",
        "error_code": code[:MAX_ERROR_CODE],
        "stage": None,
        "image_data": None,
        "finished_at": now,
    }
    result = conn.execute(
        sa.update(reads).where(reads.c.id == read_id, reads.c.status == "running").values(**values)
    )
    return result.rowcount == 1


def purge(conn: Connection, now: datetime, *, hours: int = 24) -> int:
    """Borra el texto de terceros de lecturas terminadas hace más de `hours`."""
    result = conn.execute(
        sa.update(reads)
        .where(
            reads.c.finished_at < now - timedelta(hours=hours), reads.c.untrusted_text.is_not(None)
        )
        .values(untrusted_text=None)
    )
    return result.rowcount


def get_read(conn: Connection, read_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(sa.select(*_READ_PUBLIC).where(reads.c.id == read_id)).first()
    if row is None:
        return None
    read = dict(row._mapping)
    rows = conn.execute(
        sa.select(
            cands.c.id,
            cands.c.kind,
            cands.c.value,
            cands.c.found_in,
            cands.c.resolution,
            cands.c.channel_id,
            cands.c.channel_title,
            cands.c.subscribers,
            proposal_requests.c.id.label("proposal_id"),
            proposal_requests.c.status.label("proposal_status"),
        )
        .select_from(
            cands.outerjoin(
                proposal_requests, proposal_requests.c.id == cands.c.proposal_request_id
            )
        )
        .where(cands.c.read_id == read_id)
        .order_by(cands.c.position)
    )
    items: list[dict[str, Any]] = []
    for item in rows:
        data = dict(item._mapping)
        proposal_id, proposal_status = data.pop("proposal_id"), data.pop("proposal_status")
        data["id"] = str(data["id"])
        data["proposal"] = (
            {"id": str(proposal_id), "status": proposal_status} if proposal_id is not None else None
        )
        items.append(data)
    read["candidates"] = items
    return read


def _read_status(conn: Connection, read_id: UUID) -> str:
    row = conn.execute(
        sa.select(reads.c.status, reads.c.closed_at).where(reads.c.id == read_id)
    ).first()
    if row is None or row.status != "ready" or row.closed_at is not None:
        raise LeadRejected("not_ready")
    return str(row.status)


def queue_names(
    conn: Connection, read_id: UUID, candidate_ids: Sequence[UUID], now: datetime
) -> int:
    """Pide la búsqueda por nombre (100 unidades) de candidatos `name_only`: nunca se hace sola."""
    _read_status(conn, read_id)
    ids = list(dict.fromkeys(candidate_ids))
    if not ids or len(ids) > MAX_CANDIDATES:
        raise LeadRejected("invalid_candidates")
    valid = (
        conn.execute(
            sa.select(cands.c.id).where(
                cands.c.read_id == read_id, cands.c.id.in_(ids), cands.c.resolution == "name_only"
            )
        )
        .scalars()
        .all()
    )
    if len(valid) != len(ids):
        raise LeadRejected("invalid_candidates")
    result = conn.execute(
        sa.update(cands)
        .where(cands.c.id.in_(ids), cands.c.resolution == "name_only")
        .values(resolution="name_queued", updated_at=now)
    )
    return result.rowcount


def claim_name_search(conn: Connection, now: datetime) -> dict[str, Any] | None:
    next_id = conn.execute(
        sa.select(cands.c.id)
        .select_from(cands.join(reads, reads.c.id == cands.c.read_id))
        .where(cands.c.resolution == "name_queued", reads.c.closed_at.is_(None))
        .order_by(cands.c.updated_at, cands.c.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=cands)
    ).scalar_one_or_none()
    if next_id is None:
        return None
    row = conn.execute(
        sa.update(cands)
        .where(cands.c.id == next_id)
        .values(resolution="searching", updated_at=now)
        .returning(cands.c.id, cands.c.read_id, cands.c.value)
    ).one()
    return dict(row._mapping)


def finish_name_search(
    conn: Connection, candidate_id: UUID, resolution: str, channel: Channel | None, now: datetime
) -> None:
    """Fija el resultado solo si el candidato sigue `searching`."""
    conn.execute(
        sa.update(cands)
        .where(cands.c.id == candidate_id, cands.c.resolution == "searching")
        .values(
            resolution=resolution,
            channel_id=channel.id if channel else None,
            channel_title=channel.title[:120] if channel else None,
            subscribers=channel.subscribers if channel else None,
            updated_at=now,
        )
    )


def _is_seed(conn: Connection, channel_id: str) -> bool:
    return (
        conn.execute(
            sa.select(sa.literal(1))
            .select_from(seeds.join(hypotheses, hypotheses.c.id == seeds.c.hypothesis_id))
            .where(seeds.c.channel_id == channel_id, hypotheses.c.status != "archived")
            .limit(1)
        ).first()
        is not None
    )


def propose(
    conn: Connection,
    read_id: UUID,
    candidate_ids: Sequence[UUID],
    *,
    now: datetime,
    per_day: int,
) -> list[dict[str, Any]]:
    """Una propuesta por canal marcado; idempotente por `lead:{lectura}:{candidato}`."""
    _read_status(conn, read_id)
    ids = list(dict.fromkeys(candidate_ids))
    if not ids or len(ids) > MAX_CANDIDATES:
        raise LeadRejected("invalid_candidates")
    rows = {
        row.id: row
        for row in conn.execute(
            sa.select(
                cands.c.id,
                cands.c.resolution,
                cands.c.channel_id,
                cands.c.proposal_request_id,
            ).where(cands.c.read_id == read_id, cands.c.id.in_(ids))
        )
    }
    if len(rows) != len(ids):
        raise LeadRejected("invalid_candidates")
    read = conn.execute(
        sa.select(reads.c.tweet_author, reads.c.tweet_id).where(reads.c.id == read_id)
    ).one()
    out: list[dict[str, Any]] = []
    for candidate_id in ids:
        row = rows[candidate_id]
        item: dict[str, Any] = {"candidate_id": str(candidate_id), "proposal_id": None}
        if row.proposal_request_id is not None:  # doble toque, o la propuesta ya avanzó
            out.append(item | {"outcome": "queued", "proposal_id": str(row.proposal_request_id)})
        elif row.channel_id is None or row.resolution not in ("resolved", "ambiguous"):
            out.append(item | {"outcome": "not_resolved"})
        elif _is_seed(conn, row.channel_id):
            out.append(item | {"outcome": "duplicate"})
        else:
            try:
                with conn.begin_nested():
                    proposal_id, _ = proposals.enqueue(
                        conn,
                        row.channel_id,
                        manual=None,
                        origin="lead",
                        key=f"lead:{read_id}:{candidate_id}",
                        now=now,
                        per_day=per_day,
                        lead_author=read.tweet_author,
                        lead_tweet_id=read.tweet_id,
                    )
                    conn.execute(
                        sa.update(cands)
                        .where(cands.c.id == candidate_id)
                        .values(proposal_request_id=proposal_id, updated_at=now)
                    )
            except proposals.ProposalRejected as error:
                out.append(item | {"outcome": error.code})
            else:
                out.append(item | {"outcome": "queued", "proposal_id": str(proposal_id)})
    conn.execute(sa.update(reads).where(reads.c.id == read_id).values(untrusted_text=None))
    return out


def close(conn: Connection, read_id: UUID, now: datetime) -> bool:
    result = conn.execute(
        sa.update(reads).where(reads.c.id == read_id).values(closed_at=now, untrusted_text=None)
    )
    return result.rowcount == 1
