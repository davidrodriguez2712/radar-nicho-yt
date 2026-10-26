# Estado de implementación — 2026-10-01

Release `v1-candidate-20261001-011` desplegada: el Home del dashboard resume el panorama
de oportunidades (conteos por estado, candidatos ordenados por score final → Market Score
→ volumen de evidencia → Creator Fit) con una tarjeta "Hacia dónde ir ahora" que traduce
los bloqueos reales. Suma ganancia mensual estimada por oportunidad (`GET
/opportunities/{id}/profit`): rango entre el canal mejor y peor ya compitiendo en el nicho
(velocidad de vistas real observada, nunca asumida) por un RPM investigado y activado para
"culture" (US$0,83–3,00/1000 vistas largo, US$0,03–0,10 Shorts), menos el costo real de
producción. Sin datos reales suficientes, el estado queda `incomplete` con la razón
exacta. Sin migración de esquema. Ver [release 011](release-20261001-011.md) y
[advertising-scoring.md](advertising-scoring.md).

La release anterior (010) autoaplicó la receta de producción por defecto (Creator Fit) en
cada evaluación sin receta propia, con capacidad real declarada de sus 4 herramientas
compartidas, así que el score resuelve `88.75`/`viable` desde la primera evaluación.
Migración `0009` (aditiva) aplicada en Contabo; el backlog real se conservó. Ver
[release 010](release-20260928-010.md) y [creator-fit-rubric.md](creator-fit-rubric.md).

La release 009 terminó el rediseño del dashboard (estilo de navegación y todo
el JSON crudo restante convertido a tablas), subió los topes de créditos vidIQ a
25/175/350 (ejecución/semana/ciclo) y dejó YouTube y el enriquecimiento LLM (`gpt-6-luna`,
tope US$5/semana) **validados con un piloto real**, no solo configurados: 2 unidades de
cuota YouTube y 16 enriquecimientos LLM exitosos (`llm_emphasis_only`, cero errores,
US$0,003044 confirmados). El radar volvió a pausa automáticamente. Ver
[release 009](release-20260927-009.md) y [piloto YouTube/LLM](youtube-llm-pilot-20260927.md).

OpenSpec `continuous-niche-discovery`: 54/55 tareas cerradas. La única tarea abierta es
9.4, sobre respaldo, restauración y conservación futura.

Prioridad acordada el 2026-09-16: dejar el almacenamiento externo como punto futuro
y retomar la preparación del piloto (10.6). R2/B2 no elegidos ni contratados; 9.4
continúa abierta y el respaldo del Mac sigue limitado al estado inicial sin investigación.
El propietario autorizó después el piloto personal acotado; no cambia el alcance general.

## Comprobado

- Autenticación por clave API MCP propia de vidIQ y comando `nicheradar-vidiq`,
  disponibles solo localmente. Por defecto comprueba configuración sin red;
  `--check-connection` inicializa MCP y lista herramientas sin ejecutarlas.
  Veintidós pruebas nuevas con el SDK real y HTTP simulado verifican límites,
  paginación, secretos, autenticación y fallos antes/después del envío.
  Conexión real aceptada desde el Mac con clave propia y catálogo de 59 herramientas
  inspeccionado sin ejecutar ninguna. Corregidos los parámetros de outliers conforme
  al contrato anunciado; cinco casos adicionales prueban traducción y conflictos.
  El worker desplegado está conectado al adaptador real mediante el gateway presupuestado;
  falla cerrado antes de llamar al proveedor si falta cualquier requisito.
  Ver [vidiq-connection.md](vidiq-connection.md) y [contrato](vidiq-contract-20260921.md).
- Diagnóstico del piloto en API privada y dashboard. Lee configuración y políticas sin
  escribir datos, contactar proveedores ni habilitar gasto. El preflight programado del
  despliegue quedó listo con 19 políticas y límites 5/25/100.
  Ver [pilot-readiness.md](pilot-readiness.md).
- Piloto real aislado completado: una búsqueda de canales y dos saldos, 5 créditos
  confirmados, saldo 175 → 170, 6,748 segundos y cero reservas inciertas. La base temporal
  se eliminó; el informe agregado no contiene nombres, IDs o consultas. Diez canales para
  `culture`, sin videos por el tope; calibración mantenida en `uncalibrated`.
  Ver [informe del piloto](vidiq-pilot-20260922.md).
