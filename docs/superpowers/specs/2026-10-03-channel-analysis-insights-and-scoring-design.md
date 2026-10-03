# Score de oportunidad y vista ejecutiva de análisis de canal — diseño

Estado: validado en conversación con el propietario el 2026-10-03. Pendiente de revisión
del archivo antes de pasar a `writing-plans`.

## Resumen

La pestaña "Análisis de canal" del dashboard hoy vuelca el `checkpoints` interno completo
del pipeline (`render_structured(snapshot)`) — útil para depurar, inservible para decidir
rápido si un nicho vale la pena. Este diseño reemplaza esa vista por una vista ejecutiva
(insights resumidos por canal, filtro por canal, borrado), agrega un **Score de
oportunidad** (0-100, "qué tan explotable está el nicho") que permite comparar de un
vistazo todos los canales ya investigados, y resuelve dos huecos reales encontrados
durante pruebas en producción: (1) el benchmark publicitario era un único valor global
declarado a mano, ahora pasa a ser una tabla de 218 nichos reales con asignación
automática vía LLM; (2) `batch_size=20` hacía que casi todo análisis real terminara
`"partial"` sin panorama ni ganancia.

## Objetivo de negocio

Responder, de un vistazo y comparando entre todos los canales ya investigados: ¿cuál de
estos nichos conviene más explorar primero? El Score mide **oportunidad del nicho**, no
qué tan fuerte es el canal puntual que se investigó — un competidor fuerte dentro de un
nicho es evidencia de que el nicho funciona, no necesariamente una señal negativa.

## Fuera de alcance (explícito)

- Edición de los 218 nichos desde el dashboard — se cargan una sola vez desde
  `youtube_niches_rpm_longform_2026.json` vía migración/seed; agregar o editar nichos
  después de este trabajo es un seguimiento documentado, no parte de esta entrega.
- Reconsultas automáticas/periódicas de canales ya investigados — el Nivel 3 (crecimiento
  real) se nutre solo de que el propietario reinvestigue un canal manualmente, nunca de un
  job programado nuevo.
- Historial completo de videos para **todos** los comparables de cada análisis — demasiado
  caro (ver "Acción manual: historial completo"); solo disponible como acción explícita
  por canal.
- Certificación de monetización o garantía de resultados — se mantiene la regla ya
  vigente de `scoring/profit.py`: solo se muestra rango observado, nunca una promesa.

## Hallazgos de esta investigación (contexto, no decisiones nuevas)

Confirmados con datos reales de producción durante esta sesión:

1. `views_subscriber_ratios` siempre sale vacío en channel-analysis: `fetch_channel_videos`
   nunca copia `subscriber_count` desde el `Channel` comparable (ya está en memoria) a cada
   `Video` antes de llamar a `calculate()`. Costo de arreglo: cero, no hay llamada nueva.
2. `channels.list` ya pide `part=snippet,contentDetails,statistics,brandingSettings` en
   cada llamada real — `snippet.publishedAt` (antigüedad) y `statistics.videoCount` vienen
   gratis en la respuesta y hoy se descartan al no estar en el contrato `Channel`.
3. `playlistItems.list` (verificado en vivo contra la API real y en la documentación
   oficial): 1 unidad de cuota por llamada, hasta 50 items, **sin parámetro de orden ni
   filtro de fecha** — los items siempre llegan del más reciente al más antiguo, sin forma
   de saltar al final. Confirmado con un canal real (184 videos, 5 meses de antigüedad):
   traer su historial completo cuesta 8 unidades de cuota (4 `playlistItems.list` + 4
   `videos.list`); extrapolado a 8-20 comparables con historiales más largos, entre ~80 y
   ~800 unidades extra por análisis — si se hiciera automáticamente para todos.
4. `batch_size=20` (tope compartido de llamadas a proveedores por ejecución,
   `src/nicheradar/config.py`) es insuficiente: un análisis real necesita ~21-25 llamadas
   solo para completar las 7 etapas con 8 comparables. Ya se corrigió en producción
   (`NR_BATCH_SIZE=100`, commit `61a2903`) como fix puntual previo a este diseño.

## Modelo de datos

### Tabla nueva: `advertising_benchmarks`

