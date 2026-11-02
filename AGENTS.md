# Guía de agentes — NicheRadar

Este archivo aplica a todo el repositorio. Es el punto de entrada para cualquier agente
que continúe el proyecto. El producto es un radar privado de oportunidades de YouTube en
inglés que analiza videos largos y Shorts por separado. No crea canales, no publica videos
y no convierte una puntuación en una decisión automática.

## Lectura obligatoria antes de cambiar código

Lee en este orden:

1. `[INICIO]` [`README.md`](README.md): visión general, comandos y mapa documental.
2. `[ESTADO-ACTUAL]` [`docs/implementation-status.md`](docs/implementation-status.md):
   qué está implementado, probado, desplegado y pendiente.
3. `[TAREAS]`
   [`openspec/changes/continuous-niche-discovery/tasks.md`](openspec/changes/continuous-niche-discovery/tasks.md):
   checklist verificable. Hay 54/55 tareas cerradas; solo 9.4 sigue abierta.
4. `[DISEÑO]`
   [`openspec/changes/continuous-niche-discovery/design.md`](openspec/changes/continuous-niche-discovery/design.md):
   decisiones de arquitectura, datos, métricas, presupuesto y ejecución durable.
5. `[PRODUCCIÓN]` [`docs/live-operation.md`](docs/live-operation.md) y
   `[RELEASE-ACTIVA]` [`docs/release-20261001-011.md`](docs/release-20261001-011.md):
   estado operativo y digests desplegados.
6. Lee después el documento especializado de la integración o componente que vayas a
   modificar; el índice completo está al final de este archivo.

Cuando haya una discrepancia, comprueba primero el código y las pruebas. Las especificaciones
OpenSpec describen el comportamiento requerido; `docs/implementation-status.md` y la release
más reciente describen el estado comprobado. Los documentos de releases anteriores son
históricos y no representan la configuración activa.

## Estado actual comprobado

- Fecha de este contexto: 1 de octubre de 2026.
- Cambio OpenSpec activo: `continuous-niche-discovery`, 54/55 tareas cerradas.
- Único pendiente formal: tarea 9.4, respaldo/restauración/rollback compatible con la
  conservación de datos externos futuros.
- Release activa: `v1-candidate-20261001-011` (Home del dashboard con panorama de
  oportunidades y ganancia mensual estimada por canal real × RPM investigado − costo
  real; sin migración de esquema).
- Despliegue: proyecto Easypanel `proy1-credito-riesgo`, servicios
  `nicheradar-api`, `nicheradar-worker`, `nicheradar-dashboard` y `nicheradar-db`.
- Host SSH: `root@194.61.28.253`, clave local `~/.ssh/id_ed25519`; no hay alias confirmado.
- Dominio: `nicheradar.soydavidrodriguez.com`, protegido por HTTPS y Basic Auth.
- Runtime: modo `live`, radar pausado. Mantenerlo pausado durante cambios y verificaciones.
- vidIQ: integración real conectada. Topes subidos a 25/175/350 créditos
  (ejecución/semana/ciclo) el 2026-09-27; no eleves límites para evitar el tope ni
  asumas que esos valores siguen vigentes sin una lectura actual.
- YouTube Data API: `videos.list` conectada, **habilitada y piloteada** el 2026-09-27
  (2 unidades reales de cuota, 46 videos con idioma corregido). Cuotas 2/10/40
  (ejecución/semana/mes). El radar sigue pausado. `.env.example` contiene únicamente
  nombres y ejemplos; nunca debe contener el secreto.
- LLM: **habilitado y piloteado** el 2026-09-27, modelo `gpt-6-luna`, tope US$5/semana.
  16 enriquecimientos reales exitosos (`llm_emphasis_only`), cero errores,
  US$0,003044 confirmados. Ver [piloto](docs/youtube-llm-pilot-20260927.md). Publicidad
  real sigue sin referencias calibradas.
- Última suite completa: 356 pruebas aprobadas con PostgreSQL temporal; Ruff y mypy sin
  errores. Las pruebas automatizadas no llaman proveedores externos.
