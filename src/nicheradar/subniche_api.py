# src/nicheradar/subniche_api.py
"""Private read-only API for sub-niche hypotheses; same Bearer as the rest of /api/v1."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import Connection

from nicheradar.subniche_discovery.catalog import list_subniches, subniche_detail


def subniche_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subniches", dependencies=[Depends(authenticate)])

    @router.get("")
    def listing(
        connection: Annotated[Connection, Depends(db)],
        include_inactive: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        return {"items": list_subniches(connection, include_inactive=include_inactive)}

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
