# src/nicheradar/pilots/tokens.py
"""Tokens por canal. Solo se guarda el SHA-256; el token en claro se entrega una vez.

Un token de canal solo abre las rutas de pilotos, y solo las de su propio canal.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, select, update

from nicheradar.repositories.schema import channel_tokens as tokens

PREFIX = "nrc_"
CHANNEL_RE = re.compile(r"^canal-[a-z0-9-]{1,40}$")
_DUMMY = hashlib.sha256(b"nicheradar-no-token").hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(
    connection: Connection, channel_id: str, label: str, now: datetime
) -> tuple[str, dict[str, Any]]:
    """Crea un token aleatorio de 32 bytes. Devuelve ``(token_en_claro, fila_sin_hash)``."""
    if not CHANNEL_RE.fullmatch(channel_id):
        raise ValueError("channel_id")
    token = PREFIX + secrets.token_urlsafe(32)
    row_id = uuid4()
    connection.execute(
        tokens.insert().values(
            id=row_id,
            channel_id=channel_id,
            token_hash=hash_token(token),
            label=label,
            created_at=now,
        )
    )
    return token, {"id": str(row_id), "channel_id": channel_id, "label": label, "created_at": now}


def authenticate(connection: Connection, bearer: str, now: datetime) -> str | None:
    """Devuelve el canal del token vigente, o ``None``. Registra el uso (``last_used_at``)."""
    digest = hash_token(bearer)
    row = connection.execute(
        select(tokens.c.id, tokens.c.channel_id, tokens.c.token_hash).where(
            tokens.c.token_hash == digest, tokens.c.revoked_at.is_(None)
        )
    ).one_or_none()
    stored = row.token_hash if row is not None else _DUMMY
    if not hmac.compare_digest(stored, digest) or row is None:
        return None
    connection.execute(update(tokens).where(tokens.c.id == row.id).values(last_used_at=now))
    return str(row.channel_id)


def revoke(connection: Connection, token_id: str, now: datetime) -> bool:
    result = connection.execute(
        update(tokens)
        .where(tokens.c.id == token_id, tokens.c.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return bool(result.rowcount)


def listing(connection: Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(
            tokens.c.id,
            tokens.c.channel_id,
            tokens.c.label,
            tokens.c.created_at,
            tokens.c.last_used_at,
            tokens.c.revoked_at,
        ).order_by(tokens.c.created_at.desc())
    ).mappings()
    return [{**row, "id": str(row["id"])} for row in rows]


def last_contact(connection: Connection, channel_id: str) -> datetime | None:
    row = connection.execute(
        select(tokens.c.last_used_at)
        .where(tokens.c.channel_id == channel_id, tokens.c.last_used_at.is_not(None))
        .order_by(tokens.c.last_used_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row
