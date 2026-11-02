# Rediseño móvil: cimientos de la web y primera pantalla (Subnichos) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar construida la web móvil nueva (paquete `nicheradar.web`) con sesión segura, el sistema de estilos del Figma, PWA mínima y las pantallas M9 (lista de subnichos) y M10 (ficha del subnicho), para comprobar la fidelidad con el Figma antes de planificar el resto del corte 1.

**Architecture:** Aplicación FastAPI + Jinja2 + HTMX dentro de la misma imagen del dashboard, elegida con `NR_DASHBOARD_UI` (`streamlit` por defecto, `web` para la nueva) en el mismo punto de entrada `nicheradar-dashboard`, mismo puerto 8501. Todos los datos llegan por la API privada con el token de servicio (cliente `httpx` del lado del servidor); la sesión es una cookie firmada con clave derivada del token. Recursos estáticos propios, sin peticiones a terceros.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, python-multipart, HTMX 2.0.4 (vendorizado), fuente Inter (vendorizada), httpx, pytest (`TestClient`, `httpx.MockTransport`), Chrome sin interfaz para las capturas.

**Spec:** `docs/superpowers/specs/2026-11-02-rediseno-movil-web-design.md`. Diseño: Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil», marcos M9 (`29:2`) y M10 (`30:2`).

## Global Constraints

