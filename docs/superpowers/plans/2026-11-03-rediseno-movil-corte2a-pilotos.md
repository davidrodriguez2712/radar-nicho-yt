# Rediseño móvil, corte 2a: seguimiento de pilotos

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el propietario siga sus pilotos desde la web móvil: lista (M5), panel con pestañas (M6) y preparación del canal (M7), las acciones seguir, cerrar y cancelar con confirmación, el resumen de cierre, y la tarjeta de pilotos de «Hoy» con enlaces reales.

**Architecture:** Mismo patrón que el corte 1: rutas FastAPI delgadas (sesión + CSRF) que piden datos a `ApiClient`, módulos de modelo de vista que derivan lo que se muestra (bloqueos, siguiente acción, fechas) **sin inventar datos**, y plantillas Jinja2 con autoescape. En la API privada solo se añade lo mínimo y de solo lectura: un endpoint de videos por piloto y campos aditivos en la lista.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy Core (API), Jinja2 + HTMX (web), httpx `MockTransport` y Postgres de pruebas (`NR_TEST_POSTGRES_BIN`), pytest, ruff, mypy, Chrome sin interfaz para capturas.

**Spec:** `docs/superpowers/specs/2026-11-02-rediseno-movil-corte2-design.md` (secciones 1 a 3 y 7; la 2b —minutos humanos y M13— queda fuera). Plan previo: `docs/superpowers/plans/2026-11-02-rediseno-movil-corte1-resto.md`. Diseño: Figma `JmBvlfNURrV226WOZLuCEz`: M5 `20:111`, M6 `20:246`, M7 `20:410`, M14 `36:2`.

## Código que ya existe y se reutiliza (no reescribir)

- Web: `src/nicheradar/web/` (`app.py`, `deps.py` con `current_session`, `render(..., with_radar=False)`, `shape_guard`, `_fragment`; `client.py` con `ApiClient` y `ApiError` cuyo `.detail` conserva el cuerpo 422; `format.py` con `usd`, `pct`, `compact`, `local_datetime`, `spanish_date`; `report.py`; `routes_pilots.py` y `pilots_form.py` (autorizar); `today.py` y `routes_today.py` (Hoy); plantillas `base.html`, `components.html` (`chip`, `button`, `topbar`, `bottomnav`, `segmented`), CSS `static/css/app.css`) y las pruebas `tests/web_helpers.py` (`Api`, `make_client`, `csrf_of`, `pilot_item`, `HOSTILE`, …), `tests/test_web_smoke_screens.py`, `tests/test_web_shape_guard.py`.
- API de pilotos: `src/nicheradar/pilots_api.py` (rutas), `src/nicheradar/pilots/service.py` (`get_pilot`, `_detail`, `list_pilots`, `_videos_for_rules`, `_row`, `_own`, `decide`, `cancel`, `closing_summary`), tablas `pilot_videos` y `pilot_shorts_measurements` en `repositories/schema.py`, pruebas de API en `tests/test_pilots_api.py` (`ready_dossier`, `authorize_body`, `deliver`, `bearer`, `isolated_engine`, marca `postgres`).

## Formas verificadas de la API de pilotos (leídas del código el 2026-11-02)

- `GET /pilots?status=&limit≤100` → `{items}`; item: `pilot_id`, `status` (`autorizado|entregado|en_ejecucion|decision_pendiente|cerrado|cancelado`), `niche_label`, `format`, `target_channel`, `authorized_at`, `last_report_at`, `channel_last_contact_at`, `totals{videos,published,measured,by_stage{},spent_usd,equivalent_usd,machine_minutes,machine_minutes_complete}`, `proposal{action,reason}`, `needs_decision`. Más recientes primero; sin `offset`.
- `GET /pilots/{id}` → los de arriba más `language`, `authorized_by`, `valid_until`, `delivered_at`, `first_report_at`, `closed_at`, `close_reason`, `channel` (`{reported_at, channel_status, checks[{id,label,ok,detail,expires_at}], note}` o `null`), `package` (pilot-package-v1 congelado: `niche`, `evidence`, `dossier{request_id,…}`, `budget{currency,low,likely,high,max_videos,basis}`, `stop_rules`, `close_after_failed_milestones`, y los campos opcionales de cadencia/preparación **si el paquete los trae** —verificar los nombres reales en `pilots/contracts.py` antes de usarlos—), `evaluation{rules[{id,text,milestone,status,detail}],milestones[{key,rules,status}],totals,warnings,close_after}`, `proposal`, `needs_decision`, `acknowledged[]`, `events[{at,actor,kind,detail}]`. Estados de reglas e hitos: `pendiente|cumple|no_cumple|sin_datos_suficientes|no_evaluable|revision_manual`. Tipos de evento: `authorized, gate_failure_accepted, superseded, delivered, first_report, decision_pending, decision_seguir, decision_cerrar, cancelled`.
- `POST /pilots/{id}/decision` cuerpo `{decision: "seguir"|"cerrar", note (1..1500), actor?}` → `{pilot_id,status}`; `seguir` solo desde `decision_pendiente`; `cerrar` no desde `autorizado`/`entregado`; 409 `bad_transition|closed|…` con `detail{code,message}`.
- `POST /pilots/{id}/cancel` cuerpo `{reason (texto), actor?}`; solo desde `autorizado`/`entregado`.
- `GET /pilots/{id}/closing-summary` → `text/plain` Markdown; 409 `bad_transition` si el piloto no está `cerrado`. **`ApiClient.request` hoy solo devuelve JSON**: para este texto hace falta un método nuevo (Task 4).
- Las rutas humanas exigen el token de servicio; un token de canal solo ve sus pilotos.

## Global Constraints

