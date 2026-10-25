# tests/test_channel_sync.py
"""channel_sync.py: baja paquetes verificados y sube reportes sin filtrar el token."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from scripts import channel_sync as sync
from tests.test_pilots_api import BASE, CHANNEL, bearer, launched, report, video

pytestmark = pytest.mark.postgres


def adapter(api: TestClient, token: str, tamper: bool = False) -> sync.Http:
    def call(method: str, path: str, body: Any = None) -> tuple[int, Any]:
        response = api.request(method, path, json=body, headers=bearer(token))
        data = response.json() if response.content else None
        if tamper and path.endswith("/package") and isinstance(data, dict):
            data["budget"]["high"] = 9999
        return response.status_code, data

    return call


def test_fetch_stores_a_verified_package_confirms_delivery_and_is_idempotent(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    canal = tmp_path / CHANNEL
    canal.mkdir()
    lines: list[str] = []
    assert sync.fetch(adapter(api, token), canal, CHANNEL, lines.append) == 0
    stored = json.loads((canal / ".nicheradar" / "inbox" / f"{pilot_id}.json").read_text())
    assert stored["pilot_id"] == pilot_id
    assert sync.canonical_sha256(stored) == stored["package_sha256"]
    assert api.get(f"{BASE}/{pilot_id}", headers=bearer(token)).json()["status"] == "entregado"
    again: list[str] = []
    assert sync.fetch(adapter(api, token), canal, CHANNEL, again.append) == 0
    assert again == ["sin pilotos nuevos"]
    assert token not in " ".join(lines + again)


def test_fetch_claims_a_package_without_target_channel_for_this_channel(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    api, pilot_id, token = launched(isolated_engine, target_channel=None)
    canal = tmp_path / CHANNEL
    canal.mkdir()
    assert sync.fetch(adapter(api, token), canal, CHANNEL, lambda _: None) == 0
    assert (canal / ".nicheradar" / "inbox" / f"{pilot_id}.json").exists()
    assert api.get(f"{BASE}/{pilot_id}", headers=bearer(token)).json()["target_channel"] == CHANNEL


def test_fetch_rejects_a_package_whose_hash_does_not_match(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    canal = tmp_path / CHANNEL
    canal.mkdir()
    lines: list[str] = []
    assert sync.fetch(adapter(api, token, tamper=True), canal, CHANNEL, lines.append) == 1
    assert not (canal / ".nicheradar" / "inbox").exists()
    assert "huella" in lines[0]
    status = api.get(f"{BASE}/{pilot_id}", headers=bearer(token)).json()["status"]
    assert status == "autorizado"  # no se confirmó la entrega de un paquete dudoso


def test_fetch_reports_a_bad_token_instead_of_crashing(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    api, _, _ = launched(isolated_engine)
    with pytest.raises(sync.SyncError, match="HTTP 401"):
        sync.fetch(adapter(api, "nrc_falso"), tmp_path, CHANNEL, lambda _: None)


def test_report_sends_outbox_files_and_moves_the_accepted_ones(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    canal = tmp_path / CHANNEL
    canal.mkdir()
    sync.fetch(adapter(api, token), canal, CHANNEL, lambda _: None)
    outbox = canal / ".nicheradar" / "outbox"
    outbox.mkdir()
    (outbox / "ok.json").write_text(json.dumps(report(pilot_id, [video(1)])))
    (outbox / "mal.json").write_text(
        json.dumps(report(pilot_id, [video(2, cost_usd=-1)], reported_at="2026-09-13T12:00:00Z"))
    )
    (outbox / "roto.json").write_text("{no es json")
    lines: list[str] = []
    assert sync.report(adapter(api, token), canal, CHANNEL, lines.append) == 1
    assert (outbox / "sent" / "ok.json").exists() and not (outbox / "ok.json").exists()
    assert (outbox / "mal.json").exists() and (outbox / "roto.json").exists()
    text = "\n".join(lines)
    assert "ok.json: aceptado (en_ejecucion)" in text and "rechazado por el contrato" in text
    assert "no es JSON válido" in text


def test_report_with_an_empty_outbox_is_not_an_error(tmp_path: Path) -> None:
    lines: list[str] = []
    assert sync.report(lambda *_: (500, None), tmp_path, CHANNEL, lines.append) == 0
    assert lines == ["nada que reportar"]


def test_report_refuses_a_file_for_another_channel(tmp_path: Path) -> None:
    outbox = tmp_path / ".nicheradar" / "outbox"
    outbox.mkdir(parents=True)
    other = report("pil_20260913_x", [video(1)], channel_id="canal-otro")
    (outbox / "otro.json").write_text(json.dumps(other))
    called: list[str] = []

    def spy(*_: Any) -> tuple[int, Any]:
        called.append("x")
        return 200, {}

    result = sync.report(spy, tmp_path, CHANNEL, lambda _: None)
    assert result == 1 and called == []


def test_the_token_is_never_sent_over_cleartext_http_to_a_remote_host() -> None:
    with pytest.raises(sync.SyncError, match="HTTP en claro"):
        sync.make_http("http://nicheradar.example.org", "t")
    with pytest.raises(sync.SyncError):
        sync.make_http("ftp://x", "t")
    sync.make_http("http://127.0.0.1:8000", "t")
    sync.make_http("https://nicheradar.example.org", "t")


@pytest.fixture
def redirecting_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/robado")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_redirects_are_not_followed_so_the_token_cannot_leak(redirecting_server: str) -> None:
    status, body = sync.make_http(redirecting_server, "secreto")("GET", "/x", None)
    assert status == 302 and body is None


def test_main_validates_its_environment_without_printing_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    canal = tmp_path / CHANNEL
    canal.mkdir()
    assert sync.main(["fetch", "--channel-dir", str(canal)], env={}) == 2
    assert "NR_SYNC_URL" in capsys.readouterr().err
    odd = tmp_path / "carpeta-rara"
    odd.mkdir()
    env = {"NR_SYNC_URL": "https://x.example", "NR_SYNC_TOKEN": "nrc_muy_secreto"}
    assert sync.main(["fetch", "--channel-dir", str(odd)], env=env) == 2
    captured = capsys.readouterr()
    assert "canal-<nombre>" in captured.err and "nrc_muy_secreto" not in captured.out + captured.err
    assert sync.main(["fetch", "--channel-dir", str(tmp_path / "no-existe")], env=env) == 2