- Misma app de Easypanel `nicheradar-dashboard`, mismo dominio y puerto 8501; el contenedor del dashboard **no** accede a la base de datos: solo `NR_API_URL`, `NR_SERVICE_TOKEN` y `NR_DASHBOARD_PASSWORD`.
- `NR_DASHBOARD_UI` admite `streamlit` o `web`; **por defecto `streamlit`**. Con `streamlit` el comportamiento actual no cambia y no se importa nada de `nicheradar.web`.
- Sesión: cookie `nr_session` firmada, `HttpOnly`, `SameSite=Lax`, vigencia de 12 horas, `Secure` cuando la petición llega por HTTPS (`X-Forwarded-Proto: https` o esquema `https`). La clave se deriva con `HMAC-SHA256(NR_SERVICE_TOKEN, "nicheradar-web-session")`.
- Protección CSRF con token por sesión en todo POST que cambia datos; límite de 5 intentos fallidos de inicio de sesión por minuto.
- Cabeceras: `Content-Security-Policy` solo con recursos propios (`default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY` y `Cache-Control: no-store` en las páginas con datos.
- La web no hace ninguna petición a terceros (sin CDN): HTMX, la fuente Inter, el CSS y los iconos se sirven desde `/static`. Sin atributos `style=""` ni scripts en línea (la CSP los bloquea).
- Todo texto que venga de la API (etiquetas, consultas, títulos de canales, mensajes de error) se escapa siempre: plantillas Jinja2 con autoescape y nunca `|safe` sobre datos de la API.
- Diseño móvil de 390 px de base con la paleta del Figma: Inter; fondo `#fff8f5`; primario `#be123c`; texto `#1c1917`, apagado `#78716c`; tarjetas blancas con borde `#f0e3dc` y radio 16; botones en píldora; etiquetas de 11 px.
- Texto visible en español llano; nombres de código en inglés, como el resto del paquete.
- El service worker guarda en caché **solo recursos estáticos** y la página `/sin-conexión`; nunca datos de la API ni páginas autenticadas.
- `/_stcore/health` se conserva (responde 200 sin sesión): el `healthcheck` de `compose.yaml`, `scripts/smoke_compose.py` y la sonda de `scripts/easypanel_stage.mjs` lo usan.
- Sin cambios de base de datos ni de la API privada.

## Review Focus

1. Texto hostil (`**x**`, `<script>`, `[x](https://evil.test)`) en etiqueta, consultas, familia, títulos de canales y mensajes de error de la API se muestra escapado en la lista y en la ficha (Tasks 5 y 6).
2. Cookie manipulada, vencida o firmada con otro token se rechaza; una petición HTMX sin sesión recibe `401` con `HX-Redirect: /login` (Task 2).
3. `?next=` con un destino externo (`//evil.test`, `https://evil.test`, `/\evil`) se ignora al iniciar sesión (Task 2).
4. POST sin token CSRF o con uno ajeno (investigar, salir) se rechaza con 403 y no llama a la API (Tasks 2 y 6).
5. API caída o lenta: la lista y la ficha muestran un mensaje claro en español con estado 503, no un error 500 ni una traza (Tasks 5 y 6).
6. Parámetros de filtro basura (`familia=<script>`, `estado=zzz`, `finalistas=2`) se ignoran sin error (Task 5).

---

### Task 1: Cimientos, selección de interfaz y cabeceras

**Files:**
- Modify: `pyproject.toml` (dependencias `jinja2`, `python-multipart`), `uv.lock`
- Modify: `src/nicheradar/config.py` (campo `dashboard_ui`)
- Modify: `src/nicheradar/entrypoints.py` (función `dashboard`)
- Create: `src/nicheradar/web/__init__.py`, `src/nicheradar/web/app.py`
- Create: `tests/web_helpers.py`, `tests/test_web_app.py`

**Interfaces:**
- Consumes: `Settings` (`dashboard_host`, `dashboard_port`, `service_token`, `dashboard_password`, `api_url`).
- Produces: `Settings.dashboard_ui: Literal["streamlit", "web"]`; `create_app(config: Settings | None = None, *, transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.time) -> FastAPI` en `nicheradar.web.app` (en esta tarea sin rutas salvo `/_stcore/health`; el parámetro `transport` y `clock` se guardan en `app.state.transport` y `app.state.clock` para las tareas siguientes); en pruebas, `tests/web_helpers.py`: `TOKEN`, `PASSWORD`, `settings(**over) -> Settings`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/web_helpers.py`:

```python
# tests/web_helpers.py
"""Shared helpers for the mobile web tests."""

from pydantic import SecretStr

from nicheradar.config import Settings

TOKEN = "t" * 32
PASSWORD = "p" * 32


def settings(**over: object) -> Settings:
    values: dict[str, object] = {
        "service_token": SecretStr(TOKEN),
        "dashboard_password": SecretStr(PASSWORD),
        "api_url": "http://api.test",
        "dashboard_ui": "web",
    }
    return Settings(**(values | over))  # type: ignore[arg-type]
```

Crear `tests/test_web_app.py`:

```python
# tests/test_web_app.py
import subprocess
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nicheradar import entrypoints
from nicheradar.config import Settings
from nicheradar.web.app import create_app
from tests.web_helpers import settings


def test_the_dashboard_ui_defaults_to_streamlit_and_can_be_switched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NR_DASHBOARD_UI", raising=False)
    assert Settings(_env_file=None).dashboard_ui == "streamlit"  # type: ignore[call-arg]
    monkeypatch.setenv("NR_DASHBOARD_UI", "web")
    assert Settings(_env_file=None).dashboard_ui == "web"  # type: ignore[call-arg]


def test_the_dashboard_entry_point_launches_the_web_app_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setenv("NR_DASHBOARD_UI", "web")
    monkeypatch.setattr(entrypoints.uvicorn, "run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(
        entrypoints.subprocess, "call", lambda *a, **k: pytest.fail("streamlit must not start")
    )
    entrypoints.dashboard()
    (args, kwargs) = calls[0]
    assert args == ("nicheradar.web.app:create_app",)
    assert kwargs["factory"] is True and kwargs["port"] == 8501 and kwargs["access_log"] is False


def test_the_dashboard_entry_point_still_launches_streamlit_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.delenv("NR_DASHBOARD_UI", raising=False)
    monkeypatch.setattr(entrypoints.uvicorn, "run", lambda *a, **k: pytest.fail("web must not start"))

    def fake_call(command: list[str], **_: object) -> int:
        commands.append(command)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    with pytest.raises(SystemExit) as exit_info:
        entrypoints.dashboard()
    assert exit_info.value.code == 0 and "streamlit" in commands[0]


def test_the_health_endpoint_answers_without_a_session() -> None:
    client = TestClient(create_app(settings()))
    response = client.get("/_stcore/health")
    assert response.status_code == 200 and response.text == "ok"


def test_every_response_carries_the_security_headers() -> None:
    response = TestClient(create_app(settings())).get("/_stcore/health")
    policy = response.headers["content-security-policy"]
    for needle in ("default-src 'self'", "script-src 'self'", "style-src 'self'", "frame-ancestors 'none'"):
        assert needle in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_the_api_docs_are_not_exposed() -> None:
    client = TestClient(create_app(settings()))
    assert [client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")] == [404] * 3
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_web_app.py -q 2>&1 | tail -8`
Expected: FAIL (`ModuleNotFoundError: nicheradar.web` y `dashboard_ui` desconocido).

- [ ] **Step 3: Implementar**

En `pyproject.toml`, añadir a `dependencies` (en orden alfabético): `"jinja2>=3.1,<4",` y `"python-multipart>=0.0.20,<1",`. Ejecutar `uv lock` y comprobar `uv sync --locked`.

En `src/nicheradar/config.py`, junto a `dashboard_port`:

```python
    dashboard_ui: Literal["streamlit", "web"] = "streamlit"
```

En `src/nicheradar/entrypoints.py`, al inicio de `dashboard()` tras `config = Settings()`:

```python
    if config.dashboard_ui == "web":
        uvicorn.run(
            "nicheradar.web.app:create_app",
            factory=True,
            host=config.dashboard_host,
            port=config.dashboard_port,
            access_log=False,
        )
        return
```

Crear `src/nicheradar/web/__init__.py` (vacío) y `src/nicheradar/web/app.py`:

```python
# src/nicheradar/web/app.py
"""Mobile web UI (FastAPI + Jinja2 + HTMX) served in place of the Streamlit dashboard."""

import time
from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from nicheradar.config import Settings

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


def create_app(
    config: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    config = config or Settings()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.transport = transport
    app.state.clock = clock

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/_stcore/health", response_class=PlainTextResponse)
    def health() -> str:
        # Same path Streamlit exposes: compose, the smoke test and the proxy probe rely on it.
        return "ok"

    return app
```

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_web_app.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS; ruff y mypy sin errores.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/nicheradar/config.py src/nicheradar/entrypoints.py src/nicheradar/web tests/web_helpers.py tests/test_web_app.py
git commit -m "feat: cimientos de la web móvil, selección de interfaz y cabeceras de seguridad"
```

---

### Task 2: Sesión, inicio de sesión y CSRF

**Files:**
- Create: `src/nicheradar/web/security.py`, `src/nicheradar/web/deps.py`, `src/nicheradar/web/routes_auth.py`
- Create: `src/nicheradar/web/templates/login.html`, `src/nicheradar/web/templates/error.html`, `src/nicheradar/web/templates/base.html` (versión mínima; se amplía en la Task 4)
- Modify: `src/nicheradar/web/app.py` (estado, plantillas, routers, ruta `/`)
- Create: `tests/test_web_session.py`

**Interfaces:**
- Consumes: `create_app`, `settings`, `TOKEN`, `PASSWORD` (Task 1).
- Produces: `SESSION_COOKIE = "nr_session"`, `SESSION_SECONDS`, `Session(expires: int, nonce: str)`, `SessionSigner(key: bytes, clock)` con `from_settings(config, clock) -> SessionSigner | None`, `.issue() -> str`, `.read(token: str | None) -> Session | None`, `.csrf(session) -> str`, `.csrf_valid(session, value) -> bool`; `LoginLimiter(clock, attempts=5, window=60)` con `.blocked(key) -> bool`, `.fail(key)`, `.reset(key)`; en `deps.py`: `current_session(request) -> Session` (dependencia: redirige a `/login?next=…` con 303, o `401` + `HX-Redirect` si es HTMX), `safe_next(value: str | None) -> str`, `render(request, name, context=None, *, status_code=200, session=None)`; en `app.state`: `signer`, `limiter`, `templates`; rutas `GET /login`, `POST /login`, `POST /salir`, `GET /` (redirige a `/subnichos` en este corte).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_web_session.py`:

```python
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
    secure = login(client(), **{})
    assert secure is not None


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
    response = client().post("/login", data={"password": PASSWORD, "next": "/subnichos?finalistas=1"})
    assert response.headers["location"] == "/subnichos?finalistas=1"


def test_a_session_signed_with_another_token_is_rejected() -> None:
    first = client()
    cookie = first.post("/login", data={"password": PASSWORD}).cookies[SESSION_COOKIE]
    other = TestClient(
        create_app(settings(service_token="z" * 32), clock=Clock()), follow_redirects=False
    )
    other.cookies.set(SESSION_COOKIE, cookie)
    assert other.get("/").status_code == 303


def test_logout_needs_the_csrf_token_and_clears_the_cookie() -> None:
    web = client()
    login(web)
    assert web.post("/salir", data={"csrf": "wrong"}).status_code == 403
    page = web.get("/subnichos-demo-csrf")
    assert page.status_code in (200, 404)


def test_logout_with_a_valid_token_ends_the_session() -> None:
    web = client()
    login(web)
    web.app.state.signer  # noqa: B018 - the signer exists once the app is created
    session = web.app.state.signer.read(web.cookies[SESSION_COOKIE])
    token = web.app.state.signer.csrf(session)
    response = web.post("/salir", data={"csrf": token})
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert 'expires=' in response.headers["set-cookie"].lower() or "max-age=0" in response.headers["set-cookie"].lower()
```

(Las dos pruebas de `logout` se pueden afinar al implementar: la intención es que `/salir` sin token válido dé 403, y con token válido borre la cookie y redirija a `/login`. Eliminar `test_logout_needs_the_csrf_token_and_the_cookie` en su forma actual y sustituirla por la prueba del 403 sin la línea de `subnichos-demo-csrf`; la prueba del token válido queda como está.)

Antes de ejecutar, dejar `test_logout_needs_the_csrf_token_and_clears_the_cookie` así:

```python
def test_logout_needs_the_csrf_token() -> None:
    web = client()
    login(web)
    assert web.post("/salir", data={"csrf": "wrong"}).status_code == 403
    assert web.post("/salir").status_code == 403
```

y eliminar la línea `secure = login(client(), **{})` / `assert secure is not None` de `test_a_correct_password_sets_a_safe_cookie_and_redirects`.

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_session.py -q 2>&1 | tail -6`
Expected: FAIL por `ModuleNotFoundError: nicheradar.web.security`.

- [ ] **Step 3: Implementar**

Crear `src/nicheradar/web/security.py`:

```python
# src/nicheradar/web/security.py
"""Signed session cookie, CSRF token and login rate limit for the mobile web."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from nicheradar.config import Settings

SESSION_COOKIE = "nr_session"
SESSION_SECONDS = 12 * 3600
LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class Session:
    expires: int
    nonce: str


class SessionSigner:
    def __init__(self, key: bytes, clock: Callable[[], float] = time.time) -> None:
        self._key = key
        self._clock = clock

    @classmethod
    def from_settings(
        cls, config: Settings, clock: Callable[[], float] = time.time
    ) -> "SessionSigner | None":
        if config.service_token is None:
            return None
        key = hmac.new(
            config.service_token.get_secret_value().encode(),
            b"nicheradar-web-session",
            hashlib.sha256,
        ).digest()
        return cls(key, clock)

    def _mac(self, message: str) -> str:
        return hmac.new(self._key, message.encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        payload = f"{int(self._clock()) + SESSION_SECONDS}.{secrets.token_urlsafe(16)}"
        return f"{payload}.{self._mac(payload)}"

    def read(self, token: str | None) -> Session | None:
        if not token:
            return None
        payload, _, mac = token.rpartition(".")
        if not payload or not hmac.compare_digest(mac, self._mac(payload)):
            return None
        expires, _, nonce = payload.partition(".")
        if not expires.isdigit() or not nonce or int(expires) <= self._clock():
            return None
        return Session(int(expires), nonce)

    def csrf(self, session: Session) -> str:
        return self._mac(f"csrf:{session.nonce}")

    def csrf_valid(self, session: Session, value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(value or "", self.csrf(session))


class LoginLimiter:
    """Counts failed logins in a sliding window. One key is enough: this is a one-owner app."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        attempts: int = LOGIN_ATTEMPTS,
        window: int = LOGIN_WINDOW_SECONDS,
    ) -> None:
        self._clock = clock
        self._attempts = attempts
        self._window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] <= self._clock() - self._window:
            failures.popleft()
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self._attempts

    def fail(self, key: str) -> None:
        self._prune(key).append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
```

Crear `src/nicheradar/web/deps.py`:

```python
# src/nicheradar/web/deps.py
"""Request helpers: session guard, safe redirects and template rendering."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from nicheradar.web.security import SESSION_COOKIE, Session

TEMPLATE_DIR = Path(__file__).parent / "templates"


def make_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATE_DIR))


def safe_next(value: str | None) -> str:
    """Only local paths survive: an open redirect after login must be impossible."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def current_session(request: Request) -> Session:
    signer = request.app.state.signer
    session = signer.read(request.cookies.get(SESSION_COOKIE)) if signer is not None else None
    if session is not None:
        return session
    if request.headers.get("hx-request"):
        raise HTTPException(401, "login required", headers={"HX-Redirect": "/login"})
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    raise HTTPException(
        303, "login required", headers={"Location": f"/login?next={quote(target, safe='')}"}
    )


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    session: Session | None = None,
) -> Response:
    data: dict[str, Any] = {"active_tab": None, "radar_state": None, "csrf_token": None}
    if session is not None:
        data["csrf_token"] = request.app.state.signer.csrf(session)
    data.update(context or {})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, name, data, status_code=status_code)
```

Crear `src/nicheradar/web/routes_auth.py`:

```python
# src/nicheradar/web/routes_auth.py
"""Login, logout and the home redirect."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from nicheradar.web.deps import current_session, render, safe_next
from nicheradar.web.security import SESSION_COOKIE, SESSION_SECONDS, Session

router = APIRouter()
LIMIT_KEY = "owner"


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


@router.get("/login")
def login_form(request: Request, next: str = "/") -> Response:
    if request.app.state.config.dashboard_password is None:
        return render(request, "login.html", {"pending": True}, status_code=503)
    return render(request, "login.html", {"next": safe_next(next)})


@router.post("/login")
def login(
    request: Request,
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    config = request.app.state.config
    signer = request.app.state.signer
    if config.dashboard_password is None or signer is None:
        return render(request, "login.html", {"pending": True}, status_code=503)
    limiter = request.app.state.limiter
    if limiter.blocked(LIMIT_KEY):
        return render(
            request,
            "login.html",
            {"error": "Demasiados intentos. Espera un minuto e inténtalo de nuevo.", "next": "/"},
            status_code=429,
        )
    expected = config.dashboard_password.get_secret_value().encode()
    if not hmac.compare_digest(password.encode(), expected):
        limiter.fail(LIMIT_KEY)
        return render(
            request,
            "login.html",
            {"error": "Contraseña incorrecta.", "next": safe_next(next)},
            status_code=401,
        )
    limiter.reset(LIMIT_KEY)
    response = RedirectResponse(safe_next(next), status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        signer.issue(),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )
    return response


@router.post("/salir")
def logout(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request, "error.html", {"message": "La solicitud no es válida."}, status_code=403
        )
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/")
def home(_session: Annotated[Session, Depends(current_session)]) -> Response:
    # The mobile "Hoy" screen arrives in the next slice; until then the list is the landing page.
    return RedirectResponse("/subnichos", status_code=303)
```

Crear `src/nicheradar/web/templates/base.html` (versión mínima, se amplía en la Task 4):

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{% block title %}NicheRadar{% endblock %}</title>
</head>
<body>
<main>{% block content %}{% endblock %}</main>
</body>
</html>
```

Crear `src/nicheradar/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Entrar · NicheRadar{% endblock %}
{% block content %}
<h1>NicheRadar</h1>
{% if pending %}
<p>Acceso pendiente: configura NR_DASHBOARD_PASSWORD para abrir el observatorio.</p>
{% else %}
<form method="post" action="/login">
  <label for="password">Contraseña de acceso</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <input type="hidden" name="next" value="{{ next }}">
  {% if error %}<p role="alert">{{ error }}</p>{% endif %}
  <button type="submit">Entrar</button>
</form>
{% endif %}
{% endblock %}
```

Crear `src/nicheradar/web/templates/error.html`:

```html
{% extends "base.html" %}
{% block title %}Error · NicheRadar{% endblock %}
{% block content %}
<h1>No se pudo continuar</h1>
<p>{{ message }}</p>
<p><a href="/">Volver al inicio</a></p>
{% endblock %}
```

En `src/nicheradar/web/app.py`: importar `from nicheradar.web import routes_auth`, `from nicheradar.web.deps import make_templates`, `from nicheradar.web.security import LoginLimiter, SessionSigner`; tras `app.state.clock = clock` añadir:

```python
    app.state.signer = SessionSigner.from_settings(config, clock)
    app.state.limiter = LoginLimiter(clock)
    app.state.templates = make_templates()
```

y antes de `return app`: `app.include_router(routes_auth.router)`.

Añadir a las plantillas `login.html` el campo CSRF solo en las pantallas que cambian datos (la plantilla de login no lo necesita: no hay sesión). Para `/salir` el token se obtiene de la sesión (Task 4 lo incluye en la barra).

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_session.py tests/test_web_app.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests/test_web_session.py
git commit -m "feat: sesión firmada, inicio de sesión con límite de intentos y CSRF en la web móvil"
```

---

### Task 3: Cliente de la API

**Files:**
- Create: `src/nicheradar/web/client.py`
- Modify: `src/nicheradar/web/app.py` (guardar `app.state.api`)
- Modify: `tests/web_helpers.py` (utilidades de API simulada)
- Create: `tests/test_web_client.py`

**Interfaces:**
- Consumes: `Settings.api_url`, `Settings.service_token`.
- Produces: `ApiError(kind: str, status: int | None = None, detail: object = None)` con `.message: str` (español); `ApiClient(config, *, transport=None)` con `.request(method: str, path: str, *, params: dict[str, str] | None = None, body: object = None) -> dict[str, Any]` (prefija `/api/v1`, cabecera `Authorization: Bearer`, tiempo de espera de 15 s, `{}` en 204 o sin cuerpo); `kind` ∈ `not_configured`, `unavailable`, `unauthorized`, `not_found`, `conflict`, `invalid`, `error`; `app.state.api`; en pruebas, `tests/web_helpers.py`: `Api(routes)` (llamable como `httpx.MockTransport` handler, con `.calls: list[httpx.Request]`) y `routes: dict[tuple[str, str], tuple[int, object] | Callable[[httpx.Request], httpx.Response]]`, y `make_client(routes, **settings_over) -> TestClient` (autenticado: `follow_redirects=False`, ya con sesión iniciada).

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
import re
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from nicheradar.web.app import create_app

Route = tuple[int, object] | Callable[[httpx.Request], httpx.Response]


class Api:
    """Fake private API: a dict of (method, path) -> (status, json) or a callable."""

    def __init__(self, routes: dict[tuple[str, str], Route] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"detail": "not found"})
        if callable(route):
            return route(request)
        status, body = route
        return httpx.Response(status, json=body)

    def count(self, method: str, path: str) -> int:
        return sum(1 for c in self.calls if (c.method, c.url.path) == (method, path))


def make_client(
    api: Api, clock: Callable[[], float] | None = None, **over: object
) -> TestClient:
    app = create_app(
        settings(**over), transport=httpx.MockTransport(api), **({"clock": clock} if clock else {})
    )
    web = TestClient(app, follow_redirects=False)
    response = web.post("/login", data={"password": PASSWORD})
    assert response.status_code == 303, response.text
    return web


def csrf_of(html: str) -> str:
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, html
    return found.group(1)
```

(En `tests/test_web_session.py`, sustituir la función local `csrf_of` por `from tests.web_helpers import csrf_of` si se prefiere; no es obligatorio.)

Crear `tests/test_web_client.py`:

```python
# tests/test_web_client.py
import httpx
import pytest

from nicheradar.web.client import ApiClient, ApiError
from tests.web_helpers import TOKEN, Api, settings


def client_for(api: Api) -> ApiClient:
    return ApiClient(settings(), transport=httpx.MockTransport(api))


def test_a_request_goes_to_the_private_api_with_the_bearer_token() -> None:
    api = Api({("GET", "/api/v1/subniches"): (200, {"items": []})})
    assert client_for(api).request("GET", "/subniches", params={"include_inactive": "false"}) == {
        "items": []
    }
    call = api.calls[0]
    assert call.headers["authorization"] == f"Bearer {TOKEN}"
    assert call.url.params["include_inactive"] == "false"


def test_a_post_sends_the_json_body() -> None:
    seen: list[bytes] = []

    def echo(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(201, json={"id": "x", "created": True})

    api = Api({("POST", "/api/v1/flow-research"): echo})
    result = client_for(api).request("POST", "/flow-research", body={"niche_label": "subniche:a"})
    assert result["created"] is True and b'"niche_label"' in seen[0]


def test_an_empty_or_204_response_is_an_empty_dict() -> None:
    api = Api({("GET", "/api/v1/x"): lambda request: httpx.Response(204)})
    assert client_for(api).request("GET", "/x") == {}


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "unauthorized"), (403, "unauthorized"), (404, "not_found"), (409, "conflict"),
     (422, "invalid"), (500, "error"), (503, "error")],
)
def test_error_statuses_become_typed_errors_with_a_spanish_message(status: int, kind: str) -> None:
    api = Api({("GET", "/api/v1/x"): (status, {"detail": {"code": "c", "message": "m"}})})
    with pytest.raises(ApiError) as error:
        client_for(api).request("GET", "/x")
    assert error.value.kind == kind and error.value.status == status
    assert error.value.message and "Traceback" not in error.value.message


def test_a_conflict_carries_the_api_detail() -> None:
    api = Api({("POST", "/api/v1/x"): (409, {"detail": {"code": "subniche_not_ready", "message": "Falta algo."}})})
    with pytest.raises(ApiError) as error:
        client_for(api).request("POST", "/x", body={})
    assert error.value.detail == {"code": "subniche_not_ready", "message": "Falta algo."}
    assert error.value.message == "Falta algo."


