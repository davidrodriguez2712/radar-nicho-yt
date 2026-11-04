# Rediseño móvil, corte 3: paridad con Streamlit y retiro de Streamlit

Estado: borrador para revisión del propietario (2026-11-03). Continúa
[`2026-11-02-rediseno-movil-web-design.md`](2026-11-02-rediseno-movil-web-design.md) (corte 1, en `main`) y
[`2026-11-02-rediseno-movil-corte2-design.md`](2026-11-02-rediseno-movil-corte2-design.md) (corte 2a en `main`; 2b con plan).

## Problema

La web móvil ya cubre lo que el propietario hace a diario (Hoy, Nichos, investigación, informe, autorizar piloto,
Subnichos y todo el seguimiento de pilotos). Pero el dashboard de Streamlit sigue siendo la **única** interfaz para el
resto: el resumen de oportunidades y el consumo, el Backlog con sus cinco pestañas, los escenarios, la configuración, la
operación del radar, el análisis de canal y el detalle de un nicho. Mientras exista, hay dos interfaces que mantener y un
contenedor con una dependencia pesada (`streamlit`). El objetivo del rediseño es una sola web, móvil, en el mismo dominio.

## Objetivo

1. **Paridad funcional:** todo lo que Streamlit hace hoy se puede hacer en la web, con las mismas protecciones (confirmación
   en lo que gasta cuota o cambia el estado del radar, versiones esperadas en lo que se edita, nada de secretos en el
   navegador).
2. **Retiro de Streamlit** una vez demostrada la paridad: se elimina el código, la dependencia, los archivos de imagen,
   las sondas y las pruebas que lo usan, sin dejar a producción sin interfaz en ningún momento.

## Hechos comprobados (inventario del 2026-11-03)

- Streamlit **no toca la base de datos**: todo va por la API privada con el token de servicio (como la web).
  Solo importa funciones puras del servidor (`domain.production.STAGES`, `flow_research.contracts`,
  `flow_research.evidence.REASONS/ineligible_reason`); la web ya importa `flow_research.contracts` y `gates`.
- No usa caché, ni refresco automático, ni gráficos, ni descargas: solo tablas, métricas, JSON y texto. **No hay gráficos
  ni descargas que migrar.**
- **No falta ninguna API:** todas las funciones tienen endpoint. Hay una salvedad en el cliente web: `POST /runs` y
  `POST /channel-analyses` exigen la cabecera `Idempotency-Key` (8 a 100 caracteres) y `ApiClient.request` no admite
  cabeceras todavía.
- Lo que Streamlit hace y la web **ya cubre**: acceso con contraseña, Mercado (lista, decisión, investigación de flujo,
  dossier), Subnichos y Portafolio (superado: la web además autoriza, decide y cierra).
- Lo que **falta** (pantallas de Streamlit en el orden en que aparecen): avisos de estado completos, Resumen y Consumo,
  detalle de nicho (fichas, «cómo se calculó», «Analizar canal»), Backlog de oportunidades con cinco pestañas,
  Escenarios, Configuración, Operación y Análisis de canal.

## Diseño

### 1. Cortes de entrega

Cada entrega deja la web utilizable y se puede fusionar sola. Ninguna cambia el contenedor que sirve producción hasta el
retiro.

| Entrega | Pantallas | API principal |
|---|---|---|
| **3a Operación y estado** | Avisos de estado (modo, scraper pausado o con última ejecución parcial o fallida); **Operación**: scraper de mercado (estado, horario, pausar y reanudar con confirmación, ejecuciones) y resumen de subnichos (activas, propuestas por aprobar, pausadas, sin primera medición, última medición). **Sin el radar** (ver «Decisiones del propietario», 5) | `GET /status`, `GET/PUT /market/schedule`, `GET /market/runs`, `GET /subniches?include_inactive=true` |
| **3b Detalle de nicho** | Detalle de nicho (fichas del mercado, «cómo se calculó», descartados visibles, enlace «Analizar canal»). **Resumen y Consumo quedan fuera** (eran del radar) | `GET /market/niches/{label}`, `GET /market/niches?include_discarded` |
| ~~3c Backlog de oportunidades~~ | **Fuera de alcance:** el radar de oportunidades se quita de la web móvil (decisión 5). El código del servidor y Streamlit no se tocan hasta el retiro | — |
| **3d Análisis de canal** | Analizar, lista comparativa, detalle, historial completo (con estimación de cuota y confirmación), eliminar | `POST/GET /channel-analyses`, `/{id}`, `/deep-history/estimate`, `POST /deep-history`, `DELETE` |
| **3e Configuración** | Configuración (recursos compartidos y receta de producción por defecto): **por confirmar** si sigue haciendo falta sin el radar. **Escenarios quedan fuera** | `GET/PUT /profile`, `GET/POST /defaults/production-recipes/{format}`, `GET /catalog` |
| **3f Retiro de Streamlit** | Ver sección 4 | — |

