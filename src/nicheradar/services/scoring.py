"""Versioned, manually documented scoring inputs; no provider fetch or calibration invention."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import AwareDatetime, model_validator
from sqlalchemy import Connection, select

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Contract
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import ConflictError
from nicheradar.repositories.schema import opportunity_scoring_configs as configs
from nicheradar.scoring.advertising import AdvertisingBenchmark, Documented
from nicheradar.scoring.market import References


class ScoringConfiguration(Contract):
    format: VideoFormat
    language: Documented
    audience_key: Documented
    references: References | None = None
    advertising: AdvertisingBenchmark | None = None
    relevance_review: Documented | None = None
    retention_basis: Documented
    retain_until: AwareDatetime

    @model_validator(mode="after")
    def same_scope(self) -> Self:
        if self.format == VideoFormat.UNKNOWN:
            raise ValueError("confirmed format required")
        if self.references and self.references.format != self.format:
            raise ValueError("reference format mismatch")
        if self.advertising and (
            self.advertising.format,
            self.advertising.language,
            self.advertising.audience_key,
        ) != (self.format, self.language, self.audience_key):
            raise ValueError("advertising scope mismatch")
        return self


def latest_configuration(
    connection: Connection, opportunity_id: UUID, profile_id: UUID
) -> dict[str, Any] | None:
    row = (
        connection.execute(
            select(configs)
            .where(configs.c.opportunity_id == opportunity_id, configs.c.profile_id == profile_id)
            .order_by(configs.c.version.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    # Keep expired tombstones: never silently fall back to older assumptions.
    return dict(row) if row else None


def save_configuration(
    connection: Connection,
    opportunity_id: UUID,
    profile_id: UUID,
    configuration: ScoringConfiguration,
    expected_version: int,
    now: datetime,
) -> dict[str, Any]:
    opportunity = (
        connection.execute(
            select(s.opportunities).where(s.opportunities.c.id == opportunity_id).with_for_update()
        )
        .mappings()
        .one()
    )
    if (configuration.format, configuration.language, configuration.audience_key) != (
        opportunity["format"],
        opportunity["language"],
        opportunity["audience_key"],
    ):
        raise ValueError("configuration scope mismatch")
    if configuration.retain_until <= now:
        raise ValueError("retention deadline must be in the future")
    previous = latest_configuration(connection, opportunity_id, profile_id)
    version = previous["version"] if previous else 0
    if version != expected_version:
        raise ConflictError("scoring assumptions changed")
    connection.execute(
        configs.insert().values(
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            version=version + 1,
            configuration=configuration.model_dump(mode="json"),
            created_at=now,
            retain_until=configuration.retain_until,
        )
    )
    return {"version": version + 1}
