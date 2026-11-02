# Rediseño móvil de la web de NicheRadar

Fecha: 2026-11-02. Estado: borrador para revisión del propietario. Decisión de origen: el propietario aprobó la ruta
B (web de servidor en Python en el mismo dominio) y pidió el rediseño «cuanto antes» (2026-11-02). Diseño aprobado:
archivo de Figma «NicheRadar · Rediseño total (5 propuestas)», página «M · Móvil» (M1 a M14), `fileKey`
`JmBvlfNURrV226WOZLuCEz`.

## Problema

La web desplegada (`nicheradar.soydavidrodriguez.com`) es un dashboard de Streamlit pensado para escritorio. El
propietario aprobó un diseño móvil en español llano (tarjetas, barra inferior, botones grandes, veredicto primero) que
Streamlit no puede reproducir con fidelidad. Hay que reemplazar la interfaz sin tocar la API ni la infraestructura.

## Objetivo

Una interfaz móvil primero, instalable en el teléfono, que reemplace al dashboard de Streamlit **en la misma app de
Easypanel (`nicheradar-dashboard`), el mismo dominio y la misma seguridad**, entregada por cortes y con retroceso
inmediato a Streamlit.

## Restricciones comprobadas

- El contenedor del dashboard no tiene acceso a la base de datos: solo `NR_API_URL` (red interna), `NR_SERVICE_TOKEN` y
  `NR_DASHBOARD_PASSWORD`; 512 MB y 0,5 CPU; expone el puerto 8501. Todos los datos llegan por la API privada
  (`/api/v1/...`) con `Authorization: Bearer <NR_SERVICE_TOKEN>`, como hace hoy `api_request` en `dashboard.py`.
- Delante está el proxy de Easypanel con HTTPS y Basic Auth, y la aplicación tiene su propia contraseña. Ambas se
  mantienen.
- El punto de entrada `nicheradar-dashboard` hoy lanza Streamlit (`src/nicheradar/entrypoints.py:dashboard`).
- Todo texto visible en español; el diseño es móvil (390 px de base) con la paleta del Figma: Inter, fondo `#fff8f5`,
  primario `#be123c`, tarjetas blancas de radio 16, botones píldora.
- Sin secretos en el navegador ni en el HTML; los datos de canales, ingresos y fichas son datos no confiables y se
  escapan siempre (plantillas con autoescape; nunca `|safe` sobre datos de la API).
- No se cambia la base de datos ni la API salvo lo que se declare en este spec.

## Diseño

### 1. Arquitectura

- Paquete nuevo `src/nicheradar/web/` con una aplicación **FastAPI + Jinja2 + HTMX**, sin Node ni compilación. Los
  recursos estáticos (CSS, HTMX, fuente Inter en `woff2`, iconos, manifiesto) van **dentro del paquete y se sirven
  desde la propia aplicación**: la web no hace peticiones a CDN ni a terceros.
- Capa `web/client.py`: cliente `httpx` de la API privada (mismo contrato y los mismos manejos de error que
  `api_request`, pero devolviendo errores tipados para mostrar un mensaje claro por pantalla, no `st.stop()`).
- Una plantilla base (barra superior con el estado del radar, barra inferior de 4 pestañas: Hoy, Nichos, Pilotos, Más) y
  componentes de plantilla reutilizables (tarjeta, etiqueta, botón, selector segmentado, barra de progreso, detalle
  desplegable con `<details>`, campo de formulario).
- Interactividad con HTMX (cambio de filtros, pestañas, envío de formularios con actualización parcial). Sin
  framework de JavaScript.

### 2. Entrada y selección de interfaz

- El punto de entrada `nicheradar-dashboard` elige la interfaz con `NR_DASHBOARD_UI` (`streamlit` o `web`; **por
  defecto `streamlit`** hasta el corte). `web` arranca `uvicorn` con `nicheradar.web.app:app` en
  `NR_DASHBOARD_HOST:NR_DASHBOARD_PORT` (0.0.0.0:8501), de modo que Easypanel no cambia ni el dominio ni el puerto.
- Pasar de Streamlit a la web nueva, o volver, es **solo cambiar la variable** y reiniciar la app; además se conserva el
  retroceso por imagen (digests del release anterior). El código de Streamlit se mantiene hasta la paridad completa
  (corte 3) y se elimina después en un cambio aparte.

### 3. Autenticación y sesión

- Inicio de sesión con `NR_DASHBOARD_PASSWORD` (comparación en tiempo constante, igual que hoy) y cookie de sesión
  firmada: `HttpOnly`, `Secure`, `SameSite=Lax`, vigencia de 12 horas. La clave de firma se **deriva** del token de
  servicio (`HMAC-SHA256(NR_SERVICE_TOKEN, "nicheradar-web-session")`): no añade secretos nuevos y rotar el token
  invalida las sesiones.
- Protección contra CSRF en los formularios que cambian datos (token por sesión) además de `SameSite`. Límite de
  intentos de inicio de sesión (en memoria, 5 por minuto por origen). Cierre de sesión.
- Cabeceras de seguridad: `Content-Security-Policy` solo con recursos propios, `X-Content-Type-Options`,
  `Referrer-Policy: same-origin`, `Cache-Control: no-store` en las páginas con datos.
- Si falta `NR_DASHBOARD_PASSWORD` la aplicación no abre (igual que hoy: «Acceso pendiente»).

