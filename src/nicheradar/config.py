"""Validated runtime configuration. Construction never makes external requests."""

from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from nicheradar.integrations.llm import LLMConfiguration


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NR_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    mode: Literal["synthetic", "live"] = "synthetic"
    radar_paused: bool = True
    timezone: str = "America/Lima"
    service_token: SecretStr | None = None
    dashboard_password: SecretStr | None = None
    database_url: SecretStr | None = None
    vidiq_token: SecretStr | None = None
    vidiq_auth_scope: str | None = Field(default=None, min_length=1, max_length=120)
    vidiq_connection_validated_at: AwareDatetime | None = None
    vidiq_credit_cycle_started_at: AwareDatetime | None = None
    vidiq_live_enabled: bool = False
    vidiq_pilot_authorized: bool = False
    youtube_api_key: SecretStr | None = None
    youtube_auth_scope: str | None = Field(default=None, min_length=1, max_length=120)
    youtube_connection_validated_at: AwareDatetime | None = None
    youtube_live_enabled: bool = False
    youtube_quota_per_run: int = Field(default=0, ge=0, le=10_000)
    youtube_quota_per_week: int = Field(default=0, ge=0, le=100_000)
    youtube_quota_per_month: int = Field(default=0, ge=0, le=1_000_000)
    youtube_maximum_videos: int = Field(default=100, ge=1, le=200)
    youtube_search_quota_per_run: int = Field(default=100, ge=0, le=10_000)
    youtube_search_quota_per_week: int = Field(default=700, ge=0, le=100_000)
    youtube_search_quota_per_month: int = Field(default=3000, ge=0, le=1_000_000)
    # Field names kept as "detail" for clarity of intent (channel-analysis's own run/
    # week/month caps for its detail-call operations); the Cost/Limits unit they map to
    # is the shared "youtube_quota" (services/channel_analysis_providers.py), the same
    # one the catalog's own enrichment flow uses for the same real external quota pool.
    youtube_detail_quota_per_run: int = Field(default=100, ge=0, le=10_000)
    youtube_detail_quota_per_week: int = Field(default=500, ge=0, le=100_000)
    youtube_detail_quota_per_month: int = Field(default=2000, ge=0, le=1_000_000)

    # Descubrimiento de subnichos (spec 2026-10-31-subniche-discovery-youtube-design).
    # El defecto de búsqueda diaria es 1 búsqueda (100 unidades) hasta que el propietario verifique
    # el cupo real de search.list en Google Cloud Console.
    subniche_enabled: bool = False
    # Google resets the YouTube quota at midnight Pacific, not at the local `timezone` midnight.
    subniche_quota_timezone: str = "America/Los_Angeles"
    subniche_search_units_per_day: int = Field(default=100, ge=0, le=100_000)
    subniche_search_pages: int = Field(default=2, ge=1, le=3)
    subniche_channels_per_hypothesis: int = Field(default=30, ge=1, le=100)
    subniche_search_quota_per_run: int = Field(default=100, ge=0, le=100_000)
    subniche_search_quota_per_week: int = Field(default=700, ge=0, le=1_000_000)
    subniche_search_quota_per_month: int = Field(default=3000, ge=0, le=10_000_000)
    subniche_detail_quota_per_run: int = Field(default=5000, ge=0, le=100_000)
    subniche_detail_quota_per_week: int = Field(default=10_000, ge=0, le=1_000_000)
    subniche_detail_quota_per_month: int = Field(default=30_000, ge=0, le=10_000_000)
    llm_enabled: bool = False
    llm_api_key: SecretStr | None = None
    llm_configuration: LLMConfiguration | None = None
    anthropic_enabled: bool = False
    anthropic_api_key: SecretStr | None = None
    anthropic_configuration: LLMConfiguration | None = None
    api_url: str = "http://127.0.0.1:8000"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = Field(default=8501, ge=1024, le=65535)
    worker_poll_seconds: int = Field(default=30, ge=1, le=3600)
    worker_maximum_attempts: int = Field(default=3, ge=1, le=10)
    external_concurrency: int = Field(default=1, ge=1, le=4)
    batch_size: int = Field(default=100, ge=1, le=10_000)
    trend_interval_tolerance: float = Field(default=0.1, ge=0, le=0.25)
    trend_lookback_days: int = Field(default=90, ge=1, le=90)
    embedding_model_directory: Path | None = None
    embedding_model_version: str | None = Field(default=None, min_length=1, max_length=80)
    embedding_batch_size: int = Field(default=16, ge=1, le=32)
    topic_relevance_threshold: float = Field(default=0.35, gt=0, le=1)
    topic_minimum_size: int = Field(default=3, ge=2, le=200)
    topic_similarity_threshold: float = Field(default=0.8, gt=0, le=1)
    topic_maximum_videos: int = Field(default=200, ge=2, le=200)
    topic_maximum_text_chars: int = Field(default=2000, ge=100, le=4000)
    market_intel_base_url: str = "https://dealbaron.com"
    market_intel_max_pages: int = Field(default=200, ge=1, le=500)
    market_intel_request_delay_seconds: float = Field(default=1.0, ge=0.2, le=30)
    market_intel_detail_cap_per_run: int = Field(default=300, ge=0, le=2000)
    market_intel_classify_cap_per_run: int = Field(default=100, ge=0, le=1000)
    market_intel_verify_cap_per_run: int = Field(default=20, ge=0, le=200)
    # Canales a enriquecer con la API de YouTube por corrida (0 = etapa desactivada).
    market_intel_enrich_cap_per_run: int = Field(default=0, ge=0, le=2000)
    # Fichas a revisar con lectura de capturas por corrida (0 = etapa desactivada).
    market_intel_evidence_cap_per_run: int = Field(default=0, ge=0, le=500)
    # Compuerta del spec: en modo live el scraper no corre hasta que el propietario revise los
    # Términos de Servicio de la fuente y active este indicador de forma explícita.
    market_intel_live_enabled: bool = False
    # Compuertas de selección (2026-10-26). Los umbrales son supuestos iniciales del agente, no
    # datos medidos: ajústalos con evidencia. No cambian los scores; solo frenan el flujo.
    gate_min_automation: int = Field(default=90, ge=0, le=100)
    gate_max_human_minutes: int = Field(default=60, ge=0, le=10_000)
    gate_block_high_policy_risk: bool = True

    @field_validator("timezone", "subniche_quota_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("unknown IANA timezone") from None
        return value

    @field_validator("service_token", "dashboard_password")
    @classmethod
    def strong_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("secret must contain at least 32 characters")
        return value

    @field_validator("vidiq_auth_scope", "youtube_auth_scope")
    @classmethod
    def safe_auth_scope(cls, value: str | None) -> str | None:
        if value is not None and (
            value.strip() != value
            or not all(char.isalnum() or char in {"-", "_", "."} for char in value)
        ):
            raise ValueError("provider account scope must be a non-secret stable identifier")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                url = make_url(value.get_secret_value())
                if url.drivername != "postgresql+psycopg" or not url.database:
                    raise ValueError
            except Exception:
                raise ValueError("expected a postgresql+psycopg URL with database") from None
        return value

    @model_validator(mode="after")
    def protect_public_bindings(self) -> Self:
        if self.topic_minimum_size > self.topic_maximum_videos:
            raise ValueError("topic minimum exceeds batch limit")
        if (self.embedding_model_directory is None) != (self.embedding_model_version is None):
            raise ValueError(
                "local embedding directory and immutable version must be configured together"
            )
        if self.api_host not in {"127.0.0.1", "localhost", "::1"} and self.service_token is None:
            raise ValueError("public API binding requires service token")
        if self.dashboard_host not in {"127.0.0.1", "localhost", "::1"}:
            if self.dashboard_password is None:
                raise ValueError("public dashboard binding requires dashboard password")
        return self

    def public_status(self) -> dict[str, object]:
        # Explicit allowlist: never serialize the settings object into API responses/logs.
        return {
            "mode": self.mode,
            "radar_paused": self.radar_paused,
            "timezone": self.timezone,
            "database_configured": self.database_url is not None,
            "service_auth_configured": self.service_token is not None,
            "explanations": {
                "enabled": self.llm_enabled,
                "credentials_configured": self.llm_api_key is not None,
                "tariff_configured": self.llm_configuration is not None,
            },
            "hypothesis_proposals": {
                "enabled": self.anthropic_enabled,
                "credentials_configured": self.anthropic_api_key is not None,
                "tariff_configured": self.anthropic_configuration is not None,
            },
            "providers": {
                "synthetic": {"credentials_configured": True, "policy": "enabled"},
                "vidiq": {
                    "credentials_configured": self.vidiq_token is not None,
                    "account_scope_configured": self.vidiq_auth_scope is not None,
                    "connection_validated": self.vidiq_connection_validated_at is not None,
                    "cycle_start_configured": self.vidiq_credit_cycle_started_at is not None,
                    "live_enabled": self.vidiq_live_enabled,
                    "pilot_authorized": self.vidiq_pilot_authorized,
                    "policy": "pending",
                },
                "youtube": {
                    "credentials_configured": self.youtube_api_key is not None,
                    "account_scope_configured": self.youtube_auth_scope is not None,
                    "connection_validated": self.youtube_connection_validated_at is not None,
                    "live_enabled": self.youtube_live_enabled,
                    "quota_configured": min(
                        self.youtube_quota_per_run,
                        self.youtube_quota_per_week,
                        self.youtube_quota_per_month,
                    )
                    > 0,
                    "policy": "pending",
                },
            },
        }