- Todo lo de los planes anteriores sigue vigente: misma app y puerto; el contenedor solo conoce `NR_API_URL`, `NR_SERVICE_TOKEN`, `NR_DASHBOARD_PASSWORD`; `NR_DASHBOARD_UI=streamlit` por defecto; CSP propia sin recursos externos ni estilos o scripts en línea; texto de la API siempre escapado (nada de `|safe` ni Markdown sobre datos de la API); identificadores validados con `fullmatch` antes de usarlos en rutas o enlaces (`pilot_id` con `^pil_\d{8}_[a-z0-9_-]+$`, informes con la expresión de UUID); avisos solo desde un conjunto fijo de claves; todo POST con sesión y CSRF antes de llamar a la API (403 y cero llamadas si falla); pantallas GET protegidas con `shape_guard`, y los POST que redibujan una página con un guardia equivalente; una llamada principal fallida usa `render(..., with_radar=False)`; listas con tope de 100 avisan cuando llegan a 100; fechas sin zona horaria se interpretan como UTC; números no finitos se muestran «—».
- Todo texto que escribe el **canal** (`channel.checks[].label/detail`, `channel.note`, `events[].detail`, `close_reason`, `evaluation.rules[].text/detail`) y el que escribe el propietario (nota de decisión, motivo de cancelación) se trata como no confiable: escapado siempre.
- **No se inventan datos.** Lo que la API no entrega se omite o se rotula «tentativa»: la frase «Elegir la postura editorial del video N» se omite; las fechas de próxima revisión solo aparecen si hay base; la cadencia solo si el paquete la trae.
- **Ningún token ni clave se muestra** en la web; la emisión del token del canal sigue en `scripts/pilots.py token-issue`.
- Las acciones `seguir`, `cerrar` y `cancelar` son irreversibles o casi: exigen una pantalla de confirmación (GET) con la consecuencia explícita y la nota; el POST valida la nota (1 a 1500 caracteres, o el motivo de cancelación con el mismo límite) y el estado del piloto antes de llamar a la API.
- Móvil de 390 px de base (360 sin desplazamiento horizontal); objetivos táctiles ≥ 44 px; paleta del Figma (Inter; fondo `#fff8f5`; primario `#be123c`; tarjetas blancas con borde `#f0e3dc` y radio 16; botones en píldora; etiquetas de 11 px).
- Cambios de API: solo de lectura y aditivos (Task 1); sin migraciones; sin tocar contratos de reporte ni el paquete; nada se despliega con este plan.

## Rulings de diseño

1. **Campos aditivos en la lista.** Para que M5 muestre bloqueos del canal («Falta autorizar YouTube», «vence el 7 dic») sin hacer 100 llamadas de detalle, `GET /pilots` añade a cada item `valid_until`, `delivered_at` y `channel` (el mismo bloque que ya devuelve el detalle). Es aditivo; si una prueba existente compara el item completo se actualiza. Costo si es incorrecto: quitar tres claves.
2. **Pestañas por query, no por rutas.** El panel es `/pilotos/{id}?pestana=resumen|preparacion|videos|reglas|historial` (por defecto `resumen`); `/pilotos/{id}/preparacion` responde 303 a `?pestana=preparacion` (conserva la ruta del spec). Un valor de `pestana` desconocido cae en `resumen`.
3. **Tras autorizar** (corte 1) la redirección pasa de `/informes/{id}?aviso=piloto&piloto=…` a `/pilotos/{pilot_id}?aviso=autorizado` cuando el `pilot_id` cumple la expresión regular; si no, se conserva el comportamiento anterior.
4. **«Hoy»:** la tarjeta de pilotos enlaza al panel y «Ver pilotos» pasa a ser un enlace a `/pilotos`; la tarjeta de pilotos en calibración (M14) **no** entra: es 2b.
5. **Fechas.** El plazo de preparación es `delivered_at + preparation_days` solo si el paquete trae `preparation_days`; el hito de semana o mes se calcula desde `authorized_at`; el de video se calcula solo si el paquete trae cadencia planificada, si no se escribe «al llegar al video N». Todas llevan «(tentativa)».

## Review Focus

1. Texto hostil (`**x**`, `<script>`, `[x](https://evil.test)`) en notas, checks, eventos, motivos de cierre y reglas: escapado en M5, M6, M7 y la confirmación (Tasks 2 a 4).
2. `seguir`/`cerrar`/`cancelar` sin CSRF, con nota vacía o de más de 1500 caracteres, o sobre un piloto en el estado equivocado: la API recibe cero llamadas cuando falla la validación local y un 409 de la API se muestra con mensaje claro y la nota conservada (Task 4).
3. Un piloto con `channel` nulo, `checks` vacíos, fechas sin zona, estados desconocidos, `package` sin los campos opcionales y 100 pilotos en la lista: ninguna pantalla da 500 (Tasks 2 y 3).
4. `pilot_id` malformado, con salto de línea final o de otro formato en la ruta, en los POST y en los enlaces: 404 sin llamar a la API (Tasks 2 a 5).
5. API caída o lenta en cada pantalla, y «Hoy» con la fuente de pilotos caída (Tasks 2 a 5).
6. El endpoint de videos: un token de canal pide los videos de un piloto ajeno → 404, no 403 ni datos; piloto sin videos → lista vacía; números y fechas serializados sin NaN (Task 1).

---

### Task 1: API — videos por piloto y campos aditivos en la lista

**Files:**
- Modify: `src/nicheradar/pilots/service.py` (`list_videos`, campos aditivos en `list_pilots`), `src/nicheradar/pilots_api.py` (ruta), `docs/pilots.md`
- Modify: `tests/test_pilots_api.py` (o crear `tests/test_pilots_videos_api.py` si el archivo ya es muy grande)

**Interfaces:**
- Consumes: `_row`, `_own`, `videos`/`shorts` (tablas), `_plain`, `Anyone`/`Db` dependencias de `pilots_router`.
- Produces: `service.list_videos(connection, pilot_id: str, channel_id: str | None) -> list[dict[str, Any]]` y la ruta `GET /api/v1/pilots/{pilot_id}/videos` → `{"items": [{"video_id","source_state","stage","visibility","published_at","cost_usd","cost_equivalent_usd","machine_minutes","failure_code","measurement"}]}` ordenados por `published_at` ascendente (nulos al final) y luego `video_id`; `measurement` es `null` o `{measured_at, window_days, views, avd_pct, browse_share_pct, subscribers_gained, …campos Shorts presentes}`; `GET /pilots` items con `valid_until`, `delivered_at`, `channel` además de los actuales.

- [ ] **Step 1: Pruebas que fallan**

Añadir pruebas de API (patrón de `tests/test_pilots_api.py`: `isolated_engine`, `ready_dossier`, `authorize_body`, `deliver`, `bearer`; leer cómo suben reportes las pruebas existentes —`report_body` o similar— y reutilizarlo):

```python
def test_videos_lists_the_reported_videos_in_publication_order(isolated_engine: Engine) -> None:
    # authorize + deliver + submit a report with two videos (one published earlier, one not yet published)
    # GET /pilots/{id}/videos with the service token → 200
    # items == 2, ordered by published_at asc with null last; keys exactly the contract list;
    # cost_usd serialized as a number/string consistently with GET /pilots/{id} (no Decimal repr issues)
    ...

def test_videos_of_a_pilot_without_reports_is_an_empty_list(isolated_engine: Engine) -> None:
    # authorized pilot, no reports → {"items": []}
    ...

def test_videos_follow_the_same_visibility_rules_as_the_detail(isolated_engine: Engine) -> None:
    # channel token of ANOTHER channel → 404 (same body as detail's not_found), no data
    # the pilot's own channel token → 200
    # no credential → 401; malformed pilot_id → 404 (not_found), never 500
    ...

def test_a_shorts_video_includes_its_measurement_fields(isolated_engine: Engine) -> None:
    # shorts pilot + v2 report with a measurement → item["measurement"] has engaged_views, avg_view_pct, …
    ...

def test_the_pilot_list_exposes_valid_until_delivered_at_and_channel(isolated_engine: Engine) -> None:
    # after delivery and a report with checks: GET /pilots item has valid_until, delivered_at and
    # channel == the same block GET /pilots/{id} returns; for an undelivered pilot delivered_at is None
    # and channel is None
    ...
```

