#!/usr/bin/env python3
"""Autoriza una sola vez el acceso de SOLO LECTURA a un canal de YouTube y guarda el refresh token.

    youtube_oauth.py authorize   # abre el navegador; guarda el token con permisos 0600
    youtube_oauth.py check       # comprueba el token contra la Data API y la Analytics API

Solo biblioteca estándar. Flujo de «app de escritorio» con PKCE y redirección a 127.0.0.1.
El JSON del cliente y el token viven en ``~/Library/Application Support/NicheRadar/oauth/``
(0700 / 0600), nunca en el repo. Ningún secreto, código ni token se imprime.
Guía: docs/guia-oauth-youtube-permanente.md.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import webbrowser
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path.home() / "Library/Application Support/NicheRadar/oauth"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
TIMEOUT = 30
Post = Callable[[str, Mapping[str, str]], dict[str, Any]]
Get = Callable[[str, str], dict[str, Any]]


class OAuthError(Exception):
    pass


def private_path(path: Path, *, directory: bool) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise OAuthError(
            "ruta privada requerida: dueño tú y permisos 0700 (carpeta) o 0600 (archivo)"
        )


def load_client(path: Path) -> dict[str, str]:
    private_path(path.parent, directory=True)
    private_path(path, directory=False)
    data = json.loads(path.read_text())
    client = data.get("installed")
    if not isinstance(client, dict):
        raise OAuthError(
            "el JSON del cliente debe ser de tipo «app de escritorio» (clave installed)"
        )
    for key in ("client_id", "client_secret"):
        if not isinstance(client.get(key), str) or not client[key]:
            raise OAuthError(f"falta {key} en el JSON del cliente")
    if client.get("token_uri", TOKEN_URI) != TOKEN_URI:
        raise OAuthError("token_uri inesperado")
    return {"client_id": client["client_id"], "client_secret": client["client_secret"]}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorization_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URI}?{urlencode(query)}"


def http_post(url: str, form: Mapping[str, str]) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise OAuthError("solo https")
    request = Request(url, data=urlencode(form).encode(), method="POST")
    try:
        with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return dict(json.loads(response.read()))
    except HTTPError as error:
        raise OAuthError(f"Google rechazó la petición (HTTP {error.code})") from None
    except URLError:
        raise OAuthError("no se pudo contactar a Google") from None


def http_get(url: str, bearer: str) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise OAuthError("solo https")
    request = Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return dict(json.loads(response.read()))
    except HTTPError as error:
        raise OAuthError(f"la API respondió HTTP {error.code}") from None
    except URLError:
        raise OAuthError("no se pudo contactar a la API") from None


def exchange_code(
    client: Mapping[str, str], code: str, verifier: str, redirect_uri: str, post: Post
) -> dict[str, Any]:
    token = post(
        TOKEN_URI,
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if not token.get("refresh_token"):
        raise OAuthError(
            "Google no devolvió refresh token: revoca el acceso previo en "
            "myaccount.google.com/permissions y autoriza de nuevo"
        )
    granted = set(str(token.get("scope", "")).split())
    if not set(SCOPES) <= granted:
        raise OAuthError("no se concedieron los dos permisos de solo lectura")
    return token


def save_token(path: Path, token: Mapping[str, Any], now: datetime, force: bool) -> None:
    private_path(path.parent, directory=True)
    record = {
        "refresh_token": token["refresh_token"],
        "scopes": sorted(str(token["scope"]).split()),
        "obtained_at": now.isoformat(),
    }
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise OAuthError("ya existe un token; usa --force para reemplazarlo") from None
    with os.fdopen(descriptor, "w") as file:
        json.dump(record, file)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(path, 0o600)


def access_token(client: Mapping[str, str], path: Path, post: Post) -> str:
    private_path(path.parent, directory=True)
    private_path(path, directory=False)
    refresh = json.loads(path.read_text())["refresh_token"]
    response = post(
        TOKEN_URI,
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
    )
    if not response.get("access_token"):
        raise OAuthError("Google no devolvió access token")
    return str(response["access_token"])


class _Callback(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        type(self).result = query
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Listo. Puedes cerrar esta pestaña y volver a la terminal.".encode())

    def log_message(self, *_: Any) -> None:
        return


def wait_for_code(server: HTTPServer, state: str) -> str:
    server.timeout = 300
    _Callback.result = {}
    server.handle_request()
    result = _Callback.result
    if not result:
        raise OAuthError("tiempo agotado esperando la autorización")
    if result.get("state") != state:
        raise OAuthError("estado de la redirección inválido")
    if "error" in result or not result.get("code"):
        raise OAuthError("la autorización fue rechazada o canceló")
    return result["code"]


def authorize(client_path: Path, token_path: Path, force: bool) -> None:
    client = load_client(client_path)
    server = HTTPServer(("127.0.0.1", 0), _Callback)
    redirect = f"http://127.0.0.1:{server.server_port}"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = authorization_url(client["client_id"], redirect, state, challenge)
    print("Abriendo el navegador. Entra con la cuenta DUEÑA DEL CANAL y acepta los dos permisos.")
    print("Si no se abre, copia esta dirección en el navegador:\n" + url)
    webbrowser.open(url)
    try:
        code = wait_for_code(server, state)
    finally:
        server.server_close()
    token = exchange_code(client, code, verifier, redirect, http_post)
    save_token(token_path, token, datetime.now(UTC), force)
    print(json.dumps({"token_saved": True, "path": str(token_path), "scopes": 2}))


def check(
    client_path: Path, token_path: Path, post: Post = http_post, get: Get = http_get
) -> dict[str, Any]:
    client = load_client(client_path)
    bearer = access_token(client, token_path, post)
    channels = get(CHANNELS_URL, bearer).get("items", [])
    end = datetime.now(UTC).date()
    window = {
        "ids": "channel==MINE",
        "metrics": "views",
        "startDate": str(end - timedelta(days=28)),
        "endDate": str(end),
    }
    report = get(f"{REPORTS_URL}?{urlencode(window)}", bearer)
    return {
        "data_api_ok": True,
        "channels": [
            {"id": c.get("id"), "title": c.get("snippet", {}).get("title")} for c in channels
        ],
        "analytics_api_ok": isinstance(report.get("rows"), list),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["authorize", "check"])
    parser.add_argument("--client", type=Path, default=ROOT / "canal-gaming-client.json")
    parser.add_argument("--token", type=Path, default=ROOT / "canal-gaming-token.json")
    parser.add_argument(
        "--force", action="store_true", help="authorize: reemplazar un token existente"
    )
    args = parser.parse_args()
    if args.action == "authorize":
        authorize(args.client, args.token, args.force)
    else:
        print(json.dumps(check(args.client, args.token)))


if __name__ == "__main__":
    try:
        main()
    except OAuthError as error:
        print(json.dumps({"oauth_failed": str(error)}))
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - nunca mostrar detalles que puedan traer secretos
        print(json.dumps({"oauth_failed": type(error).__name__, "details_withheld": True}))
        sys.exit(1)