- Releases 004, 005 y 006 desplegadas. La ejecución ampliada usó 20 créditos, consultó
  publicaciones, procesó 100 videos y creó dos entradas reales sin puntuación. La 004
  heredó de forma trazable el idioma declarado del canal; la 005 añade verificación
  semántica ONNX local para los casos de relevancia desconocida. La reevaluación 005 desde
  caché consumió cero créditos pagados, confirmó 4 largos, dejó 5 Shorts fuera de la
  ventana y produjo un snapshot de 8 entradas sin puntuación. Saldo actual 145, consumo semanal 25 y radar
  pausado. La 006 conecta YouTube como enriquecimiento opcional y permanece apagada hasta
  configurar una clave propia. Ver [release 006](release-20260923-006.md),
  [informe ampliado](vidiq-scheduled-expanded-20260922.md) y [guía](live-operation.md).
- YouTube Data API conectada en código como etapa opcional posterior a vidIQ: `videos.list`
  agrupa hasta 50 IDs, usa cuota/políticas/caché propias, comparte identidad canónica y
  combina únicamente campos compatibles. Incluye diagnóstico de una unidad y permanece
  apagada hasta configurar y validar una clave propia. Ver
  [youtube-enrichment.md](youtube-enrichment.md).
- 626 pruebas locales aprobadas con PostgreSQL temporal; las pruebas automatizadas no llaman proveedores,
  incluida restauración cifrada del esquema `public` en otro clúster.
- Ruff, formato y mypy sin errores. Dos advertencias de obsolescencia de dependencias
  del cliente de pruebas; no errores del producto. CI definida, no ejecutada remotamente.
- Catálogo → consultas sintéticas → cohortes separadas → métricas → backlog, conservando
  descartes y reutilizando caché. API privada y navegación del dashboard probadas.
- Rotación persistente, expansión real de consultas sintéticas desde subtemas,
  actualización por oportunidad/formato y continuación de lotes con recibos SQL.
  Cadencias editables y cobertura pendiente visible en API/dashboard. Ver
  [discovery-operation.md](discovery-operation.md) para límites y alcance.
- Programación concurrente, pausa y reclamación serializadas; atraso consolidado sin
  acumular ejecuciones mientras hay trabajo pendiente. Reintentos y recuperación de
  leases limitados, espera persistida con jitter y suspensión de ocurrencias que requieren
  atención. Solo una confirmación explícita de no envío libera una reserva de transporte;
  cobros inciertos permanecen bloqueados. Límites manuales/programados y fallos persistentes
  verificados con transportes inventados en `tests/test_scheduling_retries.py`.
- Embeddings ONNX locales conectados, con pruebas de vectores sintéticos para identidad,
  ruido, ambigüedad, alternativas, relevancia semántica y límites. El modelo fijado usa
  artefactos cuantizados por arquitectura y hashes verificados; el benchmark amd64 sobre
  100 videos alcanzó 172 MiB y 3,602 s. Artefactos con todas sus fuentes y caducidad;
  método visible en el detalle. Ver [topic-grouping.md](topic-grouping.md).
- Historial de vistas integrado: cambios y velocidades observadas, ventanas comparables,
  cobertura, deduplicación de fechas y caducidad de derivados. Concentración con mínimos
  de canales y distribuciones conocidas. Ver [temporal-metrics.md](temporal-metrics.md).
- Límites transaccionales, techo USD compartido y reserva, sublímites persistidos,
  créditos separados, incertidumbre tras envío y protección entre ejecuciones.
- Matriz integrada de 19 casos: recuperación por etapa, salida abrupta de un proceso,
  pérdida real de una conexión PostgreSQL de pruebas después de recibir respuesta,
  timeout/cancelación, presupuesto agotado, caducidad y dos workers competidores.
  No se repiten solicitudes de cobro incierto ni se duplican resultados confirmados.
  Corregido el contador del worker que informaba cero llamadas tras un error SQL posterior
  a las consultas; sigue distinguiéndose de los cargos confirmados.
  Ver [failure-verification.md](failure-verification.md) para evidencia y límites.
- Conciliación de saldos por cuenta, renovación observada y diferencias no atribuidas;
  comprobación al iniciar ejecución y tras consumo, sin convertir adicionales en asignación
  recurrente ni duplicar suscripciones USD. Reservas preparadas se revalidan antes del envío;
  las comprobaciones gratuitas cuentan en el límite de llamadas. Fechas originales intactas,
  concurrencia, caducidad y restauración comprobadas; migración `0008`.
  Ver [balance-reconciliation.md](balance-reconciliation.md) para controles y configuración pendiente.
