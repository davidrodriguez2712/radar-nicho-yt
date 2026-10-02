from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Integer, cast, func, select

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import CreatorProfile
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import (
    balance_reconciliations,
    credit_balances,
    topic_artifact_sources,
)
from nicheradar.scoring.profit import estimate_profit
from nicheradar.services.backlog import latest_decision
from nicheradar.services.budget import balance_needs_refresh
from nicheradar.services.comparison import compare_evaluations
from nicheradar.services.production import ProductionPlan, evaluate_plan, latest_plan
from nicheradar.services.ranking import history as ranking_history
from nicheradar.services.scoring import ScoringConfiguration, latest_configuration


def backlog(
    connection: Connection,
    *,
    limit: int = 20,
    offset: int = 0,
    format: str | None = None,
    state: str | None = None,
    confidence: str | None = None,
    query: str | None = None,
    sort_by: str = "score",
    descending: bool = True,
    viability: str | None = None,
    minimum_score: float | None = None,
    evaluated_after: datetime | None = None,
) -> dict[str, Any]:
    latest_id = (
        select(s.evaluation_versions.c.id)
        .where(s.evaluation_versions.c.opportunity_id == s.opportunities.c.id)
        .order_by(s.evaluation_versions.c.version.desc())
        .limit(1)
        .correlate(s.opportunities)
        .scalar_subquery()
    )
    decision_state = (
        select(s.opportunity_decisions.c.state)
        .where(s.opportunity_decisions.c.opportunity_id == s.opportunities.c.id)
        .order_by(s.opportunity_decisions.c.version.desc())
        .limit(1)
        .correlate(s.opportunities)
        .scalar_subquery()
    )
    resource_gate = func.coalesce(
        s.evaluation_versions.c.explanation["combined"]["resource_gate"].astext, "not_evaluable"
    )
    evidence_videos = cast(s.evaluation_versions.c.explanation["metrics"]["videos"].astext, Integer)
    evidence_channels = cast(
        s.evaluation_versions.c.explanation["metrics"]["channels"].astext, Integer
    )
    statement = (
        select(
            s.opportunities.c.id,
            s.opportunities.c.format,
            s.opportunities.c.language,
            s.topics.c.label,
            s.evaluation_versions.c.id.label("evaluation_id"),
            s.evaluation_versions.c.state.label("evaluation_state"),
            s.evaluation_versions.c.confidence,
            s.evaluation_versions.c.market_score,
            s.evaluation_versions.c.creator_fit,
            s.evaluation_versions.c.final_score,
            s.evaluation_versions.c.created_at.label("evaluated_at"),
            s.evaluation_versions.c.expired_at,
            s.analysis_runs.c.mode.label("source_mode"),
            func.coalesce(decision_state, "new").label("review_state"),
            resource_gate.label("viability"),
            evidence_videos.label("evidence_videos"),
            evidence_channels.label("evidence_channels"),
        )
        .join(s.topics, s.topics.c.id == s.opportunities.c.topic_id)
        .outerjoin(s.evaluation_versions, s.evaluation_versions.c.id == latest_id)
        .outerjoin(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
    )
    if format:
        statement = statement.where(s.opportunities.c.format == format)
    if state:
        statement = statement.where(func.coalesce(decision_state, "new") == state)
    if confidence:
        statement = statement.where(s.evaluation_versions.c.confidence == confidence)
    if query:
        statement = statement.where(s.topics.c.label.icontains(query, autoescape=True))
    if viability:
        statement = statement.where(resource_gate == viability)
    if minimum_score is not None:
        statement = statement.where(s.evaluation_versions.c.final_score >= minimum_score)
    if evaluated_after is not None:
        statement = statement.where(s.evaluation_versions.c.created_at >= evaluated_after)
    sorts = {
        "score": s.evaluation_versions.c.final_score,
        "date": s.evaluation_versions.c.created_at,
        "topic": s.topics.c.label,
        "format": s.opportunities.c.format,
        "state": func.coalesce(decision_state, "new"),
        "confidence": s.evaluation_versions.c.confidence,
        "viability": resource_gate,
    }
    ordering = sorts[sort_by].desc() if descending else sorts[sort_by].asc()
    total = connection.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        connection.execute(
            statement.order_by(
                ordering.nulls_last(),
                s.opportunities.c.id,
            )
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def opportunity_detail(
    connection: Connection, opportunity_id: UUID, now: datetime
) -> dict[str, Any] | None:
    opportunity = (
        connection.execute(
            select(s.opportunities, s.topics.c.label)
            .join(s.topics, s.topics.c.id == s.opportunities.c.topic_id)
            .where(s.opportunities.c.id == opportunity_id)
        )
        .mappings()
        .first()
    )
    if opportunity is None:
        return None
    evaluations = (
        connection.execute(
            select(
                s.evaluation_versions,
                s.analysis_runs.c.mode.label("source_mode"),
                s.analysis_runs.c.profile_id,
            )
            .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
            .where(s.evaluation_versions.c.opportunity_id == opportunity_id)
            .order_by(s.evaluation_versions.c.version.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    history = []
    for evaluation in evaluations:
        row = dict(evaluation)
        if row["retain_until"] <= now or row["expired_at"] is not None:
            for key in ("market_score", "creator_fit", "final_score", "explanation"):
                row[key] = None
            row["evidence_available"] = False
        else:
            row["evidence_available"] = row["expired_at"] is None
        history.append(row)
    evidence = []
    grouping = None
    if evaluations:
        criteria = connection.execute(
            select(s.cohorts.c.criteria).where(s.cohorts.c.id == evaluations[0]["cohort_id"])
        ).scalar_one_or_none()
        if criteria and criteria.get("topic_artifact_id"):
            expired_sources = (
                select(topic_artifact_sources.c.artifact_id)
                .join(
                    s.raw_observations,
                    s.raw_observations.c.id == topic_artifact_sources.c.observation_id,
                )
                .where(s.raw_observations.c.retain_until <= now)
            )
            artifact = (
                connection.execute(
                    select(s.topic_artifacts).where(
                        s.topic_artifacts.c.id == UUID(criteria["topic_artifact_id"]),
                        s.topic_artifacts.c.retain_until > now,
                        s.topic_artifacts.c.id.not_in(expired_sources),
                    )
                )
                .mappings()
                .first()
            )
            if artifact:
                data = artifact["data"]
                grouping = {
                    "method": data["group"]["method"],
                    "label": data["group"]["label"],
                    "members": len(data["group"]["member_ids"]),
                    "ambiguous_matches": data["group"]["ambiguous_matches"],
                    "correspondences": data.get("correspondences", []),
                    "parameters": data["parameters"],
                    "fallback_reason": data["fallback_reason"],
                    "omitted_videos": data["omitted"],
                    "retain_until": artifact["retain_until"],
                }
        rows = (
            connection.execute(
                select(
                    s.evidence_links.c.id,
                    s.evidence_links.c.availability,
                    s.raw_observations.c.payload,
                    s.raw_observations.c.fetched_at,
                    s.raw_observations.c.retain_until,
                )
                .outerjoin(
                    s.raw_observations, s.raw_observations.c.id == s.evidence_links.c.observation_id
                )
                .where(s.evidence_links.c.evaluation_id == evaluations[0]["id"])
            )
            .mappings()
            .all()
        )
        for evidence_row in rows:
            item = dict(evidence_row)
            if item["retain_until"] is None or item["retain_until"] <= now:
                item["payload"] = None
                item["availability"] = "expired"
            evidence.append(item)
    return {
        "opportunity": dict(opportunity),
        "decision": latest_decision(connection, opportunity_id),
        "evaluations": history,
        "evidence": evidence,
        "grouping": grouping,
        "comparison": compare_evaluations(history[1] if len(history) > 1 else None, history[0])
        if history
        else None,
        "ranking_history": ranking_history(
            connection, opportunity_id, history[0]["profile_id"], history[0]["source_mode"], now
        )
        if history
        else [],
    }


def evaluation_comparison(
    connection: Connection,
    opportunity_id: UUID,
    previous_version: int,
    current_version: int,
    now: datetime,
) -> dict[str, Any] | None:
    rows = (
        connection.execute(
            select(
                s.evaluation_versions,
                s.analysis_runs.c.mode.label("source_mode"),
                s.analysis_runs.c.profile_id,
            )
            .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
            .where(
                s.evaluation_versions.c.opportunity_id == opportunity_id,
                s.evaluation_versions.c.version.in_([previous_version, current_version]),
            )
            .order_by(s.evaluation_versions.c.version)
        )
        .mappings()
        .all()
    )
    if len(rows) != 2:
        return None
    versions = [
        dict(row) | {"evidence_available": row["expired_at"] is None and row["retain_until"] > now}
        for row in rows
    ]
    return compare_evaluations(versions[0], versions[1])


def consumption(connection: Connection, now: datetime) -> dict[str, Any]:
    ledger = (
        connection.execute(
            select(s.cost_ledger.c.unit, func.sum(s.cost_ledger.c.amount).label("amount")).group_by(
                s.cost_ledger.c.unit
            )
        )
        .mappings()
        .all()
    )
    reserves = (
        connection.execute(
            select(
                s.cost_reservations.c.unit,
                s.cost_reservations.c.status,
                func.sum(s.cost_reservations.c.amount).label("amount"),
            )
            .where(s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]))
            .group_by(s.cost_reservations.c.unit, s.cost_reservations.c.status)
        )
        .mappings()
        .all()
    )
    balances = (
        connection.execute(select(credit_balances).where(credit_balances.c.retain_until > now))
        .mappings()
        .all()
    )
    reconciliations = (
        connection.execute(
            select(balance_reconciliations)
            .where(balance_reconciliations.c.retain_until > now)
            .order_by(balance_reconciliations.c.observed_at.desc(), balance_reconciliations.c.id)
            .limit(20)
        )
        .mappings()
        .all()
    )
    return {
        "confirmed": [dict(row) for row in ledger],
        "reservations": [dict(row) for row in reserves],
        "balances": [
            dict(row) | {"refresh_required": balance_needs_refresh(dict(row), now)}
            for row in balances
        ],
        "balance_reconciliations": [dict(row) for row in reconciliations],
        "reconciliation_note": (
            "Diferencias no atribuidas: no prueban consumo externo ni resuelven cobros inciertos. "
            "Los cambios de ciclo no son ingresos USD."
        ),
        "period": "all_recorded_history",
        "production_estimates_excluded": True,
    }


def profit_estimate(
    connection: Connection,
    opportunity_id: UUID,
    profile_id: UUID,
    profile: CreatorProfile,
    now: datetime,
) -> dict[str, Any]:
    """Real competitor view spread x researched RPM, minus real production cost."""
    explanation = connection.execute(
        select(s.evaluation_versions.c.explanation)
        .where(
            s.evaluation_versions.c.opportunity_id == opportunity_id,
            s.evaluation_versions.c.expired_at.is_(None),
        )
        .order_by(s.evaluation_versions.c.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    metrics = (explanation or {}).get("metrics") or {}

    saved_plan = latest_plan(connection, opportunity_id, profile_id)
    plan = ProductionPlan.model_validate(saved_plan["configuration"]) if saved_plan else None
    cost = None
    if plan is not None:
        resources = evaluate_plan(plan, profile)["resources"]
        if resources["monthly_usd"] is not None:
            cost = EstimateRange.model_validate(resources["monthly_usd"])

    saved_config = latest_configuration(connection, opportunity_id, profile_id)
    advertising = None
    if saved_config and saved_config["configuration"]:
        configuration = ScoringConfiguration.model_validate(saved_config["configuration"])
        advertising = configuration.advertising

    result = estimate_profit(
        best_channel_views_per_day=metrics.get("best_channel_views_per_day"),
        worst_channel_views_per_day=metrics.get("worst_channel_views_per_day"),
        videos_per_month=plan.videos_per_month if plan else None,
        advertising=advertising,
        monthly_cost_usd=cost,
    )
    return result.model_dump(mode="json")
