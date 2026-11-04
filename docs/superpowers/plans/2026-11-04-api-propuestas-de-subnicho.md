# API de propuestas y ciclo de vida de subnichos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la web (y más adelante «Compartir») pueda proponer un subnicho a partir de una consulta, un video o un canal, ver la propuesta, y aprobarla, pausarla, reanudarla o archivarla, sin entrar al contenedor del worker. Hoy todo eso solo existe como comandos (`scripts/subniche.py add/approve/pause/resume/archive`).

**Architecture:** Una tabla nueva `subniche_proposal_requests` (migración `0022`) hace de cola: la API solo valida y encola (la web nunca llama a proveedores desde una petición); un paso nuevo del worker, `tick_proposals`, toma las solicitudes en estado `queued`, ejecuta la misma función `intake.add_hypothesis` que usa la terminal y deja `ready` (con el `slug`) o `failed` (con un código). Los cambios de estado reutilizan `store.approve/set_status`. Todo con el token de servicio, sin cambiar la medición ni el worker de medición.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy Core + Alembic, Pydantic v2, Postgres de pruebas (`NR_TEST_POSTGRES_BIN`), pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-11-03-rediseno-movil-corte3-paridad-design.md` (3d y decisión 6) y `docs/superpowers/specs/2026-11-04-compartir-android-y-tweets-de-x-design.md`. Figma M25 a M28 (`49:4`, `49:56`, `49:93`, `49:142`). Brief del backend: `docs/subniche-discovery.md`.

## Global Constraints

- **Aditivo:** una migración que solo crea una tabla; nada de lo existente cambia de forma ni de comportamiento (la CLI sigue funcionando igual).
- **La API no llama a proveedores:** validar, encolar y leer. El YouTube, el modelo de lenguaje y la cuota los usa solo el worker, con sus puertas actuales (`NR_SUBNICHE_ENABLED`, modo real, claves).
- **Nada se aprueba solo:** ninguna propuesta pasa a `active` sin una llamada explícita a `approve`; aprobar no mide al instante (la medición sigue siendo del worker, a más tardar a los 3 días).
- **Entrada no confiable:** el texto de la solicitud (hasta 500 caracteres) y todo lo que venga de YouTube o del modelo se guarda y se devuelve como texto; la API nunca lo interpreta ni lo repite dentro de mensajes de error.
- **Errores con código y mensaje en español fijo** (`{"code","message"}`); el texto del servidor o del proveedor nunca llega al cliente.
- **Idempotencia:** `POST /subniches/proposals` exige cabecera `Idempotency-Key` (8 a 100 caracteres); repetir la misma clave devuelve la misma solicitud sin crear otra.
- **Tope diario:** como máximo `subniche_proposals_per_day` solicitudes nuevas en 24 horas (valor por defecto 100) → 429 `daily_limit`.
- **Enlaces de X (tweets):** siguen sin soportarse (`tweet_not_supported_yet`, 422); su lectura es otro plan.
- Cambios de base de datos: solo la migración `0022` (se aplica en producción en una release con aprobación del propietario). Nada se despliega con este plan.

## Rulings de diseño

1. **Cola propia en lugar de reutilizar `jobs`:** `jobs` está ligada a perfiles y cadencias del radar. Costo si es incorrecto: reescribir `proposals.py` sobre otra cola.
2. **`tick_proposals` corre solo si `subniche_enabled`** (mismo interruptor que la medición) y **antes** de la cadencia de medición, en su propio paso, para que la cadencia de 3 días no retrase las propuestas.
3. **Hasta 3 solicitudes por vuelta del worker** (`BATCH = 3`) para no alargar el latido; una solicitud `running` de más de 30 minutos se marca `failed` con código `abandoned`.
4. **Solo se guarda el código del error**, no el detalle del proveedor; los mensajes en español viven en un diccionario de la API.
5. **Modo manual** (`manual: {label, family, parent}`) solo con entrada de tipo consulta, igual que la CLI (`manual_needs_a_query`).

## Review Focus

1. Dos solicitudes con la misma `Idempotency-Key` y dos solicitudes concurrentes con claves distintas sobre la misma consulta: una sola hipótesis (la segunda termina `failed` con `duplicate`), nunca dos ni una excepción (Tasks 2 y 3).
2. Un worker que muere a mitad de una solicitud `running`: se recupera como `failed` (`abandoned`) sin duplicar la hipótesis (Task 3).
3. Texto hostil en la entrada (HTML, `javascript:`, 500 caracteres, Unicode raro, NUL): se guarda y se devuelve escapado como dato; la validación rechaza lo que no sea consulta, video o canal (Tasks 2 y 4).
4. Transiciones inválidas (aprobar una activa, pausar una propuesta, reanudar una archivada) y slugs inexistentes: 409 y 404 con código y sin cambios (Task 5).
5. Aprobar una hipótesis cuyas consultas no caben en la cuota diaria: el endpoint de vista previa lo dice con cifras y aprobar sigue siendo posible (la medición la saltará con `insufficient_search_cap`), nunca un 500 (Task 5).

---

### Task 1: Migración `0022`, esquema y fijaciones de respaldo

**Files:**
- Create: `migrations/versions/0022_subniche_proposal_requests.py`, `tests/test_subniche_proposal_schema.py`
- Modify: `src/nicheradar/repositories/schema.py` (tabla `subniche_proposal_requests`), `scripts/backup_snapshot.py` (`:174` y el grupo de `REVIEWED_TABLES`), `scripts/backup_mac.py:253`, `tests/test_backup_mac.py` (l.51, 131, 317, 380), `tests/test_channel_report_v2_schema.py` (l.86-90), `tests/test_backup_subniche.py` (clasificación de tablas)

**Interfaces:**
- Produces: tabla `subniche_proposal_requests` con columnas `id UUID PK`, `idempotency_key String(100) NOT NULL UNIQUE`, `input_text String(500) NOT NULL`, `kind String(10) NOT NULL` (CHECK `query|video|channel`), `manual JSONB NULL`, `origin String(12) NOT NULL DEFAULT 'manual'` (CHECK `manual|catalog|marketplace|lead`), `status String(10) NOT NULL DEFAULT 'queued'` (CHECK `queued|running|ready|failed`), `error_code String(80) NULL`, `hypothesis_slug String(60) NULL`, `created_at/started_at/finished_at` con zona; índice `ix_subniche_proposal_status_created (status, created_at)`; revisión `0022` con `down_revision="0021"`; las fijaciones de revisión pasan a `"0022"`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_subniche_proposal_schema.py`, marca `postgres`, siguiendo `tests/test_pilot_human_minutes_schema.py`): el esquema de `schema.py` coincide con la base migrada (columnas, nulabilidad, tipos, longitudes); cada CHECK rechaza un valor inválido dentro de `db.begin_nested()` (`kind="tweet"`, `status="x"`, `origin="x"`) y acepta los válidos; la clave de idempotencia repetida da `IntegrityError`; la migración es aditiva y reversible (subir a `0021`, insertar datos previos, subir a `0022`, comprobar que lo previo se conserva, bajar a `0021` y que la tabla desaparece). Actualizar las fijaciones `"0021"` → `"0022"` y el nombre de la prueba `..._pins_revision_0021` → `..._0022` **sin debilitarlas**; añadir la tabla a un grupo de `REVIEWED_TABLES` y a `test_discovery_group_classification`.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `export NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin; uv run pytest tests/test_subniche_proposal_schema.py tests/test_backup_mac.py tests/test_channel_report_v2_schema.py tests/test_backup_subniche.py -q 2>&1 | tail -8`.
- [ ] **Step 3: Implementar** la migración con docstring en español terminado en `(additive)`, `op.create_table` con las restricciones nombradas como las de `0020`, `op.create_index`, `downgrade()` que borra índice y tabla; la tabla en `schema.py`; las fijaciones.
- [ ] **Step 4:** las pruebas anteriores más `tests/test_subniche_schema.py`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: migración 0022 con solicitudes de propuesta de subnicho`.

---

### Task 2: Servicio de solicitudes (`proposals.py`)

**Files:**
- Create: `src/nicheradar/subniche_discovery/proposals.py`, `tests/test_subniche_proposals.py`
- Modify: `src/nicheradar/config.py` (campo `subniche_proposals_per_day: int = Field(default=100, ge=1, le=1000)`), `.env.example` si lista los límites de subnichos

**Interfaces:**
- Consumes: `inputs.parse_input`, `contracts.ORIGINS`, la tabla de la Task 1.
- Produces:
  - `class ProposalRejected(Exception)` con `.code: str` (`invalid_input`, `tweet_not_supported_yet`, `manual_needs_a_query`, `daily_limit`).
  - `enqueue(conn, raw: str, *, manual: ManualFields | None, origin: str, key: str, now: datetime, per_day: int) -> tuple[UUID, bool]` → `(id, created)`; valida con `parse_input` (tweet → `ProposalRejected("tweet_not_supported_yet")`; entrada que no sea consulta con `manual` → `manual_needs_a_query`); idempotente por `key` (misma clave → `(id_existente, False)` **sin** contar contra el tope); tope: más de `per_day` creadas en las últimas 24 h → `ProposalRejected("daily_limit")`.
  - `claim_next(conn, now: datetime) -> dict | None` (fila `queued` más antigua, con `FOR UPDATE SKIP LOCKED`, pasa a `running` y fija `started_at`).
  - `release_stale(conn, now: datetime, *, minutes: int = 30) -> int` (marca `failed` con `error_code="abandoned"` las `running` más viejas).
  - `finish_ready(conn, request_id: UUID, slug: str, now) -> None`, `finish_failed(conn, request_id: UUID, code: str, now) -> None` (código recortado a 80 caracteres).
  - `get_request(conn, request_id: UUID) -> dict | None` y `list_requests(conn, limit: int = 20) -> list[dict]` (más recientes primero; nunca devuelven `idempotency_key`).

- [ ] **Step 1: Pruebas que fallan** (`tests/test_subniche_proposals.py`, marca `postgres`, fixture `db` de `tests/conftest.py`): encolar una consulta, un video (`https://youtu.be/dQw4w9WgXcQ`), un canal (`@canal_de_prueba`) y una propuesta manual válida → `created=True` y estado `queued`; la misma clave repetida → `(mismo id, False)` y una sola fila; un tweet → `ProposalRejected("tweet_not_supported_yet")`; entrada inválida (`"ab"`, una URL de YouTube no soportada, una consulta con `http`) → `invalid_input`; `manual` con un canal → `manual_needs_a_query`; el tope diario: con `per_day=2`, la tercera solicitud nueva dentro de 24 h → `daily_limit`, y una repetición idempotente después del tope sigue devolviendo la existente; `claim_next` devuelve la más antigua, la deja `running`, y una segunda llamada devuelve la siguiente o `None` (nunca la misma); `release_stale` marca `abandoned` solo las `running` viejas y no toca las recientes; `finish_ready/failed` fijan `finished_at`; `get_request/list_requests` no exponen la clave y respetan el orden; entrada con 500 caracteres de HTML, NUL y Unicode raro se guarda tal cual (las columnas la aceptan) y se devuelve igual.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_subniche_proposals.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** con SQLAlchemy Core sobre `subniche_proposal_requests`; el `slug`, el tipo y el origen de la solicitud salen de `parse_input` y del argumento `origin` (validado contra `ORIGINS`); NUL en la entrada se rechaza con `invalid_input` (Postgres no acepta NUL en `text`) y se prueba.
- [ ] **Step 4:** pruebas del archivo, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: cola de solicitudes de propuesta de subnicho`.

---

### Task 3: Paso del worker `tick_proposals`

**Files:**
- Modify: `src/nicheradar/subniche_discovery/worker.py` (nueva función `tick_proposals`), `src/nicheradar/workers/main.py` (llamarla dentro de `if config.subniche_enabled`, antes de `tick_subniche`)
- Create: `tests/test_subniche_proposals_worker.py`

**Interfaces:**
- Consumes: `proposals.claim_next/finish_ready/finish_failed/release_stale`, `intake.add_hypothesis(engine, config, raw, *, origin, manual, reader, client, clock)`.
- Produces: `tick_proposals(config: Settings, engine: Engine | None = None, *, reader: YouTubeReader | None = None, client: AnthropicClient | None = None, clock: Callable[[], datetime] = utcnow, batch: int = 3) -> dict[str, object]` con `{"service": "subniche_proposals", "status": "idle"|"processed"|"not_configured"|"error", "processed": int, "ready": int, "failed": int}` (serializable a JSON).

- [ ] **Step 1: Pruebas que fallan** (`tests/test_subniche_proposals_worker.py`, marca `postgres`; helpers `FakeReader`, `client_answering`, `seed_policies`, `seed_run`, `enabled_settings`, `GOOD`, `LLM_NOW` de las pruebas de subnichos; ver `tests/test_subniche_worker.py`): sin base de datos configurada y sin motor → `not_configured`; sin solicitudes → `idle`; una solicitud manual (`manual=ManualFields(...)`, no necesita modelo ni YouTube) → `ready` con el `slug` guardado y la hipótesis creada en estado `proposed`; una consulta con el modelo falso (`client_answering(GOOD)`) → `ready`; una solicitud cuyo alta devuelve `{"error": "llm_disabled"}` → `failed` con `error_code="llm_disabled"`; un duplicado → `failed` con `duplicate:...` (recortado a 80); un canal inexistente (`FakeReader` vacío) → `failed` `not_found`; el lote respeta `batch` (5 encoladas, 3 procesadas por vuelta); una solicitud `running` vieja se marca `abandoned` al inicio de la vuelta y **no** crea hipótesis; una excepción inesperada dentro de una solicitud la deja `failed` (`unexpected`) y la vuelta continúa con la siguiente; `SQLAlchemyError` → `status="error"` sin propagarse; dos vueltas seguidas no procesan dos veces la misma solicitud.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_subniche_proposals_worker.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar.** Cada solicitud se procesa fuera de la transacción de `claim_next` (esta se confirma antes de llamar a `asyncio.run(add_hypothesis(...))`, porque `add_hypothesis` abre sus propias transacciones); `finish_*` en una transacción nueva; en `main.py` llamar con `run_background_tick("subniche_proposals", tick_proposals, config, status, config.worker_poll_seconds)` y registrar la línea JSON igual que los demás.
- [ ] **Step 4:** pruebas del archivo y `tests/test_subniche_worker.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: el worker procesa las solicitudes de propuesta de subnicho`.

---

### Task 4: API de propuestas

**Files:**
- Modify: `src/nicheradar/subniche_api.py` (el router recibe `config`; nuevos endpoints), `src/nicheradar/api.py` (pasar `config=config` al crear el router, l.~897)
- Create: `tests/test_subniche_proposals_api.py`

**Interfaces:**
- Consumes: `proposals.*`, `subniche_router(*, authenticate, db, clock, config)`, el patrón de `flow_research_api.py` para errores y modelos.
- Produces:
  - `POST /api/v1/subniches/proposals` (202) con cabecera `Idempotency-Key` y cuerpo `{"input": str (3..500), "manual": {"label": str (3..120), "family": str (patrón ^[a-z][a-z0-9_]{1,39}$), "parent": str | null (máx. 60)} | null}` (`extra="forbid"`) → `{"id": "<uuid>", "status": "queued", "created": bool}`.
  - `GET /api/v1/subniches/proposals?limit=20` (1 a 100) → `{"items": [<solicitud>]}`.
  - `GET /api/v1/subniches/proposals/{id}` → `<solicitud>` o 404 `{"code": "not_found", "message": "Propuesta no encontrada."}`.
  - `<solicitud>` = `{"id", "status", "kind", "input", "created_at", "finished_at", "error": {"code","message"} | null, "hypothesis": {"slug","label","family","parent_niche","queries","seed_channels","status"} | null}`.
  - `MESSAGES: dict[str, str]` con los mensajes fijos en español de todos los códigos: `invalid_input` «No se reconoce esa entrada. Usa una consulta, un video, o un canal con @handle o enlace.», `tweet_not_supported_yet` «Los enlaces de X todavía no se leen.», `manual_needs_a_query` «La propuesta manual solo admite una consulta.», `daily_limit` «Se llegó al tope diario de propuestas.», `not_found` «No se encontró ese video o canal.», `duplicate` «Ya existe una hipótesis con esa consulta o con ese canal semilla.», `unknown_parent_niche` «Ese nicho padre no existe en el catálogo.», `invalid_proposal` «La propuesta no es válida.», `llm_disabled`/`synthetic_mode`/`configuration_missing`/`llm_tariff_not_current`/`policy_not_enabled`/`llm_failed`/`invalid_response`/`incomplete_response` «El modelo de lenguaje no está disponible: usa la propuesta manual.», `youtube_not_configured` «YouTube no está configurado en el servidor.», `abandoned` «La preparación se interrumpió; vuelve a intentarlo.», y un texto genérico «No se pudo preparar la propuesta.» para cualquier otro código; los códigos `duplicate:*` y los desconocidos se normalizan antes de buscar el mensaje y **el detalle nunca se devuelve**.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_subniche_proposals_api.py`, marca `postgres`; `client` y `AUTH` de `tests/test_market_api.py`): sin token o con token malo → 401 en los tres endpoints; `POST` sin `Idempotency-Key` o con una de 7 o 101 caracteres → 422; `POST` válido con consulta, video y canal → 202 con `created=true` y estado `queued`; la misma clave repetida → 202 con `created=false` y el mismo `id`; un tweet → 422 `tweet_not_supported_yet`; `"ab"` o una URL de YouTube no soportada → 422 `invalid_input`; `manual` con un canal → 422 `manual_needs_a_query`; cuerpo con campo extra → 422; el tope diario (configurar `subniche_proposals_per_day=1`) → 429 `daily_limit`; `GET` de la lista y del detalle con una solicitud `queued`, una `ready` (con `hypothesis`) y una `failed` (código `llm_disabled` → mensaje fijo; un código raro `duplicate:query:abc` → el mensaje de `duplicate` sin el detalle; un código desconocido → el genérico); la respuesta nunca contiene `idempotency_key`; `id` que no es UUID → 422/404 sin 500; texto hostil en `input` se devuelve como dato (comparar la cadena exacta); y que `POST` **no** llama a YouTube ni al modelo (el `client` de prueba no inyecta lector ni modelo: el tiempo de la prueba y la ausencia de llamadas lo demuestran con una bandera en un lector falso que falla si se usa).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_subniche_proposals_api.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** (`def` síncronos con `Depends(db)`; validar el `id` con `UUID` y devolver 404 si no existe; los errores de `ProposalRejected` se **devuelven** como `JSONResponse` (422 o 429) sin lanzar `HTTPException` cuando ya se escribió algo; antes de escribir se lanza `HTTPException` sin riesgo de perder datos porque no hay escritura previa).
