## Purpose

Descubrir periódicamente oportunidades de contenido sin exigir que el usuario conozca nichos de antemano, y formar muestras trazables para analizarlas por audiencia y formato.

## ADDED Requirements

### Requirement: Discovery without user-provided niches
El sistema SHALL iniciar exploraciones desde un catálogo versionado de familias de contenido, sin requerir una lista de nichos del usuario. SHALL registrar las familias exploradas y las pendientes, y reservar una parte configurable de la capacidad de descubrimiento para familias todavía no exploradas o menos recientemente exploradas.

#### Scenario: First exploration
- **WHEN** el usuario activa un radar con proveedores habilitados y presupuesto disponible sin introducir nichos
- **THEN** el sistema explora familias del catálogo y registra consultas, candidatos y cobertura de esa ejecución

#### Scenario: Exploration with limited resources
- **WHEN** los recursos disponibles no permiten recorrer todo el catálogo
- **THEN** el sistema procesa un subconjunto, conserva el resto pendiente y no presenta los resultados como una exploración exhaustiva de YouTube

### Requirement: Explicit language and format scope
El sistema SHALL priorizar contenido en inglés y evaluar Shorts y videos largos en cohortes separadas. SHALL distinguir idioma del contenido, país del canal y geografía de audiencia; un país declarado por el canal SHALL NOT interpretarse como procedencia de sus espectadores. La clasificación desconocida SHALL permanecer explícita hasta poder verificarse.

#### Scenario: Channel with both formats
- **WHEN** un canal publica Shorts y videos largos
- **THEN** sus videos se asignan a cohortes por formato sin mezclar vistas o tasas entre formatos

#### Scenario: Uncertain language or format
- **WHEN** una respuesta indica varios idiomas o no clasifica el formato
- **THEN** el sistema verifica los elementos que pueda y mantiene los restantes como desconocidos fuera de las cohortes confirmadas

### Requirement: Relevant and comparable candidate samples
El sistema SHALL verificar relevancia temática, deduplicar identificadores y conservar las razones de inclusión y exclusión. SHALL reunir publicaciones habituales además de outliers y registrar ventana temporal, tamaño de canal y método de selección. Un video SHALL contarse una sola vez dentro de una cohorte aunque aparezca en varias consultas.

#### Scenario: Ambiguous discovery keyword
- **WHEN** una consulta sobre astronomía devuelve un video sobre espacio personal o decoración
- **THEN** el sistema lo excluye del análisis de astronomía o lo deja pendiente de revisión si no puede determinar su relevancia

#### Scenario: Only successful videos available
- **WHEN** el proveedor solo entrega outliers para una cohorte
- **THEN** el sistema conserva los ejemplos como evidencia de descubrimiento pero marca como no calculable la tasa de breakout de esa cohorte

#### Scenario: Comparison of channel sizes
- **WHEN** se evalúa accesibilidad para creadores pequeños y competencia
- **THEN** se identifica el umbral de canal pequeño utilizado y se distingue su muestra de la muestra de competidores de mayor tamaño

### Requirement: Topic expansion and stable candidate identity
El sistema SHALL expandir familias a nichos y subnichos utilizando evidencia de canales y videos, manteniendo trazabilidad hasta los elementos de origen. SHALL identificar una oportunidad mediante audiencia, tema y formato, sin usar únicamente una etiqueta textual como identidad.

#### Scenario: Same opportunity found twice
- **WHEN** dos consultas encuentran el mismo conjunto temático con etiquetas equivalentes
- **THEN** el sistema añade evidencia a una oportunidad existente o registra una relación de posible duplicado, sin crear automáticamente dos recomendaciones independientes

#### Scenario: Insufficient evidence for a subniche
- **WHEN** los datos no permiten sostener una agrupación temática
- **THEN** el sistema conserva el candidato sin subnicho confirmado y no inventa una clasificación para completar la salida

### Requirement: Scheduled and manual bounded exploration
El sistema SHALL permitir configurar, pausar y reanudar exploraciones periódicas, así como solicitar una ejecución manual. Todas SHALL obedecer los mismos controles de presupuesto y concurrencia. SHALL priorizar por separado actualización de candidatos conocidos y descubrimiento de nuevos candidatos.

#### Scenario: Manual request while budget is exhausted
- **WHEN** el usuario solicita explorar y no hay presupuesto disponible
- **THEN** la solicitud queda identificada como aplazada por presupuesto sin efectuar llamadas de pago

#### Scenario: Paused radar
- **WHEN** el usuario pausa la exploración
- **THEN** no se inician nuevos trabajos de descubrimiento y los resultados ya guardados siguen disponibles según su vigencia
