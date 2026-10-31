# Descubrimiento de subnichos desde YouTube (subproyecto B) — diseño

Estado: diseño aprobado en conversación por el propietario el 2026-10-31 (enfoques B1 + B3);
actualizado el mismo día con las decisiones de entrada de hipótesis, LLM, cadencia y
proveedor. Pendiente de revisión de este archivo antes de pasar a `writing-plans`.

Es el **subproyecto B** de la iniciativa "descubrimiento de subnichos". Los otros tres se
diseñan después, cada uno con su propio spec: **A** taxonomía familia→nicho→subnicho y
clasificación semanal del marketplace, **C** pistas de X/Twitter, **D** informe de decisión.

## Resumen

Hoy el marketplace dice qué nichos *se venden*. Este subproyecto mide el lado de la
**demanda**: dada una *hipótesis de subnicho* (por ejemplo `history_revenge`, con consultas
como "history revenge"), busca en YouTube, encuentra los canales que ya triunfan, mide sus
visitas recientes y estima un rango de ingreso. Produce un perfil de oportunidad por
hipótesis. Una corrida grande inicial y luego corridas cada 3 días. La medición usa solo
cuota de la YouTube Data API (gratuita). El **único uso de LLM** es proponer hipótesis nuevas
(centavos por propuesta, API de Anthropic).

## Decisiones del propietario

| Tema | Decisión |
| --- | --- |
| Orden | Empezar por B; después A, C y D |
| Jerarquía | Tres niveles: familia → nicho → subnicho |
| Enfoque | B1 (búsqueda por consulta) + B3 (valores atípicos: video fuerte en canal pequeño) |
| Cuota | Autorizado subir los topes de búsqueda para una corrida inicial grande. Solo API; sin créditos de vidIQ |
| Alcance de contenido | Inglés y formato largo únicamente |
| Entrada de hipótesis | Un comando `subniche add` que acepta consulta, video, canal o tweet; crea la hipótesis en estado `propuesta` y no gasta cuota hasta que el propietario la aprueba |
| LLM | Solo para **proponer** hipótesis. Sin filtro de relevancia en la v1 (se decide tras medir el ruido de la primera corrida) |
| Proveedor de LLM | **Anthropic** para todo lo nuevo (fase 1). Las tres piezas existentes (clasificación, emparejamiento, lectura de capturas) siguen en OpenAI `gpt-6-luna` hasta una fase 2 con prueba comparativa |
| Refresco | Opción B: cada hipótesis se mide una vez al aprobarla; solo las **finalistas** se refrescan cada 7 a 14 días |
| Cadencia | Corrida cada 3 días: mide hipótesis nuevas y refresca finalistas |
| Tope de gasto en dólares | Ninguno por ahora; el gasto se mapea por operación y modelo y los topes se fijan tras la primera prueba |
| Pistas de X | El propietario las aporta (subproyecto C). Cuentan como ideas de hipótesis |

## Supuestos (documentados; corregibles)

- **Canal pequeño:** menos de 100.000 suscriptores. **Ventana de análisis:** 90 días.
- Las pistas en otro idioma se tratan como *ideas de nicho* y se prueban en inglés.
- Las cifras que publique un tercero (promotores en X) son solo pistas; todo se recalcula
  con la API.
- La primera lista (~40 hipótesis) la redacta Claude mezclando ejemplos del propietario,
  catálogo y marketplace; **el propietario la revisa antes de gastar cuota**.
- El RPM sale del catálogo de nichos (rangos por nicho) y se hereda al nicho padre cuando el
  subnicho no tiene el suyo, marcado como "heredado".

## Fuera de alcance

- LLM para filtrar relevancia de canales, clasificar subnichos o resumir canales: v2.
- Migrar a Anthropic las tres piezas LLM existentes: fase 2, con prueba comparativa sobre una
  muestra congelada (los prompts y parsers actuales están afinados contra `gpt-6-luna`).
- Taxonomía completa y promoción de hipótesis a subnicho (subproyecto A).
- Lectura de X/Twitter (subproyecto C): aquí solo queda la interfaz de entrada de hipótesis y
  canales.
- Informe final de decisión y página del dashboard (D; la página llega en una fase posterior
  de este mismo subproyecto, después del informe de solo lectura).
- Ingreso "real": todo ingreso es **estimación en rango**, nunca un dato.

## Entrada de hipótesis

Una sola puerta de entrada: la tabla `niche_hypotheses`. Otros subproyectos escriben ahí con
su propio `origin` (C: `lead`; A: `marketplace`); B solo mide.

