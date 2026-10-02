## Why

Elegir un nicho para crear canales de YouTube requiere comparar demanda, oportunidades para nuevos creadores y viabilidad de producción, con datos que cambian continuamente. NicheRadar permitirá descubrir oportunidades desde cero y mantener una selección explicable para decidir dónde invertir un presupuesto inicial limitado.

## What Changes

- Introducir un radar periódico que explore distintas familias de contenido en inglés sin exigir nichos al usuario, y evalúe Shorts y videos largos por separado.
- Integrar proveedores mediante adaptadores, con control de relevancia, cobertura, datos faltantes, procedencia, caché y conservación configurable.
- Separar atractivo del mercado, encaje con el creador y confianza en la evidencia. Priorizar ingresos publicitarios y producción con IA, admitiendo intervención humana cuando compense.
- Mantener un backlog con identidades estables, versiones del análisis, evidencia, selecciones y descartes; explicar los cambios de posición.
- Controlar gasto y créditos del radar y presentar escenarios de producción dentro de US$100–150 mensuales y 15 horas semanales de base. Excluir del presupuesto las suscripciones existentes de Claude, ChatGPT y Google AI Pro.
- Permitir contemplar varios futuros canales simultáneos: la restricción es la combinación de dinero y tiempo disponible, no un límite fijo de un canal.
- Preparar un despliegue privado mediante imágenes Docker en Easypanel: dashboard, API, worker y PostgreSQL. El VPS compartido tiene 6 núcleos, 12 GB de RAM y 400 GB de disco; su capacidad libre está por verificar.

## Capabilities

### New Capabilities

- `continuous-discovery`: exploración programada, expansión de temas y formación de muestras por formato.
- `provider-data-quality`: contratos de proveedores, normalización, procedencia, caché, calidad y conservación.
- `opportunity-evaluation`: métricas, puntuaciones versionadas, encaje de producción y explicaciones basadas en evidencia.
- `opportunity-backlog`: selección actualizada, detalle, historial y decisiones del usuario.
- `resource-budgeting`: límites, registro de consumo y escenarios de costes y tiempo compartidos.
- `radar-operations`: ejecución durable, recuperación y operación privada en Easypanel.

### Modified Capabilities

Ninguna. El repositorio no tiene especificaciones de capacidades existentes.

## Impact

Proyecto nuevo en Python, con FastAPI, Streamlit y PostgreSQL; integración inicial candidata con vidIQ MCP y complementos sujetos a validación. Se requerirán imágenes Docker, configuración por entorno, persistencia, migraciones y pruebas. No se eliminarán aplicaciones existentes del VPS.

La prueba exploratoria confirmó acceso al conector vidIQ y consumió 15 créditos (saldo posterior: 155); no validó acceso desde el VPS, un análisis completo de nicho ni derechos de conservación. La consulta enviada a vidIQ quedó registrada por su canal de feedback, sin resolución todavía. Estas dependencias se documentarán sin detener el diseño independiente de proveedores.

## Non-goals

Esta V1 no crea canales, produce o publica videos, inicia experimentos reales, optimiza automáticamente una cartera de canales, decide cierres ni entrena modelos predictivos. Tampoco promete rentabilidad, RPM real de terceros o cobertura exhaustiva de YouTube.

## Future Direction

Evolución prevista: radar continuo → experimentos supervisados → producción automatizada → asignación de recursos y evaluación automática. Un experimento futuro corresponde a un canal con una audiencia y propuesta coherentes, que puede probar subtemas y formatos. Cada lanzamiento requerirá aprobación del usuario; varios experimentos podrán coexistir si caben en los recursos. Esta visión orienta las identidades y contratos de la V1, pero no añade tareas de ejecución a este cambio.
