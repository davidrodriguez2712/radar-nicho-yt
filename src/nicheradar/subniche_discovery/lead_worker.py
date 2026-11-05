"""Una vuelta de lecturas: tweet o imagen -> menciones -> canales, y nombres pedidos."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.integrations.contracts import Channel, ProviderError
from nicheradar.integrations.tweets import (
    FxTwitterReader,
    ImageData,
    TweetReader,
    TweetReadError,
    TweetRef,
)
from nicheradar.market_intel.context import utcnow
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery import leads
from nicheradar.subniche_discovery.mentions import extract_mentions, merge_mentions, text_mentions
from nicheradar.subniche_discovery.reader import build_reader
from nicheradar.subniche_discovery.resolve import ChannelResolver, pick_by_name, resolve_mentions

LEAD_BATCH = 2
NAME_BATCH = 2


def _run(engine: Engine, config: Settings) -> dict[str, Any]:
    with engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": config.mode,
                "trigger": "lead_read",
                "status": "queued",
                "configuration": {},
            },
        )
    return {"id": run_id, "profile_id": profile_id, "mode": config.mode}


async def _read(
    engine: Engine,
    config: Settings,
    request: dict[str, Any],
    tweet_reader: TweetReader,
    resolver: ChannelResolver | None,
    client: AnthropicClient | None,
    clock: Callable[[], datetime],
) -> tuple[str | None, dict[str, Any]]:
    """(código de fallo o None, campos para `finish_ready`)."""
    author, text, images = request["tweet_author"], "", []
    if request["kind"] == "tweet":
        tweet = await tweet_reader.read(TweetRef(request["tweet_author"], request["tweet_id"]))
        author, text = tweet.author, tweet.text
        with engine.begin() as connection:
            leads.set_stage(connection, request["id"], "images")
        for url in tweet.photo_urls:
            try:
                images.append(await tweet_reader.photo(url))
            except TweetReadError:
                continue  # una foto que falla se omite; no tumba la lectura
    else:
        images.append(ImageData(request["image_type"], request["image_data"]))
    with engine.begin() as connection:
        leads.set_stage(connection, request["id"], "mentions")
    run = _run(engine, config)
    # YouTube primero: si no está configurado o no hay cupo, falla sin gastar el modelo.
    active = resolver or build_reader(engine, config, run, clock)
    outcome = await extract_mentions(engine, run, config, text, images, clock(), client=client)
    warning = None if outcome["reason"] == "response_received" else str(outcome["reason"])
    if request["kind"] == "image" and warning is not None:
        # Una imagen sin el modelo de visión no tiene qué leer: texto propio de imagen.
        return ("vision_not_configured" if warning == "configuration_missing" else warning), {}
    mentions = merge_mentions(text_mentions(text), outcome["mentions"])
    candidates = []
    if mentions:
        with engine.begin() as connection:
            leads.set_stage(connection, request["id"], "resolving")
        candidates = await resolve_mentions(mentions, active)
    return None, {
        "author": author,
        "text": text,
        "candidates": candidates,
        "photos_read": len(images) if request["kind"] == "tweet" else 0,
        "warning": warning,
    }


def _process(
    engine: Engine,
    config: Settings,
    request: dict[str, Any],
    tweet_reader: TweetReader,
    resolver: ChannelResolver | None,
    client: AnthropicClient | None,
    clock: Callable[[], datetime],
) -> bool:
    """Atiende una lectura ya reclamada, fuera de la transacción de `claim_next`."""
    try:
        code, fields = asyncio.run(
            _read(engine, config, request, tweet_reader, resolver, client, clock)
        )
    except SQLAlchemyError:
        raise  # sin base de datos no se puede liquidar; `release_stale` la recupera
    except (TweetReadError, ProviderError) as error:
        code, fields = error.code, {}
    except Exception:  # noqa: BLE001 - el detalle nunca sale; se guarda un código fijo
        code, fields = "unexpected", {}
    except BaseException:
        # Cancelación: no puede quedar `running`; `extract_mentions` ya liquidó su reserva.
        try:
            with engine.begin() as connection:
                leads.finish_failed(connection, request["id"], "cancelled", clock())
        except SQLAlchemyError:
            pass  # `release_stale` la recupera
        raise
    with engine.begin() as connection:
        if code is None:
            return leads.finish_ready(connection, request["id"], now=clock(), **fields)
        leads.finish_failed(connection, request["id"], code, clock())
    return False


async def _search(resolver: ChannelResolver, name: str) -> tuple[str, Channel | None]:
    return pick_by_name(name, await resolver.search_channels(name, 5))


def _name_search(
    engine: Engine,
    config: Settings,
    candidate: dict[str, Any],
    resolver: ChannelResolver | None,
    clock: Callable[[], datetime],
) -> None:
    """Una búsqueda por nombre ya pedida; ante cualquier fallo el nombre vuelve a `name_only`."""
    resolution: str
    channel: Channel | None
    try:
        active = resolver or build_reader(engine, config, _run(engine, config), clock)
        resolution, channel = asyncio.run(_search(active, candidate["value"]))
    except SQLAlchemyError:
        raise
    except Exception:  # noqa: BLE001 - el tope diario u otro fallo: se vuelve a pedir a mano
        resolution, channel = "name_only", None
    except BaseException:
        try:
            with engine.begin() as connection:
                leads.finish_name_search(connection, candidate["id"], "name_only", None, clock())
        except SQLAlchemyError:
            pass  # `release_stale` lo devuelve a `name_only`
        raise
    with engine.begin() as connection:
        leads.finish_name_search(connection, candidate["id"], resolution, channel, clock())


def tick_leads(
    config: Settings,
    engine: Engine | None = None,
    *,
    tweet_reader: TweetReader | None = None,
    resolver: ChannelResolver | None = None,
    client: AnthropicClient | None = None,
    clock: Callable[[], datetime] = utcnow,
    batch: int = LEAD_BATCH,
) -> dict[str, object]:
    status: dict[str, object] = {
        "service": "leads",
        "status": "idle",
        "processed": 0,
        "ready": 0,
        "failed": 0,
        "names": 0,
    }
    if not config.subniche_enabled:
        return status | {"status": "disabled"}
    if config.mode != "live":
        return status | {"status": "synthetic_mode"}
    if config.database_url is None and engine is None:
        return status | {"status": "not_configured"}
    database = engine or database_engine(config)
    reader = tweet_reader or FxTwitterReader()
    processed = ready = names = 0
    try:
        with database.begin() as connection:
            leads.release_stale(connection, clock())
            leads.expire_queued(connection, clock())
            leads.purge(connection, clock())
        for _ in range(batch):
            with database.begin() as connection:
                request = leads.claim_next(connection, clock())
            if request is None:
                break
            processed += 1
            ready += int(_process(database, config, request, reader, resolver, client, clock))
        for _ in range(NAME_BATCH):
            with database.begin() as connection:
                candidate = leads.claim_name_search(connection, clock())
            if candidate is None:
                break
            _name_search(database, config, candidate, resolver, clock)
            names += 1
    except SQLAlchemyError:
        return status | {
            "status": "error",
            "error_code": "database_unavailable",
            "processed": processed,
            "ready": ready,
            "failed": processed - ready,
            "names": names,
        }
    finally:
        if engine is None:
            database.dispose()
    return status | {
        "status": "processed" if processed or names else "idle",
        "processed": processed,
        "ready": ready,
        "failed": processed - ready,
        "names": names,
    }