def test_an_unreachable_api_is_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ApiError) as error:
        client_for(Api({("GET", "/api/v1/x"): boom})).request("GET", "/x")
    assert error.value.kind == "unavailable" and "API no disponible" in error.value.message


def test_a_missing_service_token_is_reported_without_calling_the_api() -> None:
    api = Api()
    client = ApiClient(settings(service_token=None), transport=httpx.MockTransport(api))
    with pytest.raises(ApiError) as error:
        client.request("GET", "/x")
    assert error.value.kind == "not_configured" and api.calls == []
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_client.py -q 2>&1 | tail -6`
Expected: FAIL por `ModuleNotFoundError: nicheradar.web.client`.

- [ ] **Step 3: Implementar**

Crear `src/nicheradar/web/client.py`:

```python
# src/nicheradar/web/client.py
"""Server-side client of the private API. The browser never sees the service token."""

from typing import Any

import httpx

from nicheradar.config import Settings

TIMEOUT_SECONDS = 15
MESSAGES = {
    "not_configured": "Falta configurar la credencial de servicio.",
    "unavailable": "API no disponible. Los datos anteriores no se han actualizado.",
    "unauthorized": "La API rechazó la credencial de servicio. Revisa la configuración.",
    "not_found": "No se encontró lo que buscabas.",
    "conflict": "No se aplicó el cambio: el radar está pausado, la versión cambió o falta algo.",
    "invalid": "Revisa los valores: la solicitud no cumple el formato esperado.",
    "error": "No se pudo completar la solicitud. Revisa la API y la base de datos.",
}