- El checkout puede no incluir metadatos Git utilizables. Verifica antes de ejecutar
  operaciones Git y no presupongas que existe historial local.

## Cómo funciona el sistema

Flujo principal:

```text
catálogo versionado
  → planificación y rotación de familias
  → consultas vidIQ presupuestadas
  → enriquecimiento opcional YouTube videos.list
  → normalización con procedencia y caducidad
  → muestreo y cohortes separadas long/Shorts
  → agrupamiento temático y relevancia semántica local
  → métricas de mercado, historia y concentración
  → Market Score / Creator Fit / confianza
  → evaluaciones versionadas
  → backlog, decisiones y escenarios manuales
```

PostgreSQL contiene identidades, observaciones, políticas, solicitudes, reservas, costes,
jobs, checkpoints, cohortes, evaluaciones y decisiones. El worker reclama jobs con lease y
heartbeat. Las etapas son planificación, consulta, enriquecimiento, normalización, cohorte,
métricas, evaluación y backlog. Cada solicitud externa pasa por políticas, caché, tarifa,
reserva transaccional y conciliación. Un timeout posterior al envío puede quedar como
`unknown_charge` y no se reintenta a ciegas.

vidIQ descubre candidatos. YouTube no descubre nichos: recibe únicamente IDs de candidatos
vidIQ, consulta hasta 50 por lote y puede completar título, descripción, publicación,
vistas, duración e idioma declarado. La clasificación long/Shorts y los campos exclusivos
de vidIQ conservan su fuente. Ambos proveedores comparten identidad canónica de YouTube,
pero mantienen observaciones, políticas, solicitudes y costes separados.

Los datos externos tienen procedencia y `retain_until`. La conservación operativa actual es
de siete días. No elimines estos controles ni presentes evidencia caducada como vigente.

## Archivos de código principales

- `[CONFIG]` `src/nicheradar/config.py`: variables, validación y estado público sin secretos.
- `[CONTRATOS]` `src/nicheradar/integrations/contracts.py`: operaciones, lotes, costes,
  cobertura, procedencia y errores de proveedor.
- `[VIDIQ]` `src/nicheradar/integrations/vidiq.py` y
  `src/nicheradar/integrations/vidiq_cli.py`: adaptador MCP y diagnóstico local.
- `[YOUTUBE]` `src/nicheradar/integrations/youtube.py`,
  `src/nicheradar/integrations/youtube_cli.py` y
  `src/nicheradar/services/youtube_enrichment.py`: adaptador, diagnóstico, tarifa y límites.
- `[GATEWAY]` `src/nicheradar/services/gateway.py`: políticas, caché, reservas y persistencia
  de solicitudes externas.
- `[PIPELINE]` `src/nicheradar/workers/pipeline.py`: orquestación y combinación de evidencia.
- `[COLA]` `src/nicheradar/workers/queue.py`: etapas, leases, reintentos y finalización.
- `[WORKER]` `src/nicheradar/workers/main.py`: ciclo de worker y recuento de llamadas.
- `[IDENTIDADES]` `src/nicheradar/repositories/core.py`: identidad canónica de canales/videos.
- `[ESQUEMA]` `src/nicheradar/repositories/schema_v1.py` y `migrations/`: esquema y migraciones.
- `[API]` `src/nicheradar/api.py`: API privada autenticada y controles operativos.
- `[DASHBOARD]` `src/nicheradar/dashboard.py`: interfaz privada en español.
- `[ACTIVACIÓN]` `scripts/activate_live.py`: políticas y preflight live; conserva la pausa.
- `[EASYPANEL]` `scripts/easypanel_stage.mjs`: inspección, despliegue, probes y activaciones
  acotadas. No imprimir respuestas crudas que puedan contener secretos.
- `[SMOKE]` `scripts/smoke_compose.py`: prueba aislada de imágenes exactas y persistencia.

## Reglas que no deben romperse

