# Web: Proponer subnicho y Compartir (Android) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el propietario pueda, desde la web móvil, proponer un subnicho (consulta, video o canal; modo manual), ver cómo se prepara, aprobarlo con la cuota a la vista y pausarlo, reanudarlo o archivarlo; y que pueda **compartir un enlace de YouTube desde Android** a la app y llegar a ese mismo flujo.

**Architecture:** Las pantallas nuevas son de la web (FastAPI + Jinja2 + HTMX) y solo hablan con la API privada que entrega `docs/superpowers/plans/2026-11-04-api-propuestas-de-subnicho.md` (cola de propuestas, ciclo de vida, vista previa de cuota). La web nunca llama a YouTube ni al modelo. La clave de idempotencia la deriva el servidor web de un nonce del formulario firmado con la sesión. «Compartir» es una ruta GET de solo lectura que clasifica el enlace con `parse_input` y ofrece «Proponer»; los tweets de X quedan con un aviso «todavía no se leen» hasta el plan de lectura de tweets.

**Tech Stack:** Python 3.13, FastAPI, Jinja2 (autoescape, nunca `|safe`), HTMX, httpx (`ApiClient`), pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-11-03-rediseno-movil-corte3-paridad-design.md` (3d, decisión 6) y `docs/superpowers/specs/2026-11-04-compartir-android-y-tweets-de-x-design.md` (flujo pasos 1–2, arquitectura «Manifiesto» y «Ruta /compartir», sesión de 5 días ya hecha). Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil»: M25 `49:4` (formulario), M26 `49:56` (en preparación), M27 `49:93` (lista), M28 `49:142` (confirmar aprobación), M29 `60:2` y M30 `60:21` (compartir y «Compartido contigo»). Quien implemente debe ver cada pantalla con `get_screenshot` (sesión `d677e68d-2cac-4935-9886-773dde5aaf10`) y copiar sus textos.

**Depende de:** el plan de API de propuestas ejecutado y fusionado (endpoints `POST/GET /subniches/proposals`, `POST /subniches/{slug}/approve|pause|resume|archive`, `GET /subniches/{slug}/approval`). Las pruebas de la web usan un transporte falso de httpx, así que se pueden escribir antes, pero el plan se ejecuta después.

## Global Constraints

- Plantillas con autoescape; nunca `|safe`. Todo texto que venga de la API, de YouTube, del modelo o del enlace compartido se muestra como texto.
- Los avisos usan claves fijas (`?aviso=clave` → texto del diccionario); nunca se refleja texto del usuario ni del servidor en un mensaje.
- Cada POST valida CSRF con `signer.csrf_valid(session, csrf)` y responde 403 «La solicitud no es válida.» si falla; los GET de pantalla usan `@shape_guard` y los POST capturan `SHAPE_ERRORS` a mano.
- Los errores de la API se muestran con `ApiError.message`; los códigos de error de la propuesta se traducen con el diccionario fijo de este plan (no con texto de la API).
- Listas con tope de 100 elementos y aviso; ids con `fullmatch` ASCII; fechas sin zona = UTC; números no finitos → «—».
- La web no importa nada de proveedores; solo puede importar funciones puras de `nicheradar.subniche_discovery.inputs`.
- El service worker sigue cacheando solo `/static`. `share_target` solo con `GET`; **sin** compartir imágenes en este plan.
- Nada se despliega; nada se aprueba solo (aprobar es un POST aparte con confirmación).

## Review Focus

1. Doble toque en «Proponer» (mismo nonce) y recargar la página tras el POST: una sola solicitud, nunca dos (Task 1 y 2).
2. Enlace compartido con `text` que trae el enlace en vez de `url`, con parámetros (`?si=…`), `youtu.be`, `m.youtube.com`, un canal con `@handle`, `twitter.com/x.com`, y basura (HTML, `javascript:`, 5000 caracteres): clasificado o rechazado sin 500 y sin reflejar el texto crudo sin escapar (Task 4).
3. Compartir sin sesión: login y regreso al mismo enlace, sin redirigir a otro dominio (Task 4).
4. Propuesta `failed` con códigos desconocidos o `duplicate:...`: mensaje fijo, nunca el detalle (Task 2).
5. Aprobar cuando las consultas no caben en la cuota: la pantalla M28 lo dice con cifras y deja aprobar; archivar pide confirmación y no se puede deshacer (Task 3).

---

### Task 1: Cliente con cabeceras y módulo `proposals` de la web

**Files:**
- Modify: `src/nicheradar/web/client.py` (parámetro `headers: dict[str, str] | None = None` en `ApiClient.request`, mezclado con `Authorization`, que no se puede sobrescribir; y `ApiError.code`/`ApiError.message`: los rechazos de dominio de la API de propuestas y del ciclo de vida llegan como `{"code","message"}` en la **raíz** del cuerpo (los 404 de lectura, como `{"detail":{"code","message"}}`); `_error_detail` debe reconocer ambas formas y `message` debe usar el texto fijo de la API solo si el `code` está en una lista cerrada de la web, nunca texto arbitrario)
- Create: `src/nicheradar/web/proposals.py`, `tests/test_web_proposals_module.py`
- Test: `tests/test_web_client.py` (caso nuevo para `headers`)

**Interfaces:**
- Consumes: `Signer`/`Session` de `web/security.py`; la forma de `<solicitud>` y el diccionario `MESSAGES` de la API.
- Produces:
  - `idempotency_key(signer, session, nonce: str) -> str` → `"nr-" + HMAC-SHA256(secreto de la firma, f"{session.csrf}:{nonce}").hexdigest()[:40]` (8 a 100 caracteres, determinista).
  - `new_nonce() -> str` (16 bytes hex, `secrets`).
  - `parse_form(raw_input: str, modo_manual: bool, label: str, family: str, parent: str) -> tuple[dict, str | None]` → `(body, error_key)`: recorta, exige 3..500 caracteres en `input`; si `modo_manual`, `manual={"label","family","parent"|None}` con `label` 3..120, `family` `^[a-z][a-z0-9_]{1,39}$`, `parent` ≤ 60; el error es una clave fija (`input_invalid`, `manual_invalid`).
  - `error_text(code: str | None) -> str` con el diccionario fijo (los mismos textos de `MESSAGES` de la API, incluidos `youtube_not_configured`, `youtube_quota_exhausted`, `youtube_unreachable`; `duplicate:*` y desconocidos se normalizan).
  - `proposal_view(item: dict, tz) -> dict` con `state` (`en_cola|preparando|lista|fallida`), `kind_label` (Consulta/Video/Canal), `input` (texto), `error` (texto fijo), `hypothesis` (slug, label, family, parent_niche, queries ≤ 20, seed_channels ≤ 20) y `finished_ago`.

- [ ] **Step 1: Pruebas que fallan:** `headers` llega a la API y no puede reemplazar `Authorization`; `idempotency_key` es estable para el mismo nonce y distinta para otro nonce u otra sesión; `parse_form` rechaza 2 y 501 caracteres, NUL y espacios; manual con `family` inválida; `error_text("duplicate:query:abc")` = texto de `duplicate`, desconocido = genérico; `proposal_view` con `status` raro o campos faltantes no lanza (cae en `fallida`/«—»), respeta el tope de 20 y trata texto hostil como dato.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_proposals_module.py tests/test_web_client.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** lo mínimo.
- [ ] **Step 4:** pruebas de los dos archivos, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: cabeceras en el cliente de la API y módulo de propuestas de la web`.

