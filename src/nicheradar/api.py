import secrets
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import Connection, Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from nicheradar import __version__
from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.flow_research_api import flow_research_router
from nicheradar.integrations.retention import expire
from nicheradar.market_api import market_router
from nicheradar.pilots_api import pilots_router
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import (
    ConflictError,
    get_profile,
    insert_record,
    seed_profile,
    update_profile,
)
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import channel_analyses, credit_balances
from nicheradar.scoring.advertising import assess_advertising
from nicheradar.services.backlog import ReviewState, decide
from nicheradar.services.budget import balance_needs_refresh
from nicheradar.services.console import (
    backlog,
    consumption,
    evaluation_comparison,
    opportunity_detail,
    profit_estimate,
)
from nicheradar.services.operations import jobs as list_jobs
from nicheradar.services.operations import overview
from nicheradar.services.pilot import preflight
from nicheradar.services.production import (
    DefaultRecipeTemplate,
    ProductionPlan,
    effective_recipe_default,
    evaluate_plan,
    latest_plan,
    preview_plan,
    save_plan,
    save_recipe_default,
)
from nicheradar.services.scenarios import Scenario, simulate
from nicheradar.services.scoring import (
    ScoringConfiguration,
    latest_configuration,
    save_configuration,
)
from nicheradar.subniche_api import subniche_router
from nicheradar.workers.queue import QUEUE_LOCK, create_schedule, enqueue, schedule_attention


class ProfileEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: CreatorProfile
    expected_version: int = Field(ge=1)


class DecisionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: ReviewState
    note: str = Field(default="", max_length=4000)
    expected_version: int = Field(ge=0)


class RadarEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paused: bool


class ProductionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: ProductionPlan
    expected_version: int = Field(ge=0)


class ScoringEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuration: ScoringConfiguration
    expected_version: int = Field(ge=0)


class DefaultRecipeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: DefaultRecipeTemplate
    expected_version: int = Field(ge=0)


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> FastAPI:
    config = settings or Settings()
    database = engine or (database_engine(config) if config.database_url else None)
    app = FastAPI(
        title="NicheRadar", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if config.service_token is None:
            raise HTTPException(503, "Configura la credencial de servicio para acceder a la API.")
        expected = config.service_token.get_secret_value().encode()
        if credential is None or not secrets.compare_digest(
            credential.credentials.encode(), expected
        ):
            raise HTTPException(401, "Acceso no autorizado", headers={"WWW-Authenticate": "Bearer"})

    def db() -> Iterator[Connection]:
        if database is None:
            raise HTTPException(503, "Configura PostgreSQL y aplica las migraciones.")
        with database.begin() as connection:
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            create_schedule(connection, profile_id, clock(), {"mode": config.mode})
            expire(connection, clock())
            yield connection

    def require_live_ready(connection: Connection, *, scheduled: bool) -> None:
        if config.mode != "live":
            return
        report = preflight(connection, config, clock(), scheduled=scheduled)
        if not report["ready"]:
            raise HTTPException(
                409,
                {
                    "message": "El piloto real todavía tiene requisitos pendientes.",
                    "blockers": report["blockers"],
                },
            )

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        # Never echo submitted values, arbitrary JSON keys or validation context.
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Revisa los valores: la solicitud no cumple el formato esperado.",
                "error_types": sorted({item["type"] for item in error.errors()}),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(_: Request, __: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "Base de datos no disponible o sin migrar."}
        )

    @app.exception_handler(ConflictError)
    async def edit_conflict(_: Request, __: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "Los datos cambiaron. Recarga antes de guardar."}
        )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/status")
    def status() -> dict[str, object]:
        result = config.public_status()
        if database is not None:
            with database.begin() as connection:
                now = clock()
                profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
                create_schedule(connection, profile_id, now, {"mode": config.mode})
                schedule = (
                    connection.execute(
                        select(s.radar_schedules).where(s.radar_schedules.c.schedule_key == "radar")
                    )
                    .mappings()
                    .one()
                )
                last = connection.execute(
                    select(s.analysis_runs.c.finished_at)
                    .where(
                        s.analysis_runs.c.status == "succeeded",
                        s.analysis_runs.c.trigger != "market_scrape",
                        s.analysis_runs.c.mode == config.mode,
                        s.analysis_runs.c.profile_id == profile_id,
                    )
                    .order_by(s.analysis_runs.c.finished_at.desc())
                    .limit(1)
                ).scalar()
                result |= {
                    "radar_paused": schedule["paused"],
                    "database_configured": True,
                    "next_due_at": schedule["next_due_at"],
                    "scheduler_attention_job_id": schedule_attention(connection, schedule),
                    "last_success_at": last,
                }
                live_report = preflight(connection, config, now)
                result["research"] = overview(
                    connection,
                    profile_id,
                    config.mode,
                    now,
                    provider_ready=live_report["ready"],
                )
                result["live_pipeline"] = "ready" if live_report["ready"] else "blocked"
                result["live_pipeline_blockers"] = live_report["blockers"]
        if database is None:
            result["live_pipeline"] = "database_not_configured"
        return result

    @router.get("/pilot/preflight")
    def pilot_preflight(scheduled: bool = False) -> dict[str, Any]:
        if database is None:
            raise HTTPException(503, "Configura PostgreSQL y aplica las migraciones.")
        # Do not use db(): that dependency seeds configuration and expires evidence.
        with database.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            return preflight(connection, config, clock(), scheduled=scheduled)

    @router.get("/profile")
    def profile() -> dict[str, Any]:
        if database is None:
            return CreatorProfile().model_dump(mode="json") | {"version_number": 0}
        with database.begin() as connection:
            seed_profile(connection, CreatorProfile(), initial_catalog())
            _, version, current = get_profile(connection)
            return current.model_dump(mode="json") | {"version_number": version}

    @router.put("/profile")
    def edit_profile(
        edit: ProfileEdit, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, int]:
        return {"version_number": update_profile(connection, edit.profile, edit.expected_version)}

    @router.get("/catalog")
    def catalog() -> dict[str, object]:
        return initial_catalog().model_dump(mode="json")

    @router.put("/radar")
    def edit_radar(
        edit: RadarEdit, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, bool]:
        if not edit.paused:
            require_live_ready(connection, scheduled=True)
        connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
        schedule_values: dict[str, Any] = {"paused": edit.paused}
        if not edit.paused:
            previous = connection.execute(
                select(s.radar_schedules.c.configuration).where(
                    s.radar_schedules.c.schedule_key == "radar"
                )
            ).scalar_one()
            schedule_values["configuration"] = previous | {
                "retry_authorized_after": clock().isoformat()
            }
        connection.execute(
            update(s.radar_schedules)
            .where(s.radar_schedules.c.schedule_key == "radar")
            .values(**schedule_values)
        )
        return {"paused": edit.paused}

    @router.post("/runs", status_code=202)
    def manual_run(
        connection: Annotated[Connection, Depends(db)],
        idempotency_key: Annotated[str, Header(min_length=8, max_length=100)],
    ) -> dict[str, str]:
        connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
        profile_id, _, _ = get_profile(connection)
        key = f"manual:{profile_id}:{config.mode}:{idempotency_key}"
        existing = connection.execute(
            select(s.jobs.c.id).where(s.jobs.c.occurrence_key == key)
        ).scalar_one_or_none()
        if existing is None:
            # Preserve retries issued before request keys were scoped by profile and mode.
            existing = connection.execute(
                select(s.jobs.c.id)
                .join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
                .where(
                    s.jobs.c.occurrence_key == "manual:" + idempotency_key,
                    s.analysis_runs.c.profile_id == profile_id,
                    s.analysis_runs.c.mode == config.mode,
                )
            ).scalar_one_or_none()
        if existing is not None:
            return {
                "job_id": str(existing),
                "status": "accepted",
                "status_url": f"/api/v1/jobs/{existing}",
            }
        require_live_ready(connection, scheduled=False)
        paused = connection.execute(
            select(s.radar_schedules.c.paused).where(s.radar_schedules.c.schedule_key == "radar")
        ).scalar_one()
        if paused:
            raise HTTPException(
                409, "El radar está pausado. Reanúdalo antes de solicitar una ejecución."
            )
        job = enqueue(
            connection,
            profile_id,
            key,
            clock(),
            {},
            mode=config.mode,
        )
        return {"job_id": str(job), "status": "accepted", "status_url": f"/api/v1/jobs/{job}"}

    class ChannelAnalysisRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        channel_input: str = Field(min_length=1, max_length=500)

    @router.post("/channel-analyses", status_code=202)
    def request_channel_analysis(
        body: ChannelAnalysisRequest,
        connection: Annotated[Connection, Depends(db)],
        idempotency_key: Annotated[str, Header(min_length=8, max_length=100)],
    ) -> dict[str, str]:
        from nicheradar.discovery.channel_analysis import parse_channel_input
        from nicheradar.workers.channel_analysis_queue import CHANNEL_ANALYSIS_STAGES

        try:
            parse_channel_input(body.channel_input)
        except ValueError:
            raise HTTPException(
                422, "No se reconoce ese canal; usa su @handle o su ID (UC...)."
            ) from None
        connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
        profile_id, _, profile = get_profile(connection)
        key = f"channel-analysis:{profile_id}:{config.mode}:{idempotency_key}"
        existing = connection.execute(
            select(s.jobs.c.id).where(s.jobs.c.occurrence_key == key)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "job_id": str(existing),
                "status": "accepted",
                "status_url": f"/api/v1/jobs/{existing}",
            }
        require_live_ready(connection, scheduled=False)
        if config.mode == "live":
            # require_live_ready() only confirms controls/policies are configured; it
            # never checks the real vidIQ balance. Without this, a run can be enqueued
            # and then burn through most of its vidIQ budget before failing partway.
            # This is an early, advisory signal only -- Gateway/reserve() remains the
            # real enforcement point (it does its own live balance refresh and raises
            # balance_refresh_required/balance_exhausted when genuinely not ready), so
            # a missing or stale balance row must fail OPEN here rather than
            # permanently blocking live analyses (credit_balances rows expire after at
            # most 7 days of inactivity, and nothing but a running Gateway call
            # refreshes them).
            balance = (
                connection.execute(
                    select(credit_balances).where(
                        credit_balances.c.provider == "vidiq",
                        credit_balances.c.auth_scope == config.vidiq_auth_scope,
                    )
                )
                .mappings()
                .first()
            )
            if balance is not None and not balance_needs_refresh(dict(balance), clock()):
                # Same held-reservations formula reserve() itself uses (services/budget.py):
                # available = renewable_remaining + additional_remaining - held, where held
                # is every still-open (reserved/unknown_charge) reservation for this unit.
                # confirmed_usage is a separate lifetime counter used only for balance-
                # reconciliation deltas elsewhere; it must not be subtracted here too.
                held = connection.execute(
                    select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0))
                    .join(
                        s.provider_requests,
                        s.provider_requests.c.id == s.cost_reservations.c.request_id,
                    )
                    .where(
                        s.provider_requests.c.provider == "vidiq",
                        s.provider_requests.c.auth_scope == config.vidiq_auth_scope,
                        s.cost_reservations.c.unit == "vidiq_credit",
                        s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
                    )
                ).scalar_one()
                if profile.channel_analysis_credits_per_run + held > (
                    balance["renewable_remaining"] + balance["additional_remaining"]
                ):
                    raise HTTPException(
                        409,
                        "Saldo vidIQ insuficiente para los "
                        f"{profile.channel_analysis_credits_per_run} "
                        "créditos declarados por análisis.",
                    )
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": config.mode,
                "trigger": "channel_analysis",
                "status": "running",
                "configuration": {"channel_input": body.channel_input},
            },
        )
        job_id = insert_record(
            connection,
            "jobs",
            {
                "run_id": run_id,
                "occurrence_key": key,
                "status": "queued",
                "stage": CHANNEL_ANALYSIS_STAGES[0],
                "checkpoints": {},
                "available_at": clock(),
            },
        )
        return {
            "job_id": str(job_id),
            "status": "accepted",
            "status_url": f"/api/v1/jobs/{job_id}",
        }

    @router.get("/channel-analyses")
    def channel_analyses_list(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        include_expired: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        from nicheradar.services.channel_analysis import list_channel_analyses

        return list_channel_analyses(
            connection,
            limit=limit,
            offset=offset,
            now=clock(),
            include_expired=include_expired,
        )

    @router.get("/channel-analyses/{analysis_id}")
    def channel_analysis_detail_endpoint(
        analysis_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        from nicheradar.services.channel_analysis import channel_analysis_detail

        result = channel_analysis_detail(connection, analysis_id, now=clock())
        if result is None:
            raise HTTPException(404, "Análisis no encontrado")
        return result

    @router.delete("/channel-analyses/{analysis_id}", status_code=204)
    def delete_channel_analysis(
        analysis_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> None:
        from nicheradar.services.channel_analysis import expire_now

        if not expire_now(connection, analysis_id, clock()):
            raise HTTPException(404, "Análisis no encontrado")

    @router.get("/channel-analyses/{analysis_id}/deep-history/estimate")
    def deep_history_estimate(
        analysis_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, int | None]:
        from nicheradar.services.channel_analysis import channel_analysis_detail
        from nicheradar.services.channel_analysis_deep_history import estimate_deep_history_cost

        detail = channel_analysis_detail(connection, analysis_id, now=clock())
        if detail is None or not detail["evidence_available"]:
            raise HTTPException(404, "Análisis no encontrado o sin evidencia disponible")
        channel = detail["snapshot"].get("resolve", {}).get("channel", {})
        return {"quota_units": estimate_deep_history_cost(channel.get("video_count"))}

    @router.post("/channel-analyses/{analysis_id}/deep-history")
    async def deep_history_execute(analysis_id: UUID) -> dict[str, Any]:
        from nicheradar.integrations.contracts import Channel, ProviderError
        from nicheradar.integrations.synthetic import SyntheticProvider
        from nicheradar.services.channel_analysis import channel_analysis_detail
        from nicheradar.services.channel_analysis_deep_history import fetch_deep_history
        from nicheradar.services.channel_analysis_providers import (
            channel_analysis_youtube_limits,
            channel_analysis_youtube_tariffs,
        )
        from nicheradar.services.gateway import Gateway
        from nicheradar.services.youtube_enrichment import youtube_provider

        if database is None:
            raise HTTPException(503, "Configura PostgreSQL y aplica las migraciones.")
        # Deliberately NOT Depends(db) here: that dependency holds ONE transaction open
        # for the entire request (its generator only tears down after this handler
        # returns), and seed_profile()'s `INSERT ... ON CONFLICT DO NOTHING` takes a lock
        # on the creator_profiles row for that whole transaction. Gateway opens its OWN
        # separate connections per call (services/budget.py::lock_profile does
        # `SELECT ... FOR UPDATE` on that same row) -- combined with Depends(db), the two
        # connections deadlock against each other until the statement timeout cancels it
        # (confirmed while writing this endpoint's tests). Unlike workers/pipeline.py's
        # stage processing (which keeps a transaction open across its own Gateway calls
        # safely, because it never also locks creator_profiles via seed_profile), this
        # endpoint closes its read transaction entirely before the Gateway call, since it
        # does need that lock earlier in the same request.
        # Also: this Gateway reuses the original run's existing `youtube_detail_quota_per_run`
        # budget envelope (via `detail["run_id"]` below) rather than having a truly
        # independent cap -- a run that already spent quota reaching this stage can hit
        # that shared cap well before fetch_deep_history's own internal 100-unit loop cap
        # does. Either way, a ProviderError here is mapped to 409 below rather than
        # persisting a partial fetch; quota already spent by this call before the error is
        # not recoverable -- an accepted, documented limitation, not fixed in this pass.
        with database.begin() as connection:
            profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
            create_schedule(connection, profile_id, clock(), {"mode": config.mode})
            expire(connection, clock())
            detail = channel_analysis_detail(connection, analysis_id, now=clock())
            if detail is None or not detail["evidence_available"]:
                raise HTTPException(404, "Análisis no encontrado o sin evidencia disponible")
            require_live_ready(connection, scheduled=False)
            _, _, profile = get_profile(connection)
        # Mirrors workers/pipeline.py::Pipeline's own synthetic/live split for the YouTube
        # provider -- youtube_provider(config) requires real live credentials
        # (youtube_api_key/youtube_auth_scope) and must never be constructed in synthetic
        # mode, which this one-off call has to support same as the scheduled pipeline does.
        synthetic = config.mode == "synthetic"
        youtube = SyntheticProvider() if synthetic else youtube_provider(config)
        youtube_auth_scope = "synthetic" if synthetic else config.youtube_auth_scope
        if youtube_auth_scope is None:
            raise HTTPException(409, "Configura el scope de cuenta de YouTube antes de continuar.")
        # Not guaranteed by `evidence_available` alone: a hard-failed run (e.g. the
        # channel was never resolved) can have a non-expired snapshot with no "resolve"
        # key at all (see workers/pipeline.py's failure-report write), which would
        # otherwise KeyError into an unhandled 500 here instead of a clean 404.
        channel_payload = detail["snapshot"].get("resolve", {}).get("channel")
        if channel_payload is None:
            raise HTTPException(404, "Análisis no encontrado o sin evidencia disponible")
        channel = Channel.model_validate(channel_payload)
        gateway = Gateway(
            database,
            youtube,
            profile_id,
            detail["run_id"],
            youtube_auth_scope,
            profile,
            channel_analysis_youtube_limits(config),
            channel_analysis_youtube_tariffs(),
            maximum_calls=200,
        )
        try:
            result = await fetch_deep_history(gateway, channel, clock())
        except ProviderError as error:
            raise HTTPException(409, f"No se pudo completar el historial: {error.code}") from error
        # Plain read-then-write, no row lock: acceptable here because this is a rare,
        # manual, single-operator action with no intervening await between the SELECT
        # and UPDATE -- a concurrent writer to the same analysis_id in that narrow window
        # is an accepted, documented risk, not a case this endpoint guards against.
        with database.begin() as write_connection:
            snapshot = write_connection.execute(
                select(channel_analyses.c.snapshot).where(channel_analyses.c.id == analysis_id)
            ).scalar_one()
            write_connection.execute(
                update(channel_analyses)
                .where(channel_analyses.c.id == analysis_id)
                .values(snapshot=snapshot | {"deep_history": result})
            )
        return result

    @router.get("/jobs")
    def jobs(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        return list_jobs(connection, limit=limit, offset=offset)

    @router.get("/jobs/{job_id}")
    def job_detail(job_id: UUID, connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        result = list_jobs(connection, job_id=job_id, limit=1)
        if not result["items"]:
            raise HTTPException(404, "Trabajo no encontrado")
        return dict(result["items"][0])

    @router.get("/providers")
    def providers(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        rows = (
            connection.execute(
                select(s.provider_policies)
                .order_by(s.provider_policies.c.effective_at.desc(), s.provider_policies.c.id)
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
        return {
            "configuration": config.public_status()["providers"],
            "policies": [dict(row) for row in rows],
            "total": connection.execute(
                select(func.count()).select_from(s.provider_policies)
            ).scalar_one(),
            "limit": limit,
            "offset": offset,
        }

    @router.get("/opportunities")
    def opportunities(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        format: Literal["long", "shorts"] | None = None,
        state: ReviewState | None = None,
        confidence: Literal["insufficient", "provisional", "supported"] | None = None,
        query: Annotated[str | None, Query(max_length=100)] = None,
        sort_by: Literal[
            "score", "date", "topic", "format", "state", "confidence", "viability"
        ] = "score",
        descending: bool = True,
        viability: Literal["viable", "not_viable", "not_evaluable"] | None = None,
        minimum_score: Annotated[float | None, Query(ge=0, le=100, allow_inf_nan=False)] = None,
        evaluated_after: AwareDatetime | None = None,
    ) -> dict[str, Any]:
        return backlog(
            connection,
            limit=limit,
            offset=offset,
            format=format,
            state=state,
            confidence=confidence,
            query=query,
            sort_by=sort_by,
            descending=descending,
            viability=viability,
            minimum_score=minimum_score,
            evaluated_after=evaluated_after,
        )

    @router.get("/opportunities/{opportunity_id}")
    def detail(
        opportunity_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        result = opportunity_detail(connection, opportunity_id, clock())
        if result is None:
            raise HTTPException(404, "Oportunidad no encontrada")
        return result

    @router.get("/opportunities/{opportunity_id}/comparison")
    def comparison(
        opportunity_id: UUID,
        connection: Annotated[Connection, Depends(db)],
        previous_version: Annotated[int, Query(ge=1)],
        current_version: Annotated[int, Query(ge=1)],
    ) -> dict[str, Any]:
        if previous_version >= current_version:
            raise HTTPException(422, "La versión anterior debe preceder a la actual")
        result = evaluation_comparison(
            connection, opportunity_id, previous_version, current_version, clock()
        )
        if result is None:
            raise HTTPException(404, "Evaluaciones no encontradas para esta oportunidad")
        return result

    @router.get("/opportunities/{opportunity_id}/profit")
    def profit(
        opportunity_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if (
            connection.execute(
                select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id)
            ).first()
            is None
        ):
            raise HTTPException(404, "Oportunidad no encontrada")
        profile_id, _, profile = get_profile(connection)
        return profit_estimate(connection, opportunity_id, profile_id, profile, clock())

    @router.post("/opportunities/{opportunity_id}/decisions")
    def decision(
        opportunity_id: UUID, edit: DecisionEdit, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if (
            connection.execute(
                select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id)
            ).first()
            is None
        ):
            raise HTTPException(404, "Oportunidad no encontrada")
        return decide(
            connection,
            opportunity_id,
            edit.state,
            edit.note,
            edit.expected_version,
            clock(),
        )

    @router.get("/consumption")
    def costs(connection: Annotated[Connection, Depends(db)]) -> dict[str, Any]:
        return consumption(connection, clock())

    @router.get("/opportunities/{opportunity_id}/production")
    def production_plan(
        opportunity_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if (
            connection.execute(
                select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id)
            ).first()
            is None
        ):
            raise HTTPException(404, "Oportunidad no encontrada")
        profile_id, version, profile = get_profile(connection)
        saved = latest_plan(connection, opportunity_id, profile_id)
        if saved is None:
            return {"version": 0, "plan": None, "assessment": None, "profile_version": version}
        plan = ProductionPlan.model_validate(saved["configuration"])
        return {
            "version": saved["version"],
            "plan": plan.model_dump(mode="json"),
            "assessment": evaluate_plan(plan, profile),
            "profile_version": version,
        }

    @router.post("/opportunities/{opportunity_id}/production", status_code=201)
    def assign_production(
        opportunity_id: UUID, edit: ProductionEdit, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if (
            connection.execute(
                select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id)
            ).first()
            is None
        ):
            raise HTTPException(404, "Oportunidad no encontrada")
        profile_id, profile_version, profile = get_profile(connection)
        try:
            assessment = evaluate_plan(edit.plan, profile)
            saved = save_plan(
                connection,
                opportunity_id,
                profile_id,
                edit.plan,
                edit.expected_version,
                clock(),
            )
        except ValueError:
            raise HTTPException(
                422, "Revisa unidades, herramientas, audiencia y formato de la receta."
            ) from None
        return saved | {"assessment": assessment, "profile_version": profile_version}

    @router.get("/defaults/production-recipes/{format}")
    def default_recipe_endpoint(
        format: Literal["long", "shorts"], connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        profile_id, _, profile = get_profile(connection)
        saved = effective_recipe_default(connection, profile_id, VideoFormat(format), clock())
        template = DefaultRecipeTemplate.model_validate(saved["configuration"])
        return {
            "version": saved["version"],
            "recipe": template.recipe.model_dump(mode="json"),
            "tools": [tool.model_dump(mode="json") for tool in template.tools],
            "assessment": evaluate_plan(preview_plan(template), profile),
        }

    @router.post("/defaults/production-recipes/{format}", status_code=201)
    def assign_default_recipe(
        format: Literal["long", "shorts"],
        edit: DefaultRecipeEdit,
        connection: Annotated[Connection, Depends(db)],
    ) -> dict[str, Any]:
        profile_id, _, profile = get_profile(connection)
        try:
            saved = save_recipe_default(
                connection, profile_id, format, edit.template, edit.expected_version, clock()
            )
        except ValueError:
            raise HTTPException(422, "Revisa que el formato coincida con la receta.") from None
        return {
            "version": saved["version"],
            "recipe": edit.template.recipe.model_dump(mode="json"),
            "tools": [tool.model_dump(mode="json") for tool in edit.template.tools],
            "assessment": evaluate_plan(preview_plan(edit.template), profile),
        }

    @router.get("/opportunities/{opportunity_id}/scoring")
    def scoring_configuration(
        opportunity_id: UUID, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        opportunity = (
            connection.execute(
                select(s.opportunities).where(s.opportunities.c.id == opportunity_id)
            )
            .mappings()
            .first()
        )
        if opportunity is None:
            raise HTTPException(404, "Oportunidad no encontrada")
        profile_id, _, _ = get_profile(connection)
        saved = latest_configuration(connection, opportunity_id, profile_id)
        configuration = (
            ScoringConfiguration.model_validate(saved["configuration"])
            if saved and saved["configuration"]
            else None
        )
        assessment = assess_advertising(
            configuration.advertising if configuration else None,
            format=VideoFormat(opportunity["format"]),
            language=opportunity["language"],
            audience_key=opportunity["audience_key"],
            synthetic=config.mode == "synthetic",
            now=clock(),
        )
        return {
            "version": saved["version"] if saved else 0,
            "configuration": configuration.model_dump(mode="json") if configuration else None,
            "expired": bool(saved and saved["expired_at"]),
            "advertising": assessment.model_dump(mode="json"),
        }

    @router.post("/opportunities/{opportunity_id}/scoring", status_code=201)
    def assign_scoring(
        opportunity_id: UUID, edit: ScoringEdit, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        if (
            connection.execute(
                select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id)
            ).first()
            is None
        ):
            raise HTTPException(404, "Oportunidad no encontrada")
        profile_id, _, _ = get_profile(connection)
        try:
            return save_configuration(
                connection,
                opportunity_id,
                profile_id,
                edit.configuration,
                edit.expected_version,
                clock(),
            )
        except ValueError:
            raise HTTPException(422, "Revisa formato, audiencia y plazo de conservación.") from None

    @router.post("/scenarios", status_code=201)
    def create_scenario(
        scenario: Scenario, connection: Annotated[Connection, Depends(db)]
    ) -> dict[str, Any]:
        profile_id, _, current = get_profile(connection)
        result = simulate(scenario, current)
        scenario_id = insert_record(
            connection,
            "budget_scenarios",
            {
                "profile_id": profile_id,
                "name": scenario.name,
                "assumptions": scenario.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            },
        )
        return {"id": str(scenario_id), "result": result.model_dump(mode="json")}

    @router.get("/scenarios")
    def scenarios(
        connection: Annotated[Connection, Depends(db)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        rows = (
            connection.execute(
                select(s.budget_scenarios)
                .order_by(s.budget_scenarios.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
        return {"items": [dict(row) for row in rows]}

    app.include_router(router)
    app.include_router(market_router(authenticate=authenticate, db=db, config=config, clock=clock))
    app.include_router(
        flow_research_router(authenticate=authenticate, db=db, config=config, clock=clock)
    )
    app.include_router(pilots_router(db=db, config=config, clock=clock))
    app.include_router(subniche_router(authenticate=authenticate, db=db, clock=clock))
    return app