- Recetas y escenarios manuales con varios canales, rangos, herramientas compartidas
  y resultados no evaluables cuando faltan supuestos. No crean ni producen canales.
- Creator Fit con contexto completo, costes fijos, unidades, capacidad y volumen;
  recetas inmutables asociadas a oportunidades, editor privado y copia de supuestos en
  nuevas evaluaciones. Revisiones pendientes visibles, sin validación de monetización.
  Receta genérica por defecto (IA local/API y código determinista, sin horas humanas)
  autoaplicada en cada evaluación cuando no hay una asignación propia; editable en
  Configuración y versionada en `production_recipe_defaults` (migración `0009`). Declara
  también capacidad real de sus 4 herramientas compartidas (topes de gasto LLM/Gemini de
  US$5/semana cada uno, holgura local sin cuello de botella), por lo que el score resuelve
  `88.75` y `viable` desde la primera evaluación de cada oportunidad nueva.
  Ver [creator-fit-rubric.md](creator-fit-rubric.md).
- Publicidad opcional con fuente, rango, vigencia, geografía y unidades por formato;
  configuración manual versionada, Market Score y fórmula combinada conectados al
  worker. Confianza y límites duros separados, sin proyectar cobros de canales nuevos.
  API/dashboard, preservación histórica y caducidad probadas. No hay benchmarks reales
  precargados. Ver [advertising-scoring.md](advertising-scoring.md).
- Explicaciones por afirmación con referencias y visualización en el dashboard.
  Adaptador LLM opcional para ordenar énfasis, validación de IDs, reservas USD durables,
  permisos de tratamiento separados, recuperación sin reenvío y alternativa determinista.
  Transporte real implementado y probado solo con HTTP simulado; desactivado, sin modelo,
  tarifa o permisos reales precargados. Ver [explanations.md](explanations.md).
- Comparación de versiones y posiciones históricas integrada en worker, API y panel.
  Distingue datos, métodos, supuestos y desplazamientos por otros candidatos; separa
  formatos, modos y ámbitos comparables, conserva empates y elimina clasificaciones
  dependientes de evidencia caducada. Migración y reintentos concurrentes probados.
  Ver [evaluation-history.md](evaluation-history.md).
- API operativa autenticada con detalle por trabajo, paginación y reintentos manuales
  concurrentes idempotentes; modo real bloqueado también tras una reanudación sintética.
  Validación sin devolver valores enviados. Panel con búsqueda, ordenación, filtros,
  fechas locales y estados diferenciados de configuración, presupuesto, caducidad,
  error y ausencia de resultados. Evidencia original y cambios de página probados.
  Ver [private-console.md](private-console.md).
- Docker local: construcción, migración, salud de API/dashboard/worker y persistencia
  tras recreación. Cero consultas a proveedores en la prueba de despliegue pausado.
- `pg_dump`/`pg_restore` en otra base temporal; pausa y revisión obligatorias,
  limpieza de vencidos, decisiones conservadas y reservas inciertas sin liberar.

Las tareas cerradas se corresponden con comprobaciones en `tests/test_execution.py`,
`test_evaluation.py`, `test_topics_backlog.py`, `test_pipeline.py`, `test_api_operations.py`,
`test_dashboard_navigation.py` y `scripts/smoke_compose.py`, además de las pruebas previas
de contratos, persistencia y conservación. La matriz documental está en
[provider-readiness.md](provider-readiness.md).

## Inteligencia de mercado (2026-10-20)

Implementadas las 13 tareas del plan `docs/superpowers/plans/2026-10-19-market-intel-backlog.md`
(spec 1: fuente DealBaron, clasificación, scores, backlog, API privada, pestaña Mercado,
enganches con retención/restauración/estado, scripts del piloto). Comprobado localmente:
`ruff`, `mypy` estricto y 626 pruebas con PostgreSQL temporal. Pendiente: revisión de los
Términos de Servicio de DealBaron (compuerta `NR_MARKET_INTEL_LIVE_ENABLED`), piloto live,
despliegue por digest y decisión sobre respaldar los datos de mercado (tarea 9.4).
Detalle en [market-intel.md](market-intel.md).

## Investigación de flujo (2026-10-20)

- Botón "Iniciar investigación de flujo" en Mercado para nichos `tentativo`; Claude Code
  atiende el encargo con búsqueda web (membresía, sin gasto de API) y entrega un dossier
  `dossier-v1` validado, inmutable y versionado. Detalles en `docs/flow-research.md`.