- Mantén el arranque local en modo sintético y pausado.
- El scraper de mercado tiene pausa propia (`market_intel_schedule`): no la conectes a
  `NR_RADAR_PAUSED`, no la despauses por efecto lateral de una migración o despliegue y no
  actives `NR_MARKET_INTEL_LIVE_ENABLED` sin la revisión de Términos de Servicio. Sus cifras son
  autodeclaradas (`seller_declared`) y un ingreso `$0` no es evidencia.
- Nunca escribas claves, tokens, contraseñas o valores reales en `.env.example`, Markdown,
  argumentos, fixtures, logs o respuestas. Los secretos reales viven solo en `.env` privado
  o en el entorno secreto de Easypanel.
- No llames proveedores reales desde pruebas. Una llamada real debe ser explícita, acotada,
  presupuestada y estar documentada con su operación y consumo.
- No habilites YouTube solo porque exista `NR_YOUTUBE_API_KEY`: el preflight también exige
  alcance estable, fecha de validación, límites positivos y políticas habilitadas.
- No despauses el radar como efecto lateral de una migración, despliegue o activación de
  políticas. Comprueba la pausa al terminar.
- No cambies, reinicies ni elimines servicios ajenos a `nicheradar-*` en el proyecto
  compartido de Easypanel.
- No publiques PostgreSQL, API o dashboard directamente. Conserva red interna, HTTPS,
  autenticación de aplicación y Basic Auth del proxy.
- No compres créditos, cambies planes, subas contenido, crees canales ni selecciones
  oportunidades automáticamente.
- No inventes RPM, ingresos, idioma, formato, copyright, monetización o métricas faltantes.
  Usa estados `unknown`, `insufficient_evidence` o `uncalibrated` cuando corresponda.
- Conserva la separación de long y Shorts, datos sintéticos y reales, evidencia externa y
  decisiones propias, consumo USD y créditos incluidos, y scores frente a confianza.
- No liberes reservas inciertas sin evidencia de no cobro. No repitas solicitudes externas
  después de un fallo ambiguo.
- **Diseño (Figma):** el diseño de NicheRadar vive en un solo archivo, «NicheRadar · Rediseño total (5
  propuestas)» (<https://www.figma.com/design/JmBvlfNURrV226WOZLuCEz/NicheRadar-%C2%B7-Redise%C3%B1o-total--5-propuestas->,
  `fileKey` `JmBvlfNURrV226WOZLuCEz`). Las pantallas móviles están en la página «M · Móvil» (M1 a M12; M9 a M12 son
  Subnichos: lista, ficha, informe con calibración y régimen, y autorizar piloto desde un subnicho). **El diseño es
  móvil**, en español llano, con la paleta granate `#be123c` sobre fondo `#fff8f5` y Inter. Todo trabajo de diseño va en
  ese archivo y reutiliza su estilo: no crees archivos de Figma nuevos ni pantallas de escritorio sin preguntar al
  propietario. El dashboard actual de producción sigue siendo Streamlit; el Figma es la propuesta de rediseño.
- Antes de editar OpenSpec, usa el flujo correspondiente en `.agents/skills/`. Al implementar
  el cambio activo, sigue `.agents/skills/openspec-apply-change/SKILL.md`.

## Verificación local

Instalación y controles estáticos:

```sh
uv sync --locked
uv lock --check
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src apps tests
openspec validate continuous-niche-discovery --strict
```

Suite completa con PostgreSQL temporal de Postgres.app:

```sh
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin \
  uv run pytest --tb=short
```

Para un cambio pequeño, ejecuta primero sus pruebas enfocadas y después la suite completa si
afecta pipeline, persistencia, presupuesto, ejecución durable, API, despliegue o contratos.
No uses una base real. No configures credenciales de proveedores en el entorno de pytest.

## Operación y despliegue

Inspección segura:

```sh
node scripts/easypanel_stage.mjs inspect
node scripts/easypanel_stage.mjs rollouts
node scripts/easypanel_stage.mjs public-probe
node scripts/easypanel_stage.mjs probe check
node scripts/easypanel_stage.mjs scheduled-evidence
```

