# Habilitación de proveedores

Revisión documental, integración y despliegue actualizados: 23 de septiembre de 2026.
Actualización de autenticación: 21 de septiembre de 2026; la página oficial admite
clave API MCP propia además de OAuth. [Conexión y comprobación](vidiq-connection.md)
implementadas localmente y conexión real aceptada desde el Mac con clave propia.
El catálogo anuncia 5 créditos por operación de investigación y 0 por saldo;
ver [contrato observado](vidiq-contract-20260921.md). El piloto manual ejecutó una búsqueda;
las ejecuciones programadas acumularon dos búsquedas y tres consultas de publicaciones.
Esta matriz registra decisiones operativas del proyecto, no una autorización del proveedor
ni asesoramiento jurídico. `pending` bloquea el uso correspondiente.

## Matriz de operaciones

| Fuente / operación | Coste de referencia | Consulta real | Programación | SQL / histórico | Derivados |
| --- | --- | --- | --- | --- | --- |
| Sintético / catálogo, canales, videos | US$0 | No aplica | Habilitada al reanudar | Habilitado, 7 días en el flujo | Habilitados, identificados como prueba |
| vidIQ / búsqueda de canales | 5 anunciados y confirmados por saldo | Piloto manual: 1 | Ciclos observados: 2 | Habilitado, 7 días | Snapshot actual: 8 entradas sin puntuación |
| vidIQ / publicaciones de canal | 5 anunciados en MCP, 2026-09-21 | No aislada | Ciclos observados: 3 | Habilitado, 7 días; 100 videos retenidos | Cohortes separadas por formato |
| vidIQ / outliers | 5 anunciados en MCP, 2026-09-21 | Pendiente | Habilitada, no ejercida por el tope | Política registrada, sin datos | Pendiente |
| vidIQ / keywords | 5 anunciados en MCP, 2026-09-21 | Pendiente | Pendiente | Pendiente | Pendiente |
| vidIQ / saldo | 0 anunciados y observados | Piloto: 2; diagnóstico inicial: 1 | 8 consultas programadas o de reevaluación | Habilitado, 7 días | Conciliación programada 170 → 145 |
| YouTube / `videos.list` por ID | 1 unidad por lote de hasta 50, verificado 2026-09-23 | Diagnóstico implementado; falta clave/proyecto propios | Etapa conectada, apagada | Política y conservación de 7 días preparadas, no activadas | Completa idioma declarado, vistas, fecha y metadatos compatibles |
| YouTube / canales y uploads | Cuota API por operación; no convertir a USD | Adaptador probado con fixtures | Fuera del flujo actual | Política por tipo pendiente | Pendiente |
| LLM / enriquecimiento | Máximo USD desconocido | Deshabilitado | Deshabilitado | No configurado | Explicación determinista disponible |

El artículo oficial de [vidIQ MCP](https://support.vidiq.com/en/articles/15082430-vidiq-mcp)
describe el endpoint MCP y utilidades gratuitas; indica 5 créditos para la mayoría
de herramientas, pero no sustituye el contrato vigente de cada operación. No se habilitan
herramientas de generación ni listas de competidores. El coste de Video Watch observado
en la exploración difiere del artículo: esa operación queda fuera de la V1.

Los [términos de vidIQ](https://vidiq.com/terms/) vigentes desde el 19 de septiembre de
2026 contienen restricciones a recopilación sistemática y bases de datos (secciones 4 y 5).
El propietario confirmó que dispone de constancia para el uso personal aplicado aquí.
El piloto manual se limitó a una base temporal y un informe agregado sin identificadores
externos. La habilitación programada quedó registrada con la misma constancia y siete días
de conservación; el radar volvió a pausa después de una sola ocurrencia.

Las [políticas generales de YouTube](https://developers.google.com/youtube/terms/developer-policies)
regulan conservación y métricas. Las [condiciones adicionales](https://developers.google.com/youtube/terms/derived-metrics-policy)
contemplan determinados usos aceptados y hasta 36 meses para estadísticas/derivados;
otros datos, como títulos y descripciones, mantienen reglas de actualización/eliminación
de 30 días. NicheRadar limita esta evidencia a siete días. No hay constancia de aceptación
de la extensión para métricas derivadas y no se depende de ella.
La disponibilidad pública de estadísticas no autoriza automáticamente cualquier score.

## Resultado del piloto real

El [informe agregado](vidiq-pilot-20260922.md) registra llamadas, saldo, coste, tiempo,
relevancia y cobertura. Se respetó un tope de 5 créditos. La falta de videos impidió
calibrar referencias, así que las puntuaciones permanecen `uncalibrated`.

La release 006 y la política `scheduled` de vidIQ están desplegadas. Los ciclos observados respetaron
los límites vigentes 20/25/100 y dejaron el radar pausado. El consumo semanal llegó a 25,
por lo que las nuevas operaciones pagadas quedan bloqueadas hasta el siguiente periodo.
Cambiar `NR_MODE` por sí solo nunca supera el preflight. YouTube está conectado en la
release, pero apagado y sin cuota configurada hasta validar una clave propia.

No hay compras, recargas ni cambios de plan automáticos. Las suscripciones existentes de
Claude, ChatGPT y Google AI Pro quedan excluidas; sus planes de chat no se presumen saldo API.

## Historial y datos propios

El histórico del radar se guarda en PostgreSQL, no en una lista de vidIQ. Cada observación
mantiene procedencia y caducidad; las decisiones propias se separan de la evidencia externa.
Una política pendiente no se convierte en habilitada por tener un adaptador implementado.
Los respaldos también deben caducar: ver [recuperación](backup-restore.md).
