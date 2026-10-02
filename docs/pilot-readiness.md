# Preparación del piloto real

Estado: 2026-09-22. Las tareas 10.6–10.8 están completas. El piloto manual quedó
`uncalibrated` por evidencia insuficiente y la release 003 fue publicada y desplegada.
El runtime está en modo `live`, con el radar pausado después de una ocurrencia programada.

Avance de conexión: autenticación por clave API propia y comando de comprobación MCP
implementados localmente; ver [conexión vidIQ](vidiq-connection.md). La comprobación
solo inicializa el protocolo y lista herramientas. La conexión real ya fue aceptada
con la clave propia; ver [registro del contrato](vidiq-contract-20260921.md).
El worker desplegado puede construir el adaptador real, pasarlo por el gateway de políticas,
saldo, reservas y límites, y conservar la plataforma `vidiq` en la procedencia. Sigue
cerrado antes de cualquier llamada mientras falte un requisito.

## Diagnóstico sin consultas externas

La API privada ofrece `GET /api/v1/pilot/preflight`; el dashboard incorpora el botón
«Ver requisitos del piloto real» en Operación. Requiere la autenticación habitual.
El parámetro opcional `scheduled=true` incluye las políticas de programación.

El endpoint lee PostgreSQL en una transacción de solo lectura con una vista consistente.
No crea el perfil, no limpia observaciones, no guarda políticas, no conecta proveedores,
no verifica credenciales remotas y no inicia trabajos ni reservas de gasto. El botón
solo solicita este informe; el resto de la pantalla conserva su comportamiento habitual.

El informe distingue:

- Configuración local: existencia del perfil, confirmación de presupuesto y límites
  guardados por ejecución, semana y ciclo, separados de los límites USD.
- Políticas vigentes registradas para saldo, búsqueda de canales, publicaciones y
  outliers: consulta, almacenamiento, histórico y derivados cuando corresponda.
  La programación añade su propio requisito. Un registro habilitado sin evidencia
  documental o sin plazo de almacenamiento sigue apareciendo incompleto.
- Controles del runtime real: ámbito no secreto de cuenta, fecha de validación de la
  conexión, inicio confirmado del ciclo, interruptor técnico y autorización del piloto.
  Las fechas futuras se rechazan. Tener un token no completa ninguno de estos controles.

`ready` solo puede ser `true` cuando todos los controles y políticas requeridos están
completos. El piloto aislado los configuró inicialmente en una base temporal. La release
desplegada ya tiene la configuración y las políticas programadas, pero permanece pausada.
El informe no es una revisión jurídica ni una validación remota de la cuenta.
`provider_calls: 0` corresponde solo a esta comprobación, no al historial completo.
Nunca devuelve tokens ni el texto de evidencia.
Los detalles y decisiones documentales siguen en [provider-readiness.md](provider-readiness.md).

## Piloto ejecutado

El propietario confirmó el alcance personal. El piloto usó políticas manuales con esa
constancia, conservación máxima de siete días y una base PostgreSQL eliminada al terminar.
Ejecutó dos saldos gratuitos y una búsqueda de 5 créditos. El saldo pasó de 175 a 170,
las tres solicitudes quedaron completadas y no quedaron reservas inciertas.

La familia `culture` recibió 10 canales; los dos formatos quedaron sin consultar porque
otra operación habría excedido el tope de 5 créditos. No hubo videos ni cohortes, por lo
que no se congelaron referencias ni rúbricas. El informe está en
[vidiq-pilot-20260922.md](vidiq-pilot-20260922.md).

El ciclo programado completó las siete etapas, consumió 5 créditos y creó un snapshot
vacío del backlog porque no hubo presupuesto para videos. Quedó pausado al terminar; ver
[informe programado](vidiq-scheduled-20260922.md) y [guía](live-operation.md).
El almacenamiento externo se deja para más adelante según la decisión del propietario;
esto no elimina las reglas de conservación ni completa la tarea de recuperación 9.4.

## Verificación local

`tests/test_pilot_preflight.py` cubre acceso privado, ausencia de escrituras/creación
de datos, preservación de evidencia vencida durante la consulta, ocultación de secretos,
políticas pendientes/deshabilitadas/futuras/incompletas, requisitos de programación
y el botón del dashboard. Las configuraciones se aíslan del entorno y del archivo `.env`.
`tests/test_pipeline.py` verifica que el modo live falla antes de la primera llamada
cuando faltan requisitos y que, con un fixture vidIQ, registra procedencia, saldo,
5 créditos y el corte por presupuesto. Son pruebas con PostgreSQL temporal y fixtures;
no validan una cuenta real de vidIQ.
