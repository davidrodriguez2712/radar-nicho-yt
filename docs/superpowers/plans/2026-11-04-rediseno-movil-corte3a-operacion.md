# Rediseño móvil, corte 3a: Operación sin radar, menú «Más», sesión de 5 días y calibración como «mínimo»

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la web móvil deje de hablar del radar de oportunidades y tenga la pantalla de **Operación** (scraper de mercado y resumen de subnichos), su confirmación de pausar o reanudar, la lista de ejecuciones del scraper y el menú «Más»; que la sesión dure 5 días; y que la calibración trate la cifra de minutos humanos como un **mínimo estimado** (racha «posible»).

**Architecture:** Cambios solo en `src/nicheradar/web/` más pruebas y documentación; ningún cambio de API, de base de datos ni de contenedores. Operación sigue el patrón de las pantallas existentes: un `routes_operation.py` con GET protegidos por `shape_guard`, un módulo de vista puro (`operation.py`) que recibe dicts de la API y devuelve el dict que pinta la plantilla, plantillas en `templates/operacion/`, confirmación por GET y POST con CSRF que relee el estado antes de escribir. Cada tarjeta lee su propia fuente y degrada sola si esa fuente falla.

**Tech Stack:** FastAPI, Jinja2 (autoescape, nunca `|safe`), HTMX vendorizado, httpx `MockTransport` en pruebas, pytest, ruff, mypy. Sin Postgres.

**Spec:** `docs/superpowers/specs/2026-11-03-rediseno-movil-corte3-paridad-design.md` (entrega 3a y decisiones 5 y 6). Diseño: Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil»: M15 `42:2` (Operación), M16 `42:87` (confirmar reanudar el scraper), M17 `42:127` (ejecuciones), M18 `47:2` (Más), M22 `47:217` (Entrar con la nota de sesión).

## Global Constraints

- Todo lo de los planes anteriores sigue vigente: cookie firmada, CSRF antes de llamar a la API en todo POST, CSP propia, escape de todo texto de la API, `shape_guard` en los GET, `render(..., with_radar=False)` ya no existe tras la Task 1, avisos desde claves fijas (nunca texto de la query), números no finitos como «—», fechas sin zona como UTC, tope de 100 elementos con aviso, nada de `|safe`, sin estilos ni scripts en línea.
- **El radar de oportunidades ya no existe en la web:** ninguna pantalla muestra, lee ni cita `/status.radar_paused`, `PUT /radar`, `POST /runs`, `/jobs`, `/providers` ni `/pilot/preflight`. El servidor y Streamlit no se tocan.
- **Solo datos reales de la API:** Operación usa `GET /market/schedule`, `GET /market/runs` y `GET /subniches?include_inactive=true`; nada inventado. Los estados de una ejecución son `queued|running|succeeded|partial|failed|blocked`; cualquier otro valor se muestra «desconocido».
- **Costosas o con estado = pantalla de confirmación:** pausar o reanudar el scraper es un GET de confirmación y un POST con CSRF que **relee** `GET /market/schedule` y no escribe si el estado ya es el pedido.
- **409 de reanudar en modo real** (`HTTPException(409, <str>)`): el `detail` es un `str`, así que `ApiError.message` es genérico; se muestra un texto fijo en español propio de la web, nunca el texto del servidor, y no se reintenta.
- Sesión: `SESSION_SECONDS = 5 * 24 * 3600`. Rotar `NR_SERVICE_TOKEN` sigue invalidando todas las sesiones.
- Calibración: la cifra de `claude_sessions_plus_assumed` es un **mínimo medido más un supuesto**; la racha que la usa se rotula «posible» y nunca «superada». Otros métodos conservan su texto actual.
- Nada se despliega con este plan.

## Rulings de diseño

1. **Se elimina la llamada a `/status` de la cabecera**, no solo el chip: `radar_state`, su caché y el parámetro `with_radar` desaparecen (17 usos en 9 archivos). Costo si es incorrecto: reponerlos desde git.
2. **«Más» pasa a ser una pantalla** (`/mas`) con «Operación» y «Salir». «Análisis de canal» no aparece (decisión del propietario).
3. **Ejecuciones del scraper:** se piden `limit=20` (el diseño dice «las últimas 20»); la lista completa hasta 100 queda fuera.
4. **«Sin primera medición»** de subnichos = hipótesis `active` con `measurement` nulo. **«Última medición»** = el mayor `measurement.measured_at` válido de todas las hipótesis; si ninguna tiene, «sin mediciones».
5. **Duración de una ejecución** = `finished_at - started_at` en minutos redondeados hacia arriba; si falta alguno de los dos no se muestra.
6. **Modo:** `schedule.mode == "live"` se muestra «Real»; `"synthetic"`, «De ejemplo»; otro valor, «—».

## Review Focus

1. Cada fuente (`/market/schedule`, `/market/runs`, `/subniches`) caída, lenta o con forma rota degrada **solo su tarjeta**; ninguna pantalla da 500 ni muestra una traza (Task 3).
2. Ejecuciones con `status` desconocido, `stage` desconocida, `error_code` hostil o enorme, fechas sin zona, `NaN`, `stats` gigantes: texto escapado, «desconocido» y sin 500 (Task 3).
3. Doble toque en «Confirmar y reanudar»: el segundo POST ve el scraper ya activo y no escribe (Task 4).
4. Reanudar en modo real sin scraper en vivo habilitado (409): texto fijo, sin reintento, sin perder el estado (Task 4).
5. Hipótesis con `measurement` nulo o malformado, más de 100 hipótesis y fechas sin zona: contadores correctos y sin 500 (Task 3).