Escribir los cuerpos completos usando los ayudantes reales del archivo (no inventar fixtures: leer `report(...)`/`submit` en `tests/test_pilots_api.py` y `tests/pilot_samples.py`).

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `export NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin; uv run pytest tests/test_pilots_api.py -q -k "videos or list_exposes" 2>&1 | tail -8`
Expected: FAIL (ruta 404 / claves ausentes).

- [ ] **Step 3: Implementar**

En `service.py`, añadir `list_videos` reutilizando la consulta de `_videos_for_rules` pero seleccionando también `visibility`, `source_state`, `failure_code`, `window_days`, `subscribers_gained` y los campos Shorts con valor; devolver `_plain(...)`; aplicar `row = _row(connection, pilot_id)` y `_own(row, channel_id)` primero (mismo manejo de `not_found`). En `list_pilots` añadir `"valid_until": row["valid_until"]`, `"delivered_at": row["delivered_at"]`, `"channel": row["channel_info"]`. En `pilots_api.py` añadir, **antes** de `/pilots/{pilot_id}` si el orden importa:

```python
    @router.get("/pilots/{pilot_id}/videos")
    def videos_of(pilot_id: str, who: Anyone, connection: Db) -> dict[str, Any]:
        try:
            return {"items": service.list_videos(connection, pilot_id, who.channel_id)}
        except service.PilotError as error:
            raise _http(error) from error
```

Un `pilot_id` mal formado debe terminar en 404 como en el detalle (no 500): reutilizar la validación de `_row`. Actualizar `docs/pilots.md` (tabla de rutas) con la ruta nueva y los campos aditivos.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_pilots_api.py tests/test_pilots_dashboard.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS; ruff y mypy sin errores. Si una prueba existente compara el item de la lista completo, actualizarla (ruling 1).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar tests docs/pilots.md
git commit -m "feat: GET /pilots/{id}/videos y campos aditivos en la lista de pilotos"
```

---

### Task 2: Lista de pilotos (M5), derivaciones y navegación

**Files:**
- Create: `src/nicheradar/web/pilots_view.py`, `src/nicheradar/web/routes_pilot_list.py`, `src/nicheradar/web/templates/pilotos/lista.html`, `src/nicheradar/web/templates/pilotos/_lista.html`
- Modify: `src/nicheradar/web/app.py` (router), `src/nicheradar/web/templates/components.html` (pestaña «Pilotos» activa), `tests/web_helpers.py` (`pilot_detail`, `pilot_video`, ampliar `pilot_item` con `valid_until`, `delivered_at`, `channel`)
- Create: `tests/test_web_pilot_list.py`, `tests/test_web_pilots_view.py`

**Interfaces:**
- Consumes: `render`, `current_session`, `shape_guard`, `_fragment` de `deps`; `format.local_datetime`/`spanish_date`.
- Produces: en `pilots_view.py`: `STATUS_CHIP` (`autorizado`→«Autorizado»/neutral, `entregado`→«Preparando»/amber, `en_ejecucion`→«En ejecución»/green, `decision_pendiente`→«Decisión pendiente»/rose, `cerrado`→«Cerrado»/neutral, `cancelado`→«Cancelado»/neutral), `ACTIVE`, `CLOSED`, `PILOT_RE`, `blockers(item: dict, now: datetime) -> list[dict]` (cada uno `{"text","kind"}`), `next_action(item: dict) -> str | None`, `dates(detail: dict, now: datetime) -> list[dict]`, `progress_text(item: dict) -> str` («3 de 10 videos»), `list_view(items: list[dict], filter_key: str, now: datetime, timezone: str) -> dict` (tarjetas, conteos Todos/Activos/Con bloqueo/Cerrados, `contact_text` «Tu Mac: último contacto hace 6 h»), `parse_filter(params) -> str`; rutas `GET /pilotos` (página o fragmento HTMX); en pruebas `pilot_detail(...)`, `pilot_video(...)`.

- [ ] **Step 1: Pruebas que fallan**

Añadir fixtures a `tests/web_helpers.py`:

```python
def pilot_detail(pilot_id: str = "pil_20261102_historia", **over: object) -> dict[str, object]:
    base = pilot_item(pilot_id) | {
        "language": "en", "authorized_by": "propietario (web)", "valid_until": "2026-11-16T03:00:00Z",
        "delivered_at": "2026-11-03T10:00:00Z", "first_report_at": None, "closed_at": None, "close_reason": None,
        "channel": {"reported_at": "2026-11-03T11:00:00Z", "channel_status": "active", "note": None,
                    "checks": [{"id": "youtube_oauth", "label": "Autorizar subida y medición de YouTube",
                                "ok": True, "detail": None, "expires_at": "2026-11-10T00:00:00Z"}]},
        "package": {"niche": {"label": "historia militar explicada", "format": "long", "language": "en"},
                    "dossier": {"request_id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6", "schema": "dossier-v3",
                                "recommendation": "go", "confidence": "medium", "thesis": "t", "unknowns": []},
                    "budget": {"currency": "USD", "low": 3, "likely": 19.5, "high": 41, "max_videos": 10,
                               "basis": "x"},
                    "stop_rules": [], "close_after_failed_milestones": 2},
        "evaluation": {"rules": [], "milestones": [], "totals": {}, "warnings": [], "close_after": 2},
        "acknowledged": [], "events": [],
    }
    return base | over


def pilot_video(video_id: str = "v1", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "video_id": video_id, "source_state": "PUBLICADO", "stage": "published", "visibility": "public",
        "published_at": "2026-11-05T12:00:00Z", "cost_usd": 0.32, "cost_equivalent_usd": 1.5,
        "machine_minutes": 70, "failure_code": None, "measurement": None,
    }
    return base | over
```

(Ajustar `pilot_item` para incluir `valid_until`, `delivered_at` y `channel` con los valores de `pilot_detail`, sin romper las pruebas existentes de autorizar/Hoy.) Leer los nombres reales de los campos opcionales del paquete en `pilots/contracts.py` y completar `package` en consecuencia.

Crear `tests/test_web_pilots_view.py` con pruebas unitarias exactas de las derivaciones (todas con `now` fijo):

```python
# tests/test_web_pilots_view.py
from datetime import datetime, timezone