### 2. Reglas comunes a las pantallas nuevas

- Todo lo de los cortes anteriores: cookie firmada, CSRF antes de llamar a la API en todo POST/PUT/DELETE, CSP propia,
  escape de todo texto de la API (los textos de vendedores y de YouTube se muestran como texto, nunca como Markdown),
  identificadores validados con `fullmatch` ASCII antes de usarse en rutas, avisos desde claves fijas, `shape_guard` en las
  pantallas y guardia equivalente en los POST que redibujan, `with_radar=False` tras un fallo, aviso cuando una lista llega
  a su tope, números no finitos como «—», fechas sin zona como UTC.
- **Acciones que gastan o cambian estado real** se hacen con una **pantalla de confirmación** que dice la consecuencia
  (y la cifra cuando existe): reanudar el radar, solicitar exploración (consume créditos/cuota), historial completo de un
  canal (cuota de YouTube real: se muestra `quota_units` de la estimación), pausar o reanudar el scraper, eliminar un
  análisis. La confirmación es un GET; el POST valida el CSRF y el estado antes de llamar a la API.
- **Idempotencia:** los formularios que llaman a `POST /runs` y `POST /channel-analyses` llevan una clave de idempotencia
  generada por el servidor al pintar la confirmación y firmada con el mismo HMAC de la sesión (para que un doble envío
  repita la misma clave y no cree dos trabajos). `ApiClient.request` gana un parámetro `headers`.
- **Ediciones con versión** (decisión por oportunidad, producción, puntuación, perfil, recetas): el formulario lleva
  `expected_version`; un 409 «Los datos cambiaron» se muestra con un botón «Recargar» y **conserva lo escrito**.
- **Móvil primero:** tablas anchas se convierten en tarjetas de lista; los filtros son pastillas; las pestañas del
  detalle de oportunidad son enlaces con `?pestana=` (patrón del panel de pilotos).
- **Secretos:** la web nunca muestra credenciales de proveedores, ni el token de servicio, ni valores de la base;
  `/providers` y `/status` solo exponen configuración pública y se muestran tal cual.
- **Editores JSON** (producción, puntuación y escenarios usan hoy un editor JSON crudo): ver «Decisiones pendientes».

### 3. Pruebas

Cada pantalla trae sus pruebas de ruta, de modelo de vista y de seguridad, más la **prueba de humo** del corte 1 extendida
(datos hostiles, API caída, formas mal hechas, sin recursos externos, CSP idéntico, todo POST sin CSRF → 403 y cero
llamadas). La lógica de negocio que hoy se prueba con las ayudas de Streamlit (`backlog_rows`, `listing_rows`,
`subniche_rows`, `channel_rows`, `portfolio_rows`, `render_dossier`, `render_research_status`, preflight y monitoreo) se
**migra a pruebas web equivalentes antes** de borrar las pruebas de Streamlit; la lista de pruebas a migrar y a borrar
está en el plan de 3f.

### 4. Retiro de Streamlit (3f)

Orden, para no dejar a producción sin interfaz:

1. **Release de la web** con `NR_DASHBOARD_UI=web` en la app existente de Easypanel (misma imagen, misma ruta, mismo
   dominio). La imagen anterior queda etiquetada para volver atrás con solo cambiar la variable. Requiere aprobación del
   propietario y comprobar que el proxy envía `X-Forwarded-Proto: https`.