---

### Task 1: Quitar el radar de la cabecera

**Files:**
- Modify: `src/nicheradar/web/templates/components.html` (macro `topbar`, l.10-19), `src/nicheradar/web/templates/base.html` (l.18), `src/nicheradar/web/deps.py` (borrar `radar_state`, `STATUS_TIMEOUT_SECONDS`, `RADAR_TTL_SECONDS`, el parámetro `with_radar` de `render` y sus usos en `shape_guard`), `src/nicheradar/web/app.py` (borrar `app.state.radar_cache`), y todos los `with_radar=` de `routes_subniches.py`, `routes_niches.py`, `routes_pilots.py`, `routes_pilot_list.py`, `routes_pilot_actions.py`, `routes_pilot_panel.py`, `routes_reports.py`, `routes_research.py`, `routes_today.py` (buscar con `grep -rn "with_radar" src/nicheradar/web`)
- Modify (pruebas): `tests/test_web_assets.py` (borrar `test_radar_state_...` l.135-150 y lo que dependa), `tests/test_web_pilot_authorize.py` (l.478-484: invertir a «no aparece ningún chip de radar»)
- Create: `tests/test_web_header.py`

**Interfaces:**
- Produces: `render(request, name, context=None, *, status_code=200, session=None) -> Response` (sin `with_radar`); la cabecera solo lleva la marca «NicheRadar» y el botón «Salir» (con sesión); ya no hace ninguna llamada a la API.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_header.py`):

```python
"""La cabecera ya no habla del radar ni llama a /status."""

import httpx
import pytest

from tests.web_helpers import Api, make_client

STATUS = ("GET", "/api/v1/status")


def test_no_page_shows_a_radar_chip_or_calls_status() -> None:
    api = Api({STATUS: (200, {"radar_paused": True}), ("GET", "/api/v1/subniches"): (200, {"items": []})})
    client = make_client(api)
    page = client.get("/subnichos")
    assert page.status_code == 200
    assert "Radar pausado" not in page.text and "Radar activo" not in page.text
    assert api.count("GET", "/api/v1/status") == 0


def test_the_header_keeps_the_brand_and_the_logout_button() -> None:
    api = Api({("GET", "/api/v1/subniches"): (200, {"items": []})})
    html = make_client(api).get("/subnichos").text
    assert "NicheRadar" in html and "Salir" in html


@pytest.mark.parametrize("path", ["/", "/nichos", "/pilotos", "/subnichos"])
def test_no_screen_calls_status_any_more(path: str) -> None:
    api = Api({})
    make_client(api).get(path)
    assert api.count("GET", "/api/v1/status") == 0
```

- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_header.py -q 2>&1 | tail -8` — FAIL (hoy se llama a `/status` y se pinta el chip).
- [ ] **Step 3: Implementar.** En `components.html` el macro queda:

```jinja
{% macro topbar(csrf_token) %}
  <header class="topbar">
    <a class="topbar__brand" href="/">NicheRadar</a>
    {% if csrf_token %}
    <form method="post" action="/salir" class="topbar__logout">
      <input type="hidden" name="csrf" value="{{ csrf_token }}">
      <button class="topbar__link" type="submit">Salir</button>
    </form>
    {% endif %}
  </header>
{% endmacro %}
```

  (conservar exactamente las clases y la estructura que hoy tiene el macro; solo se elimina el `radar_state` y el chip). En `base.html`: `{{ topbar(csrf_token) }}`. En `deps.py` borrar `radar_state(...)`, las constantes y el cálculo en `render`; en `app.py` quitar `app.state.radar_cache`. Eliminar todos los `with_radar=...` de las rutas y de `shape_guard`. Ajustar las dos pruebas existentes que citan el chip.
- [ ] **Step 4:** `uv run pytest tests/test_web_header.py tests/test_web_assets.py tests/test_web_pilot_authorize.py -q`; luego la suite web entera (`uv run pytest -q -k "web"`), `uv run ruff format src tests -q; uv run ruff check . && uv run mypy` — PASS. Corregir cualquier prueba que sembraba `STATUS` y dependía del chip.
- [ ] **Step 5: Commit** `refactor: la cabecera de la web ya no muestra ni consulta el radar`.

---

### Task 2: Sesión de 5 días

**Files:**
- Modify: `src/nicheradar/web/security.py:15`, `docs/web-movil.md` (sección de sesión), pruebas que fijen 12 horas (`grep -rn "12 \* 3600\|SESSION_SECONDS\|43200" tests src/nicheradar/web docs/web-movil.md`)
- Test: `tests/test_web_security.py` (o el archivo que hoy prueba la cookie; buscar)

**Interfaces:**
- Produces: `SESSION_SECONDS = 5 * 24 * 3600`; la cookie `nr_session` lleva `max_age=432000`.

