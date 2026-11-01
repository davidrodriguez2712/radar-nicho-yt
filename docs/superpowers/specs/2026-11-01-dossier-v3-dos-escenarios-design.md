# dossier-v3: tiempo humano en dos escenarios (calibración y régimen)

Fecha: 2026-11-01. Estado: borrador para revisión del propietario. Decisión de origen: el propietario aprobó el cambio
de contrato con dos escenarios (conversación del 2026-11-01).

## Problema

`dossier-v2` calcula los minutos humanos por video sumando `production_flow[].human_minutes_per_video` y la compuerta
`human_minutes` los compara con un máximo de 60 (`NR_GATE_MAX_HUMAN_MINUTES`). Esa cifra mezcla dos cosas distintas:

- **Calibración:** los primeros videos de un canal, cuando se construye y ajusta el flujo (prompts, correcciones de
  errores de producción). Es una inversión puntual de horas.
- **Régimen:** el flujo ya mapeado, donde el humano solo da la instrucción y valida.

Evidencia del propietario en `canal-historias` (reportada por él, no cronometrada con reloj, n pequeño):

| Concepto | Valor | Tipo |
|---|---|---|
| Dar la instrucción y elegir la postura | 10 min por video | declarado por el propietario |
| Validar el video privado y programarlo | 10 min por video | declarado por el propietario |
| **Régimen (suma)** | **20 min por video** | declarado, n sin contar |
| Primera semana | 2 a 3 horas por semana en errores de producción | declarado |
| Hoy | sin intervenciones por errores | declarado |

Consecuencia: las cuatro investigaciones de piloto y el catálogo de herramientas presupuestaron minutos humanos de
calibración como si fueran régimen (62–103 min en el nivel A, 49–88 en el B) y rompen la compuerta de 60 minutos sin que
el flujo estable lo haga.

Aclaración sobre el 90 % de automatización: no es una regla del dossier. `niche_reasons` compara `automation.value` del
**nicho del backlog**, y un valor desconocido no falla. Un porcentaje de automatización que el investigador estima en el
dossier no se valida contra ese umbral. Este cambio no lo toca.

## Objetivo

Que el dossier separe y valide dos cifras, y que la compuerta compare la correcta con evidencia, sin que "régimen" sea
una promesa sin respaldo.

## Diseño

### 1. Contrato `dossier-v3` (versión nueva; v2 queda de solo lectura)

Mismo patrón que v1 → v2: un `schema_version` nuevo, `dossier-v2` y `dossier-v1` se conservan para leer dossiers
guardados y las compuertas de autorización siguen funcionando con ellos. Los encargos nuevos exigen `dossier-v3`.

Cambios por paso de `production_flow` y de `automation_plan.stages`:
- `human_minutes_per_video` **pasa a significar solo régimen** (lo que compara la compuerta). El nombre no cambia, para
  que `authorization_reasons` y los dossiers v1/v2 sigan sumando lo mismo.
- Campo nuevo `calibration_minutes_per_video` (entero ≥ 0): minutos humanos por video durante la calibración. Debe ser
  ≥ `human_minutes_per_video` (la calibración nunca es más barata que el régimen).

Objeto nuevo de nivel superior `calibration`:
- `videos` (entero 1 a 12): cuántos videos dura la calibración.
- `setup_hours` (≥ 0): horas únicas de preparación del flujo (plantillas, voz de referencia, scripts), fuera del costo por
  video.
- `exit_criterion`: `{ max_minutes_per_video, consecutive_videos }`. Se pasa a régimen cuando tantos videos seguidos
  se miden por debajo del máximo. Obligatorio.
- `total_hours` (derivado, no declarado): `setup_hours + videos × Σ calibration_minutes_per_video / 60`.

Objeto nuevo `steady_state_evidence`:
- `basis`: `measured` (cronometrado en un canal del propietario), `mapped_flow_equivalent` (un canal propio con flujo ya
  mapeado de mismo formato e idioma) o `estimate` (nadie lo hizo todavía).
- `reference_channel` (obligatorio salvo `estimate`): id del canal (p. ej. `canal-historias`).
- `reference_minutes_per_video` y `reference_sample_videos` (obligatorios con `measured`).
- `format_match`: texto breve que declara si formato e idioma coinciden con el canal de referencia y qué cambia.

### 2. Compuerta