Reemplaza por completo `CreatorProfile.channel_analysis_advertising` (campo único) y el
formulario correspondiente en Configuración (`dashboard.py:885-948`) — se eliminan ambos,
no quedan como alternativa de respaldo.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `niche_label` | text, único | ej. `"true_crime_stories"` |
| `niche_description` | text | lo que lee el LLM para clasificar |
| `format` | text (`"long"`/`"shorts"`) | |
| `rate_low` / `rate_high` | numeric | USD por 1000 vistas |
| `source` | text | |
| `assumptions` | text | |
| `created_at` | timestamptz | |

Seed único vía migración, leyendo `docs/youtube-niches-rpm-longform-2026.json` (218 filas,
ya validado: esquema consistente, sin duplicados, `rate_low <= rate_high` en todas).

Al hacer *match* (ver pipeline), se construye un `AdvertisingBenchmark`
(`scoring/advertising.py`, contrato ya existente, sin cambios) a partir de la fila
encontrada: `audience_key=niche_label`, `origin="manual_assumption"`,
`revenue_scope="youtube_ads_only_after_revenue_share"`, `usage="enabled"`,
`monetization="unknown"`, `version=niche_label + fecha de carga`, `observed_at`/
`valid_until` calculados al vuelo (180 días de validez, igual que el campo que reemplaza).
`estimate_profit()` no cambia — sigue recibiendo el mismo contrato.

### `Channel` (contrato, `integrations/contracts.py`)

Dos campos nuevos, ambos `| None` (pueden faltar si la API los omite):

- `published_at: AwareDatetime | None` — de `snippet.publishedAt`.
- `video_count: int | None` — de `statistics.videoCount`.

Normalización en `integrations/youtube.py`: dos líneas de extracción adicionales donde ya
se parsea `statistics`/`snippet` para `CHANNELS`. Sin cambios de `part`, sin costo nuevo.

### `channel_analyses`

Sin columnas nuevas. El Score y los componentes Nivel 1-3 se calculan al vuelo desde el
`snapshot` ya guardado, tanto en `GET /channel-analyses` (para la tabla comparativa) como
en el detalle — así se puede ajustar la fórmula más adelante sin reprocesar análisis
viejos.

## Pipeline (`workers/pipeline.py`)

### Fix: `views_subscriber_ratios`

En la etapa `comparable_videos` (o antes de construir `comparable_videos` para la etapa
`metrics`), copiar `subscriber_count=comparable_channel.subscribers` a cada `Video` antes
de pasar el dict a `compute_panorama()`/`calculate()`. El `Channel` comparable con
`.subscribers` ya está en memoria (`checkpoints["discover_comparables"]["comparables"]`);
no se agrega ninguna llamada a proveedor.

### Etapa nueva: `advertising_match`

Entre `discover_comparables` y `metrics`. Entrada: `keywords`/`description` reales del
canal investigado (`checkpoints["resolve"]["channel"]`) + la lista completa de
`niche_label`+`niche_description` de `advertising_benchmarks`. Una sola llamada real al
LLM ya habilitado en producción (mismo proveedor que "explanation"), pidiendo el
`niche_label` que mejor calza o `"ninguno"` si no hay un calce razonable. Se ejecuta una
vez por análisis, nunca por vista del dashboard. Resultado guardado en el checkpoint:
`{"matched_niche": "<niche_label>" | None, "model": "<modelo usado>"}`.

Si no hay match (o el formato del nicho no coincide con el formato detectado del canal,
misma regla ya existente para el benchmark único), el profit sigue "incompleto" con razón
`"advertising_rate"` — igual que hoy, solo que ahora la razón de que falte puede ser
"LLM no encontró nicho aplicable" en vez de "nadie configuró un benchmark".

### Nivel 3: crecimiento real entre reinvestigaciones

En la etapa `persist`, antes de guardar la fila nueva: buscar en `channel_analyses` la fila
**más antigua** con el mismo `channel_external_id` y `status` distinto de `"failed"`. Si
existe:

```
dias = (ahora - fila_antigua.created_at).days
crecimiento_subs_dia = (target.subscribers_ahora - fila_antigua.snapshot["resolve"]["channel"]["subscribers"]) / dias
```

Guardado en el checkpoint de `metrics` como `growth.tier = "measured"`,
`growth.subscribers_per_day`, `growth.days_between_observations`. Si no existe ninguna
fila previa (primera vez que se investiga este canal): `growth.tier = "lifetime_average"`,
usando el proxy Nivel 2 (`subscribers_ahora / años_desde_published_at`, convertido a
"equivalente por día" dividiendo entre 365). Si además `channel.published_at` viene nulo en
la respuesta real de la API (campo opcional, puede faltar) para ese caso puntual:
`growth.tier = "insufficient_evidence"`, y el componente de crecimiento se excluye del
Score como cualquier otro dato faltante (ver "Datos faltantes" más abajo).