Comando `subniche add <entrada>`, con cuatro tipos de entrada:

- **Consulta** (`"history revenge"`): crea la hipótesis con esa consulta y 1 o 2 variantes.
- **Video** (URL de YouTube): resuelve el video con la API (1 unidad), toma título,
  descripción y canal.
- **Canal** (URL o `@handle`): resuelve el canal (1 a 2 unidades) y toma los títulos de sus
  últimos videos. El canal se guarda como **canal semilla**.
- **Tweet** (URL de X; llega con el subproyecto C): lee texto e imagen, extrae el canal y
  sigue como canal.

Flujo y estados: `propuesta` → `activa` → `pausada` | `archivada`.

1. El comando crea la hipótesis en `propuesta`. Un paso de **LLM** (Anthropic, ver abajo)
   propone `slug`, `label`, `family`, `parent_niche` y 2 a 3 consultas en inglés a partir del
   texto resuelto. La salida del LLM solo *propone*; el texto de YouTube o de X es dato no
   confiable y nunca se ejecuta ni se obedece.
2. El comando muestra la propuesta. El propietario la corrige o la aprueba
   (`subniche approve <slug>`); solo entonces pasa a `activa` y gasta cuota.
3. Se rechazan duplicados (misma consulta normalizada o mismo canal semilla ya asignado).

**Canal semilla:** un canal aportado por el propietario o por una pista. Se mide siempre en
la hipótesis, aparezca o no en la búsqueda, y queda marcado `semilla` en el perfil.

**Archivo versionado:** la fuente de verdad es la base de datos. Cada aprobación o pausa
exporta la lista a `config/subniche_hypotheses.yaml` en el repositorio para revisarla como
diff. El archivo es una exportación; editarlo a mano no cambia nada (v1).

**Consultas:** 2 a 3 por hipótesis (cada una cuesta 200 unidades con 2 páginas); una literal
y una de intención; sin términos tan generales que traigan todo el nicho padre.

## Arquitectura

Paquete nuevo `src/nicheradar/subniche_discovery/`, con tablas, estados y entrada de worker
propios. No modifica el marketplace ni el radar. Reutiliza la pasarela de YouTube
(`integrations/youtube.py`), su política, topes y libro de cuotas.

Unidades (una responsabilidad cada una):

1. **hypotheses**: alta, estados y comando `subniche` (ver "Entrada de hipótesis"). Interfaz
   de entrada única, que usarán C y A.
1b. **propose**: paso de LLM que convierte el texto resuelto en una propuesta de hipótesis.
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

## Flujo de medición (etapas)

`buscar` → `canales` → `videos recientes` → `estimar` → `puntuar` → `informe`.

**Cadencia:** una corrida cada 3 días. Cada corrida procesa (a) las hipótesis aprobadas desde
la última corrida (una idea espera 3 días como máximo) y (b) las **finalistas** (marca
`finalista`, que pone el propietario) cuya última medición tenga más de 7 días. Las demás se
quedan con su medición inicial; `subniche measure <slug>` fuerza una nueva. Las ventanas de
90 días cambian despacio, así que refrescar todo cada 3 días añade poca señal y multiplica el
gasto de cuota.

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
  `status` (`proposed|active|paused|archived`), `finalist` bool, `source_input` (texto de la
  entrada original), `created_at`, `approved_at`, `last_measured_at`.
- `hypothesis_seed_channels` — `hypothesis_id`, `channel_id`, `added_at`.
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

## Proveedor y gasto de LLM

El paso `propose` usa la **API de Anthropic** (Messages), con **Sonnet 5.5**: la tarea pide
criterio sobre el nicho y el volumen es de decenas de llamadas. Se añade una operación
nueva a la pasarela (`HYPOTHESIS_PROPOSAL`), un contrato de salida estricto con parser
tolerante y tarifa verificada en la página de precios de Anthropic antes de programar (igual
que el procedimiento actual de `gpt-6-luna`). El adaptador de OpenAI no se toca.

- **Credencial:** `NR_ANTHROPIC_API_KEY`, aparte de `NR_LLM_API_KEY`. Vive en el `.env` local
  privado y una acción de `scripts/easypanel_stage.mjs` la copia al servicio **worker**.
  Backend y dashboard no la reciben.
- **Sin topes en dólares por ahora:** el libro de cuentas ya registra el costo real por
  llamada. Se añade un informe de gasto por operación y modelo (script de solo lectura). La
  pasarela lleva un límite no restrictivo solo para funcionar. Los topes se fijan tras la
  primera prueba con datos reales. Como cada propuesta la dispara un comando del
  propietario, el riesgo de un bucle de gasto es bajo.