from nicheradar.web.pilots_view import blockers, dates, next_action, progress_text
from tests.web_helpers import pilot_detail, pilot_item

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def test_a_failed_check_becomes_a_blocker_with_its_detail() -> None:
    item = pilot_item(channel={"reported_at": "2026-11-03T11:00:00Z", "channel_status": "active", "note": None,
                               "checks": [{"id": "visual_assets", "label": "Visuales del nicho", "ok": False,
                                           "detail": "Faltan loops", "expires_at": None}]})
    texts = [b["text"] for b in blockers(item, NOW)]
    assert "Falta: Visuales del nicho. Faltan loops" in texts


def test_a_check_expiring_within_seven_days_is_a_blocker_and_a_later_one_is_not() -> None:
    soon = pilot_item(channel={"reported_at": "x", "channel_status": "active", "note": None,
                               "checks": [{"id": "youtube_oauth", "label": "YouTube", "ok": True, "detail": None,
                                           "expires_at": "2026-11-08T00:00:00Z"}]})
    later = pilot_item(channel={"reported_at": "x", "channel_status": "active", "note": None,
                                "checks": [{"id": "youtube_oauth", "label": "YouTube", "ok": True, "detail": None,
                                            "expires_at": "2026-12-08T00:00:00Z"}]})
    assert any("vence el 8 nov" in b["text"] for b in blockers(soon, NOW))
    assert not any("vence" in b["text"] for b in blockers(later, NOW))
    expired = pilot_item(channel={"reported_at": "x", "channel_status": "active", "note": None,
                                  "checks": [{"id": "youtube_oauth", "label": "YouTube", "ok": True,
                                              "detail": None, "expires_at": "2026-11-01T00:00:00Z"}]})
    assert any("venció" in b["text"] for b in blockers(expired, NOW))


def test_stale_contact_unknown_videos_and_pending_decision_are_blockers() -> None:
    item = pilot_item(status="en_ejecucion", channel_last_contact_at="2026-11-01T00:00:00Z",
                      needs_decision=True,
                      totals={"videos": 3, "published": 3, "measured": 1, "by_stage": {"unknown": 1},
                              "spent_usd": 1, "equivalent_usd": 2, "machine_minutes": 10,
                              "machine_minutes_complete": True})
    texts = " | ".join(b["text"] for b in blockers(item, NOW))
    assert "sin contacto" in texts and "1 video con estado desconocido" in texts and "decisión pendiente" in texts


def test_a_closed_pilot_has_no_blockers_and_a_clean_one_has_none() -> None:
    assert blockers(pilot_item(status="cerrado", needs_decision=True), NOW) == []
    assert blockers(pilot_item(), NOW) == []


def test_the_authorization_validity_is_a_blocker_only_for_undelivered_pilots() -> None:
    near = pilot_item(status="autorizado", delivered_at=None, valid_until="2026-11-05T00:00:00Z")
    assert any("vigencia" in b["text"] for b in blockers(near, NOW))
    delivered = pilot_item(status="entregado", valid_until="2026-11-05T00:00:00Z")
    assert not any("vigencia" in b["text"] for b in blockers(delivered, NOW))


def test_next_action_only_states_what_can_be_asserted() -> None:
    assert next_action(pilot_item(needs_decision=True)) == "Decide si sigue o cierra"
    waiting = pilot_item(totals={"videos": 2, "published": 0, "measured": 0, "by_stage": {"awaiting_human": 2},
                                 "spent_usd": 0, "equivalent_usd": 0, "machine_minutes": 0,
                                 "machine_minutes_complete": True})
    assert next_action(waiting) == "2 videos esperan tu veredicto en el canal"
    assert next_action(pilot_item(status="autorizado", delivered_at=None)) == "Falta que tu Mac baje el paquete"
    assert next_action(pilot_item(status="cerrado")) is None


def test_progress_text_uses_the_package_cap_when_present() -> None:
    item = pilot_item(totals={"videos": 3, "published": 3, "measured": 1, "by_stage": {}, "spent_usd": 0,
                              "equivalent_usd": 0, "machine_minutes": 0, "machine_minutes_complete": True})
    assert progress_text(item, max_videos=10) == "3 de 10 videos"
    assert progress_text(item, max_videos=None) == "3 videos"


def test_dates_are_tentative_and_only_present_with_a_basis() -> None:
    detail = pilot_detail()
    rows = dates(detail, NOW)
    assert all("tentativa" in r["label"] or r["label"] in ("Autorizado", "Entregado") for r in rows)
    assert any(r["label"].startswith("Vigencia") for r in rows)
    bare = pilot_detail(delivered_at=None, valid_until=None)
    assert dates(bare, NOW) == [r for r in dates(bare, NOW) if r["label"] == "Autorizado"]
```

Crear `tests/test_web_pilot_list.py` (`api_with` como en tests anteriores con `("GET","/api/v1/pilots")` y `/status`):

```python
# tests/test_web_pilot_list.py  (esqueleto con aserciones exactas; el implementador completa el patrón)
def test_the_list_needs_a_session_and_shows_title_filters_and_one_card_per_pilot() -> None: ...
def test_status_chips_use_the_spanish_names() -> None: ...           # Preparando, En ejecución, Decisión pendiente, Cerrado, Cancelado
def test_filters_todos_activos_con_bloqueo_cerrados_and_their_counts() -> None: ...
def test_junk_filter_values_fall_back_to_todos() -> None: ...
def test_each_card_shows_blockers_next_action_progress_and_the_panel_link() -> None: ...
def test_the_panel_link_is_only_emitted_for_a_valid_pilot_id() -> None: ...   # id con \n, vacío, 'x&y=1' → sin enlace
def test_the_last_contact_line_is_spanish_and_tz_safe() -> None: ...         # tz naive, None, futuro
def test_hostile_text_in_channel_check_labels_and_niche_is_escaped() -> None: ...
def test_a_list_of_exactly_100_pilots_shows_the_truncation_warning() -> None: ...
def test_an_empty_list_has_its_own_message() -> None: ...
def test_an_unavailable_api_gives_a_clear_503_without_a_second_status_call() -> None: ...
def test_an_htmx_request_gets_the_fragment_with_vary_and_history_restore_the_full_page() -> None: ...
def test_malformed_items_do_not_500() -> None: ...                         # items null, item sin totals, status desconocido
def test_the_pilots_tab_is_active_and_a_real_link() -> None: ...
```

Cada prueba debe escribirse completa (no dejar `...`): usar los fixtures de `tests/web_helpers.py`, aserciones sobre el marcado de la tarjeta concreta (`<article class="card">` con el nombre del nicho) y no sobre subcadenas que aparezcan en otra parte de la página.

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_pilots_view.py tests/test_web_pilot_list.py -q 2>&1 | tail -6`
Expected: FAIL (`ModuleNotFoundError: nicheradar.web.pilots_view`).

