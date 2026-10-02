# Análisis competitivo de canal — diseño

Estado: validado en conversación con el propietario el 2026-10-01. Pendiente de revisión
del archivo antes de pasar a `writing-plans`.

## Resumen

Flujo nuevo, independiente del descubrimiento por catálogo: el propietario pega la
URL/handle/ID de un canal de YouTube y el sistema investiga, con datos reales, si existe
oportunidad de competir en ese nicho — combinando un panorama del espacio competitivo con
una comparación directa contra ese canal puntual. El resultado queda guardado (no es
efímero) en una pestaña propia del dashboard, separada del Home.

## Objetivo de negocio

Responder, con evidencia real y sin inventar ningún dato faltante:

1. **Panorama del nicho**: ¿hay lugar para otro canal en el espacio donde vive este
   canal? (demanda, concentración, tasa de éxito/breakout de los canales ya compitiendo).
2. **Comparación directa**: ¿cómo se posiciona este canal específico frente a sus propios
   comparables reales? ¿Sería realista superarlo dado el costo real de producción propio
   (Creator Fit) y, si existe, una tasa publicitaria (RPM) ya declarada?

## Fuera de alcance (explícito)

- No reemplaza ni se mezcla con el descubrimiento por catálogo de familias semilla; es un
  flujo bajo demanda, separado.
- No certifica monetización, no garantiza resultados, no proyecta el desempeño de un canal
  nuevo más allá de mostrar el rango real ya observado entre comparables (misma regla que
  ya rige `scoring/profit.py`).
- No usa Social Blade (sin capa gratuita real, confirmado por investigación) ni el feed
  RSS de YouTube (zona gris de cumplimiento: funciona, pero es un resto no documentado
  oficialmente de una API descontinuada en 2015) ni Google Trends (sin API oficial
  pública; solo alpha cerrada por invitación, y la librería no oficial más usada está
  archivada). Ninguna de las tres se usa aunque estén disponibles técnicamente.

## Fuentes de datos (todas en paralelo, nunca una de respaldo de otra)

Cada análisis combina **YouTube Data API v3** (gratis, ya autenticado) **y vidIQ** (de
pago, cupo real escaso) a la vez, para la mejor información posible. Si vidIQ falla por
cupo/crédito agotado, el análisis **continúa solo con YouTube**, marcado explícitamente
(`vidiq_omitted: budget_exhausted`), nunca falla por completo ni inventa el dato que
faltó.

### YouTube Data API v3 (cuotas reales confirmadas por el propietario en su propio panel)

| Operación | Costo | Cupo diario real | Uso en este flujo |
|---|---|---|---|
| `search.list` (type=channel/video) | 100 unidades | **100/día** (bucket propio, separado) | Descubrir comparables por categoría/palabras clave |
| `channels.list` | 1 unidad | 10.000/día (pool compartido) | Resolver identidad del canal objetivo y de cada comparable |
| `playlistItems.list` (uploads) | 1 unidad | 10.000/día (pool compartido) | Listar videos recientes de cada canal |
| `videos.list` (`statistics`) | 1 unidad | 10.000/día (pool compartido) | Vistas, likes, comentarios por video |
| `commentThreads.list` | 1 unidad | 10.000/día (pool compartido) | Señal de engagement adicional (nuevo, no usado antes en el proyecto) |
| `videoCategories.list` / `i18nRegions.list` | 1 unidad | 10.000/día (pool compartido) | Nombre legible de categoría (nuevo) |

Con 100 búsquedas/día, el límite práctico real es **cuántas categorías/palabras clave se
pueden explorar por día**, no cuántos canales se pueden mirar en detalle (eso tiene
10.000/día de margen). El diseño debe acotar `search.list` a **una sola llamada por
análisis** (buscar comparables de la categoría del canal objetivo una vez), dejando el
resto de las llamadas (detalle de cada comparable encontrado) en el pool barato.

### vidIQ (de pago, cupo real escaso)