---

### Task 2: Proponer subnicho (M25, M26, M27)

**Files:**
- Create: `src/nicheradar/web/routes_proposals.py`, `src/nicheradar/web/templates/subnichos/proponer.html`, `.../propuesta.html`, `.../_propuesta.html` (fragmento con sondeo), `tests/test_web_proposals_routes.py`
- Modify: `src/nicheradar/web/app.py` (incluir el router), `src/nicheradar/web/templates/components.html` si hace falta un macro
- Test: `tests/test_web_security_matrix.py` (si existe: añadir las rutas nuevas a la matriz de sesión/CSRF)

**Interfaces:**
- Consumes: Task 1 completa; la API de propuestas.
- Produces:
  - `GET /subnichos/proponer` (M25): formulario con un campo, ayuda «consulta, video o canal», casilla «Propuesta manual» que muestra etiqueta, familia y nicho padre; `nonce` y `csrf` ocultos; acepta `?q=` para rellenar el campo (lo usa Compartir).
  - `POST /subnichos/proponer`: CSRF → `parse_form` → `POST /subniches/proposals` con `Idempotency-Key` → 303 a `/subnichos/propuestas/{id}`. Errores de la API (422/429) vuelven al formulario con el texto fijo y el campo conservado.
  - `GET /subnichos/propuestas/{id}` (M26/M27): `id` con `fullmatch` de UUID; si `en_cola/preparando` muestra el estado y un fragmento que se recarga solo cada 5 s con `hx-trigger="every 5s"` hasta que termine; `lista` (M27) muestra la hipótesis (etiqueta, familia, padre, consultas, canales semilla, línea «Origen: …» solo cuando exista origen en los datos) y el botón «Revisar y aprobar» → `/subnichos/{slug}/aprobar`; `fallida` muestra el texto fijo y «Volver a intentar» (vuelve al formulario con `?q=`).
  - Enlaces «+ Proponer» en la lista de subnichos (`lista.html`) y en «Más».

