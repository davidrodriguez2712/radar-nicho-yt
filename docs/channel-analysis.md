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
- **`featuredChannelsUrls`** (señal de YouTube sobre "canales destacados") y **scraping de
  HTML** de páginas de YouTube como fuente de "canales similares": ambas evaluadas en vivo
  contra canales reales y descartadas explícitamente para descubrimiento de comparables —
  ver "Consulta de descubrimiento" más abajo para el detalle de por qué.

Ninguna se activa aunque esté disponible técnicamente; una decisión de usar alguna en el
futuro es nueva, no automática.

## Flujo paso a paso (stages de la cola)

`CHANNEL_ANALYSIS_STAGES` (`workers/channel_analysis_queue.py`) define la secuencia que
despacha `Pipeline._process_channel_analysis_stage` (`workers/pipeline.py`):

1. **`resolve`**: `resolve_channel` llama a `channels.list` para identificar el canal
   objetivo. Si no se encuentra, `ProviderError("channel_not_found")` antes de gastar
   ningún crédito de vidIQ.
2. **`target_videos`**: `fetch_channel_videos` trae hasta 25 videos del canal objetivo
   (`playlistItems.list` + `videos.list`).
3. **`discover_comparables`**: `discover_comparables` hace **una sola llamada**
   `search.list` (`type=channel`, `maxResults=50`) de YouTube más, si vidIQ está
   disponible, `channel_search`; deduplica por `channel.id`, excluye al canal objetivo de
   sus propios comparables, y recorta a `MAX_COMPARABLES = 8`. La consulta (`q`) la deriva
   `_discovery_query` del propio canal objetivo, nunca de una categoría o subtema
   (confirmado que YouTube nunca los rellena): usa la primera palabra clave declarada en
   `Channel.keywords` (ver "Consulta de descubrimiento" más abajo) si existe; si no, un
   hashtag de su `description`; si tampoco hay, su título como último recurso.
4. **`comparable_videos`**: `fetch_channel_videos` se repite para cada comparable
   encontrado (con heartbeat entre cada uno).
5. **`metrics`**: `compute_comparison` calcula la velocidad de vistas/día del canal
   objetivo y del conjunto comparable (mediana de vistas/día por canal, excluyendo al
   objetivo del rango mejor/peor), la posición del objetivo (`above`/`below`/`within`/
   `unknown`), la ganancia estimada (`scoring/profit.py::estimate_profit`, ver
   "Ganancia estimada" más abajo) y el panorama del nicho (`compute_panorama`, ver
   "Panorama del nicho" más abajo) a partir de los videos comparables.
6. **`profit`**: la ganancia ya se calculó dentro de `compute_comparison` en la etapa
   `metrics`; esta etapa existe solo para que la secuencia coincida 1:1 con el diseño
   original y deja espacio a una mejora futura sin tener que renumerar stages — hoy solo
   reenvía el checkpoint de `metrics`.
7. **`persist`**: `save_channel_analysis` guarda canal objetivo, comparables, métricas,
   posición y ganancia estimada en `channel_analyses.snapshot`, con `status`
   `completed`/`partial`. `consumption` refleja el gasto real de la ejecución con el
   mismo criterio que la vista de jobs: `confirmed` (libro de costos, por unidad:
   `youtube_search_quota`, `youtube_quota`, `vidiq_credit`) y `reservations`
   todavía abiertas (`reserved`/`unknown_charge`); las liberadas no cuentan.
   `configuration` guarda los parámetros reales (`channel_input`, `mode`,
   `max_comparables`, `maximum_calls`).

Retención: `integrations/retention.py::expire()` borra `snapshot` (la metadata retenida
de YouTube/vidIQ) y marca `expired_at` cuando vence `retain_until`; `configuration` y
`consumption` se conservan como rastro de auditoría. El listado y el detalle siguen
mostrando el análisis con `evidence_available=false`.

Políticas de uso: `scripts/activate_live.py` habilita, vía
`integrations/policies.py::seed_youtube_policies`, una fila explícita por operación de
YouTube (`videos`, `channels`, `uploads`, `search`, `comment_threads`,
`video_categories`) — sin comodín `*`.

`channel_view_rate` usa la misma mediana de vistas/día que `demand_by_age`, pero por
canal. `compute_comparison` nunca inventa un comparable: con cero comparables reales,
la posición queda `"unknown"` y la ganancia `"incomplete"` con `"channel_view_rate"` en
la lista de insumos faltantes.

