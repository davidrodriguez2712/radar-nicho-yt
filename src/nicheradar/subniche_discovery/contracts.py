# src/nicheradar/subniche_discovery/contracts.py
"""A sub-niche hypothesis as the owner or the LLM proposes it, validated before storage."""

import re

from pydantic import Field, field_validator

from nicheradar.integrations.contracts import Contract

ORIGINS = ("manual", "catalog", "marketplace", "lead")
STATUSES = ("proposed", "active", "paused", "archived")
_SLUG = re.compile(r"^[a-z0-9_]{3,60}$")
_FAMILY = re.compile(r"^[a-z0-9_]{2,40}$")
_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def normalize_query(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def clean_queries(values: tuple[str, ...]) -> tuple[str, ...]:
    queries = tuple(normalize_query(value) for value in values)
    if not 1 <= len(queries) <= 3:
        raise ValueError("1 to 3 queries are required")
    if len(set(queries)) != len(queries):
        raise ValueError("duplicate queries")
    for query in queries:
        if not 3 <= len(query) <= 80 or "http" in query or "www" in query:
            raise ValueError("invalid query")
    return queries


class HypothesisDraft(Contract):
    slug: str
    label: str = Field(min_length=3, max_length=120)
    family: str
    parent_niche_slug: str | None = Field(default=None, max_length=60)
    queries: tuple[str, ...]
    origin: str
    source_input: str | None = Field(default=None, max_length=500)
    seed_channel_ids: tuple[str, ...] = ()

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not _SLUG.match(value):
            raise ValueError("slug must be snake_case, 3 to 60 characters")
        return value

    @field_validator("family")
    @classmethod
    def valid_family(cls, value: str) -> str:
        if not _FAMILY.match(value):
            raise ValueError("family must be snake_case, 2 to 40 characters")
        return value

    @field_validator("origin")
    @classmethod
    def valid_origin(cls, value: str) -> str:
        if value not in ORIGINS:
            raise ValueError("unknown origin")
        return value

    @field_validator("queries")
    @classmethod
    def valid_queries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return clean_queries(value)

    @field_validator("seed_channel_ids")
    @classmethod
    def valid_seeds(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not all(_CHANNEL_ID.match(item) for item in value):
            raise ValueError("invalid YouTube channel id")
        return value