- [ ] **Step 1: Pruebas que fallan** (transporte falso de httpx; patrón de `tests/test_web_operation_routes.py`): GET del formulario sin sesión → redirección al login; con sesión → 200 con el nonce; POST sin CSRF → 403 y la API no recibe nada; POST válido → la API recibe el cuerpo exacto y una `Idempotency-Key` estable (dos POST con el mismo nonce → misma clave) y responde 303; 422 `invalid_input`/429 `daily_limit` → vuelve el formulario con el texto fijo; modo manual con consulta válida y con canal; detalle `en_cola` incluye `hx-trigger`, `lista` no; `fallida` con `duplicate:query:x` muestra el texto de duplicado y **no** `x`; id no UUID → 404; la API caída → 503 con aviso; texto hostil en `input` aparece escapado.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_proposals_routes.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** siguiendo `routes_operation.py` y `routes_subniches.py` (estilos, `render`, `shape_guard`, avisos por clave); revisar las tres pantallas contra Figma.
- [ ] **Step 4:** pruebas del archivo y del módulo, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: pantallas para proponer un subnicho y ver su preparación`.

---

### Task 3: Confirmar aprobación y ciclo de vida (M28)

**Files:**
- Modify: `src/nicheradar/web/routes_proposals.py` (o un `routes_lifecycle.py` si el archivo pasa de ~300 líneas), `src/nicheradar/web/templates/subnichos/ficha.html`
- Create: `src/nicheradar/web/templates/subnichos/aprobar.html`, `tests/test_web_lifecycle_routes.py`

**Interfaces:**
- Consumes: `GET /subniches/{slug}/approval`, `POST /subniches/{slug}/approve|pause|resume|archive`, `GET /subniches/{slug}`.
- Produces:
  - `GET /subnichos/{slug}/aprobar` (M28): muestra consultas, páginas, **unidades de búsqueda necesarias frente al tope diario** y, si `fits` es falso, un aviso «Con la cuota actual la medición se saltará hasta que haya cupo»; texto «aprobar no mide al instante: la primera medición ocurre a más tardar en 3 días»; botón «Aprobar» (POST) y «Volver». Si la hipótesis no está `proposed` → mensaje claro sin botón.
  - `POST /subnichos/{slug}/aprobar|pausar|reanudar|archivar` → llaman a la API y redirigen a la ficha con `?aviso=clave` (`aprobado`, `pausado`, `reanudado`, `archivado`, `transicion_invalida`). 404 → página de error; 409 → aviso `transicion_invalida`.
  - La ficha del subnicho muestra, según el estado, los botones válidos: `proposed` → «Revisar y aprobar»; `active` → «Pausar»; `paused` → «Reanudar»; cualquiera salvo `archived` → «Archivar» con una confirmación explícita (casilla «Entiendo que no se puede deshacer» que el POST exige).

- [ ] **Step 1: Pruebas que fallan:** M28 con `fits` verdadero y falso (cifras exactas en el HTML, aviso solo cuando no cabe); aprobar sobre `active` → aviso `transicion_invalida`; cada POST sin CSRF → 403 y sin llamada a la API; archivar sin la casilla → vuelve a la confirmación sin llamar a la API; slug inexistente → 404; slug de 61 caracteres → 404 sin 500; los botones de la ficha por estado; 409 con texto de la API no se refleja.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_lifecycle_routes.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4:** pruebas del archivo y `tests/test_web_subniches_routes.py` (o el que ya cubra la ficha), ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: confirmar la aprobación y gestionar el ciclo de vida del subnicho desde la web`.

---

### Task 4: Compartir desde Android (M29, M30)

**Files:**
- Modify: `src/nicheradar/web/static/manifest.webmanifest` (añadir `share_target`), `src/nicheradar/web/routes_auth.py` (regreso tras el login, solo rutas internas), `src/nicheradar/web/app.py`
- Create: `src/nicheradar/web/share.py`, `src/nicheradar/web/routes_share.py`, `src/nicheradar/web/templates/compartir.html`, `tests/test_web_share.py`

