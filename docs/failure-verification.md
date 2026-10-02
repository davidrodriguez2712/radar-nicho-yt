# Verificación integrada de fallos y concurrencia

La matriz de `tests/test_integrated_failures.py` recorre la cola, reservas, gateway,
pipeline y backlog reales contra PostgreSQL aislado. Los datos, permisos y costes
del transporte de pruebas son inventados: cada llamada simula USD 1. No se usan
credenciales ni servicios de vidIQ, YouTube o LLM; no se descarga un modelo.

## Matriz de 19 casos

| Interrupción o límite | Casos | Comprobación |
| --- | ---: | --- |
| Antes de consulta, normalización, cohorte, métricas, evaluación o backlog | 6 | Un worker nuevo retoma el checkpoint SQL; no duplica solicitudes, cargos, evaluaciones ni clasificación final. |
| Salida abrupta de un proceso independiente después de normalizar | 1 | El hijo termina sin ejecutar finalizadores; otro worker completa ambos formatos leyendo únicamente PostgreSQL, sin nuevas consultas. |
| Respuesta y coste guardados, recibo de consulta aún no guardado | 1 | Se reutiliza la respuesta persistida; la consulta pagada no se repite. |
| Conexión PostgreSQL perdida después de la respuesta y antes del commit | 1 | Se termina exclusivamente la conexión de la prueba; el resultado no queda guardado, la reserva pasa a cobro incierto y el reenvío se bloquea incluso desde otra ejecución. |
| Timeout con posible cobro o cancelación durante el transporte | 2 | La reserva incierta se conserva y no se reclama automáticamente otro intento. |
| Presupuesto por ejecución de USD 0 o USD 5 | 2 | Cero o cinco llamadas respectivamente; cobertura parcial y motivo de presupuesto agotado visibles, sin declarar la familia completada. |
| Evidencia expirada durante inactividad antes de normalización, evaluación o backlog | 3 | Se limpian las fuentes y derivados afectados; no reaparecen ni se consultan automáticamente otra vez. |
| Dos workers compiten por recuperar la misma ejecución | 1 | Solo uno la reclama y completa; no se duplica gasto ni evaluación. |
| Error SQL antes o después de las consultas, observado desde el tick del worker | 2 | Se informa el error sin detalles del controlador ni un falso contador de cero llamadas. |

Las seis interrupciones por etapa usan una excepción que evita los manejadores normales;
no son reinicios de Docker. El caso de proceso independiente sí utiliza una terminación
abrupta real (`os._exit`) y el caso de conexión sí termina un backend PostgreSQL real,
ambos creados para la prueba. El reloj controlado permite vencer leases y conservación
sin esperar minutos o días. La concurrencia utiliza dos hilos con conexiones separadas.

## Interpretación operativa

`provider_calls` en la salida del worker cuenta intentos del proceso actual, también
cuando ocurre un error SQL. **No demuestra cargos confirmados**, ni agrega llamadas de
workers anteriores. Para gasto y reservas se consulta la contabilidad persistida. Si
la base no está disponible, la conciliación espera a recuperarla; no se asume coste cero.

El fallo de conexión comprueba precisamente el límite de la garantía: puede existir
un cobro sin resultado guardado. El radar bloquea la repetición y conserva la reserva,
pero no puede determinar por sí solo qué facturó un proveedor externo. Un saldo nuevo
no equivale a conciliar esa solicitud individual.

## Reproducir

```sh
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_integrated_failures.py --tb=short
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest --tb=short
```

La fixture crea una instancia temporal con socket privado, sin escuchar TCP, y esquemas
únicos por prueba. Al terminar elimina exclusivamente sus datos temporales. También se
admite la base de pruebas local vacía validada por `tests/conftest.py`; nunca usar una
base de aplicación para esta matriz.

Esto completa la verificación integrada local de 10.2, no las validaciones de Easypanel,
carga sostenida, almacenamiento de respaldos, autenticación de proveedores o piloto real.
Los controles específicos de reservas concurrentes, programación, saldos y restauración
siguen cubiertos además por sus suites correspondientes.
