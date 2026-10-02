"""Fixed-panel observed changes; cache reuse never creates another observation date."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, func, select

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s


@dataclass(frozen=True)
class Observation:
    observed_at: datetime
    views: int | None
    raw_id: UUID
    retain_until: datetime
    conflicting: bool = False
    source_ids: tuple[UUID, ...] = ()


def load_history(
    connection: Connection,
    current_ids: list[UUID],
    now: datetime,
    lookback_days: int,
) -> dict[UUID, tuple[Observation, ...]]:
    if not current_ids:
        return {}
    current, historic = (
        s.video_observations.alias("current"),
        s.video_observations.alias("historic"),
    )
    current_raw, historic_raw = (
        s.raw_observations.alias("current_raw"),
        s.raw_observations.alias("historic_raw"),
    )
    current_request, historic_request = (
        s.provider_requests.alias("current_request"),
        s.provider_requests.alias("historic_request"),
    )
    partition = [historic.c.video_id, historic.c.observed_at]
    current_run, historic_run = (
        s.analysis_runs.alias("current_run"),
        s.analysis_runs.alias("historic_run"),
    )
    matching = (
        select(
            historic.c.video_id,
            historic.c.observed_at,
            historic.c.views,
            current.c.observed_at.label("anchor_at"),
            func.max(historic.c.observed_at)
            .over(partition_by=historic.c.video_id)
            .label("latest_at"),
            historic_raw.c.id.label("raw_id"),
            func.min(func.least(historic_raw.c.retain_until, historic.c.retain_until))
            .over(partition_by=partition)
            .label("retain_until"),
            func.array_agg(historic_raw.c.id).over(partition_by=partition).label("source_ids"),
            func.min(historic.c.views).over(partition_by=partition).label("minimum"),
            func.max(historic.c.views).over(partition_by=partition).label("maximum"),
            func.count(historic.c.views).over(partition_by=partition).label("known"),
            func.count().over(partition_by=partition).label("total"),
            func.row_number()
            .over(
                partition_by=partition, order_by=[historic_raw.c.fetched_at.desc(), historic.c.id]
            )
            .label("duplicate"),
        )
        .select_from(
            current.join(
                historic,
                (historic.c.video_id == current.c.video_id)
                & (historic.c.format == current.c.format)
                & (historic.c.language == current.c.language)
                & (historic.c.observed_at <= current.c.observed_at),
            )
            .join(current_raw, current_raw.c.id == current.c.raw_observation_id)
            .join(historic_raw, historic_raw.c.id == historic.c.raw_observation_id)
            .join(current_request, current_request.c.id == current_raw.c.request_id)
            .join(historic_request, historic_request.c.id == historic_raw.c.request_id)
            .join(current_run, current_run.c.id == current_request.c.run_id)
            .join(historic_run, historic_run.c.id == historic_request.c.run_id)
        )
        .where(
            current.c.id.in_(current_ids),
            historic_raw.c.retain_until > now,
            historic.c.retain_until > now,
            historic_raw.c.fetched_at <= now,
            historic.c.observed_at >= now - timedelta(days=lookback_days),
            historic.c.observed_at <= now,
            historic_request.c.provider == current_request.c.provider,
            historic_request.c.auth_scope == current_request.c.auth_scope,
            historic_request.c.operation == current_request.c.operation,
            historic_raw.c.normalization_version == current_raw.c.normalization_version,
            historic_run.c.mode == current_run.c.mode,
            historic_run.c.profile_id == current_run.c.profile_id,
        )
        .subquery()
    )
    distinct_dates = (
        select(
            matching,
            func.row_number()
            .over(
                partition_by=matching.c.video_id,
                order_by=matching.c.observed_at.desc(),
            )
            .label("position"),
        )
        .where(matching.c.duplicate == 1, matching.c.latest_at == matching.c.anchor_at)
        .subquery()
    )
    rows = connection.execute(
        select(distinct_dates)
        .where(distinct_dates.c.position <= 3)
        .order_by(
            distinct_dates.c.video_id,
            distinct_dates.c.observed_at.desc(),
        )
    ).mappings()
    result: dict[UUID, list[Observation]] = {}
    for row in rows:
        result.setdefault(row["video_id"], []).append(
            Observation(
                observed_at=row["observed_at"],
                views=row["views"],
                raw_id=row["raw_id"],
                retain_until=row["retain_until"],
                conflicting=row["minimum"] != row["maximum"] or row["known"] != row["total"],
                source_ids=tuple(set(row["source_ids"])),
            )
        )
    return {key: tuple(values) for key, values in result.items()}


def summarize_history(
    history: dict[UUID, tuple[Observation, ...]],
    panel: set[UUID],
    tolerance: float,
) -> dict[str, Any]:
    if not 0 <= tolerance <= 0.25:
        raise ValueError("invalid temporal interval tolerance")
    result: dict[str, Any] = {
        "method_version": "observed-panel-v1",
        "panel_videos": len(panel),
        "videos_with_two_observations": sum(len(history.get(key, ())) >= 2 for key in panel),
        "videos_with_three_observations": sum(len(history.get(key, ())) >= 3 for key in panel),
        "coverage": 0.0,
        "interval_tolerance": tolerance,
        "status": "insufficient_history",
        "observed_views_change": None,
        "recent_views_per_day": None,
        "previous_views_per_day": None,
        "trend_relative_change": None,
        "windows": [],
        "reason": "fewer_than_two_observations",
    }
    if not panel:
        result["reason"] = "no_eligible_recent_videos"
        return result
    result["coverage"] = result["videos_with_three_observations"] / len(panel)
    # Do not select only successful survivors of the current panel.
    if result["videos_with_two_observations"] != len(panel):
        return result
    records = [history[key] for key in sorted(panel, key=str)]
    intervals: list[list[float]] = []
    rates, changes = [], []
    for index in range(2):
        if any(len(points) <= index + 1 for points in records):
            result["reason"] = "fewer_than_three_observations"
            return result
        pairs = [(points[index + 1], points[index]) for points in records]
        if any(point.conflicting or point.views is None for pair in pairs for point in pair):
            result["reason"] = "unknown_or_conflicting_counts"
            return result
        seconds = [(end.observed_at - start.observed_at).total_seconds() for start, end in pairs]
        if min(seconds) <= 0:
            result["reason"] = "non_increasing_dates"
            return result
        for position in (0, 1):
            dates = [pair[position].observed_at for pair in pairs]
            if (max(dates) - min(dates)).total_seconds() > tolerance * min(seconds):
                result["reason"] = "unaligned_observation_windows"
                return result
        deltas = [int(end.views or 0) - int(start.views or 0) for start, end in pairs]
        if min(deltas) < 0:
            result["reason"] = "counts_revised_downwards"
            return result
        intervals.append(seconds)
        rates.append(
            sum(delta / elapsed for delta, elapsed in zip(deltas, seconds, strict=True)) * 86400
        )
        changes.append(sum(deltas))
        result["windows"].append(
            {
                "start_min": min(start.observed_at for start, _ in pairs).isoformat(),
                "start_max": max(start.observed_at for start, _ in pairs).isoformat(),
                "end_min": min(end.observed_at for _, end in pairs).isoformat(),
                "end_max": max(end.observed_at for _, end in pairs).isoformat(),
                "duration_seconds_min": min(seconds),
                "duration_seconds_max": max(seconds),
            }
        )
        if index == 0:
            result.update(
                status="change_observed",
                observed_views_change=changes[0],
                recent_views_per_day=rates[0],
            )
    if any(
        abs(recent - previous) > tolerance * min(recent, previous)
        for recent, previous in zip(*intervals, strict=True)
    ):
        result["reason"] = "non_equivalent_intervals"
        return result
    result["previous_views_per_day"] = rates[1]
    if rates[1] <= 0:
        result["reason"] = "zero_previous_velocity"
        return result
    result.update(
        status="trend_observed", reason=None, trend_relative_change=(rates[0] - rates[1]) / rates[1]
    )
    return result


def temporal_evidence(
    connection: Connection,
    rows: Sequence[Any],
    now: datetime,
    config: Settings,
) -> tuple[dict[str, Any], dict[UUID, datetime]]:
    selected = [row for row in rows if row["included"] and row["selection_method"] == "recent"]
    panel = {row["video_id"] for row in selected}
    history = load_history(
        connection,
        [row["video_observation_id"] for row in selected],
        now,
        config.trend_lookback_days,
    )
    result = summarize_history(history, panel, config.trend_interval_tolerance)
    result["lookback_days"] = config.trend_lookback_days
    result["cohort_included_videos"] = sum(bool(row["included"]) for row in rows)
    sources: dict[UUID, datetime] = {}
    for points in history.values():
        for point in points:
            for source_id in point.source_ids or (point.raw_id,):
                sources[source_id] = min(
                    sources.get(source_id, point.retain_until), point.retain_until
                )
    return result, sources
