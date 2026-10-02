"""Explicit connection diagnostic. Does not write credentials or research data."""

import argparse
import asyncio
import getpass
import json
import logging
import sys
from datetime import UTC, datetime

from pydantic import SecretStr, ValidationError

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.vidiq import MCPTransport, VidIQAPIKeyAuth, VidIQProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Conexión propia de NicheRadar con vidIQ")
    remote = parser.add_mutually_exclusive_group()
    remote.add_argument(
        "--check-connection",
        action="store_true",
        help="Autenticar y listar herramientas MCP; no ejecuta herramientas ni investigación",
    )
    remote.add_argument(
        "--check-balance",
        action="store_true",
        help="Consultar únicamente el saldo gratuito; no guarda la respuesta",
    )
    parser.add_argument(
        "--prompt-token", action="store_true", help="Leer una clave API sin eco ni persistencia"
    )
    args = parser.parse_args()
    if args.prompt_token and not (args.check_connection or args.check_balance):
        parser.error("--prompt-token requiere una comprobación remota")
    # Third-party transport exceptions can contain raw server text. Only our
    # allowlisted report leaves this standalone diagnostic process.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        config = Settings()
        token = config.vidiq_token
        if args.prompt_token:
            if not sys.stdin.isatty():
                raise ProviderError("interactive_terminal_required", not_sent=True)
            token = SecretStr(getpass.getpass("Clave API MCP propia de vidIQ (no se guarda): "))
        if not (args.check_connection or args.check_balance):
            print(
                json.dumps(
                    {
                        "status": "configured" if token else "credential_missing",
                        "credential_material_present": token is not None,
                        "network_requests": 0,
                        "tool_calls": 0,
                        "pilot_ready": False,
                    }
                )
            )
            return
        if token is None:
            raise ProviderError("authentication_required", not_sent=True)
        transport = MCPTransport(auth=VidIQAPIKeyAuth(token), enabled=True)
        if args.check_connection:
            report = asyncio.run(transport.inspect_tools())
        else:
            batch = asyncio.run(
                VidIQProvider(transport, "balance-diagnostic").fetch(
                    Operation.BALANCE, {}, datetime.now(UTC)
                )
            )
            if batch.balance is None:
                raise ProviderError("balance_source_mismatch", may_have_charged=True)
            report = {
                "status": "balance_checked",
                "tool_calls": 1,
                "credit_unit": "vidiq_credit",
                "renewable": str(batch.balance.renewable),
                "additional": str(batch.balance.additional),
                "recurring_allocation": str(batch.balance.recurring_allocation),
                "renews_at": batch.balance.renews_at.isoformat()
                if batch.balance.renews_at
                else None,
                "cycle_started_at": batch.balance.cycle_started_at.isoformat()
                if batch.balance.cycle_started_at
                else None,
                "unlimited": batch.balance.unlimited,
                "maximum_call_cost": "0",
            }
    except (ProviderError, ValidationError, EOFError, KeyboardInterrupt) as error:
        code = error.code if isinstance(error, ProviderError) else "invalid_configuration"
        sent = bool(args.check_balance and isinstance(error, ProviderError) and not error.not_sent)
        print(json.dumps({"status": "blocked", "error_code": code, "tool_calls": int(sent)}))
        raise SystemExit(1) from None
    finally:
        logging.disable(previous_logging)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