## Consulta de descubrimiento (`_discovery_query`, `discovery/channel_analysis.py`)

`discover_comparables` ya no busca por el título del canal objetivo (señal débil: el
título rara vez describe el nicho). `_discovery_query` construye la consulta real de
`search.list`/`channel_search` con esta prioridad, verificada en
`test_discover_comparables_queries_by_keyword_not_title` y
`test_discover_comparables_falls_back_to_description_hashtag_then_title`:

1. La primera palabra clave de `Channel.keywords` (viene de
   `brandingSettings.channel.keywords`, ver abajo), si el canal objetivo declaró alguna.
2. Si no hay `keywords`, el primer hashtag encontrado en `Channel.description`.
3. Si tampoco hay hashtag, el título del canal como último recurso.

Antes de esto, el diseño original planeaba usar categoría/subtemas del canal como
consulta; se confirmó que YouTube nunca los rellena en la práctica, así que esa ruta
nunca se implementó.

**Señales evaluadas y descartadas explícitamente (no reabrir sin evidencia nueva):**

- **`featuredChannelsUrls`**: evaluado en vivo contra 2 canales reales. Devuelve los
  propios canales secundarios del creador y amistades personales, no competidores — una
  señal de "a quién conoce", no "con quién compite". Descartado.
- **Scraping de HTML de páginas de YouTube** para encontrar "canales similares":
  investigado en vivo (se llegó a descargar páginas reales de YouTube) y descartado
  explícitamente — duplicaría la misma señal ya descartada de `featuredChannelsUrls`, con
  riesgo adicional de incumplimiento de los Términos de Servicio y fragilidad ante
  cambios de maquetación, sin aportar información nueva.

`search.list` ahora pide `maxResults=50` (antes no se especificaba, por lo que la API
usaba su valor por defecto más bajo); el costo sigue siendo el mismo plano de 100
unidades por llamada sin importar `maxResults`, así que esto es estrictamente más
cobertura por el mismo costo, no un gasto adicional.

## Panorama del nicho (`compute_panorama`, `discovery/channel_analysis.py`)

La etapa `metrics` también calcula un panorama real del nicho a partir de **los videos de
los comparables, excluyendo al canal objetivo** (reutiliza
`features/metrics.py::calculate()`, el mismo motor que ya usa el catálogo de familias
semilla). Devuelve uno de dos estados:

- `{"status": "incomplete", "reason": "no_comparable_videos"}`: ningún comparable aportó
  videos (p. ej. cero comparables encontrados, o todos sin videos recuperables).
- `{"status": "incomplete", "reason": "mixed_formats_not_evaluable"}`: los videos
  comparables mezclan formatos (`long` y `shorts` a la vez) — `calculate()` no evalúa una
  cohorte mixta como una sola población, y el panorama no fuerza una elección arbitraria.
- `{"status": "computed", "metrics": {...}}`: el `CohortMetrics` completo
  (`videos`, `channels`, `demand_by_age`, `hhi`/`concentration_score`, `breakout_rate`,
  etc.), igual que en el catálogo. El dashboard muestra videos analizados, canales
  comparables, tasa de breakout y concentración (HHI) en la pestaña de detalle.

**Clasificación de breakout por tamaño real de canal.** `compute_panorama` recibe los
`Channel` reales de cada comparable (ya resueltos en la etapa `discover_comparables`,
incluyendo `.subscribers`) y clasifica el `size_stratum` de cada `Membership` como
`"small"` o `"large"` comparando los suscriptores reales del comparable contra
`CreatorProfile.small_channel_subscribers` (por defecto 50.000) — el mismo umbral que ya
usa el flujo de catálogo (`discovery/sampling.py::sample()`). Cuando el comparable no
tiene suscriptores resueltos (`Channel.subscribers is None`), el estrato queda
`"unknown"` y ese miembro simplemente no participa en la clasificación de breakout — una
degradación honesta, no un dato inventado. La clasificación se indexa por el canal
comparable bajo el que se obtuvieron los videos (la propia clave de
`comparable_videos`), no por `video.channel_id`: para `SyntheticProvider`, el video
devuelto por `fetch_channel_videos` declara siempre el mismo `channel_id` sin importar
qué comparable se pidió, así que usar `video.channel_id` directamente clasificaría mal
casi todos los videos.

## Ganancia estimada (`scoring/profit.py::estimate_profit`)

