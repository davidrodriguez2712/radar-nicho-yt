# Descubrimiento de subnichos desde YouTube (subproyecto B) — diseño

Estado: diseño aprobado en conversación por el propietario el 2026-10-31 (enfoques B1 + B3).
Pendiente de revisión de este archivo antes de pasar a `writing-plans`.

Es el **subproyecto B** de la iniciativa "descubrimiento de subnichos". Los otros tres se
diseñan después, cada uno con su propio spec: **A** taxonomía familia→nicho→subnicho y
clasificación semanal del marketplace, **C** pistas de X/Twitter, **D** informe de decisión.

## Resumen

Hoy el marketplace dice qué nichos *se venden*. Este subproyecto mide el lado de la
**demanda**: dada una *hipótesis de subnicho* (por ejemplo `history_revenge`, con consultas
como "history revenge"), busca en YouTube, encuentra los canales que ya triunfan, mide sus
visitas recientes y estima un rango de ingreso. Produce un perfil de oportunidad por
hipótesis. Una corrida grande inicial y luego una semanal. **Sin LLM en la v1: coste de
modelo cero.** Solo cuota de la YouTube Data API (gratuita).

## Decisiones del propietario

| Tema | Decisión |
| --- | --- |
| Orden | Empezar por B; después A, C y D |
| Jerarquía | Tres niveles: familia → nicho → subnicho |
| Enfoque | B1 (búsqueda por consulta) + B3 (valores atípicos: video fuerte en canal pequeño) |
| Cuota | Autorizado subir los topes de búsqueda para una corrida inicial grande. Solo API; sin créditos de vidIQ |
| Alcance de contenido | Inglés y formato largo únicamente |
| Pistas de X | El propietario las aporta (subproyecto C). Cuentan como ideas de hipótesis |

## Supuestos (documentados; corregibles)

- **Canal pequeño:** menos de 100.000 suscriptores. **Ventana de análisis:** 90 días.
- Las pistas en otro idioma se tratan como *ideas de nicho* y se prueban en inglés.
- La primera lista (~40 hipótesis) la redacta Claude mezclando ejemplos del propietario,
  catálogo y marketplace; **el propietario la revisa antes de gastar cuota**.
- El RPM sale del catálogo de nichos (rangos por nicho) y se hereda al nicho padre cuando el
  subnicho no tiene el suyo, marcado como "heredado".

## Fuera de alcance

- Llamadas a LLM (clasificar subnichos, resumir canales): v2.
- Taxonomía completa y promoción de hipótesis a subnicho (subproyecto A).
- Lectura de X/Twitter (subproyecto C): aquí solo queda la interfaz de entrada de hipótesis y
  canales.
- Informe final de decisión y página del dashboard (D; la página llega en una fase posterior
  de este mismo subproyecto, después del informe de solo lectura).
- Ingreso "real": todo ingreso es **estimación en rango**, nunca un dato.

## Arquitectura

Paquete nuevo `src/nicheradar/subniche_discovery/`, con tablas, estados y entrada de worker
propios. No modifica el marketplace ni el radar. Reutiliza la pasarela de YouTube
(`integrations/youtube.py`), su política, topes y libro de cuotas.

Unidades (una responsabilidad cada una):

1. **hypotheses**: alta y estado de hipótesis (nombre, familia, nicho padre, consultas,
   idioma, formato, origen). Interfaz de entrada única, que usarán C y A.
2. **search**: ejecuta `search.list` por consulta; devuelve videos y canales candidatos.
3. **harvest**: completa canales (`channels.list`) y videos recientes (`playlistItems` +
   `videos.list`) en lotes de 50.
4. **estimate**: visitas por ventana, separación largo/Shorts, rango de ingreso, banderas de
   calidad. Funciones puras, sin red.
5. **outliers (B3)**: razón visitas-de-video / suscriptores-del-canal; cuenta canales
   pequeños con tracción.
6. **score**: agrega por hipótesis (perfil de oportunidad).
7. **report**: informe de solo lectura (ranking y canales de ejemplo).

### Cambios en la pasarela de YouTube

La lista blanca de parámetros de `search` solo admite `q,type,order,regionCode,maxResults,
pageToken`. Hay que añadir `publishedAfter`, `relevanceLanguage` y `videoDuration`
(`long` = más de 20 min; `medium` = 4–20 min). Es un cambio localizado, con test.
`_normalize_search` hoy deja `published_at=None` para videos de búsqueda; se completa con
`videos.list` (1 unidad por 50), no con búsqueda.

## Flujo semanal (etapas)

`buscar` → `canales` → `videos recientes` → `estimar` → `puntuar` → `informe`.

1. **Buscar.** Por hipótesis activa y consulta: `search.list` con `type=video`,
   `order=viewCount`, `publishedAfter=ahora−90 días`, `relevanceLanguage=en`,
   `videoDuration=long`, hasta 2 páginas (100 unidades por página).
2. **Canales.** `channels.list` para los canales distintos hallados (lotes de 50).
3. **Videos recientes.** Últimos 20 a 50 videos por canal elegido (los 30 canales con más
   visitas en 90 días por hipótesis), con duración y visitas.
4. **Estimar.** Ver la sección siguiente.
5. **Puntuar y reportar.** Agregados semanales por hipótesis; informe en archivo/CLI.

Las etapas son reanudables y respetan la reserva de cuota antes de cada llamada (misma
semántica que el pipeline existente: una etapa que choca con el tope termina `partial`, no
falla).

## Estimación y calidad

- **Ingreso mensual estimado** = visitas de videos largos en 30 días × RPM del nicho /
  1000, **siempre como rango** [bajo, alto] usando el rango de RPM del catálogo, y marcado
  `estimate`. No se calibra con el marketplace (muestra insuficiente); se contrasta donde
  ambos coinciden.
