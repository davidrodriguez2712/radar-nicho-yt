# Descubrimiento y actualización — validación sintética

El worker parte del catálogo versionado sin pedir nichos al usuario. Este flujo está
probado con datos inventados; no habilita consultas reales, producción ni canales.

## Selección del trabajo

- Los cursores SQL separan perfil y modo sintético/real. Priorizan familias nunca
  exploradas o menos recientemente intentadas cuando corresponde capacidad nueva.
- El objetivo inicial de exploración nueva es 25 % de las llamadas enviadas,
  configurable en el perfil. El reparto usa el historial y decide por lote completo:
  puede superar esa proporción temporalmente, no es una partición exacta de créditos.
  La caché no cuenta como una llamada enviada. Los límites monetarios prevalecen.
- Los seleccionados se actualizan desde las 24 horas; los candidatos en seguimiento,
  desde las 168 horas. Ambas cadencias son configurables y no garantizan puntualidad.
  Se priorizan seleccionados, luego seguimiento; el descubrimiento conserva capacidad.
- Cada actualización se dirige a una oportunidad y formato, mantiene su identidad y
  su decisión manual, y añade una evaluación. Cambiar idioma o formatos excluye de
  actualización automática los candidatos fuera del alcance actual. Los descartados
  no se actualizan automáticamente ni se reactivan por redescubrimiento.

## Consultas acotadas y trazabilidad

Se buscan canales pequeños y grandes por separado y se amplían consultas usando
subtemas de canales con categoría compatible con la familia. El perfil limita las
ampliaciones (2 inicialmente, máximo 5) y los canales (10 inicialmente, entre 2 y 10).
Los resultados de cada búsqueda se intercalan antes de aplicar el límite, para que
una página llena de canales pequeños no excluya a todos los grandes.

Se solicitan publicaciones recientes de los canales y ejemplos outlier por formato.
La procedencia distingue ambos tipos; encontrar el mismo video por dos rutas no
duplica el denominador. Los subtemas consultados tienen referencias a la observación
original y la consulta madre; los checkpoints guardan identificadores y huellas,
no copias de textos del proveedor.

La expansión busca evidencia adicional; no confirma por sí sola un subnicho. El
agrupamiento admite embeddings locales opcionales, con límites, correspondencias y
ruido explícitos. Sin modelo continúa usando categorías del proveedor, sin presentarlas
como clustering propio validado. Ver [agrupamiento temático](topic-grouping.md).

## Lotes parciales y recuperación

`NR_BATCH_SIZE` limita llamadas enviadas por ejecución (20 inicialmente), incluso si
el worker reinicia. Un resultado de caché puede reutilizarse aunque se alcance ese
límite. Los sublímites de presupuesto siguen aplicándose en la misma pasarela.

Cada respuesta queda confirmada por separado. Un lote interrumpido por presupuesto o
capacidad conserva sus referencias SQL y puede continuar en otra ejecución, sin repetir
respuestas todavía conservables y compatibles con los parámetros. Reutilizar evidencia
no cambia su fecha original. Modificar filtros, formatos o límites de muestra invalida
la continuación incompatible; la caché normal todavía puede ahorrar consultas válidas.

La falta de evidencia en una actualización queda como parcial, sin fingir una
evaluación nueva. El siguiente intento puede volver a consultar respetando la caché,
en lugar de perpetuar respuestas vacías. Las incertidumbres de cobro conservan los
bloqueos existentes; no autorizan reenvíos automáticos.

## Programación y reintentos

La pausa, el planificador y la reclamación de trabajo comparten un bloqueo SQL. Dos
planificadores registran una sola ocurrencia lógica; Lima y UTC representan el mismo
instante y las funciones de programación rechazan fechas sin zona horaria. Una pausa
impide iniciar trabajo nuevo, pero no cancela una operación que ya estaba ejecutándose.

Si se pierden varias horas, se consolida el atraso en una sola ocurrencia. Mientras
esa programación tenga un trabajo en cola o en ejecución, los siguientes intervalos
no acumulan más trabajos: el calendario avanza y la cobertura pendiente permanece en
los cursores. Al terminar, un intervalo futuro podrá reunir más evidencia. No se
lanzan ejecuciones inmediatas adicionales para eludir los límites por lote.

`NR_WORKER_MAXIMUM_ATTEMPTS` limita los intentos por trabajo (3 inicialmente; 1–10).
Incluye recuperaciones de leases tras caídas del proceso. Los fallos transitorios
seguros esperan 30, 60, etc. segundos, con espera base acotada y jitter de 0–30 segundos.
La espera se guarda en SQL: el worker no duerme bloqueando otros trabajos. Un propietario
que perdió su lease no puede confirmar etapas ni sobrescribir al nuevo propietario.

Autenticación, cuota, políticas pendientes y cobros inciertos no se reintentan por
recibir una etiqueta genérica de error seguro. Si falla una ocurrencia programada por
una condición que requiere atención, se bloquean nuevas ocurrencias de esa programación
hasta una reanudación explícita. El panel muestra el ID del trabajo: corrige la causa
y usa **Pausar radar → Reanudar radar sintético** para autorizar un intento posterior.
Los límites de dinero y saldo se vuelven a comprobar en cada operación; agotarlos no
autoriza compras y puede aplazar lotes posteriores. Las solicitudes manuales explícitas
siguen sujetas a los mismos controles y no concilian por sí solas una deuda incierta.

Una excepción después de entregar una solicitud al transporte se considera de cobro
incierto, salvo que el adaptador certifique expresamente `not_sent=True`. Solo en ese
caso se libera la reserva y el siguiente intento crea otro recibo auditable; no se borra
la intención de envío anterior. El adaptador YouTube certifica así un `ConnectError`,
no un timeout o una respuesta perdida. Los fallos ambiguos, cancelaciones y caídas del
proceso nunca se convierten en prueba de no envío. Al agotar intentos se liberan reservas
preparadas que no llegaron a envío y se conservan como inciertas las potencialmente enviadas.

Las pruebas de estas reglas usan relojes controlados, PostgreSQL temporal y transportes
inventados en `tests/test_scheduling_retries.py`. Incluyen igualdad de límites monetarios
para solicitudes manuales/programadas. No constituyen un piloto real ni validan todavía
todas las interrupciones y pérdidas de conexión de la tarea 10.2.

En **Operación**, cada ejecución muestra su modo, tipo de trabajo, familias no
recorridas, actualizaciones pendientes al planificar y motivo de resultado parcial.
Es una instantánea de ese lote, no un censo de YouTube ni una lista en tiempo real.
Las cadencias y tamaños se editan en **Configuración**.

Verificación: `tests/test_discovery.py`, `tests/test_api_operations.py` y
`tests/test_dashboard_navigation.py`. La migración `0003` añade cursores; aplicar
`alembic upgrade head` en la base del radar antes de usar este worker actualizado.