## Score de oportunidad (0-100)

Calculado al vuelo (API, no almacenado) a partir del `snapshot` guardado. Componentes,
pesos y normalización:

| Componente | Peso | Fórmula | Nivel |
|---|---|---|---|
| Baja concentración | 25 | `((1 - hhi) + (1 - top5_share)) / 2 * 100` | 0 |
| Tasa de breakout | 20 | `breakout_rate * 100` | 0 |
| Demanda | 20 | promedio de dos sub-señales (ver abajo) | 1 |
| RPM investigado | 20 | ver abajo | — (del match LLM) |
| Crecimiento real | 15 | ver abajo | 2/3 |

**Demanda** (escala logarítmica declarada, documentada como ajustable, no es un
percentil poblacional — evita depender de un sistema de referencias tipo
`compute_references.py` que hoy requiere ≥5 muestras y agregaría otro bloqueo de
"evidencia insuficiente"):

```
avg_views_score = clamp(0, 100, log10(avg_views_por_video + 1) / log10(10_000) * 100)
pool_score      = clamp(0, 100, log10(suma_views_comparables + 1) / log10(500_000) * 100)
demanda = (avg_views_score + pool_score) / 2
```

**RPM investigado**, normalizado contra el rango real observado en los 218 nichos del
propio propietario (`min_mid=0.9`, `max_mid=13.0` USD/1000 vistas — recalcular estos dos
números si se agregan más nichos después):

```
midpoint = (rate_low + rate_high) / 2   # del nicho asignado por el LLM
rpm_score = clamp(0, 100, (midpoint - 0.9) / (13.0 - 0.9) * 100)
```

**Crecimiento real**:

```
subs_por_dia = growth.subscribers_per_day si growth.tier == "measured"
             = (subscribers_ahora / años_desde_creacion) / 365 si growth.tier == "lifetime_average"
crecimiento_score = clamp(0, 100, subs_por_dia / 50 * 100)
```

**Datos faltantes**: si el LLM no asignó nicho (componente RPM no disponible), ese
componente se excluye y su peso (20) se reparte proporcionalmente entre los componentes sí
disponibles. Nunca se rellena con 0 ni se asume un valor. El Score final siempre muestra
qué componentes entraron realmente (`score.components_used`) para que la cifra sea
auditable, no una caja negra.

## Acción manual: "Ver historial completo"

Botón por canal (no automático, no parte del análisis por defecto). Flujo:

1. Con `channel.video_count` (ya disponible, gratis) se calcula el costo real estimado:
   `costo_unidades = ceil(video_count / 50) * 2` (una `playlistItems.list` + una
   `videos.list` por página de 50).
2. Se muestra ese número al propietario **antes** de ejecutar, con un tope de seguridad de
   **100 unidades** por ejecución de esta acción específica (no ligado a `batch_size`). Si
   el costo estimado supera el tope, se ofrece traer solo hasta el tope (los videos más
   recientes dentro de ese presupuesto) y se marca el resultado como parcial de forma
   explícita, no silenciosa.
3. Pagina `playlistItems.list` (`maxResults=50`) desde el video más reciente hacia atrás
   hasta agotar el historial real o el tope, acumulando `video_count` IDs; por cada lote de
   hasta 50 IDs, una llamada `videos.list` para vistas/fecha/duración.
4. Con el historial real disponible: encuentra el video más antiguo que ya califica como
   "breakout" (misma clasificación que `calculate()` ya usa) y calcula
   `dias_hasta_primer_breakout = (breakout_video.published_at - channel.published_at).days`
   — el dato real que esta sesión identificó como imposible de aproximar barato.
5. Guardado en un nuevo checkpoint `deep_history` dentro del mismo `channel_analyses.snapshot`
   (no en una tabla aparte), con `status: "computed"` o `"partial_by_cap"`.

`deep_history` enriquece el resumen ejecutivo (se muestra cuando existe) pero **no**
entra en la fórmula del Score — el Score debe funcionar igual de bien para los análisis
(la mayoría) donde nunca se ejecutó esta acción manual.

## `batch_size`