Tope propio y declarado: **50 créditos vidIQ por análisis** (decisión del propietario),
chequeado en vivo contra el saldo real igual que los demás topes del proyecto (nunca se
sube para forzar que alcance). Operaciones usadas: `channel_search` (comparables),
`channel_videos` (videos recientes), `outliers` (detección de outliers que YouTube no
ofrece), `keyword_research`. Si el saldo real no alcanza para todas, se ejecuta lo que
alcance y el resto queda `partial`, nunca silencioso.

## Flujo de datos, paso a paso

1. El propietario pega una URL/handle/ID de canal en la pestaña "Análisis de canal".
2. **Resolver identidad real** (YouTube `channels.list`): canal objetivo, categoría cruda,
   suscriptores. Si no se encuentra, error claro, **sin gastar ningún crédito de vidIQ**.
3. **Videos del canal objetivo** en paralelo: YouTube (`playlistItems.list` +
   `videos.list` + `commentThreads.list`) y vidIQ (`channel_videos`) — se usan ambas
   fuentes, no una sustituye a la otra. Con esto se calcula la velocidad real de
   vistas/día del canal objetivo (mismo método que `demand_by_age`, pero por canal).
4. **Descubrir comparables reales**: una llamada a YouTube `search.list`
   (`type=channel`, `q=<categoría/palabras clave del canal objetivo>`) **y** vidIQ
   `channel_search`/`outliers`/`keyword_research`, acotado a un máximo combinado de
   comparables (a definir en el plan de implementación, ej. 8–10, deduplicados por
   `channel_external_id`).
5. **Videos de cada comparable**: mismo patrón del paso 3, para cada canal comparable
   encontrado, respetando el tope de 50 créditos vidIQ del análisis completo.
6. **Nombre legible de categoría**: YouTube `videoCategories.list`/`i18nRegions.list`.
7. **Métricas del conjunto comparable**: reutiliza `features/metrics.py::calculate()` (o
   una variante mínima) sobre los videos de los comparables — demanda, concentración,
   tasa de breakout, y velocidad de vistas mejor/peor del conjunto, **excluyendo al canal
   objetivo** del rango mejor/peor (para comparar "tú vs. el resto", no contigo mismo).
8. **Posición del canal objetivo**: su propia velocidad de vistas/día frente al rango
   mejor/peor de los comparables (por encima, por debajo, o dentro del rango).
9. **Ganancia mensual estimada** (si hay receta de producción y RPM declarados para un
   formato/audiencia equivalente): reutiliza `scoring/profit.py::estimate_profit` con el
   rango mejor/peor del conjunto comparable, igual metodología que el Home. Si falta
   cualquier insumo real, `status: "incomplete"` con la razón exacta.
10. **Persistir todo**: canal objetivo, comparables, métricas, posición, ganancia
    estimada, consumo real gastado (créditos vidIQ + cuota YouTube por bucket) — en la
    tabla nueva `channel_analyses`.

## Ejecución: reutiliza la cola de trabajos existente

No es una llamada HTTP síncrona bloqueante. Se ejecuta con el mismo mecanismo de
`analysis_runs`/`jobs` que ya usa el radar (arrendamiento, heartbeat, reintentos,
checkpoints, reanudación tras fallo) — consistente con todo lo demás en el proyecto.

- `analysis_runs.trigger` nuevo valor: `"channel_analysis"` (hoy solo existen
  `"scheduled"`/`"manual"`).
- `workers/pipeline.py::Pipeline.process()` gana una secuencia de etapas paralela,
  despachada cuando `run["trigger"] == "channel_analysis"`: `resolve` → `target_videos` →
  `discover_comparables` → `comparable_videos` → `metrics` → `profit` → `persist`. No
  modifica ni comparte estado con la secuencia existente de catálogo/refresh.
- Igual que el resto del sistema: si el presupuesto (vidIQ o cuota YouTube) se agota a
  mitad de camino, el job termina `partial`, con lo que sí se alcanzó a reunir, nunca
  truncado en silencio.

## Modelo de datos (migración aditiva, tabla nueva)