- [ ] **Step 1: Pruebas que fallan:** una prueba que entra y comprueba `max_age` de la cookie (cabecera `Set-Cookie` con `Max-Age=432000`), una que verifica que una sesión emitida hace 4 días y 23 horas sigue leyéndose y una de hace 5 días y 1 minuto expira (usar el reloj inyectable de `SessionSigner`/`make_client(api, clock=...)`), y que la sesión sigue invalidándose al rotar el token de servicio (ya existe; confirmarla).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_security.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** el cambio de constante y actualizar `docs/web-movil.md` («una cookie copiada sirve hasta 5 días; rotar `NR_SERVICE_TOKEN` invalida todas las sesiones»; contraseña aleatoria de al menos 32 caracteres cuando no hay Basic Auth en el proxy).
- [ ] **Step 4:** pruebas del archivo, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: la sesión de la web dura 5 días`.

---

### Task 3: Pantalla de Operación (M15)

**Files:**
- Create: `src/nicheradar/web/operation.py`, `src/nicheradar/web/routes_operation.py`, `src/nicheradar/web/templates/operacion/operacion.html`
- Modify: `src/nicheradar/web/format.py` (helper `ago`), `src/nicheradar/web/app.py` (import e `include_router`), `src/nicheradar/web/static/css/app.css` (reglas de las clases nuevas), `tests/web_helpers.py` (builders `schedule(**over)` y `scrape_run(**over)`), `tests/test_web_assets.py` (añadir `templates/operacion` al recorrido de clases CSS)
- Create (pruebas): `tests/test_web_operation.py`

**Interfaces:**
- Consumes: `ApiClient.request`, `render`, `shape_guard`, `current_session`, `format.local_datetime`, `format.parse_utc`, `tests/web_helpers.py` (`Api`, `make_client`).
- Produces:
  - `format.ago(value: object, now: datetime) -> str` («hace un momento», «hace 5 min», «hace 6 h», «hace 3 d», «—» si no se entiende, «ahora» si la fecha está en el futuro).
  - `operation.STATUS_LABEL: dict[str, str]`, `STATUS_TONE: dict[str, str]`, `STAGE_LABEL: dict[str, str]`, `MODE_LABEL: dict[str, str]`.
  - `operation.scraper_card(schedule: object, runs: object, now: datetime, tz: str) -> dict[str, object]` con claves `ok`, `paused`, `state_text`, `mode_text`, `frequency_text`, `next_text`, `action` (`"reanudar"` o `"pausar"`), `warnings: list[str]`.
  - `operation.runs_card(runs: object, now: datetime, tz: str, limit: int) -> dict[str, object]` con `ok`, `rows: list[{when, detail, status_label, tone}]`, `empty`, `truncated`.
  - `operation.subniches_card(items: object, now: datetime) -> dict[str, object]` con `ok`, `active`, `proposed`, `paused`, `unmeasured`, `last_measured_text`.
  - `operation.warnings(schedule_card, runs_card) -> list[str]` (avisos de la parte superior).
  - `operation_view(sources: dict[str, object], now: datetime, tz: str) -> dict[str, object]` con las tres tarjetas y `warnings`.
  - Ruta `GET /operacion` (`active_tab="mas"`), plantilla `operacion/operacion.html`.

Reglas de contenido (texto exacto del diseño y de la API):

- Estados de ejecución: `queued` «en cola», `running` «en curso», `succeeded` «correcta», `partial` «parcial», `failed` «falló», `blocked` «bloqueada»; otro valor «desconocido». Tonos: correcta `green`, parcial `amber`, falló `rose`, bloqueada `gray`, en curso y en cola `blue`, desconocido `gray`.
- Etapas: `list` «listados», `detail` «detalle», `reconcile` «reconciliación», `classify` «clasificación», `verify` «verificación», `enrich` «enriquecimiento», `evidence` «evidencia», `snapshot` «captura»; otro valor «—».
- Línea de una ejecución: fecha corta local y hora (`local_datetime`), segunda línea `etapa: <etapa>` más ` · <N> min` si hay duración, y ` · error: <error_code recortado a 60 caracteres>` si hay `error_code` (el código se pinta como texto escapado).
- Tarjeta del scraper: filas «Estado» (`Activo` o `Pausado`), «Modo» (ruling 6), «Frecuencia» (`interval_seconds` → «Cada 24 h» si es múltiplo de 3600, «Cada N min» si es múltiplo de 60, «—» si no es un entero positivo), «Próxima ejecución» (`local_datetime(next_due_at)` si está activo; «—  (pausado)» si está pausado); botón «Reanudar scraper» (primario) si está pausado y «Pausar scraper» (contorno) si está activo, que enlazan a `/operacion/scraper/reanudar` y `/operacion/scraper/pausar`.
- Avisos (claves fijas, en este orden): pausado → «El scraper de mercado está pausado: no trae anuncios nuevos hasta que lo reanudes.»; última ejecución `partial` → «La última ejecución del scraper salió parcial.»; `failed` → «La última ejecución del scraper falló.»; `blocked` → «La última ejecución del scraper quedó bloqueada.»; modo `live` con `live_enabled` falso → «En modo real, el scraper no se activa hasta habilitar el scraper en vivo en el servidor.». Si no hay avisos, la tarjeta de avisos no aparece.
- Tarjeta de subnichos: filas «Activas (se miden solas)», «Propuestas por aprobar», «Pausadas», «Sin primera medición», «Última medición» (con `ago`), la nota «Las hipótesis activas se miden solas, a más tardar cada 3 días; las nuevas, primero.» y el botón «Ver subnichos» a `/subnichos`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_operation.py`, completas; añadir los builders a `tests/web_helpers.py` primero con las claves reales):

