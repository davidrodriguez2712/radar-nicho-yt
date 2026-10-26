# src/nicheradar/pilots_api.py
"""API de pilotos: el humano autoriza y decide; el canal descarga el paquete y reporta.

Dos credenciales: el token de servicio (el humano, todas las rutas) y un token POR CANAL (solo las
rutas del canal y solo sobre los pilotos de ese canal). Un piloto ajeno responde 404 para
no revelar su existencia. Los routers existentes siguen exigiendo el token de servicio.
"""

import json
import secrets
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any, Literal, NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.pilots import service, tokens
from nicheradar.pilots.contracts import (
    CHANNEL_ID,
    MAX_REPORT_BYTES,
    Budget,
    Recipe,
    StopRule,
    validate_report,
)

Format = Literal["long", "shorts"]
Status = Literal[
    "autorizado", "entregado", "en_ejecucion", "decision_pendiente", "cerrado", "cancelado"
]
Channel = Annotated[str, Field(pattern=CHANNEL_ID)]
Note = Annotated[str, Field(min_length=1, max_length=1500)]


class Principal(NamedTuple):
    kind: Literal["service", "channel"]
    channel_id: str | None


class AuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    niche_label: str = Field(min_length=1, max_length=140)
    format: Format
    dossier_request_id: UUID
    budget: Budget
    stop_rules: list[StopRule] | None = Field(default=None, min_length=1, max_length=10)
    close_after_failed_milestones: int = Field(default=2, ge=1, le=5)
    target_channel: Channel | None = None
    recipe: Recipe | None = None
    valid_days: int = Field(default=service.DEFAULT_VALID_DAYS, ge=1, le=60)
    authorized_by: str = Field(min_length=1, max_length=160)
    accept_no_go: bool = False
    supersedes: str | None = Field(default=None, pattern=r"^pil_[0-9]{8}_[a-z0-9-]{1,40}$")


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["seguir", "cerrar"]
    note: Note
    actor: str = Field(default="humano", min_length=1, max_length=120)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Note
    actor: str = Field(default="humano", min_length=1, max_length=120)


class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: Channel
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: Channel
    label: str = Field(min_length=1, max_length=80)


def _http(error: service.PilotError) -> HTTPException:
    status = {"not_found": 404, "forbidden": 403, "gone": 410}.get(error.code, 409)
    return HTTPException(status, {"code": error.code, "message": service.MESSAGES[error.code]})


def _invalid(error: service.PilotError) -> JSONResponse:
    # Se devuelve en vez de lanzar para no revertir la transacción; sin repetir lo enviado.
    return JSONResponse(status_code=422, content={"accepted": False, "problems": error.problems})


