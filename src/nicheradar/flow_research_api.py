# src/nicheradar/flow_research_api.py
"""Private API for flow-research requests: the app orders, Claude Code researches."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.flow_research.gates import Gates
from nicheradar.flow_research.service import (
    MESSAGES,
    FlowResearchError,
    claim_request,
    create_request,
    get_request,
    list_requests,
    pending_requests,
    submit_dossier,
)

Format = Literal["long", "shorts"]
Status = Literal["pendiente", "en_curso", "listo", "rechazado"]
Owner = Annotated[str, Field(min_length=1, max_length=120)]
Language = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


class GateOverride(BaseModel):
    """A human's explicit, recorded decision to research a niche that fails a selection gate."""

    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)
    by: str = Field(min_length=1, max_length=160)


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    niche_label: str = Field(min_length=1, max_length=140)
    format: Format
    language: Language
    gate_override: GateOverride | None = None


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: Owner


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: Owner
    dossier: dict[str, Any]


def _http(error: FlowResearchError) -> HTTPException:
    status = 404 if error.code == "not_found" else 409
    detail: dict[str, Any] = {"code": error.code, "message": MESSAGES[error.code]}
    if error.reasons:
        detail["reasons"] = error.reasons
    return HTTPException(status, detail)


def flow_research_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    config: Settings,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/flow-research", dependencies=[Depends(authenticate)])

    @router.post("", status_code=201)
    def create(
        request: CreateRequest, response: Response, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        try:
            row, created = create_request(
                connection,
                request.niche_label,
                request.format,
                request.language,
                clock(),
                config.timezone,
                gates=Gates.from_settings(config),
                gate_override=None
                if request.gate_override is None
                else request.gate_override.model_dump(),
            )
        except FlowResearchError as error:
            raise _http(error) from error
        if not created:
            response.status_code = 200
        return {k: v for k, v in row.items() if k not in ("evidence", "dossier")} | {
            "created": created
        }

    @router.get("")
    def listing(
        connection: Annotated[Connection, Depends(db)],
        niche_label: Annotated[str | None, Query(max_length=140)] = None,
        format: Format | None = None,
        language: Annotated[str | None, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = None,
        status: Status | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        items = list_requests(
            connection,
            niche_label=niche_label,
            format=format,
            language=language,
            status=status,
            limit=limit,
        )
        return {"items": items}

    @router.get("/pending")
    def pending(connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        return {"items": pending_requests(connection, clock())}

    @router.get("/{request_id}")
    def detail(request_id: UUID, connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        row = get_request(connection, request_id)
        if row is None:
            raise _http(FlowResearchError("not_found"))
        return row

    @router.post("/{request_id}/claim")
    def claim(
        request_id: UUID, request: ClaimRequest, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        try:
            return claim_request(connection, request_id, request.owner, clock())
        except FlowResearchError as error:
            raise _http(error) from error

    @router.post("/{request_id}/dossier", response_model=None)
    def dossier(
        request_id: UUID, request: SubmitRequest, connection: Annotated[Connection, Depends(db)]
    ) -> Any:
        try:
            result = submit_dossier(
                connection,
                request_id,
                request.owner,
                request.dossier,
                clock(),
                Gates.from_settings(config),
            )
        except FlowResearchError as error:
            raise _http(error) from error
        if result["accepted"]:
            return jsonable_encoder(result)
        # Returned, not raised: the rejection and its attempt counter must be committed.
        return JSONResponse(status_code=422, content=jsonable_encoder(result))

    return router
