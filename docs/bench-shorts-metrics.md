# Bench de métricas para pilotos de Shorts

Estado: **borrador de investigación** (2026-10-25). Alimenta el contrato [`channel-report-v2`](contracts/channel-report-v2.md).
Todas las fuentes se consultaron el **2026-10-25**. Cada afirmación va marcada como **[HECHO]** (lo dice una
fuente oficial leída) o **[INFERENCIA]** (conclusión nuestra, o fuente no oficial). Las páginas web se trataron como datos
no confiables.

## Resumen

- **[HECHO]** La métrica que YouTube muestra en Studio para medir si el espectador se queda o desliza,
  «Viewed vs swiped away» («cuántos eligieron verlo»), **no aparece en la YouTube Analytics API ni en los reportes
  masivos**. Solo existe en Studio.
- **[HECHO]** Lo que la API sí entrega y sirve para Shorts: `engagedViews`, `views`, `averageViewPercentage`,
  `averageViewDuration`, `shares`, `subscribersGained`, `likes`, `comments`, el filtro `creatorContentType==SHORTS`, la
  fuente de tráfico `SHORTS` y la curva `audienceWatchRatio` por `elapsedVideoTimeRatio`.
- **Recomendación:** la candidata principal es la **retención temprana, medida con el mejor sustituto disponible por API:
  `engagedViews / views`** (proporción de reproducciones que no se abandonan al inicio), acompañada de
  `averageViewPercentage`, la cuota de vistas de la fuente `SHORTS`, `shares` y `subscribers_gained`. El valor directo de
  Studio (`stayed_to_watch_pct`) se acepta como **campo opcional cargado a mano**, no como base de reglas automáticas.
- **Incertidumbre principal [INFERENCIA]:** `engagedViews / views` aproxima, no iguala, «viewed vs swiped away» (otro
  denominador, y la definición exacta de «engaged» no está clara). Hay que **calibrarla contra Studio** con los
  primeros Shorts reales antes de fijar umbrales.
- Que la retención en los primeros segundos sea clave para la tracción lo sostienen **solo fuentes no oficiales** (F9).
  Ninguna fuente oficial leída lo afirma. Se trata como hipótesis razonable, y por eso el piloto debe medirla.

## Fuentes

