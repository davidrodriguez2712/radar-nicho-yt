# Saldos, renovación y conciliación

El radar guarda los saldos en PostgreSQL; no escribe información en vidIQ.
La implementación está probada con transportes inventados. No activa una cuenta,
compra créditos ni confirma condiciones de uso pendientes.

## Qué se registra

- Saldo renovable disponible, saldo adicional y asignación recurrente por separado.
  Una asignación de 150 más 20 adicionales no equivale a 170 por ciclo futuro.
- Inicio y fin del ciclo del proveedor, separados del mes financiero en Lima.
- Fecha original de observación y una señal independiente de actualización necesaria.
  Confirmar consumo o restaurar una copia no modifica artificialmente esa fecha.
- Consumo confirmado por solicitud y unidad. La suscripción se registra en USD;
  gastar sus créditos no vuelve a registrar su precio en dólares.

`GET /api/v1/consumption` y el resumen del dashboard muestran el saldo retenido y
las últimas 20 conciliaciones, además del consumo, reservas y cobros inciertos.
Una diferencia negativa no atribuida puede corresponder a uso fuera del radar,
un cobro todavía incierto o una corrección del proveedor: no prueba su causa.

En el mismo ciclo se calcula:

`diferencia no atribuida = saldo nuevo − saldo anterior + consumo confirmado del radar entre comprobaciones`.

El consumo entre comprobaciones se obtiene de un contador acumulado por proveedor,
cuenta y unidad, no de una conversión a USD ni del orden supuesto de las dos bolsas.
En cambios de ciclo o consumo concurrente con la lectura, esa atribución queda
desconocida. Una renovación nunca genera ingresos ni un asiento USD.

## Antes de consultar

Para operaciones con créditos, el gateway comprueba el saldo al empezar cada
ejecución que necesita una llamada externa. Vuelve a comprobarlo si han pasado
más de 60 minutos, terminó el ciclo o se confirmó consumo desde la observación.
Los resultados de investigación reutilizables en caché no requieren consultar saldo.
La lectura histórica de saldo en caché nunca se trata como una comprobación nueva.

La actualización automática exige una operación de saldo soportada, tarifa máxima
explícitamente gratuita, presupuesto confirmado y políticas habilitadas, también
la de programación cuando corresponda. No inventa una tarifa ni consulta un
proveedor sustituto. Las comprobaciones cuentan dentro del máximo durable de llamadas
del lote, junto con los intentos de investigación. Si no queda capacidad, aplaza.

La reserva y el envío vuelven a verificar el saldo bajo bloqueos transaccionales.
Si aparece consumo externo que deja una reserva preparada sin respaldo suficiente,
la solicitud no se envía. El cierre del trabajo libera solo lo que no pudo enviarse;
las obligaciones inciertas se mantienen, incluso al cruzar un ciclo.

## Renovación sin créditos inventados

Llegar a la fecha de renovación no recarga la base automáticamente: se requiere una
nueva observación del proveedor. Se conservan exactamente sus dos saldos y la
asignación informada, sin trasladar adicionales a capacidad recurrente.

El inicio del ciclo debe venir en el contrato normalizado o en configuración explícita
del gateway (`credit_cycle_started_at`). Puede reutilizarse el inicio anterior solo si
el fin del ciclo no cambió. El contrato vidIQ observado informa el próximo vencimiento,
pero no el inicio: antes de conectarlo al pipeline real hay que configurar fechas
verificadas o una regla documentada del proveedor. No se presume un mes de 30 días.
Ante un cambio sin inicio verificable, queda `balance_cycle_required`; no sigue gastando.

Una observación vieja, futura o con fecha remota idéntica a otra comprobación distinta
no puede reemplazar el saldo. Si se confirma gasto mientras se consulta el saldo,
se conserva la incertidumbre y se exige otra comprobación antes de autorizar más gasto.
Una nueva lectura de saldo **no** concilia por sí sola una solicitud `unknown_charge`.

## Conservación y recuperación

La migración `0008` añade procedencia, caducidad y conciliaciones. Las observaciones
remotas referencian la respuesta autorizada; los derivados dependen de ambas respuestas
comparadas y caducan con la primera de ellas. Acortar o revocar una política elimina
también los datos de saldo y diferencias afectados. Las entradas manuales internas
sin fuente remota tienen un plazo conservador de siete días; no son datos de proveedor
autorizados para siempre. Las observaciones anteriores a la migración requieren refresco.

La fecha límite de respaldo incluye saldos y conciliaciones. Restaurar exige una
comprobación nueva, mantiene los cobros inciertos y deja la programación pausada.

Pruebas: `tests/test_balance_reconciliation.py`, además de reservas concurrentes,
recuperación y contratos de adaptadores. Todas usan datos inventados, sin gasto real.