- Migración `0014`; las tablas nuevas cuentan como datos de investigación en el respaldo.
- Pendiente: la búsqueda web real no se prueba automáticamente; los términos de la membresía
  para uso automatizado no se han verificado.


## Pilotos de canal (2026-10-25)

- Un nicho con dossier pasa a «piloto»: NicheRadar congela el paquete (evidencia, presupuesto,
  reglas de parada), el canal lo baja desde el Mac, reporta por video y NicheRadar propone
  seguir o cerrar sin decidir solo. Guía: [pilots.md](pilots.md); diseño:
  [ecosistema-youtube.md](ecosistema-youtube.md).
- Migración `0015` (`pilots`, `pilot_videos`, `pilot_events`, `channel_tokens`), rutas
  `/api/v1/pilots`, tokens por canal, `scripts/channel_sync.py`, `scripts/pilots.py` y panel
  «Portafolio» de solo lectura. Rama `feat/experimentos-ecosistema`.
- **Desplegado el 2026-10-25** (release [013](release-20261025-013.md), migración `0015`).
  El Mac alcanza la API por túnel SSH (`scripts/pilots_tunnel.py`). Las tablas de pilotos se
  respaldan. Los datos de mercado y de flujo se respaldan desde la rama
  `feat/respaldo-datos-investigacion` (decisión 9.4, opción A; ver abajo).

## Respaldo de datos de investigación (2026-10-25, tarea 9.4, opción A)

- El snapshot acepta mercado y flujo (alcance `bootstrap+pilots+research`), mantiene el bloqueo
  de la evidencia de proveedores y de tablas no revisadas, y fija la revisión `0017`
  (subida desde `0016` al añadir `pilot_shorts_measurements`, ver `channel-report-v2`).
  Informa `delete_after` (`backup_deadline` ahora incluye mercado y flujo).
- Retención local en el Mac: 7 diarias + 4 semanales y borrado al vencer los datos
  (`backup_mac.py prune`, simulación por defecto). Detalle y procedimiento de custodia/rotación
  de la clave en [backup-restore.md](backup-restore.md).
- **Pendiente del propietario** (no ejecutado aquí): custodia externa de la clave, exclusión de
  la carpeta de respaldos de Time Machine/iCloud, y decidir si `backup`+`prune` se automatizan.
  Hasta entonces la tarea 9.4 sigue abierta. El cambio no está desplegado: el script de
  snapshot se envía al VPS en cada respaldo, pero no se ha ejecutado ningún respaldo real.

## Pendientes de integración y verificación

- Observar la calidad de las cohortes semánticas en más periodos antes de mantener la
  programación activa. Los topes se subieron el 2026-09-27 a 25/175/350
  (ejecución/semana/ciclo) como decisión consciente de invertir más, no como parche
  puntual; el radar permanece pausado.
- YouTube: piloto real completado el 2026-09-27 (2 unidades de cuota, 46 videos con
  idioma corregido a `different_language` que vidIQ había heredado como inglés). Falta
  observar más ciclos antes de considerarlo parte estable de la cadencia automática.
- Obtener benchmarks publicitarios autorizados y referencias reales calibradas mediante
  el piloto: no hay RPM inventados en el producto. Las recetas admiten estimaciones
  manuales; precios y rutas reales de producción todavía deben investigarse y probarse.
- LLM: piloto real completado el 2026-09-27 con modelo `gpt-6-luna` — 16 enriquecimientos
  reales exitosos (`llm_emphasis_only`), cero errores, US$0,003044 confirmados. Falta
  observar el comportamiento en más ciclos y con evaluaciones que sí lleguen a puntuarse.
- Respaldo cifrado inicial en el Mac y restauración aislada del estado del VPS comprobados
  el 2026-09-16. Faltan conservación de copias futuras con datos externos, programación,
  custodia externa de la clave y verificación de rollback. El script bloquea investigaciones
  y proveedores activos, incluso en modo sintético; no se ha reducido el alcance aprobado.
Corrección de `backup_deadline` probada y desplegada desde 003. Ver
  [backup-restore.md](backup-restore.md). Tarea 9.4 abierta.

Estas ampliaciones permanecen explícitas en la documentación. No hubo compras ni cargas
de videos; el piloto manual consumió 5 créditos y las ejecuciones programadas 25 en total.

## Acceso a Contabo

### Mejora de monitoreo posterior a la candidata desplegada