La ganancia mensual estimada (dentro de `compute_comparison`, etapa `metrics`) usa el
mismo motor que el resto del radar: un rango acotado por el canal comparable mejor y peor
posicionado ya observado, nunca una proyección de un canal nuevo. Para resolver a
`"estimated"` necesita los cuatro insumos a la vez; si falta alguno, `status` queda
`"incomplete"` con la razón exacta en `missing` (`channel_view_rate`,
`videos_per_month`, `advertising_rate`, `production_cost`) — nunca se rellena con un
valor inventado:

1. **`channel_view_rate`**: viene de `compute_comparison` (mejor/peor vistas/día entre
   comparables reales).
2. **`videos_per_month`**: `DEFAULT_VIDEOS_PER_MONTH` (`services/production.py`), fijo
   para este flujo.
3. **`production_cost`**: el pipeline simula la **misma receta de producción por defecto**
   que ya se documenta para el catálogo (`services/production.py::default_recipe`/
   `default_template`, según el formato mayoritario de los videos del canal objetivo y el
   idioma del perfil), vía `services/scenarios.py::simulate`, para obtener un
   `monthly_cost_usd` real — no una suposición de costo cero.
4. **`advertising_rate`**: requiere que el propietario haya declarado un
   `CreatorProfile.channel_analysis_advertising` (ver "Benchmark publicitario" abajo). Si
   es `None`, o si el valor guardado no valida como `AdvertisingBenchmark` (dato
   corrupto/incompleto), la ganancia degrada a `"incomplete"` — nunca interrumpe el
   análisis completo.

**Benchmark publicitario (`CreatorProfile.channel_analysis_advertising`, Configuración):**
campo opcional (`dict[str, Any] | None`, guardado crudo y revalidado como
`AdvertisingBenchmark` en el momento de usarlo) que el propietario declara una sola vez,
no por análisis, desde la pestaña Configuración del dashboard (formulario "Benchmark
publicitario para análisis de canal", `dashboard.py`). El formulario permite declarar
versión/fecha, fuente, RPM mínimo/máximo (USD por 1000 vistas), audiencia y supuestos; un
checkbox sin marcar al guardar limpia el benchmark de vuelta a `None`. El formulario fija
`format="long"` y `unit="usd_ads_per_1000_views"` siempre — el pipeline no cruza este
`format` contra el formato real detectado del canal analizado, así que un benchmark
declarado para contenido largo se aplica igual si el canal analizado resulta ser
mayoritariamente Shorts.

## Presupuesto real (`services/channel_analysis_providers.py`, `config.py`)

| Operación | Costo por llamada | Tope por análisis | Tope semanal | Tope mensual |
|---|---|---|---|---|
| YouTube `search.list` (`youtube_search_quota`) | 100 unidades | 100 (`youtube_search_quota_per_run`, 1 llamada) | 700 (`youtube_search_quota_per_week`) | 3000 (`youtube_search_quota_per_month`) |
| YouTube `channels.list`/`playlistItems.list`/`videos.list`/`commentThreads.list`/`videoCategories.list` (`youtube_quota`) | 1 unidad | 100 (`youtube_detail_quota_per_run`) | 500 (`youtube_detail_quota_per_week`) | 2000 (`youtube_detail_quota_per_month`) |
| vidIQ `channel_search`/`channel_videos`/`outliers`/`keyword_research` (`vidiq_credit`) | 5 créditos planos | 50 (`CreatorProfile.channel_analysis_credits_per_run`) | `credits_per_week` del perfil (25 por defecto) | `credits_per_cycle` del perfil (100 por defecto) |

> **Nota:** Google anunció una migración a un sistema de cuotas más granular para
> `search.list` a partir de junio de 2026, que podría ya estar vigente en tu cuenta.
> Antes de depender de estos números en producción, vuelve a verificar en
> [Google Cloud Console → YouTube Data API v3 → Cuotas](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas).

Valores por defecto verificados en `Settings`/`CreatorProfile`
(`test_new_budget_fields_have_conservative_defaults`). La cuota de `search.list` de
YouTube tiene su propio bucket separado (100/día real declarado por el propietario); el
diseño la acota a una sola llamada por análisis a propósito, dejando el resto de
llamadas (detalle de cada comparable) en el pool barato de 10.000/día.

**`youtube_quota` es la misma unidad que usa el catálogo.** Las operaciones de detalle
(`channels`/`uploads`/`videos`/`commentThreads`/`videoCategories`) reservan bajo el
mismo nombre de unidad `"youtube_quota"` que ya usa el flujo de catálogo
(`services/youtube_enrichment.py::youtube_tariffs()`), porque ambos flujos consumen
realmente el mismo cupo externo compartido de 10.000/día de Google — no dos pools
internos separados para un solo recurso externo. Los topes run/week/month de este flujo
(`youtube_detail_quota_per_run/week/month` en `Settings`, nombre histórico conservado
por claridad de intención) siguen siendo propios de channel-analysis, pero el consumo
contra ellos se contabiliza junto con el del catálogo, porque `services/budget.py`
agrega por `(profile_id, unit)`, no por flujo.

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
`balance_refresh_required`, `shared_budget_exhausted`, `batch_limit`, y en ambos
conjuntos también `quota`: el código con el que `YouTubeProvider` traduce el 403
`quotaExceeded`/`dailyLimitExceeded` o el 429 de Google, y con el que vidIQ traduce su
429) de errores reales
(`channel_not_found`, `contract_mismatch`, etc.):

