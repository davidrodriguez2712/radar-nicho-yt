# Inteligencia de mercado: backlog de nichos desde marketplaces de canales — diseño

Estado: validado en conversación con el propietario el 2026-10-19. Pendiente de revisión
del archivo antes de pasar a `writing-plans`.

## Resumen

Paso previo a la inspección por URL o canal. Un proceso diario scrapea las fichas de
canales de YouTube en venta de un marketplace público (v1: DealBaron), las normaliza,
las clasifica en la taxonomía de nichos que ya usa el radar y construye un **backlog de
nichos priorizado** por oportunidad, con un **score de automatización** aparte y una
confianza explícita. El propietario marca nichos como tentativos o descartados; desde una
ficha puede saltar al análisis de canal existente.

Es un subsistema nuevo dentro del repo (enfoque "contexto separado en los mismos
servicios"): comparte Postgres, cola durable, LLM, YouTube API y dashboard, pero tiene
tablas, paquete, programación y pausa propias. No se mezcla con `opportunities`, que solo
contiene evidencia de vidIQ/YouTube.

## Objetivo de negocio

Responder, antes de gastar créditos en análisis profundos: **¿qué temáticas generan más
dinero y son accesibles para un entrante, y cuáles se pueden automatizar más?**
Éxito del v1:

1. Cada día se incorporan las fichas nuevas sin intervención y sin tocar el radar de vidIQ.
2. El backlog ordena nichos por Opportunity Score y expone Automation Score y confianza
   por separado.
3. Toda cifra declarada por vendedores está marcada `seller_declared`; las cifras
   verificadas contra YouTube se distinguen de ellas.
4. Nada gasta créditos de vidIQ ni crea canales de forma automática.

## Fuera de alcance (explícito)

- **Investigación de flujo** ("Iniciar investigación de flujo": roadmap, presupuesto,
  herramientas por fase, mapa de automatización). Es el **spec 2**; aquí solo queda el
  estado `tentativo` como punto de entrada.
- Fuentes adicionales (Flippa, Empire Flippers, FE International…). El v1 solo implementa
  DealBaron; el contrato de adaptador deja la puerta abierta sin tocar el scoring.
- Señales de demanda externas (Google Trends, Social Blade, RSS de YouTube): siguen
  descartadas por `docs/channel-analysis.md`.
- Distinguir "vendido" de "retirado": el marketplace solo muestra fichas activas.
- Benchmarks de RPM para Shorts: no existen; esas fichas quedan `uncalibrated`.

## Reglas heredadas que este diseño respeta

- No inventar métricas: campo ausente = `unknown`/`insufficient_evidence`/`uncalibrated`.
- Separar long y Shorts, sintético y real, evidencia externa y decisiones propias, score y
  confianza.
- Sin llamadas reales a proveedores desde pruebas.
- El arranque local es sintético y sin salida a Internet.
- No despausar el radar como efecto lateral; no gastar créditos ni elegir oportunidades
  automáticamente.

## Decisiones tomadas con el propietario

| Tema | Decisión |
|---|---|
| Partición | Spec 1 = fuentes + backlog con score. Investigación de flujo = spec 2 |
| Integración | Contexto separado en el mismo repo y servicios |
| Retención | 6 meses para fichas y observaciones (clase propia, distinta de los 7 días de proveedores) |
| Pausa | Interruptor propio del scraper; independiente de `NR_RADAR_PAUSED` |
| Fuentes v1 | Solo DealBaron, con adaptador por fuente y verificación cruzada con YouTube API |

## Arquitectura

Paquete `src/nicheradar/market_intel/`:

- `sources/base.py`: contrato `ListingSource` (`list_pages()`, `fetch_detail()`) que
  devuelve `NormalizedListing`.
- `sources/dealbaron.py`: único adaptador del v1. HTTP simple (las páginas son HTML
  renderizado en servidor; no se necesita navegador).
- `ingest.py`: upsert de fichas y observaciones, `reconcile`.
- `classify.py`: nicho, formato, idioma y banderas de automatización vía LLM.
- `scoring.py`: Opportunity Score, Automation Score y confianza, calculados al vuelo.
- `repositories` y migración `0013`; rutas en la API; módulo de dashboard propio
  (`dashboard.py` ya tiene ~1.450 líneas y no debe crecer).

El scraper se ejecuta como un tipo de job de la cola existente (`jobs`, lease, heartbeat,
reintentos, checkpoints), con `analysis_runs.trigger = "market_scrape"`, sin compartir
etapas ni estado con el pipeline de catálogo ni con `channel_analysis`.

### Programación y pausa

Una fila nueva en `radar_schedules` con `schedule_key = 'market_intel_scrape'`,
`interval_seconds = 86400` y `paused = true` por defecto. Su pausa es independiente de
`NR_RADAR_PAUSED`: el scraper es gratuito y no consume créditos de vidIQ. La migración y el
despliegue nunca la activan.

## Modelo de datos (migración `0013`, aditiva)

- `marketplace_listings`: fuente, id externo, URL, `first_seen_at`, `last_seen_at`,
  estado (`active` | `disappeared`), `channel_id` nullable (enlazado a `channels` tras
  resolver la URL del canal), `retain_until` (= `last_seen_at` + 6 meses).
- `listing_observations`: una fila por ficha y día visto. Precio, suscriptores, ingreso
  mensual, gasto mensual (todos nullable), categoría de la fuente, descripción recortada,
  marca `seller_declared`, `retain_until`.
- `listing_classifications`: `niche_label` (uno de los 218 del catálogo de RPM o
  `other:<texto>`), formato (`long`|`shorts`|`unknown`), idioma inferido o `unknown`,
  banderas de automatización, versión del prompt, costo del LLM. Versionada para poder
  reclasificar.
- `market_niche_snapshots`: agregados diarios por nicho (para tendencia); no guarda
  scores, que se calculan al vuelo.
- `market_niche_decisions`: decisión del propietario (`nuevo` | `tentativo` |
  `descartado`) con nota; separada de la evidencia.
- `retention.py` se extiende para purgar estas tablas al vencer `retain_until`.

## Flujo del scraper (etapas de la cola)

1. **`list`**: recorre las páginas del listado `/youtube` con pausa entre peticiones,
   User-Agent identificable y tope de páginas por corrida.
2. **`detail`**: descarga la ficha solo de fichas nuevas y de las que cambiaron de
   precio, para obtener URL del canal, gasto y descripción.
3. **`reconcile`**: las fichas activas que ya no aparecen pasan a `disappeared`. **Solo si
   el recorrido del listado terminó completo y sin errores**; un crawl parcial nunca
   cambia estados.
4. **`classify`**: una llamada LLM por ficha sin clasificar, reutilizando el patrón de
   `niche_match` de `integrations/llm.py` (lista cerrada de nichos, entrada tratada como
   dato no confiable, salida estructurada).
5. **`verify`**: `channels.list` de YouTube, solo para el top del backlog, para contrastar
   suscriptores declarados con reales (≤ 1 unidad cada 50 canales).

Idempotencia: `occurrence_key = market_scrape:AAAA-MM-DD`.

## Clasificación

- Entrada: título, categoría de DealBaron (taxonomía gruesa de ~15 etiquetas) y
  descripción.
- Salida: `niche_label`, formato, idioma y banderas de automatización.
- Si el LLM responde `ninguno`, se guarda `other:<texto>`; la ficha entra al backlog con
  RPM `uncalibrated`.
- Shorts: sin benchmark de RPM, se puntúan aparte y `uncalibrated`.

## Automation Score (0-100)

El LLM solo etiqueta rasgos (nivel 0-2); una fórmula determinista, versionada y
configurable calcula el número.

| Rasgo | Peso |
|---|---|
| Sin presencia en cámara (faceless) | 30 |
| Guion generable por LLM desde fuentes públicas | 25 |
| Visuales automatizables (stock, imágenes IA, diapositivas) | 20 |
| Voz sintética aceptable | 15 |
| Baja dependencia de material con copyright | 10 |

- Prior por nicho: cada uno de los 218 nichos se etiqueta una vez y queda cacheado.
- Ajuste por ficha con evidencia de la descripción del vendedor (`seller_declared`).
- `policy_risk` (riesgo de desmonetización por contenido masivo o "inauthentic content") se
  muestra como columna aparte, nunca restado del score. Su análisis detallado pertenece
  al spec 2.
- Los pesos son un punto de partida; viven en configuración versionada que el propietario
  puede ajustar.

## Opportunity Score por nicho (0-100)

Unidad del backlog = `niche_label`, agregado sobre una ventana de 90 días. Se calcula al
vuelo desde las observaciones (mismo criterio que `channel_analysis_scoring.py`).

| Bloque | Peso | Métricas |
|---|---|---|
| Rentabilidad | 30 | Mediana de ingreso mensual; mediana de margen (ingreso − gasto) |
| Eficiencia | 30 | Ingreso por 1.000 suscriptores; RPM benchmark del nicho (solo long) |
| Validación de mercado | 25 | Múltiplo precio / (ingreso × 12); nº de fichas activas |
| Dinámica | 15 | Tasa de desaparición de fichas (señal débil) |

- Plausibilidad: recorte de atípicos con MAD dentro del nicho y contraste de
  suscriptores con YouTube para el top.
- **Confianza** (alta/media/baja) por separado, según nº de fichas con ingreso declarado,
  % verificado y antigüedad. Con menos de 3 fichas con ingreso, el nicho es
  `insufficient_evidence` y no se ordena junto a los demás.
- Orden por defecto: Opportunity Score. Orden alternativo y filtro por Automation Score.

## API (mismo Bearer del resto)

- `GET /api/v1/market/niches`, `GET /api/v1/market/niches/{label}`
- `GET /api/v1/market/listings`
- `GET /api/v1/market/runs`
- `POST /api/v1/market/niches/{label}/decisions`
- Control de pausa/reanudación de la programación del scraper.

## Dashboard (módulo nuevo)

- Pestaña **"Mercado"**: tabla del backlog (nicho, Opportunity, Automation, confianza,
  nº de fichas, ingreso mediano, múltiplo, tendencia).
- Detalle de nicho: fichas con datos declarados frente a verificados, serie histórica y
  evidencia; decisión `nuevo`/`tentativo`/`descartado` con nota.
- Cada ficha tiene un enlace **"Analizar canal"** que rellena el formulario de análisis de
  canal existente. No lanza nada por sí solo: el gasto de vidIQ sigue siendo manual.
- **Operación**: interruptor propio del scraper, última corrida, errores de parseo.

## Manejo de errores

- 403/429: backoff y corte con estado `blocked`; sin rotación de IP ni disfraz de cliente.
  La fuente queda en pausa visible en Operación.
- Cambio de layout: si más de un umbral de tarjetas de una página no se parsea, la
  corrida falla con `layout_changed`. Una ficha suelta con error queda `parse_error`.
- Tope del LLM alcanzado: fichas `unclassified`, se retoman al día siguiente. Comparte el
  tope semanal de US$5 y no afecta al flujo de vidIQ.
- YouTube sin cuota: se omite `verify` y baja la confianza.
- Cortesía: solo páginas públicas, sin login, ~1 petición/s, tope de páginas por corrida.

## Pruebas

- Fixtures HTML guardados una vez: listado, ficha completa, ficha sin ingreso, layout
  roto. Ninguna prueba toca la red.
- Unitarias: parser, normalización numérica ("81 000", "$ 1 990"), `reconcile`, fórmulas
  de ambos scores con valores de referencia, recorte MAD, cifras no verificadas que no
  inflan el score.
- Integración con Postgres temporal: migración `0013`, idempotencia del job, purga a 6
  meses, interruptor propio funcionando con el radar pausado sin despausarlo.
- API y dashboard: contratos, autenticación, navegación.
- LLM simulado con transporte falso. Cierre con `ruff`, `mypy` y suite completa.

## Despliegue

- Migración aditiva; la fila `market_intel_scrape` nace pausada.
- Modo sintético: la fuente usa fixtures; el arranque local no sale a Internet.
- Live: un piloto manual acotado (tope de páginas) documentado en
  `docs/market-intel-pilot.md`; después, activación de la programación diaria.
- Despliegue por digest en Easypanel; comprobar al final que el radar sigue pausado.
- Documentación nueva `docs/market-intel.md`; índices de `README.md` y `AGENTS.md`
  actualizados.

## Compuerta antes de activar en live (decisión del propietario)

Revisar los Términos de Servicio de DealBaron. Solo se verificó `robots.txt` (permite todo,
`Disallow:` vacío). No se activa el scraper en live sin esa revisión.

## Suposiciones

- Las páginas de listado y ficha de DealBaron mantienen la estructura observada el
  2026-10-03 (tarjetas `post__*`, ficha con suscriptores/ingreso/gasto/precio).
- Los pesos de los scores son iniciales y se calibrarán con datos reales del piloto.
- El LLM actual (`gpt-6-luna`) rinde suficiente para clasificar fichas; si no, se evalúa
  en el piloto.
- El registro de este trabajo como cambio OpenSpec propio (en vez de ampliar
  `continuous-niche-discovery`) se decide en la etapa de plan.

## Riesgos

- Datos autodeclarados y poco fiables: mitigado con recorte de atípicos, verificación y
  confianza explícita, pero no eliminado.
- Dependencia de una sola fuente en el v1.
- Posible bloqueo o cambio de layout de DealBaron.
- "Desaparecida" no equivale a "vendida": la señal de dinámica es débil y pesa 15.
