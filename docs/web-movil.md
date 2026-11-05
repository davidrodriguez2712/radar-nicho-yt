# Web móvil de NicheRadar

Interfaz móvil (FastAPI + Jinja2 + HTMX, paquete `src/nicheradar/web/`) que reemplaza al dashboard de
Streamlit en el mismo dominio. Habla con la API privada igual que el dashboard; no accede a la base.

## Variables

| Variable | Uso |
|---|---|
| `NR_DASHBOARD_UI` | `streamlit` (por defecto) o `web`. Elige qué interfaz sirve la imagen del dashboard |
| `NR_API_URL`, `NR_SERVICE_TOKEN`, `NR_DASHBOARD_PASSWORD` | Las mismas que usa el dashboard |

## Cambiar y volver atrás

Cambiar: fijar `NR_DASHBOARD_UI=web` en la app del dashboard y reiniciarla. Volver atrás: quitar la
variable (o ponerla en `streamlit`) y reiniciar, o desplegar la imagen anterior. No hay migraciones ni
datos propios, así que el retroceso no pierde nada. El cambio en producción requiere la aprobación del propietario.

## Sesión y seguridad

- Cookie firmada de 5 días, con la clave derivada del token de servicio.
- CSRF en todos los formularios `POST`; límite de intentos de acceso (una sola clave, la app es de un propietario).
- CSP sin recursos externos; las páginas con datos llevan `Cache-Control: no-store`.
- Salir solo borra la cookie: las sesiones no se pueden revocar en el servidor, así que una cookie copiada sigue válida hasta 5 días. Rotar `NR_SERVICE_TOKEN` invalida todas las sesiones.
- Sin Basic Auth en el proxy, la contraseña de la app debe ser aleatoria y de al menos 32 caracteres: es la única barrera y la sesión dura 5 días.
- El proxy debe enviar `X-Forwarded-Proto: https` para que la cookie lleve la marca `Secure` (verificarlo al desplegar).
- htmx no guarda copias de páginas (`historyCacheSize: 0`): no quedan datos ni el token CSRF en el teléfono.
- `/_stcore/health` se conserva para el `healthcheck` de compose y las sondas.

## Recursos incluidos

HTMX 2.0.4 e Inter 4.0 (con su licencia) viven en `src/nicheradar/web/static/`; las huellas están en
`static/js/VENDOR.md`. No se carga nada de terceros en tiempo de ejecución.

## PWA

Manifiesto, iconos y un service worker que solo guarda los estáticos (nunca páginas con datos); hay una
página sin conexión.

## Pantallas del corte 1

| Pantalla | Ruta | API que usa |
|---|---|---|
| Hoy (M1, M14 parcial) | `/` | `/market/niches`, `/flow-research`, `/pilots`, `/subniches`; cada tarjeta degrada sola si su fuente falla |
| Nichos (M2) y decisión | `/nichos`, `POST /nichos/decidir` | `/market/niches` (hasta 200), `/flow-research` (últimos 100), `/market/niches/{etiqueta}/decisions` |
| Iniciar investigación (M8) | `/nichos/investigar?etiqueta=&formato=`, `POST` | `/market/niches/{etiqueta}`, `POST /flow-research` |
| Informe (M3, M11) | `/informes/{id}` | `/flow-research/{id}` (dossier v1, v2 y v3; v1/v2 con aviso; subnicho con aviso de confianza y fecha) |
| Autorizar piloto (M4, M12) | `/pilotos/autorizar?informe=`, `POST` | `/flow-research/{id}`, `/pilots` (canales ocupados), `POST /pilots` |
| Subnichos (M9, M10) | `/subnichos`, `/subnichos/{slug}`, `POST /subnichos/{slug}/investigar` | `/subniches`, `/subniches/{slug}`, `POST /flow-research` |

Todas las pantallas de datos son `GET` protegidos por sesión; todo `POST` exige CSRF (salvo `/login`).

### Rulings del plan