La release activa y sus digests están en
[`docs/release-20261001-011.md`](docs/release-20261001-011.md). No despliegues etiquetas
mutables: usa digests verificados. Antes de sustituir una imagen, confirma imagen anterior,
entorno `live`, `NR_RADAR_PAUSED=true`, recursos, puertos, montajes y autenticación. Después
comprueba rollout `completed`, HTTPS, rechazo anónimo, WebSocket, comunicación interna y
pausa final.

Activación futura de YouTube, solo después de colocar la clave en `.env` privado:

```sh
uv run nicheradar-youtube --check-video <VIDEO_ID_PUBLICO>
node scripts/easypanel_stage.mjs configure-youtube-paused
node scripts/easypanel_stage.mjs activate-live-db
```

El primer comando realiza una llamada real y consume una unidad. Copia su `validated_at` a
`NR_YOUTUBE_CONNECTION_VALIDATED_AT`. Los comandos remotos mantienen el radar pausado. Haz
un piloto acotado separado antes de dejar la programación activa.

## Índice etiquetado de Markdown

### Entrada, estado y especificación

- `[INICIO]` [`README.md`](README.md): visión general, desarrollo, pruebas e índice corto.
- `[PILOTOS]` [`docs/pilots.md`](docs/pilots.md) y [`docs/ecosistema-youtube.md`](docs/ecosistema-youtube.md): pilotos de canal, contratos en `docs/contracts/`.
- `[AGENTES]` [`AGENTS.md`](AGENTS.md): contexto y reglas para continuar el proyecto.
- `[ESTADO-ACTUAL]` [`docs/implementation-status.md`](docs/implementation-status.md):
  inventario de lo implementado, evidencia y pendientes.
- `[PROPUESTA]`
  [`openspec/changes/continuous-niche-discovery/proposal.md`](openspec/changes/continuous-niche-discovery/proposal.md):
  objetivo y alcance original del cambio.
- `[DISEÑO]`
  [`openspec/changes/continuous-niche-discovery/design.md`](openspec/changes/continuous-niche-discovery/design.md):
  arquitectura y decisiones técnicas completas.
- `[TAREAS]`
  [`openspec/changes/continuous-niche-discovery/tasks.md`](openspec/changes/continuous-niche-discovery/tasks.md):
  checklist de implementación y verificación.
- `[SPEC-DESCUBRIMIENTO]`
  [`openspec/changes/continuous-niche-discovery/specs/continuous-discovery/spec.md`](openspec/changes/continuous-niche-discovery/specs/continuous-discovery/spec.md):
  descubrimiento continuo y formación de muestras.
- `[SPEC-BACKLOG]`
  [`openspec/changes/continuous-niche-discovery/specs/opportunity-backlog/spec.md`](openspec/changes/continuous-niche-discovery/specs/opportunity-backlog/spec.md):
  backlog, decisiones e historial.
- `[SPEC-EVALUACIÓN]`
  [`openspec/changes/continuous-niche-discovery/specs/opportunity-evaluation/spec.md`](openspec/changes/continuous-niche-discovery/specs/opportunity-evaluation/spec.md):
  métricas, puntuación, explicaciones y confianza.
- `[SPEC-PROVEEDORES]`
  [`openspec/changes/continuous-niche-discovery/specs/provider-data-quality/spec.md`](openspec/changes/continuous-niche-discovery/specs/provider-data-quality/spec.md):
  contratos, calidad, procedencia, políticas y conservación.
- `[SPEC-OPERACIÓN]`
  [`openspec/changes/continuous-niche-discovery/specs/radar-operations/spec.md`](openspec/changes/continuous-niche-discovery/specs/radar-operations/spec.md):
  worker, programación, API, dashboard y despliegue.
- `[SPEC-PRESUPUESTO]`
  [`openspec/changes/continuous-niche-discovery/specs/resource-budgeting/spec.md`](openspec/changes/continuous-niche-discovery/specs/resource-budgeting/spec.md):
  límites, créditos, gasto y escenarios de recursos.

### Proveedores e integraciones

