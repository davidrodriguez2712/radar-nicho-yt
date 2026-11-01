# Etapa 07: Publicación, programación y analítica

Fecha de consulta: 2026-11-01. Todo dato `web` caduca a 90 días (2027-01-30). Las páginas se leyeron con WebFetch (un modelo pequeño resume la página, así que las citas literales son del resumen y no de la página completa; las páginas largas se leyeron truncadas). No se instaló nada, no se creó ninguna cuenta ni proyecto de Google Cloud, y no se subió ningún video.

Tipos de dato: **medido**, **web** (URL y fecha), **tercero**, **supuesto**.

---

## 1. Resumen y recomendación

### Hallazgos que cambian el plan

1. **Los umbrales de monetización de un canal nuevo cambian el 2027-02-01.** Dos fuentes oficiales de YouTube dicen cosas distintas y hay que leerlas juntas:
   - La página de ayuda de elegibilidad al YPP sigue mostrando 1.000 suscriptores + 4.000 horas públicas de los últimos 12 meses (o 10 millones de vistas de Shorts en 90 días). Solo agrega el aviso "Starting February 1, 2027, we are introducing updates to the YouTube Partner Program" y pide aceptar los términos nuevos en Studio antes del 2027-01-31. No menciona 8.000 horas. (web, https://support.google.com/youtube/answer/72851, consultada 2026-11-01; sin fecha de actualización visible, solo "©2026 Google").
   - El anuncio en el blog de Google (fecha 11 de agosto de 2026) dice que los solicitantes nuevos necesitarán "8,000 qualified watch hours in the last 365 days, or 20M qualified Shorts views in the last 90 days", más 1.000 suscriptores; y que "This update won't impact creators already in YPP". (web, https://blog.google/intl/en-mena/product-updates/connect-communicate/new-opportunities-to-earn-and-changes-to-the-youtube-partner-program/, consultada 2026-11-01.) Es el blog de la región MENA; no encontré la misma entrada en el blog global.
   - Por tanto el "8.000 horas desde 2027-02-01" del informe **está respaldado por el blog oficial de Google, no por la página de ayuda**. El umbral aplica a solicitantes nuevos; quien ya esté en el YPP no se ve afectado.
   - Resumen de NewsShooter (tercero que cita el anuncio, https://www.newsshooter.com/2026/08/10/youtube-updates-its-partner-program/, 2026-11-01): fan funding, Creator Partnerships y Shopping se mantienen en 500 suscriptores + 3.000 horas (o 3 millones de vistas de Shorts); el reparto de Shorts exige 10 millones de vistas en 90 días solo para quien ya cobra por Shorts.
   - **Consecuencia para NicheRadar**: un canal que aún no existe no puede juntar 4.000 horas antes del 2027-02-01 (quedan 3 meses). Hay que planificar el hito de monetización con **8.000 horas + 1.000 suscriptores** (supuesto de planificación prudente). A 22 min por video, 8.000 h son 21.800 reproducciones completas equivalentes; con retención media del 40 % son unas 54.500 vistas. Es un cálculo mío (supuesto), no una estadística de YouTube.
2. **La cuota de subida cambió y ahora es muy holgada.** Desde 2026-06-01 `videos.insert` tiene su propio cubo: **100 llamadas/día a 1 unidad**; `search.list` otro cubo de 100/día; el resto comparte 10.000 unidades/día. Antes de 2025-12-04 una subida costaba ~1.600 unidades. (web, https://developers.google.com/youtube/v3/determine_quota_cost y https://developers.google.com/youtube/v3/revision_history, 2026-11-01.) Para 1 a 3 videos por semana la cuota no es un límite.
3. **Contradicción sin resolver sobre el bloqueo a "privado" de proyectos no verificados.**
   - Las páginas actuales de `videos` y `videos.insert` dicen textualmente: "Videos uploaded from unverified API projects are not restricted to private viewing mode." (web, https://developers.google.com/youtube/v3/docs/videos/insert, 2026-11-01).
   - El historial de revisiones conserva la entrada de 2020-07-28 que imponía el bloqueo (web, https://developers.google.com/youtube/v3/revision_history), y la ayuda de Studio sigue diciendo que un video "locked" por subirse con un servicio de API no verificado no se puede apelar y hay que re-subirlo desde un servicio verificado o desde la web (web, https://support.google.com/youtube/answer/7300965, 2026-11-01).
   - Lo más probable es que la restricción se haya retirado en la documentación de desarrolladores y la página de ayuda esté desactualizada, pero **no está verificado**. Experimento barato en la sección 5.
4. **La API de Analytics no expone impresiones ni CTR en las páginas leídas; la API de Reporting sí** (reportes `channel_reach_basic_a1` con `video_thumbnail_impressions` y `video_thumbnail_impressions_ctr`). (web, https://developers.google.com/youtube/reporting/v1/reports/channel_reports, 2026-11-01.) La página de métricas de Analytics no lista `videoThumbnailImpressions` (web, https://developers.google.com/youtube/analytics/metrics; la página se leyó truncada, así que "no aparece" es "no lo vi"). Esto concuerda con lo medido por el propietario: la columna de impresiones del CSV de Studio salió vacía con pocas vistas (medido, `stacks/thumbnails-packaging.md`).

### Tabla de decisión

| Nivel | Recomendación | Por qué | Minutos humanos por video |
|---|---|---|---|
| A: gratis y local | Script propio en Python (`google-api-python-client`, OAuth de escritorio con `youtube.upload` y `youtube.readonly`/`yt-analytics.readonly`) que sube **privado + `publishAt`**, pone miniatura, capítulos, lista de reproducción y "AI use"; más YouTube Studio para Test & Compare y revisión final | 0 USD, cuota sobrada, corre en macOS (Python puro). Studio hace lo que la API no hace (Test & Compare es solo escritorio en Studio) | 5 a 10 (supuesto): revisar video privado en Studio, confirmar la programación, mirar el reporte semanal |
| B: gratis con límites / bajo costo | Lo mismo que A + **vidIQ gratis** (150 créditos de IA/mes) o **Metricool gratis** (1 marca, 20 posts/mes) solo como extras | Aportan ideas o calendario multired, no la publicación de YouTube larga | +0 a 5 |
| C: pago | **vidIQ Boost 19 USD/mes** o **TubeBuddy Pro/Legend** | Solo si se prueba que mueven CTR; no son necesarios para publicar ni medir | +5 a 10 (supuesto) |

**Qué automatiza la etapa**: subida, metadatos, programación, miniatura, capítulos, lista de reproducción, divulgación de contenido sintético, y descarga de métricas. **No automatizable** (decisión humana): la revisión de que el video no es contenido inauténtico, la respuesta a comentarios y la lectura del Test & Compare. **Cuenta 5 a 10 minutos humanos por video** para esta etapa (supuesto: no medido todavía).

---

## 2. Catálogo de candidatos

Costo en dinero / tiempo de máquina / minutos humanos van por separado. Tiempo de máquina de subida: depende de la red, un archivo de ~1-3 GB tarda minutos de subida resumable (supuesto, no medido).

| # | Herramienta | Tipo | Dinero | Tiempo de máquina | Min. humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **YouTube Data API v3** (`videos.insert`, `thumbnails.set`, `playlistItems.insert`, `videos.update`) | API | 0 USD. Cuota por defecto: 100 `videos.insert`/día (1 unidad) + 10.000 unidades/día resto; `thumbnails.set` 50, `playlistItems.insert` 50, `videos.update` 50, `captions.insert` 400 | Minutos de subida (supuesto) | 2 a 5 una vez montado (supuesto) | Sujeto a YouTube API Services Terms y Developer Policies; cuotas extra solo tras auditoría | Sí, es HTTP (cualquier cliente) | Resumible, reintentos recomendados con backoff en 500/502/503/504 | Metadatos multi-idioma | web, https://developers.google.com/youtube/v3/determine_quota_cost y https://developers.google.com/youtube/v3/guides/uploading_a_video, 2026-11-01 |
| 2 | **google-api-python-client + google-auth-oauthlib** | Librería Python | 0 USD | n/a | n/a | No verifiqué la licencia en esta investigación (el ejemplo oficial lo usa). Marca: licencia **no verificada** | Sí (Python puro) | El ejemplo oficial es antiguo ("Python 2.5 o superior" en la página) pero la librería sigue vigente | n/a | web, https://developers.google.com/youtube/v3/guides/uploading_a_video, 2026-11-01 |
| 3 | **YouTube Studio** (programación, Test & Compare, "AI use", capítulos) | Servicio | 0 USD | n/a | 3 a 8 si es manual | Términos de YouTube | Navegador | Test & Compare: hasta 3 títulos o miniaturas, gana por **tiempo de visualización** (no CTR), solo escritorio, termina en ~2 semanas, no sirve para Shorts, Premieres ni videos para niños; cambiar título/miniatura durante la prueba la detiene | n/a | web, https://support.google.com/youtube/answer/13861714, 2026-11-01 |
| 4 | **YouTube Analytics API** (`reports.query`) | API | 0 USD | Segundos | 0 una vez automatizado | Términos de la API | Sí (HTTP) | Tiene `views`, `estimatedMinutesWatched`, `averageViewDuration`, `averageViewPercentage`, `subscribersGained`; retención con `elapsedVideoTimeRatio` + `audienceWatchRatio`/`relativeRetentionPerformance` (un solo video por consulta); ingresos con `yt-analytics-monetary.readonly`. Impresiones y CTR no figuran en lo leído. Cuota de Analytics: **no verificada** | n/a | web, https://developers.google.com/youtube/analytics/channel_reports y https://developers.google.com/youtube/analytics/metrics, 2026-11-01 |
| 5 | **YouTube Reporting API** (reportes masivos) | API | 0 USD | Los reportes se generan por lotes; disponibilidad y retención de datos **no verificadas** | 0 una vez montado | Términos de la API | Sí | `channel_reach_basic_a1`: impresiones y CTR por video/día; `channel_basic_a3`: vistas, `watch_time_minutes`, `subscribers_gained`. No hay informe de retención dedicado (solo duración media y porcentaje medio) | n/a | web, https://developers.google.com/youtube/reporting/v1/reports/channel_reports, 2026-11-01 |
| 6 | **CSV de YouTube Studio** (importación manual) | Manual | 0 USD | n/a | 2 a 3 (supuesto) | n/a | Navegador | Es lo que el propietario ya usa (`importar-ctr`); con pocas vistas la columna de impresiones salió vacía | n/a | medido, `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md` |
| 7 | **vidIQ** | Servicio / extensión | Gratis: 0 USD con 150 créditos IA/mes. Boost 19 USD/mes (199/año). MAX 49 USD/mes (468/año) | n/a | 5 a 10 si se usa | Términos comerciales de vidIQ (no revisados); no sube videos | Navegador | Ideas, tendencias, coach IA; trae un servidor MCP en todos los planes que consume créditos. No es publicador | Inglés principalmente (supuesto) | web, https://vidiq.com/pricing/, 2026-11-01 |
| 8 | **TubeBuddy** | Servicio / extensión | La página no mostró precios ni los límites del plan gratis (marcadores vacíos). Planes Pro, Star, Legend; 20 % de descuento anual; 50 % con el cupón RisingStarBuddy si <1.000 suscriptores. **Precio no verificado** | n/a | 5 a 10 si se usa | No disponible para canales de más de 50.000 suscriptores ni empresas; licencia por canal | Navegador | Legend trae pruebas A/B y seguimiento de ranking; las pruebas A/B ya existen gratis en Studio | n/a | web, https://www.tubebuddy.com/pricing, 2026-11-01 |
| 9 | **Metricool** | Servicio | Gratis: 1 marca, 20 posts programados/mes, 30 días de analítica, 5 competidores. Starter desde 20 USD/mes (anual) o 25 (mensual) | n/a | 3 a 5 | Términos de Metricool (no revisados) | Navegador | Programador multired con YouTube; si programa video largo vía API de YouTube **no se verificó** (la página no lo dice) | n/a | web, https://metricool.com/pricing/, 2026-11-01 |
| 10 | **Buffer** | Servicio | Gratis: 3 canales, 10 posts programados por canal. Essentials 5 USD/canal/mes, Team 10 USD | n/a | 3 a 5 | Términos de Buffer (no revisados) | Navegador | **Solo YouTube Shorts**: su ayuda dice que no soporta videos largos (reporte de búsqueda sobre el artículo oficial de Buffer; la página oficial en sí no se abrió) | n/a | web, https://buffer.com/pricing y https://support.buffer.com/article/562-using-youtube-shorts-with-buffer, 2026-11-01 |
| 11 | **Script propio de automatización** (cron/launchd + Python, o Claude Code) | Local | 0 USD | Segundos de CPU más red | 1 a 2 | Código propio | Sí | Hay que mantener el OAuth y los tokens (ver riesgos) | n/a | supuesto |

Notas de cada fila sobre Buffer: la fila dice "reporte" porque la lectura vino de un resumen de búsqueda; marcada como `tercero` hasta abrir el artículo.

---

## 3. Fichas de las herramientas recomendadas

### Script propio sobre la YouTube Data API (nivel A)

- **Qué es**: un programa local que sube el MP4 con subida resumable y rellena `snippet` (título, descripción con capítulos, idioma), `status` (`privacyStatus: private`, `publishAt` ISO 8601, `selfDeclaredMadeForKids`, `containsSyntheticMedia`) y luego llama a `thumbnails.set` y `playlistItems.insert`.
- **Reglas verificadas**:
  - `publishAt` solo se puede fijar si el video está `private`; al actualizar hay que reenviar `privacyStatus: private`; una hora pasada publica de inmediato. (web, https://developers.google.com/youtube/v3/docs/videos, 2026-11-01.)
  - Si se omite `privacyStatus`, el video sale público por defecto (algunas cuentas privado). Subir siempre con el campo explícito. (misma fuente.)
  - `containsSyntheticMedia` existe en `videos.insert` y `videos.update` (entrada del historial del 2024-10-30). (web, https://developers.google.com/youtube/v3/revision_history.)
  - Miniatura: máximo 50 MB desde 2026-09-14, JPEG o PNG, 50 unidades. (web, https://developers.google.com/youtube/v3/docs/thumbnails/set y revision_history.) Ojo: la API devuelve 403 si la cuenta no tiene permiso de miniaturas personalizadas; el requisito de verificación del canal **no aparece en esa página**, sí suele exigirlo Studio (no verificado aquí).
  - Capítulos: lista de marcas de tiempo en la descripción; la primera en 00:00, mínimo 3, cada capítulo de al menos 10 s; sustituyen a los automáticos. Son texto, así que se generan desde el guion sin API aparte. (web, https://support.google.com/youtube/answer/9884579, 2026-11-01.)
  - Presupuesto de cuota por video (web + cálculo): insert 1 (cubo propio) + miniatura 50 + lista 50 + update 50 = ~150 unidades del cubo de 10.000; con subtítulos propios (`captions.insert`, 400) ~550. Sobra para decenas de videos por día.
- **OAuth**: alcance `https://www.googleapis.com/auth/youtube.upload` para subir (permite subir al canal y nada más). (web, guía de subida.) Un proyecto de Google Cloud con tipo de usuario externo y estado "Testing" recibe un refresh token que **caduca a los 7 días** (web, https://developers.google.com/identity/protocols/oauth2, 2026-11-01). Para un script desatendido hay que dejar la app en estado de producción (con pantalla de "app no verificada" para uno mismo) o aceptar re-autorizar cada semana. El límite de 100 usuarios de prueba y la necesidad de verificación para un solo usuario propietario **no se verificaron** (la página leída no los menciona).
- **Riesgos**: el bloqueo a privado (hallazgo 3), tokens caducados que dejan la programación sin ejecutarse, y subir con "No" en AI use un video con voz sintética realista de otra persona.

### YouTube Studio: Test & Compare y revisión (nivel A)

Sin API. Se usa con el video ya subido; 3 minutos humanos para iniciar la prueba. Con un canal pequeño habrá pocas impresiones, así que las pruebas pueden quedar "Inconclusive" (supuesto razonado a partir de la regla de que termina por impresiones; el propietario midió que con pocas vistas el CTR es ruidoso: medido, stack de miniaturas).

### YouTube Analytics API + Reporting API (nivel A)

- **Retención y duración**: `reports.query` con `dimensions=elapsedVideoTimeRatio`, filtro `video==ID`, métricas `audienceWatchRatio` y `relativeRetentionPerformance`. Una consulta por video.
- **Horas de reproducción y suscriptores** para los hitos del YPP: `estimatedMinutesWatched` / 60 y `subscribersGained` por día. Ojo: las "horas calificadas" del YPP no tienen por qué coincidir con las horas totales de la API (por ejemplo, las horas del feed de Shorts no cuentan para las 4.000: web, página de elegibilidad); la comprobación oficial es la pestaña de monetización de Studio.
- **Impresiones y CTR**: `channel_reach_basic_a1` en la API de Reporting (hay que crear un "reporting job" y esperar a que se generen los lotes; el retraso no se verificó).
- **Ingresos**: `estimatedRevenue` requiere el alcance `yt-analytics-monetary.readonly` y se ajusta a fin de mes. (web, métricas de Analytics.)

### vidIQ gratis o Metricool gratis (nivel B, opcional)

- vidIQ gratis: ideas de contenido y coach de IA con 150 créditos al mes; no publica ni reemplaza el script. Su MCP puede integrarse con agentes pero cada llamada gasta créditos.
- Metricool gratis: calendario para 1 marca y 20 posts/mes; sirve si algún día se reparte el contenido en otras redes. No se recomienda para la publicación larga de YouTube hasta comprobar que programa videos largos.

---

## 4. Riesgos de política y de derechos

- **Contenido inauténtico (YPP)**: la política renombrada el 2025-07-15 excluye contenido "mass-produced, generic, repetitive" y menciona expresamente "AI-generated content built on generic or unoriginal templates", presentaciones de imágenes y texto con poca narrativa. Permite mismas intro/outro y series con historias distintas. (web, https://support.google.com/youtube/answer/1311392, 2026-11-01.) Un canal "sin rostro" con narración de IA y imágenes generadas es exactamente el perfil que se revisa al pedir la monetización; automatizar la **publicación** no es el riesgo, automatizar la **originalidad** sí. Esto exige una revisión humana mínima de cada video.
- **Divulgación de contenido alterado o sintético**: se exige para contenido realista (persona real diciendo algo que no dijo, evento o lugar real alterado, escena realista que no ocurrió, música como foco). **No** se exige para: guion, esquema, miniatura, título o infografía asistidos por IA; animación o escenas irreales; mejoras técnicas de audio; clonar la propia voz para locuciones. Se marca en Studio, sección Atributos, "AI use", o con `status.containsSyntheticMedia` por API. (web, https://support.google.com/youtube/answer/14328491, 2026-11-01.) Una narración con voz sintética genérica no suplanta a una persona real, por lo que normalmente no requiere el sí; imágenes fotorrealistas de **eventos históricos o personas reales** sí lo requieren. Decisión por video, hecha por el humano.
- **Cuota y auditoría**: pedir más cuota exige una auditoría de cumplimiento; no es necesario con el uso previsto (web, https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
- **Términos 2027**: hay que aceptar los módulos nuevos de monetización en Studio antes del 2027-01-31 o se pierden ingresos de esas funciones desde 2027-02-01 (web, página de elegibilidad; NewsShooter, tercero). Aplica a cuentas ya en el YPP.
- **Programación y bots**: no encontré una regla oficial que prohíba programar con API; el riesgo es de abuso de cuota, no aplica a este volumen.
- **Terceros**: vidIQ y TubeBuddy exigen conectar el canal con OAuth; concede acceso a datos del canal (privacidad); no revisé sus términos.

---

## 5. Comparación con lo que ya mide el propietario y qué falta medir

- **Medido por el propietario** (`~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md`): un canal, 20 miniaturas, mediana de CTR 2,6 %, con CTR e impresiones importados desde CSV de Studio; la columna de impresiones salió vacía; no hay datos de subida, programación ni retención. No existe en el Foundry un stack de publicación (`stacks/` solo tiene `thumbnails-packaging.md` y `voice-narration.md`).
- **Experimentos baratos que puede correr** (todos sin gasto):
  1. **Probar el bloqueo a privado**: crear un proyecto de Google Cloud, habilitar la API, subir un video corto **privado** con el script y comprobar si Studio muestra el aviso de "locked". Responde el hallazgo 3 en 15 minutos. (No lo ejecuté: el brief prohíbe crear cuentas y proyectos.)
  2. **Medir la caducidad del token**: dejar la app en "Testing" y comprobar a los 8 días si el token falla; luego pasar a producción y repetir.
  3. **Reportes de alcance**: crear un job `channel_reach_basic_a1` y anotar cuántas horas tardan los primeros datos con el canal nuevo.
  4. **Retención real**: ejecutar `audienceWatchRatio` en el primer video y registrar el resultado en el Foundry como dato `medido`.
  5. **Horas calificadas frente a la API**: cada semana comparar `estimatedMinutesWatched/60` con el contador de Studio.
- **Minutos humanos de la etapa**: hoy no hay dato `medido`; las cifras de este documento son `supuesto` hasta cronometrar tres videos.

---

## 6. Unknowns y fuentes

### Unknowns

1. Si el bloqueo a privado de proyectos no verificados sigue activo (docs de desarrolladores dicen que no; la ayuda de Studio y el historial dicen que existió).
2. Si un proyecto externo en producción con el alcance `youtube.upload` necesita verificación de la app de Google para un único usuario propietario, y el límite de 100 usuarios; la página de OAuth leída no lo dice.
3. Cuota y límites de la YouTube Analytics API y retraso/retención de los reportes de la Reporting API.
4. Si el anuncio de 8.000 horas del blog MENA coincide con el blog global y con cómo se aplica a un canal que ya reúne 1.000 suscriptores y 4.000 horas antes del 2027-02-01 pero solicita después.
5. Precios y plan gratis de TubeBuddy (la página mostró marcadores vacíos); licencias y términos de vidIQ, TubeBuddy, Metricool y Buffer; si Metricool programa videos largos de YouTube.
6. Licencia de `google-api-python-client` y requisito de canal verificado para miniaturas personalizadas.

### Tabla de fuentes

| Fuente | URL | Acceso |
|---|---|---|
| Costos de cuota de la API | https://developers.google.com/youtube/v3/determine_quota_cost | 2026-11-01 |
| Historial de revisiones de la API | https://developers.google.com/youtube/v3/revision_history | 2026-11-01 |
| Recurso `videos` | https://developers.google.com/youtube/v3/docs/videos | 2026-11-01 |
| `videos.insert` | https://developers.google.com/youtube/v3/docs/videos/insert | 2026-11-01 |
| `thumbnails.set` | https://developers.google.com/youtube/v3/docs/thumbnails/set | 2026-11-01 |
| Guía de subida | https://developers.google.com/youtube/v3/guides/uploading_a_video | 2026-11-01 |
| Auditoría y cuota extra | https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits | 2026-11-01 |
| Formulario de auditoría | https://support.google.com/youtube/contact/yt_api_form | 2026-11-01 |
| Ayuda: videos bloqueados por API no verificada | https://support.google.com/youtube/answer/7300965 | 2026-11-01 |
| OAuth 2.0 de Google (caducidad de tokens) | https://developers.google.com/identity/protocols/oauth2 | 2026-11-01 |
| Elegibilidad al YPP | https://support.google.com/youtube/answer/72851 | 2026-11-01 |
| Anuncio de cambios al YPP (blog Google MENA, 2026-08-11) | https://blog.google/intl/en-mena/product-updates/connect-communicate/new-opportunities-to-earn-and-changes-to-the-youtube-partner-program/ | 2026-11-01 |
| NewsShooter (tercero) | https://www.newsshooter.com/2026/08/10/youtube-updates-its-partner-program/ | 2026-11-01 |
| Contenido inauténtico | https://support.google.com/youtube/answer/1311392 | 2026-11-01 |
| Divulgación de contenido alterado o sintético | https://support.google.com/youtube/answer/14328491 | 2026-11-01 |
| Test & Compare | https://support.google.com/youtube/answer/13861714 | 2026-11-01 |
| Capítulos | https://support.google.com/youtube/answer/9884579 | 2026-11-01 |
| Analytics API, informes de canal | https://developers.google.com/youtube/analytics/channel_reports | 2026-11-01 |
| Analytics API, métricas | https://developers.google.com/youtube/analytics/metrics | 2026-11-01 |
| Reporting API, informes de canal | https://developers.google.com/youtube/reporting/v1/reports/channel_reports | 2026-11-01 |
| vidIQ precios | https://vidiq.com/pricing/ | 2026-11-01 |
| TubeBuddy precios | https://www.tubebuddy.com/pricing | 2026-11-01 |
| Metricool precios | https://metricool.com/pricing/ | 2026-11-01 |
| Buffer precios | https://buffer.com/pricing | 2026-11-01 |
| Buffer: Shorts solo (vía búsqueda; artículo no abierto) | https://support.buffer.com/article/562-using-youtube-shorts-with-buffer | 2026-11-01 |
| Stack de miniaturas del propietario (medido) | `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md` | 2026-11-01 |