1. La etiqueta del nicho viaja por query (`?etiqueta=`), no por ruta, porque la API de mercado no admite etiquetas con `/`.
2. «Descartar» solo aparece para nichos de backlog (no subnichos).
3. Autorizar un piloto no pide cadencia, preparación ni receta.
4. `authorized_by` es un valor fijo.
5. La pestaña Pilotos se activa en el corte 2a; «Más» se activa en el corte 3a (menú con Operación y Salir).

### Límites conocidos

- `/market/niches`, `/flow-research` y `/pilots` se leen con tope de 100 a 200 registros y sin paginar: con más, la web ve los más recientes y lo avisa (por ejemplo, «Puede haber investigaciones más antiguas que no se ven; el botón Investigar podría repetir una»).
- Etiquetas con `/` en el nombre del nicho: la API de mercado las rechaza (limitación de su ruta); la web no las puede abrir.
- Un cuerpo de la API con forma inesperada (campos que faltan, `NaN`, tipos incorrectos) en cualquier `GET` de pantalla o en los `POST` que redibujan una pantalla (autorizar piloto, iniciar investigación) muestra un 503 en español («formato inesperado»); en un fragmento HTMX es un aviso pequeño con estado 200. Las cifras no finitas se ven como «—» y una fecha sin zona horaria se lee como UTC.
- Autorizar: «Canal nuevo» ignora el nombre escrito (no se envía `target_channel`); «Usar el canal que escribo» lo envía. El presupuesto mostrado es el del informe y no cambia con el tope de videos.
- Si la API cae, cada pantalla muestra su mensaje en español con 503 (o 200 en fragmentos HTMX).

### Lo que no se muestra a propósito

Porque la API no entrega el dato o el diseño lo difiere: Fit, Demanda y Volumen de un nicho; el idioma en la lista de nichos (y su filtro); Cadencia, Preparación y Receta al autorizar; la barra de proporción por etapa del informe; «Descartar» en subnichos. No se inventa ningún valor para estos huecos.

### Pruebas transversales

`tests/test_web_smoke_screens.py` recorre las rutas de los cortes 1, 2a y 3a y el detalle de nicho (`/nichos/ver`, con su `POST` de decisión y `volver`) (Operación, Ejecuciones y Más; los dos `POST` del scraper sin CSRF o en estado no permitido no escriben; `/mas` no lee la API) (incluidas las cinco pestañas del piloto, las confirmaciones y el cierre) con texto hostil en todas las cadenas, con la API caída, con cuerpos mal formados (cada campo reemplazado por `null`, texto, número, `NaN`, infinito, listas y objetos vacíos), con fechas sin zona horaria, y comprueba que no haya orígenes de terceros, código en línea, CSP distinto entre rutas ni `POST` sin CSRF que toque la API (también los de pilotos), y que un `POST` con CSRF en un estado no permitido no escriba nada.


## Pantallas del corte 2a (pilotos)

| Pantalla | Ruta | API que usa |
|---|---|---|
| Lista de pilotos (M5) | `/pilotos?filtro=todos\|activos\|bloqueo\|cerrados` | `GET /pilots?limit=100` (con `valid_until`, `delivered_at` y `channel`, campos aditivos de la lista) |
| Panel (M6) con Resumen, Preparación (M7), Videos, Reglas e Historial | `/pilotos/{id}?pestana=…`; `/pilotos/{id}/preparacion` redirige (303) a la pestaña | `GET /pilots/{id}`; la pestaña Videos además `GET /pilots/{id}/videos` (endpoint nuevo del corte 2a) |
| Seguir o cerrar | `/pilotos/{id}/decidir?accion=seguir\|cerrar`, `POST` | `GET /pilots/{id}`, `POST /pilots/{id}/decision` |
| Cancelar | `/pilotos/{id}/cancelar`, `POST` | `GET /pilots/{id}`, `POST /pilots/{id}/cancel` |
| Resumen de cierre | `/pilotos/{id}/cierre` | `GET /pilots/{id}/closing-summary` (texto, tope 256 KiB) |
| Hoy (M14 parcial) | `/` | las tarjetas de pilotos enlazan al panel; los informes ya con piloto se excluyen |

