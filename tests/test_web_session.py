# tests/test_web_session.py
import re

import pytest
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app
from nicheradar.web.security import (
    SESSION_COOKIE,
    SESSION_SECONDS,
    LoginLimiter,
    SessionSigner,
)
from tests.web_helpers import PASSWORD, TOKEN, settings

KEY = b"k" * 32


class Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def client(clock: Clock | None = None, **over: object) -> TestClient:
    return TestClient(create_app(settings(**over), clock=clock or Clock()), follow_redirects=False)


def login(web: TestClient, password: str = PASSWORD, **data: str) -> object:
    return web.post("/login", data={"password": password, **data})


def csrf_of(html: str) -> str:
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, html
    return found.group(1)


def test_a_session_round_trips_and_expires() -> None:
    clock = Clock()
    signer = SessionSigner(KEY, clock)
    token = signer.issue()
    session = signer.read(token)
    assert session is not None and session.expires == int(clock.now) + SESSION_SECONDS
    clock.now += SESSION_SECONDS + 1
    assert signer.read(token) is None


def test_a_tampered_or_foreign_session_is_rejected() -> None:
    signer = SessionSigner(KEY, Clock())
    token = signer.issue()
    expires, nonce, mac = token.split(".")
    assert signer.read(f"{int(expires) + 99}.{nonce}.{mac}") is None
    assert signer.read(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
    assert SessionSigner(b"x" * 32, Clock()).read(token) is None
    for junk in (None, "", "abc", "..", "1.2"):
        assert signer.read(junk) is None


def test_the_csrf_token_belongs_to_one_session() -> None:
    signer = SessionSigner(KEY, Clock())
    first = signer.read(signer.issue())
    second = signer.read(signer.issue())
    assert first is not None and second is not None
    assert signer.csrf_valid(first, signer.csrf(first)) is True
    assert signer.csrf_valid(first, signer.csrf(second)) is False
    assert signer.csrf_valid(first, None) is False and signer.csrf_valid(first, "") is False


def test_the_login_limiter_blocks_after_five_failures_and_recovers() -> None:
    clock = Clock()
    limiter = LoginLimiter(clock)
    for _ in range(5):
        assert limiter.blocked("k") is False
        limiter.fail("k")
    assert limiter.blocked("k") is True
    clock.now += 61
    assert limiter.blocked("k") is False
    limiter.fail("k")
    limiter.reset("k")
    assert limiter.blocked("k") is False


def test_the_login_page_shows_the_form_and_hides_nothing_secret() -> None:
    response = client().get("/login")
    assert response.status_code == 200 and 'name="password"' in response.text
    assert PASSWORD not in response.text and TOKEN not in response.text


def test_a_missing_password_means_the_access_is_pending() -> None:
    response = client(dashboard_password=None).get("/login")
    assert response.status_code == 503 and "Acceso pendiente" in response.text


def test_a_correct_password_sets_a_safe_cookie_and_redirects() -> None:
    web = client()
    response = login(web)
    assert response.status_code == 303 and response.headers["location"] == "/"  # type: ignore[attr-defined]
    cookie = response.headers["set-cookie"]  # type: ignore[attr-defined]
    assert cookie.startswith(f"{SESSION_COOKIE}=") and "HttpOnly" in cookie
    assert "SameSite=lax" in cookie and f"Max-Age={SESSION_SECONDS}" in cookie
    assert "Secure" not in cookie


def test_the_cookie_is_secure_behind_the_https_proxy() -> None:
    response = client().post(
        "/login", data={"password": PASSWORD}, headers={"x-forwarded-proto": "https"}
    )
    assert "Secure" in response.headers["set-cookie"]


def test_a_wrong_password_is_refused_and_counted() -> None:
    web = client()
    response = login(web, "x" * 32)
    assert response.status_code == 401 and "Contraseña incorrecta" in response.text  # type: ignore[attr-defined]
    assert SESSION_COOKIE not in response.cookies  # type: ignore[attr-defined]


def test_five_wrong_passwords_block_even_the_right_one() -> None:
    web = client()
    for _ in range(5):
        login(web, "x" * 32)
    response = login(web)
    assert response.status_code == 429 and "Demasiados intentos" in response.text  # type: ignore[attr-defined]


def test_a_protected_page_redirects_to_login_and_remembers_the_destination() -> None:
    response = client().get("/")
    assert response.status_code == 303 and response.headers["location"] == "/login?next=%2F"


def test_an_htmx_request_without_a_session_gets_an_hx_redirect() -> None:
    response = client().get("/", headers={"hx-request": "true"})
    assert response.status_code == 401 and response.headers["hx-redirect"] == "/login"


def test_after_login_the_home_redirects_to_the_subniche_list() -> None:
    web = client()
    login(web)
    response = web.get("/")
    assert response.status_code == 303 and response.headers["location"] == "/subnichos"


@pytest.mark.parametrize("target", ["//evil.test", "https://evil.test", "/\\evil.test", "evil"])
def test_an_external_next_destination_is_ignored(target: str) -> None:
    response = client().post("/login", data={"password": PASSWORD, "next": target})
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_a_local_next_destination_is_followed() -> None:
    response = client().post(
        "/login", data={"password": PASSWORD, "next": "/subnichos?finalistas=1"}
    )
    assert response.headers["location"] == "/subnichos?finalistas=1"


def test_a_session_signed_with_another_token_is_rejected() -> None:
    first = client()
    cookie = first.post("/login", data={"password": PASSWORD}).cookies[SESSION_COOKIE]
    other = TestClient(
        create_app(settings(service_token="z" * 32), clock=Clock()), follow_redirects=False
    )
    other.cookies.set(SESSION_COOKIE, cookie)
    assert other.get("/").status_code == 303


def test_logout_needs_the_csrf_token() -> None:
    web = client()
    login(web)
    assert web.post("/salir", data={"csrf": "wrong"}).status_code == 403
    assert web.post("/salir").status_code == 403


def test_logout_with_a_valid_token_ends_the_session() -> None:
    app = create_app(settings(), clock=Clock())
    web = TestClient(app, follow_redirects=False)
    login(web)
    session = app.state.signer.read(web.cookies[SESSION_COOKIE])
    token = app.state.signer.csrf(session)
    response = web.post("/salir", data={"csrf": token})
    assert response.status_code == 303 and response.headers["location"] == "/login"
    set_cookie = response.headers["set-cookie"].lower()
    assert "expires=" in set_cookie or "max-age=0" in set_cookie


def test_non_ascii_input_is_rejected_without_crashing() -> None:
    signer = SessionSigner(KEY, Clock())
    session = signer.read(signer.issue())
    assert session is not None
    assert signer.read("1.a.é") is None
    assert signer.csrf_valid(session, "é") is False


def test_a_non_ascii_session_cookie_redirects_to_login() -> None:
    response = client().get("/", headers={"cookie": f"{SESSION_COOKIE}=1.a.é".encode()})
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_a_non_ascii_csrf_on_logout_is_forbidden() -> None:
    web = client()
    login(web)
    assert web.post("/salir", data={"csrf": "é"}).status_code == 403
