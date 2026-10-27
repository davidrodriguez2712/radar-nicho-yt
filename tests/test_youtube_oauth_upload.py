"""`--upload`: el permiso de subida es aparte, opcional y verificable en el token."""

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from scripts import youtube_oauth as oauth
from tests.test_youtube_oauth import GOOD_SCOPE, NOW, client_file, private_dir

CLIENT = {"client_id": "cid", "client_secret": "sec"}
REDIRECT = "http://127.0.0.1:1"


def scopes_of(url: str) -> list[str]:
    return parse_qs(urlparse(url).query)["scope"][0].split()


def test_the_upload_scope_is_separate_and_never_part_of_the_defaults() -> None:
    assert oauth.UPLOAD_SCOPE == "https://www.googleapis.com/auth/youtube.upload"
    assert oauth.UPLOAD_SCOPE not in oauth.SCOPES
    _, challenge = oauth.pkce_pair()
    plain = oauth.authorization_url("cid", REDIRECT, "s", challenge)
    assert scopes_of(plain) == list(oauth.SCOPES)
    full = oauth.authorization_url("cid", REDIRECT, "s", challenge, upload=True)
    assert scopes_of(full) == [*oauth.SCOPES, oauth.UPLOAD_SCOPE]


def test_an_upload_authorization_must_actually_grant_the_upload_scope() -> None:
    read_only = {"refresh_token": "r", "scope": GOOD_SCOPE}
    with_upload = {"refresh_token": "r", "scope": f"{GOOD_SCOPE} {oauth.UPLOAD_SCOPE}"}
    assert oauth.exchange_code(CLIENT, "c", "v", REDIRECT, lambda u, f: with_upload, upload=True)
    with pytest.raises(oauth.OAuthError, match="youtube.upload"):
        oauth.exchange_code(CLIENT, "c", "v", REDIRECT, lambda u, f: read_only, upload=True)
    # Sin --upload no se exige, aunque Google conceda de más.
    assert oauth.exchange_code(CLIENT, "c", "v", REDIRECT, lambda u, f: with_upload)


def test_check_reports_whether_the_stored_token_can_upload(tmp_path: Path) -> None:
    folder = private_dir(tmp_path)
    client = client_file(folder)

    def run(name: str, scope: str) -> dict[str, Any]:
        token = folder / name
        oauth.save_token(token, {"refresh_token": "r", "scope": scope}, NOW, False)

        def get(url: str, bearer: str) -> dict[str, Any]:
            return {"items": []} if "channels" in url else {"rows": []}

        return oauth.check(client, token, lambda url, form: {"access_token": "at"}, get)

    assert run("read.json", GOOD_SCOPE)["upload_scope"] is False
    assert run("full.json", f"{GOOD_SCOPE} {oauth.UPLOAD_SCOPE}")["upload_scope"] is True