Los `POST` validan CSRF, el id y la nota localmente, releen el piloto y solo entonces escriben; la decisión
sale de la ruta y el actor lo fija el servidor. Tras una acción se vuelve al panel con un aviso
(`?aviso=`, claves fijas).

### Lo que el corte 2a omite a propósito

- La frase de postura editorial, la URL del canal y la emisión de tokens (se hace por línea de comandos).
- El plazo de preparación y la cadencia: el contrato del paquete no tiene esos campos, así que no se muestran ni se calculan.
- Las fechas sin una base real; las que se muestran van rotuladas «tentativa».

### Límites del corte 2a

- `GET /pilots` se lee con tope de 100: con exactamente 100 la lista y Hoy avisan de que puede haber más. Los videos, reglas y eventos se muestran hasta un tope fijo por pestaña, también con aviso.
- Un id de piloto con `%2F` no llega a la ruta: responde 404 por defecto.
- Una zona horaria de configuración inválida cae a UTC en vez de romper la pantalla.

### Corte 2b: calibración (M13) y pilotos en calibración (M14)

- Pestaña **Calibración** del panel: aparece solo si el paquete del piloto trae un dossier v3. (Desde la alineación con el Figma, en un piloto con dossier v3 todas las pestañas leen `GET /flow-research/{id}` y `GET /pilots/{id}/videos`, porque la línea de estados de calibración y el Resumen los necesitan: son 2 lecturas extra por página, una vez cada una, siempre con `limit` de la API y sin reintentos; un piloto sin v3 no hace ninguna, y la lectura de videos de la pestaña Videos se reutiliza.) Si el dossier o los videos no se pueden leer, la pestaña lo dice y el resto del panel sigue.
- Línea de estados de calibración: «autorizado · entregado · preparado · en calibración · pasa a régimen · decisión pendiente», derivada solo del estado de la API y de `passes`; con cifras de mínimo estimado el paso se rotula «pasa a régimen (posible)». Para el estado `entregado` el paso activo es «preparado» (el canal aún se prepara; su `title` dice «Entregado: el canal se está preparando»). El chip «En calibración» y el «Día N desde el primer video» solo se usan en estados abiertos con calibración legible; cerrado y cancelado conservan el chip y el texto normales.
- La calibración se calcula al leer, en la web, y es una sugerencia en texto («Pasa a régimen»): el servidor no evalúa nada y no hay botones nuevos.
- El criterio de salida `max_minutes_per_video` es **inclusivo**: un video lo cumple con `human_minutes <= max`. La racha cuenta los últimos videos consecutivos que cumplen; un video sin medir (`null` o un valor inválido: negativo, no finito o no entero) la corta; un cero medido es válido y cuenta («0 min»).
- La calibración usa solo videos publicados (`published_at` legible): un borrador sin publicar no cuenta ni corta la racha. El texto de la racha es «Racha de hasta N minutos» (criterio inclusivo) y el método se toma solo de videos con minutos medidos.
- Las horas de preparación del dossier son un plan: se rotulan «Preparación del canal (hecha)» solo con el piloto en ejecución, con decisión pendiente o cerrado; antes se rotulan «(prevista)» y las horas de calibración dicen «(incluye preparación prevista)».
- Nunca se muestra «0 min» por datos sin medir: se dice «Aún sin minutos medidos» (el total de la API suma solo los medidos). La etiqueta del método sale de `human_minutes_method` de los videos («estimado (método X)»; varios métodos, «métodos mezclados»). El productor `scripts/channel_human_minutes.py` genera `v3` con el método `claude_sessions_plus_assumed`: «estimado (método claude_sessions_plus_assumed)» significa tiempo activo humano en Claude Code más un supuesto fijo por video para YouTube Studio, no un cronómetro; los videos de reportes `v1`/`v2` siguen «sin medir» y un reporte `v1`/`v2` nunca toca los minutos humanos ya guardados: los videos enviados antes en `v3` conservan sus valores (ver `docs/pilots.md`).
- **Mínimo estimado (`claude_sessions_plus_assumed`)**: la cifra de ese método es un piso, no una medida: suma el tiempo humano de lectura y escritura en las sesiones de Claude Code más un supuesto declarado, y buena parte del tiempo medido queda sin atribuir. Por eso, si algún video medido declara ese método (`LOWER_BOUND_METHODS` en `calibration.py`; con métodos mezclados que lo incluyan basta), la web rotula «mínimo estimado (método …)», muestra cada fila como «≥ N min» (un cero medido, «≥ 0 min»; «sin medir» no cambia) y la racha como «posible»: «Racha de hasta N minutos: X de Y (posible: las cifras son un mínimo)». Si la racha alcanza el criterio, `passes` sigue siendo verdadero pero el chip de Hoy y la propuesta dicen «Podrías pasar a régimen», con la nota «Las cifras son un mínimo estimado: confírmalo con tu propio criterio.»; la decisión es del propietario. Los números (racha, horas, avisos) no cambian; con cualquier otro método o ninguno los textos son los de siempre.
- Cada cifra: los minutos por video salen de `human_minutes` de `GET /pilots/{id}/videos`; la meta, la racha exigida, las horas de preparación y los minutos previstos por paso, del bloque `calibration` del dossier v3; el régimen, de los minutos por video de la automatización del dossier; la racha y las horas, calculadas en la web. Un `human_minutes` fuera del rango del contrato (0..100000) o de otro tipo se lee como «sin medir».
- El rótulo del método sale de `human_minutes_method`; si ningún video trae minutos medidos la pantalla dice «Aún sin minutos medidos».
- Hoy: tarjeta «N pilotos en calibración» con la racha y el último video, solo para pilotos activos con calibración legible; mira como máximo 5 pilotos (tres lecturas cada uno) y avisa «y N más».