2. **Periodo de prueba** del propietario con la web como interfaz real.
3. **Retiro del código**, solo después de que el propietario confirme que no necesita volver atrás: borrar `dashboard.py`,
   `market_dashboard.py`, `flow_research_dashboard.py`, `subniche_dashboard.py`, `pilots_dashboard.py`, la rama de Streamlit
   de `entrypoints.dashboard()` y el campo `dashboard_ui`; quitar `streamlit` de `pyproject.toml` y regenerar `uv.lock`;
   quitar `.streamlit/` del `Dockerfile` y `.dockerignore`; reescribir las sondas (`scripts/easypanel_probe.py`,
   la sonda WebSocket de `scripts/easypanel_stage.mjs`, `scripts/smoke_compose.py`) para HTTP simple sobre la web nueva;
   mantener (o renombrar) la ruta de salud que usa `compose.yaml`; eliminar o migrar las pruebas con `AppTest`
   (`test_dashboard_navigation`, `test_market_dashboard`, `test_pilots_dashboard`, `test_subniche_dashboard`,
   `test_flow_research_dashboard`, `test_console_states`, `test_pilot_preflight`, `test_operational_monitoring`,
   partes de `test_foundation`, `test_integrated_failures`, `test_web_app`, `test_smoke`); actualizar la documentación
   (`docs/private-console.md`, `README.md`, `AGENTS.md`, `docs/web-movil.md`, `docs/comandos.md`,
   `docs/deployment-easypanel.md` y los documentos de operación que mencionan pestañas). Los `docs/release-*.md` y los
   specs y planes históricos **no se tocan**.
4. **Release de limpieza** (imagen sin Streamlit), también con aprobación.

## Compatibilidad y despliegue

- 3a a 3e no cambian contratos, base de datos ni contenedores; no se despliega nada con ellos.
- 3f toca el despliegue de producción (variable en Easypanel, imagen, sondas): cada release requiere la aprobación explícita
  del propietario, y las dos primeras comprobaciones (`probe` y humo en el contenedor) se ejecutan antes de dar por buena
  una release.

## Riesgos y casos a probar

1. Doble envío de «solicitar exploración» o de un análisis de canal: una sola ejecución (misma clave de idempotencia).
2. Reanudar el radar en modo real con el piloto no listo (409 con `blockers`): se muestran los bloqueos y no se reintenta.
3. Historial completo de un canal sin evidencia (404 en la estimación) o con cuota insuficiente: mensaje claro, sin gasto.
4. Ediciones concurrentes (409 de versión): lo escrito se conserva y se ofrece recargar.
5. Oportunidades con más de 100 elementos y filtros combinados: paginación correcta y avisos de recorte.
6. Texto hostil (vendedores, YouTube, notas) en todas las pantallas nuevas.
7. API caída o lenta en cada pantalla; la web nunca muestra una traza.
8. Después del retiro, `NR_DASHBOARD_UI` desaparece sin romper ningún despliegue existente (valor `streamlit` en el entorno
   de producción → ver «Decisiones pendientes»).

## Fuera de alcance

Gráficos nuevos; descargas o exportaciones (Streamlit no las tiene); rediseñar la lógica de puntuación; cambios de la API
privada (no hacen falta); cambios de proveedor o de infraestructura.

## Decisiones del propietario (2026-11-03)

1. **Diseño de las pantallas nuevas: (B).** Se diseñan primero en el archivo de Figma móvil existente y se implementan
   contra ese diseño. Bloquea la implementación de cada entrega hasta que su diseño esté aprobado.
2. **Editores JSON: (A).** Cuadro de texto JSON validado por la API, con la plantilla de la receta por defecto y los
   errores del servidor visibles.
3. **Orden de las entregas:** 3a, 3b, 3c, 3d, 3e y 3f (supuesto del recomendado; sin objeción).
4. **`NR_DASHBOARD_UI` tras el retiro: (A).** Se elimina; un valor `streamlit` se ignora con un aviso en el arranque.
5. **El radar de oportunidades se quita de la web móvil: (A).** Decidido el 2026-11-04. Quedan fuera: pausar y reanudar el
   radar, solicitar exploración, requisitos del piloto real, ejecuciones y proveedores del radar, Resumen, Consumo, Backlog
   y Escenarios. El backend y Streamlit permanecen hasta el retiro (3f); al retirar Streamlit esas pantallas dejan de existir
   en la interfaz. Pendiente de confirmar: si «Configuración» sigue siendo necesaria sin el radar.