- [ ] **Step 3: Implementar**

`pilots_view.py` (reglas exactas):

- `PILOT_RE = re.compile(r"^pil_\d{8}_[a-z0-9_-]+$")` y toda comprobación con `fullmatch`.
- `_moment(value)` convierte cadenas ISO a `datetime` con zona (sin zona = UTC; valores inválidos → `None`; nunca lanza).
- `blockers(item, now)`: lista vacía si `status in CLOSED` (`cerrado`, `cancelado`). Si no, en este orden: por cada `channel.checks[]` con `ok is False` → `{"text": f"Falta: {label}" + (f". {detail}" if detail else ""), "kind": "falta"}`; por cada check con `expires_at` válido: vencido → «{label} venció el {d MMM}», en los próximos 7 días → «{label} vence el {d MMM}» (`kind: "vence"`); `status == "autorizado"` sin `delivered_at` y `valid_until` dentro de 3 días → «La vigencia vence el {d MMM} si tu Mac no baja el paquete»; `status in {"entregado","en_ejecucion"}` con `channel_last_contact_at` de hace más de 48 h → «Tu Mac está sin contacto hace {N} h»; `totals.by_stage.unknown > 0` → «{N} video(s) con estado desconocido»; `needs_decision` → «Hay una decisión pendiente». Todo con tolerancia a claves ausentes y tipos inesperados (usa `.get` y comprobaciones de tipo; un `channel` o `checks` inválido se ignora).
- `next_action(item)`: `None` si cerrado o cancelado; si `needs_decision` → «Decide si sigue o cierra»; si `by_stage.awaiting_human > 0` → «{N} video(s) esperan tu veredicto en el canal» (singular/plural correctos); si `status == "autorizado"` y sin `delivered_at` → «Falta que tu Mac baje el paquete»; si no, `None`.
- `progress_text(item, max_videos)`: «{published} de {max_videos} videos» o «{published} videos».
- `dates(detail, now)`: filas `{label, value, note}`: «Autorizado» (`authorized_at`), «Entregado» (`delivered_at`, si existe), «Plazo de preparación (tentativa)» (`delivered_at + preparation_days` si el paquete trae `preparation_days`, con «dentro del plazo»/«vencido»), «Vigencia (tentativa)» (`valid_until` si no hubo entrega) y los hitos de las reglas de parada de tipo semana/mes calculados desde `authorized_at` (`milestone` con formato `kind:value`) rotulados «Revisión (tentativa)»; los de tipo video solo con cadencia del paquete; si no, la nota «al llegar al video N». Formato `d MMM` en español, con la zona configurada.
- `list_view(items, filter_key, now, timezone)`: filtra `todos|activos|bloqueo|cerrados` (`activos` = estados fuera de `cerrado`/`cancelado`; `bloqueo` = activos con al menos un bloqueo), cuenta cada filtro sobre la lista completa, y devuelve por tarjeta `{pilot_id (solo si cumple PILOT_RE, si no None), href, niche_label, status_text, status_kind, format_text, channel_text («canal por definir» si falta), blockers, next_action, progress, budget_cap}`; `max_videos` solo del paquete si el item lo trae (la lista no trae paquete: en la lista se usa solo «{published} videos» salvo que se añada `max_videos`, ver Step 3 de Task 1 como mejora opcional; no inventar).
- `contact_text`: «Tu Mac: último contacto hace {N} h/min/días» con el contacto más reciente entre los pilotos activos, o «Tu Mac: sin contacto todavía».

Ruta `GET /pilotos` (`routes_pilot_list.py`): `shape_guard`; `GET /pilots?limit=100` (error → mensaje con 503, o 200 si fragmento; `with_radar=False`); aviso si llegan exactamente 100; fragmento HTMX con `Vary` como `routes_niches.py`; filtros como radios dentro de `.pill`; pestaña `pilotos` activa. Plantillas con el contenido de M5: título «Pilotos», subtítulo «Dónde está cada uno, qué lo frena y cuándo hay decisión. Fechas tentativas.», chips de filtro con conteos, línea de contacto del Mac, tarjetas con chip de estado, formato, idioma si se conoce, canal, bloqueos («Sin bloqueos» si no hay), siguiente acción, progreso y botón «Abrir». En `components.html`, la pestaña «Pilotos» deja de ser `tab--soon`: `("pilotos", "◫", "Pilotos", "/pilotos")`; actualizar las pruebas que esperaban la pestaña desactivada.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_pilots_view.py tests/test_web_pilot_list.py tests/test_web_assets.py tests/test_web_today.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests
git commit -m "feat: pantalla M5, lista de pilotos con bloqueos derivados y pestaña Pilotos"
```

---

### Task 3: Panel del piloto (M6) y preparación del canal (M7)

**Files:**
- Create: `src/nicheradar/web/pilot_panel.py`, `src/nicheradar/web/routes_pilot_panel.py`, `src/nicheradar/web/templates/pilotos/panel.html`, `src/nicheradar/web/templates/pilotos/_resumen.html`, `_preparacion.html`, `_videos.html`, `_reglas.html`, `_historial.html`
- Modify: `src/nicheradar/web/app.py` (router), `src/nicheradar/web/routes_pilots.py` (redirección tras autorizar, ruling 3), `tests/web_helpers.py` (si hace falta)
- Create: `tests/test_web_pilot_panel.py`

**Interfaces:**
- Consumes: `pilots_view` (`blockers`, `next_action`, `dates`, `STATUS_CHIP`, `PILOT_RE`, `progress_text`), `render`, `current_session`, `shape_guard`, `ApiClient`.
- Produces: `pilot_panel.py`: `TABS = ("resumen","preparacion","videos","reglas","historial")`, `parse_tab(value) -> str`, `STATES_LINE` (los seis pasos del Figma: autorizado → entregado → preparando → en ejecución → decisión pendiente → cerrado, marcando el actual), `panel_view(detail: dict, videos: list[dict] | None, now: datetime, timezone: str, tab: str) -> dict`, `prep_steps(detail) -> dict` (pasos = `channel.checks[]`, plazo y cuenta atrás, texto «Faltan N de M pasos»), `rule_rows(detail)`, `event_rows(detail)`, `video_rows(videos)`, `EVENT_TEXT` (texto en español por `kind`); rutas `GET /pilotos/{pilot_id}` (con `?pestana=` y `?aviso=`) y `GET /pilotos/{pilot_id}/preparacion` (303).

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_pilot_panel.py`; escribir cada prueba completa)

Pruebas mínimas:

```python
def test_a_valid_panel_shows_title_status_line_and_the_five_tabs() -> None: ...
def test_the_state_line_marks_exactly_the_current_state_for_each_status() -> None: ...   # parametrizar 6 estados
def test_summary_shows_blockers_next_action_dates_proposal_rules_and_costs() -> None: ...
def test_costs_show_spent_against_the_package_budget_and_flag_incomplete_machine_minutes() -> None: ...
def test_preparation_tab_lists_the_channel_checks_as_steps_with_status_and_detail() -> None: ...
def test_preparation_counts_missing_steps_and_the_deadline_when_the_package_has_preparation_days() -> None: ...
def test_preparation_without_channel_report_says_the_channel_has_not_reported_yet() -> None: ...
def test_preparation_says_nothing_secret_is_stored_and_tokens_are_issued_in_the_cli() -> None: ...
def test_videos_tab_lists_each_video_with_stage_visibility_cost_and_machine_minutes() -> None: ...
def test_videos_tab_when_the_videos_call_fails_shows_a_note_and_the_rest_still_renders() -> None: ...
def test_rules_tab_lists_each_rule_with_its_milestone_status_and_detail_escaped() -> None: ...
def test_history_tab_translates_event_kinds_and_escapes_details() -> None: ...
def test_an_unknown_tab_falls_back_to_summary() -> None: ...
def test_the_preparation_route_redirects_to_the_tab() -> None: ...
def test_a_malformed_pilot_id_is_404_and_never_reaches_the_api() -> None: ...   # fullmatch, \n final, ../, vacío
def test_unknown_pilot_is_404_and_api_down_is_503_without_status_call() -> None: ...
def test_hostile_text_everywhere_is_escaped() -> None: ...   # note, checks, events, close_reason, rules, niche
def test_package_without_optional_fields_and_null_channel_do_not_500() -> None: ...
def test_the_authorize_success_redirect_goes_to_the_panel() -> None: ...   # ruling 3, ajustar test_web_pilot_authorize
def test_the_notice_comes_only_from_fixed_keys() -> None: ...
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_pilot_panel.py -q 2>&1 | tail -6`
Expected: FAIL (rutas inexistentes).

- [ ] **Step 3: Implementar**

Reglas del panel (textos del Figma M6/M7 entre comillas):

- Cabecera: «Piloto · {niche_label}», chips de estado, formato, idioma y, si hay `target_channel`, el nombre del canal (texto plano; **no** se genera un enlace `youtube.com/@…` porque la API no entrega la URL). `Resumen` incluye: «Estado actual» (día desde el primer reporte y «N de M publicados» cuando hay datos), la línea de seis estados, «Bloqueos y avisos (N)» con cada bloqueo y su responsable («Tú, en tu Mac», «El canal»), «Siguiente acción tuya», «Fechas (tentativas)» (`dates`), «Propuesta de NicheRadar» (`proposal.action` traducido: `seguir`→«Seguir», `cerrar`→«Cerrar», `revision_manual`→«Revisión manual», `sin_datos_suficientes`→«Sin datos suficientes», más `reason` escapado) con los botones «Seguir» y «Cerrar piloto» como **enlaces a las pantallas de confirmación de la Task 4** (deshabilitados si el estado no lo permite: `seguir` solo en `decision_pendiente`, `cerrar` solo si no es `autorizado`/`entregado`/`cerrado`/`cancelado`; «Cancelar piloto» solo en `autorizado`/`entregado`), «Reglas de parada» (resumen), «Costos y tiempos» («Dinero gastado: US$ x de {budget.high}», «Equivalente de Claude: US$ y (no se suma)», «Minutos de máquina: h min» con «(incompleto)» si `machine_minutes_complete` es falso, «Último reporte: hace N h»).
- `Preparación` (M7): «Plazo de preparación: vence el {fecha} (tentativa)» solo si el paquete trae `preparation_days`; «{N} días desde la entrega. Faltan {k} de {n} pasos.»; los pasos son exactamente los `channel.checks[]` (`label`, estado ✓/!, `detail`, y «caduca el …» si `expires_at`); sin `channel` o sin `checks`: «El canal todavía no informó pasos de preparación.»; el bloque «Qué guarda NicheRadar» con los tres puntos del Figma (enlace público del canal solo si existe, el estado de cada paso que informa el canal, «Ninguna clave ni token: viven solo en tu Mac») y la línea «Los tokens del canal se emiten en la línea de comandos (`scripts/pilots.py token-issue`), no desde la web.».
- `Videos`: una fila por video con `video_id`, etapa traducida (`in_production`→«En producción», `awaiting_human`→«Espera tu veredicto», `uploaded`→«Subido», `published`→«Publicado», `measuring`→«Midiendo», `killed`→«Descartado», `blocked`→«Bloqueado», `unknown`→«Estado desconocido»), visibilidad, `published_at`, costo y minutos de máquina; si `GET /pilots/{id}/videos` falla, la pestaña muestra «No se pudieron cargar los videos» y el resto de la página sigue; sin videos: «Todavía no hay videos reportados.».
- `Reglas`: cada regla con `text`, hito (`milestone` traducido: `video:10`→«video 10», `week:6`→«semana 6», `month:6`→«mes 6»), estado traducido, `detail`.
- `Historial`: eventos más recientes primero con `EVENT_TEXT` (`authorized`→«Autorizado», `delivered`→«Entregado al canal», `first_report`→«Primer reporte», `decision_pending`→«Decisión pendiente», `decision_seguir`→«Decidiste seguir», `decision_cerrar`→«Decidiste cerrar», `cancelled`→«Cancelado», `superseded`→«Reemplazado», `gate_failure_accepted`→«Aceptaste una compuerta no cumplida»; kind desconocido: texto plano escapado), actor y `detail` escapados.
- Ruta: `shape_guard`; `pilot_id` con `PILOT_RE.fullmatch` **antes** de llamar a la API (404 con `error.html` si no); `GET /pilots/{id}` (error → 404 si `not_found`, 503 si no; `with_radar=False`); `GET /pilots/{id}/videos` solo si la pestaña es `videos` o `resumen` necesita conteos (si falla, `videos=None`); aviso desde claves fijas (`autorizado`, `seguido`, `cerrado`, `cancelado`); redirigir `/pilotos/{id}/preparacion` a `?pestana=preparacion` con 303.
- Cambiar el redireccionamiento exitoso de `routes_pilots.authorize` según el ruling 3 y actualizar sus pruebas.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_pilot_panel.py tests/test_web_pilot_authorize.py tests/test_web_pilot_list.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests
git commit -m "feat: pantallas M6 y M7, panel del piloto con pestañas y preparación del canal"
```

---

### Task 4: Acciones seguir, cerrar y cancelar, y resumen de cierre

**Files:**
- Modify: `src/nicheradar/web/client.py` (método `request_text`), `src/nicheradar/web/app.py` (router), `tests/test_web_client.py`
- Create: `src/nicheradar/web/pilot_actions.py`, `src/nicheradar/web/routes_pilot_actions.py`, `src/nicheradar/web/templates/pilotos/confirmar.html`, `src/nicheradar/web/templates/pilotos/cierre.html`
- Create: `tests/test_web_pilot_actions.py`

**Interfaces:**
- Consumes: `pilots_view.PILOT_RE`, `render`, `current_session`, `shape_guard`, `ApiClient`.
- Produces: `ApiClient.request_text(method, path, *, params=None, timeout=None) -> str` (devuelve `response.text`; misma gestión de errores que `request`; límite de tamaño de 256 KiB); `pilot_actions.py`: `ACTIONS = {"seguir": {...}, "cerrar": {...}, "cancelar": {...}}` (texto de consecuencia y estados permitidos), `allowed(action: str, status: str) -> bool`, `NOTE_MAX = 1500`, `validate_note(value: str) -> str | None`, `CONFLICT_MESSAGES` por `detail.code` (`bad_transition`, `closed`, `not_found`, …); rutas `GET /pilotos/{pilot_id}/decidir?accion=seguir|cerrar`, `POST /pilotos/{pilot_id}/decidir`, `GET /pilotos/{pilot_id}/cancelar`, `POST /pilotos/{pilot_id}/cancelar`, `GET /pilotos/{pilot_id}/cierre`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_pilot_actions.py` y ampliación de `tests/test_web_client.py`; cada prueba completa)

