# Operación y monitoreo

## Estado de entrega

El desglose contable por ejecución está desplegado en Contabo mediante
`v1-candidate-20260915-002`, con digests nuevos, pruebas sintéticas y smoke test
pausado. La candidata anterior no se sobrescribió. La tarea 9.3 queda completa;
ver [evidencia de release y verificación remota](release-20260915-002.md).

No se reanudó el radar del VPS ni se añadieron datos inventados a su base. Las
pruebas con ejecuciones y contabilidad se realizan únicamente en PostgreSQL temporal.

## Dónde revisar cada señal

| Señal | Vista o comprobación | Interpretación |
| --- | --- | --- |
| Última ejecución correcta | Resumen / Operación | Un fallo posterior no reemplaza la fecha del último éxito. |
| Antigüedad de evidencia | Cabecera del dashboard | Fecha de observación, no fecha de lectura de caché. |
| Estado, etapa, intentos y error | Operación → Ejecuciones y errores | Los trabajos pendientes no se presentan como terminados. |
| Cobertura | Operación → Cobertura de ejecución | Instantánea del lote, familias pendientes y motivo parcial; no censo de YouTube. |
| Consumo por ejecución | Operación → Consumo de ejecución (código nuevo) | Confirmados separados de reservas activas e incertidumbres, agrupados por unidad. |
| Consumo total | Resumen → Consumo registrado | Historial completo, no una cifra exclusivamente mensual. |
| CPU y memoria | Resources de cada servicio en Easypanel | Límites de contenedor; no métricas de mercado ni alertas automáticas. |
| Salud del worker | `python -m nicheradar.workers.health` en su contenedor | Heartbeat reciente con acceso a base; una pausa válida es saludable. |

El desglose por ejecución enlaza asientos y reservas mediante la solicitud de
proveedor y su `run_id`. No mezcla unidades, no duplica reservas confirmadas ni
incluye reservas liberadas. Las suscripciones sin solicitud asociada permanecen en
el consumo global; no se reparten arbitrariamente entre ejecuciones. Las estimaciones
de producción no entran en la contabilidad. Una lista vacía significa **sin movimientos
registrados**, no prueba de ausencia de un posible cobro externo aún desconocido.

Las consultas agregan únicamente los runs de la página solicitada y no exponen
claves de solicitud, ámbito de cuenta, propietario del lease ni contenido de checkpoints.
El diagnóstico de un fallo SQL usa un código fijo, no el mensaje de la excepción.

## Límites y procedimiento

El despliegue actual tiene 512 MiB por servicio y 128 MiB de reserva. CPU máxima:
PostgreSQL/dashboard 0,5; API/worker 1. Estos controles están en Easypanel/Swarm;
no se cambian desde el dashboard. La verificación efectiva y la persistencia están
registradas en [el despliegue](deployment-20260915.md).

En el worker, `NR_EXTERNAL_CONCURRENCY=1`, `NR_BATCH_SIZE=20` y
`NR_WORKER_MAXIMUM_ATTEMPTS=3` son los valores desplegados. La configuración valida
rangos (concurrencia 1–4, lote 1–100, intentos 1–10). Cambiarlos requiere volver a
desplegar solo el servicio correspondiente y verificar sus límites; no hacerlo como
respuesta automática a un presupuesto agotado. Memoria baja no autoriza retirar
límites ni detener otras aplicaciones del VPS.

Ante un error, revisar primero su código y la cobertura. Para autenticación,
políticas pendientes o cobro incierto, corregir o conciliar antes de autorizar un
reintento. El estado de pausa persistido manda: modificar `NR_RADAR_PAUSED` no
sustituye el control de pausa de una base ya activa. No reanudar proveedores reales
durante un smoke test.

No se ha instalado un sistema de alertas externas ni se ha validado carga real
sostenida. El monitoreo actual es consultivo desde el dashboard y Easypanel.

## Evidencia reproducible

Verificación local del 2026-09-15: **297 pruebas aprobadas**, Ruff y mypy sin
errores; validación estricta de OpenSpec correcta. Persisten dos advertencias
de deprecación de dependencias del cliente de pruebas (Starlette/httpx y AnyIO).
Estos resultados locales se complementaron con pruebas en Contabo: login, vistas,
monitoreo con fixtures en memoria, límites efectivos, persistencia y HTTPS/WebSocket.

`tests/test_operational_monitoring.py` cubre separación de runs y páginas, monedas,
reservas confirmadas/liberadas/inciertas, exclusión de cargos globales, ausencia de
datos internos, último éxito frente a fallo posterior, antigüedad y visualización
de cobertura y costes a través de dashboard/API/SQL. También verifica controles
configurables y diagnóstico SQL sin texto secreto.

Complementos: `test_console_states.py`, `test_api_contracts.py`,
`test_dashboard_navigation.py` y `test_worker_health.py`.

```sh
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest --tb=short
uv run ruff check src tests
uv run mypy
```

La fixture crea y retira exclusivamente su clúster/esquemas temporales. No pasarle
la conexión de aplicación ni la del VPS.
