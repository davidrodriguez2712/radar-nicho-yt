## Purpose

Comparar oportunidades mediante métricas y puntuaciones explicables, distinguiendo atractivo del mercado, viabilidad para el creador y confianza en datos que pueden ser parciales.

## ADDED Requirements

### Requirement: Versioned deterministic market evaluation
El sistema SHALL calcular un Market Score heurístico de 0 a 100 mediante transformaciones, pesos y reglas versionadas cuando se cumplan los mínimos de evidencia y calibración. SHALL evaluar demanda, breakout, competencia y concentración, tendencia y potencial publicitario cuando haya evidencia habilitada, y mostrar oferta observada por ventana temporal. SHALL registrar componentes utilizados, componentes ausentes y cobertura de la puntuación; ésta SHALL NOT presentarse como probabilidad de éxito.

#### Scenario: Repeat evaluation with identical inputs
- **WHEN** se evalúan los mismos datos y configuración vigentes con la misma versión
- **THEN** se obtienen los mismos componentes numéricos y la misma puntuación

#### Scenario: Candidate batch changes
- **WHEN** se incorpora otro candidato al lote sin cambiar los datos ni la configuración de una oportunidad existente
- **THEN** su puntuación numérica no cambia solamente por la composición del lote

### Requirement: Comparable breakout and temporal metrics
El sistema SHALL calcular tasas únicamente sobre cohortes con denominador conocido y criterios declarados. SHALL diferenciar scores del proveedor y scores propios, separar formatos y tener en cuenta antigüedad de publicaciones. SHALL distinguir velocidad promedio desde la publicación de variaciones observadas entre fechas.

#### Scenario: No small-channel baseline
- **WHEN** hay ejemplos exitosos de canales pequeños pero faltan publicaciones comparables no seleccionadas por éxito
- **THEN** el sistema muestra los ejemplos y declara insuficiente la evidencia para una tasa de breakout

#### Scenario: Single observation
- **WHEN** solo existe una observación de vistas de un video
- **THEN** el sistema puede mostrar un promedio desde la publicación claramente etiquetado, pero no afirma haber medido aceleración ni crecimiento reciente

#### Scenario: Zero or hidden subscriber count
- **WHEN** no hay un número de suscriptores válido mayor que cero
- **THEN** el cociente vistas/suscriptores queda no disponible, sin división por cero ni sustitución arbitraria

### Requirement: Creator fit and production estimates
El sistema SHALL evaluar por separado el encaje de producción mediante rutas estimadas para ideación, investigación, guion, voz, recursos visuales, edición y revisión. SHALL priorizar producción con IA, admitir rutas semiautomáticas y mostrar supuestos, costes, horas, necesidad de intervención y calidad de evidencia. SHALL separar faceless de automatización viable y señalar dependencias de material ajeno, originalidad y repetición que requieran revisión, sin garantizar elegibilidad para monetización.

#### Scenario: Faceless but dependent on original recordings
- **WHEN** un canal comparable no muestra rostros pero requiere grabaciones propias o recursos difíciles de obtener
- **THEN** su condición faceless no basta para asignar alta automatización ni bajo coste

#### Scenario: Unknown production cost
- **WHEN** falta una estimación fundamentada de una etapa necesaria
- **THEN** el sistema señala la etapa desconocida y no presenta el coste total ni Creator Fit como confirmados

#### Scenario: Automated route with unresolved material rights
- **WHEN** una ruta automatizable depende de material cuyo uso no está verificado
- **THEN** el sistema muestra esa dependencia pendiente y no convierte la facilidad de producción en una garantía de monetización

### Requirement: Advertising potential without invented revenue
El sistema SHALL priorizar ingresos publicitarios de YouTube, excluir otras fuentes del cálculo inicial y etiquetar cualquier estimación económica con procedencia, rango, formato y supuestos. SHALL distinguir tracción previa a monetización de rentabilidad posterior, sin atribuir RPM privado a competidores ni garantizar que contenido en inglés tenga un RPM determinado.

#### Scenario: No earnings evidence
- **WHEN** las respuestas no incluyen ingresos ni hay un supuesto económico válido y documentado
- **THEN** el componente de monetización queda no disponible sin convertirlo en cero o completar cifras con un modelo de lenguaje

#### Scenario: New channel scenario
- **WHEN** se muestra un escenario económico para un canal todavía no monetizado
- **THEN** los ingresos publicitarios se identifican como condicionados a la elegibilidad y activación de monetización y no se proyectan como cobros desde el primer video

### Requirement: Evidence-based explanations and provisional outcomes
El sistema SHALL presentar Market Score, Creator Fit y confianza separadamente. Solo SHALL calcular una puntuación combinada si ambos scores reúnen sus condiciones mínimas. Las explicaciones SHALL vincular afirmaciones a evidencia o supuestos identificados y SHALL señalar ausencia de datos; un modelo de lenguaje SHALL NOT crear métricas o modificar puntuaciones deterministas.

#### Scenario: Strong views with poor coverage
- **WHEN** un candidato tiene vistas elevadas pero carece de información esencial para evaluarlo
- **THEN** se presenta como pendiente de investigación o provisional, sin una recomendación firme de inversión

#### Scenario: Explanation service unavailable
- **WHEN** falla el modelo de lenguaje o no hay presupuesto para usarlo
- **THEN** las métricas y una explicación estructurada de sus factores continúan disponibles

#### Scenario: Evidence no longer retained
- **WHEN** parte de la evidencia de una evaluación deja de poder conservarse
- **THEN** el sistema no promete reproducibilidad completa de esa evaluación y la señala como no verificable con los datos actualmente disponibles