### 4. PWA

Manifiesto y un service worker mínimo que guarda en caché **solo los recursos estáticos** (nunca datos de la API) para
poder instalar la web en el teléfono; sin conexión muestra una pantalla «Sin conexión». Los iconos se generan a partir
de la marca «NicheRadar» en granate.

### 5. Corte 1: el trabajo diario

| Pantalla (Figma) | Ruta web | API que usa |
|---|---|---|
| M1 / M14 Hoy | `/` | `GET /status`, `GET /market/niches`, `GET /pilots`, `GET /flow-research?status=listo`, `GET /subniches` |
| M2 Nichos | `/nichos` | `GET /market/niches`, `POST /market/niches/{label}/decisions` |
| M9 Subnichos | `/subnichos` | `GET /subniches` |
| M10 Ficha del subnicho | `/subnichos/{slug}` | `GET /subniches/{slug}`, `POST /flow-research` |
| M8 Iniciar investigación (idioma) | `/nichos/{label}/investigar` | `GET /market/niches/{label}`, `POST /flow-research` |
| M3 / M11 Informe | `/informes/{id}` | `GET /flow-research/{id}` (dossier v3; v1 y v2 guardados con un aviso) |
| M4 / M12 Autorizar piloto | `/pilotos/autorizar` | `POST /pilots` |

Reglas de datos de este corte:
- «Hoy» agrega en el servidor web: pilotos que necesitan algo (`needs_decision`, pendientes de entrega), informes
  `listo` sin piloto, y los 3 nichos o subnichos que más merecen atención. Si una fuente falla, la tarjeta correspondiente
  muestra «no disponible» y el resto sigue.
- Los textos de las pantallas M1 a M4 que hoy son datos de ejemplo del Figma se sustituyen por datos reales; donde el
  Figma pide una cifra que la API no entrega (p. ej. `Demanda (3 m)` o `Volumen` si no vienen en `/market/niches`), la
  tarjeta omite esa cifra en lugar de inventarla.
- El informe de un dossier v3 muestra calibración y régimen y las compuertas; el de un subnicho añade el aviso de
  confianza y la fecha de la medición.

### 6. Corte 2: pilotos y preparación

M5 Lista de pilotos (`GET /pilots`), M6 Panel del piloto (`GET /pilots/{id}`), M7 Preparación del canal y M13 Panel del
piloto en calibración, M14 completo. **Hueco de datos conocido:** el reporte de canal (`channel-report-v1` y `v2`)
trae `machine_minutes` pero **no los minutos humanos por video**, que es lo que M13 necesita para la racha de
calibración. Opciones: (a) añadir un campo opcional de minutos humanos por video al reporte de canal (contrato nuevo,
`channel-report-v3`), o (b) que el propietario los registre a mano en el panel del piloto. Hasta decidirlo, M13 muestra
solo lo que la API ya entrega.

### 7. Corte 3: paridad con Streamlit

Operación, Escenarios, Configuración, Análisis de canal y el detalle de oportunidades (`/opportunities/...`),
`/consumption`, `/jobs` y lo que hoy hace Streamlit. Tras la paridad se retira Streamlit y su dependencia.

## Fuera de alcance

- Cambios de infraestructura de Easypanel, dominio, proxy o red.
- Cambios de la API privada o de la base de datos (salvo la decisión del hueco de M13, que sería un cambio aparte).
- Una aplicación nativa.
- Diseño de pantallas nuevas fuera de M1 a M14.

## Compatibilidad y despliegue

- Cada corte es un release (imagen del dashboard) con la aprobación del propietario en cada paso de producción. El
  cambio de Streamlit a la web nueva se hace con `NR_DASHBOARD_UI=web` y se puede deshacer al instante.
- Los pilotos, encargos y dossiers guardados no cambian.

## Riesgos y casos a probar

1. Inicio de sesión: contraseña incorrecta, límite de intentos, cookie manipulada o vencida, y sesión invalidada al cambiar
   el token de servicio.
2. CSRF: un POST sin token o con token ajeno se rechaza.
3. Texto hostil en datos (`**x**`, HTML, `<script>`, `[x](https://evil.test)`) en títulos de canales, consultas,
   etiquetas y campos del dossier se muestra escapado en todas las pantallas del corte 1.
4. API caída o lenta: cada pantalla muestra un mensaje claro y no una página rota; «Hoy» degrada tarjeta por tarjeta.
5. Un dossier v1 o v2 guardado se abre sin error con un aviso; un dossier v3 muestra calibración y régimen.
6. Móvil: 360 y 390 px sin desplazamiento horizontal; objetivos táctiles de al menos 44 px; contraste legible.
7. `NR_DASHBOARD_UI=streamlit` sigue funcionando sin cambios y `web` no importa Streamlit.
8. La web no hace ninguna petición externa (revisión de la política de contenido y de las pruebas).

## Decisiones pendientes del propietario

1. **Orden de los cortes:** ¿el corte 1 (trabajo diario) primero, como propongo, o prefieres otro orden?
2. **Hueco de M13:** ¿añadimos los minutos humanos por video al reporte de canal (contrato nuevo) o los registras a mano
   en el panel del piloto?
3. **Fuente Inter:** se incluye en el paquete (unos cientos de KB) para que la web no dependa de terceros; si prefieres
   la fuente del sistema, se omite y pierde algo de fidelidad con el Figma.
