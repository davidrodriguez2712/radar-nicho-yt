"""Immutable, scoped positions; a ranking expires with any of its source evaluations."""

import hashlib
import json
import math
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, or_, select

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import ranking_entries as entries
from nicheradar.repositories.schema import ranking_snapshots as snapshots
from nicheradar.services.backlog import latest_decision
from nicheradar.services.comparison import compare_evaluations, component_set, method_inputs


def capture(connection: Connection, run_id: UUID, now: datetime) -> UUID:
    run = (
        connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == run_id))
        .mappings()
        .one()
    )
    # Serialize the sequence and idempotency check for this personal profile.
    connection.execute(
        select(s.creator_profiles.c.id)
        .where(s.creator_profiles.c.id == run["profile_id"])
        .with_for_update()
    ).one()
    existing: UUID | None = connection.execute(
        select(snapshots.c.id).where(snapshots.c.run_id == run_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    rows = (
        connection.execute(
            select(
                s.evaluation_versions,
                s.opportunities.c.format,
                s.opportunities.c.language,
                s.analysis_runs.c.mode.label("source_mode"),
            )
            .join(s.opportunities, s.opportunities.c.id == s.evaluation_versions.c.opportunity_id)
            .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
            .where(
                s.analysis_runs.c.profile_id == run["profile_id"],
                s.analysis_runs.c.mode == run["mode"],
                or_(
                    s.analysis_runs.c.id == run_id,
                    s.analysis_runs.c.status == "succeeded",
                    s.analysis_runs.c.id.in_(select(snapshots.c.run_id)),
                ),
            )
            .order_by(s.evaluation_versions.c.version.desc(), s.evaluation_versions.c.id)
        )
        .mappings()
        .all()
    )
    latest: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        latest.setdefault(row["opportunity_id"], dict(row))
    snapshot_id = uuid4()
    records = []
    deadlines = []
    groups: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for opportunity_id, evaluation in latest.items():
        # Never fall back to an older score when the latest version is unavailable.
        if evaluation["expired_at"] or evaluation["retain_until"] <= now:
            continue
        decision = latest_decision(connection, opportunity_id)
        scope = {
            "format": evaluation["format"],
            "language": evaluation["language"],
            "mode": run["mode"],
            "method": method_inputs(evaluation),
            "components": component_set(evaluation),
            "creator_profile": ((evaluation["explanation"] or {}).get("production") or {}).get(
                "profile"
            ),
        }
        group_key = hashlib.sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        score = evaluation["final_score"]
        reason = (
            "dismissed"
            if decision["state"] == "dismissed"
            else "unscored"
            if score is None or not math.isfinite(score)
            else "ranked"
        )
        record = {
            "snapshot_id": snapshot_id,
            "opportunity_id": opportunity_id,
            "evaluation_id": evaluation["id"],
            "group_key": group_key,
            "scope": scope,
            "position": None,
            "review_state": decision["state"],
            "reason": reason,
        }
        records.append(record)
        deadlines.append(evaluation["retain_until"])
        if reason == "ranked":
            groups.setdefault(group_key, []).append((score, record))
    for group in groups.values():
        previous_score = None
        position = 0
        for index, (score, record) in enumerate(sorted(group, key=lambda item: -item[0]), 1):
            if score != previous_score:
                position = index
            record["position"] = position
            previous_score = score
    sequence = (
        connection.execute(
            select(func.coalesce(func.max(snapshots.c.sequence), 0)).where(
                snapshots.c.profile_id == run["profile_id"]
            )
        ).scalar_one()
        + 1
    )
    connection.execute(
        snapshots.insert().values(
            id=snapshot_id,
            profile_id=run["profile_id"],
            run_id=run_id,
            sequence=sequence,
            mode=run["mode"],
            method_version="ranking-v1",
            created_at=now,
            retain_until=min(deadlines) if deadlines else None,
        )
    )
    if records:
        connection.execute(entries.insert(), records)
    return snapshot_id


def history(
    connection: Connection,
    opportunity_id: UUID,
    profile_id: UUID,
    mode: str,
    now: datetime,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    headers = (
        connection.execute(
            select(snapshots)
            .where(snapshots.c.profile_id == profile_id, snapshots.c.mode == mode)
            .order_by(snapshots.c.sequence.desc())
            .limit(limit)
        )
        .mappings()
        .all()
    )
    result = []
    for header in headers:
        item = {
            "snapshot_id": header["id"],
            "sequence": header["sequence"],
            "created_at": header["created_at"],
            "mode": mode,
            "position": None,
            "evaluation_id": None,
            "group_key": None,
            "scope": None,
            "reason": "not_present",
            "review_state": None,
        }
        # Read-time guard as well as periodic deletion: a peer's revoked evidence invalidates rank.
        invalid_source = connection.execute(
            select(entries.c.evaluation_id)
            .join(s.evaluation_versions, s.evaluation_versions.c.id == entries.c.evaluation_id)
            .where(
                entries.c.snapshot_id == header["id"],
                or_(
                    s.evaluation_versions.c.expired_at.is_not(None),
                    s.evaluation_versions.c.retain_until <= now,
                ),
            )
            .limit(1)
        ).first()
        if (
            header["expired_at"]
            or (header["retain_until"] and header["retain_until"] <= now)
            or invalid_source
        ):
            item["reason"] = "evidence_unavailable"
        else:
            row = (
                connection.execute(
                    select(entries).where(
                        entries.c.snapshot_id == header["id"],
                        entries.c.opportunity_id == opportunity_id,
                    )
                )
                .mappings()
                .first()
            )
            if row:
                item.update(dict(row))
        result.append(item)
    for index, item in enumerate(result):
        item["change"] = compare_positions(
            connection, result[index + 1] if index + 1 < len(result) else None, item
        )
    return result


def compare_positions(
    connection: Connection, previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "first_snapshot", "position_delta": None}
    if current["reason"] == "evidence_unavailable" or (
        previous and previous["reason"] == "evidence_unavailable"
    ):
        return result | {"kind": "evidence_unavailable"}
    if previous is None:
        return result
    if previous["position"] is None or current["position"] is None:
        return result | {
            "kind": "eligibility_changed" if previous["reason"] != current["reason"] else "unranked"
        }
    if previous["group_key"] != current["group_key"]:
        return result | {"kind": "comparison_scope_changed"}
    delta = current["position"] - previous["position"]
    if not delta:
        return result | {"kind": "unchanged", "position_delta": 0}
    versions = {}
    for item in (previous, current):
        row = (
            connection.execute(
                select(s.evaluation_versions).where(
                    s.evaluation_versions.c.id == item["evaluation_id"]
                )
            )
            .mappings()
            .one()
        )
        versions[item["evaluation_id"]] = dict(row) | {"source_mode": item["mode"]}
    changes = compare_evaluations(
        versions[previous["evaluation_id"]], versions[current["evaluation_id"]]
    )
    unchanged = changes["changes"] in (["unchanged"], ["evaluation_state_changed"])
    return {
        "kind": "other_candidates_changed"
        if unchanged
        else "relative_rank_and_own_evaluation_changed",
        "position_delta": delta,
        "own_evaluation_changes": changes["changes"],
    }
