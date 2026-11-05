"""API privada de lecturas de tweets e imágenes (mismo Bearer que /api/v1). Solo valida y encola."""

import base64
import binascii
import json
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.integrations.tweets import (
    MAX_IMAGE_BYTES,
    ImageData,
    TweetRef,
    parse_tweet_url,
    sniff_image_type,
)
from nicheradar.subniche_api import IDEMPOTENCY_KEY, MESSAGES, PROVIDER_CODES, Clean
from nicheradar.subniche_discovery import leads
from nicheradar.subniche_discovery.leads import LeadRejected

MAX_IMAGE_BODY = 7_100_000
VISION_UNAVAILABLE = (
    "El modelo con visión no está disponible: solo se leyeron los enlaces del texto."
)
GENERIC = "No se pudo leer."
LEAD_MESSAGES: dict[str, str] = {
    "reading_disabled": "La lectura de tweets e imágenes no está activa en el servidor.",
    "invalid_tweet_url": "Ese enlace no es un tweet de X.",
    "daily_limit": "Se llegó al tope diario de lecturas de tweets.",
    "invalid_image": "La imagen no es un PNG, JPEG o WEBP válido.",
    "image_too_large": "La imagen pasa de 5 MB.",
    "not_ready": "La lectura todavía no terminó.",
    "invalid_candidates": "Esos canales no pertenecen a esta lectura o no se pueden usar así.",
    "tweet_unavailable": (
        "No se pudo leer el tweet: puede estar borrado, ser privado o de una cuenta protegida. "
        "Comparte la imagen."
    ),
    "reader_failed": "El servicio de lectura de tweets no respondió. Comparte la imagen.",
    "expired": "La lectura caducó sin atenderse; vuelve a intentarla.",
    "cancelled": "La lectura se canceló; vuelve a intentarlo.",
    "abandoned": "La lectura se interrumpió; vuelve a intentarlo.",
    "youtube_not_configured": MESSAGES["youtube_not_configured"],
    "youtube_quota_exhausted": MESSAGES["youtube_quota_exhausted"],
    "youtube_unreachable": MESSAGES["youtube_unreachable"],
    **dict.fromkeys(
        (
            "llm_disabled",
            "synthetic_mode",
            "configuration_missing",
            "llm_tariff_not_current",
            "policy_not_enabled",
            "llm_failed",
            "invalid_response",
            "incomplete_response",
        ),
        VISION_UNAVAILABLE,
    ),
}


def lead_error(code: str | None) -> dict[str, str] | None:
    if code is None:
        return None
    normalized = PROVIDER_CODES.get(code, code)
    if normalized not in LEAD_MESSAGES:
        return {"code": "unknown", "message": GENERIC}
    return {"code": normalized, "message": LEAD_MESSAGES[normalized]}


def _reject(code: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"code": code, "message": LEAD_MESSAGES.get(code, GENERIC)}
    )


STATUS = {"daily_limit": 429, "image_too_large": 413, "not_ready": 409}
MAX_TEXT = 1000


class TweetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: Annotated[str, Field(min_length=10, max_length=500), Clean]


class ImageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data: Annotated[str, Field(min_length=8, max_length=MAX_IMAGE_BODY)]


class CandidatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_ids: Annotated[list[UUID], Field(min_length=1, max_length=10)]


def _present(read: dict[str, Any]) -> dict[str, Any]:
    tweet = None
    if read["kind"] == "tweet":
        tweet = {
            "author": read["tweet_author"],
            "url": TweetRef(read["tweet_author"], read["tweet_id"]).canonical_url,
        }
    failed = read["status"] == "failed"
    return {
        "id": str(read["id"]),
        "kind": read["kind"],
        "status": read["status"],
        "stage": read["stage"],
        "created_at": read["created_at"],
        "finished_at": read["finished_at"],
        "tweet": tweet,
        "untrusted_text": (read["untrusted_text"] or "")[:MAX_TEXT] or None,
        "error": lead_error(read["error_code"]) if failed else None,
        "warning": lead_error(read["error_code"]) if read["status"] == "ready" else None,
        "candidates": [
            {
                "id": c["id"],
                "kind": c["kind"],
                "value": c["value"],
                "found_in": c["found_in"],
                "resolution": c["resolution"],
                "channel": (
                    {
                        "id": c["channel_id"],
                        "title": c["channel_title"],
                        "subscribers": c["subscribers"],
                    }
                    if c["channel_id"]
                    else None
                ),
                "proposal": c["proposal"],
            }
            for c in read["candidates"]
        ],
    }


