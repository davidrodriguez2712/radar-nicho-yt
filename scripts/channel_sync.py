#!/usr/bin/env python3
"""Sincroniza un canal de YouTube con NicheRadar. Solo biblioteca estándar (corre en el Mac).

    channel_sync.py fetch  --channel-dir ~/Programming/youtube-project/canal-historias
    channel_sync.py report --channel-dir ~/Programming/youtube-project/canal-historias

Solo este script inicia conexiones; NicheRadar nunca abre una hacia el Mac. Entorno (nunca por
argumento): ``NR_SYNC_URL`` (base de la API) y ``NR_SYNC_TOKEN`` (token DE ESTE CANAL, que no se
imprime ni se escribe en disco). El paquete se verifica por su huella antes de guardarse y la
entrega se confirma después.
Contratos: docs/contracts/pilot-package-v1.md, channel-report-v1.md (largo) y channel-report-v2.md
(Shorts). `report` sube el archivo tal cual: el campo `contract` decide qué validador aplica.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

CHANNEL_RE = re.compile(r"^canal-[a-z0-9-]{1,40}$")
PILOT_RE = re.compile(r"^pil_[0-9]{8}_[a-z0-9-]{1,40}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
TIMEOUT = 30
Http = Callable[[str, str, Any], tuple[int, Any]]  # (método, ruta, cuerpo) -> (estado, json)


class SyncError(Exception):
    pass


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    """Huella de NicheRadar: JSON canónico (claves ordenadas, sin espacios) sin la huella."""
    body = {key: value for key, value in payload.items() if key != "package_sha256"}
    text = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, *args: Any, **kwargs: Any
    ) -> None:  # el token no debe seguir a otro host
        return None


def make_http(base_url: str, token: str) -> Http:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SyncError("NR_SYNC_URL no es una URL válida")
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
        raise SyncError("el token no se envía por HTTP en claro: usa https (o un túnel local)")
    opener = urllib.request.build_opener(_NoRedirect)
    root = base_url.rstrip("/")

    def call(method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(root + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SyncError(f"sin conexión con NicheRadar ({type(error).__name__})") from error
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, None

    return call


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8"
    )
    temp.replace(path)


def _detail(body: Any) -> str:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("code", "error"))
        if isinstance(detail, str):
            return detail[:120]
    return "sin detalle"


def fetch(
    http: Http, channel_dir: Path, channel_id: str, out: Callable[[str], None] = print
) -> int:
    """Baja los paquetes autorizados para este canal, los guarda en inbox/ y confirma la entrega."""
    status, body = http("GET", f"/api/v1/pilots/pending?channel={quote(channel_id)}", None)
    if status != 200 or not isinstance(body, dict):
        raise SyncError(f"no se pudo consultar los pendientes (HTTP {status}: {_detail(body)})")
    inbox = channel_dir / ".nicheradar" / "inbox"
    failures = 0
    for item in body.get("items", []):
        pilot_id = str(item.get("pilot_id", ""))
        if not PILOT_RE.fullmatch(pilot_id):
            out("saltado: un piloto con identificador inválido")
            failures += 1
            continue
        status, package = http("GET", f"/api/v1/pilots/{pilot_id}/package", None)
        if status != 200 or not isinstance(package, dict):
            out(f"{pilot_id}: no se pudo bajar el paquete (HTTP {status}: {_detail(package)})")
            failures += 1
            continue
        digest = canonical_sha256(package)
        if digest != package.get("package_sha256") or digest != item.get("package_sha256"):
            out(f"{pilot_id}: la huella no coincide; el paquete se rechaza")
            failures += 1
            continue
        if package.get("target_channel") not in (None, channel_id):
            out(f"{pilot_id}: el paquete es de otro canal; se rechaza")
            failures += 1
            continue
        target = inbox / f"{pilot_id}.json"
        if (
            not target.exists()
            or json.loads(target.read_text("utf-8")).get("package_sha256") != digest
        ):
            _atomic_write(target, package)
        sent = {"channel_id": channel_id, "package_sha256": digest}
        status, answer = http("POST", f"/api/v1/pilots/{pilot_id}/delivery", sent)
        if status != 200:
            out(f"{pilot_id}: sin confirmar entrega (HTTP {status}: {_detail(answer)})")
            failures += 1
            continue
        out(f"{pilot_id}: entregado y guardado en .nicheradar/inbox/")
    if not body.get("items"):
        out("sin pilotos nuevos")
    return 1 if failures else 0


def report(
    http: Http, channel_dir: Path, channel_id: str, out: Callable[[str], None] = print
) -> int:
    """Sube los reportes de outbox/ y mueve a outbox/sent/ los aceptados."""
    outbox = channel_dir / ".nicheradar" / "outbox"
    files = sorted(outbox.glob("*.json")) if outbox.is_dir() else []
    if not files:
        out("nada que reportar")
        return 0
    failures = 0
    for path in files:
        try:
            payload = json.loads(path.read_text("utf-8"))
        except ValueError:
            out(f"{path.name}: no es JSON válido; se deja sin enviar")
            failures += 1
            continue
        pilot_id = str(payload.get("pilot_id", "")) if isinstance(payload, dict) else ""
        if not PILOT_RE.fullmatch(pilot_id) or payload.get("channel_id") != channel_id:
            out(f"{path.name}: pilot_id o channel_id inválidos para este canal; no se envía")
            failures += 1
            continue
        status, answer = http("POST", f"/api/v1/pilots/{pilot_id}/reports", payload)
        if status == 200:
            (outbox / "sent").mkdir(exist_ok=True)
            path.replace(outbox / "sent" / path.name)
            state = answer.get("pilot_status") if isinstance(answer, dict) else "?"
            out(f"{path.name}: aceptado ({state})")
            for warning in (answer or {}).get("warnings", []):
                out(f"  aviso: {warning}")
        elif status == 422 and isinstance(answer, dict):
            out(f"{path.name}: rechazado por el contrato; se deja en outbox/")
            for problem in answer.get("problems", [])[:10]:
                out(f"  {problem.get('path')}: {problem.get('message')}")
            failures += 1
        else:
            out(f"{path.name}: no se envió (HTTP {status}: {_detail(answer)})")
            failures += 1
    return 1 if failures else 0


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sincroniza un canal con NicheRadar")
    parser.add_argument("command", choices=["fetch", "report"])
    parser.add_argument("--channel-dir", required=True, type=Path)
    parser.add_argument("--channel-id", help="por defecto, el nombre de la carpeta del canal")
    args = parser.parse_args(argv)
    environment = os.environ if env is None else env
    try:
        channel_dir = args.channel_dir.expanduser().resolve()
        channel_id = args.channel_id or channel_dir.name
        if not CHANNEL_RE.fullmatch(channel_id):
            raise SyncError("el canal debe llamarse canal-<nombre> (o indica --channel-id)")
        if not channel_dir.is_dir():
            raise SyncError("la carpeta del canal no existe")
        url, token = environment.get("NR_SYNC_URL"), environment.get("NR_SYNC_TOKEN")
        if not url or not token:
            raise SyncError("faltan NR_SYNC_URL y NR_SYNC_TOKEN en el entorno")
        run = fetch if args.command == "fetch" else report
        return run(make_http(url, token), channel_dir, channel_id)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
