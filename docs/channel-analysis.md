# Análisis competitivo de canal

Flujo bajo demanda, independiente del descubrimiento por catálogo de familias semilla:
el propietario pega la URL/handle/ID de un canal real de YouTube en la pestaña
"Análisis de canal" del dashboard (`render_channel_analysis` en `dashboard.py`) y el
radar investiga, con datos reales, si hay oportunidad de competir en ese nicho. El
resultado queda guardado de forma permanente (no es efímero) en `channel_analyses`;
volver a analizar el mismo canal crea un registro nuevo, nunca edita uno existente.

Se ejecuta con el mismo mecanismo de `analysis_runs`/`jobs` que el resto del radar
(arrendamiento, heartbeat, reintentos, checkpoints, reanudación tras fallo) — no es una
llamada HTTP síncrona. `analysis_runs.trigger` usa el valor `"channel_analysis"` y no
comparte stages ni estado con la secuencia existente de catálogo/refresh.

## Entrada soportada

`parse_channel_input` (`discovery/channel_analysis.py`) solo reconoce dos formas:

- `@handle` (cualquier texto que contenga `@algo`).
- Un ID de canal crudo `UC` + 22 caracteres, siempre que no venga como parte de una URL
  `/@handle`.

**`/c/NombrePersonalizado` y `/user/NombreLegado` no se reconocen.** Pegar una URL en
ese formato produce `ValueError("unsupported_channel_input")`, que la API traduce a un
422 claro (`"No se reconoce ese canal; usa su @handle o su ID (UC...)."`,
`POST /api/v1/channel-analyses` en `api.py`). Es un recorte de alcance explícito de esta
implementación, no un bug pendiente; el dashboard lo advierte en la misma pantalla del
formulario.

## Fuentes de datos (en paralelo, ninguna de respaldo de otra)

Cada etapa combina **YouTube Data API v3** y **vidIQ** a la vez quien pueda aportar dato;
si vidIQ falla por cupo agotado, el análisis continúa solo con YouTube. Explícitamente
**no se usan**:

- **Social Blade**: sin capa gratuita real confirmada.
- **El feed RSS de YouTube**: funciona, pero es un resto no documentado oficialmente de
  una API descontinuada en 2015 — zona gris de cumplimiento.
- **Google Trends**: sin API oficial pública; solo alpha cerrada por invitación, y la
  librería no oficial más usada está archivada.

Ninguna de las tres se activa aunque esté disponible técnicamente; una decisión de usar
alguna en el futuro es nueva, no automática.

## Flujo paso a paso (stages de la cola)

`CHANNEL_ANALYSIS_STAGES` (`workers/channel_analysis_queue.py`) define la secuencia que
despacha `Pipeline._process_channel_analysis_stage` (`workers/pipeline.py`):

1. **`resolve`**: `resolve_channel` llama a `channels.list` para identificar el canal
   objetivo. Si no se encuentra, `ProviderError("channel_not_found")` antes de gastar
   ningún crédito de vidIQ.
2. **`target_videos`**: `fetch_channel_videos` trae hasta 25 videos del canal objetivo
   (`playlistItems.list` + `videos.list`).
3. **`discover_comparables`**: `discover_comparables` hace **una sola llamada**
   `search.list` (`type=channel`) de YouTube más, si vidIQ está disponible,
   `channel_search`; deduplica por `channel.id`, excluye al canal objetivo de sus propios
   comparables, y recorta a `MAX_COMPARABLES = 8`.
4. **`comparable_videos`**: `fetch_channel_videos` se repite para cada comparable
   encontrado (con heartbeat entre cada uno).
5. **`metrics`**: `compute_comparison` calcula la velocidad de vistas/día del canal
   objetivo y del conjunto comparable (mediana de vistas/día por canal, excluyendo al
   objetivo del rango mejor/peor), y la posición del objetivo (`above`/`below`/`within`/
   `unknown`).
6. **`profit`**: reutiliza `scoring/profit.py::estimate_profit` (ya calculado dentro de
   `compute_comparison`); esta etapa existe solo para que la secuencia coincida 1:1 con
   el diseño original y deja espacio a una mejora futura (p. ej. adjuntar una receta o
   benchmark publicitario específico) sin tener que renumerar stages — hoy solo reenvía
   el checkpoint de `metrics`.
7. **`persist`**: `save_channel_analysis` guarda canal objetivo, comparables, métricas,
   posición y ganancia estimada en `channel_analyses.snapshot`, con `status`
   `completed`/`partial`.

