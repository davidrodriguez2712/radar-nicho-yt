# src/nicheradar/market_intel/priors.py
"""One-time automation priors per niche, labelled through the same bounded LLM path.

A niche is presented as a pseudo-listing; the traits the model returns become the prior that
fills in any trait a real listing leaves unknown. Nothing here runs outside the live pilot.
"""

from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Connection, Engine, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.market_intel.classify import PROMPT_VERSION, classify_listing
from nicheradar.repositories.schema import niche_automation_priors as priors_table
from nicheradar.repositories.schema_v1 import analysis_runs
from nicheradar.services.advertising_benchmarks import list_niche_options


def pseudo_listing(label: str, description: str) -> dict[str, Any]:
    return {
        "id": uuid5(NAMESPACE_URL, f"niche-prior:{label}"),
        "title": label,
        "category": None,
        "description": (
            f"Nicho de contenido de YouTube: {description} "
            "Evalúa los rasgos típicos de los canales de este nicho."
        ),
    }


def pending_priors(connection: Connection, limit: int) -> list[dict[str, str]]:
    done = set(connection.execute(select(priors_table.c.niche_label)).scalars())
    options = [dict(option) for option in list_niche_options(connection)]
    return [option for option in options if option["niche_label"] not in done][:limit]


def save_prior(
    connection: Connection, label: str, traits: dict[str, int | None], now: datetime
) -> None:
    values = {"traits": traits, "prompt_version": PROMPT_VERSION}
    connection.execute(
        insert(priors_table)
        .values(id=uuid4(), niche_label=label, created_at=now, **values)
        .on_conflict_do_update(index_elements=["niche_label"], set_=values)
    )


def close_analysis_run(engine: Engine, run_id: UUID, status: str, now: datetime) -> None:
    """The labelling script opens its own analysis run; closing it keeps /status honest."""
    with engine.begin() as connection:
        connection.execute(
            update(analysis_runs)
            .where(analysis_runs.c.id == run_id)
            .values(status=status, finished_at=now)
        )


async def label_niche_priors(
    engine: Engine,
    run: dict[str, Any],
    config: Settings,
    now: datetime,
    *,
    limit: int,
    selector: OpenAISelector | None = None,
) -> dict[str, Any]:
    with engine.connect() as connection:
        # Every pending niche is a candidate: one that keeps answering invalid must not take a
        # slot of the batch forever. The limit counts saved priors, not attempts.
        candidates = pending_priors(connection, 10_000)
    pending = candidates[:limit]
    saved = 0
    stopped: str | None = None
    for option in candidates:
        if saved >= limit:
            break
        label = option["niche_label"]
        answer = await classify_listing(
            engine,
            run,
            config,
            pseudo_listing(label, option["niche_description"]),
            (label,),
            now,
            selector=selector,
        )
        result = answer["classification"]
        if result is None:
            stopped = answer["reason"]
            break
        if result.reason != "response_received":
            continue  # an invalid answer is skipped and the niche is retried next time
        with engine.begin() as connection:
            save_prior(connection, label, result.traits, now)
        saved += 1
    return {"pending": len(pending), "saved": saved, "stopped_reason": stopped}