## Corte 3a: Operación, menú Más y cabecera

| Pantalla | Ruta | API que usa |
|---|---|---|
| Menú Más (M18) | `/mas` | ninguna: enlaza a Operación y trae el botón Salir (`POST /salir`, con CSRF) |
| Operación (M15) | `/operacion?aviso=` | `GET /market/schedule`, `GET /market/runs?limit=20`, `GET /subniches?include_inactive=true`; cada tarjeta (scraper, últimas ejecuciones, subnichos) degrada sola si su fuente falla |
| Ejecuciones | `/operacion/ejecuciones` | `GET /market/runs?limit=20` |
| Pausar o reanudar el scraper | `/operacion/scraper/pausar\|reanudar`, `POST` | `GET /market/schedule` y `PUT /market/schedule` con `{"paused": bool}` |

- **Confirmación del scraper**: pausar y reanudar pasan por una pantalla de confirmación con la consecuencia en texto. El `POST` valida CSRF, relee el estado y solo entonces escribe; la acción sale de la ruta, nunca del formulario. Si ya estaba en ese estado, vuelve a Operación con «El scraper ya estaba en ese estado.»; si el modo es real y el scraper en vivo no está habilitado en el servidor, reanudar se bloquea (409, sin escritura). Los avisos de la pantalla usan claves fijas (`?aviso=`), nunca texto de la URL.
- **Avisos de Operación**: scraper pausado, última ejecución parcial, fallida o bloqueada, y modo real sin scraper en vivo habilitado.
- **Subnichos**: resumen de activas, propuestas, pausadas, sin primera medición y última medición.
- **Cabecera sin radar**: la cabecera ya no muestra ni consulta el estado del radar; la web no llama a `/status`.
- **Sesión de 5 días**: la cookie dura 5 días (ver Sesión y seguridad).
- **Calibración como mínimo estimado**: la cifra de minutos de `claude_sessions_plus_assumed` se rotula como mínimo (ver corte 2b).
- **El radar de oportunidades no está en la web**, ni tampoco «Análisis de canal»: siguen solo en Streamlit hasta su retiro (3f). No se mostrará su estado, no se pausa ni se reanuda desde la web.

## Alineación con el Figma ordenado (2026-11-04)

