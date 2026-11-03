# Rediseño móvil, corte 2b-1: contrato `channel-report-v3`, minutos humanos y calibración (M13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que NicheRadar pueda recibir, guardar y mostrar **minutos humanos por video** con el método declarado (`channel-report-v3`), y que la web muestre la calibración de un piloto (M13: racha de videos bajo el criterio de salida del informe, horas acumuladas) y los pilotos en calibración en «Hoy» (M14).

**Architecture:** Cambio aditivo en tres capas. (1) Contrato: modelos nuevos `channel-report-v3` (largos y shorts, selector `format`) sin tocar v1 ni v2. (2) Datos: migración `0021` con dos columnas nullable en `pilot_videos`, ingestión en `submit_report`, totales `human_minutes` en la evaluación y los videos en `GET /pilots/{id}/videos`. (3) Web: la calibración se **calcula al leer** a partir del `calibration` del dossier y los `human_minutes` por video (sin congelar nada en el paquete); la pantalla rotula siempre el método de cada cifra.

**Qué NO incluye (decisión pendiente del propietario):** el productor de los minutos humanos (`scripts/channel_human_minutes.py`) y su método de medición. El hallazgo del 2026-11-03 (spec, sección 5) mostró que medir esperas en compuertas subestima por un orden de magnitud; el método queda reabierto. Todo lo de este plan funciona con `human_minutes = null` («sin medir») y con cualquier método futuro, porque el contrato declara `human_minutes_method`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy Core + Alembic, Pydantic v2, Postgres de pruebas (`NR_TEST_POSTGRES_BIN`), Jinja2 + HTMX, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-11-02-rediseno-movil-corte2-design.md` (secciones 4, 5 con el hallazgo, 6). Plan previo: `docs/superpowers/plans/2026-11-03-rediseno-movil-corte2a-pilotos.md`. Diseño: Figma `JmBvlfNURrV226WOZLuCEz`: M13 `35:2`, M14 `36:2`.

## Código que ya existe y se reutiliza (verificado el 2026-11-03)

- `src/nicheradar/pilots/contracts.py`: `Contract` (`extra="forbid"`, `frozen`, `allow_inf_nan=False`), `VideoBase` (l.~302, campos obligatorios sin defaults, `machine_minutes: Annotated[int, Field(ge=0)] | None`), `Video`, `ShortsVideo`, `ReportBase`, `Report` (v1), `ReportV2`, `AnyReport = Report | ReportV2`, `REPORT_FORMAT = {contract: format}` y `report_format(report)`, `report_problems(report, now)`, `validate_report(payload, now) -> (AnyReport | None, problems)` (elige el modelo por `payload["contract"]`; hoy cualquier valor distinto de `channel-report-v2` cae en v1).
- `src/nicheradar/pilots/service.py`: `_VIDEO_FIELDS`, `_video_values(video, channel_id, reported_at)`, `submit_report`, `_videos_for_rules`, `list_videos`, `closing_summary` (usa `totals["machine_minutes"]`); `rules.py` `_totals(videos, max_videos)`.
- `src/nicheradar/repositories/schema.py` (`pilot_videos`, columna `machine_minutes`); migraciones `migrations/versions/00NN_slug.py` (última `0020`, `down_revision="0019"`); ejemplo de `op.add_column` en `0016_flow_research_language.py`.
- **Fijaciones de la revisión `0020`** que una `0021` obliga a actualizar: `scripts/backup_snapshot.py:174`, `scripts/backup_mac.py:253`, `tests/test_backup_mac.py` (l.51, 131, 317, 380) y `tests/test_channel_report_v2_schema.py` (l.86-90, prueba `..._pins_revision_0020`).
- Pruebas: `tests/pilot_samples.py` (`report`, `video`, `package`, `iso`), `tests/shorts_report_samples.py` (`shorts_report`, `shorts_video`), `tests/test_pilot_contracts.py` (sin DB), `tests/test_pilots_api.py` y `tests/test_channel_report_v2_api.py` (helpers `send`, `launched`, `shorts_pilot`, `issue_token`, `deliver`), `tests/test_pilots_videos_api.py` (`ITEM_KEYS` con el conjunto exacto de claves), `tests/test_channel_report_v2_schema.py` (patrón de migración aditiva y reversible).
- Web: `src/nicheradar/web/pilot_panel.py`, `routes_pilot_panel.py`, `pilots_view.py`, `today.py`, `report.py` (calibración del dossier y `calibration_total_hours` de `flow_research.contracts`), plantillas `pilotos/*`, `hoy.html`; `tests/web_helpers.py` (`pilot_detail`, `pilot_video`, `dossier_v3`).
- Documentación de contratos: `docs/contracts/channel-report-v2.md` (plantilla «qué cambia respecto a…»).

## Global Constraints

- **Aditivo y compatible:** v1 y v2 siguen aceptándose sin cambios; un piloto antiguo no cambia; la migración es reversible y solo añade columnas nullable. No se toca `pilot-package-v1` ni `dossier-v3`.
- **`human_minutes` nulo significa «no se pudo medir»**, nunca 0 por defecto (en el contrato, la base, los totales y la web). Un total de minutos humanos con algún video sin medir se rotula «incompleto» (mismo patrón que `machine_minutes_complete`).
- **El método siempre se declara:** `human_minutes_method` (patrón `^[a-z0-9_]{1,60}$`) es obligatorio en el reporte v3, y la web lo muestra («estimado» o el nombre humano del método) junto a las cifras. Una cifra sin método no se acepta.
- **La calibración es una sugerencia de la web, no un estado del piloto:** no hay evaluación en el servidor ni reglas de parada nuevas en este plan.
- Todo lo de los planes anteriores sigue vigente (cookie firmada, CSRF, CSP, escape de todo texto de la API, ids con `fullmatch` ASCII `^pil_[0-9]{8}_[a-z0-9-]{1,40}$`, `shape_guard`, `with_radar=False` tras fallo, avisos de tope de 100, números no finitos → «—», fechas sin zona = UTC, nada de `|safe`).
- Cambios de base de datos: solo la migración `0021` (se aplica en producción en una release con aprobación del propietario). Nada se despliega con este plan.

## Rulings de diseño

1. **v3 cubre largos y shorts con un campo `format`** (`"long"|"shorts"`) en el reporte; `REPORT_FORMAT` pasa a resolverse por `(contract, format)` para v3 y se mantiene por `contract` para v1/v2. Costo si es incorrecto: separar en `channel-report-v3` y `-v3-shorts`.
2. **`human_minutes_method` vive a nivel de reporte** y se copia a cada video guardado (columna por video, para que un reporte posterior con otro método no reescriba la historia de los anteriores). Costo: una columna de texto repetida.
3. **Un video reportado en v3 sin `human_minutes`** (clave ausente) se rechaza (422), igual que el resto de campos obligatorios del contrato; `null` explícito es válido.
4. **La calibración usa solo videos publicados** del piloto, en orden de `published_at`, y compara `human_minutes <= exit_criterion.max_minutes_per_video`... **verificar en `docs/contracts/dossier-v3.md` si el criterio es «menor que» o «menor o igual»** y seguir el texto del contrato; el informe lo expresa con `statement`.
5. **«Hoy» (M14)** muestra pilotos en calibración con racha y último valor solo si hay dossier v3 con `calibration`; si no, el piloto aparece como antes.

## Review Focus

1. Reporte v3 con `human_minutes` negativo, enorme, `NaN`/`inf` (vía JSON crudo), booleano, cadena, ausente o nulo; `human_minutes_method` ausente, vacío, con mayúsculas o de 61 caracteres; `format` ausente o inconsistente con el piloto: 422 con problemas claros y nada guardado (Tasks 1 y 3).
2. v1 y v2 siguen aceptándose y los pilotos antiguos conservan sus datos tras la migración y su reversión (Task 2).
3. Un reporte posterior con `reported_at` más viejo no pisa minutos ya guardados; uno más nuevo sí; empate conserva lo guardado (Task 3).
4. Calibración con videos sin medir, empates en el umbral, menos videos que `consecutive_videos`, dossier v1/v2 sin `calibration`, `calibration` malformada y piloto sin dossier legible: ninguna pantalla da 500 y el texto dice qué falta (Task 5).
5. El total `human_minutes_complete` no engaña: con un video sin medir dice «incompleto» (Tasks 3 y 5).
6. Texto hostil en `human_minutes_method`, `calibration.step` y el criterio: escapado (Task 5).

---

### Task 1: Contrato `channel-report-v3`

**Files:**
- Modify: `src/nicheradar/pilots/contracts.py`, `tests/test_pilot_contracts.py`, `tests/pilot_samples.py` (ayudantes `video_v3`, `report_v3`), `tests/shorts_report_samples.py` (`shorts_video_v3`, `shorts_report_v3`)

**Interfaces:**
- Consumes: `VideoBase`, `Video`, `ShortsVideo`, `ReportBase`, `report_problems`, `validate_report`, `REPORT_FORMAT`, `report_format`.
- Produces: `VideoV3(Video)` y `ShortsVideoV3(ShortsVideo)` con `human_minutes: Annotated[int, Field(ge=0)] | None`; `ReportV3(ReportBase)` con `contract: Literal["channel-report-v3"]`, `format: Literal["long","shorts"]`, `human_minutes_method: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,60}$")]`, `videos: list[VideoV3] | list[ShortsVideoV3]` (la forma se decide por `format`; ver abajo); `AnyReport = Report | ReportV2 | ReportV3`; `report_format(report)` devuelve `report.format` para v3; `validate_report` selecciona v3 cuando `contract == "channel-report-v3"`; `REPORT_CONTRACT_V3 = "channel-report-v3"`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_pilot_contracts.py`, sin DB). Escribir completas, con aserciones sobre `paths(problems)` exactos:
  - un reporte v3 largo válido con `human_minutes` entero y con `None` se acepta, y su `report_format` es `"long"`; uno de shorts con `format="shorts"` y videos de shorts se acepta y su formato es `"shorts"`;
  - rechazos con la ruta del campo en el problema: `human_minutes` negativo, `-1`, `1.5`, `True`, `"10"`, `NaN`/`Infinity` (JSON crudo parseado con `json.loads`), ausente; `human_minutes_method` ausente, `""`, `"Gate Waits"`, `"x"*61`; `format` ausente, `"other"`; clave extra en el reporte o en el video; videos de shorts dentro de un reporte `format="long"` (y viceversa);
  - v1 y v2 siguen aceptando exactamente lo que aceptaban (reutilizar las pruebas existentes) y **rechazan** `human_minutes` y `human_minutes_method` como claves extra (`extra="forbid"`);
  - `validate_report` con `contract` desconocido sigue cayendo en v1 y produce el problema `contract` esperado (no cambiar ese comportamiento).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_pilot_contracts.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** en `contracts.py` siguiendo el patrón de `Report`/`ReportV2`; para la forma de `videos` según `format`, usar dos clases internas (`_ReportV3Long`, `_ReportV3Shorts`) con un `model_validator`/unión discriminada por `format`, de modo que `validate_report` devuelva siempre un `ReportV3` con los videos del tipo correcto. Mantener `report_problems` (coherencia de estados, mediciones) aplicable a v3 reutilizando `_shorts_problems` y la anotación `Sequence[Video | ShortsVideo]`.
- [ ] **Step 4:** `uv run pytest tests/test_pilot_contracts.py -q; uv run ruff format src tests -q; uv run ruff check . && uv run mypy` — PASS.
- [ ] **Step 5: Commit** `feat: contrato channel-report-v3 con minutos humanos por video y método declarado`.

---

### Task 2: Migración `0021`, esquema y fijaciones de respaldo

**Files:**
- Create: `migrations/versions/0021_pilot_human_minutes.py`
- Modify: `src/nicheradar/repositories/schema.py`, `scripts/backup_snapshot.py:174`, `scripts/backup_mac.py:253`, `tests/test_backup_mac.py`, `tests/test_channel_report_v2_schema.py`, `tests/test_pilots_schema.py`
- Create: `tests/test_pilot_human_minutes_schema.py`

**Interfaces:**
- Produces: columnas `pilot_videos.human_minutes` (`Integer`, nullable, `CHECK human_minutes IS NULL OR human_minutes >= 0`, nombre global único `pilot_videos_human_minutes_nonneg`) y `pilot_videos.human_minutes_method` (`String(60)`, nullable); revisión `0021` con `down_revision="0020"`; los respaldos y sus pruebas fijan `"0021"`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_pilot_human_minutes_schema.py`, marca `postgres`, patrón de `test_the_migration_is_additive_and_reversible`): subir a `0020`, insertar un piloto y un video con `machine_minutes`, subir a `head` y comprobar que lo previo se conserva y las columnas nuevas son `NULL`; la restricción rechaza `-1` y acepta `0` y `NULL`; bajar a `0020` elimina ambas columnas sin perder el resto; el esquema de `schema.py` coincide con la base migrada (patrón de `test_pilots_schema.py`). Actualizar las seis fijaciones de `"0020"` a `"0021"` y el nombre de la prueba `..._pins_revision_0020` → `..._pins_revision_0021`, **sin debilitarlas**.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `NR_TEST_POSTGRES_BIN=… uv run pytest tests/test_pilot_human_minutes_schema.py tests/test_backup_mac.py tests/test_channel_report_v2_schema.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** la migración con `op.add_column` y `op.create_check_constraint` (downgrade con `op.drop_constraint` y `op.drop_column`), las columnas en `schema.py`, y las fijaciones de respaldo.
- [ ] **Step 4:** pruebas anteriores + `tests/test_pilots_schema.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: migración 0021 con minutos humanos por video`.

---

### Task 3: Ingestión, totales y API

**Files:**
- Modify: `src/nicheradar/pilots/service.py` (`_VIDEO_FIELDS`, `_video_values`, `submit_report`, `_videos_for_rules`, `list_videos`, `closing_summary`), `src/nicheradar/pilots/rules.py` (`_totals`), `src/nicheradar/pilots_dashboard.py` (solo si lee totales y debe mostrarlos; no romper Streamlit), `docs/pilots.md`
- Modify: `tests/test_pilots_videos_api.py` (`ITEM_KEYS`), `tests/test_pilot_rules.py`, `tests/test_pilot_shorts_rules.py`
- Create: `tests/test_channel_report_v3_api.py`

**Interfaces:**
- Consumes: `ReportV3`, columnas de la Task 2, helpers de `tests/test_channel_report_v2_api.py` (`shorts_pilot`, `stored`) y `tests/test_pilots_api.py` (`launched`, `send`, `issue_token`, `deliver`).
- Produces: `_video_values(video, channel_id, reported_at, method=None)`; `_totals` añade `human_minutes` (suma de los no nulos) y `human_minutes_complete` (`len(medidos) == len(videos)`, igual patrón que `machine_minutes_complete`); `list_videos` añade `human_minutes` y `human_minutes_method` a cada item; el resumen de cierre añade la línea de minutos humanos con «(incompleto…)» si faltan.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_channel_report_v3_api.py`, marca `postgres`, completas):
  - un reporte v3 largo y uno de shorts se aceptan (200) y quedan guardados con `human_minutes` y `human_minutes_method` por video; `GET /pilots/{id}/videos` los devuelve; `GET /pilots/{id}` trae `totals.human_minutes` y `totals.human_minutes_complete`;
  - con un video sin medir (`None`), `human_minutes_complete` es falso y la suma ignora el nulo; sin videos, el patrón coincide con `machine_minutes_complete`;
  - un reporte v3 cuyo `format` no coincide con el del piloto → 422 `report_format_mismatch` (mismo código que v1/v2); un v3 inválido → 422 con problemas y **nada guardado** (contar filas);
  - orden/idempotencia: `reported_at` más viejo no pisa los minutos guardados, más nuevo sí, empate conserva lo guardado; un reporte v1 posterior sobre el mismo video **no borra** `human_minutes` ya guardados (decisión: v1/v2 no tocan esas columnas; test explícito);
  - un v1 y un v2 siguen funcionando exactamente igual y sus videos quedan con `human_minutes = NULL` y método `NULL`;
  - `ITEM_KEYS` incluye las dos claves nuevas; el resumen de cierre muestra la línea nueva y el «(incompleto)» cuando corresponde;
  - autorización: un token de canal ajeno sigue recibiendo 404; `human_minutes` no aparece en `GET /pilots` (lista) salvo dentro de `totals`.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `NR_TEST_POSTGRES_BIN=… uv run pytest tests/test_channel_report_v3_api.py tests/test_pilots_videos_api.py -q 2>&1 | tail -8`.
- [ ] **Step 3: Implementar** siguiendo los patrones de `machine_minutes` en cada función; `submit_report` pasa `method = getattr(report, "human_minutes_method", None)` y solo escribe las dos columnas cuando el reporte es v3 (v1/v2 no las tocan, ni en el insert —quedan `NULL`— ni en el update).
- [ ] **Step 4:** `uv run pytest tests/test_channel_report_v3_api.py tests/test_pilots_api.py tests/test_channel_report_v2_api.py tests/test_pilots_videos_api.py tests/test_pilot_rules.py tests/test_pilot_shorts_rules.py tests/test_pilots_dashboard.py -q`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: ingestión de channel-report-v3, totales y API de minutos humanos`.

---

### Task 4: Documentación del contrato

**Files:**
- Create: `docs/contracts/channel-report-v3.md`
- Modify: `docs/pilots.md`, `docs/contracts/channel-report-v2.md` (enlace «ver también v3»), `scripts/channel_sync.py` (solo el docstring: menciona v1/v2)

- [ ] **Step 1:** Escribir `channel-report-v3.md` con la estructura de `channel-report-v2.md` («Qué cambia respecto a v1/v2» en tabla): aditivo sobre v1/v2, `format`, `human_minutes` (entero ≥ 0 o `null` = no medido, nunca 0), `human_minutes_method` (patrón y significado de los métodos conocidos, con la advertencia del hallazgo: un método que solo mide esperas en compuertas subestima), reglas de coherencia, idempotencia (v1/v2 no tocan los minutos guardados), ejemplo JSON largo y shorts, «Quién lo genera» (el método y el productor están pendientes de decisión del propietario; el contrato es neutral), «Qué NO cubre» (no evalúa reglas de parada con minutos humanos). Actualizar `docs/pilots.md` (tabla de contratos y de totales).
- [ ] **Step 2:** `uv run ruff check . && uv run mypy` (el docstring de `channel_sync.py`) y revisión de enlaces (`grep -rn "channel-report-v3" docs` sin enlaces rotos).
- [ ] **Step 3: Commit** `docs: contrato channel-report-v3`.

---

### Task 5: Calibración en el panel (M13) y en «Hoy» (M14)

**Files:**
- Create: `src/nicheradar/web/calibration.py`, `src/nicheradar/web/templates/pilotos/_calibracion.html`
- Modify: `src/nicheradar/web/pilot_panel.py` (pestaña `calibracion`), `routes_pilot_panel.py` (pedir el dossier del piloto y los videos para esa pestaña), `pilots_view.py`/`today.py` y `templates/hoy.html` (tarjeta de pilotos en calibración), `static/css/app.css`, `tests/web_helpers.py` (`pilot_video` con `human_minutes`)
- Create: `tests/test_web_calibration.py`; Modify: `tests/test_web_pilot_panel.py`, `tests/test_web_today.py`

**Interfaces:**
- Consumes: `GET /pilots/{id}` (`package.dossier.request_id`), `GET /flow-research/{request_id}` (dossier v3 con `calibration`), `GET /pilots/{id}/videos` (con `human_minutes`, `human_minutes_method`), `pilots_view` helpers, `report.py` (extracción de `calibration`; reutilizar, no duplicar).
- Produces: `calibration.py`: `Calibration` (dataclass congelado: `videos_planned`, `setup_hours`, `max_minutes`, `consecutive`, `statement`, `steps: list[tuple[str,int]]`), `parse_calibration(dossier: object) -> Calibration | None` (tolerante: `None` si el dossier no es v3, no trae `calibration` o está malformada; nunca lanza), `streak(minutes: list[int | None], max_minutes: int, ...) -> int` (racha **final** de videos consecutivos que cumplen el criterio; un `None` corta la racha y se marca «sin medir»), `view(calibration, videos, now, tz) -> dict` con filas «Video N: M min / pendiente / sin medir», `streak_text` («Racha bajo {max} minutos: {k} de {consecutive}»), «Horas de calibración hasta hoy» (`setup_hours` + suma de `human_minutes` medidos / 60) contra las previstas (`calibration_total_hours`), «Régimen que buscamos» (suma de `production_flow` del dossier, minutos), «Último video», `passes: bool` («pasa a régimen» cuando la racha ≥ `consecutive`), `method_text` (método declarado en los videos: «estimado (método {nombre})»; si hay más de uno, «métodos mezclados»), `incomplete: bool`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_calibration.py` y ampliaciones; escribir completas con aserciones exactas):
  - unitarias de `parse_calibration`/`streak`/`view`: racha con `[92,71,58]` y máximo 60 → 1; con `[58,59,55]` → 3 y `passes`; un `None` en medio corta y marca «sin medir»; empate exactamente en el umbral según el criterio del contrato (ruling 4); menos videos que `consecutive`; ceros; negativos y `NaN` (ignorar y marcar); dossier v1/v2 sin `calibration` → `None`; `calibration` con tipos erróneos → `None`; 0 videos; más videos que los planificados; horas acumuladas;
  - panel: con dossier v3 con `calibration` aparece la pestaña «Calibración» (y solo entonces), con las filas, la racha, las horas, el régimen buscado y la etiqueta del método; sin `human_minutes` medidos dice «Aún sin minutos medidos» (no «0 min»); si el dossier no se puede leer, la pestaña muestra «No se pudo leer el informe de calibración» y el resto del panel sigue; la propuesta «pasa a régimen» es texto, sin botón nuevo; texto hostil en método/step/statement escapado;
  - «Hoy»: tarjeta «N pilotos en calibración» con racha y último video solo para pilotos activos con calibración legible; sin ellos la tarjeta no aparece; una fuente caída degrada solo esa tarjeta; enlaces solo con ids válidos (`fullmatch` ASCII);
  - peticiones: el dossier y los videos se piden **solo** para la pestaña de calibración (y para «Hoy» solo el dossier+videos de pilotos activos con calibración: máximo 5 pilotos, con aviso «y N más» si hay más, para acotar llamadas).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_calibration.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar.** Textos del Figma M13: «Calibración: tu tiempo por video», «Pasas a régimen cuando {statement}», filas «Video 1 … 92 min / pendiente», «Racha bajo 60 minutos: 1 de 3», «Tu tiempo», «Horas de calibración hasta hoy: 4,4 h de 21,5 previstas», «Preparación del canal (hecha)» (solo si el dato existe: `setup_hours`), «Régimen que buscamos: 20 min por video», «Último video», bloque «Bloqueos y avisos» con el aviso «Los primeros videos pasaron de 60 minutos / Es normal en calibración» solo si hay datos que lo sostengan. No inventar «Ver qué tomó más tiempo» (no hay desglose por paso en los reportes).
- [ ] **Step 4:** `uv run pytest tests/test_web_calibration.py tests/test_web_pilot_panel.py tests/test_web_today.py tests/test_web_assets.py -q`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: pantalla M13, calibración del piloto con racha y horas, y pilotos en calibración en Hoy`.

---

### Task 6: Integración, capturas y documentación

**Files:**
- Modify: `tests/test_web_smoke_screens.py`, `scripts/web_preview.py`, `scripts/web_preview_data.py` (datos con `human_minutes`), `docs/web-movil.md`, `docs/pilots.md`

- [ ] **Step 1:** Extender la prueba de humo con la pestaña de calibración y la tarjeta de Hoy: datos hostiles recursivos, API caída, formas mal hechas (`human_minutes` como cadena/lista/`NaN` crudo, `calibration` de otro tipo), CSP y sin recursos externos. Cada fallo es un defecto real: corregirlo con su prueba (RED primero); no debilitar.
- [ ] **Step 2:** Capturas `calibracion.png` y la tarjeta de Hoy en `hoy.png`; mirar cada PNG y listar defectos visibles; corregir los obvios (clases sin regla en `app.css`; todas las clases nuevas deben tener regla, hay una prueba que lo exige).
- [ ] **Step 3:** Documentar en `docs/web-movil.md`: la pestaña de calibración, de dónde sale cada cifra, el rótulo del método y que sin productor de minutos humanos la pantalla dice «Aún sin minutos medidos».
- [ ] **Step 4: Validación completa:** `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=… PATH="$PWD/.venv/bin:$PATH" uv run pytest -q` (en primer plano, unos 300 s) — todo en verde.
- [ ] **Step 5: Commit** `docs: capturas y prueba de humo de la calibración`.

---

## Fuera de este plan

El productor de minutos humanos (`scripts/channel_human_minutes.py`) y la elección de su método (decisión pendiente del propietario, spec sección 5); reglas de parada o hitos evaluados por el servidor con minutos humanos; el desglose por paso en los reportes; despliegue y migración en producción (release con aprobación).

## Self-Review

- **Cobertura del spec (2b, secciones 4 y 6):** contrato v3 (Task 1), migración (Task 2), ingestión y totales (Task 3), documentación del contrato (Task 4), calibración calculada al leer y M13/M14 (Task 5), humo y capturas (Task 6). La sección 5 (método y productor) queda explícitamente fuera por el hallazgo.
- **Rulings:** (1) `format` dentro de v3; (2) método a nivel de reporte copiado por video; (3) clave ausente rechazada, `null` válido; (4) umbral según el texto del contrato (hay que verificarlo); (5) «Hoy» solo con dossier v3 legible. Cada uno anota su costo.
- **Consistencia:** `ReportV3`/`VideoV3`/`ShortsVideoV3` (Task 1) los usan las Tasks 2 y 3; `human_minutes`/`human_minutes_method` (columnas Task 2) los leen `list_videos` y la web (Tasks 3 y 5); `calibration.py` (Task 5) reutiliza `report.py` y `flow_research.contracts`.
- **Riesgos:** una `0021` toca seis fijaciones de respaldo (listadas); `REPORT_FORMAT` pasa a depender de `format` en v3; sin productor, la pantalla mostrará «sin medir» en producción hasta que se decida el método; `GET /pilots/{id}` hace una llamada extra al dossier para la pestaña (acotada a la pestaña y a 5 pilotos en Hoy).
- **Sin placeholders:** las Tasks 1 a 3 traen pruebas y reglas exactas; las Tasks 5 y 6 traen pruebas por escenario y reglas del modelo de vista que el implementador escribe completas siguiendo los patrones ya probados.
