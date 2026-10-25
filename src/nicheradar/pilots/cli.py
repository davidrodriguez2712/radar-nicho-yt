# src/nicheradar/pilots/cli.py
"""Acciones del humano sobre los pilotos: lanzar, decidir, cancelar, resumen y tokens.

Imprime JSON y nunca el token de servicio. Un token de canal nuevo se imprime UNA vez (stdout) y
no se puede volver a leer: solo se guarda su huella.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Self

import httpx

from nicheradar.config import Settings


class ApiError(Exception):
    def __init__(self, status: int, detail: object) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


class PilotsClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @classmethod
    def from_settings(cls, config: Settings) -> Self:
        if config.service_token is None:
            raise ValueError("Configura NR_SERVICE_TOKEN")
        token = config.service_token.get_secret_value()
        http = httpx.Client(
            base_url=config.api_url, timeout=30, headers={"Authorization": f"Bearer {token}"}
        )
        return cls(http)

    def call(self, method: str, path: str, body: Any = None) -> Any:
        response = self.http.request(method, "/api/v1" + path, json=body)
        if response.status_code >= 400:
            try:
                detail: object = response.json().get("detail", response.json())
            except (ValueError, AttributeError):
                detail = response.text[:200]
            raise ApiError(response.status_code, detail)
        if response.headers.get("content-type", "").startswith("text/"):
            return response.text
        return response.json() if response.content else None


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pilots")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="listar pilotos")
    listing.add_argument("--status")
    show = commands.add_parser("show", help="detalle, reglas y propuesta")
    show.add_argument("pilot_id")
    lanzar = commands.add_parser(
        "authorize", help="«Lanzar»: congela el paquete de un nicho con dossier"
    )
    lanzar.add_argument("--niche-label", required=True)
    lanzar.add_argument("--format", required=True, choices=["long", "shorts"])
    lanzar.add_argument("--dossier-id", required=True)
    lanzar.add_argument("--low", required=True, type=float)
    lanzar.add_argument("--likely", required=True, type=float)
    lanzar.add_argument("--high", required=True, type=float)
    lanzar.add_argument("--max-videos", required=True, type=int)
    lanzar.add_argument("--basis", required=True)
    lanzar.add_argument("--authorized-by", required=True)
    lanzar.add_argument("--target-channel")
    lanzar.add_argument("--recipe", help="nombre@versión, p. ej. faceless-storytelling@0.1.0")
    lanzar.add_argument(
        "--stop-rules", help="archivo JSON con las reglas (por defecto, las del canal base)"
    )
    lanzar.add_argument("--close-after", type=int, default=2)
    lanzar.add_argument("--valid-days", type=int, default=14)
    lanzar.add_argument("--accept-no-go", action="store_true")
    lanzar.add_argument("--supersedes")
    decide = commands.add_parser("decide", help="decidir: seguir o cerrar")
    decide.add_argument("pilot_id")
    decide.add_argument("decision", choices=["seguir", "cerrar"])
    decide.add_argument("--note", required=True)
    decide.add_argument("--actor", default="humano")
    cancel = commands.add_parser("cancel", help="cancelar antes de ejecutar")
    cancel.add_argument("pilot_id")
    cancel.add_argument("--reason", required=True)
    summary = commands.add_parser("summary", help="resumen de evidencia de un piloto cerrado")
    summary.add_argument("pilot_id")
    summary.add_argument("--out", help="archivo donde guardarlo (por defecto, la salida estándar)")
    issue = commands.add_parser(
        "token-issue", help="emitir un token para un canal (se muestra una vez)"
    )
    issue.add_argument("--channel", required=True)
    issue.add_argument("--label", required=True)
    commands.add_parser("token-list", help="listar tokens (sin el token)")
    revoke = commands.add_parser("token-revoke", help="revocar un token")
    revoke.add_argument("token_id")
    return parser


def _authorize_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "niche_label": args.niche_label,
        "format": args.format,
        "dossier_request_id": args.dossier_id,
        "budget": {
            "currency": "USD",
            "low": args.low,
            "likely": args.likely,
            "high": args.high,
            "max_videos": args.max_videos,
            "basis": args.basis,
        },
        "close_after_failed_milestones": args.close_after,
        "valid_days": args.valid_days,
        "authorized_by": args.authorized_by,
        "accept_no_go": args.accept_no_go,
        "target_channel": args.target_channel,
        "supersedes": args.supersedes,
    }
    if args.recipe:
        name, _, version = args.recipe.partition("@")
        body["recipe"] = {"name": name, "version": version}
    if args.stop_rules:
        body["stop_rules"] = json.loads(Path(args.stop_rules).read_text())
    return body


def main(argv: list[str] | None = None, *, client: PilotsClient | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        api = client or PilotsClient.from_settings(Settings())
        command = args.command
        if command == "list":
            query = f"?status={args.status}" if args.status else ""
            _print(api.call("GET", "/pilots" + query))
        elif command == "show":
            _print(api.call("GET", f"/pilots/{args.pilot_id}"))
        elif command == "authorize":
            _print(api.call("POST", "/pilots", _authorize_body(args)))
        elif command == "decide":
            body = {"decision": args.decision, "note": args.note, "actor": args.actor}
            _print(api.call("POST", f"/pilots/{args.pilot_id}/decision", body))
        elif command == "cancel":
            body = {"reason": args.reason}
            _print(api.call("POST", f"/pilots/{args.pilot_id}/cancel", body))
        elif command == "summary":
            text = api.call("GET", f"/pilots/{args.pilot_id}/closing-summary")
            if args.out:
                Path(args.out).write_text(text)
                _print({"written": args.out})
            else:
                print(text)
        elif command == "token-issue":
            issued = api.call(
                "POST", "/channel-tokens", {"channel_id": args.channel, "label": args.label}
            )
            print("Guarda este token ahora: no se puede volver a mostrar.", file=sys.stderr)
            _print(issued)
        elif command == "token-list":
            _print(api.call("GET", "/channel-tokens"))
        elif command == "token-revoke":
            api.call("DELETE", f"/channel-tokens/{args.token_id}")
            _print({"revoked": args.token_id})
    except ApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