Plan: `docs/superpowers/plans/2026-11-04-alineacion-web-con-figma.md`. Solo cambia `src/nicheradar/web/`; no toca la API ni la base.

| Pieza | Ruta o lugar | Notas |
|---|---|---|
| Detalle de nicho (M19) | `GET /nichos/ver?etiqueta=&formato=` | Lee `GET /market/niches/{etiqueta}`. La etiqueta va por query (puede traer `/` u `other:`). «Ver más fichas» muestra 10 más por toque sobre las ya cargadas; hasta 100 fichas, con aviso si hay más. La tendencia es «sube», «baja», «estable» o «sin dato». |
| Recorrido hasta el piloto | macro `journey` (`journey.py`) en el detalle de nicho y en la ficha de subnicho | Seis pasos: Candidato, Decisión, Listo para investigar, Investigación de flujo, Informe, Piloto. Regla: cada paso es `done` (✓), `now` (●) o `pending` (○); `now` es el **primer paso no hecho**; si todos están hechos, Piloto es `now`. El texto de Piloto es «Piloto {estado}» (por ejemplo «Piloto en ejecución») si hay un piloto abierto, o «Decide si lo lanzas» si no. Nicho descartado: Decisión es `now` («Descartado: se oculta de la lista») y todo lo siguiente `pending`, aunque existan datos (Ruling 2). Subnicho pausado: Decisión `done` («Pausada») y «Listo para investigar» `now` («Reanúdala para medirla»); archivado: Decisión `now`. Nunca lanza ante datos mal formados: dice qué falta. |
| Decisión del nicho | `POST /nichos/decidir` | Sin decidir, Tentativo, Descartado; reversible, con CSRF y sin pantalla de confirmación. |
| Control con conteos | `Nichos (N) \| Subnichos (M)` en las dos listas | Cada lista hace una lectura cruzada extra para el conteo de la otra (`GET /subniches` o `GET /market/niches?limit=1`) con timeout de 3 s; si falla, el conteo se muestra como desconocido y la lista sigue. |
| Informe y autorización | `/informes/{id}`, `/pilotos/autorizar` | Una sola pantalla para nichos y subnichos, con rótulo de origen; v1/v2 con aviso. |
| Panel del piloto y Hoy | `/pilotos/{id}`, `/` | Calibración en el Resumen; Hoy con pendientes fusionados, títulos dinámicos y tarjetas con acciones. |

### Retorno seguro (`volver`)

«Hoy» y el detalle de nicho envían `volver` en la decisión. Solo se acepta una lista blanca de rutas internas: `/`, `/nichos` y `/nichos/ver?...`. Cualquier otro valor (`https://…`, `//host`, `javascript:`, `/nichos/../x`) se ignora y se vuelve a `/nichos`.

El detalle de nicho avisa (mismo aviso fijo que la lista) cuando la lectura de investigaciones o de pilotos llega al tope de 100, y entonces deshabilita «Investigar» con el motivo para no repetir una investigación que no se ve.

### Costo de lecturas del panel

Con un dossier v3, el panel del piloto hace 2 lecturas extra por página (`GET /flow-research/{id}` y `GET /pilots/{id}/videos`), una vez cada una y sin reintentos; sin v3 no hace ninguna (ver «Corte 2b»).

### Lo que el diseño tiene y la web aún no

- Cadencia y días de preparación al autorizar (M12): no existen en el contrato de pilotos, que es inmutable tras autorizar; es un corte propio.
- Idioma por nicho en la lista y en Hoy (chip «EN 80 %» y filtro «Idioma»): exige un resumen de `language_mix` en `GET /market/niches`.
- «Fit» de M2: se quitó del Figma el 2026-11-04 (no existe para nichos de mercado); no se muestra.
- Decisión del subnicho y «+ Proponer subnicho»: ya existen (ver «Proponer subnicho y Compartir (Android)»).
- Botones de acción por bloqueo del panel («Renovar paso a paso», «Revisar tabla»): sin destino definido.
- Botones de nicho apilados en vez de en fila (Hoy y listas): diferencia de maquetación aceptada.
- Presupuesto «por suscripción / por API» de M12: se conserva bajo, probable y alto del dossier.