```python
def test_request_text_returns_the_plain_text_and_maps_errors_like_request() -> None: ...   # test_web_client
def test_request_text_refuses_bodies_over_the_limit() -> None: ...

def test_the_confirmation_page_states_the_consequence_and_has_a_note_field_and_csrf() -> None: ...   # seguir y cerrar y cancelar
def test_an_unknown_action_or_a_disallowed_state_never_shows_the_form() -> None: ...                 # seguir en en_ejecucion, cerrar en autorizado, cancelar en cerrado
def test_posting_a_decision_sends_the_pilot_id_decision_and_note_and_redirects_with_a_notice() -> None: ...
def test_the_actor_and_decision_come_from_the_server_not_the_form() -> None: ...                     # campos hostiles ignorados; actor fijo
def test_the_note_must_be_1_to_1500_characters_and_blank_notes_are_rejected_before_the_api() -> None: ...   # '', '   ', 1501 chars, solo saltos de línea
def test_bad_or_missing_csrf_is_403_with_zero_api_calls_for_all_three_posts() -> None: ...
def test_a_malformed_pilot_id_is_404_without_api_calls() -> None: ...
def test_api_conflicts_are_shown_with_clear_messages_and_the_note_is_kept() -> None: ...             # bad_transition, closed, not_found
def test_an_api_outage_on_post_keeps_the_form_with_a_message() -> None: ...
def test_a_double_submit_of_the_same_decision_is_reported_not_repeated() -> None: ...                # segundo POST → 409 closed de la API mostrado claro
def test_cancel_posts_the_reason_and_redirects_with_the_cancelled_notice() -> None: ...
def test_the_closing_summary_page_shows_the_text_escaped_in_a_pre_and_handles_409() -> None: ...     # piloto no cerrado → mensaje claro
def test_hostile_text_in_the_note_the_reason_and_the_summary_is_escaped() -> None: ...
def test_the_notice_after_an_action_comes_only_from_fixed_keys() -> None: ...
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_pilot_actions.py tests/test_web_client.py -q 2>&1 | tail -6`
Expected: FAIL.

- [ ] **Step 3: Implementar**

- `ApiClient.request_text` reutiliza el cliente y los errores de `request`; rechaza respuestas de más de 256 KiB con `ApiError("error")`; una respuesta de error sigue produciendo `ApiError` tipado; el token solo viaja en la cabecera.
- Las pantallas de confirmación **piden primero el piloto** (`GET /pilots/{id}`) para comprobar el estado con `allowed(...)`; si la acción no está permitida muestran la razón («Solo se puede seguir una decisión pendiente», «Un piloto en preparación se cancela, no se cierra», «Este piloto ya está cerrado») sin formulario. Consecuencias que se muestran: `seguir` → «El piloto continúa hasta el siguiente hito.»; `cerrar` → «Esto cierra el piloto y no se puede deshacer. Se genera el resumen de cierre.»; `cancelar` → «Esto cancela el piloto antes de producir. El canal queda libre.».
- `POST /pilotos/{id}/decidir`: CSRF primero (403, cero llamadas), `PILOT_RE.fullmatch`, acción y nota validadas localmente (error → re-render de la confirmación con 422 y la nota conservada), cuerpo enviado a la API `{"decision": accion, "note": nota_sin_espacios_extremos, "actor": "humano"}` (el `actor` y la decisión salen del servidor/ruta, no de campos ocultos del formulario); éxito → 303 a `/pilotos/{id}?aviso=seguido|cerrado`; conflicto → re-render con el mensaje y la nota; fallo de API → 503 con la nota conservada.
- `cancelar` análogo con `{"reason": motivo, "actor": "humano"}` → aviso `cancelado`.
- `GET /pilotos/{id}/cierre`: `request_text("GET", f"/pilots/{id}/closing-summary")`, se muestra dentro de `<pre>` escapado (nunca Markdown renderizado); 409 `bad_transition` → «El resumen existe solo cuando el piloto está cerrado.»; el enlace «Ver resumen de cierre» aparece en el panel y en el aviso `cerrado` solo si el estado es `cerrado`.
- Los tres POST llevan el guardia de forma inesperada de los POST que redibujan (patrón de la revisión final del corte 1) y `with_radar=False` en los fallos.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_pilot_actions.py tests/test_web_client.py tests/test_web_pilot_panel.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests
git commit -m "feat: seguir, cerrar y cancelar un piloto con confirmación, y resumen de cierre"
```

---

### Task 5: «Hoy» con pilotos reales

**Files:**
- Modify: `src/nicheradar/web/today.py`, `src/nicheradar/web/routes_today.py`, `src/nicheradar/web/templates/hoy.html`, `tests/test_web_today.py`

**Interfaces:**
- Consumes: `pilots_view` (`blockers`, `next_action`, `STATUS_CHIP`, `PILOT_RE`).
- Produces: `today.attention_cards` usa `next_action` y `blockers` y enlaza a `/pilotos/{pilot_id}` (solo con `PILOT_RE.fullmatch`); «Ver pilotos» pasa a enlace real a `/pilotos`.

- [ ] **Step 1: Pruebas que fallan** (ampliar `tests/test_web_today.py`)

```python
def test_a_pilot_needing_something_links_to_its_panel_with_the_derived_reason() -> None: ...
def test_a_pilot_with_a_blocker_but_no_decision_is_listed_with_that_blocker() -> None: ...
def test_the_pilots_link_is_a_real_link_now() -> None: ...                  # reemplaza la aserción de 'Próximamente'
def test_an_invalid_pilot_id_never_becomes_a_link() -> None: ...
def test_closed_and_cancelled_pilots_never_appear_in_the_attention_card() -> None: ...
def test_the_counting_text_stays_correct_in_singular_and_plural() -> None: ...
def test_a_malformed_pilot_item_only_degrades_its_own_card() -> None: ...
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_today.py -q 2>&1 | tail -6`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Un piloto entra en la tarjeta «necesitan algo» si no está `cerrado`/`cancelado` y tiene `needs_decision`, o `next_action` no vacío, o al menos un bloqueo; el texto principal es `next_action` (si existe) o el primer bloqueo; cada tarjeta enlaza al panel. El conteo conserva el singular y el plural del corte 1. Sin cambios en las demás tarjetas ni en la regla de degradar por tarjeta. «Ver pilotos» es un enlace secundario a `/pilotos`.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_today.py tests/test_web_pilot_list.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests
git commit -m "feat: Hoy enlaza a los pilotos y lista lo que cada uno necesita"
```

