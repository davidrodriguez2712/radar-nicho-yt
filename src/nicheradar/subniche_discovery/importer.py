# src/nicheradar/subniche_discovery/importer.py
"""Bulk-load sub-niche hypotheses from the file `store.export_yaml` writes.

No YAML library: every scalar in that file is a JSON value, so a strict line parser is enough.
The file's `status` and `finalist` are ignored: everything imported is `proposed` and not a
finalist, and must still be approved one by one before it spends quota.
"""

import json
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection

from nicheradar.subniche_discovery import store
from nicheradar.subniche_discovery.contracts import HypothesisDraft, normalize_query

MAX_CHARS = 200_000
MAX_BLOCKS = 500
ALLOWED_KEYS = (
    "slug",
    "label",
    "family",
    "parent_niche",
    "queries",
    "origin",
    "status",
    "finalist",
    "seed_channels",
)
REQUIRED_KEYS = ("slug", "label", "family", "queries", "origin")
_START = re.compile(r"^- slug: (.+)$")
_FIELD = re.compile(r"^  ([a-z_]+): (.+)$")


class ImportFormatError(ValueError):
    pass


def _value(raw: str, number: int) -> Any:
    try:
        return json.loads(raw)
    except ValueError as error:
        raise ImportFormatError(f"line {number}: invalid JSON value") from error


def parse_export(text: str) -> list[dict[str, Any]]:
    if len(text) > MAX_CHARS:
        raise ImportFormatError(f"file is larger than {MAX_CHARS} characters")
    items: list[dict[str, Any]] = []
    started: list[int] = []

    def close() -> None:
        if items:
            missing = [key for key in REQUIRED_KEYS if key not in items[-1]]
            if missing:
                raise ImportFormatError(f"line {started[-1]}: missing key {', '.join(missing)}")

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if start := _START.match(line):
            close()
            if len(items) >= MAX_BLOCKS:
                raise ImportFormatError(f"line {number}: more than {MAX_BLOCKS} blocks")
            items.append({"slug": _value(start.group(1), number)})
            started.append(number)
        elif (field := _FIELD.match(line)) and items:
            key = field.group(1)
            if key not in ALLOWED_KEYS:
                raise ImportFormatError(f"line {number}: unknown key {key}")
            if key in items[-1]:
                raise ImportFormatError(f"line {number}: repeated key {key}")
            items[-1][key] = _value(field.group(2), number)
        else:
            raise ImportFormatError(f"line {number}: unexpected line")
    close()
    return items


def _problem(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
    return str(error)


def _validate(
    items: Sequence[dict[str, Any]], labels: Sequence[str]
) -> tuple[list[HypothesisDraft], list[dict[str, str]]]:
    drafts: list[HypothesisDraft] = []
    invalid: list[dict[str, str]] = []
    slugs: set[str] = set()
    queries: set[str] = set()
    for item in items:
        slug = str(item.get("slug"))
        try:
            parent = item.get("parent_niche")
            if parent is not None and parent not in labels:
                raise ValueError(f"unknown parent_niche {parent!r}")
            draft = HypothesisDraft(
                slug=item["slug"],
                label=item["label"],
                family=item["family"],
                parent_niche_slug=parent,
                queries=tuple(item["queries"]),
                origin=item["origin"],
                source_input=None,
                seed_channel_ids=tuple(item.get("seed_channels") or ()),
            )
            if draft.slug in slugs:
                raise ValueError("slug repeated in the file")
            clash = sorted(set(draft.queries) & queries)
            if clash:
                raise ValueError(f"query repeated in the file: {clash[0]}")
        except (ValidationError, ValueError, TypeError, KeyError) as error:
            invalid.append({"slug": slug, "error": _problem(error)})
            # Remember what a bad item claimed so later duplicates of it are still caught.
            if isinstance(item.get("slug"), str):
                slugs.add(item["slug"])
            if isinstance(item.get("queries"), list):
                queries.update(normalize_query(q) for q in item["queries"] if isinstance(q, str))
            continue
        slugs.add(draft.slug)
        queries.update(draft.queries)
        drafts.append(draft)
    return drafts, invalid


def import_hypotheses(
    connection: Connection,
    items: Sequence[dict[str, Any]],
    labels: Sequence[str],
    now: datetime,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    drafts, invalid = _validate(items, labels)
    if invalid:
        return {"ok": False, "dry_run": dry_run, "invalid": invalid, "total": len(items)}
    imported: list[str] = []
    skipped: list[dict[str, str]] = []
    savepoint = connection.begin_nested() if dry_run else None
    try:
        for draft in drafts:
            try:
                store.create_proposed(connection, draft, now)
                imported.append(draft.slug)
            except store.DuplicateHypothesis as duplicate:
                skipped.append({"slug": draft.slug, "reason": duplicate.reason})
    finally:
        if savepoint is not None:
            savepoint.rollback()
    return {
        "ok": True,
        "dry_run": dry_run,
        "imported": imported,
        "skipped": skipped,
        "total": len(items),
    }