```python
# tests/web_helpers.py (añadir)
def schedule(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "paused": False, "next_due_at": "2026-11-05T11:00:00+00:00",
        "interval_seconds": 86400, "mode": "live", "live_enabled": True, "radar_paused": True,
    }
    return base | over


def scrape_run(status: str = "succeeded", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "7a1b2c3d-0000-4000-8000-000000000001", "run_key": "run-1", "analysis_run_id": None,
        "status": status, "stage": "snapshot", "attempts": 1, "lease_owner": None, "lease_until": None,
        "checkpoints": {}, "error_code": None, "stats": {},
        "started_at": "2026-11-03T11:00:00+00:00", "finished_at": "2026-11-03T11:03:10+00:00",
        "created_at": "2026-11-03T11:00:00+00:00",
    }
    return base | over
```

```python
# tests/test_web_operation.py
from datetime import UTC, datetime

import httpx
import pytest

from nicheradar.web import operation as op
from nicheradar.web.format import ago
from tests.web_helpers import HOSTILE, Api, make_client, schedule, scrape_run, subniche_item

SCHEDULE = ("GET", "/api/v1/market/schedule")
RUNS = ("GET", "/api/v1/market/runs")
SUBNICHES = ("GET", "/api/v1/subniches")
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def api_with(**over: object) -> Api:
    routes: dict = {
        SCHEDULE: (200, schedule()),
        RUNS: (200, {"items": [scrape_run()]}),
        SUBNICHES: (200, {"items": [subniche_item("a", status="active")]}),
    }
    routes.update(over)
    return Api(routes)


# ---- format.ago
@pytest.mark.parametrize("value,expected", [
    ("2026-11-04T11:59:30+00:00", "hace un momento"),
    ("2026-11-04T11:55:00+00:00", "hace 5 min"),
    ("2026-11-04T06:00:00+00:00", "hace 6 h"),
    ("2026-11-01T12:00:00+00:00", "hace 3 d"),
    ("2026-11-04T13:00:00+00:00", "ahora"),
    ("2026-11-04T11:55:00", "hace 5 min"),
    ("basura", "—"), (None, "—"), (7, "—"),
])
def test_ago(value: object, expected: str) -> None:
    assert ago(value, NOW) == expected


# ---- vista pura
def test_run_status_labels_and_unknown_values() -> None:
    card = op.runs_card([scrape_run("partial"), scrape_run("raro", stage="inventada")], NOW, "America/Lima", 20)
    labels = [r["status_label"] for r in card["rows"]]
    assert labels == ["parcial", "desconocido"]
    assert "etapa: —" in card["rows"][1]["detail"]


def test_run_detail_has_stage_duration_and_error_code() -> None:
    row = op.runs_card([scrape_run("failed", stage="list", error_code="timeout")], NOW, "UTC", 20)["rows"][0]
    assert row["detail"] == "etapa: listados · 4 min · error: timeout"  # 3 min 10 s se redondea hacia arriba


def test_duration_is_omitted_when_a_date_is_missing_or_garbage() -> None:
    row = op.runs_card([scrape_run(finished_at=None)], NOW, "UTC", 20)["rows"][0]
    assert "min" not in row["detail"].replace("etapa", "")


def test_hostile_error_code_is_trimmed_and_kept_as_text() -> None:
    row = op.runs_card([scrape_run("failed", error_code="x" * 500)], NOW, "UTC", 20)["rows"][0]
    assert len(row["detail"]) < 140


def test_scraper_card_active_and_paused() -> None:
    active = op.scraper_card(schedule(), [], NOW, "UTC")
    assert (active["state_text"], active["mode_text"], active["frequency_text"], active["action"]) == (
        "Activo", "Real", "Cada 24 h", "pausar")
    paused = op.scraper_card(schedule(paused=True), [], NOW, "UTC")
    assert (paused["state_text"], paused["action"]) == ("Pausado", "reanudar")
    assert "pausado" in paused["next_text"]


@pytest.mark.parametrize("seconds,text", [(86400, "Cada 24 h"), (7200, "Cada 2 h"), (1800, "Cada 30 min"), (0, "—"), ("x", "—"), (-5, "—")])
def test_frequency_text(seconds: object, text: str) -> None:
    assert op.scraper_card(schedule(interval_seconds=seconds), [], NOW, "UTC")["frequency_text"] == text


def test_warnings_follow_the_fixed_order_and_keys() -> None:
    sc = op.scraper_card(schedule(paused=True, mode="live", live_enabled=False), [scrape_run("partial")], NOW, "UTC")
    assert sc["warnings"] == [
        "El scraper de mercado está pausado: no trae anuncios nuevos hasta que lo reanudes.",
        "La última ejecución del scraper salió parcial.",
        "En modo real, el scraper no se activa hasta habilitar el scraper en vivo en el servidor.",
    ]


def test_no_warnings_when_everything_is_fine() -> None:
    assert op.scraper_card(schedule(), [scrape_run()], NOW, "UTC")["warnings"] == []


def test_subniche_counters_and_last_measurement() -> None:
    items = [
        subniche_item("a", status="active"),
        subniche_item("b", status="active", measurement=None),
        subniche_item("c", status="proposed", measurement=None),
        subniche_item("d", status="paused"),
        subniche_item("e", status="archived"),
        "no es un dict", None,
    ]
    card = op.subniches_card(items, NOW)
    assert (card["active"], card["proposed"], card["paused"], card["unmeasured"]) == (2, 1, 1, 1)
    assert card["last_measured_text"].startswith("hace ") or card["last_measured_text"] == "sin mediciones"


def test_subniche_card_degrades_on_a_wrong_shape() -> None:
    assert op.subniches_card({"x": 1}, NOW)["ok"] is False
    assert op.subniches_card(None, NOW)["ok"] is False


def test_runs_truncation_warning_at_the_limit() -> None:
    card = op.runs_card([scrape_run() for _ in range(20)], NOW, "UTC", 20)
    assert card["truncated"] is True


# ---- ruta
def test_the_screen_requires_a_session() -> None:
    from nicheradar.web.app import create_app
    from tests.web_helpers import settings
    from fastapi.testclient import TestClient
    r = TestClient(create_app(settings()), follow_redirects=False).get("/operacion")
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_the_screen_renders_the_three_cards() -> None:
    page = make_client(api_with()).get("/operacion")
    assert page.status_code == 200
    for text in ("Operación", "Scraper de mercado", "Últimas ejecuciones del scraper", "Subnichos",
                 "Pausar scraper", "Ver todas las ejecuciones", "Ver subnichos"):
        assert text in page.text
    assert "Radar" not in page.text


def test_runs_are_requested_with_limit_20_and_subniches_with_inactive() -> None:
    api = api_with()
    make_client(api).get("/operacion")
    runs_call = next(c for c in api.calls if c.url.path.endswith("/market/runs"))
    assert runs_call.url.params["limit"] == "20"
    sub_call = next(c for c in api.calls if c.url.path.endswith("/subniches"))
    assert sub_call.url.params["include_inactive"] == "true"


@pytest.mark.parametrize("down", [SCHEDULE, RUNS, SUBNICHES])
def test_one_failing_source_degrades_only_its_card(down: tuple[str, str]) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")
    routes: dict = {
        SCHEDULE: (200, schedule()), RUNS: (200, {"items": [scrape_run()]}),
        SUBNICHES: (200, {"items": [subniche_item("a")]}),
    }
    routes[down] = boom
    page = make_client(Api(routes)).get("/operacion")
    assert page.status_code == 200
    assert "Traceback" not in page.text
    assert "no disponible" in page.text.lower()
    # las otras dos tarjetas siguen presentes
    present = sum(t in page.text for t in ("Scraper de mercado", "Últimas ejecuciones del scraper", "Subnichos"))
    assert present >= 2


def test_hostile_text_in_runs_is_escaped() -> None:
    api = api_with(**{RUNS: (200, {"items": [scrape_run("failed", error_code=HOSTILE)]})})
    page = make_client(api).get("/operacion")
    assert "<script>" not in page.text and "&lt;script&gt;" in page.text
```

- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_operation.py -q 2>&1 | tail -8`.
- [ ] **Step 3: Implementar** `format.ago`, `operation.py` (funciones puras que toleran basura: ante un tipo erróneo la tarjeta devuelve `{"ok": False}`), `routes_operation.py` (tres lecturas independientes con `try/except ApiError` por fuente; los errores de una fuente ponen su tarjeta en `{"ok": False}` y el resto se pinta; `limit=20` para ejecuciones; `render(request, "operacion/operacion.html", {"active_tab": "mas", "view": view, "notice": AVISOS.get(aviso)}, session=session)` con `Vary: HX-Request, HX-History-Restore-Request`), plantilla con las tarjetas del diseño (clases existentes `card`, `list`, `chip`, `btn`, `note`; las nuevas con regla en `app.css`), registrar el router en `app.py`, y `AVISOS = {"reanudado": ("Scraper reanudado.", "green"), "pausado": ("Scraper pausado.", "green"), "sin-cambio": ("El scraper ya estaba en ese estado.", "amber"), "error": ("No se pudo aplicar el cambio.", "rose")}` en `operation.py` (se usa en la Task 4).
- [ ] **Step 4:** `uv run pytest tests/test_web_operation.py tests/test_web_assets.py -q` (añadir `templates/operacion` al recorrido de clases CSS de `test_web_assets.py`); ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: pantalla Operación con scraper de mercado y resumen de subnichos`.

---

### Task 4: Confirmar pausar o reanudar el scraper (M16) y ejecuciones (M17)

**Files:**
- Modify: `src/nicheradar/web/routes_operation.py`, `src/nicheradar/web/operation.py`
- Create: `src/nicheradar/web/templates/operacion/confirmar.html`, `src/nicheradar/web/templates/operacion/ejecuciones.html`
- Modify: `src/nicheradar/web/static/css/app.css`
- Create (pruebas): `tests/test_web_operation_actions.py`

