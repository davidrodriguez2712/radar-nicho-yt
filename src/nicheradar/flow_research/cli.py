# src/nicheradar/flow_research/cli.py
"""Command line for the flow-research skill. Prints JSON; never prints the token."""

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nicheradar.config import Settings
from nicheradar.flow_research.client import ApiError, FlowResearchClient
from nicheradar.flow_research.contracts import DossierV2, validate_dossier


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str))


def _read(path: str) -> Any:
    return json.loads(Path(path).read_text())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow_research")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pending", help="list pending requests")
    create = commands.add_parser(
        "create", help="order a research request (it must pass the selection gates)"
    )
    create.add_argument("niche_label")
    create.add_argument("--format", required=True, choices=["long", "shorts"])
    create.add_argument("--language", required=True)
    create.add_argument(
        "--gate-override-reason",
        help="human decision: research the niche although it fails a gate (recorded)",
    )
    create.add_argument("--gate-override-by", help="who takes that decision")
    claim = commands.add_parser("claim", help="claim a request (60 minute lease)")
    claim.add_argument("request_id")
    claim.add_argument("--owner", required=True)
    validate = commands.add_parser("validate", help="validate a dossier file offline")
    validate.add_argument("file")
    submit = commands.add_parser("submit", help="validate then send a dossier")
    submit.add_argument("request_id")
    submit.add_argument("file")
    submit.add_argument("--owner", required=True)
    commands.add_parser("schema", help="print the dossier-v2 JSON schema")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client: FlowResearchClient | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "schema":
            _print(DossierV2.model_json_schema())
            return 0
        if args.command in ("validate", "submit"):
            payload = _read(args.file)
            dossier, problems = validate_dossier(payload, now())
            if dossier is None:
                _print({"valid": False, "problems": problems})
                return 1
            if args.command == "validate":
                _print({"valid": True, "problems": []})
                return 0
        api = client or FlowResearchClient.from_settings(Settings())
        if args.command == "create":
            override = None
            if args.gate_override_reason or args.gate_override_by:
                if not (args.gate_override_reason and args.gate_override_by):
                    raise ValueError(
                        "la excepción exige --gate-override-reason y --gate-override-by"
                    )
                override = {"reason": args.gate_override_reason, "by": args.gate_override_by}
            _print(api.create(args.niche_label, args.format, args.language, override))
        elif args.command == "pending":
            _print(api.pending())
        elif args.command == "claim":
            _print(api.claim(args.request_id, args.owner))
        else:
            result = api.submit(args.request_id, args.owner, payload)
            _print(result)
            return 0 if result["accepted"] else 1
        return 0
    except (OSError, ValueError, ApiError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