- `[PROVEEDORES]` [`docs/provider-readiness.md`](docs/provider-readiness.md): matriz de
  operaciones, costes, consulta, almacenamiento, derivados y estado de habilitación.
- `[VIDIQ-CONEXIÓN]` [`docs/vidiq-connection.md`](docs/vidiq-connection.md): configuración,
  diagnóstico MCP y manejo de la clave propia.
- `[VIDIQ-CONTRATO]`
  [`docs/vidiq-contract-20260921.md`](docs/vidiq-contract-20260921.md): contrato observado,
  catálogo de herramientas, parámetros y costes.
- `[YOUTUBE]` [`docs/youtube-enrichment.md`](docs/youtube-enrichment.md): funcionamiento,
  precedencia de campos, cuotas, políticas y activación pausada.
- `[PILOTO-PREPARACIÓN]` [`docs/pilot-readiness.md`](docs/pilot-readiness.md): preflight y
  requisitos antes de una ejecución real.
- `[PILOTO-VIDIQ]` [`docs/vidiq-pilot-20260922.md`](docs/vidiq-pilot-20260922.md): informe
  agregado del piloto real aislado.
- `[CICLO-VIDIQ]`
  [`docs/vidiq-scheduled-20260922.md`](docs/vidiq-scheduled-20260922.md): primer ciclo
  programado observado.
- `[CICLO-AMPLIADO]`
  [`docs/vidiq-scheduled-expanded-20260922.md`](docs/vidiq-scheduled-expanded-20260922.md):
  ejecución ampliada, reevaluación semántica, consumo y cobertura.
- `[SALDOS]` [`docs/balance-reconciliation.md`](docs/balance-reconciliation.md): saldo
  renovable/adicional, ciclos, conciliación y diferencias externas.

### Descubrimiento, métricas y evaluación

- `[DESCUBRIMIENTO]` [`docs/discovery-operation.md`](docs/discovery-operation.md): rotación,
  expansión de consultas, actualización y continuación por recibos.
- `[AGRUPAMIENTO]` [`docs/topic-grouping.md`](docs/topic-grouping.md): embeddings ONNX,
  relevancia, grupos, ruido, ambigüedad y fallback.
- `[MÉTRICAS-TEMPORALES]` [`docs/temporal-metrics.md`](docs/temporal-metrics.md): historia de
  vistas, cambios, concentración, ventanas y mínimos.
- `[CREATOR-FIT]` [`docs/creator-fit-rubric.md`](docs/creator-fit-rubric.md): recetas,
  rúbrica, costes, capacidad y límites de interpretación.
- `[PUBLICIDAD]` [`docs/advertising-scoring.md`](docs/advertising-scoring.md): benchmarks
  opcionales, puntuación combinada y confianza.
- `[EXPLICACIONES]` [`docs/explanations.md`](docs/explanations.md): afirmaciones trazables,
  evidencia y enriquecimiento LLM opcional.
- `[HISTORIAL]` [`docs/evaluation-history.md`](docs/evaluation-history.md): comparación de
  evaluaciones y posiciones históricas.
- `[CONSOLA]` [`docs/private-console.md`](docs/private-console.md): contratos de la API,
  filtros, dashboard y estados visibles.

### Ejecución, fallos y conservación

- `[FALLOS]` [`docs/failure-verification.md`](docs/failure-verification.md): recuperación,
  concurrencia, cobro incierto, caducidad y límites de reintento.
- `[MONITOREO]` [`docs/operations-monitoring.md`](docs/operations-monitoring.md): estado,
  antigüedad, consumo y diagnóstico operativo.
- `[OPERACIÓN-LIVE]` [`docs/live-operation.md`](docs/live-operation.md): guía vigente para
  inspección, lectura de resultados, pausa y retorno.
- `[MERCADO]` [`docs/market-intel.md`](docs/market-intel.md): scraper de fichas de canales en
  venta, scores del backlog de nichos, pausa propia y retención de 6 meses.
- `[MERCADO-PILOTO]` [`docs/market-intel-pilot.md`](docs/market-intel-pilot.md): compuerta de
  Términos de Servicio y pasos del piloto live.
