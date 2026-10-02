## Purpose

Controlar el consumo del radar y comparar escenarios de producción usando un presupuesto compartido, sin confundir créditos, suscripciones y costes estimados con dinero efectivamente gastado.

## ADDED Requirements

### Requirement: Shared configurable resource envelope
El sistema SHALL permitir configurar un presupuesto mensual total en USD, sublímites del radar y reserva para imprevistos, así como disponibilidad semanal de horas. El perfil inicial SHALL representar US$100 como objetivo y US$150 como techo propuesto, con 15 horas semanales de base, editables por el usuario. SHALL excluir del cálculo inicial Claude, ChatGPT y Google AI Pro existentes; cualquier gasto adicional de infraestructura SHALL poder registrarse explícitamente.

#### Scenario: Initial budget profile
- **WHEN** se crea el perfil inicial
- **THEN** se muestran los límites propuestos para confirmación antes de activar consultas pagadas, sin descontar las tres suscripciones excluidas

#### Scenario: More effort permitted for a specific scenario
- **WHEN** el usuario aumenta la disponibilidad para evaluar un escenario
- **THEN** se utiliza esa disponibilidad explícita y no se asume automáticamente más tiempo por una puntuación alta

### Requirement: Separate currency and provider-credit accounting
El sistema SHALL registrar separadamente gastos en USD, créditos renovables, créditos adicionales, fecha de renovación y consumo por operación. SHALL NOT equiparar créditos con dólares sin una conversión documentada, ni considerar todo saldo observado como una asignación mensual recurrente.

#### Scenario: Bonus credits included in balance
- **WHEN** un proveedor informa 150 créditos renovables y 20 adicionales
- **THEN** el sistema distingue ambas bolsas y no planifica ciclos futuros suponiendo 170 créditos renovables

#### Scenario: Balance changed outside the radar
- **WHEN** el proveedor informa un saldo inferior al previsto por consumo externo
- **THEN** se reconcilia el saldo, se muestran las diferencias y se ajustan las operaciones pendientes

### Requirement: Preflight limits and durable reservations
El sistema SHALL verificar y reservar recursos antes de cada operación pagada considerando consumos confirmados, reservas concurrentes y límites por ejecución y periodo. SHALL registrar coste estimado y real; una respuesta ambigua SHALL conservar una reserva pendiente de conciliación. SHALL NOT comprar créditos, cambiar planes ni activar recargas automáticamente.

#### Scenario: Concurrent operations would exceed budget
- **WHEN** dos operaciones caben individualmente pero juntas superan el límite restante
- **THEN** solo se autoriza el conjunto que cabe y las restantes quedan aplazadas sin enviarse al proveedor

#### Scenario: Cost is unknown
- **WHEN** no se conoce un coste máximo verificable para una operación
- **THEN** la operación no se ejecuta automáticamente y se señala la necesidad de configurar su límite

#### Scenario: Response lost after a paid request
- **WHEN** una solicitud pudo haber sido cobrada pero no se recibió confirmación
- **THEN** el sistema marca su consumo como incierto, conserva la reserva y no repite ciegamente la operación

### Requirement: Multi-channel production scenarios
El sistema SHALL permitir comparar selecciones manuales de varias propuestas de canal mediante volumen de producción, costes variables, suscripciones compartidas, repeticiones estimadas y horas de supervisión. SHALL contar una suscripción compartida una sola vez, comprobar su capacidad disponible y mostrar si el conjunto cabe en los recursos restantes tras el radar y la reserva.

#### Scenario: Two channels share a voice subscription
- **WHEN** un escenario contiene dos canales que usan la misma suscripción de voz
- **THEN** el coste fijo se suma una vez, el consumo de ambos se acumula y cualquier exceso de capacidad se refleja en la viabilidad

#### Scenario: Individually affordable but jointly infeasible
- **WHEN** dos propuestas caben por separado pero juntas exceden presupuesto u horas
- **THEN** el escenario combinado se marca como no viable e identifica el recurso excedido, sin seleccionar ni lanzar canales automáticamente

#### Scenario: Incomplete cost estimate
- **WHEN** una ruta de producción tiene costes esenciales desconocidos
- **THEN** el sistema marca el escenario como no evaluable en vez de declarar que cabe en el presupuesto

### Requirement: Visible resource usage
El sistema SHALL mostrar consumo confirmado, reservas, incertidumbres, saldo conocido y estimación del trabajo pendiente. SHALL distinguir costes estimados de producción futura de los gastos reales del radar.

#### Scenario: Scenario creation
- **WHEN** el usuario crea una simulación de producción
- **THEN** los importes se muestran como estimados y no se descuentan del saldo real ni se registran como compras