class ApiError(Exception):
    def __init__(self, kind: str, status: int | None = None, detail: object = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.status = status
        self.detail = detail

    @property
    def message(self) -> str:
        if self.kind == "conflict" and isinstance(self.detail, dict):
            text = self.detail.get("message")
            if isinstance(text, str) and text:
                return text
        return MESSAGES.get(self.kind, MESSAGES["error"])


def _kind(status: int) -> str:
    if status in (401, 403):
        return "unauthorized"
    return {404: "not_found", 409: "conflict", 422: "invalid"}.get(status, "error")


class ApiClient:
    def __init__(self, config: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: object = None,
    ) -> dict[str, Any]:
        token = self._config.service_token
        if token is None:
            raise ApiError("not_configured")
        try:
            with httpx.Client(
                base_url=self._config.api_url,
                timeout=TIMEOUT_SECONDS,
                transport=self._transport,
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
            ) as client:
                response = client.request(method, "/api/v1" + path, params=params, json=body)
        except httpx.HTTPError as error:
            raise ApiError("unavailable") from error
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise ApiError(_kind(response.status_code), response.status_code, detail)
        if response.status_code == 204 or not response.content:
            return {}
        result: dict[str, Any] = response.json()
        return result
```

En `src/nicheradar/web/app.py`: importar `from nicheradar.web.client import ApiClient` y, junto a las otras asignaciones de estado, `app.state.api = ApiClient(config, transport=transport)`.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_client.py tests/test_web_session.py tests/test_web_app.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web/client.py src/nicheradar/web/app.py tests/web_helpers.py tests/test_web_client.py
git commit -m "feat: cliente de la API privada para la web móvil"
```

---

### Task 4: Sistema de estilos, plantilla base y PWA

**Files:**
- Create: `src/nicheradar/web/static/css/app.css`, `src/nicheradar/web/static/js/app.js`, `src/nicheradar/web/static/js/htmx.min.js`, `src/nicheradar/web/static/js/VENDOR.md`
- Create: `src/nicheradar/web/static/fonts/InterVariable.woff2`, `src/nicheradar/web/static/fonts/INTER-LICENSE.txt`
- Create: `src/nicheradar/web/static/icons/icon.svg`, `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`
- Create: `src/nicheradar/web/static/manifest.webmanifest`, `src/nicheradar/web/static/sw.js`
- Create: `src/nicheradar/web/templates/components.html`, `src/nicheradar/web/templates/offline.html`
- Modify: `src/nicheradar/web/templates/base.html`, `login.html`, `error.html` (usan la base completa)
- Modify: `src/nicheradar/web/deps.py` (`radar_state`, `render` completo), `src/nicheradar/web/app.py` (estáticos, `/sw.js`, `/sin-conexión`)
- Create: `tests/test_web_assets.py`

**Interfaces:**
- Consumes: `create_app`, `render`, `ApiClient` (Tasks 1–3).
- Produces: base `base.html` con bloques `title` y `content` y variables `active_tab` (`"nichos"` etc.), `radar_state` (`"paused"`, `"active"` o `None`), `csrf_token`; macros en `components.html`: `chip(text, kind="neutral")`, `button(label, kind="primary", href=None, disabled=False, type="button")`, `topbar(radar_state, csrf_token)`, `bottomnav(active)`, `segmented(options)` con `options = [(label, href|None, selected: bool, count|None)]`; rutas `/static/...` (archivos), `/sw.js`, `/sin-conexión` (sin sesión); `radar_state(request) -> str | None` en `deps.py` con caché de 30 s; clases CSS: `.app .topbar .brand .spacer .page .bottomnav .tab .tab--on .tab--soon .chip .chip--neutral|rose|blue|green|amber .btn .btn--primary|secondary|danger .btn[disabled] .card .eyebrow .h1 .h2 .caption .lead .muted .segmented .segmented__item .segmented__item--on .filters .pill .pill--on .pill--select .tags .income .income__label .income__value .stats .rows .row .acc .note .note--amber .note--green .note--rose .rank`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_web_assets.py`:

```python
# tests/test_web_assets.py
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from nicheradar.web import app as web_app
from nicheradar.web.app import create_app
from tests.web_helpers import Api, make_client, settings

ROOT = Path(web_app.__file__).parent
STATIC = ROOT / "static"


def anonymous() -> TestClient:
    return TestClient(create_app(settings()), follow_redirects=False)


def test_the_stylesheet_the_font_and_htmx_are_served_from_the_app() -> None:
    web = anonymous()
    for path, kind in (
        ("/static/css/app.css", "text/css"),
        ("/static/js/htmx.min.js", "javascript"),
        ("/static/js/app.js", "javascript"),
        ("/static/fonts/InterVariable.woff2", "font/woff2"),
        ("/static/icons/icon-192.png", "image/png"),
        ("/static/icons/icon-512.png", "image/png"),
        ("/static/icons/apple-touch-icon.png", "image/png"),
    ):
        response = web.get(path)
        assert response.status_code == 200, path
        assert kind in response.headers["content-type"], path
    assert "cache-control" not in {k.lower() for k in web.get("/static/css/app.css").headers} or (
        web.get("/static/css/app.css").headers["cache-control"] != "no-store"
    )


def test_the_manifest_declares_a_standalone_app_with_the_brand_colors() -> None:
    manifest = json.loads(anonymous().get("/static/manifest.webmanifest").text)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    assert manifest["theme_color"] == "#be123c" and manifest["background_color"] == "#fff8f5"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes


def test_the_service_worker_is_served_at_the_root_scope_and_caches_only_static_files() -> None:
    response = anonymous().get("/sw.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    assert response.headers["service-worker-allowed"] == "/"
    body = response.text
    assert "/static/" in body and "/sin-conexión" in body
    assert "/api/" not in body  # never caches API data


def test_the_offline_page_is_public() -> None:
    response = anonymous().get("/sin-conexión")
    assert response.status_code == 200 and "Sin conexión" in response.text


def test_no_template_stylesheet_or_script_reaches_a_third_party() -> None:
    offenders: list[str] = []
    files = [*ROOT.glob("templates/**/*.html"), STATIC / "css/app.css", STATIC / "js/app.js", STATIC / "sw.js", STATIC / "manifest.webmanifest"]
    for path in files:
        for found in re.findall(r"https?://[^\s\"')]+", path.read_text()):
            offenders.append(f"{path.name}: {found}")
    assert offenders == []


def test_the_templates_use_no_inline_styles_or_scripts() -> None:
    for path in ROOT.glob("templates/**/*.html"):
        text = path.read_text()
        assert not re.search(r"\sstyle\s*=", text), path.name
        assert not re.search(r"<script(?![^>]*\ssrc=)", text), path.name
        assert not re.search(r"\son[a-z]+\s*=", text), path.name


def test_an_authenticated_page_uses_the_base_with_the_bar_the_nav_and_the_pwa_links() -> None:
    api = Api({("GET", "/api/v1/status"): (200, {"radar_paused": True})})
    web = make_client(api)
    page = web.get("/sin-conexión")  # public, but the base is shared
    assert 'rel="manifest"' in page.text and 'name="theme-color"' in page.text
    assert "/static/css/app.css" in page.text and "/static/js/htmx.min.js" in page.text
    assert "htmx-config" in page.text and "includeIndicatorStyles" in page.text


def test_the_radar_badge_reflects_the_api_state_and_is_cached() -> None:
    api = Api({("GET", "/api/v1/status"): (200, {"radar_paused": True})})
    now = [1_000.0]
    web = make_client(api, clock=lambda: now[0])
    # The shell pages call the status endpoint through render(); two renders inside 30 s hit it once.
    from nicheradar.web.deps import radar_state

    class Req:  # minimal stand-in carrying the app state
        app = web.app

    assert radar_state(Req()) == "paused"  # type: ignore[arg-type]
    assert radar_state(Req()) == "paused"  # type: ignore[arg-type]
    assert api.count("GET", "/api/v1/status") == 1
    now[0] += 31
    api.routes[("GET", "/api/v1/status")] = (200, {"radar_paused": False})
    assert radar_state(Req()) == "active"  # type: ignore[arg-type]


def test_a_status_failure_hides_the_badge_instead_of_breaking_the_page() -> None:
    from nicheradar.web.deps import radar_state

    web = make_client(Api())  # /status answers 404
    class Req:
        app = web.app

    assert radar_state(Req()) is None  # type: ignore[arg-type]
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_assets.py -q 2>&1 | tail -6`
Expected: FAIL (no existen los estáticos ni `/sw.js`).

- [ ] **Step 3: Conseguir los recursos vendorizados**

HTMX (sin CDN en producción; se descarga una vez al repo):

```bash
mkdir -p src/nicheradar/web/static/{css,js,fonts,icons}
curl -fsSL https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o src/nicheradar/web/static/js/htmx.min.js
shasum -a 256 src/nicheradar/web/static/js/htmx.min.js
```

Fuente Inter (SIL Open Font License) desde la publicación oficial:

```bash
mkdir -p /tmp/inter-dl && cd /tmp/inter-dl
curl -fsSL -o Inter.zip https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip
unzip -q -o Inter.zip
find . -name "InterVariable.woff2" -o -name "LICENSE.txt" | head
cd -
cp "$(find /tmp/inter-dl -name InterVariable.woff2 | head -1)" src/nicheradar/web/static/fonts/InterVariable.woff2
cp "$(find /tmp/inter-dl -name LICENSE.txt | head -1)" src/nicheradar/web/static/fonts/INTER-LICENSE.txt
shasum -a 256 src/nicheradar/web/static/fonts/InterVariable.woff2
```

Si una descarga falla (red, archivo con otro nombre), reportar `BLOCKED` con el detalle: no sustituir por otra fuente ni por un CDN.

Crear `src/nicheradar/web/static/js/VENDOR.md` con las versiones y las huellas reales calculadas arriba:

```markdown
# Recursos de terceros incluidos

| Recurso | Versión | Origen | SHA-256 | Licencia |
|---|---|---|---|---|
| htmx.min.js | 2.0.4 | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | <huella calculada> | BSD Zero Clause |
| fonts/InterVariable.woff2 | 4.0 | https://github.com/rsms/inter/releases/tag/v4.0 | <huella calculada> | SIL Open Font License 1.1 (`fonts/INTER-LICENSE.txt`) |
```

(Sustituir `<huella calculada>` por las huellas reales. Este archivo no entra en el análisis de URLs externas de la prueba porque vive en `static/js/VENDOR.md`, no es plantilla ni CSS.)

Iconos: crear `src/nicheradar/web/static/icons/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#be123c"/>
  <circle cx="256" cy="256" r="150" fill="none" stroke="#ffffff" stroke-width="26" opacity="0.55"/>
  <circle cx="256" cy="256" r="84" fill="none" stroke="#ffffff" stroke-width="26"/>
  <circle cx="256" cy="256" r="26" fill="#ffffff"/>
  <line x1="256" y1="256" x2="376" y2="150" stroke="#ffffff" stroke-width="26" stroke-linecap="round"/>
</svg>
```

y generar los PNG con Chrome sin interfaz (macOS):

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ICON=$(pwd)/src/nicheradar/web/static/icons
for size in 192 512 180; do
  printf '<!doctype html><body style="margin:0"><img src="file://%s/icon.svg" width="%s" height="%s"></body>' "$ICON" "$size" "$size" > /tmp/icon-$size.html
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
    --window-size=$size,$size --screenshot=/tmp/icon-$size.png "file:///tmp/icon-$size.html"
done
cp /tmp/icon-192.png "$ICON/icon-192.png"; cp /tmp/icon-512.png "$ICON/icon-512.png"; cp /tmp/icon-180.png "$ICON/apple-touch-icon.png"
file "$ICON"/*.png
```

(Los HTML temporales usan un atributo `style` pero viven en `/tmp`, no en las plantillas.) Comprobar que cada PNG tiene el tamaño esperado (`file` lo informa).

- [ ] **Step 4: Escribir el CSS, la plantilla base, las macros, el service worker y las rutas**

Crear `src/nicheradar/web/static/css/app.css`:

```css
@font-face{font-family:"Inter";src:url("../fonts/InterVariable.woff2") format("woff2");font-weight:100 900;font-style:normal;font-display:swap}
:root{--bg:#fff8f5;--ink:#1c1917;--muted:#78716c;--primary:#be123c;--white:#fff;--line:#f0e3dc;--line2:#e7d5cc;--soft:#f5e4dc;--pale:#faf3ef;--rose:#ffe4e6;--rose-line:#fda4af;--amber:#fef3c7;--amber-ink:#92400e;--amber-line:#fcd34d;--blue:#dbeafe;--blue-ink:#1d4ed8;--green:#dcfce7;--green-ink:#166534;--neutral:#f5f5f4;--neutral-ink:#57534e;--faint:#d6c2b8;--off:#e8d3c8}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:400 14px/1.4 "Inter",system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100dvh}
a{color:inherit}
.app{max-width:480px;margin:0 auto;min-height:100dvh;display:flex;flex-direction:column;background:var(--bg)}
.topbar{display:flex;align-items:center;gap:8px;padding:14px 16px;background:var(--white);border-bottom:1px solid var(--line)}
.brand{font-weight:700;font-size:17px;color:var(--primary);text-decoration:none}
.spacer{flex:1}
.page{flex:1;display:flex;flex-direction:column;gap:14px;padding:16px}
.bottomnav{position:sticky;bottom:0;display:flex;padding:8px 8px calc(8px + env(safe-area-inset-bottom));background:var(--white);border-top:1px solid var(--line)}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:4px 0;color:var(--muted);text-decoration:none}
.tab__icon{font-size:18px;line-height:22px}
.tab__label{font-size:11px;font-weight:500}
.tab--on{color:var(--primary)}
.tab--on .tab__label{font-weight:600}
.tab--soon{opacity:.55;pointer-events:none}
h1,.h1{margin:0;font-size:28px;line-height:34px;font-weight:700}
.h1--md{font-size:26px;line-height:32px}
h2,.h2{margin:0;font-size:18px;line-height:24px;font-weight:700}
.eyebrow{font-size:11px;font-weight:600;color:var(--primary);letter-spacing:.02em;text-transform:uppercase}
.caption{font-size:12px;color:var(--muted)}
.lead{font-size:14px;color:var(--muted)}
.muted{color:var(--muted)}
.chip{display:inline-flex;align-items:center;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:500;white-space:nowrap}
.chip--neutral{background:var(--neutral);color:var(--neutral-ink)}
.chip--rose{background:var(--rose);color:var(--primary)}
.chip--blue{background:var(--blue);color:var(--blue-ink)}
.chip--green{background:var(--green);color:var(--green-ink)}
.chip--amber{background:var(--amber);color:var(--amber-ink)}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.btn{display:flex;align-items:center;justify-content:center;width:100%;padding:13px 16px;border-radius:99px;border:1px solid transparent;font:600 14px/1.2 "Inter",system-ui,sans-serif;text-decoration:none;cursor:pointer}
.btn--primary{background:var(--primary);color:var(--white)}
.btn--secondary{background:var(--white);color:var(--ink);border-color:var(--line2)}
.btn--danger{background:var(--white);color:var(--primary);border-color:var(--rose-line)}
.btn[disabled],.btn--disabled{background:var(--off);color:var(--white);border-color:transparent;cursor:not-allowed}
.card{display:flex;flex-direction:column;gap:8px;padding:16px;background:var(--white);border:1px solid var(--line);border-radius:16px}
.card__title{display:flex;align-items:center;gap:8px}
.card__name{font-size:16px;font-weight:600;text-decoration:none}
.rank{font-size:18px;color:var(--faint)}
.income{display:flex;flex-direction:column}
.income__label{font-size:11px;color:var(--muted)}
.income__value{font-size:24px;line-height:30px;font-weight:700;color:var(--primary)}
.income__value--lg{font-size:30px;line-height:36px}
.stats{display:flex;gap:18px;margin:0}
.stats dt{font-size:11px;color:var(--muted)}
.stats dd{margin:0;font-size:14px;font-weight:600}
.segmented{display:flex;gap:2px;padding:4px;background:var(--soft);border-radius:99px}
.segmented__item{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:10px 12px;border-radius:99px;font-size:13px;font-weight:500;color:var(--muted);text-decoration:none}
.segmented__item--on{background:var(--white);color:var(--ink);font-weight:600}
.segmented__count{font-size:12px;font-weight:600;color:var(--primary)}
.filters{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}
.filters::-webkit-scrollbar{display:none}
.pill{position:relative;display:inline-flex;align-items:center;flex:none;padding:9px 14px;border:1px solid var(--line2);border-radius:99px;background:var(--white);font:400 13px/1.2 "Inter",system-ui,sans-serif;color:var(--ink);white-space:nowrap}
.pill input{position:absolute;opacity:0;pointer-events:none}
.pill--on,.pill:has(input:checked){background:var(--rose);border-color:var(--primary);color:var(--primary);font-weight:600}
.pill--select{appearance:none;-webkit-appearance:none;padding-right:14px}
.countline{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:var(--muted)}
.countline strong{color:var(--ink)}
.rows{display:flex;flex-direction:column;gap:8px}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;background:var(--pale);border-radius:10px}
.row__label{font-size:13px;color:var(--muted)}
.row__value{font-size:15px;font-weight:700}
.list{display:flex;flex-direction:column}
.list__item{display:flex;flex-direction:column;gap:4px;padding:10px 0;border-bottom:1px solid var(--line)}
.list__item:last-child{border-bottom:0}
.list__name{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600}
.acc{background:var(--white);border:1px solid var(--line2);border-radius:14px}
.acc summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;cursor:pointer;list-style:none}
.acc summary::-webkit-details-marker{display:none}
.acc__title{font-size:14px;font-weight:600}
.acc__sub{font-size:12px;color:var(--muted)}
.acc__body{display:flex;flex-direction:column;gap:6px;padding:0 16px 14px;font-size:13px;color:var(--muted)}
.note{display:flex;flex-direction:column;gap:6px;padding:12px 14px;border-radius:12px;font-size:12px}
.note__title{font-size:13px;font-weight:600}
.note--amber{background:var(--amber);color:var(--amber-ink)}
.note--green{background:var(--green);color:var(--green-ink)}
.note--rose{background:var(--rose);color:var(--primary)}
.field{display:flex;flex-direction:column;gap:6px}
.field label{font-size:13px;font-weight:600}
.field input{padding:13px 14px;border:1px solid var(--line2);border-radius:12px;background:var(--white);font:400 14px "Inter",system-ui,sans-serif}
.field input:focus-visible,.btn:focus-visible,.pill:focus-within,.tab:focus-visible,a:focus-visible,.acc summary:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
@media (prefers-reduced-motion:no-preference){.card,.btn,.pill{transition:border-color .15s,background-color .15s}}
```

Crear `src/nicheradar/web/static/js/app.js`:

```js
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  });
}
```

Crear `src/nicheradar/web/static/sw.js`:

```js
const CACHE = "nicheradar-static-v1";
const OFFLINE = "/sin-conexión";
const PRECACHE = [
  OFFLINE,
  "/static/css/app.css",
  "/static/js/htmx.min.js",
  "/static/js/app.js",
  "/static/fonts/InterVariable.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
  }
});
```

Crear `src/nicheradar/web/static/manifest.webmanifest`:

```json
{
  "name": "NicheRadar",
  "short_name": "NicheRadar",
  "description": "Radar de nichos y pilotos de YouTube",
  "lang": "es",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#fff8f5",
  "theme_color": "#be123c",
  "icons": [
    {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
  ]
}
```

Reemplazar `src/nicheradar/web/templates/base.html`:

```html
{% from "components.html" import topbar, bottomnav %}
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#be123c">
<meta name="htmx-config" content='{"includeIndicatorStyles": false, "allowEval": false}'>
<link rel="manifest" href="/static/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<link rel="stylesheet" href="/static/css/app.css">
<title>{% block title %}NicheRadar{% endblock %}</title>
<script src="/static/js/htmx.min.js" defer></script>
<script src="/static/js/app.js" defer></script>
</head>
<body>
<div class="app">
{% if not bare %}{{ topbar(radar_state, csrf_token) }}{% endif %}
<main class="page">{% block content %}{% endblock %}</main>
{% if not bare %}{{ bottomnav(active_tab) }}{% endif %}
</div>
</body>
</html>
```

Crear `src/nicheradar/web/templates/components.html`:

```html
{% macro chip(text, kind="neutral") -%}
<span class="chip chip--{{ kind }}">{{ text }}</span>
{%- endmacro %}

{% macro button(label, kind="primary", href=None, disabled=False, type="button") -%}
{% if href and not disabled %}<a class="btn btn--{{ kind }}" href="{{ href }}">{{ label }}</a>
{% else %}<button class="btn btn--{{ kind }}" type="{{ type }}"{% if disabled %} disabled{% endif %}>{{ label }}</button>{% endif %}
{%- endmacro %}

{% macro topbar(radar_state, csrf_token) -%}
<header class="topbar">
  <a class="brand" href="/">NicheRadar</a>
  <span class="spacer"></span>
  {% if radar_state == "paused" %}{{ chip("Radar pausado", "amber") }}{% elif radar_state == "active" %}{{ chip("Radar activo", "green") }}{% endif %}
  {% if csrf_token %}
  <form method="post" action="/salir"><input type="hidden" name="csrf" value="{{ csrf_token }}"><button class="btn btn--secondary" type="submit">Salir</button></form>
  {% endif %}
</header>
{%- endmacro %}

{% macro bottomnav(active) -%}
<nav class="bottomnav" aria-label="Principal">
  {% for key, icon, label, href in [("hoy", "◉", "Hoy", "/"), ("nichos", "▦", "Nichos", "/subnichos"), ("pilotos", "◫", "Pilotos", None), ("mas", "⋯", "Más", None)] %}
  {% if href %}
  <a class="tab{% if key == active %} tab--on{% endif %}" href="{{ href }}"{% if key == active %} aria-current="page"{% endif %}><span class="tab__icon" aria-hidden="true">{{ icon }}</span><span class="tab__label">{{ label }}</span></a>
  {% else %}
  <span class="tab tab--soon" aria-disabled="true" title="Próximamente"><span class="tab__icon" aria-hidden="true">{{ icon }}</span><span class="tab__label">{{ label }}</span></span>
  {% endif %}
  {% endfor %}
</nav>
{%- endmacro %}

{% macro segmented(options) -%}
<div class="segmented" role="tablist">
  {% for label, href, selected, count in options %}
  {% if href %}<a class="segmented__item{% if selected %} segmented__item--on{% endif %}" href="{{ href }}"{% if selected %} aria-current="page"{% endif %}>{{ label }}{% if count is not none %} <span class="segmented__count">{{ count }}</span>{% endif %}</a>
  {% else %}<span class="segmented__item" aria-disabled="true" title="Próximamente">{{ label }}</span>{% endif %}
  {% endfor %}
</div>
{%- endmacro %}
```

Crear `src/nicheradar/web/templates/offline.html`:

```html
{% extends "base.html" %}
{% set bare = true %}
{% block title %}Sin conexión · NicheRadar{% endblock %}
{% block content %}
<p class="eyebrow">NicheRadar</p>
<h1 class="h1">Sin conexión</h1>
<p class="lead">No hay conexión con el servidor. Los datos no se guardan en el teléfono: vuelve a intentarlo cuando tengas red.</p>
<a class="btn btn--primary" href="/">Reintentar</a>
{% endblock %}
```

Actualizar `login.html` y `error.html` para la base completa: `login.html` con `{% set bare = true %}` tras el `extends`, clases `field`, `btn btn--primary`, `note note--rose` para el error y `h1 class="h1"`; `error.html` con `<h1 class="h1">No se pudo continuar</h1>`, `<p class="lead">{{ message }}</p>` y `<a class="btn btn--secondary" href="/">Volver al inicio</a>`. Ejemplo de `login.html`:

```html
{% extends "base.html" %}
{% set bare = true %}
{% block title %}Entrar · NicheRadar{% endblock %}
{% block content %}
<p class="eyebrow">NicheRadar</p>
<h1 class="h1">Entrar</h1>
{% if pending %}
<div class="note note--amber"><span class="note__title">Acceso pendiente</span>Configura NR_DASHBOARD_PASSWORD para abrir el observatorio.</div>
{% else %}
<form class="page" method="post" action="/login">
  <div class="field"><label for="password">Contraseña de acceso</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required></div>
  <input type="hidden" name="next" value="{{ next }}">
  {% if error %}<div class="note note--rose" role="alert">{{ error }}</div>{% endif %}
  <button class="btn btn--primary" type="submit">Entrar</button>
</form>
{% endif %}
{% endblock %}
```

(La prueba de la Task 2 espera el texto «Acceso pendiente» y «Contraseña incorrecta»: se conservan.)

En `src/nicheradar/web/deps.py`, añadir `radar_state` y completar `render` para incluir el estado del radar en las páginas con sesión:

```python
from nicheradar.web.client import ApiError

RADAR_TTL_SECONDS = 30


def radar_state(request: Request) -> str | None:
    """'paused', 'active' or None when the API cannot say; cached so each page is not a status call."""
    app = request.app
    cache: dict[str, Any] = app.state.radar_cache
    now = app.state.clock()
    if cache["until"] > now:
        value: str | None = cache["value"]
        return value
    try:
        data = app.state.api.request("GET", "/status")
        value = "paused" if data.get("radar_paused") else "active"
    except ApiError:
        value = None
    cache.update(until=now + RADAR_TTL_SECONDS, value=value)
    return value
```

y en `render`, dentro de `if session is not None:` añadir `data["radar_state"] = radar_state(request)`.

En `src/nicheradar/web/app.py`: importar `from pathlib import Path`, `from fastapi.staticfiles import StaticFiles`, `from fastapi.responses import FileResponse`; añadir `app.state.radar_cache = {"until": 0.0, "value": None}`; montar los estáticos y definir las rutas públicas:

```python
STATIC_DIR = Path(__file__).parent / "static"
...
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/sw.js")
    def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.get("/sin-conexión")
    def offline(request: Request) -> Response:
        return render(request, "offline.html")
```

(importar `render` de `nicheradar.web.deps`). La ruta `/sin-conexión` va sin sesión; `render` sin sesión no llama a la API.

- [ ] **Step 5: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_assets.py tests/test_web_session.py tests/test_web_client.py tests/test_web_app.py -q 2>&1 | tail -6; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/web tests/test_web_assets.py
git commit -m "feat: sistema de estilos del Figma, plantilla base y PWA mínima"
```

---

### Task 5: Pantalla M9, lista de subnichos

**Files:**
- Create: `src/nicheradar/web/format.py`, `src/nicheradar/web/subniches.py`, `src/nicheradar/web/routes_subniches.py`
- Create: `src/nicheradar/web/templates/subnichos/lista.html`, `src/nicheradar/web/templates/subnichos/_lista.html`
- Modify: `src/nicheradar/web/app.py` (registrar el router)
- Modify: `tests/web_helpers.py` (datos de ejemplo)
- Create: `tests/test_web_format.py`, `tests/test_web_subniches_list.py`

**Interfaces:**
- Consumes: `render`, `current_session`, `ApiClient`, `ApiError`, macros `chip`, `button`, `segmented` (Tasks 2–4); API `GET /api/v1/subniches?include_inactive=true|false` → `{"items": [{"slug","label","family","parent_niche_slug","status","finalist","language","format","queries","measurement": {...}|null,"research": {"id","status","language","created_at"}|null}]}`.
- Produces: `es_int(value: float) -> str`, `usd_range(low: str | None, high: str | None) -> str | None`, `compact(value: float | int | None) -> str`, `local_datetime(value: str, timezone: str) -> str` en `format.py`; `FAMILIES`, `STATUS_LABELS`, `RESEARCH`, `Filters` (dataclass: `finalistas: bool`, `familia: str`, `estado: str`, `inactivos: bool`), `parse_filters(params: Mapping[str, str]) -> Filters`, `card(item: dict, rank: int) -> dict`, `list_view(items: list[dict], filters: Filters) -> dict` en `subniches.py`; rutas `GET /subnichos` (página completa o, con `HX-Request`, solo `subnichos/_lista.html`); en pruebas, `subniche_item(...)`, `measurement(...)`, `research(...)` en `tests/web_helpers.py`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def measurement(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "measured_at": "2026-10-31T12:00:00Z",
        "included": 29,
        "stable_channels": 18,
        "volatile_channels": 11,
        "traction_channels": 19,
        "large_channels": 4,
        "excluded": {"language": 1},
        "income_low": "672.80",
        "income_high": "1681.99",
        "rpm_source": "inherited:wildlife_documentaries",
        "signal": "estimable",
    }
    return base | over


def research(status: str = "listo", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "status": status,
        "language": "en",
        "created_at": "2026-11-02T02:05:45Z",
    }
    return base | over


def subniche_item(slug: str = "prehistoric_creatures", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "slug": slug,
        "label": slug.replace("_", " ").title(),
        "family": "nature_science",
        "parent_niche_slug": "wildlife_documentaries",
        "status": "active",
        "finalist": True,
        "language": "en",
        "format": "long",
        "queries": ["prehistoric creatures documentary", "extinct animals that once ruled earth"],
        "measurement": measurement(),
        "research": None,
    }
    return base | over
```

Crear `tests/test_web_format.py`:

```python
# tests/test_web_format.py
import pytest

from nicheradar.web.format import compact, es_int, local_datetime, usd_range


@pytest.mark.parametrize(
    ("value", "text"), [(0, "0"), (999.4, "999"), (1629.23, "1.629"), (1234567.8, "1.234.568")]
)
def test_es_int_uses_dots_for_thousands(value: float, text: str) -> None:
    assert es_int(value) == text


def test_usd_range_rounds_and_handles_missing_values() -> None:
    assert usd_range("672.80", "1681.99") == "US$ 673 – 1.682"
    assert usd_range(None, "10") is None and usd_range("10", None) is None


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, "—"), (987, "987"), (39600, "39,6 mil"), (5580483, "5,6 M"), (14600000, "14,6 M")],
)
def test_compact_abbreviates_counts_in_spanish(value: float | None, text: str) -> None:
    assert compact(value) == text


def test_local_datetime_converts_to_the_configured_timezone() -> None:
    assert local_datetime("2026-10-31T12:00:00Z", "America/Lima") == "31/10/2026 07:00"
    assert local_datetime("2026-10-31T12:00:00+00:00", "UTC") == "31/10/2026 12:00"
```

Crear `tests/test_web_subniches_list.py`:

```python
# tests/test_web_subniches_list.py
from tests.web_helpers import HOSTILE, Api, make_client, measurement, research, subniche_item

LIST = ("GET", "/api/v1/subniches")


def api_with(*items: dict[str, object]) -> Api:
    return Api({LIST: (200, {"items": list(items)}), ("GET", "/api/v1/status"): (200, {"radar_paused": True})})


def test_the_list_requires_a_session() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    response = TestClient(create_app(settings()), follow_redirects=False).get("/subnichos")
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_the_list_renders_one_card_per_subniche_with_the_figma_content() -> None:
    api = api_with(
        subniche_item("prehistoric_creatures", research=research("listo")),
        subniche_item(
            "forgotten_history", label="Forgotten History Events", family="history",
            measurement=measurement(income_low="1629.23", income_high="3723.96",
                                    traction_channels=11, stable_channels=10, large_channels=9),
        ),
    )
    page = make_client(api).get("/subnichos")
    assert page.status_code == 200
    text = page.text
    assert "Subnichos" in text and "Ingreso típico por canal al mes" in text
    assert "US$ 673 – 1.682" in text and "US$ 1.629 – 3.724" in text
    assert "Ciencia y naturaleza" in text and "Historia" in text
    assert "Dossier listo" in text and "Sin investigar" in text
    assert "Despegaron" in text and "Constantes" in text and "Grandes" in text
    assert "Finalista" in text
    assert text.count('class="card') == 2
    assert api.calls[-1].url.params["include_inactive"] == "false" or any(
        c.url.params.get("include_inactive") == "false" for c in api.calls
    )


def test_the_buttons_follow_the_research_state() -> None:
    api = api_with(
        subniche_item("a_new", research=None),
        subniche_item("a_running", research=research("en_curso")),
        subniche_item("a_done", research=research("listo")),
        subniche_item("a_paused", status="paused", research=None),
        subniche_item("a_unmeasured", measurement=None, research=None),
    )
    text = make_client(api).get("/subnichos").text
    assert text.count("Investigar</a>") == 1
    assert "Ver estado" in text and text.count("Ver subnicho") == 3
    assert 'href="/subnichos/a_new"' in text


def test_an_unmeasured_subniche_says_so_instead_of_showing_numbers() -> None:
    text = make_client(api_with(subniche_item("x_one", measurement=None))).get("/subnichos").text
    assert "Todavía sin medición" in text and "Ingreso típico" not in text


def test_the_count_line_and_the_segmented_selector() -> None:
    api = api_with(subniche_item("a_one"), subniche_item("b_two", finalist=False))
    text = make_client(api).get("/subnichos").text
    assert "1 finalistas de 2" in text or "1 finalista de 2" in text
    assert "Nichos" in text and "Subnichos" in text and 'aria-current="page"' in text


def test_filters_narrow_the_cards_in_the_web_layer() -> None:
    api = api_with(
        subniche_item("a_one", label="Alpha", family="history", finalist=True),
        subniche_item("b_two", label="Beta", family="scifi", finalist=False),
        subniche_item("c_three", label="Gamma", family="history", finalist=False, status="proposed"),
    )
    web = make_client(api)
    assert "Beta" not in web.get("/subnichos", params={"familia": "history"}).text
    only = web.get("/subnichos", params={"finalistas": "1"}).text
    assert "Alpha" in only and "Beta" not in only and "Gamma" not in only
    state = web.get("/subnichos", params={"estado": "proposed"}).text
    assert "Gamma" in state and "Alpha" not in state


def test_the_inactive_toggle_asks_the_api_for_inactive_hypotheses() -> None:
    api = api_with(subniche_item("a_one"))
    make_client(api).get("/subnichos", params={"inactivos": "1"})
    assert api.calls[-1].url.params["include_inactive"] == "true" or any(
        c.url.params.get("include_inactive") == "true" for c in api.calls
    )


def test_junk_filter_values_are_ignored_without_an_error() -> None:
    api = api_with(subniche_item("a_one", label="Alpha"))
    web = make_client(api)
    for params in (
        {"familia": "<script>alert(1)</script>"},
        {"estado": "zzz"},
        {"finalistas": "2"},
        {"inactivos": "yes", "familia": "x" * 500},
    ):
        response = web.get("/subnichos", params=params)
        assert response.status_code == 200 and "Alpha" in response.text, params
        assert "<script>alert(1)</script>" not in response.text


def test_an_htmx_request_gets_only_the_list_fragment() -> None:
    api = api_with(subniche_item("a_one", label="Alpha"))
    response = make_client(api).get("/subnichos", headers={"hx-request": "true"})
    assert response.status_code == 200 and "Alpha" in response.text
    assert "<html" not in response.text and 'class="topbar"' not in response.text


def test_hostile_api_text_is_escaped_everywhere_in_the_list() -> None:
    api = api_with(
        subniche_item("hostile_one", label=HOSTILE, family=HOSTILE, language="en"),
    )
    text = make_client(api).get("/subnichos").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_an_unavailable_api_shows_a_clear_message_with_503() -> None:
    import httpx

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({LIST: boom, ("GET", "/api/v1/status"): (200, {"radar_paused": False})})
    response = make_client(api).get("/subnichos")
    assert response.status_code == 503 and "API no disponible" in response.text
    assert "Traceback" not in response.text


def test_an_empty_list_has_its_own_message() -> None:
    text = make_client(api_with()).get("/subnichos").text
    assert "Todavía no hay subnichos" in text
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_format.py tests/test_web_subniches_list.py -q 2>&1 | tail -6`
Expected: FAIL por `ModuleNotFoundError: nicheradar.web.format`.

- [ ] **Step 3: Implementar el formato y el modelo de vista**

Crear `src/nicheradar/web/format.py`:

```python
# src/nicheradar/web/format.py
"""Spanish number, money and date formatting for the mobile web."""

from datetime import datetime
from zoneinfo import ZoneInfo


def es_int(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def usd_range(low: str | None, high: str | None) -> str | None:
    if low is None or high is None:
        return None
    return f"US$ {es_int(float(low))} – {es_int(float(high))}"


def compact(value: float | int | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}".replace(".", ",") + " M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}".replace(".", ",") + " mil"
    return es_int(number)


def local_datetime(value: str, timezone: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(timezone))
    return moment.strftime("%d/%m/%Y %H:%M")
```

Crear `src/nicheradar/web/subniches.py`:

```python
# src/nicheradar/web/subniches.py
"""View models for the sub-niche screens: what the templates show, never raw API payloads."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

from nicheradar.web.format import usd_range

FAMILIES = {
    "nature_science": "Ciencia y naturaleza",
    "history": "Historia",
    "tech_engineering": "Ingeniería",
    "scifi": "Ciencia ficción",
    "business": "Negocios",
    "mysteries": "Misterios",
    "stories": "Historias narradas",
    "black_audience": "Audiencia afro",
}
STATUS_LABELS = {
    "active": "Activos",
    "proposed": "Propuestos",
    "paused": "Pausados",
    "archived": "Archivados",
}
RESEARCH = {
    None: ("Sin investigar", "neutral"),
    "pendiente": ("En cola", "amber"),
    "en_curso": ("Investigando", "blue"),
    "listo": ("Dossier listo", "green"),
    "rechazado": ("Rechazada", "rose"),
}


@dataclass(frozen=True)
class Filters:
    finalistas: bool = False
    familia: str = ""
    estado: str = ""
    inactivos: bool = False


def parse_filters(params: Mapping[str, str]) -> Filters:
    estado = params.get("estado", "")
    return Filters(
        finalistas=params.get("finalistas") == "1",
        familia=params.get("familia", "")[:40],
        estado=estado if estado in STATUS_LABELS else "",
        inactivos=params.get("inactivos") == "1",
    )


def card(item: dict[str, Any], rank: int) -> dict[str, Any]:
    measured = item["measurement"]
    research = item["research"]
    state = research["status"] if research else None
    text, kind = RESEARCH.get(state, ("Investigación", "neutral"))
    if item["status"] != "active" or measured is None:
        button = ("Ver subnicho", "secondary")
    elif state in (None, "rechazado"):
        button = ("Investigar", "primary")
    elif state in ("pendiente", "en_curso"):
        button = ("Ver estado", "secondary")
    else:
        button = ("Ver subnicho", "secondary")
    return {
        "slug": item["slug"],
        "label": item["label"],
        "rank": rank,
        "finalist": item["finalist"],
        "family": FAMILIES.get(item["family"], item["family"]),
        "language": str(item["language"]).upper(),
        "research_text": text,
        "research_kind": kind,
        "income": usd_range(measured["income_low"], measured["income_high"]) if measured else None,
        "stats": (
            [
                ("Despegaron", measured["traction_channels"]),
                ("Constantes", measured["stable_channels"]),
                ("Grandes", measured["large_channels"]),
            ]
            if measured
            else None
        ),
        "button_label": button[0],
        "button_kind": button[1],
        "href": f"/subnichos/{quote(item['slug'], safe='')}",
    }


def list_view(items: list[dict[str, Any]], filters: Filters) -> dict[str, Any]:
    families = sorted({str(item["family"]) for item in items})
    familia = filters.familia if filters.familia in families else ""
    shown = [
        item
        for item in items
        if (not familia or item["family"] == familia)
        and (not filters.estado or item["status"] == filters.estado)
        and (not filters.finalistas or item["finalist"])
    ]
    return {
        "cards": [card(item, rank) for rank, item in enumerate(shown, 1)],
        "total": len(items),
        "finalists": sum(1 for item in items if item["finalist"]),
        "familias": [(family, FAMILIES.get(family, family)) for family in families],
        "estados": list(STATUS_LABELS.items()),
        "filtros": replace(filters, familia=familia),
    }
```

- [ ] **Step 4: Implementar la ruta y las plantillas**

Crear `src/nicheradar/web/routes_subniches.py`:

```python
# src/nicheradar/web/routes_subniches.py
"""Sub-niche screens: M9 list (this task) and M10 card (next task)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render
from nicheradar.web.security import Session
from nicheradar.web.subniches import list_view, parse_filters

router = APIRouter()


@router.get("/subnichos")
def subniche_list(
    request: Request, session: Annotated[Session, Depends(current_session)]
) -> Response:
    filters = parse_filters(request.query_params)
    htmx = bool(request.headers.get("hx-request"))
    template = "subnichos/_lista.html" if htmx else "subnichos/lista.html"
    try:
        data = request.app.state.api.request(
            "GET", "/subniches", params={"include_inactive": "true" if filters.inactivos else "false"}
        )
    except ApiError as error:
        return render(
            request,
            template,
            {"active_tab": "nichos", "error": error.message, "view": None, "filtros": filters},
            status_code=503,
            session=session,
        )
    view = list_view(data["items"], filters)
    return render(
        request,
        template,
        {"active_tab": "nichos", "error": None, "view": view, "filtros": view["filtros"]},
        session=session,
    )
```

En `src/nicheradar/web/app.py`: importar `from nicheradar.web import routes_auth, routes_subniches` y añadir `app.include_router(routes_subniches.router)`.

Crear `src/nicheradar/web/templates/subnichos/lista.html`:

```html
{% extends "base.html" %}
{% from "components.html" import segmented %}
{% block title %}Subnichos · NicheRadar{% endblock %}
{% block content %}
{{ segmented([("Nichos", None, False, None), ("Subnichos", "/subnichos", True, view.total if view else None)]) }}
<h1 class="h1">Subnichos</h1>
<p class="caption">Ideas de nicho que medimos en YouTube. El ingreso es una estimación de un canal típico, no lo que ganarías.</p>
<form class="filters" id="filtros" method="get" action="/subnichos"
      hx-get="/subnichos" hx-trigger="change" hx-target="#contenido" hx-swap="innerHTML" hx-push-url="true">
  <label class="pill{% if filtros.finalistas %} pill--on{% endif %}"><input type="checkbox" name="finalistas" value="1"{% if filtros.finalistas %} checked{% endif %}>Finalistas</label>
  <select class="pill pill--select" name="familia" aria-label="Familia">
    <option value="">Familia ▾</option>
    {% if view %}{% for key, label in view.familias %}<option value="{{ key }}"{% if filtros.familia == key %} selected{% endif %}>{{ label }}</option>{% endfor %}{% endif %}
  </select>
  <select class="pill pill--select" name="estado" aria-label="Estado">
    <option value="">Estado ▾</option>
    {% if view %}{% for key, label in view.estados %}<option value="{{ key }}"{% if filtros.estado == key %} selected{% endif %}>{{ label }}</option>{% endfor %}{% endif %}
  </select>
  <label class="pill{% if filtros.inactivos %} pill--on{% endif %}"><input type="checkbox" name="inactivos" value="1"{% if filtros.inactivos %} checked{% endif %}>Ver pausados y archivados</label>
  <noscript><button class="btn btn--secondary" type="submit">Aplicar</button></noscript>
</form>
<div id="contenido" class="page">
{% include "subnichos/_lista.html" %}
</div>
{% endblock %}
```

Crear `src/nicheradar/web/templates/subnichos/_lista.html`:

```html
{% from "components.html" import chip, button %}
{% if error %}
<div class="note note--rose" role="alert"><span class="note__title">No se pudo cargar</span>{{ error }}</div>
{% elif not view.cards and not view.total %}
<p class="lead">Todavía no hay subnichos. Cárgalos con <code>scripts/subniche.py import</code>.</p>
{% else %}
<div class="countline"><span><strong>{{ view.finalists }}</strong> finalistas de {{ view.total }}</span><span>Finalistas y tracción ↓</span></div>
{% for c in view.cards %}
<article class="card">
  <div class="card__title"><span class="rank">{{ c.rank }}</span><a class="card__name" href="{{ c.href }}">{{ c.label }}</a></div>
  <div class="tags">
    {% if c.finalist %}{{ chip("Finalista", "rose") }}{% endif %}
    {{ chip(c.family, "neutral") }}{{ chip(c.language, "blue") }}{{ chip(c.research_text, c.research_kind) }}
  </div>
  {% if c.income %}
  <div class="income"><span class="income__label">Ingreso típico por canal al mes</span><span class="income__value">{{ c.income }}</span></div>
  <dl class="stats">{% for label, value in c.stats %}<div><dt>{{ label }}</dt><dd>{{ value }}</dd></div>{% endfor %}</dl>
  {% else %}
  <p class="muted">Todavía sin medición.</p>
  {% endif %}
  {{ button(c.button_label, c.button_kind, href=c.href) }}
</article>
{% else %}
<p class="lead">Ningún subnicho coincide con los filtros.</p>
{% endfor %}
<p class="caption">«Despegaron»: canales pequeños con un video muy por encima de su tamaño. «Constantes»: canales con vistas estables. «Grandes»: canales grandes en el tema.</p>
{% endif %}
```

(La pantalla de lista de la Figma M9 abre con el selector «Nichos | Subnichos», el título, la explicación, los filtros, el conteo y las tarjetas: el orden de las plantillas lo respeta. Si Jinja rechaza `{% for %}…{% else %}` combinado con `button(...)` en una sola línea, separar el macro en una variable local.)

- [ ] **Step 5: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_format.py tests/test_web_subniches_list.py tests/test_web_assets.py tests/test_web_session.py tests/test_web_client.py tests/test_web_app.py -q 2>&1 | tail -6; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_format.py tests/test_web_subniches_list.py
git commit -m "feat: pantalla M9, lista de subnichos de la web móvil"
```

---

### Task 6: Pantalla M10, ficha del subnicho e iniciar investigación

**Files:**
- Modify: `src/nicheradar/web/subniches.py` (añadir `detail_view`, `NOT_READY`, `AVISOS`, `LANGUAGE_NAMES`), `src/nicheradar/web/routes_subniches.py` (ficha y POST)
- Create: `src/nicheradar/web/templates/subnichos/ficha.html`
- Modify: `tests/web_helpers.py` (`subniche_card`)
- Create: `tests/test_web_subniche_card.py`

**Interfaces:**
- Consumes: `Filters`/`card` (Task 5), `ApiClient`, `render`, `current_session`, `local_datetime`, `compact`, `usd_range` (Tasks 2–5); API `GET /api/v1/subniches/{slug}` → `{"hypothesis": {...,"queries": [...]}, "measurement": {...}|null, "channels": [{"channel_id","title","subscribers","monthly_long_views","income_low","income_high","traction","flags"}], "channels_available": bool, "research": {...}|null}`; `POST /api/v1/flow-research` body `{"niche_label": "subniche:<slug>", "format", "language"}` → `{"id","created": bool,...}` (409 con `detail.code = subniche_not_ready` si no se puede).
- Produces: `NOT_READY = "La hipótesis debe estar activa y tener al menos una medición."`, `LANGUAGE_NAMES`, `AVISOS: dict[str, tuple[str, str]]` (clave → (texto, tipo de nota)), `detail_view(card: dict, timezone: str) -> dict`; rutas `GET /subnichos/{slug}` (acepta `?aviso=<clave>`; solo claves de `AVISOS`) y `POST /subnichos/{slug}/investigar` (campo `csrf`; redirige 303 a la ficha con `?aviso=creada|existente|no-lista|error`); en pruebas `subniche_card(...)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
def channel(title: str = "WUFO TV", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "channel_id": "UC" + "a" * 22,
        "title": title,
        "subscribers": 39600,
        "monthly_long_views": 5580483,
        "income_low": "11160.97",
        "income_high": "27902.42",
        "traction": True,
        "flags": [],
    }
    return base | over


def subniche_card(slug: str = "prehistoric_creatures", **over: object) -> dict[str, object]:
    item = subniche_item(slug)
    base: dict[str, object] = {
        "hypothesis": {k: item[k] for k in item if k not in ("measurement", "research")},
        "measurement": item["measurement"],
        "channels": [channel(), channel("Curious Fing", subscribers=16800, monthly_long_views=1376974)],
        "channels_available": True,
        "research": None,
    }
    return base | over
```

Crear `tests/test_web_subniche_card.py`:

```python
# tests/test_web_subniche_card.py
import httpx

from tests.web_helpers import (
    HOSTILE, Api, channel, csrf_of, make_client, measurement, research, subniche_card, subniche_item,
)

SLUG = "prehistoric_creatures"
CARD = ("GET", f"/api/v1/subniches/{SLUG}")
ORDER = ("POST", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")


def api_with(card: dict[str, object], **extra: object) -> Api:
    routes: dict[tuple[str, str], object] = {CARD: (200, card), STATUS: (200, {"radar_paused": True})}
    routes.update(extra)  # type: ignore[arg-type]
    return Api(routes)  # type: ignore[arg-type]


def test_the_card_shows_the_measurement_channels_and_the_start_button() -> None:
    text = make_client(api_with(subniche_card())).get(f"/subnichos/{SLUG}").text
    assert "Prehistoric Creatures" in text and "SUBNICHO" in text.upper()
    assert "US$ 673 – 1.682" in text and "mediana" in text.lower()
    assert "Medimos 29 canales" in text and "31/10/2026" in text
    assert "Pequeños que despegaron" in text and "Excluidos por idioma" in text
    assert "WUFO TV" in text and "39,6 mil suscriptores" in text and "5,6 M de vistas al mes" in text
    assert "Iniciar investigación en inglés" in text
    assert 'name="csrf"' in text and f'action="/subnichos/{SLUG}/investigar"' in text


def test_the_measurement_time_uses_the_configured_timezone() -> None:
    text = make_client(api_with(subniche_card())).get(f"/subnichos/{SLUG}").text
    assert "31/10/2026 07:00" in text  # 12:00 UTC in America/Lima


def test_expired_channel_data_is_declared_not_hidden() -> None:
    card = subniche_card(channels=[], channels_available=False)
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "vencieron" in text and "WUFO TV" not in text


def test_an_unmeasured_subniche_has_no_start_button() -> None:
    card = subniche_card(measurement=None)
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "Todavía no medimos este subnicho" in text and "Iniciar investigación" not in text


def test_a_non_active_subniche_disables_the_button_with_the_reason() -> None:
    item = subniche_item(SLUG, status="paused")
    card = subniche_card(hypothesis={k: item[k] for k in item if k not in ("measurement", "research")})
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "La hipótesis debe estar activa y tener al menos una medición." in text
    assert "<button" in text and " disabled" in text


def test_a_running_investigation_disables_the_button() -> None:
    card = subniche_card(research=research("en_curso"))
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "investigación en curso" in text.lower() and " disabled" in text


def test_a_finished_investigation_shows_its_state_without_a_start_button() -> None:
    card = subniche_card(research=research("listo"))
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "Dossier listo" in text and "Iniciar investigación" not in text


def test_a_rejected_investigation_can_be_retried() -> None:
    card = subniche_card(research=research("rechazado"))
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "Reintentar investigación en inglés" in text


def test_the_notice_comes_only_from_a_fixed_set_of_keys() -> None:
    web = make_client(api_with(subniche_card()))
    assert "Investigación creada" in web.get(f"/subnichos/{SLUG}", params={"aviso": "creada"}).text
    page = web.get(f"/subnichos/{SLUG}", params={"aviso": HOSTILE})
    assert page.status_code == 200 and "<script>" not in page.text and "evil.test" not in page.text


def test_an_unknown_subniche_is_a_404_page() -> None:
    api = Api({CARD: (404, {"detail": {"code": "not_found", "message": "Hipótesis no encontrada."}}),
               STATUS: (200, {"radar_paused": True})})
    response = make_client(api).get(f"/subnichos/{SLUG}")
    assert response.status_code == 404 and "No se encontró" in response.text


def test_an_unavailable_api_shows_a_clear_message_with_503() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    response = make_client(Api({CARD: boom, STATUS: (200, {"radar_paused": True})})).get(f"/subnichos/{SLUG}")
    assert response.status_code == 503 and "API no disponible" in response.text


def test_hostile_text_is_escaped_in_the_card() -> None:
    item = subniche_item(SLUG, label=HOSTILE, family=HOSTILE, queries=[HOSTILE])
    card = subniche_card(
        hypothesis={k: item[k] for k in item if k not in ("measurement", "research")},
        channels=[channel(HOSTILE)],
        measurement=measurement(rpm_source=HOSTILE, excluded={HOSTILE: 3}),
    )
    text = make_client(api_with(card)).get(f"/subnichos/{SLUG}").text
    assert "<script>alert(1)</script>" not in text
    assert text.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 3


def test_starting_the_research_posts_the_hypothesis_own_format_and_language() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"id": "r1", "created": True})

    api = api_with(subniche_card(), **{ORDER: accept})
    web = make_client(api)
    token = csrf_of(web.get(f"/subnichos/{SLUG}").text)
    response = web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": token, "language": "es"})
    assert response.status_code == 303
    assert response.headers["location"] == f"/subnichos/{SLUG}?aviso=creada"
    import json

    assert json.loads(bodies[0]) == {
        "niche_label": f"subniche:{SLUG}", "format": "long", "language": "en",
    }


def test_an_existing_order_is_reported_as_such() -> None:
    api = api_with(subniche_card(), **{ORDER: (200, {"id": "r1", "created": False})})
    web = make_client(api)
    token = csrf_of(web.get(f"/subnichos/{SLUG}").text)
    response = web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": token})
    assert response.headers["location"].endswith("?aviso=existente")


def test_an_api_conflict_and_an_api_failure_map_to_clear_notices() -> None:
    not_ready = {"detail": {"code": "subniche_not_ready", "message": "x"}}
    web = make_client(api_with(subniche_card(), **{ORDER: (409, not_ready)}))
    token = csrf_of(web.get(f"/subnichos/{SLUG}").text)
    assert web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": token}).headers["location"].endswith("?aviso=no-lista")
    web2 = make_client(api_with(subniche_card(), **{ORDER: (500, {"detail": "x"})}))
    token2 = csrf_of(web2.get(f"/subnichos/{SLUG}").text)
    assert web2.post(f"/subnichos/{SLUG}/investigar", data={"csrf": token2}).headers["location"].endswith("?aviso=error")


def test_a_post_without_or_with_a_foreign_csrf_token_never_reaches_the_api() -> None:
    api = api_with(subniche_card(), **{ORDER: (201, {"id": "r1", "created": True})})
    web = make_client(api)
    assert web.post(f"/subnichos/{SLUG}/investigar").status_code == 403
    assert web.post(f"/subnichos/{SLUG}/investigar", data={"csrf": "wrong"}).status_code == 403
    assert api.count("POST", "/api/v1/flow-research") == 0
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_subniche_card.py -q 2>&1 | tail -6`
Expected: FAIL (404 en `/subnichos/{slug}`).

- [ ] **Step 3: Implementar el modelo de vista de la ficha**

Añadir a `src/nicheradar/web/subniches.py` (con `from nicheradar.web.format import compact, local_datetime, usd_range`):

```python
NOT_READY = "La hipótesis debe estar activa y tener al menos una medición."
LANGUAGE_NAMES = {
    "en": "inglés", "es": "español", "pt": "portugués", "ru": "ruso", "de": "alemán", "fr": "francés",
}
EXCLUSIONS = {
    "language": "por idioma",
    "no_recent_videos": "sin videos recientes",
    "harvest_failed": "con lectura fallida",
}
AVISOS = {
    "creada": ("Investigación creada. Claude Code la atenderá en la próxima sesión.", "green"),
    "existente": ("Ya había una investigación activa para este subnicho.", "amber"),
    "no-lista": (NOT_READY, "amber"),
    "error": ("No se pudo crear la investigación. Revisa la API e inténtalo de nuevo.", "rose"),
}


def detail_view(card: dict[str, Any], timezone: str) -> dict[str, Any]:
    hypothesis = card["hypothesis"]
    measured = card["measurement"]
    research = card["research"]
    state = research["status"] if research else None
    language = LANGUAGE_NAMES.get(str(hypothesis["language"]), str(hypothesis["language"]))
    action: dict[str, Any] = {"kind": "hidden"}
    if measured is not None:
        if hypothesis["status"] != "active":
            action = {"kind": "disabled", "label": f"Iniciar investigación en {language}", "note": NOT_READY}
        elif state in ("pendiente", "en_curso"):
            action = {
                "kind": "disabled",
                "label": f"Iniciar investigación en {language}",
                "note": "Hay una investigación en curso para este subnicho.",
            }
        elif state == "listo":
            action = {
                "kind": "done",
                "note": "Dossier listo. El informe móvil llega en el siguiente corte.",
            }
        else:
            prefix = "Reintentar" if state == "rechazado" else "Iniciar"
            action = {"kind": "start", "label": f"{prefix} investigación en {language}"}
    excluded = [
        (EXCLUSIONS.get(reason, reason), count) for reason, count in (measured or {}).get("excluded", {}).items()
    ]
    return {
        "slug": hypothesis["slug"],
        "label": hypothesis["label"],
        "finalist": hypothesis["finalist"],
        "family": FAMILIES.get(hypothesis["family"], hypothesis["family"]),
        "language": str(hypothesis["language"]).upper(),
        "language_name": language,
        "status": hypothesis["status"],
        "queries": list(hypothesis["queries"]),
        "measured": None
        if measured is None
        else {
            "when": local_datetime(measured["measured_at"], timezone),
            "included": measured["included"],
            "income": usd_range(measured["income_low"], measured["income_high"]),
            "rows": [
                ("Canales medidos", measured["included"]),
                ("Pequeños que despegaron", measured["traction_channels"]),
                ("Con vistas constantes", measured["stable_channels"]),
                ("Con picos recientes", measured["volatile_channels"]),
                ("Grandes en el tema", measured["large_channels"]),
                *[(f"Excluidos {label}", count) for label, count in excluded],
            ],
            "rpm_source": measured["rpm_source"],
        },
        "channels": [
            {
                "name": channel["title"] or channel["channel_id"],
                "takeoff": channel["traction"],
                "line": (
                    f"{compact(channel['subscribers'])} suscriptores · "
                    f"{compact(channel['monthly_long_views'])} de vistas al mes"
                    + (
                        f" · {usd_range(channel['income_low'], channel['income_high'])}"
                        if channel["income_low"] is not None
                        else ""
                    )
                ),
            }
            for channel in card["channels"]
        ],
        "channels_available": card["channels_available"],
        "research_text": RESEARCH.get(state, ("Investigación", "neutral"))[0],
        "research_kind": RESEARCH.get(state, ("Investigación", "neutral"))[1],
        "action": action,
    }
```

(El texto «Excluidos por idioma» de la prueba sale de `("Excluidos " + "por idioma")`.)

- [ ] **Step 4: Implementar las rutas y la plantilla**

Añadir a `src/nicheradar/web/routes_subniches.py` (importar `Form`, `RedirectResponse`, `quote`, `AVISOS`, `detail_view`):

```python
@router.get("/subnichos/{slug}")
def subniche_card(
    request: Request,
    slug: str,
    session: Annotated[Session, Depends(current_session)],
    aviso: str = "",
) -> Response:
    try:
        card = request.app.state.api.request("GET", f"/subniches/{quote(slug, safe='')}")
    except ApiError as error:
        status = 404 if error.kind == "not_found" else 503
        return render(
            request, "error.html", {"message": error.message, "active_tab": "nichos"},
            status_code=status, session=session,
        )
    view = detail_view(card, request.app.state.config.timezone)
    notice = AVISOS.get(aviso)
    return render(
        request,
        "subnichos/ficha.html",
        {"active_tab": "nichos", "v": view, "notice": notice},
        session=session,
    )


@router.post("/subnichos/{slug}/investigar")
def start_research(
    request: Request,
    slug: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request, "error.html", {"message": "La solicitud no es válida."},
            status_code=403, session=session,
        )
    api = request.app.state.api
    target = f"/subnichos/{quote(slug, safe='')}"
    try:
        card = api.request("GET", f"/subniches/{quote(slug, safe='')}")
        hypothesis = card["hypothesis"]
        result = api.request(
            "POST",
            "/flow-research",
            body={
                "niche_label": f"subniche:{hypothesis['slug']}",
                "format": hypothesis["format"],
                "language": hypothesis["language"],
            },
        )
    except ApiError as error:
        aviso = "no-lista" if error.kind == "conflict" else "error"
        return RedirectResponse(f"{target}?aviso={aviso}", status_code=303)
    aviso = "creada" if result.get("created") else "existente"
    return RedirectResponse(f"{target}?aviso={aviso}", status_code=303)
```

(El formato y el idioma se toman de la hipótesis en el servidor; nunca del formulario.)

Crear `src/nicheradar/web/templates/subnichos/ficha.html`:

```html
{% extends "base.html" %}
{% from "components.html" import chip %}
{% block title %}{{ v.label }} · NicheRadar{% endblock %}
{% block content %}
<p class="eyebrow">Subnicho · {% if v.measured %}medido{% else %}sin medición{% endif %}</p>
<h1 class="h1 h1--md">{{ v.label }}</h1>
<div class="tags">
  {% if v.finalist %}{{ chip("Finalista", "rose") }}{% endif %}
  {{ chip(v.family, "neutral") }}{{ chip(v.language, "blue") }}
  {% if v.status == "active" %}{{ chip("Activo", "green") }}{% else %}{{ chip(v.status, "neutral") }}{% endif %}
</div>
{% if notice %}<div class="note note--{{ notice[1] }}" role="status">{{ notice[0] }}</div>{% endif %}
{% if v.measured %}
<p class="lead">Medimos {{ v.measured.included }} canales de YouTube el {{ v.measured.when }}. Las cifras son estimaciones, no ingresos verificados.</p>
{% if v.measured.income %}
<section class="card">
  <span class="caption">Ingreso típico por canal al mes</span>
  <span class="income__value income__value--lg">{{ v.measured.income }}</span>
  <span class="caption">Es la mediana de los canales con vistas constantes, con el pago por mil vistas de un tema vecino. Un canal nuevo ganaría menos al principio.</span>
</section>
{% endif %}
<section class="card">
  <h2 class="h2">Qué encontramos</h2>
  <div class="rows">{% for label, value in v.measured.rows %}<div class="row"><span class="row__label">{{ label }}</span><span class="row__value">{{ value }}</span></div>{% endfor %}</div>
</section>
<h2 class="h2">Canales para mirar</h2>
<section class="card">
  {% if v.channels_available and v.channels %}
  <div class="list">{% for c in v.channels %}<div class="list__item"><span class="list__name">{{ c.name }}{% if c.takeoff %} {{ chip("Despegó", "rose") }}{% endif %}</span><span class="caption">{{ c.line }}</span></div>{% endfor %}</div>
  <span class="caption">Los datos de los canales se guardan 30 días; después se muestra que vencieron.</span>
  {% else %}
  <p class="muted">Los datos de los canales vencieron (30 días) o no hay una medición vigente.</p>
  {% endif %}
</section>
<h2 class="h2">Detalle (toca para abrir)</h2>
<details class="acc"><summary><span><span class="acc__title">Consultas que usamos</span><br><span class="acc__sub">{{ v.queries|length }} búsquedas en YouTube</span></span><span aria-hidden="true">▾</span></summary>
  <div class="acc__body">{% for q in v.queries %}<span>{{ q }}</span>{% endfor %}</div></details>
<details class="acc"><summary><span><span class="acc__title">Cómo se calcula el ingreso</span><br><span class="acc__sub">mediana por canal · pago heredado del tema vecino</span></span><span aria-hidden="true">▾</span></summary>
  <div class="acc__body"><span>Origen del pago por mil vistas: {{ v.measured.rpm_source }}</span></div></details>
{% else %}
<div class="note note--amber">Todavía no medimos este subnicho.</div>
{% endif %}
{% if v.action.kind != "hidden" %}
<section class="card">
  <h2 class="h2">Investigación de flujo</h2>
  <p class="muted">Idioma: {{ v.language_name }}, el de la hipótesis. Se crea un encargo y Claude Code investiga la competencia, las herramientas y el presupuesto en ese idioma.</p>
  <span>{{ chip(v.research_text, v.research_kind) }}</span>
  {% if v.action.kind == "start" %}
  <form method="post" action="/subnichos/{{ v.slug }}/investigar">
    <input type="hidden" name="csrf" value="{{ csrf_token }}">
    <button class="btn btn--primary" type="submit">{{ v.action.label }}</button>
  </form>
  {% elif v.action.kind == "disabled" %}
  <button class="btn btn--primary" type="button" disabled>{{ v.action.label }}</button>
  <p class="caption">{{ v.action.note }}</p>
  {% else %}
  <p class="caption">{{ v.action.note }}</p>
  {% endif %}
</section>
{% endif %}
<p class="caption"><a href="/subnichos">← Volver a Subnichos</a></p>
{% endblock %}
```

- [ ] **Step 5: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_subniche_card.py tests/test_web_subniches_list.py tests/test_web_format.py tests/test_web_assets.py tests/test_web_session.py tests/test_web_client.py tests/test_web_app.py -q 2>&1 | tail -6; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_subniche_card.py
git commit -m "feat: pantalla M10, ficha del subnicho con inicio de la investigación"
```

---

### Task 7: Capturas para comparar con el Figma y documentación

**Files:**
- Create: `scripts/web_preview.py`, `scripts/web_preview_data.py`
- Create: `docs/web-movil.md`
- Modify: `docs/comandos.md`, `docs/deployment-easypanel.md` (una nota breve sobre `NR_DASHBOARD_UI`), `AGENTS.md` (una línea en «Archivos de código principales»)
- Create: `tests/test_web_preview.py`

**Interfaces:**
- Consumes: `create_app`, `settings`-equivalente (la ruta de datos de ejemplo no importa de `tests`), el paquete `nicheradar.web` completo (Tasks 1–6).
- Produces: `scripts/web_preview.py` con `main(argv: list[str] | None = None) -> int`: `uv run python scripts/web_preview.py --out DIR [--chrome RUTA]` renderiza `/subnichos` y la ficha de ejemplo con datos de `scripts/web_preview_data.py` (sin API real: usa `httpx.MockTransport`), guarda `lista.html` y `ficha.html` con rutas de recursos reescritas a `file://` en `DIR` y, si encuentra Chrome, `lista.png` y `ficha.png` a 390 px de ancho con factor de escala 2; imprime las rutas generadas. `docs/web-movil.md` explica el funcionamiento, las variables, el retroceso a Streamlit y la comprobación visual.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_web_preview.py`:

```python
# tests/test_web_preview.py
from pathlib import Path

import pytest

from scripts import web_preview


def test_the_preview_renders_the_list_and_the_card_with_local_assets(tmp_path: Path) -> None:
    assert web_preview.main(["--out", str(tmp_path), "--no-screenshots"]) == 0
    lista = (tmp_path / "lista.html").read_text()
    ficha = (tmp_path / "ficha.html").read_text()
    assert "Subnichos" in lista and "Prehistoric Creatures" in lista
    assert "Ingreso típico por canal al mes" in ficha
    assert 'href="/static/' not in lista and "file://" in lista
    assert "http://" not in lista.replace("file://", "") and "https://" not in lista


def test_the_preview_refuses_a_missing_output_directory_argument() -> None:
    with pytest.raises(SystemExit):
        web_preview.main([])
```

(`scripts` debe ser importable como paquete en las pruebas; si el repo no tiene `scripts/__init__.py`, comprobar cómo importan otros tests los scripts —p. ej. `tests/test_subniche_report.py` o `tests/test_smoke*.py`— y usar el mismo mecanismo; no añadir un `__init__.py` si no existe la convención.)

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `uv run pytest tests/test_web_preview.py -q 2>&1 | tail -6`
Expected: FAIL (`ModuleNotFoundError` o importación de `scripts.web_preview`).

- [ ] **Step 3: Implementar el script**

Crear `scripts/web_preview_data.py` con datos de ejemplo (las mediciones reales del 31/10/2026 que usa el Figma M9 y M10: Prehistoric Creatures 29 canales, 18 constantes, 11 con picos, 19 que despegaron, 4 grandes, ingreso 672.80–1681.99, y los canales WUFO TV, Curious Fing y Extinct World; más Deep Sea Mysteries, Forgotten History Events, History Revenge Stories y Ancient Egypt Secrets con sus cifras de la lista) como diccionarios con la forma exacta de la API: `ITEMS: list[dict[str, Any]]` y `CARD: dict[str, Any]`. Los estados de investigación de la lista son ilustrativos, como en el Figma (Prehistoric: `listo`; Deep Sea: `en_curso`; el resto sin investigación).

Crear `scripts/web_preview.py`:

```python
# scripts/web_preview.py
"""Render the mobile web screens with sample data to HTML and PNG, to compare them with Figma."""

import argparse
import subprocess
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.web import app as web_app
from nicheradar.web.app import create_app
from scripts.web_preview_data import CARD, ITEMS

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PASSWORD = "p" * 32
STATIC = Path(web_app.__file__).parent / "static"


def _api(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/subniches":
        return httpx.Response(200, json={"items": ITEMS})
    if path.startswith("/api/v1/subniches/"):
        return httpx.Response(200, json=CARD)
    if path == "/api/v1/status":
        return httpx.Response(200, json={"radar_paused": True})
    return httpx.Response(404, json={"detail": "not found"})


def _local(html: str) -> str:
    return html.replace('"/static/', f'"file://{STATIC}/')


def render_pages(out: Path) -> dict[str, Path]:
    config = Settings(
        service_token=SecretStr("t" * 32),
        dashboard_password=SecretStr(PASSWORD),
        api_url="http://api.test",
        dashboard_ui="web",
    )
    web = TestClient(create_app(config, transport=httpx.MockTransport(_api)), follow_redirects=False)
    assert web.post("/login", data={"password": PASSWORD}).status_code == 303
    pages = {"lista": "/subnichos", "ficha": f"/subnichos/{CARD['hypothesis']['slug']}"}
    written: dict[str, Path] = {}
    for name, path in pages.items():
        target = out / f"{name}.html"
        target.write_text(_local(web.get(path).text))
        written[name] = target
    return written


def screenshot(page: Path, chrome: str, height: int) -> Path:
    png = page.with_suffix(".png")
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=2", f"--window-size=390,{height}",
         f"--screenshot={png}", f"file://{page}"],
        check=True, capture_output=True, timeout=60,
    )
    return png


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chrome", default=CHROME)
    parser.add_argument("--no-screenshots", action="store_true")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    pages = render_pages(args.out)
    for name, path in pages.items():
        print(path)
        if not args.no_screenshots and Path(args.chrome).exists():
            print(screenshot(path, args.chrome, 1800 if name == "lista" else 1750))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