- `[FLUJO]` [`docs/flow-research.md`](docs/flow-research.md): investigación de flujo, dossier
  por Claude Code desde un nicho tentativo.
- `[RESPALDO]` [`docs/backup-restore.md`](docs/backup-restore.md): respaldo cifrado,
  restauración aislada, limpieza y rollback. Contiene el único pendiente formal 9.4.

### Despliegue y releases

- `[EASYPANEL]` [`docs/deployment-easypanel.md`](docs/deployment-easypanel.md): servicios,
  red, dominio, recursos, secretos, migraciones y verificación remota.
- `[DESPLIEGUE-INICIAL]` [`docs/deployment-20260915.md`](docs/deployment-20260915.md):
  evidencia histórica de preparación y primer despliegue en Contabo.
- `[DOCKER-HUB]` [`docs/release-dockerhub.md`](docs/release-dockerhub.md): construcción,
  smoke, publicación y fijación por digest.
- `[RELEASE-001]` [`docs/release-20260915-001.md`](docs/release-20260915-001.md): primera
  candidata publicada; histórica.
- `[RELEASE-002]` [`docs/release-20260915-002.md`](docs/release-20260915-002.md): monitoreo
  desplegado; histórica.
- `[RELEASE-003]` [`docs/release-20260922-003.md`](docs/release-20260922-003.md): conexión
  live y controles de piloto; histórica.
- `[RELEASE-004]` [`docs/release-20260922-004.md`](docs/release-20260922-004.md): flujo
  ampliado y herencia trazable de idioma; histórica.
- `[RELEASE-005]` [`docs/release-20260922-005.md`](docs/release-20260922-005.md): relevancia
  semántica ONNX; rollback inmediato de la release activa.
- `[RELEASE-006]`
  [`docs/release-20260923-006.md`](docs/release-20260923-006.md): YouTube opcional;
  histórica, rollback de la release activa.
- `[RELEASE-007]`
  [`docs/release-20260926-007.md`](docs/release-20260926-007.md): corrección de interfaz
  del dashboard, tema de colores; histórica, rollback de la release activa.
- `[RELEASE-008]`
  [`docs/release-20260927-008.md`](docs/release-20260927-008.md): rediseño parcial y
  activación de YouTube/LLM; histórica, rollback de la release activa.
- `[RELEASE-009]`
  [`docs/release-20260927-009.md`](docs/release-20260927-009.md): rediseño completo del
  dashboard; histórica, rollback de la release activa.
- `[RELEASE-010]`
  [`docs/release-20260928-010.md`](docs/release-20260928-010.md): receta de producción
  por defecto autoaplicada, capacidad real de herramientas compartidas, migración `0009`;
  histórica, rollback de la release activa.
- `[RELEASE-011-ACTIVA]`
  [`docs/release-20261001-011.md`](docs/release-20261001-011.md): Home del dashboard con
  panorama de oportunidades, ganancia mensual estimada por canal real × RPM investigado,
  digests activos, verificaciones y retorno.
- `[PILOTO-YOUTUBE-LLM]`
  [`docs/youtube-llm-pilot-20260927.md`](docs/youtube-llm-pilot-20260927.md): primera
  ejecución real con ambos proveedores, evidencia agregada sin secretos.

## Cómo dejar contexto para el siguiente agente

Al terminar un cambio sustancial:

1. Actualiza el código, pruebas y artefactos OpenSpec correspondientes.
2. Actualiza `docs/implementation-status.md` con hechos comprobados, fecha y pendientes.
3. Si hubo despliegue, crea una release nueva; no reescribas la evidencia histórica de una
   release anterior. Actualiza `README.md`, `docs/deployment-easypanel.md` y
   `docs/live-operation.md` para señalar la release activa.
4. Registra comandos de verificación y resultados agregados, sin secretos ni respuestas
   crudas de proveedores.
5. Mantén este `AGENTS.md` sincronizado cuando cambien arquitectura, release activa,
   estado de integraciones, pruebas o rutas documentales.