## Proponer subnicho y Compartir (Android)

Plan: `docs/superpowers/plans/2026-11-04-web-proponer-subnicho-y-compartir.md`. Solo cambia `src/nicheradar/web/`; la web nunca llama a YouTube ni al modelo: habla con la API privada de propuestas.

| Pantalla | Ruta | API que usa |
|---|---|---|
| Proponer (M25) | `GET /subnichos/proponer?q=`, `POST` | `POST /subniches/proposals` con `Idempotency-Key` |
| En preparación y lista (M26, M27) | `/subnichos/propuestas/{id}` (fragmento HTMX con sondeo) | `GET /subniches/proposals/{id}` |
| Confirmar aprobación (M28) | `/subnichos/{slug}/aprobar` | `GET /subniches/{slug}/approval`, `POST /subniches/{slug}/approve` |
| Pausar, reanudar, archivar | `POST /subnichos/{slug}/pausar\|reanudar\|archivar`; `/subnichos/{slug}/archivar` pide confirmación | `POST /subniches/{slug}/pause\|resume\|archive` |
| Compartir (M29, M30) | `GET /compartir?title=&text=&url=` | ninguna (solo clasifica el enlace) |

### Flujo

1. Se pega una consulta, un video o un canal (o se comparte un enlace desde Android) y se pulsa «Proponer». Una consulta no gasta cuota; un video gasta 1 unidad y un canal 1 o 2. El modo manual («Sin modelo de lenguaje») pide etiqueta, familia y nicho padre opcional, y exige una consulta (un enlace en modo manual lo rechaza la API).
2. La propuesta queda **en cola**, un worker la **prepara** y queda **lista** (hipótesis con familia, nicho padre, canales semilla y consultas) o **fallida**. La pantalla se actualiza sola con htmx.
3. «Revisar y aprobar» abre M28, que muestra consultas, páginas, unidades de búsqueda por medición y el tope diario. Si no caben en la cuota lo dice con las cifras y deja aprobar. Aprobar no mide al instante: la primera medición ocurre en la próxima ronda con cupo. Nada se aprueba solo: es un `POST` aparte con CSRF.
4. La ficha vuelve con el aviso `aprobado` y el botón «Pausar» (después «Reanudar»). Archivar pide marcar «Entiendo que no se puede deshacer».

Los textos de error de una propuesta fallida vienen de un diccionario fijo de la web según el `code` (un código desconocido da un texto genérico; `duplicate:...` muestra el texto fijo de duplicado, nunca el detalle); el texto de la API, de YouTube o del modelo nunca se muestra. Los avisos usan claves fijas (`?aviso=`).

### Sondeo acotado

El detalle de una propuesta en cola o preparándose se vuelve a pedir cada 5 s (`hx-trigger="every 5s"`, contador `?n=`) y se detiene tras 120 vueltas, unos 10 minutos: pasado el tope muestra «Actualizar» a mano. Un fallo transitorio de la API conserva la pantalla (204) y el siguiente sondeo reintenta; un 404 detiene el sondeo con un aviso (estado 286).

### Clave de idempotencia

El formulario lleva un nonce de 32 hex. La clave que se envía a la API es `nr-` más 40 hex derivados con el HMAC de la sesión (`signer.derive("idem", f"{csrf}:{nonce}:{sha256(cuerpo canónico)}")`, con el cuerpo canónico en JSON de claves ordenadas): el mismo nonce y el mismo contenido en la misma sesión dan la misma clave, así que un doble toque, recargar o reenviar tras un fallo transitorio no crea dos propuestas, y un contenido corregido con el mismo nonce es otra solicitud (no devuelve en silencio la anterior). Un rechazo de dominio (422/429 con código) genera un nonce nuevo; un fallo transitorio lo conserva.

### Compartir desde Android

