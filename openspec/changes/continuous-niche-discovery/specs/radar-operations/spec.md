## Purpose

Ejecutar un radar privado de forma continua y recuperable en el VPS compartido, con límites de recursos, almacenamiento persistente y visibilidad de fallos y trabajos aplazados.

## ADDED Requirements

### Requirement: Durable scheduled execution
El sistema SHALL ejecutar trabajos periódicos independientemente de que el dashboard esté abierto o el Mac Studio esté encendido. SHALL persistir programación, estado y progreso, impedir que una misma ocurrencia se programe duplicada y permitir limitar la concurrencia.

#### Scenario: Dashboard closed
- **WHEN** llega una ejecución programada con servicios disponibles
- **THEN** se ejecuta aunque no haya una sesión de usuario abierta

#### Scenario: Multiple scheduler instances
- **WHEN** dos instancias detectan la misma ocurrencia pendiente
- **THEN** se registra un solo trabajo lógico para esa ocurrencia

### Requirement: Restart recovery and bounded retries
El sistema SHALL recuperar trabajos interrumpidos desde etapas confirmadas y mantener un registro de intentos. SHALL distinguir fallos transitorios, autenticación, cuota, presupuesto y condiciones pendientes. Las llamadas externas sin garantía de idempotencia SHALL NOT tratarse como exactamente una vez.

#### Scenario: Worker restarts after a completed stage
- **WHEN** se reinicia el worker después de guardar una etapa
- **THEN** retoma desde el siguiente punto pendiente sin repetir por defecto consultas pagadas ya confirmadas

#### Scenario: Missed scheduled occurrences
- **WHEN** el servidor vuelve tras varias ejecuciones omitidas
- **THEN** el sistema consolida el trabajo pendiente según la configuración y el presupuesto, sin disparar una ráfaga ilimitada de consultas

#### Scenario: Persistent provider failure
- **WHEN** un proveedor sigue fallando tras el máximo configurado de reintentos
- **THEN** la ejecución registra el fallo o resultado parcial y libera recursos no consumidos sin bloquear indefinidamente otros trabajos

### Requirement: Private deployment with persistent data
El sistema SHALL poder desplegarse mediante imágenes Docker en un proyecto de Easypanel con dashboard, API, worker y almacenamiento persistente. El dashboard SHALL requerir autenticación; las conexiones públicas SHALL usar HTTPS. La API, base de datos y worker SHALL quedar en redes internas salvo una configuración explícita de acceso autenticado.

#### Scenario: Unauthenticated visitor
- **WHEN** una persona intenta consultar el dashboard sin autenticarse
- **THEN** no accede a oportunidades, costes, datos ni operaciones administrativas

#### Scenario: Application image replaced
- **WHEN** se actualiza una imagen de la aplicación
- **THEN** los datos persistentes y las decisiones permanecen disponibles tras las migraciones compatibles

### Requirement: Shared-server resource controls
El sistema SHALL admitir límites de memoria, CPU, concurrencia y tamaño de lote, y comprobar capacidad disponible antes de activar carga continua. Su despliegue SHALL NOT requerir eliminar aplicaciones existentes ni publicar los puertos de la base de datos.

#### Scenario: Insufficient server headroom
- **WHEN** la inspección del VPS muestra que el perfil previsto no cabe junto a las aplicaciones existentes
- **THEN** se reduce la carga o se presenta el recurso faltante sin borrar ni detener servicios ajenos automáticamente

### Requirement: Operational visibility and recovery
El sistema SHALL exponer salud de servicios, última ejecución satisfactoria, antigüedad de datos, trabajos pendientes, fallos y costes por ejecución, sin secretos. SHALL disponer de un procedimiento comprobable de respaldo y restauración, con reglas de conservación compatibles con las de los datos.

#### Scenario: Stale data after failed runs
- **WHEN** varias ejecuciones fallan y permanecen resultados anteriores
- **THEN** el dashboard muestra el retraso y el motivo en lugar de presentarlos como actualizados

#### Scenario: Restore from backup
- **WHEN** se restaura un respaldo en un entorno aislado
- **THEN** se recuperan los datos y decisiones permitidos, se aplica la limpieza por conservación y las tareas pagadas permanecen pausadas hasta reactivación explícita