**Interfaces:**
- Consumes: `schedule`, `scrape_run` (builders), `operation.runs_card`, `operation.AVISOS`, patrón de `routes_pilot_actions.py` (GET de confirmación, POST con `csrf_valid`, relectura, redirect 303 con `?aviso=`).
- Produces:
  - `operation.ACTIONS = {"reanudar": {"title": "Reanudar el scraper", "consequence": ..., "button": "Confirmar y reanudar", "kind": "primary", "paused": False}, "pausar": {"title": "Pausar el scraper", "consequence": ..., "button": "Confirmar y pausar", "kind": "danger", "paused": True}}`.
  - `operation.LIVE_BLOCK = "En modo real, el scraper en vivo debe estar habilitado en el servidor. Mientras no lo esté, no se puede reanudar."`.
  - `operation.confirm_view(action: str, schedule: object, now, tz) -> dict` con `title`, `consequence`, `rows`, `blocked: str | None`, `already: bool`.
  - Rutas: `GET /operacion/scraper/{accion}` (confirmación), `POST /operacion/scraper/{accion}`, `GET /operacion/ejecuciones`.

Textos exactos (Figma M16): reanudar: consecuencia «El scraper de mercado volverá a recorrer los anuncios en su próxima hora programada.» con filas «Frecuencia», «Próxima ejecución» (será ahora mismo si está pausado: la API fija `next_due_at=now`; texto «en cuanto el servidor lo recoja»), «Modo»; pausar: «El scraper de mercado dejará de traer anuncios nuevos hasta que lo reanudes. No borra nada.». Botones: «Confirmar y reanudar» o «Confirmar y pausar» y enlace «Volver sin cambios». Si `blocked`: aviso ámbar con `LIVE_BLOCK`, sin formulario, estado 409.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_operation_actions.py`):

```python
import httpx
import pytest

from tests.web_helpers import Api, csrf_of, make_client, schedule, scrape_run

SCHEDULE = ("GET", "/api/v1/market/schedule")
PUT = ("PUT", "/api/v1/market/schedule")
RUNS = ("GET", "/api/v1/market/runs")


def api(paused: bool, put: object = None, **sched: object) -> Api:
    routes: dict = {SCHEDULE: (200, schedule(paused=paused, **sched)),
                    PUT: put or (200, schedule(paused=not paused)),
                    RUNS: (200, {"items": [scrape_run()]})}
    return Api(routes)


def writes(a: Api) -> list:
    return [c for c in a.calls if c.method == "PUT"]


def test_confirmation_page_for_resume_states_the_consequence() -> None:
    page = make_client(api(True)).get("/operacion/scraper/reanudar")
    assert page.status_code == 200
    for t in ("Reanudar el scraper", "volverá a recorrer los anuncios", "Confirmar y reanudar", "Volver sin cambios"):
        assert t in page.text


def test_confirmation_page_for_pause() -> None:
    page = make_client(api(False)).get("/operacion/scraper/pausar")
    assert "Confirmar y pausar" in page.text and "No borra nada" in page.text


def test_unknown_action_is_a_404_and_calls_nothing() -> None:
    a = api(True)
    assert make_client(a).get("/operacion/scraper/borrar").status_code == 404
    assert writes(a) == []


def test_resume_in_live_mode_without_live_enabled_is_blocked_without_a_form() -> None:
    page = make_client(api(True, mode="live", live_enabled=False)).get("/operacion/scraper/reanudar")
    assert page.status_code == 409
    assert "scraper en vivo debe estar habilitado" in page.text
    assert "Confirmar y reanudar" not in page.text


def test_post_without_csrf_is_rejected_and_writes_nothing() -> None:
    a = api(True)
    r = make_client(a).post("/operacion/scraper/reanudar", data={})
    assert r.status_code in (400, 403) and writes(a) == []


def test_post_resumes_and_redirects_with_a_notice_key() -> None:
    a = api(True)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 303 and r.headers["location"] == "/operacion?aviso=reanudado"
    assert len(writes(a)) == 1 and writes(a)[0].content == b'{"paused":false}'


def test_a_second_post_when_already_active_writes_nothing() -> None:
    a = api(False)  # ya activo
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 303 and r.headers["location"] == "/operacion?aviso=sin-cambio"
    assert writes(a) == []


def test_post_pauses() -> None:
    a = api(False)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/pausar").text)
    r = c.post("/operacion/scraper/pausar", data={"csrf": token})
    assert r.headers["location"] == "/operacion?aviso=pausado" and len(writes(a)) == 1


def test_a_409_from_the_api_shows_a_fixed_text_and_does_not_retry() -> None:
    gate = (409, "texto del servidor que no se debe mostrar")
    a = api(True, put=gate)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code == 409
    assert "texto del servidor" not in r.text and "scraper en vivo debe estar habilitado" in r.text
    assert len(writes(a)) == 1


def test_api_down_on_post_shows_a_message_not_a_trace() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")
    a = api(True, put=boom)
    c = make_client(a)
    token = csrf_of(c.get("/operacion/scraper/reanudar").text)
    r = c.post("/operacion/scraper/reanudar", data={"csrf": token})
    assert r.status_code in (503, 200) and "Traceback" not in r.text


