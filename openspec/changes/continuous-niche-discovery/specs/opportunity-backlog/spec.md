## Purpose

Mantener una selección privada y actualizada de oportunidades con evidencia e historial, preservando las decisiones del usuario para futuras pruebas de canales.

## ADDED Requirements

### Requirement: Ranked backlog with evidence details
El sistema SHALL permitir consultar, filtrar y ordenar oportunidades por tema, formato, estado, puntuación, confianza, fecha y viabilidad estimada. El detalle SHALL mostrar evidencias enlazadas, componentes, limitaciones, explicación y diferencias frente a la evaluación anterior. Las etiquetas generadas SHALL NOT sustituir la identidad estable de la oportunidad.

#### Scenario: Updated opportunity
- **WHEN** una nueva ejecución cambia la evaluación de un candidato
- **THEN** el backlog muestra la fecha y los factores modificados, distinguiendo nuevos datos de un cambio de versión del método

#### Scenario: Few supported opportunities
- **WHEN** solo tres oportunidades cumplen los criterios configurados
- **THEN** se muestran esas tres sin inventar siete adicionales para completar un top diez

### Requirement: Persistent review decisions
El sistema SHALL permitir marcar oportunidades como nuevas, en seguimiento, seleccionadas o descartadas, con notas y fecha. Las actualizaciones automáticas SHALL NOT sobrescribir decisiones explícitas del usuario.

#### Scenario: Previously dismissed candidate rediscovered
- **WHEN** una exploración vuelve a encontrar una oportunidad descartada
- **THEN** conserva el descarte y su motivo, y no la vuelve a presentar como nueva

#### Scenario: New evidence for dismissed opportunity
- **WHEN** aparece evidencia material nueva en una oportunidad descartada
- **THEN** el sistema puede señalar el cambio en su historial sin reactivarla automáticamente

### Requirement: Selection does not execute a channel experiment
El sistema SHALL tratar la selección en V1 como una decisión de investigación y planificación. SHALL permitir seleccionar varias oportunidades, sin crear canales, publicar contenido, reservar compras o iniciar experimentos reales. SHALL distinguir candidatos por formato de una futura propuesta de canal que puede agrupar formatos para la misma audiencia.

#### Scenario: User selects two opportunities
- **WHEN** el usuario selecciona dos nichos distintos
- **THEN** ambos quedan seleccionados sin imponer un límite de un canal ni iniciar acciones externas

#### Scenario: Two formats for the same audience
- **WHEN** una propuesta de canal incluye Shorts y videos largos del mismo tema y audiencia
- **THEN** mantiene evidencia y costes separados por formato sin contar necesariamente dos canales futuros

### Requirement: History with traceable changes
El sistema SHALL conservar historial de decisiones y versiones de evaluación en la medida permitida por las políticas de datos. SHALL distinguir cambios numéricos, cambios de posición causados por otros candidatos y cambios de definición. SHALL NOT retener datos externos expirados dentro de textos explicativos para evitar su eliminación.

#### Scenario: Rank changes without score change
- **WHEN** otro candidato mejora y desplaza una oportunidad cuya evaluación permanece igual
- **THEN** el historial explica que cambió la posición relativa y no atribuye una caída de rendimiento a la oportunidad

### Requirement: Private dashboard and useful empty states
El sistema SHALL ofrecer un dashboard privado para un usuario, con resumen de oportunidades, ejecuciones y recursos. SHALL diferenciar ausencia de resultados, radar pausado, proveedor pendiente, falta de presupuesto y error técnico; la interfaz inicial SHALL usar español para navegación manteniendo el idioma original de la evidencia.

#### Scenario: Provider not configured
- **WHEN** el usuario abre el dashboard antes de habilitar una integración
- **THEN** se muestra qué configuración falta y no se presenta una lista vacía como prueba de que no existen oportunidades