`channel_analyses`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID, PK | |
| `profile_id` | UUID, FK `creator_profiles` | |
| `run_id` | UUID, FK `analysis_runs`, unique | el job que lo generó |
| `channel_input` | texto | lo que el propietario pegó originalmente (auditoría) |
| `channel_external_id` | texto | ID real de YouTube ya resuelto |
| `status` | texto | `completed` / `partial` / `failed` |
| `configuration` | JSONB | parámetros reales de la búsqueda (tope de comparables, etc.) |
| `snapshot` | JSONB | canal objetivo, comparables, métricas, posición, ganancia estimada |
| `consumption` | JSONB | créditos vidIQ y unidades de cuota YouTube realmente gastados, por bucket |
| `created_at` | timestamp | |
| `retain_until` | timestamp | conservación, mismo patrón que el resto del proyecto |
| `expired_at` | timestamp, nullable | mismo patrón de limpieza por vencimiento ya existente |

Cada análisis es inmutable una vez creado; volver a analizar el mismo canal crea un
registro nuevo (nunca edita uno existente), para no perder el historial de lo ya gastado.

## API privada

- `POST /api/v1/channel-analyses` — body `{channel_input: str}`. Encola el job (mismo
  patrón que `POST /runs`), devuelve `job_id`/`status_url`. Antes de encolar, valida que
  el radar esté en condiciones (`require_live_ready` si está en modo live) y que haya
  cupo real declarado para el tope de 50 créditos.
- `GET /api/v1/channel-analyses` — lista paginada de análisis guardados (mismo patrón que
  `GET /opportunities`).
- `GET /api/v1/channel-analyses/{id}` — detalle completo (snapshot + consumo + estado).

## UI (dashboard)

Pestaña nueva "Análisis de canal", separada del Home:

- Formulario: campo de texto para URL/handle/ID, botón "Analizar" que muestra el costo
  máximo real antes de confirmar (mismo patrón de "no autoriza nada por accidente" que ya
  usa el resto del dashboard).
- Lista de análisis previos (fecha, canal, estado, costo real gastado).
- Detalle de un análisis: panorama del nicho (demanda/concentración/breakout), posición
  del canal objetivo frente al rango de comparables, ganancia mensual estimada (o razón
  de por qué está incompleta), y qué fuentes se usaron realmente (incluye aviso si vidIQ
  se omitió por cupo agotado).

## Manejo de errores y degradación

- Canal no encontrado / URL inválida → error claro antes de gastar cualquier crédito.
- Cero comparables reales encontrados → análisis `partial`/`incomplete` en esa sección,
  nunca comparables inventados.
- vidIQ sin cupo → continúa solo con YouTube, marcado explícitamente.
- Cuota YouTube `search.list` agotada (100/día) → el análisis falla esa etapa específica
  con un error claro (`youtube_search_quota_exhausted`), sugiriendo reintentar al día
  siguiente; no usa RSS ni ninguna fuente no aprobada como sustituto silencioso.
- Presupuesto vidIQ de 50 créditos agotado a mitad → `partial`, con lo ya reunido.

## Pruebas (a detallar en el plan de implementación)

- Proveedor sintético para todo el flujo (igual que el resto del sistema): resolución de
  canal, descubrimiento de comparables, métricas, persistencia.
- Casos: canal no encontrado, cero comparables, presupuesto vidIQ agotado a mitad,
  cuota YouTube `search.list` agotada, ganancia estimada completa e incompleta.
- Migración nueva verificada con `compare_metadata` (mismo patrón que `production_recipe_defaults`).

## Riesgos y limitaciones conocidas

- El límite real de 100 búsquedas/día de YouTube es compartido entre todos los análisis
  de canal que se pidan en un mismo día; pedir muchos análisis seguidos puede agotarlo
  antes de llegar al tope de créditos vidIQ.
- vidIQ sigue siendo necesario para `outliers`/`keyword_research`, que YouTube no ofrece
  de forma equivalente; no se puede prescindir de vidIQ por completo con las fuentes
  gratuitas actuales.
- Social Blade, RSS y Google Trends quedan explícitamente fuera; si en el futuro Google
  Trends sale de alpha cerrada o Social Blade ofrece un nivel gratuito real, es una
  decisión nueva a tomar, no una activación automática.
