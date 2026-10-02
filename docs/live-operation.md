# Operación live acotada

La release `v1-candidate-20261001-011` está configurada en modo `live` y pausada. Suma al
Home del dashboard un panorama de oportunidades ordenado por madurez real y una ganancia
mensual estimada (canal mejor/peor real × RPM investigado − costo real), sin migración de
esquema; ver [release 011](release-20261001-011.md). La release 010 añadió la receta de
producción por defecto (migración `0009`, aditiva) autoaplicada en cada evaluación; ver
[creator-fit-rubric.md](creator-fit-rubric.md) y [release 010](release-20260928-010.md). Las
ejecuciones del 22 de septiembre comprobaron planificador, worker, persistencia y
reprocesamiento desde caché con límites de 20 créditos por ejecución, 25 por semana y
100 por ciclo.

## Comprobación antes de ejecutar

Desde el checkout autorizado, con el token de Easypanel y la clave vidIQ únicamente en el
`.env` privado:

```sh
node scripts/easypanel_stage.mjs inspect
node scripts/easypanel_stage.mjs activate-live-db
```

`activate-live-db` es idempotente para políticas y deja el calendario pausado. Con YouTube
apagado debe devolver `ready: true`, sin bloqueos, 19 políticas y los tres límites
anteriores. Con YouTube activo añade cinco políticas y sus límites de cuota. No imprime tokens.
El consumo semanal actual es 25; una nueva operación pagada queda aplazada hasta el
siguiente periodo aunque haya saldo en la cuenta.

## Una ocurrencia observada

```sh
node scripts/easypanel_stage.mjs run-scheduled-once
node scripts/easypanel_stage.mjs scheduled-evidence
```

El primer comando reanuda el radar, espera una nueva ocurrencia y ejecuta la pausa en un
bloque `finally`. Solo acepta como éxito un trabajo `live` terminado en `succeeded` o
`partial` y exige comprobar la pausa final. Si el comando termina de forma anómala, hay que
pausar desde la API privada antes de cualquier diagnóstico adicional.

El segundo comando es de solo lectura y devuelve estados, operaciones, consumo, saldos,
snapshot del backlog y configuración del calendario, sin cargas externas ni secretos.

## Lectura del resultado actual

La ejecución ampliada terminó `partial` con `run_budget_exhausted`: consumió 20 créditos,
procesó 100 videos y creó cohortes de 50 largos y 50 Shorts. Una reevaluación posterior
reutilizó esas observaciones, consumió cero créditos pagados y terminó
`period_budget_exhausted`. El primer backlog contiene dos entradas reales sin puntuación.
La reevaluación semántica 005 produjo ocho: confirmó cuatro largos dentro de la ventana,
dejó cinco Shorts fuera de ella y marcó cuatro grupos individuales como ruido. Este estado
expresa evidencia todavía insuficiente, no ausencia de oportunidades.

La release 005 incluye un modelo ONNX local fijado y verifica relevancia semántica cuando
el filtro léxico queda desconocido. El corte inicial 0,35 fue medido sobre evidencia
retenida y controles, pero todavía requiere observación del pipeline completo. El radar
permanece pausado y no se deben elevar límites para eludir el tope semanal.

Antes de mantener el calendario sin pausa hay que observar más periodos, revisar la calidad
de las cohortes semánticas y decidir la cadencia. Siguen pendientes la calibración de scores
y la conservación de futuros respaldos con datos externos. YouTube Data API ya está
conectada como enriquecimiento opcional de candidatos vidIQ. Permanece apagada hasta
configurar una clave propia, comprobarla con una consulta de una unidad y registrar sus
límites; publicidad y LLM continúan deshabilitados o sin calibrar.

## Retorno

La pausa es el retorno operativo inmediato. Para volver al código anterior, fijar los
digests de la [release 010](release-20260928-010.md) en API, worker y dashboard, y volver
a comprobar pausa, autenticación, salud y persistencia. La release 011 no tiene
migración; no requiere `downgrade` para funcionar tras un rollback.