Desplegado en la candidata `v1-candidate-20260915-002` el desglose contable por ejecución,
separando unidades, confirmados, reservas e incertidumbres. Pruebas sintéticas
comprueban fallo posterior a un éxito, antigüedad, cobertura y ausencia de secretos.
Imágenes amd64 publicadas con nuevos digests y verificadas en Swarm; pausa, salud,
persistencia, login, monitoreo con fixtures en memoria y HTTPS/WebSocket correctos.
9.3 completa. Ver [release](release-20260915-002.md) y
[guía de monitoreo](operations-monitoring.md).

### Servicios desplegados

**Estado actual:** cuatro servicios `nicheradar-*` desplegados en el proyecto
`proy1-credito-riesgo`, según autorización posterior por límite de proyectos.
Migración 0008, imágenes 003 fijadas, límites efectivos, autenticación interna,
dashboard y persistencia comprobados. Radar live pausado después de una ocurrencia real;
los 21 servicios previos permanecen sin modificaciones.
El propietario actualizó DNS a `194.61.28.253`; ambos autoritativos y Cloudflare lo
confirmaron. HTTPS válido, Basic Auth y handshake WebSocket comprobados contra el
VPS, además del login interno y cinco vistas con AppTest. Tras la candidata 002,
la resolución normal del Mac ya llega al VPS y devuelve 401, no el 404 anterior;
sesión manual del propietario en navegador aún no observada.
Tareas 9.2 y 10.5 completas por estas pruebas, no solo por arrancar contenedores.
Ver [evidencia, acceso e incidencia del CLI](deployment-20260915.md).

### Registro de preparación anterior al despliegue

El propietario confirmó `nicheradar.soydavidrodriguez.com` y Docker Hub
`davidrodriguez2712`. Los repositorios públicos verificados son `nicheradar-backend` y
`nicheradar-dashboard`; visibilidad pública inicial autorizada, con futura privacidad
sujeta a configuración explícita. Ambos contienen la candidata `v1-candidate-20260915-001`;
publicación, digests remotos y arquitectura amd64 verificados. El pull por digest se comprobó
localmente usando capas en caché, no desde Contabo.
Consulta DNS de solo lectura del 2026-09-15: NS de BanaHosting y registro A del
subdominio en `66.225.221.53`, distinto del VPS previsto. No se cambió DNS.
Ver [preparación de release](release-dockerhub.md).
Las dos imágenes candidatas amd64 ya están construidas localmente y se verificó que
comparten la huella del código revisado. El contexto Docker ahora incluye solo entradas
de construcción permitidas. El smoke acepta imágenes preconstruidas sin reconstruir ni
cargar el `.env` del usuario. Ver [registro de candidata](release-20260915-001.md).
La tarea 9.2 permanece abierta: falta comprobar las imágenes en la configuración efectiva de Easypanel,
incluida compatibilidad del montaje de PostgreSQL del servicio administrado.

Tras instalar el propietario su clave pública, la inspección SSH de solo lectura funcionó
el 2026-09-13. Se observó arquitectura amd64, Ubuntu 22.04.5 LTS, Docker 28.3.2,
6 CPU, aproximadamente 8,7 GiB de RAM disponible y 338 GiB de disco disponible.
Había 21 servicios Swarm y 21 contenedores. La muestra se tomó poco después del arranque:
no valida carga sostenida ni justifica eliminar aplicaciones existentes.

UFW estaba inactivo y servicios PostgreSQL/Redis existentes publicaban puertos en todas
las interfaces. No se comprobó el firewall externo de Contabo ni accesibilidad desde
Internet. Se requiere revisar esa exposición antes del despliegue; no se modificó nada.
No se empleó VNC ni se cambiaron rutas, firewall o servicios. El radar no está desplegado.

El 2026-09-15 el propietario autorizó crear/configurar exclusivamente NicheRadar en
Easypanel. Nueva inspección de solo lectura: 7997 MiB de RAM disponible, 343 GiB
de disco libre, 21 servicios 1/1, casi dos días de uptime y carga media 0,05/0,02/0,01.
Easypanel efectivo es 2.34.0; su interfaz local responde HTTP 200. La ruta persistente
observada en un Postgres administrado es `/var/lib/postgresql/data`, por lo que no se
da por validado PostgreSQL 18 con ese montaje. No se modificó ningún recurso del VPS.
En ese momento faltaba acceso autenticado de administración del panel; se mantenían
46/54 tareas completas. El propietario configuró posteriormente el CLI y autorizó
el destino compartido; el estado actual y sus verificaciones figuran arriba.