**Interfaces:**
- Consumes: `nicheradar.subniche_discovery.inputs.parse_input` (función pura), la ruta `/subnichos/proponer?q=` de la Task 2.
- Produces:
  - Manifiesto: `"share_target": {"action": "/compartir", "method": "GET", "params": {"title": "title", "text": "text", "url": "url"}}`.
  - `share.extract_link(title: str, text: str, url: str) -> str | None`: toma `url` si parece un enlace `http(s)`; si no, el primer enlace de `text`; luego de `title`; recorta a 500 caracteres; ignora esquemas que no sean http(s).
  - `share.classify(link: str | None) -> dict` → `{"kind": "channel|video|tweet|unknown|none", "link": str}`; `tweet` si el host es `x.com`, `twitter.com`, `mobile.twitter.com` o `www.` de ellos; el resto con `parse_input` (canal/video de YouTube). No llama a ningún servicio ni escribe.
  - `GET /compartir` (M29/M30 «Compartido contigo»): con sesión, muestra el tipo detectado y el enlace como texto; canal/video → botón «Proponer» que lleva a `/subnichos/proponer?q=<enlace codificado>`; tweet → texto «Los enlaces de X todavía no se leen. Copia el canal o el enlace de YouTube que menciona.» sin acción; desconocido/ninguno → «No reconocimos ese enlace.» Sin sesión → login con regreso a `/compartir?...` (el regreso solo acepta rutas que empiecen por `/` y no por `//`).
  - El service worker no cambia (se verifica con una prueba que su lista de rutas cacheadas sigue siendo solo `/static`).

- [ ] **Step 1: Pruebas que fallan:** `extract_link` con `url`, con enlace en `text`, con `title` solamente, con `javascript:alert(1)`, 5000 caracteres, vacío; `classify` para `youtu.be/…?si=x`, `m.youtube.com/watch?v=…`, `youtube.com/@canal`, `x.com/u/status/123?s=20`, `twitter.com`, `mobile.twitter.com`, `x.com/i/status/1`, un enlace cualquiera y texto sin enlace; `GET /compartir` sin sesión → login y regreso al mismo `/compartir?...`; el regreso rechaza `https://otro.com` y `//otro.com`; la página escapa HTML del enlace; no hay llamadas a la API; el manifiesto es JSON válido con `share_target` GET y sin `files`; el service worker sigue cacheando solo `/static`.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_share.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** (revisar contra Figma M29 y M30).
- [ ] **Step 4:** pruebas del archivo, `tests/test_web_auth.py` (o equivalente), ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: compartir enlaces de YouTube desde Android hacia Proponer subnicho`.

---

### Task 5: Integración, documentación y validación completa

**Files:**
- Create: `tests/test_web_proposals_flow.py`
- Modify: `docs/web-movil.md` (nuevas pantallas, Compartir en Android: cómo instalar la PWA y compartir), `docs/subniche-discovery.md` (enlace a la web)

- [ ] **Step 1:** prueba de extremo a extremo con transporte falso: compartir un enlace de canal → «Proponer» → formulario relleno → POST → estado en cola → listo → «Revisar y aprobar» → M28 → aprobar → ficha con aviso `aprobado` y botón «Pausar»; y el mismo recorrido con modo manual.
- [ ] **Step 2:** Documentar el flujo, los límites (enlaces de X aún no se leen; solo Android; sin imágenes) y qué necesita producción: API de propuestas desplegada, worker con `NR_SUBNICHE_ENABLED=true` y la PWA reinstalada en el teléfono para que Android registre el destino de «Compartir».
- [ ] **Step 3: Validación completa:** `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin PATH="$PWD/.venv/bin:$PATH" uv run pytest -q` (primer plano) — todo en verde. Capturas de las pantallas nuevas en 390 px frente a las de Figma.
- [ ] **Step 4: Commit** `docs: Proponer subnicho y Compartir en la web móvil`.

---

## Fuera de este plan

- **Lectura de tweets y de imágenes** (M31 a M34: `TweetReader` con FxTwitter, extractor de canales con visión, candidatos, tope de 50 tweets al día): plan aparte que extiende la API de propuestas con origen `lead`.
- Compartir imágenes (`share_target` POST con archivos y service worker).
- Quitar la Basic Auth del proxy y contraseña larga: acción del propietario en Easypanel.
- Despliegue de cualquier cosa a producción.