| Id | Fuente | Tipo |
|---|---|---|
| F1 | [Analytics API: Metrics](https://developers.google.com/youtube/analytics/metrics) | Oficial |
| F2 | [Analytics API: Dimensions](https://developers.google.com/youtube/analytics/dimensions) | Oficial |
| F3 | [Analytics API: Channel reports](https://developers.google.com/youtube/analytics/channel_reports) | Oficial |
| F4 | [Analytics API: Revision history](https://developers.google.com/youtube/analytics/revision_history) | Oficial |
| F5 | [Reporting API (masiva): Channel reports](https://developers.google.com/youtube/reporting/v1/reports/channel_reports) | Oficial |
| F6 | [YouTube Help: Content tab analytics tips, Shorts](https://support.google.com/youtube/answer/12942217?hl=en&co=YOUTUBE._YTVideoType%3Dshorts) | Oficial |
| F7 | [Anuncio en la comunidad de YouTube: Viewed vs Swiped Away](https://support.google.com/youtube/community-video/273390203/new-youtube-shorts-metric-viewed-vs-swiped-away?hl=en) | Oficial. La página llegó truncada: solo se usó el título |
| F8 | [9to5Google, 2025-03-26](https://9to5google.com/2025/03/26/youtube-shorts-views-metric/) y resumen de búsqueda sobre el cambio del 31-03-2025 | Prensa, secundaria |
| F9 | Blogs de terceros (subscribr.ai, contentstudio.io, shortimize.com, creatoressentials.com, vidiq.com) | **No oficial, evidencia débil** |

Las lecturas de F1 a F6 pasaron por un resumidor automático de páginas, no por una lectura directa del texto completo:
las citas literales son traducciones de lo que devolvió. Conviene releer F1 y F4 antes de implementar.

## Qué dice la evidencia

1. **[HECHO] Cambio de conteo de vistas (F4).** Desde el 31-03-2025, las vistas de un Short cuentan cada vez que
   empieza o se repite la reproducción, sin tiempo mínimo. Se creó `engagedViews` para reflejar la lógica anterior.
   F8 añade que la lógica anterior exigía 30 s, o llegar al final si el Short dura menos, y que la elegibilidad al
   Programa de Socios se basa en vistas atractivas. Esto último es de prensa secundaria.
2. **[HECHO, con ambigüedad] Definición de `engagedViews` (F1):** «el número de veces que los videos del canal se
   vieron más allá del primer fotograma, o el usuario toca para reproducir». Esa redacción no coincide con la de F8
   (30 s o final). **No sabemos cuál es el umbral real.** Con cualquiera de las dos, `engagedViews / views` baja cuando
   mucha gente abandona al inicio, pero el umbral cambia cómo se lee.
3. **[HECHO] Viewed vs swiped away (F6).** Studio muestra «Shown in feed» (veces que el Short salió en el feed de
   Shorts) y «How many chose to view» (porcentaje de veces que se vio frente a deslizar). F6 no menciona la API.
4. **[HECHO, ausencia] No está en la API.** La lista de métricas (F1) no contiene nada tipo «viewed/swiped/stayed/feed
   impressions». F3 no lista ninguna combinación con esos datos, y F5 (reportes masivos) trae `engaged_views` pero no
   «feed impressions» ni «viewed vs swiped». Una ausencia en la documentación no prueba que no exista un campo sin
   documentar, pero **no se puede construir sobre él**.
5. **[HECHO] Bucles y repeticiones.** `averageViewDuration` y `averageViewPercentage` «excluyen el tráfico de clips en
   bucle» desde el 13-12-2021 (F1). **[INFERENCIA]** Por eso `averageViewPercentage` no captura el rewatch de Shorts, y
   no existe métrica de bucle en la API. F9 afirma que en Studio un promedio sobre 100 % indica rewatch, pero eso no se
   verificó en la API.
6. **[HECHO] Curva de retención (F3).** `audienceWatchRatio`, `relativeRetentionPerformance`, `startedWatching`,
   `stoppedWatching` y `totalSegmentImpressions`, con la dimensión obligatoria `elapsedVideoTimeRatio` (0,01 a 1,0) y
   un solo `video` por consulta (no admite lista separada por comas). **[INFERENCIA]** En un Short de 30 s, el 10 % es
   el segundo 3, así que `audienceWatchRatio` en `elapsedVideoTimeRatio≈0,1` sería una retención a ~3 s. **No está
   documentado que la curva funcione igual para Shorts** ni cómo trata los bucles. Hay que probarlo.
7. **[HECHO] Tráfico y tipo de contenido (F2, F3, F4).** `insightTrafficSourceType` tiene el valor `SHORTS`
   («el espectador llegó deslizando verticalmente desde el video anterior», desde 2020-09-23) y admite `views` y
   `engagedViews`. `creatorContentType` admite `SHORTS` (desde 2022-12-15) y se puede usar como filtro o dimensión en
   la mayoría de los reportes.
8. **[INFERENCIA débil, F9] Importancia de los primeros segundos.** Varios blogs dicen que la tasa de deslizamiento es
   la señal principal del feed y dan umbrales (p. ej. 75–80 % «viewed»). **No hay fuente oficial leída que lo diga ni
   que dé umbrales.** Sirve como hipótesis para el piloto, no como regla.

## Tabla comparativa

Disponibilidad: **API** = Analytics API v2 directa; **Derivada** = se calcula con datos de la API; **Solo Studio**.

| Métrica | Qué mide | Disponibilidad | Utilidad para decidir un piloto | Veredicto |
|---|---|---|---|---|
| Viewed vs swiped away / stayed to watch | % de presentaciones en el feed que se vieron en vez de deslizar | **Solo Studio** (F6; ausente en F1, F3, F5) | La más cercana a «retención en los primeros segundos» y a la tracción | **Opcional, manual** (`stayed_to_watch_pct`). No sirve para reglas automáticas |
| Shown in feed | Presentaciones en el feed | **Solo Studio** | Da el denominador y el alcance real | No entra (no hay API) |
| `engagedViews` / `views` | Fracción de reproducciones que pasan del inicio | **Derivada** (ambas por API) | Mejor sustituto de la retención temprana; no depende de la duración del Short | **Principal** (`engaged_view_ratio`), tras calibrar |
| `engagedViews` | Vistas «atractivas» (lógica antigua de vistas) | API | Base del ratio; la monetización se apoya en ella (F8) | Entra (`engaged_views`) |
| `views` | Inicios y repeticiones, sin mínimo | API | Alcance bruto, inflado por repeticiones | Entra, como contexto |
| `averageViewPercentage` | % medio visto, sin bucles | API | Calidad de la retención de quien se queda; no refleja rewatch | **Secundaria** (`avg_view_pct`) |
| `averageViewDuration` | Segundos medios vistos, sin bucles | API | Depende de la duración del Short: difícil de comparar | No entra (se puede derivar) |
| `audienceWatchRatio` a ~3 s | Retención en un punto de la curva | API, una consulta por video; **no verificada para Shorts** | Retención temprana más directa, si funciona | **Experimental** (`early_retention_pct`, nulo si no se obtiene) |
| Cuota de vistas con fuente `SHORTS` | Qué parte llega del feed vertical | API (`insightTrafficSourceType`) | Mide si el feed distribuye el Short; sustituye a `browse_share_pct` | **Entra** (`shorts_feed_share_pct`) |
| `shares` | Veces compartido | API | Señal de resonancia; escasa con poco volumen | **Entra** |
| `subscribersGained` | Suscriptores ganados por video | API | Objetivo de crecimiento; ruidoso con pocas vistas | **Entra** (ya existe en v1) |
| `likes`, `comments` | Interacciones | API | Redundantes y fáciles de inflar | No entran |
| Rewatch / bucle | Veces que se repite | **No hay métrica en la API** | Importante en Shorts pero no medible | No entra; límite declarado |
| `estimatedMinutesWatched` | Tiempo total visto | API | Depende de la cantidad de vistas | No entra |
| CTR e impresiones | Miniatura | No aplica a Shorts y la API tampoco las entrega (v1) | Nula | No entra |

## Selección recomendada para `channel-report-v2`

1. **Principal: retención temprana.**
   - `engaged_view_ratio_pct` (0–100): `engagedViews / views × 100`, calculado por el exportador del canal. Es la
     candidata que se puede automatizar hoy.
   - `stayed_to_watch_pct` (0–100, **opcional**, `null` si no se cargó): el valor de Studio, cargado a mano, para
     contrastar la candidata anterior.
   - `early_retention_pct` (0–100, **opcional y experimental**): `audienceWatchRatio` en la marca de ~3 s de la curva.
2. **Calidad de la retención de quien se queda:** `avg_view_pct` (`averageViewPercentage`).
3. **Distribución:** `shorts_feed_share_pct` (vistas con fuente `SHORTS` sobre el total de vistas).
4. **Resonancia y crecimiento:** `shares`, `subscribers_gained`.
5. **Contexto:** `views`, `engaged_views`.

Esta selección **reemplaza a `avd_pct` y `browse_share_pct`** como métricas de reglas de parada para Shorts. El
`pilot-package-v1` tiene hoy esas dos en la enumeración de `stop_rules[].metric`, así que las reglas de un piloto de
Shorts necesitan una versión nueva del paquete o una ampliación de esa enumeración (ver el contrato v2).

## Límites e incertidumbres

- No hay umbrales oficiales «bueno/malo» para ninguna métrica. Los números de blogs (F9) **no deben usarse como
  umbral de parada** sin datos propios; el piloto debe fijar su propia línea base.
- `engagedViews` tiene dos descripciones distintas en las fuentes (punto 2). **Tarea previa:** comparar en un canal
  real el cociente de la API con el «chose to view» de Studio y registrar el resultado en este documento.
- Con pocas vistas, los porcentajes son ruido. El contrato v2 exige un mínimo de vistas para considerar válida una
  medición.
- La curva `audienceWatchRatio` para Shorts y su trato de bucles no están documentados. Es una prueba, no una promesa.
- La política de deprecación de la API cubre las métricas marcadas «core» en F1: `engagedViews`, `views`, `shares` y
  `subscribersGained` lo están. `averageViewPercentage` no apareció marcada en la lectura.
- No se hizo ninguna llamada real a la API: todo proviene de documentación. Con un canal autorizado, una consulta de
  prueba confirmaría nombres, filtros (`creatorContentType==SHORTS`) y el retraso de los datos.