- Si vidIQ agota su cupo durante `discover_comparables`, el `ProviderError` se atrapa
  ahí mismo y el análisis **continúa solo con YouTube**, dejando
  `"vidiq_omitted": "budget_exhausted"` en el checkpoint `discover_comparables` (y por
  tanto en el snapshot); `null` si vidIQ corrió o no formaba parte de la ejecución.
- Si cualquier etapa YouTube o vidIQ agota su cupo con un código de la lista de arriba,
  esa etapa confirma `{"reason": error.code}` en vez de propagar el error; el `reason`
  se arrastra checkpoint a checkpoint hasta `persist`, que guarda `status="partial"` y
  cierra el job como `"partial"` (nunca `"failed"`, nunca truncado en silencio). Un
  código que no está en la lista (p. ej. `channel_not_found`) sí propaga al manejador
  genérico de `fail_job()`, pero antes se guarda una fila `status="failed"` con
  `snapshot.failure = {stage, error_code}` para que el fallo aparezca en el listado. Si
  `fail_job()` reencola el job y un reintento termina bien, `persist` reemplaza esa fila
  (una fila por `run_id`).
- Cero comparables reales encontrados nunca se rellena con un comparable inventado;
  `compute_comparison` deja la posición `"unknown"` y la ganancia `"incomplete"`.

### Corregido: en modo live, el costo real de YouTube liquidaba siempre como `unknown_charge`

`Gateway.fetch` solo marca una reserva como `"confirmed"` cuando las unidades de costo que
devuelve el proveedor (`batch.costs`) coinciden exactamente con las unidades de la tarifa
reservada (`services/gateway.py`, comparación `set(actual) == {cost.unit for cost in
costs}`). Antes de la corrección, las tarifas de este flujo
(`channel_analysis_youtube_tariffs()`) declaraban `"youtube_search_quota"` para
`search.list` y `"youtube_detail_quota"` para el resto, pero `YouTubeProvider.normalize()`
(`integrations/youtube.py`) siempre etiquetaba su costo real como la unidad genérica
`"youtube_quota"` en ambas ramas, sin distinguir búsqueda de detalle. Esas unidades nunca
coincidían, así que en modo live toda llamada YouTube de este flujo liquidaba como
`"unknown_charge"` en vez de `"confirmed"`, sin importar que el cargo real sí se conocía
(el proveedor sí reportaba un `actual` correcto, solo que bajo el nombre de unidad
equivocado). El modo sintético nunca sufrió esto porque `Gateway.fetch` sustituye la
tarifa por una unidad `"USD"` fija cuando `synthetic=True`, evitando la comparación.

