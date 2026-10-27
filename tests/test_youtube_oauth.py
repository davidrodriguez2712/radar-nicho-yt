import json
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from scripts import youtube_oauth as oauth

NOW = datetime(2026, 10, 26, tzinfo=UTC)
GOOD_SCOPE = " ".join(oauth.SCOPES)


def private_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "oauth"
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    return folder


def client_file(folder: Path, body: dict[str, object] | None = None, mode: int = 0o600) -> Path:
    path = folder / "client.json"
    payload = body or {"installed": {"client_id": "cid", "client_secret": "sec"}}
    path.write_text(json.dumps(payload))
    path.chmod(mode)
    return path


def test_the_client_must_be_a_desktop_client_in_private_storage(tmp_path: Path) -> None:
    folder = private_dir(tmp_path)
    assert oauth.load_client(client_file(folder)) == {"client_id": "cid", "client_secret": "sec"}
    with pytest.raises(oauth.OAuthError, match="escritorio"):
        oauth.load_client(client_file(folder, {"web": {"client_id": "x", "client_secret": "y"}}))
    with pytest.raises(oauth.OAuthError, match="privada"):
        oauth.load_client(client_file(folder, mode=0o644))
    folder.chmod(0o755)
    with pytest.raises(oauth.OAuthError, match="privada"):
        oauth.load_client(client_file(folder))


def test_the_authorization_url_is_read_only_offline_and_uses_pkce() -> None:
    _, challenge = oauth.pkce_pair()
    query = parse_qs(
        urlparse(oauth.authorization_url("cid", "http://127.0.0.1:1", "st", challenge)).query
    )
    assert query["scope"] == [GOOD_SCOPE]
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"] and query["state"] == ["st"]
    assert all("upload" not in scope and not scope.endswith("/youtube") for scope in oauth.SCOPES)


def test_the_exchange_requires_a_refresh_token_and_both_read_scopes() -> None:
    client = {"client_id": "cid", "client_secret": "sec"}

    def respond(body: dict[str, str]):  # type: ignore[no-untyped-def]
        return lambda url, form: body

    good = {"refresh_token": "r", "scope": GOOD_SCOPE}
    assert (
        oauth.exchange_code(client, "c", "v", "http://127.0.0.1:1", respond(good))["refresh_token"]
        == "r"
    )
    with pytest.raises(oauth.OAuthError, match="refresh token"):
        oauth.exchange_code(client, "c", "v", "u", respond({"scope": GOOD_SCOPE}))
    with pytest.raises(oauth.OAuthError, match="permisos"):
        oauth.exchange_code(
            client, "c", "v", "u", respond({"refresh_token": "r", "scope": oauth.SCOPES[0]})
        )


def test_the_token_is_stored_0600_and_not_replaced_without_force(tmp_path: Path) -> None:
    folder = private_dir(tmp_path)
    path = folder / "token.json"
    token = {"refresh_token": "secret-refresh", "scope": GOOD_SCOPE, "access_token": "short-lived"}
    oauth.save_token(path, token, NOW, force=False)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    saved = json.loads(path.read_text())
    assert saved["refresh_token"] == "secret-refresh" and "access_token" not in saved
    with pytest.raises(oauth.OAuthError, match="--force"):
        oauth.save_token(path, token, NOW, force=False)
    oauth.save_token(path, token | {"refresh_token": "newer"}, NOW, force=True)
    assert json.loads(path.read_text())["refresh_token"] == "newer"


def test_check_reads_both_apis_without_printing_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = private_dir(tmp_path)
    client = client_file(folder)
    oauth.save_token(folder / "token.json", {"refresh_token": "r", "scope": GOOD_SCOPE}, NOW, False)
    seen: list[str] = []

    def post(url: str, form: Mapping[str, str]) -> dict[str, Any]:
        assert form["grant_type"] == "refresh_token"
        return {"access_token": "at"}

    def get(url: str, bearer: str) -> dict[str, Any]:
        seen.append(url)
        assert bearer == "at"
        if "channels" in url:
            return {"items": [{"id": "UC1", "snippet": {"title": "Gaming"}}]}
        return {"rows": [[10]]}

    result = oauth.check(client, folder / "token.json", post, get)
    assert result == {
        "data_api_ok": True,
        "channels": [{"id": "UC1", "title": "Gaming"}],
        "analytics_api_ok": True,
        "upload_scope": False,
    }
    assert len(seen) == 2
    printed = capsys.readouterr()
    assert "at" not in printed.out + printed.err