---

### Task 6: Integración, capturas contra el Figma y documentación

**Files:**
- Modify: `tests/test_web_smoke_screens.py`, `scripts/web_preview.py`, `scripts/web_preview_data.py`, `docs/web-movil.md`, `AGENTS.md` (solo si cambia su lista de archivos)
- Modify (según lo que la prueba de humo exponga): los módulos responsables, cada uno con su prueba específica

**Interfaces:**
- Consumes: todas las rutas de las Tasks 2 a 5.
- Produces: la prueba de humo cubre `/pilotos`, `/pilotos/{id}` (las cinco pestañas), `/pilotos/{id}/decidir?accion=…`, `/pilotos/{id}/cancelar`, `/pilotos/{id}/cierre`; `scripts/web_preview.py` genera `pilotos.png`, `piloto.png`, `preparacion.png` y `confirmar.png`.

- [ ] **Step 1: Prueba de humo que falla (o pasa)**

Ampliar `tests/test_web_smoke_screens.py` con las rutas de pilotos y las mismas cuatro familias de comprobaciones del corte 1: datos hostiles recursivos (todas las cadenas salvo claves estructurales: `status`, `format`, `language`, `stage`, `kind`, `action`, `source_state`, `visibility`, `id`, `pilot_id` válido), API caída, formas mal hechas (`items` nulo, `channel` de otro tipo, `NaN` crudo, fechas sin zona), sin recursos de terceros y CSP idéntico, y **todos los POST nuevos sin CSRF → 403 y cero llamadas a la API**. Cada fallo es un defecto real: corregir en el módulo responsable con su prueba específica (RED primero); no debilitar la prueba de humo.

- [ ] **Step 2: Capturas y documentación**

Extender `scripts/web_preview_data.py` (formas exactas de la API; copiar datos, no importar de `tests/`) y `scripts/web_preview.py` con las cuatro pantallas nuevas. Mirar cada PNG con la herramienta de lectura de imágenes y listar defectos visibles (desbordes, bloques sin estilo, colores, fuente); corregir los defectos obvios (clases usadas por plantillas y ausentes en `app.css`, siguiendo los tokens del Figma). Actualizar `docs/web-movil.md`: pantallas del corte 2a (rutas y API que usa cada una), qué se omite a propósito (frase de postura editorial, URL del canal, fechas sin base, cadencia, emisión de tokens), el aviso de recorte a 100, y que M13 y los minutos humanos son 2b.

- [ ] **Step 3: Validación completa**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy; export NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin; PATH="$PWD/.venv/bin:$PATH" uv run pytest -q 2>&1 | tail -4` (en primer plano y con tiempo de espera largo: la suite tarda unos 200 s).
Expected: todo en verde. Después `uv run python scripts/web_preview.py --out /tmp/web-preview` y confirmar las imágenes nuevas. **La comparación contra el Figma la hace el controlador.**

- [ ] **Step 4: Commit**

```bash
git add tests scripts docs src
git commit -m "docs: capturas y prueba de humo de las pantallas de pilotos del corte 2a"
```

---

## Fuera de este plan

2b (contrato `channel-report-v3`, migración de minutos humanos, `scripts/channel_human_minutes.py`, M13 y la tarjeta de pilotos en calibración de M14); emisión de tokens de canal desde la web; reabrir un piloto cerrado; paridad con Streamlit y su retiro (corte 3); cualquier despliegue (requiere aprobación del propietario).

## Self-Review

- **Cobertura del spec (2a):** M5 (Task 2), M6 y M7 (Task 3), acciones y resumen de cierre (Task 4), M14 parcial (Task 5), endpoint de videos y campos aditivos (Task 1), seguridad de los POST nuevos (Task 4), prueba de humo (Task 6). M13 y los minutos humanos quedan para 2b, como acordó el propietario.
- **Desviación consciente del spec:** el spec decía «un solo endpoint nuevo»; el plan añade además tres campos aditivos a `GET /pilots` (ruling 1) para no hacer 100 llamadas de detalle. Se actualiza el spec en el mismo commit del plan.
- **Rulings:** (1) campos aditivos en la lista; (2) pestañas por query con la ruta `/preparacion` como redirección; (3) tras autorizar se va al panel; (4) «Hoy» sin calibración; (5) fechas solo con base y rotuladas «tentativa». Cada uno anota su costo si es incorrecto.
- **Consistencia de tipos:** `pilots_view` (Task 2) lo usan las Tasks 3 y 5; `PILOT_RE` se define una vez y se usa con `fullmatch` en todas partes; `pilot_detail`/`pilot_video` se añaden a `tests/web_helpers.py` en la Task 2 y los reutilizan las Tasks 3 a 5; `ApiClient.request_text` (Task 4) solo lo usa el resumen de cierre.
- **Riesgos conocidos:** los nombres reales de los campos opcionales del paquete (`preparation_days`, cadencia) hay que leerlos de `pilots/contracts.py` (el plan no los asume); la lista de pilotos no trae paquete, así que «N de M videos» en M5 puede quedar como «N videos» (no se inventa el tope); `GET /pilots` y los reportes están acotados a 100 elementos y la pantalla avisa.
- **Sin placeholders de producción:** las Tasks 1, 2 y 3 traen pruebas y reglas exactas; los esqueletos de pruebas con `...` de las Tasks 2 a 5 son **listas de pruebas con nombre y escenario exacto** que el implementador debe escribir completas (cada una con aserciones sobre el marcado concreto), siguiendo el estilo de los planes anteriores.