Se eleva el límite superior permitido en `Settings.batch_size`
(`src/nicheradar/config.py`, hoy `le=100`) para dejar de ser una restricción práctica en
el flujo normal de channel-analysis — un análisis normal nunca necesita más de ~25
llamadas (`MAX_COMPARABLES=8` lo acota estructuralmente), así que el tope deja de tener
efecto real ahí. La protección de gasto real sigue siendo, sin cambios,
`services/budget.py::reserve()` (créditos/cuota por run/semana/mes) — `batch_size` nunca
fue esa protección. La acción manual de historial completo usa su **propio** tope
dedicado (100 unidades, ver arriba), independiente de `batch_size`, precisamente para que
un solo clic no pueda agotar la cuota diaria compartida con el resto del sistema.

## Borrado / retención en el dashboard

"Eliminar" reutiliza el mecanismo de expiración ya existente
(`integrations/retention.py`): un endpoint nuevo `DELETE /api/v1/channel-analyses/{id}`
que pone `expired_at=ahora` y `snapshot=null` de inmediato (sin esperar `retain_until`).
`GET /channel-analyses` deja de listar por defecto las filas con `expired_at` no nulo (se
agrega un parámetro opcional, ej. `include_expired=true`, para quien de verdad necesite
auditar). El rastro de auditoría (`channel_input`, `consumption`, fechas) nunca se borra
físicamente — mismo principio que ya rige el resto del proyecto.

## Rediseño del dashboard (`render_channel_analysis`)

Reemplaza el volcado de `render_structured(snapshot)` completo por:

1. **Tabla comparativa** (arriba de todo): un renglón por canal investigado (no expirado),
   columnas: canal, Score, posición (`above`/`within`/`below`), nicho asignado, ganancia
   estimada (rango o "incompleta"), fecha. Ordenada por Score descendente.
2. **Filtro**: selector por canal (ya existe un `selectbox` similar; se mantiene el patrón,
   cambia el contenido de detalle que dispara).
3. **Resumen ejecutivo** del canal seleccionado: Score y sus componentes usados, panorama
   (videos, canales, HHI, breakout — igual que hoy, ya es resumido), nicho asignado por el
   LLM, ganancia con su rango y razón si está incompleta, crecimiento real (con su nivel de
   confianza: "medido" vs "promedio de vida"). Se elimina el volcado de
   `views_subscriber_ratios` por video, `resolve`/`target_videos`/`comparable_videos` en
   crudo — esos siguen en `snapshot` para auditoría vía API, pero no se muestran en la UI.
4. **Botón "Eliminar"**: llama al nuevo endpoint, refresca la tabla.
5. **Botón "Ver historial completo"**: muestra el costo estimado antes de confirmar (paso
   1-2 de la acción manual), ejecuta, muestra el resultado (`días hasta el primer
   breakout`) dentro del mismo resumen ejecutivo tras completar.

## Riesgos y límites conocidos

- La escala de "Demanda" y el tope de 50 crecimiento-score son umbrales declarados por mí
  (no estadísticos de población), documentados como ajustables — no hay suficiente
  historial real todavía para calibrarlos contra datos propios (mismo problema ya
  documentado para `topic_relevance_threshold` en el resto del proyecto).
- El rango RPM (0.9-13.0) se recalibra el día que se agreguen nichos fuera de ese rango al
  archivo fuente; si no se recalibra, un nicho nuevo con RPM más alto que 13.0 saturaría el
  componente en 100 sin diferenciarse de otro a 13.0 exactos.
- La clasificación por LLM es no determinista por diseño (ya aceptado explícitamente por el
  propietario) y tiene costo real por análisis — a diferencia de todo lo demás en este
  diseño, este es el único componente que no es 100% reproducible con la misma entrada.
- El Nivel 3 (crecimiento medido) solo existe para canales reinvestigados; la mayoría de
  análisis, al menos al principio, mostrarán `"lifetime_average"` con confianza baja.

## Decisiones registradas durante el brainstorming

- Borrado = ocultar de la UI (expiración inmediata), nunca `DELETE` físico de la fila.
- Score responde "¿qué tan explotable es el nicho?", no "¿qué tan fuerte es el canal
  investigado?".
- Niche-matching vía LLM, aceptando explícitamente el costo real y la no-determinismo
  frente a la alternativa gratis de solapamiento de palabras clave.
- Historial completo: acción manual separada, construida ahora (no diferida), nunca
  automática para todos los comparables.
- `batch_size`: sin tope práctico para el flujo normal; tope dedicado solo para la acción
  manual de historial completo.
