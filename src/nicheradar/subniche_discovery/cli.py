"""`subniche` commands. Every command prints one JSON line; exit code 1 on a stated error."""

import argparse
import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.market_intel.context import utcnow
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery import store
from nicheradar.subniche_discovery.contracts import STATUSES
from nicheradar.subniche_discovery.intake import ManualFields, add_hypothesis
from nicheradar.subniche_discovery.reader import YouTubeReader


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subniche")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("input")
    add.add_argument("--manual", action="store_true")
    add.add_argument("--label")
    add.add_argument("--family")
    add.add_argument("--parent")
    add.add_argument(
        "--origin", default="manual", choices=["manual", "catalog", "marketplace", "lead"]
    )
    for name in ("approve", "pause", "resume", "archive", "measure"):
        sub.add_parser(name).add_argument("slug")
    finalist = sub.add_parser("finalist")
    finalist.add_argument("slug")
    finalist.add_argument("--off", action="store_true")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=list(STATUSES))
    export = sub.add_parser("export")
    export.add_argument("--out")
    return parser


def _say(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, default=str), flush=True)


def _transition(engine: Engine, args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    with engine.begin() as connection:
        if args.command == "approve":
            store.approve(connection, args.slug, now)
        elif args.command == "pause":
            store.set_status(connection, args.slug, "paused")
        elif args.command == "resume":
            store.set_status(connection, args.slug, "active")
        elif args.command == "archive":
            store.set_status(connection, args.slug, "archived")
        elif args.command == "finalist":
            store.set_finalist(connection, args.slug, not args.off)
        elif args.command == "measure":
            store.request_remeasure(connection, args.slug)
        return {"ok": True, "slug": args.slug, "command": args.command}


def main(
    argv: list[str] | None = None,
    *,
    config: Settings | None = None,
    engine: Engine | None = None,
    reader: YouTubeReader | None = None,
    client: AnthropicClient | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    args = _parser().parse_args(argv)
    settings = config or Settings()
    database = engine or database_engine(settings)
    try:
        if args.command == "add":
            manual = None
            if args.manual:
                if not args.label or not args.family:
                    _say({"error": "manual_needs_label_and_family"})
                    return 1
                manual = ManualFields(args.label, args.family, args.parent)
            result = asyncio.run(
                add_hypothesis(
                    database,
                    settings,
                    args.input,
                    origin=args.origin,
                    manual=manual,
                    reader=reader,
                    client=client,
                    clock=clock,
                )
            )
        elif args.command == "list":
            with database.connect() as connection:
                rows = store.list_hypotheses(connection, args.status)
            result = {
                "hypotheses": [
                    {key: row[key] for key in ("slug", "label", "status", "finalist", "queries")}
                    for row in rows
                ]
            }
        elif args.command == "export":
            with database.connect() as connection:
                text = store.export_yaml(connection)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as handle:
                    handle.write(text)
                result = {"ok": True, "written": args.out}
            else:
                print(text, end="")
                return 0
        else:
            result = _transition(database, args, clock())
    except store.UnknownHypothesis:
        _say({"error": "unknown_hypothesis", "slug": getattr(args, "slug", None)})
        return 1
    except store.InvalidTransition as error:
        _say({"error": "invalid_transition", "detail": str(error)})
        return 1
    finally:
        if engine is None:
            database.dispose()
    _say(result)
    return 1 if "error" in result else 0