def pilots_router(
    *,
    db: Callable[..., Iterator[Connection]],
    config: Settings,
    clock: Callable[[], datetime],
) -> APIRouter:
    bearer = HTTPBearer(auto_error=False)
    router = APIRouter(prefix="/api/v1")

    def principal(
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
        connection: Annotated[Connection, Depends(db)],
    ) -> Principal:
        if config.service_token is None:
            raise HTTPException(503, "Configura la credencial de servicio para acceder a la API.")
        unauthorized = HTTPException(
            401, "Acceso no autorizado", headers={"WWW-Authenticate": "Bearer"}
        )
        if credential is None:
            raise unauthorized
        given = credential.credentials
        if secrets.compare_digest(given.encode(), config.service_token.get_secret_value().encode()):
            return Principal("service", None)
        channel = tokens.authenticate(connection, given, clock())
        if channel is None:
            raise unauthorized
        return Principal("channel", channel)

    def human(who: Annotated[Principal, Depends(principal)]) -> Principal:
        if who.kind != "service":
            raise HTTPException(403, {"code": "forbidden", "message": "Ruta solo para el humano."})
        return who

    Anyone = Annotated[Principal, Depends(principal)]
    Human = Annotated[Principal, Depends(human)]
    Db = Annotated[Connection, Depends(db)]

    @router.post("/pilots", status_code=201, response_model=None)
    def authorize(body: AuthorizeRequest, _: Human, connection: Db) -> Any:
        try:
            result = service.authorize(
                connection,
                niche_label=body.niche_label,
                format=body.format,
                dossier_request_id=body.dossier_request_id,
                budget=body.budget.model_dump(mode="json", exclude={"currency"}),
                stop_rules=None
                if body.stop_rules is None
                else [rule.model_dump(mode="json") for rule in body.stop_rules],
                close_after=body.close_after_failed_milestones,
                target_channel=body.target_channel,
                recipe=None if body.recipe is None else body.recipe.model_dump(mode="json"),
                valid_days=body.valid_days,
                authorized_by=body.authorized_by,
                accept_no_go=body.accept_no_go,
                supersedes=body.supersedes,
                now=clock(),
                timezone=config.timezone,
            )
        except service.PilotError as error:
            if error.code == "invalid":
                return _invalid(error)
            raise _http(error) from error
        return jsonable_encoder(result)

    @router.get("/pilots")
    def list_all(
        _: Human,
        connection: Db,
        status: Annotated[Status | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        return {"items": service.list_pilots(connection, status, limit, clock())}

    @router.get("/pilots/pending")
    def pending(
        who: Anyone, connection: Db, channel: Annotated[Channel, Query()]
    ) -> dict[str, Any]:
        if who.kind == "channel" and who.channel_id != channel:
            raise HTTPException(
                403, {"code": "forbidden", "message": service.MESSAGES["forbidden"]}
            )
        return {"items": service.pending_for_channel(connection, channel, clock())}

    @router.get("/pilots/{pilot_id}/closing-summary", response_class=PlainTextResponse)
    def closing_summary(pilot_id: str, _: Human, connection: Db) -> str:
        try:
            return service.closing_summary(connection, pilot_id, clock())
        except service.PilotError as error:
            raise _http(error) from error

    @router.get("/pilots/{pilot_id}/package")
    def package(pilot_id: str, who: Anyone, connection: Db) -> dict[str, Any]:
        try:
            return service.package_for(connection, pilot_id, who.channel_id, clock())
        except service.PilotError as error:
            raise _http(error) from error

    @router.post("/pilots/{pilot_id}/delivery")
    def delivery(
        pilot_id: str, body: DeliveryRequest, who: Anyone, connection: Db
    ) -> dict[str, Any]:
        if who.kind == "channel" and who.channel_id != body.channel_id:
            raise HTTPException(
                403, {"code": "forbidden", "message": service.MESSAGES["forbidden"]}
            )
        try:
            return service.confirm_delivery(
                connection, pilot_id, body.channel_id, body.package_sha256, clock()
            )
        except service.PilotError as error:
            raise _http(error) from error

    @router.post("/pilots/{pilot_id}/reports", response_model=None)
    async def report(pilot_id: str, request: Request, who: Anyone, connection: Db) -> Any:
        body = await request.body()
        if len(body) > MAX_REPORT_BYTES:
            raise HTTPException(413, {"code": "too_large", "message": "El reporte supera 256 KiB."})
        try:
            payload = json.loads(body)
        except ValueError:
            bad: list[dict[str, str]] = [
                {"path": "(raiz)", "message": "el cuerpo no es JSON válido"}
            ]
            return JSONResponse(status_code=422, content={"accepted": False, "problems": bad})
        parsed, problems = validate_report(payload, clock())
        if parsed is None:
            return JSONResponse(status_code=422, content={"accepted": False, "problems": problems})
        if parsed.pilot_id != pilot_id:
            wrong: list[dict[str, str]] = [
                {"path": "pilot_id", "message": "no coincide con la ruta"}
            ]
            return JSONResponse(status_code=422, content={"accepted": False, "problems": wrong})
        channel = who.channel_id if who.kind == "channel" else parsed.channel_id
        assert channel is not None
        try:
            result = service.submit_report(connection, channel, parsed, clock())
        except service.PilotError as error:
            if error.code == "report_format_mismatch":
                return _invalid(error)
            raise _http(error) from error
        return jsonable_encoder(result)

    @router.get("/pilots/{pilot_id}")
    def detail(pilot_id: str, who: Anyone, connection: Db) -> dict[str, Any]:
        try:
            return service.get_pilot(connection, pilot_id, who.channel_id, clock())
        except service.PilotError as error:
            raise _http(error) from error

    @router.post("/pilots/{pilot_id}/decision")
    def decision(pilot_id: str, body: DecisionRequest, _: Human, connection: Db) -> dict[str, Any]:
        try:
            return service.decide(
                connection, pilot_id, body.decision, body.note, body.actor, clock()
            )
        except service.PilotError as error:
            raise _http(error) from error

    @router.post("/pilots/{pilot_id}/cancel")
    def cancel(pilot_id: str, body: CancelRequest, _: Human, connection: Db) -> dict[str, Any]:
        try:
            return service.cancel(connection, pilot_id, body.reason, body.actor, clock())
        except service.PilotError as error:
            raise _http(error) from error

    @router.post("/channel-tokens", status_code=201)
    def issue_token(body: TokenRequest, _: Human, connection: Db) -> dict[str, Any]:
        token, row = tokens.issue(connection, body.channel_id, body.label, clock())
        # El token en claro se muestra una sola vez; solo se guarda su huella.
        return {**jsonable_encoder(row), "token": token}

    @router.get("/channel-tokens")
    def list_tokens(_: Human, connection: Db) -> dict[str, Any]:
        return {"items": jsonable_encoder(tokens.listing(connection))}

    @router.delete("/channel-tokens/{token_id}", status_code=204)
    def revoke_token(token_id: UUID, _: Human, connection: Db) -> Response:
        if not tokens.revoke(connection, str(token_id), clock()):
            raise HTTPException(
                404, {"code": "not_found", "message": service.MESSAGES["not_found"]}
            )
        return Response(status_code=204)

    return router
