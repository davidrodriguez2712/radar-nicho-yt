# Contrato dossier-v3

Versión vigente del dossier de investigación de flujo. Reemplaza a `dossier-v2` (ver
[`dossier-v2.md`](dossier-v2.md), solo lectura de lo guardado). Los campos de v2 (derechos, plan de automatización,
presupuesto, competidores, herramientas) no cambian; v3 añade el tiempo humano en dos escenarios.

## Qué cambia respecto a v2

| Campo | Cambio |
|---|---|
| `schema_version` | `"dossier-v3"` |
| `production_flow[].human_minutes_per_video` | Significa **régimen** (flujo ya mapeado). El total se deriva (suma) y es lo que compara la compuerta `human_minutes` |
| `verdict.conditions` | Lista de condiciones (obligatoria; no vacía con `go_with_conditions`) |
| `calibration` | Objeto nuevo: `videos` (1 a 12), `setup_hours` (≥ 0), `exit_criterion` {`max_minutes_per_video`, `consecutive_videos`, `statement`}, `minutes_by_step[]` {`step`, `minutes_per_video`} |
| `steady_state_evidence` | Objeto nuevo: `basis` (`measured`, `mapped_flow_equivalent`, `estimate`), `reference_channel`, `reference_minutes_per_video`, `reference_sample_videos`, `format_match` |

## Reglas

1. `minutes_by_step` tiene un valor por cada paso de `production_flow` (sin repetir ni omitir) y ninguno es menor
   que el régimen de ese paso.
2. Horas de calibración (derivadas, no declaradas): `setup_hours + videos × Σ minutes_by_step / 60`, redondeado a
   2 decimales. Declarar `total_hours` es un campo no permitido.
3. `basis` distinto de `estimate` exige `reference_channel`; `measured` exige además `reference_minutes_per_video` y
   `reference_sample_videos`.
4. Con `basis = estimate` no se puede recomendar `go`; con `go_with_conditions`, `calibration.exit_criterion.statement`
   debe estar literalmente en `verdict.conditions`.

## Compuertas

Además de las de v2: `NR_GATE_MAX_CALIBRATION_HOURS` (40 por defecto; **supuesto inicial, no medido**) compara las horas
de calibración derivadas. Un dossier con `go` o `go_with_conditions` se rechaza (`422`, ruta `verdict.recommendation`)
si el régimen supera `NR_GATE_MAX_HUMAN_MINUTES` (60) o la calibración supera el tope, salvo `gate_override` registrado.
`no_go` siempre se acepta. Al autorizar el piloto se repiten las comprobaciones; un dossier v1 o v2 guardado se evalúa
como antes (su total cuenta como régimen y no tiene calibración).

## Evidencia de referencia

`canal-historias`: ~20 min de régimen por video (10 de instrucción y postura + 10 de validación y programación) en los
últimos 10 videos; primera semana: 2 a 3 horas por semana en errores de producción, hoy ninguna. Montaje inicial del canal: unas 12 horas
("me debe haber tomado 12 horas"; incluye construir el pipeline desde cero). Tiempos declarados por el
propietario, no cronometrados con reloj.