def lead_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    clock: Callable[[], datetime],
    config: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/leads", dependencies=[Depends(authenticate)])
    enabled = config.subniche_enabled and config.mode == "live"  # sin worker no se encola nada

    @router.post("/tweets", status_code=202)
    def read_tweet(
        body: TweetBody,
        connection: Annotated[Connection, Depends(db)],
        idempotency_key: Annotated[IDEMPOTENCY_KEY, Header(alias="Idempotency-Key")],
    ) -> Any:
        if not enabled:
            return _reject("reading_disabled", 503)
        ref = parse_tweet_url(body.url)
        if ref is None:
            return _reject("invalid_tweet_url", 422)
        try:
            read_id, created = leads.enqueue_tweet(
                connection, ref, key=idempotency_key, now=clock(), per_day=config.lead_reads_per_day
            )
        except LeadRejected as error:
            return _reject(error.code, STATUS.get(error.code, 422))
        return {"id": str(read_id), "status": "queued", "created": created}

    @router.post("/images", status_code=202)
    async def read_image(
        request: Request,
        connection: Annotated[Connection, Depends(db)],
        idempotency_key: Annotated[IDEMPOTENCY_KEY, Header(alias="Idempotency-Key")],
    ) -> Any:
        if not enabled:
            return _reject("reading_disabled", 503)
        declared = request.headers.get("content-length", "")
        if declared.isascii() and declared.isdigit() and int(declared) > MAX_IMAGE_BODY:
            return _reject("image_too_large", 413)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_IMAGE_BODY:
                return _reject("image_too_large", 413)
        try:
            body = ImageBody.model_validate(json.loads(raw))
            data = base64.b64decode(body.data, validate=True)
        except (ValueError, ValidationError, binascii.Error, RecursionError):
            return _reject("invalid_image", 422)
        if len(data) > MAX_IMAGE_BYTES:
            return _reject("image_too_large", 413)
        if sniff_image_type(data) != body.media_type:
            return _reject("invalid_image", 422)
        try:
            read_id, created = await run_in_threadpool(
                leads.enqueue_image,
                connection,
                ImageData(body.media_type, data),
                key=idempotency_key,
                now=clock(),
                per_day=config.lead_reads_per_day,
            )
        except LeadRejected as error:
            return _reject(error.code, STATUS.get(error.code, 422))
        return {"id": str(read_id), "status": "queued", "created": created}

    def _existing(connection: Connection, read_id: UUID) -> dict[str, Any]:
        read = leads.get_read(connection, read_id)
        if read is None:
            raise HTTPException(404, {"code": "not_found", "message": "Lectura no encontrada."})
        return read

    @router.get("/{read_id}")
    def detail(read_id: UUID, connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        return _present(_existing(connection, read_id))

    @router.post("/{read_id}/names", status_code=202)
    def names(
        read_id: UUID, body: CandidatesBody, connection: Annotated[Connection, Depends(db)]
    ) -> Any:
        _existing(connection, read_id)
        try:
            return {"queued": leads.queue_names(connection, read_id, body.candidate_ids, clock())}
        except LeadRejected as error:
            return _reject(error.code, STATUS.get(error.code, 422))

    @router.post("/{read_id}/proposals")
    def propose(
        read_id: UUID, body: CandidatesBody, connection: Annotated[Connection, Depends(db)]
    ) -> Any:
        _existing(connection, read_id)
        try:
            items = leads.propose(
                connection,
                read_id,
                body.candidate_ids,
                now=clock(),
                per_day=config.subniche_proposals_per_day,
            )
        except LeadRejected as error:
            return _reject(error.code, STATUS.get(error.code, 422))
        return {"items": items}

    @router.post("/{read_id}/close")
    def close(read_id: UUID, connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        _existing(connection, read_id)
        leads.close(connection, read_id, clock())
        return {"id": str(read_id), "closed": True}

    return router
