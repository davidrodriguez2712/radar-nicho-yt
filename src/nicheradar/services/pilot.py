"""Read-only readiness and runtime construction for a bounded vidIQ pilot."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, select

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Cost, Operation, ProviderError
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.integrations.vidiq import MCPTransport, VidIQAPIKeyAuth, VidIQProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.budget import Limits

PILOT_OPERATIONS = (
    Operation.BALANCE,
    Operation.CHANNEL_SEARCH,
    Operation.CHANNEL_VIDEOS,
    Operation.OUTLIERS,
)
VIDIQ_TARIFF_SOURCE = "vidIQ MCP tools/list inspected 2026-09-21"


def vidiq_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    return {
        operation: (
            Cost(
                unit="vidiq_credit",
                maximum=Decimal(0 if operation == Operation.BALANCE else 5),
                source=VIDIQ_TARIFF_SOURCE,
            ),
        )
        for operation in PILOT_OPERATIONS
    }


def vidiq_limits(profile: CreatorProfile) -> dict[str, Limits]:
    return {
        "vidiq_credit": Limits(
            operation=Decimal(5),
            run=Decimal(profile.credits_per_run),
            week=Decimal(profile.credits_per_week),
            period=Decimal(profile.credits_per_cycle),
        )
    }


def vidiq_provider(config: Settings) -> VidIQProvider:
    if config.vidiq_token is None:
        raise ProviderError("authentication_required", not_sent=True)
    if config.vidiq_auth_scope is None:
        raise ProviderError("account_scope_required", not_sent=True)
    return VidIQProvider(
        MCPTransport(auth=VidIQAPIKeyAuth(config.vidiq_token), enabled=True),
        config.vidiq_auth_scope,
    )


def preflight(
    connection: Connection, config: Settings, now: datetime, *, scheduled: bool = False
) -> dict[str, Any]:
    """Report whether the bounded live pipeline can execute without bypassing controls.

    Registered policies are not a legal opinion. A configured token is not proof
    of a working connection. Neither can override the runtime and authorization gates.
    """
    row = (
        connection.execute(
            select(s.creator_profiles.c.configuration).where(
                s.creator_profiles.c.profile_key == "personal"
            )
        )
        .mappings()
        .one_or_none()
    )
    profile = CreatorProfile.model_validate(row["configuration"]) if row else None

    def check(code: str, configured: bool, message: str) -> dict[str, Any]:
        return {
            "code": code,
            "status": "configured" if configured else "pending",
            "message": message,
        }

    checks: list[dict[str, Any]] = [
        check(
            "runtime_mode_live",
            config.mode == "live",
            "Configurar NR_MODE=live únicamente en el entorno del piloto.",
        ),
        check(
            "live_pipeline_connected",
            True,
            "El worker puede construir vidIQ y conectarlo al gateway presupuestado.",
        ),
        check(
            "provider_credential_present",
            config.vidiq_token is not None,
            "Configurar la clave API MCP propia en el entorno secreto del worker.",
        ),
        check(
            "provider_account_scope_configured",
            config.vidiq_auth_scope is not None,
            "Configurar un identificador estable y no secreto para la cuenta.",
        ),
        check(
            "provider_connection_validated",
            bool(
                config.vidiq_connection_validated_at and config.vidiq_connection_validated_at <= now
            ),
            "Registrar una fecha no futura de validación MCP realizada con esa credencial.",
        ),
        check(
            "credit_cycle_start_configured",
            bool(
                config.vidiq_credit_cycle_started_at and config.vidiq_credit_cycle_started_at <= now
            ),
            "Configurar el inicio confirmado y no futuro del ciclo; "
            "el contrato solo devuelve su fin.",
        ),
        check(
            "live_tariffs_verified",
            True,
            "Saldo 0 créditos; búsqueda, publicaciones y outliers 5 créditos por llamada.",
        ),
        check(
            "live_runtime_enabled",
            config.vidiq_live_enabled,
            "Activar el interruptor técnico solo cuando los demás controles estén completos.",
        ),
        check(
            "pilot_authorization_required",
            config.vidiq_pilot_authorized,
            "Autorizar explícitamente el alcance y el tope del piloto.",
        ),
        {
            "code": "profile_configured",
            "status": "configured" if profile else "missing",
            "message": (
                "Perfil guardado en PostgreSQL."
                if profile
                else "Falta guardar el perfil; esta comprobación no crea uno."
            ),
        },
        {
            "code": "paid_budget_confirmed",
            "status": "configured" if profile and profile.paid_limits_confirmed else "pending",
            "message": "La confirmación del presupuesto no sustituye la autorización del piloto.",
        },
        check(
            "credit_limits_support_one_call",
            bool(
                profile
                and profile.credits_per_run >= 5
                and profile.credits_per_week >= 5
                and profile.credits_per_cycle >= 5
            ),
            "Los límites de ejecución, semana y ciclo deben admitir "
            "al menos una llamada de 5 créditos.",
        ),
    ]
    if config.youtube_live_enabled:
        checks.extend(
            [
                check(
                    "youtube_credential_present",
                    config.youtube_api_key is not None,
                    "Configurar una clave restringida de YouTube Data API en el worker.",
                ),
                check(
                    "youtube_account_scope_configured",
                    config.youtube_auth_scope is not None,
                    "Configurar un identificador estable y no secreto del proyecto de Google.",
                ),
                check(
                    "youtube_connection_validated",
                    bool(
                        config.youtube_connection_validated_at
                        and config.youtube_connection_validated_at <= now
                    ),
                    "Registrar una validación no futura de la clave de YouTube.",
                ),
                check(
                    "youtube_quota_limits_configured",
                    min(
                        config.youtube_quota_per_run,
                        config.youtube_quota_per_week,
                        config.youtube_quota_per_month,
                    )
                    >= 1,
                    "Los límites de cuota deben admitir al menos un videos.list.",
                ),
            ]
        )
    policies = []
    for operation in PILOT_OPERATIONS:
        usages = [Usage.QUERY, Usage.STORAGE, Usage.HISTORY]
        if operation != Operation.BALANCE:
            usages.append(Usage.DERIVED)
        if scheduled:
            usages.append(Usage.SCHEDULED)
        for usage in usages:
            state = "enabled"
            retention = None
            try:
                policy_id = require_usage(connection, "vidiq", operation, usage, "metadata", now)
                policy = (
                    connection.execute(
                        select(s.provider_policies).where(s.provider_policies.c.id == policy_id)
                    )
                    .mappings()
                    .one()
                )
                if not policy["evidence_source"].strip():
                    state = "policy_evidence_missing"
                retention = policy["retention_seconds"]
                if usage == Usage.STORAGE and not retention:
                    state = "retention_not_configured"
            except ProviderError as error:
                state = error.code
            policies.append(
                {
                    "provider": "vidiq",
                    "operation": operation.value,
                    "usage": usage.value,
                    "data_type": "metadata",
                    "status": state,
                    "retention_seconds": retention,
                }
            )
    if config.youtube_live_enabled:
        usages = [Usage.QUERY, Usage.STORAGE, Usage.HISTORY, Usage.DERIVED]
        if scheduled:
            usages.append(Usage.SCHEDULED)
        for usage in usages:
            state = "enabled"
            retention = None
            try:
                policy_id = require_usage(
                    connection, "youtube", Operation.VIDEOS, usage, "metadata", now
                )
                policy = (
                    connection.execute(
                        select(s.provider_policies).where(s.provider_policies.c.id == policy_id)
                    )
                    .mappings()
                    .one()
                )
                if not policy["evidence_source"].strip():
                    state = "policy_evidence_missing"
                retention = policy["retention_seconds"]
                if usage == Usage.STORAGE and not retention:
                    state = "retention_not_configured"
                if usage == Usage.STORAGE and retention and retention > 30 * 86400:
                    state = "retention_exceeds_youtube_limit"
            except ProviderError as error:
                state = error.code
            policies.append(
                {
                    "provider": "youtube",
                    "operation": Operation.VIDEOS.value,
                    "usage": usage.value,
                    "data_type": "metadata",
                    "status": state,
                    "retention_seconds": retention,
                }
            )
    blockers = [item["code"] for item in checks if item["status"] != "configured"]
    if any(policy["status"] != "enabled" for policy in policies):
        blockers.append("provider_policies_incomplete")
    return {
        "provider": "vidiq+youtube" if config.youtube_live_enabled else "vidiq",
        "scope": "scheduled" if scheduled else "manual_pilot",
        "checked_at": now,
        "read_only": True,
        "provider_calls": 0,
        "ready": not blockers,
        "runtime_mode": config.mode,
        "credential_material_present": config.vidiq_token is not None,
        "checks": checks,
        "policies": policies,
        "blockers": blockers,
        "budget": {
            "credits_per_run": profile.credits_per_run,
            "credits_per_week": profile.credits_per_week,
            "credits_per_cycle": profile.credits_per_cycle,
            "usd_per_run": str(profile.radar_usd_per_run),
            "usd_per_month": str(profile.radar_usd_per_month),
        }
        if profile
        else None,
        "warnings": [
            "El adaptador vidIQ no confirma el idioma del video; esos casos quedan desconocidos.",
            "Sin referencias reales revisadas, las puntuaciones permanecen sin calibrar.",
            "Este informe es de solo lectura y no ejecuta llamadas ni cambia la programación.",
        ],
    }