1. En Chrome para Android abrir la web y elegir «Instalar app» (o «Agregar a la pantalla principal»). **Si la PWA ya estaba instalada, hay que desinstalarla y reinstalarla**: Android registra el destino de «Compartir» (`share_target` del manifiesto) al instalar.
2. En YouTube (o en cualquier app) tocar «Compartir» y elegir NicheRadar.
3. Se abre «Compartido contigo» con el tipo (canal o video de YouTube) y el botón «Proponer», que lleva al formulario ya relleno con la forma canónica del enlace (`https://www.youtube.com/watch?v=…`, `@handle`…). Compartir nunca crea nada solo.

El enlace se toma de `url`, o de `text` o `title` si ahí viene el enlace; los enlaces de otro dominio, `javascript:` o con caracteres de control se descartan. Sin sesión, el login devuelve al mismo enlace (`next` solo acepta rutas internas).

### Límites

- Los enlaces de X (tweets) todavía no se leen: la pantalla lo avisa y pide copiar el canal o el enlace de YouTube que menciona.
- Solo Android: el `share_target` de las PWA no existe en iOS.
- Sin imágenes: el destino es `GET` con título, texto y enlace; compartir imágenes exige `POST` con archivos y un service worker, fuera de este plan.
- Las consultas y los canales semilla de una propuesta se muestran hasta 20 cada lista, con el aviso fijo «Se muestran los primeros 20.».

### Qué necesita producción

- API de propuestas y worker con `NR_SUBNICHE_ENABLED=true`: **ya desplegados en la release 036**.
- La PWA reinstalada en el teléfono (ver arriba) para que Android registre «Compartir».
- `NR_DASHBOARD_UI=web`.
- Contraseña de la app larga y aleatoria y **sin Basic Auth del proxy** (acción del propietario en Easypanel): `/compartir` debe llegar con la cookie de sesión.

### Seguimiento

- Reservar los slugs `proponer` y `propuestas` en la API. Hoy la web solo rechaza `proponer`, y solo en la etiqueta manual; `propuestas` no se rechaza en ningún sitio. Efecto real: `/subnichos/propuestas/aprobar` y `/subnichos/propuestas/archivar` caen en la ruta del detalle de propuesta y dan 404 (la ficha de un subnicho con ese slug no se puede abrir ni aprobar desde la web); la CLI sigue sirviendo.
- Lectura de tweets y de imágenes (M31 a M34): plan aparte.

## Comprobación visual contra el Figma

```
uv run python scripts/web_preview.py --out /tmp/web-preview
```

Renderiza Subnichos (lista y ficha con Recorrido), Hoy, Nichos, Detalle de nicho (`nicho_detalle`), Investigar, Informe v3, Autorizar y, del corte 2a, Pilotos, Piloto (Resumen), Preparación y Confirmar, del corte 2b, Calibración (piloto en ejecución) y, del corte 3a, Operación, Ejecuciones, Más y Confirmar scraper y, de Proponer y Compartir, las siete pantallas nuevas (`proponer`, `propuesta_cola`, `propuesta_lista`, `aprobar`, `archivar`, `compartir` y `compartir_tweet`), con datos de ejemplo
(`scripts/web_preview_data.py`, sin API real) y guarda `lista`, `ficha`, `hoy`, `nichos`, `nicho_detalle`, `investigar`,
`informe`, `autorizar`, `pilotos`, `piloto`, `preparacion`, `calibracion`, `confirmar`, `operacion`, `ejecuciones`, `mas`, `confirmar-scraper`, `proponer`, `propuesta_cola`, `propuesta_lista`, `aprobar`, `archivar`, `compartir` y `compartir_tweet` como `.html` y, si hay Chrome (`--chrome RUTA`), como `.png` a 390 px de ancho con
escala 2. Compárense con el Figma M9 (`29:2`), M10 (`30:2`), M19 (`47:37`), M14 (`36:2`), M11 (`31:2`), M12 (`32:2`), M13 (`35:2`) y los demás marcos del archivo. Los estados de investigación de la lista son
ilustrativos, como en el Figma. Las rutas `file://` solo existen en esta vista previa. Chrome headless no
baja de 500 px de ventana, por eso la página se mide dentro de un `iframe` de 390 px y se recorta con `sips`
(macOS).