**Corrección aplicada:** `_normalize_search` (`integrations/youtube.py`) ahora reporta
`"youtube_search_quota"` (search.list es, en los hechos, un cupo real separado de
100/día); las otras tres ramas de costo (CHANNELS/UPLOADS/VIDEOS genérica,
`_normalize_comment_threads`, `_normalize_video_categories`) siguen reportando
`"youtube_quota"`, sin cambios. `channel_analysis_youtube_tariffs()` ahora reserva
`"youtube_quota"` para las operaciones de detalle (en vez de `"youtube_detail_quota"`),
que es exactamente lo que el proveedor ya reportaba — y la misma unidad que usa
`services/youtube_enrichment.py::youtube_tariffs()` para el catálogo, así que ambos
flujos ahora comparten el mismo seguimiento contra el cupo real externo de Google (ver
"Presupuesto real" arriba). Cubierto end-to-end por
`test_youtube_detail_and_search_calls_settle_confirmed_not_unknown_charge`
(`tests/test_channel_analysis_budget.py`), que recorre el `Gateway.fetch()` real.

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
`VIDIQ_BUDGET_ERROR_CODES`, `discover_comparables` lo atrapa y sigue "solo con
YouTube" — el resultado práctico es que **este flujo hoy siempre degrada a
YouTube-only en modo live**. El snapshot sí muestra `vidiq_omitted: "budget_exhausted"`,
pero ese marcador no distingue "vidIQ se quedó sin cupo real" de "vidIQ nunca fue
alcanzable por este hueco de tarifa". Es un seguimiento conocido, todavía sin corregir.

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
análisis previos (canal, estado, fecha) y detalle del seleccionado. Antes del `snapshot`
completo (vía `render_structured`), si `snapshot.metrics.panorama` existe se muestra un
subtítulo "Panorama del nicho" con videos analizados, canales comparables, tasa de
breakout (`"—"` si `breakout_rate is None` — p. ej. cuando ningún comparable resolvió un
estrato `"small"`, como se documenta arriba) y concentración (HHI); o un aviso con la
razón exacta si el panorama quedó `"incomplete"`.

La pestaña Configuración (`dashboard.py`) agrega un formulario "Benchmark publicitario
para análisis de canal" (ver "Ganancia estimada" arriba) debajo de los límites de
presupuesto existentes, antes de la receta de producción por defecto.

## Pruebas

- `tests/test_channel_analysis_discovery.py` — `parse_channel_input`, resolución sin
  gastar cupo ajeno, `channel_view_rate`, deduplicación/exclusión de comparables,
  degradación por cupo vidIQ agotado, posición y ganancia con comparables reales y con
  cero comparables, `_discovery_query` por `keywords`/hashtag/título
  (`test_discover_comparables_queries_by_keyword_not_title`,
  `test_discover_comparables_falls_back_to_description_hashtag_then_title`), y
  `compute_panorama` computado/incompleto por cero comparables o formatos mixtos
  (`test_compute_panorama_computes_real_metrics_across_comparables`,
  `test_compute_panorama_incomplete_when_no_comparable_videos`,
  `test_compute_panorama_skips_mixed_formats_without_crashing`).
- `tests/test_channel_analysis_pipeline.py` — secuencia completa de stages en modo
  sintético (incluyendo panorama y ganancia con un benchmark publicitario sembrado en el
  perfil) y el camino de cupo YouTube `search.list` agotado a mitad de un segundo
  análisis en la misma semana, dejando el job `"partial"` sin truncar en silencio.
- `tests/test_channel_analysis_advertising_benchmark.py` — `CreatorProfile` acepta,
  omite por defecto y rechaza (si está malformado) `channel_analysis_advertising` — a
  nivel de dominio, no del formulario de Configuración (ver abajo).
- `tests/test_channel_analysis_queue.py` — avance y finalización de
  `CHANNEL_ANALYSIS_STAGES`, confirmación parcial.
- `tests/test_channel_analysis_budget.py` — valores por defecto conservadores, tope de
  ejecución propio distinto del `credits_per_run` general, tarifas cubren todas las
  operaciones usadas.
- `tests/test_channel_analysis_contracts.py` — nuevas `Operation`s y que el proveedor
  sintético las soporta.
- `tests/test_channel_analysis_youtube.py` — mapeo de respuestas YouTube reales
  (`search`, `commentThreads`, `videoCategories`, `channels`) a los contratos internos,
  incluyendo `keywords` desde `brandingSettings` (presente, ausente o malformado).
- `tests/test_channel_analysis_service.py` — guardar/listar/detallar un análisis.
- `tests/test_channel_analysis_api.py` — encolado autenticado y rechazo 422 de entrada
  no soportada.

**Hueco de cobertura aceptado conscientemente:** no existe un test a nivel de dashboard
(`AppTest`) que ejercite el formulario "Benchmark publicitario para análisis de canal" en
sí — ni su envío ni su camino de limpiar el checkbox para volver a `None` —, solo el
modelo de dominio subyacente (arriba). Se aceptó como hueco menor porque replicaría el
patrón de prueba de envío de formularios ya existente en el archivo de pruebas del
dashboard sin aportar cobertura nueva significativa.