- [ ] **Step 4:** pruebas del archivo y `tests/test_subniche_api.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: API para proponer subnichos y consultar su preparación`.

---

### Task 5: API del ciclo de vida y vista previa de la aprobación

**Files:**
- Modify: `src/nicheradar/subniche_api.py`
- Create: `tests/test_subniche_lifecycle_api.py`

**Interfaces:**
- Consumes: `store.approve(conn, slug, now)`, `store.set_status(conn, slug, status)`, `store.UnknownHypothesis`, `store.InvalidTransition`, `worker.search_units_needed(queries, config)`, `catalog.subniche_detail`.
- Produces:
  - `POST /api/v1/subniches/{slug}/approve`, `/pause`, `/resume`, `/archive` (200) → `{"slug", "status"}` con el estado nuevo; slug de 1 a 60 caracteres.
  - Errores: 404 `{"code": "not_found", "message": "Hipótesis no encontrada."}`; 409 `{"code": "invalid_transition", "message": "Esa hipótesis no puede pasar a ese estado."}` (sin el texto de la excepción).
  - `GET /api/v1/subniches/{slug}/approval` → `{"slug", "status", "queries": int, "pages": int, "search_units_needed": int, "daily_cap": int, "fits": bool, "cadence_days": 3}` donde `search_units_needed = len(queries) * config.subniche_search_pages * 100`, `daily_cap = min(config.subniche_search_units_per_day, config.subniche_search_quota_per_run)` y `fits = search_units_needed <= daily_cap`; 404 si no existe. Es solo lectura y sirve para la pantalla M28.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_subniche_lifecycle_api.py`, marca `postgres`; sembrar con `create_proposed/approve` y `draft` de `tests/subniche_samples.py`): sin token → 401; `approve` sobre `proposed` → 200 `active` y `approved_at` fijado; `approve` sobre una `active` → 409 `invalid_transition` y sin cambios; `pause` sobre `active` → `paused`; `resume` sobre `paused` → `active`; `pause` sobre `proposed` → 409; `archive` sobre `proposed`, `active` y `paused` → `archived` (y `finalist` en falso); cualquier transición desde `archived` → 409; slug inexistente → 404 en los cinco POST y en `approval`; slug de 61 caracteres → 422; `approval` con 2 consultas, 2 páginas y tope 100 → `search_units_needed=400`, `daily_cap=100`, `fits=false`; con 1 consulta, 1 página y tope 1000 → `fits=true`; el mensaje de error nunca contiene el texto de la excepción; los POST de ciclo de vida no llaman al worker ni a YouTube.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_subniche_lifecycle_api.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** (cada POST abre la transacción de `db`; al capturar `InvalidTransition` o `UnknownHypothesis` **devolver** la respuesta de error antes de cualquier escritura, ya que `store` valida antes de actualizar).
- [ ] **Step 4:** pruebas del archivo, `tests/test_subniche_store.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: API para aprobar, pausar, reanudar y archivar subnichos`.

---

### Task 6: Integración, documentación y validación completa

**Files:**
- Create: `tests/test_subniche_proposals_flow.py`
- Modify: `docs/subniche-discovery.md` (sección «API»), `docs/private-console.md` (endpoints nuevos), `docs/comandos.md` si lista los comandos de subnichos

- [ ] **Step 1:** Prueba de extremo a extremo (marca `postgres`): `POST /proposals` (manual) → `tick_proposals(...)` → `GET /proposals/{id}` `ready` con la hipótesis → `GET /{slug}/approval` → `POST /{slug}/approve` → la hipótesis `active` aparece en `GET /subniches`; y el mismo recorrido con una consulta y el modelo falso; una solicitud que falla (modelo desactivado) llega a `failed` con el mensaje fijo y sin hipótesis.
- [ ] **Step 2:** Documentar: los endpoints con ejemplos de `curl` (la clave de idempotencia, la forma de la respuesta, los códigos de error), que la preparación es asíncrona y la hace el worker (`NR_SUBNICHE_ENABLED=true`), el tope `subniche_proposals_per_day`, que `approve` no mide al instante y la regla de cuota (consultas × páginas × 100 contra el tope diario), y la nota de despliegue: la migración `0022` y la imagen del worker necesitan una release con aprobación del propietario.
- [ ] **Step 3: Validación completa:** `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin PATH="$PWD/.venv/bin:$PATH" uv run pytest -q` (en primer plano, unos 400 s) — todo en verde.
- [ ] **Step 4: Commit** `docs: API de propuestas de subnicho y prueba de extremo a extremo`.

---

## Fuera de este plan

La lectura de tweets e imágenes (`TweetReader`, extractor de canales, candidatos, tope de 50 tweets al día) y el «Compartir» de Android: planes propios que se apoyan en esta API. Las pantallas web de Proponer subnicho, aprobar y archivar (plan web propio, siguiente). Editar una propuesta (solo se descarta y se crea otra). Desplegar nada.

## Self-Review

- **Cobertura del spec 3d y de Compartir:** alta por consulta, video o canal con propuesta asíncrona (Tasks 2, 3 y 4), modo manual (Tasks 2 a 4), aprobar y descartar con confirmación de cuota (Task 5), idempotencia y tope diario (Tasks 2 y 4), la API sin llamadas a proveedores (Tasks 4 y 6), tweets fuera de alcance con su código (Tasks 2 y 4).
- **Marcadores de relleno:** ninguno; las firmas, los códigos de error y los mensajes están escritos; las pruebas listan cada caso con su resultado esperado.
- **Consistencia de tipos:** `proposals.enqueue/claim_next/release_stale/finish_ready/finish_failed/get_request/list_requests`, `ProposalRejected`, `tick_proposals`, `MESSAGES` y los endpoints se nombran igual en todas las tareas.
- **Review Focus:** 1 en Tasks 2 y 3; 2 en Task 3; 3 en Tasks 2 y 4; 4 y 5 en Task 5.
