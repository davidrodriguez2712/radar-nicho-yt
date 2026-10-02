from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nicheradar.domain.profile import CreatorProfile, SeedCatalog
from nicheradar.repositories import schema
from nicheradar.repositories import schema_v1 as s


class ConflictError(Exception):
    """The user edited a stale version; reload before applying another decision."""


def canonical_platform(provider: str) -> str:
    """vidIQ and YouTube expose identifiers from the same YouTube namespace."""
    return "youtube" if provider in {"vidiq", "youtube"} else provider


def seed_profile(connection: Connection, profile: CreatorProfile, catalog: SeedCatalog) -> UUID:
    connection.execute(
        pg_insert(s.creator_profiles)
        .values(profile_key="personal", configuration=profile.model_dump(mode="json"), version=1)
        .on_conflict_do_nothing(index_elements=["profile_key"])
    )
    profile_id: UUID = connection.execute(
        select(s.creator_profiles.c.id).where(s.creator_profiles.c.profile_key == "personal")
    ).scalar_one()
    for family in catalog.families:
        connection.execute(
            pg_insert(s.seed_families)
            .values(
                family_key=family.id,
                catalog_version=catalog.version,
                configuration=family.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(index_elements=["family_key"])
        )
    return profile_id


def channel_identity(connection: Connection, platform: str, external_id: str) -> UUID:
    platform = canonical_platform(platform)
    aliases = ("youtube", "vidiq") if platform == "youtube" else (platform,)
    existing = connection.execute(
        select(s.channels.c.id)
        .where(s.channels.c.platform.in_(aliases), s.channels.c.external_id == external_id)
        .order_by((s.channels.c.platform == platform).desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return UUID(str(existing))
    connection.execute(
        pg_insert(s.channels)
        .values(platform=platform, external_id=external_id)
        .on_conflict_do_nothing(index_elements=["platform", "external_id"])
    )
    result: UUID = connection.execute(
        select(s.channels.c.id).where(
            s.channels.c.platform == platform, s.channels.c.external_id == external_id
        )
    ).scalar_one()
    return result


def video_identity(
    connection: Connection, platform: str, external_id: str, channel_id: UUID
) -> UUID:
    platform = canonical_platform(platform)
    aliases = ("youtube", "vidiq") if platform == "youtube" else (platform,)
    existing = (
        connection.execute(
            select(s.videos)
            .where(s.videos.c.platform.in_(aliases), s.videos.c.external_id == external_id)
            .order_by((s.videos.c.platform == platform).desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if existing is not None:
        if existing["channel_id"] != channel_id:
            raise ConflictError("video identity refers to a different channel")
        return UUID(str(existing["id"]))
    connection.execute(
        pg_insert(s.videos)
        .values(platform=platform, external_id=external_id, channel_id=channel_id)
        .on_conflict_do_nothing(index_elements=["platform", "external_id"])
    )
    row = (
        connection.execute(
            select(s.videos).where(
                s.videos.c.platform == platform, s.videos.c.external_id == external_id
            )
        )
        .mappings()
        .one()
    )
    if row["channel_id"] != channel_id:
        raise ConflictError("video identity refers to a different channel")
    return UUID(str(row["id"]))


def get_profile(connection: Connection) -> tuple[UUID, int, CreatorProfile]:
    row = (
        connection.execute(
            select(s.creator_profiles).where(s.creator_profiles.c.profile_key == "personal")
        )
        .mappings()
        .one()
    )
    return row["id"], row["version"], CreatorProfile.model_validate(row["configuration"])


def update_profile(connection: Connection, profile: CreatorProfile, expected_version: int) -> int:
    result = connection.execute(
        update(s.creator_profiles)
        .where(
            s.creator_profiles.c.profile_key == "personal",
            s.creator_profiles.c.version == expected_version,
        )
        .values(configuration=profile.model_dump(mode="json"), version=expected_version + 1)
    )
    if result.rowcount != 1:
        raise ConflictError("profile version changed")
    return expected_version + 1


def insert_record(connection: Connection, table_name: str, values: Mapping[str, Any]) -> UUID:
    """Internal repository helper. Never pass an untrusted table name from HTTP."""
    # Check schema_v1 first (frozen baseline), then schema (extended with newer tables).
    if table_name in s.metadata.tables:
        table = s.metadata.tables[table_name]
    else:
        table = schema.metadata.tables[table_name]
    result: UUID = connection.execute(
        insert(table).values(**values).returning(table.c.id)
    ).scalar_one()
    return result