def test_runs_screen_lists_up_to_20_with_labels() -> None:
    items = [scrape_run("partial"), scrape_run("failed", error_code="timeout"), scrape_run("blocked")]
    a = Api({RUNS: (200, {"items": items})})
    page = make_client(a).get("/operacion/ejecuciones")
    assert page.status_code == 200
    for t in ("Ejecuciones del scraper", "parcial", "falló", "bloqueada", "Las últimas 20"):
        assert t in page.text
    call = next(c for c in a.calls if c.url.path.endswith("/market/runs"))
    assert call.url.params["limit"] == "20"


def test_runs_screen_with_the_api_down_is_a_503_with_a_spanish_message() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")
    page = make_client(Api({RUNS: boom})).get("/operacion/ejecuciones")
    assert page.status_code == 503 and "Traceback" not in page.text
```

- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_operation_actions.py -q 2>&1 | tail -8`.
- [ ] **Step 3: Implementar** siguiendo `routes_pilot_actions.py`: `ACTIONS` como lista blanca, id de acción validada antes de cualquier llamada, POST con `csrf_valid` primero, relectura de `GET /market/schedule`, comparación `schedule["paused"] is desired` (si ya está, redirect `?aviso=sin-cambio` sin escribir), `api.request("PUT", "/market/schedule", body={"paused": desired})`, `ApiError.kind == "conflict"` → re-muestra la confirmación con `LIVE_BLOCK` y estado 409, otro error → mensaje fijo y 503, éxito → 303 con la clave. `SHAPE_ERRORS` capturados a mano en el POST. La pantalla de ejecuciones usa `operation.runs_card(..., limit=20)` y la nota «Las últimas 20, de la más reciente a la más antigua.» y «Estados posibles: en cola, en curso, correcta, parcial, falló y bloqueada.». El enlace «Ver todas las ejecuciones» de M15 apunta a `/operacion/ejecuciones`.
- [ ] **Step 4:** pruebas del archivo y de la Task 3, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: confirmar pausar o reanudar el scraper y lista de ejecuciones`.

---

### Task 5: Menú «Más» (M18)

**Files:**
- Modify: `src/nicheradar/web/templates/components.html` (bottomnav l.21-31: la pestaña «Más» deja de ser `tab--soon` y apunta a `/mas`), `src/nicheradar/web/static/css/app.css` (quitar o conservar `.tab--soon` según uso)
- Create: `src/nicheradar/web/routes_more.py`, `src/nicheradar/web/templates/mas.html`; modificar `app.py` (`include_router`)
- Create (pruebas): `tests/test_web_more.py`; Modify: `tests/test_web_pilot_list.py` y `tests/test_web_today.py` solo si fijan el `<span class="tab tab--soon">` de «Más» (buscar con grep)

**Interfaces:**
- Produces: `GET /mas` (`active_tab="mas"`) con la lista «Operación» (enlace a `/operacion`, subtítulo «Scraper de mercado y subnichos») y el botón «Salir» (POST `/salir` con CSRF, ya existente). **No** incluye Análisis de canal ni nada del radar.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_more.py`): la ruta pide sesión (303); la página contiene «Más», «Operación», «Scraper de mercado y subnichos», un `<form method="post" action="/salir">` con campo `csrf`, y **no** contiene «Análisis de canal»; la barra inferior ya no tiene la pestaña deshabilitada («Próximamente» ausente) y «Más» enlaza a `/mas` (`href="/mas"`); en `/mas` la pestaña «Más» queda marcada activa (`aria-current`/clase activa, según el macro); en `/operacion` también.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_more.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** la lista de pestañas `("mas","⋯","Más","/mas")`, la ruta y la plantilla (clases existentes `list`, `card`, `btn`).
- [ ] **Step 4:** `uv run pytest tests/test_web_more.py tests/test_web_pilot_list.py tests/test_web_today.py tests/test_web_assets.py -q`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: menú Más con Operación y salida`.

---

### Task 6: La calibración trata la cifra como mínimo estimado (opción A)

**Files:**
- Modify: `src/nicheradar/web/calibration.py` (`_method_text` l.165-175, `view` l.215-267, constantes), `src/nicheradar/web/templates/pilotos/_calibracion.html`, `src/nicheradar/web/templates/hoy.html` (l.32), `docs/web-movil.md`
- Modify (pruebas): `tests/test_web_calibration.py`, `tests/test_web_pilot_panel.py`, `tests/test_web_today.py`

**Interfaces:**
- Produces: `LOWER_BOUND_METHODS: frozenset[str] = frozenset({"claude_sessions_plus_assumed"})`; `view(...)` añade `lower_bound: bool` (verdadero si algún video medido declara un método de ese conjunto); cuando `lower_bound`:
  - `method_text` = «mínimo estimado (método claude_sessions_plus_assumed)» (el nombre real del método);
  - `streak_text` = «Racha de hasta {limit} minutos: {run} de {consecutive} (posible: las cifras son un mínimo)»;
  - si la racha alcanza el criterio, `passes` sigue siendo verdadero pero el chip de Hoy y la propuesta dicen «Podrías pasar a régimen» en lugar de «Pasa a régimen», con la nota «Las cifras son un mínimo estimado: confírmalo con tu propio criterio.»;
  - cada fila medida pasa de «58 min» a «≥ 58 min».
  - Con cualquier otro método, o sin método, el texto actual no cambia.

- [ ] **Step 1: Pruebas que fallan:** en `tests/test_web_calibration.py`: un piloto con videos `[58, 59, 55]` y `human_minutes_method="claude_sessions_plus_assumed"` da `lower_bound` verdadero, `method_text == "mínimo estimado (método claude_sessions_plus_assumed)"`, `streak_text` con «(posible: las cifras son un mínimo)», filas «≥ 58 min», y el texto de propuesta «Podrías pasar a régimen» y no «Pasa a régimen»; con otro método (`gate_waits`) conserva «estimado (método gate_waits)», «58 min» y «Pasa a régimen»; con métodos mezclados que incluyan el de mínimo, `lower_bound` es verdadero y `method_text` sigue siendo «métodos mezclados»; un video sin medir sigue diciendo «sin medir» (nunca «≥»); un 0 medido dice «≥ 0 min». En `test_web_pilot_panel.py` y `test_web_today.py`: la pestaña y la tarjeta de Hoy muestran «Podrías pasar a régimen» con ese método y la nota; un nombre de método hostil se escapa.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_calibration.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** los cambios de texto como ramas por `lower_bound` (sin tocar `streak()` ni la lógica numérica) y actualizar `docs/web-movil.md` («por qué una cifra de `claude_sessions_plus_assumed` es un mínimo y la racha es “posible”»).
- [ ] **Step 4:** `uv run pytest tests/test_web_calibration.py tests/test_web_pilot_panel.py tests/test_web_today.py -q`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: la calibración rotula como mínimo estimado la cifra de sesiones de Claude`.