- **Fase 2 (fuera de este spec):** migrar a Anthropic la clasificación de fichas y el
  emparejamiento de nichos (candidato: Haiku 5.5) y la lectura de capturas (Haiku 5.5 a
  prueba, Sonnet 5.5 si falla), con comparación contra la muestra ya leída.
- **Subproyecto C:** la lectura de tweets e imágenes usará el mismo adaptador (Sonnet 5.5).

## Cuota y coste

search.list = 100 unidades; `channels.list`/`videos.list`/`playlistItems` = 1 por llamada
(≤50 ids). Corrida inicial de ~60 hipótesis × 2 consultas × 2 páginas = 24.000 unidades de
búsqueda, más ~1.500 de detalle: **~22.000 a 26.000 unidades repartidas en 3 días** (el
límite diario de la API es 10.000). Con refresco solo de finalistas, el régimen posterior es de
~2.000 a 4.000 unidades por semana (5 a 10 finalistas) más ~400 a 600 por cada hipótesis
nueva aprobada.

Acciones necesarias (las ejecuta el propietario, como el resto de los despliegues):

- Subir `youtube_search_quota_per_run/week/month` a valores que cubran la corrida (cada
  campo tiene tope máximo en `config.py`; `per_week` admite hasta 100.000).
- Añadir un tope diario nuevo (`subniche_daily_units`, defecto 9.000) para no agotar el
  límite diario de la API que comparten las demás etapas.
- Coste de modelo: solo el paso `propose`, centavos por propuesta. Sin vidIQ.

## Errores y casos límite

- Tope de cuota o 403 `quotaExceeded`: la etapa termina `partial`, la siguiente corrida
  continúa. Nunca reintenta en bucle.
- Consulta sin resultados: la hipótesis queda con perfil vacío (`sin_senal`), no falla.
- Canal eliminado o privado entre etapas: se descarta con motivo registrado.
- Hipótesis duplicadas (misma consulta normalizada): el alta las rechaza.
- Resultados con idioma no inglés: se descartan y se cuentan (`excluidos_idioma`).

## Pruebas

- Comando `subniche`: parseo de los cuatro tipos de entrada, estados y transiciones, rechazo
  de duplicados, exportación al YAML.
- `propose`: contrato de salida y parser tolerante con respuestas simuladas del LLM,
  incluido texto de entrada con instrucciones hostiles (debe tratarse como dato).
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
- **Calidad de la propuesta del LLM:** puede inventar una familia o un nicho padre
  inadecuado. Mitigación: estado `propuesta` con aprobación del propietario antes de gastar
  cuota; el RPM heredado queda marcado como tal.
- **Segundo proveedor de LLM:** durante la fase 1 conviven OpenAI y Anthropic, con
  credenciales, tarifas y topes por separado. Se documenta en el informe de gasto.
- **Cupo real de `search.list` por verificar:** `docs/channel-analysis.md` registra que
  `search.list` tiene un cupo propio ("Search Queries per day = 100" en Google Cloud Console),
  distinto del pool de 10.000/día. Este spec asumió 100 unidades por búsqueda contra ese pool
  (≈100 búsquedas al día). Si el cupo real es 1 búsqueda al día, la corrida inicial es inviable
  y hay que rediseñarla. El propietario verifica el límite y el uso en la consola antes de
  subir `subniche_search_units_per_day` (defecto conservador: 100). Ver el plan.
- **Cuota compartida:** una corrida grande puede dejar sin cuota al análisis de canales;
  se mitiga con el tope diario y ejecutando de noche.
- **Términos de la API:** retención de 30 días de datos de API; se cumple con la poda.

## Fases de entrega

1. Núcleo: parámetros de búsqueda, tablas, estimación pura, etapas y cuota (con tests).
2. Comando `subniche` con el paso `propose` (adaptador Anthropic, tarifa, informe de gasto) e
   informe de solo lectura; lista inicial de hipótesis para revisión.
3. Corrida inicial en producción (acciones del propietario) y primera lectura de resultados.
4. Página en el dashboard (después, solo si el informe resulta útil).

## Preguntas abiertas

Ninguna que bloquee el plan. Pendiente de verificar antes de programar: la tarifa vigente de
Sonnet 5.5 en la página de precios de Anthropic. Se decide al implementar, con test: valores exactos del
umbral `outlier_ratio` (partir en 5) y de "visitas de 28 días muy por encima" (partir en
2× el ritmo de 90 días).