(Si el repo no es importable como `scripts.*` desde las pruebas, copiar la convención que usen los demás scripts con pruebas y ajustar los dos `import` al estilo existente; no cambiar la estructura de `scripts/` por esto. La fuente se carga con `file://` solo en esta vista previa; la aplicación real nunca usa `file://`.)

- [ ] **Step 4: Documentación**

Crear `docs/web-movil.md` con: qué es (la web móvil que reemplaza al dashboard de Streamlit en el mismo dominio); variables (`NR_DASHBOARD_UI` = `streamlit` por defecto o `web`; las demás son las del dashboard: `NR_API_URL`, `NR_SERVICE_TOKEN`, `NR_DASHBOARD_PASSWORD`); cómo cambiar y volver atrás (variable más reinicio; o imagen anterior); sesión y seguridad (cookie firmada de 12 horas con clave derivada del token, CSRF, límite de intentos, CSP sin recursos externos); recursos incluidos (HTMX 2.0.4 e Inter 4.0 con su licencia, en `static/`; huellas en `static/js/VENDOR.md`); PWA; pantallas de este corte (M9 y M10) y las que faltan; cómo generar las capturas (`uv run python scripts/web_preview.py --out /tmp/web-preview`) y compararlas con el Figma M9 (`29:2`) y M10 (`30:2`). En `docs/comandos.md`, una fila para `scripts/web_preview.py` y para `NR_DASHBOARD_UI`. En `docs/deployment-easypanel.md`, una nota con la variable y el retroceso. En `AGENTS.md`, en «Archivos de código principales», una línea para `src/nicheradar/web/` y `docs/web-movil.md`.