---

### Task 7: Integración, capturas y documentación

**Files:**
- Modify: `tests/test_web_smoke_screens.py` (añadir `/operacion`, `/operacion/ejecuciones`, `/mas` a `ROUTES`; `/market/schedule` y `/market/runs` a `RESOURCES`, a `fixtures` y a `NAN_PATHS`; los dos POST nuevos a `POSTS`; claves `stage`, `status`, `error_code` a `STRUCTURAL` solo si se pintan como código), `scripts/web_preview.py`, `scripts/web_preview_data.py` (`SCHEDULE`, `RUNS`), `tests/test_web_preview.py`, `docs/web-movil.md`, `docs/comandos.md` si cita la cabecera

- [ ] **Step 1:** Extender la prueba de humo: texto hostil recursivo, API caída, formas mal hechas (`items` como cadena o lista de números, `status` numérico, `interval_seconds` `NaN`), fechas sin zona, `NaN` crudo en el cuerpo, CSP idéntica y ningún recurso externo; los dos POST sin CSRF → 302/303/400/403 y ninguna escritura; estado no permitido → 409 y ninguna escritura. Cada fallo es un defecto real: se corrige con su prueba (RED primero); no se debilita nada.
- [ ] **Step 2:** Datos de vista previa (`SCHEDULE` pausado, `RUNS` con una parcial, una correcta y una fallida) y la entrada `"operacion": "/operacion"` (más `"mas"` y `"ejecuciones"`) en `web_preview.py`; mirar cada PNG y listar defectos visibles (texto cortado, solapes, objetivos táctiles menores de 44 px); corregir los obvios.
- [ ] **Step 3:** `docs/web-movil.md`: Operación, el menú Más, la confirmación del scraper, la sesión de 5 días, la cabecera sin radar y la calibración como mínimo estimado; indicar que **el radar de oportunidades no está en la web** y que «Análisis de canal» tampoco.
- [ ] **Step 4: Validación completa:** `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin PATH="$PWD/.venv/bin:$PATH" uv run pytest -q` (en primer plano, unos 400 s) — todo en verde.
- [ ] **Step 5: Commit** `docs: capturas, prueba de humo y documentación de Operación`.

---

## Fuera de este plan

Alinear las pantallas ya implementadas con el Figma ordenado (tarjeta «Decisión» con píldoras, «Recorrido hasta el piloto» en nichos y subnichos, sección de nichos en Hoy, informe y autorizar unificados): plan propio, después de este. «Proponer subnicho», Compartir en Android y la lectura de tweets (plan de API y plan de web propios). Borrar código del radar del servidor. Retiro de Streamlit (3f). Desplegar nada.

## Self-Review

- **Cobertura del spec 3a:** avisos de estado y Operación del scraper (Task 3), pausar y reanudar con confirmación y ejecuciones (Task 4), resumen de subnichos (Task 3), menú Más (Task 5), cabecera sin radar (Task 1), sesión de 5 días (Task 2), calibración como mínimo (Task 6, opción A del propietario), humo, capturas y docs (Task 7). Radar, proveedores, preflight y `ApiClient` con cabeceras quedan fuera por decisión 5.
- **Marcadores de relleno:** ninguno; los textos exactos, las firmas y las pruebas están escritos. Las tareas que modifican código existente indican el archivo, la línea y el comando para localizar cada uso.
- **Consistencia de tipos:** `scraper_card`, `runs_card`, `subniches_card`, `operation_view`, `AVISOS`, `ACTIONS`, `LIVE_BLOCK` y `confirm_view` se nombran igual en todas las tareas; `schedule` y `scrape_run` son los builders de `tests/web_helpers.py` usados por las Tasks 3, 4 y 7.
- **Review Focus:** 1, 2 y 5 en la Task 3; 3 y 4 en la Task 4.