- `human_minutes` compara **solo el régimen** (`Σ human_minutes_per_video`) con el máximo de 60, como hoy.
- Nueva comprobación `calibration_hours`: `calibration.total_hours` contra `NR_GATE_MAX_CALIBRATION_HOURS`
  (por defecto 40; **supuesto inicial, no medido**: el propietario reportó 2 a 3 h por semana en la primera semana).
  Misma excepción registrada que las demás compuertas.
- Regla de evidencia: con `basis = estimate`, el dossier no puede recomendar `go` (solo `go_with_conditions` o
  `no_go`), y entre sus `conditions` debe estar el `exit_criterion`. Con `measured` o `mapped_flow_equivalent` puede
  recomendar `go`. Esto evita aprobar con un régimen que nadie ha visto.
- `authorization_reasons` (autorización del piloto) repite estas comprobaciones sobre el dossier guardado; un dossier v1
  o v2 se evalúa como antes (su total se trata como régimen).

### 3. Skill `flow-research` y documentación

- La skill instruye separar calibración y régimen, a citar el canal de referencia y a no presupuestar régimen sin base.
- `docs/contracts/dossier-v3.md` nuevo; `docs/contracts/dossier-v2.md` queda con una nota de legado;
  `docs/flow-research.md` y el catálogo de herramientas (`docs/investigacion-herramientas/CATALOGO-CONSOLIDADO.md`)
  reescriben sus tablas de minutos humanos en dos columnas.
- El dashboard (panel de flujo) muestra ambos escenarios y la evidencia de régimen.

### 4. Datos del canal de referencia

El valor de `canal-historias` (20 min de régimen) entra como evidencia `measured` con `reference_sample_videos` que el
propietario indique; si no se conoce, se declara `mapped_flow_equivalent`. El propietario puede cronometrar el próximo
video para fijar el dato.

## Fuera de alcance

- Cambiar el umbral de 60 minutos o el de automatización del backlog.
- Medir automáticamente el tiempo humano real (queda como medición manual del propietario).
- Migrar dossiers v1 y v2 guardados.
- La integración de subnichos en el dashboard (spec aparte).

## Compatibilidad y despliegue

- Sin cambios de esquema de base de datos: los dossiers se guardan como JSON; la validación vive en `contracts.py`.
- Release nuevo (034 o siguiente): código de la API, dashboard y la skill. Despliegue con aprobación del propietario.
- Los encargos pendientes con `dossier-v2` se rechazan con un mensaje que indica pasar a v3 (igual que hoy v1 → v2).

## Riesgos y casos a probar

1. **Régimen sin evidencia que pasa la compuerta:** con `estimate` y `go`, debe rechazarse; con `estimate` y
   `go_with_conditions` sin el criterio de salida entre las condiciones, también.
2. **Calibración menor que régimen** en un paso: error de validación.
3. **Formato distinto al canal de referencia** (`format_match` vacío o que declare diferencia sin explicarla): error.
4. **Dossier v2 guardado** pasa por `authorization_reasons` sin cambio de resultado.
5. **Dinero ≠ tiempo de máquina:** el tiempo de máquina sigue sin contar como minutos humanos (regla del PR #64).
6. **`calibration.total_hours`** se deriva; si el payload lo trae declarado, se rechaza (campo no permitido).

## Decisiones del propietario (2026-11-01, spec aprobado)

1. `NR_GATE_MAX_CALIBRATION_HOURS` por defecto en 40 h (propuesta aceptada con el spec; supuesto no medido).
2. La calibración termina tras 3 videos seguidos bajo el máximo, con salida por defecto en 60 min por video (propuesta
   aceptada con el spec).
3. `canal-historias`: los últimos 10 videos tomaron ~20 min de régimen (10 + 10), salvo que el propietario decida un
   cambio grande en algún frente del flujo. Se declara `measured`, `reference_sample_videos = 10`, tiempo **declarado
   por el propietario, no cronometrado con reloj**.

## Nota sobre el porcentaje de automatización

El contrato ya captura por etapa `mode` (manual, semi, auto), herramientas con su interfaz, entradas, salidas, puerta de
calidad, modo de fallo, reintentos, minutos humanos y qué sigue siendo humano (`automation_plan.stages`). **No deriva
ningún porcentaje:** el 90 % del backlog es otra fuente (puntuación del nicho). Calcular un porcentaje del dossier a
partir de las etapas queda fuera de este spec y se trata como seguimiento si el propietario lo pide.