- [ ] **Step 5: Validación completa**

Run: `uv run pytest tests/test_web_preview.py -q 2>&1 | tail -3; uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q 2>&1 | tail -4`
Expected: todo en verde; la suite completa pasa con Postgres. Luego generar las capturas: `uv run python scripts/web_preview.py --out /tmp/web-preview` y confirmar que se crean `lista.png` y `ficha.png` (390 px de ancho a escala 2). **Las comparaciones con el Figma las hace el controlador**; el implementador solo entrega las rutas de las imágenes y anota cualquier diferencia visible que detecte (p. ej. el desplegable nativo de los selectores).

- [ ] **Step 6: Commit**

```bash
git add scripts/web_preview.py scripts/web_preview_data.py tests/test_web_preview.py docs/web-movil.md docs/comandos.md docs/deployment-easypanel.md AGENTS.md
git commit -m "docs: vista previa de la web móvil y guía de la nueva interfaz"
```

---

## Fuera de este plan

Las demás pantallas del corte 1 (Hoy, Nichos con decisiones, iniciar investigación de un nicho, informe, autorizar piloto), los cortes 2 y 3, el contrato `channel-report-v3`, la imagen de producción y el cambio de `NR_DASHBOARD_UI` en Easypanel (release con la aprobación del propietario). Este plan termina con las capturas de M9 y M10 para compararlas con el Figma.