`channel_view_rate` usa la misma mediana de vistas/día que `demand_by_age`, pero por
canal. `compute_comparison` nunca inventa un comparable: con cero comparables reales,
la posición queda `"unknown"` y la ganancia `"incomplete"` con `"channel_view_rate"` en
la lista de insumos faltantes.

## Presupuesto real (`services/channel_analysis_providers.py`, `config.py`)

| Operación | Costo por llamada | Tope por análisis | Tope semanal | Tope mensual |
|---|---|---|---|---|
| YouTube `search.list` (`youtube_search_quota`) | 100 unidades | 100 (`youtube_search_quota_per_run`, 1 llamada) | 100 (`youtube_search_quota_per_week`) | 300 (`youtube_search_quota_per_month`) |
| YouTube `channels.list`/`playlistItems.list`/`videos.list`/`commentThreads.list`/`videoCategories.list` (`youtube_detail_quota`) | 1 unidad | 100 (`youtube_detail_quota_per_run`) | 500 (`youtube_detail_quota_per_week`) | 2000 (`youtube_detail_quota_per_month`) |
| vidIQ `channel_search`/`channel_videos`/`outliers`/`keyword_research` (`vidiq_credit`) | 5 créditos planos | 50 (`CreatorProfile.channel_analysis_credits_per_run`) | `credits_per_week` del perfil (25 por defecto) | `credits_per_cycle` del perfil (100 por defecto) |

Valores por defecto verificados en `Settings`/`CreatorProfile`
(`test_new_budget_fields_have_conservative_defaults`). La cuota de `search.list` de
YouTube tiene su propio bucket separado (100/día real declarado por el propietario); el
diseño la acota a una sola llamada por análisis a propósito, dejando el resto de
llamadas (detalle de cada comparable) en el pool barato de 10.000/día.

El tope de **50 créditos vidIQ por análisis es un tope de ejecución propio de este
flujo**, más alto que el `credits_per_run` por defecto del resto del radar (5), pero
**comparte el mismo pool semanal/mensual de `vidiq_credit`** que ya usa el piloto
(`credits_per_week`/`credits_per_cycle` del mismo `CreatorProfile`) — pedir varios
análisis de canal seguidos puede agotar ese cupo compartido antes de llegar al tope de
50 créditos de un análisis individual.

## Manejo de errores y degradación

`VIDIQ_BUDGET_ERROR_CODES` (en `discover_comparables`) y `budget_error_codes` (en
`_process_channel_analysis_stage`) distinguen códigos de agotamiento de cupo/crédito
(`run_budget_exhausted`, `period_budget_exhausted`, `balance_exhausted`,
`balance_refresh_required`, `shared_budget_exhausted`, `batch_limit`) de errores reales
(`channel_not_found`, `contract_mismatch`, etc.):

- Si vidIQ agota su cupo durante `discover_comparables`, el `ProviderError` se atrapa
  ahí mismo y el análisis **continúa solo con YouTube** (sin aviso explícito distinto en
  el snapshot — ver limitación abajo).
- Si cualquier etapa YouTube o vidIQ agota su cupo con un código de la lista de arriba,
  esa etapa confirma `{"reason": error.code}` en vez de propagar el error; el `reason`
  se arrastra checkpoint a checkpoint hasta `persist`, que guarda `status="partial"` y
  cierra el job como `"partial"` (nunca `"failed"`, nunca truncado en silencio). Un
  código que no está en la lista (p. ej. `channel_not_found`) sí propaga al manejador
  genérico de `fail_job()`.
- Cero comparables reales encontrados nunca se rellena con un comparable inventado;
  `compute_comparison` deja la posición `"unknown"` y la ganancia `"incomplete"`.

### Limitación conocida: una etapa interrumpida descarta su progreso parcial

**Un fallo de cupo/crédito a mitad de una etapa descarta todo el progreso parcial hecho
dentro de esa etapa** (por ejemplo, si `comparable_videos` ya trajo los videos de 3 de 8
comparables cuando el cupo YouTube se agota en el cuarto, esos 3 resultados nunca se
guardan: la excepción se atrapa en el `except ProviderError` externo de
`_process_channel_analysis_stage`, que confirma `{"reason": error.code}` para toda la
etapa, descartando el diccionario `videos_by_channel` acumulado localmente). El job
igual termina limpio como `"partial"` con la razón visible, y **todas las etapas
anteriores ya completadas sí se conservan** en el snapshot final guardado — pero no se
calcula ninguna métrica de mejor esfuerzo a partir de una etapa interrumpida a medias.
Es un recorte de alcance deliberado documentado en la bitácora de implementación, no un
bug; una mejora futura podría guardar checkpoints incrementales dentro de la etapa para
habilitar esto. `test_second_analysis_same_week_hits_search_quota_cleanly`
(`tests/test_channel_analysis_pipeline.py`) ejercita este camino a nivel de
`discover_comparables`.

