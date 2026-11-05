# src/nicheradar/subniche_api.py
"""Private API for sub-niche hypotheses and proposal requests; same Bearer as /api/v1."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.repositories.schema import hypothesis_seed_channels as seeds
from nicheradar.repositories.schema import niche_hypotheses as nh
from nicheradar.subniche_discovery import proposals, store, worker
from nicheradar.subniche_discovery.catalog import list_subniches, subniche_detail
from nicheradar.subniche_discovery.intake import ManualFields
from nicheradar.subniche_discovery.proposals import ProposalRejected
from nicheradar.subniche_discovery.reader import search_units_needed

LLM_UNAVAILABLE = "El modelo de lenguaje no está disponible: usa la propuesta manual."
GENERIC = "No se pudo preparar la propuesta."
MESSAGES: dict[str, str] = {
    "invalid_input": (
        "No se reconoce esa entrada. Usa una consulta, un video, o un canal con @handle o enlace."
    ),
    "tweet_not_supported_yet": "Los enlaces de X todavía no se leen.",
    "manual_needs_a_query": "La propuesta manual solo admite una consulta.",
    "daily_limit": "Se llegó al tope diario de propuestas.",
    "not_found": "No se encontró ese video o canal.",
    "duplicate": "Ya existe una hipótesis con esa consulta o con ese canal semilla.",
    "unknown_parent_niche": "Ese nicho padre no existe en el catálogo.",
    "invalid_proposal": "La propuesta no es válida.",
    "youtube_not_configured": "YouTube no está configurado en el servidor.",
    "youtube_quota_exhausted": (
        "La cuota de búsqueda de YouTube de hoy está agotada; "
        "inténtalo mañana o usa una consulta manual."
    ),
    "youtube_unreachable": "No se pudo consultar YouTube; vuelve a intentarlo.",
    "abandoned": "La preparación se interrumpió; vuelve a intentarlo.",
    **{
        code: LLM_UNAVAILABLE
        for code in (
            "llm_disabled",
            "synthetic_mode",
            "configuration_missing",
            "llm_tariff_not_current",
            "policy_not_enabled",
            "llm_failed",
            "invalid_response",
            "incomplete_response",
        )
    },
}

PROVIDER_CODES = {
    "integration_disabled": "youtube_not_configured",
    "authentication_required": "youtube_not_configured",
    "quota": "youtube_quota_exhausted",
    "subniche_daily_search_cap": "youtube_quota_exhausted",
    "connection_failed": "youtube_unreachable",
}


def _clean(value: str) -> str:
    """Rechaza NUL y sustitutos Unicode sueltos: la base de datos no los admite."""
    if any(char == "\x00" or "\ud800" <= char <= "\udfff" for char in value):
        raise ValueError("caracteres no permitidos")
    return value


Clean = AfterValidator(_clean)
IDEMPOTENCY_KEY = Annotated[
    str, Field(min_length=8, max_length=100, pattern=r"^[^\x00-\x1f\x7f-\x9f]+$")
]


class ManualBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Annotated[str, Field(min_length=3, max_length=120), Clean]
    family: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")]
    parent: Annotated[str, Field(max_length=60), Clean] | None = None


class ProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: Annotated[str, Field(min_length=3, max_length=500), Clean]
    manual: ManualBody | None = None


def error_message(code: str | None) -> dict[str, str] | None:
    if code is None:
        return None
    normalized = "duplicate" if code.startswith("duplicate") else PROVIDER_CODES.get(code, code)
    if normalized not in MESSAGES:
        return {"code": "unknown", "message": GENERIC}
    return {"code": normalized, "message": MESSAGES[normalized]}


def _hypothesis(connection: Connection, slug: str | None) -> dict[str, Any] | None:
    if slug is None:
        return None
    row = connection.execute(sa.select(nh).where(nh.c.slug == slug)).mappings().first()
    if row is None:
        return None
    channels = connection.execute(
        sa.select(seeds.c.channel_id)
        .where(seeds.c.hypothesis_id == row["id"])
        .order_by(seeds.c.channel_id)
    ).scalars()
    return {
        "slug": row["slug"],
        "label": row["label"],
        "family": row["family"],
        "parent_niche": row["parent_niche_slug"],
        "queries": list(row["queries"]),
        "seed_channels": list(channels),
        "status": row["status"],
    }


def _present(connection: Connection, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "kind": row["kind"],
        "input": row["input_text"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
        "error": error_message(row["error_code"]),
        "hypothesis": _hypothesis(connection, row["hypothesis_slug"]),
    }


def _lifecycle_error(error: Exception) -> JSONResponse:
    """Mensaje fijo: el texto de la excepción nunca llega al cliente."""
    if isinstance(error, store.UnknownHypothesis):
        return JSONResponse(
            status_code=404,
            content={"code": "not_found", "message": "Hipótesis no encontrada."},
        )
    return JSONResponse(
        status_code=409,
        content={
            "code": "invalid_transition",
            "message": "Esa hipótesis no puede pasar a ese estado.",
        },
    )


Slug = Annotated[str, Path(min_length=1, max_length=60)]


def subniche_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    clock: Callable[[], datetime],
    config: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subniches", dependencies=[Depends(authenticate)])

    @router.post("/proposals", status_code=202)
    def propose(
        body: ProposalBody,
        connection: Annotated[Connection, Depends(db)],
        idempotency_key: Annotated[IDEMPOTENCY_KEY, Header(alias="Idempotency-Key")],
    ) -> Any:
        manual = (
            ManualFields(body.manual.label, body.manual.family, body.manual.parent)
            if body.manual is not None
            else None
        )
        try:
            request_id, created = proposals.enqueue(
                connection,
                body.input,
                manual=manual,
                origin="manual",
                key=idempotency_key,
                now=clock(),
                per_day=config.subniche_proposals_per_day,
            )
        except ProposalRejected as error:
            status = 429 if error.code == "daily_limit" else 422
            return JSONResponse(
                status_code=status,
                content={"code": error.code, "message": MESSAGES.get(error.code, GENERIC)},
            )
        return {"id": str(request_id), "status": "queued", "created": created}

    @router.get("/proposals")
    def proposal_listing(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        rows = proposals.list_requests(connection, limit)
        return {"items": [_present(connection, row) for row in rows]}

    @router.get("/proposals/{request_id}")
    def proposal_detail(
        request_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        row = proposals.get_request(connection, request_id)
        if row is None:
            raise HTTPException(404, {"code": "not_found", "message": "Propuesta no encontrada."})
        return _present(connection, row)

    @router.get("")
    def listing(
        connection: Annotated[Connection, Depends(db)],
        include_inactive: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        return {"items": list_subniches(connection, include_inactive=include_inactive)}

    @router.get("/{slug}/approval")
    def approval_preview(slug: Slug, connection: Annotated[Connection, Depends(db)]) -> Any:
        # Lectura sin bloqueo (sin FOR UPDATE): es un GET de solo lectura.
        hypothesis = (
            connection.execute(sa.select(nh.c.status, nh.c.queries).where(nh.c.slug == slug))
            .mappings()
            .first()
        )
        if hypothesis is None:
            return _lifecycle_error(store.UnknownHypothesis(slug))
        queries = list(hypothesis["queries"])
        needed = search_units_needed(queries, config)
        cap = min(config.subniche_search_units_per_day, config.subniche_search_quota_per_run)
        return {
            "slug": slug,
            "status": hypothesis["status"],
            "queries": len(queries),
            "pages": config.subniche_search_pages,
            "search_units_needed": needed,
            "daily_cap": cap,
            "fits": needed <= cap,
            "cadence_days": worker.CADENCE.days,
        }

    def _transition(
        connection: Connection, slug: str, change: Callable[[], None], target: str
    ) -> Any:
        try:
            change()
        except (store.UnknownHypothesis, store.InvalidTransition) as error:
            return _lifecycle_error(error)
        return {"slug": slug, "status": target}

    @router.post("/{slug}/approve")
    def approve(slug: Slug, connection: Annotated[Connection, Depends(db)]) -> Any:
        return _transition(
            connection, slug, lambda: store.approve(connection, slug, clock()), "active"
        )

    @router.post("/{slug}/pause")
    def pause(slug: Slug, connection: Annotated[Connection, Depends(db)]) -> Any:
        return _transition(
            connection, slug, lambda: store.set_status(connection, slug, "paused"), "paused"
        )

    @router.post("/{slug}/resume")
    def resume(slug: Slug, connection: Annotated[Connection, Depends(db)]) -> Any:
        return _transition(
            connection, slug, lambda: store.set_status(connection, slug, "active"), "active"
        )

    @router.post("/{slug}/archive")
    def archive(slug: Slug, connection: Annotated[Connection, Depends(db)]) -> Any:
        return _transition(
            connection, slug, lambda: store.set_status(connection, slug, "archived"), "archived"
        )

    @router.get("/{slug}")
    def detail(
        slug: Annotated[str, Path(min_length=1, max_length=60)],
        connection: Annotated[Connection, Depends(db)],
    ) -> dict[str, Any]:
        card = subniche_detail(connection, slug, clock())
        if card is None:
            raise HTTPException(404, {"code": "not_found", "message": "Hipótesis no encontrada."})
        return card

    return router