## Self-Review

- **Cobertura del spec:** arquitectura FastAPI + Jinja2 + HTMX con recursos propios (Tasks 1 y 4); selección por `NR_DASHBOARD_UI` con Streamlit por defecto (Task 1); sesión, CSRF, límite de intentos y cabeceras (Tasks 1 y 2); cliente de la API (Task 3); PWA con service worker que solo guarda estáticos (Task 4); M9 y M10 con filtros, estados y botones (Tasks 5 y 6); fuente Inter incluida (Task 4); comprobación de fidelidad con el Figma (Task 7). Pendiente, por diseño: el resto del corte 1 y los cortes 2 y 3.
- **Ruling 1:** el spec pide `Cache-Control: no-store` en las páginas con datos; el plan lo aplica a todo lo que no sea `/static`, incluidas las páginas públicas (login, sin conexión), por sencillez.
- **Ruling 2:** el límite de intentos usa una sola clave (`owner`), no la IP, porque detrás del proxy todas las peticiones llegan de la misma dirección y la app es de un solo propietario; el costo es que cinco fallos bloquean a cualquiera durante un minuto.
- **Ruling 3:** `/_stcore/health` se conserva en la web nueva (no está en el spec): el `healthcheck` de `compose.yaml`, `scripts/smoke_compose.py` y la sonda de `easypanel_stage.mjs` dependen de esa ruta.
- **Ruling 4:** la barra «Pilotos» y «Más», y el segmento «Nichos», aparecen desactivados («Próximamente») hasta que existan; la ficha de un subnicho con dossier listo dice que el informe móvil llega en el siguiente corte, en lugar de enlazar a una ruta que aún no existe. La etiqueta de orden de la lista dice «Finalistas y tracción ↓», que es el orden real de la API, no «Ingreso típico ↓» del Figma.
- **Ruling 5:** los filtros usan formularios `GET` con HTMX; los selectores de Familia y Estado son `<select>` nativos (el menú desplegado lo dibuja el sistema), diferencia con el Figma que se evalúa en la comparación visual.
- **Consistencia de tipos:** `create_app(config, *, transport, clock)` y `app.state.{config,transport,clock,signer,limiter,templates,api,radar_cache}` se definen en las Tasks 1 a 4 y las usan las posteriores; `render(request, name, context, *, status_code, session)` (Task 2) lo usan las Tasks 4 a 6; `card`/`list_view`/`detail_view` y las constantes `NOT_READY`, `AVISOS`, `FAMILIES`, `RESEARCH` viven en `subniches.py`; las pruebas comparten `tests/web_helpers.py` (`Api`, `make_client`, `csrf_of`, `subniche_item`, `subniche_card`, `HOSTILE`).
- **Sin placeholders:** cada paso de código trae el código; las notas entre paréntesis indican cómo adaptar una prueba si una convención del repo (importación de `scripts`, firma de un ayudante) difiere.