### Limitación conocida: vidIQ nunca aporta dato real en modo live hoy

`channel_analysis_vidiq_tariffs()` **no declara ninguna tarifa para `Operation.BALANCE`**
(a diferencia de `pilot.vidiq_tariffs()`, que sí incluye `BALANCE` con `maximum=0`,
es decir, gratis). `Gateway.fetch` exige una tarifa `BALANCE` explícitamente gratis para
poder refrescar el saldo real antes de una llamada externa en modo live
(`services/gateway.py`); sin ella, **toda llamada vidIQ de este flujo en modo live
levanta `balance_refresh_required`** inmediatamente. Como ese código está en
`VIDIQ_BUDGET_ERROR_CODES`, `discover_comparables` lo atrapa en silencio y sigue "solo
con YouTube" — el resultado práctico es que **este flujo hoy siempre degrada a
YouTube-only en modo live**, sin ningún aviso visible que distinga "vidIQ se quedó sin
cupo real" de "vidIQ nunca fue alcanzable por este hueco de tarifa". Es un seguimiento
conocido, todavía sin corregir.

### Limitación conocida: falta el pre-check de cupo real antes de encolar

El diseño original pedía verificar el **saldo real de vidIQ con margen suficiente para
el tope de 50 créditos antes de encolar** el análisis (`POST /api/v1/channel-analyses`),
distinto del tope de ejecución `channel_analysis_credits_per_run` que ya se aplica
durante el procesamiento. **Esa verificación previa nunca se implementó**: el endpoint
solo corre `require_live_ready` (comprobación general de que el radar está listo en modo
live), no una comprobación de saldo vidIQ específica para este tope. Es un hueco conocido
— se recomienda no depender del camino vidIQ en vivo de esta función en producción sin
resolverlo primero.

## API privada

- `POST /api/v1/channel-analyses` — body `{"channel_input": str}`, requiere header
  `Idempotency-Key`. Valida el formato de entrada (422 si no se reconoce), exige
  `require_live_ready` si el radar está en modo live, y encola el job devolviendo
  `job_id`/`status_url` (mismo patrón que `POST /runs`).
- `GET /api/v1/channel-analyses` — lista paginada de análisis guardados.
- `GET /api/v1/channel-analyses/{id}` — detalle completo (snapshot + estado), 404 si no
  existe.

## UI (dashboard)

Pestaña "Análisis de canal" (`render_channel_analysis`, separada del Home): formulario
de texto para URL/handle/ID con el costo máximo real declarado antes de confirmar
("hasta 50 créditos vidIQ y 1 búsqueda —100 unidades— de cuota de YouTube"), tabla de
análisis previos (canal, estado, fecha) y detalle del seleccionado mostrando el
`snapshot` completo vía `render_structured`.

## Pruebas

- `tests/test_channel_analysis_discovery.py` — `parse_channel_input`, resolución sin
  gastar cupo ajeno, `channel_view_rate`, deduplicación/exclusión de comparables,
  degradación por cupo vidIQ agotado, posición y ganancia con comparables reales y con
  cero comparables.
- `tests/test_channel_analysis_pipeline.py` — secuencia completa de stages en modo
  sintético y el camino de cupo YouTube `search.list` agotado a mitad de un segundo
  análisis en la misma semana, dejando el job `"partial"` sin truncar en silencio.
- `tests/test_channel_analysis_queue.py` — avance y finalización de
  `CHANNEL_ANALYSIS_STAGES`, confirmación parcial.
- `tests/test_channel_analysis_budget.py` — valores por defecto conservadores, tope de
  ejecución propio distinto del `credits_per_run` general, tarifas cubren todas las
  operaciones usadas.
- `tests/test_channel_analysis_contracts.py` — nuevas `Operation`s y que el proveedor
  sintético las soporta.
- `tests/test_channel_analysis_youtube.py` — mapeo de respuestas YouTube reales
  (`search`, `commentThreads`, `videoCategories`, `channels`) a los contratos internos.
- `tests/test_channel_analysis_service.py` — guardar/listar/detallar un análisis.
- `tests/test_channel_analysis_api.py` — encolado autenticado y rechazo 422 de entrada
  no soportada.