- **Largo vs Shorts:** por duración (≤180 s = Short). Solo el largo cuenta; la proporción de
  Shorts se guarda como señal.
- **Volatilidad:** canal con menos de 180 días, o con visitas de 28 días muy por encima del
  ritmo de 90 días, se marca `volatil` y no entra en los agregados de ingreso mediano.
- **Idioma:** se excluyen canales cuyo idioma no coincide con el de la hipótesis (campo del
  canal o idioma del video cuando exista).
- **B3 (valores atípicos):** `outlier_ratio = visitas_video / max(suscriptores, 1000)`; un
  canal pequeño (<100k) con un video con razón ≥ 5 es *canal con tracción*. El perfil cuenta
  cuántos hay y su razón mediana.
- **Honestidad del dato:** las cifras que un promotor publique en X son solo pistas; todo se
  recalcula con la API.

Lección heredada del marketplace: el ingreso declarado fue poco fiable y el propietario
rechazó descontarlo; aquí no hay ingreso declarado, solo estimación explícita en rango.

## Datos (migración 0020)

- `niche_hypotheses` — `id`, `slug` único, `label`, `family`, `parent_niche_slug` null,
  `queries` (jsonb), `language`, `format`, `origin` (`manual|catalog|marketplace|lead`),
  `status` (`active|paused|archived`), `created_at`.
- `discovery_channels` — `channel_id` PK, `title`, `first_seen_at`, `last_seen_at`.
- `discovery_channel_snapshots` — instantánea semanal de datos de la API (suscriptores,
  visitas, país, fechas). **Retención 30 días** (política de términos de la API); un job de
  poda la aplica, igual que `listing_channel_snapshots`.
- `hypothesis_channel_hits` — `hypothesis_id`, `channel_id`, `run_id`, `rank`,
  `views_90d_long`, `views_28d_long`, `shorts_share`, `outlier_ratio_max`, `flags`.
- `hypothesis_snapshots` — agregados semanales por hipótesis (n canales, mediana de
  ingreso en rango, canales con tracción, competencia). **Se conservan** porque son derivados
  propios, no datos de la API.
- `discovery_runs` — corrida, etapa, cuota usada, estado.

Los datos derivados que se conservan no incluyen valores crudos de la API más allá de los
agregados; las tablas con datos de API siguen la retención de 30 días.

## Cuota y coste

search.list = 100 unidades; `channels.list`/`videos.list`/`playlistItems` = 1 por llamada
(≤50 ids). Corrida inicial de ~60 hipótesis × 2 consultas × 2 páginas = 24.000 unidades de
búsqueda, más ~1.500 de detalle: **~22.000 a 26.000 unidades repartidas en 3 días** (el
límite diario de la API es 10.000). Corrida semanal posterior: ~8.000 a 10.000 si se
mantienen las 40–60 hipótesis activas (se puede reducir a 1 página).

Acciones necesarias (las ejecuta el propietario, como el resto de los despliegues):

- Subir `youtube_search_quota_per_run/week/month` a valores que cubran la corrida (cada
  campo tiene tope máximo en `config.py`; `per_week` admite hasta 100.000).
- Añadir un tope diario nuevo (`subniche_daily_units`, defecto 9.000) para no agotar el
  límite diario de la API que comparten las demás etapas.
- Coste de modelo: **0**. Sin vidIQ.

## Errores y casos límite

- Tope de cuota o 403 `quotaExceeded`: la etapa termina `partial`, la siguiente corrida
  continúa. Nunca reintenta en bucle.
- Consulta sin resultados: la hipótesis queda con perfil vacío (`sin_senal`), no falla.
- Canal eliminado o privado entre etapas: se descarta con motivo registrado.
- Hipótesis duplicadas (misma consulta normalizada): el alta las rechaza.
- Resultados con idioma no inglés: se descartan y se cuentan (`excluidos_idioma`).

## Pruebas

- Unitarias: estimación de ingreso en rango, separación largo/Shorts, volatilidad,
  `outlier_ratio`, normalización de consultas, parámetros nuevos de `search`.
- Cuota: reserva antes de llamar; `partial` al tocar tope; tope diario.
- Retención: la poda borra snapshots de API y conserva `hypothesis_snapshots`.
- Integración con respuestas simuladas de YouTube (transporte falso, como el resto del
  sistema): corrida completa sobre 2 hipótesis, reanudación tras `partial`.
- Migración 0020 sube y baja limpia.

## Riesgos

- **Estimación de ingreso con error de 2 a 10×** (audiencia, mezcla de Shorts, RPM por
  país). Mitigación: rango, bandera `estimate`, contraste con marketplace.
- **Sesgo de búsqueda:** `order=viewCount` favorece videos viejos virales dentro de la
  ventana; B3 y la separación de volatilidad lo compensan parcialmente.
- **Cuota compartida:** una corrida grande puede dejar sin cuota al análisis de canales;
  se mitiga con el tope diario y ejecutando de noche.
- **Términos de la API:** retención de 30 días de datos de API; se cumple con la poda.

## Fases de entrega

1. Núcleo: parámetros de búsqueda, tablas, estimación pura, etapas y cuota (con tests).
2. Informe de solo lectura (script/CLI) y lista inicial de hipótesis para revisión.
3. Corrida inicial en producción (acciones del propietario) y primera lectura de resultados.
4. Página en el dashboard (después, solo si el informe resulta útil).

## Preguntas abiertas

Ninguna que bloquee el plan. Se decide al implementar, con test: valores exactos del
umbral `outlier_ratio` (partir en 5) y de "visitas de 28 días muy por encima" (partir en
2× el ritmo de 90 días).
