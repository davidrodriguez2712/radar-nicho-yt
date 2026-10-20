# src/nicheradar/market_api.py
"""Private API for the market-intelligence backlog; same Bearer as the rest of /api/v1."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, and_, func, select

from nicheradar.config import Settings
from nicheradar.market_intel.classify import PROMPT_VERSION
from nicheradar.market_intel.niches import backlog, niche_detail, save_decision
from nicheradar.market_intel.runs import ensure_schedule, get_schedule, recent_runs, set_paused
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import listing_classifications as lc
from nicheradar.repositories.schema import marketplace_listings as ml

Format = Literal["long", "shorts"]
LIVE_GATE_MESSAGE = (
    "En modo live el scraper no se activa hasta revisar los Términos de Servicio de la fuente "
    "y habilitar NR_MARKET_INTEL_LIVE_ENABLED."
)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Format
    decision: Literal["nuevo", "tentativo", "descartado"]
    note: str | None = Field(default=None, max_length=1000)


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paused: bool


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None


def market_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    config: Settings,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/market", dependencies=[Depends(authenticate)])

    @router.get("/niches")
    def niches(
        connection: Annotated[Connection, Depends(db)],
        format: Format | None = None,
        order: Literal["opportunity", "automation"] = "opportunity",
        include_discarded: bool = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        return backlog(
            connection,
            clock(),
            format=format,
            order=order,
            include_discarded=include_discarded,
            limit=limit,
            offset=offset,
        )

    @router.get("/niches/{label}")
    def niche(
        label: Annotated[str, Path(min_length=1, max_length=140)],
        format: Format,
        connection: Annotated[Connection, Depends(db)],
    ) -> dict[str, Any]:
        detail = niche_detail(connection, label, format, clock())
        if detail is None:
            raise HTTPException(404, "Nicho no encontrado")
        return detail

    @router.post("/niches/{label}/decisions", status_code=201)
    def decide(
        label: Annotated[str, Path(min_length=1, max_length=140)],
        request: DecisionRequest,
        connection: Annotated[Connection, Depends(db)],
    ) -> dict[str, Any]:
        now = clock()
        if niche_detail(connection, label, request.format, now) is None:
            raise HTTPException(404, "Nicho no encontrado")
        save_decision(connection, label, request.format, request.decision, request.note, now)
        return {"niche_label": label, "format": request.format, "decision": request.decision}

    @router.get("/listings")
    def listings(
        connection: Annotated[Connection, Depends(db)],
        status: Literal["active", "disappeared"] | None = None,
        query: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        conditions = []
        if status is not None:
            conditions.append(ml.c.status == status)
        if query:
            conditions.append(ml.c.title.icontains(query, autoescape=True))
        total = connection.execute(
            select(func.count()).select_from(ml).where(*conditions)
        ).scalar_one()
        rows = connection.execute(
            select(
                ml.c.external_id,
                ml.c.title,
                ml.c.url,
                ml.c.status,
                ml.c.category,
                ml.c.price_usd,
                ml.c.subscribers,
                ml.c.income_monthly_usd,
                ml.c.expense_monthly_usd,
                ml.c.channel_url,
                ml.c.first_seen_at,
                ml.c.last_seen_at,
                lc.c.niche_label,
                lc.c.other_label,
                lc.c.format,
            )
            .select_from(
                ml.outerjoin(
                    lc, and_(lc.c.listing_id == ml.c.id, lc.c.prompt_version == PROMPT_VERSION)
                )
            )
            .where(*conditions)
            .order_by(ml.c.last_seen_at.desc(), ml.c.external_id.desc())
            .limit(limit)
            .offset(offset)
        ).mappings()
        items = [
            dict(row)
            | {
                "price_usd": _number(row["price_usd"]),
                "income_monthly_usd": _number(row["income_monthly_usd"]),
                "expense_monthly_usd": _number(row["expense_monthly_usd"]),
                "seller_declared": True,
            }
            for row in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/runs")
    def runs(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        return {"items": recent_runs(connection, limit)}

    def schedule_view(connection: Connection) -> dict[str, Any]:
        ensure_schedule(connection, clock())
        row = get_schedule(connection)
        radar = connection.execute(
            select(s.radar_schedules.c.paused).where(s.radar_schedules.c.schedule_key == "radar")
        ).scalar_one_or_none()
        return {
            "paused": row["paused"],
            "next_due_at": row["next_due_at"],
            "interval_seconds": row["interval_seconds"],
            "mode": config.mode,
            "live_enabled": config.market_intel_live_enabled,
            "radar_paused": radar,
        }

    @router.get("/schedule")
    def schedule(connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        return schedule_view(connection)

    @router.put("/schedule")
    def update_schedule(
        request: ScheduleRequest, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if not request.paused and config.mode == "live" and not config.market_intel_live_enabled:
            raise HTTPException(409, LIVE_GATE_MESSAGE)
        set_paused(connection, request.paused, clock())
        return schedule_view(connection)

    return router
