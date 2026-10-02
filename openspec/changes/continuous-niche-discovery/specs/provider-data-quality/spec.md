## Purpose

Ofrecer datos externos trazables y utilizables sin confundir valores desconocidos, clasificaciones de proveedores y observaciones verificadas, respetando las condiciones configuradas de cada fuente.

## ADDED Requirements

### Requirement: Provider capabilities and provenance
El sistema SHALL declarar por proveedor las operaciones soportadas, unidades de coste, credenciales requeridas y usos habilitados. Cada dato utilizado SHALL incluir proveedor, operación, fecha de consulta, fecha de observación si existe y versión de normalización. Los secretos SHALL NOT aparecer en respuestas de usuario, claves de caché visibles o registros de diagnóstico.

#### Scenario: Provider lacks a capability
- **WHEN** un análisis requiere una operación no soportada por el proveedor
- **THEN** el sistema informa la limitación y utiliza un sustituto habilitado o entrega un resultado parcial sin inventar el dato

#### Scenario: Provider authentication failure
- **WHEN** una credencial no permite consultar el servicio
- **THEN** el sistema informa que la integración requiere atención sin mostrar la credencial ni repetir indefinidamente la solicitud

### Requirement: Missing and inconsistent values
El sistema SHALL preservar la diferencia entre cero, valor desconocido y valor inconsistente. SHALL registrar las unidades y la definición de métricas del proveedor y SHALL NOT equiparar automáticamente métricas de igual nombre de fuentes diferentes.

#### Scenario: Missing breakout score
- **WHEN** un video devuelve una puntuación de breakout nula
- **THEN** el valor permanece desconocido y no se transforma en cero ni en un video fallido

#### Scenario: Different growth definitions
- **WHEN** una fuente entrega crecimiento porcentual y otra un incremento absoluto
- **THEN** el sistema conserva unidades distintas y solo las compara después de una transformación explícita y verificable

#### Scenario: Conflicting counts
- **WHEN** el número de publicaciones de una ventana supera un total informado sin explicación disponible
- **THEN** el sistema registra la inconsistencia y evita usar ambos valores como si pertenecieran a una misma observación coherente

### Requirement: Cache reuse and freshness
El sistema SHALL reutilizar una respuesta válida para una solicitud equivalente cuando su política lo permita. La identidad de la solicitud SHALL incluir parámetros, filtros, proveedor, versión y ámbito de cuenta cuando corresponda. SHALL distinguir vigencia de caché, fecha real de los datos y plazo máximo de conservación.

#### Scenario: Equivalent request within cache validity
- **WHEN** se repite una consulta cuyos datos siguen vigentes y reutilizables
- **THEN** el sistema devuelve los datos guardados sin una nueva llamada pagada y mantiene la fecha de obtención original

#### Scenario: Cache expired and budget unavailable
- **WHEN** los datos necesitan actualización y no hay presupuesto
- **THEN** el sistema marca la información como desactualizada, si todavía puede conservarla, y aplaza su actualización sin presentarla como reciente

### Requirement: Provider-specific retention and allowed uses
El sistema SHALL mantener políticas versionadas para consulta programada, almacenamiento de respuestas, conservación histórica y cálculos derivados por proveedor y tipo de dato. SHALL permitir desarrollar y probar con datos sintéticos mientras se validan integraciones. Un permiso pendiente SHALL NOT registrarse como confirmado por el carácter personal del proyecto.

#### Scenario: Pending provider conditions
- **WHEN** una integración no tiene validado un uso requerido para almacenamiento histórico o puntuación
- **THEN** ese uso permanece deshabilitado y visible como pendiente mientras el resto de funcionalidades independientes continúa disponible

#### Scenario: Retention deadline reached
- **WHEN** vence el plazo de conservación de una observación
- **THEN** el sistema la elimina o actualiza según la política aplicable y aplica el tratamiento correspondiente a sus derivados y referencias

#### Scenario: Provider policy changes
- **WHEN** se registra una nueva política con plazos o usos diferentes
- **THEN** el sistema la aplica a nuevas operaciones y revisa los datos existentes afectados, preservando un registro de la acción sin conservar contenido prohibido

### Requirement: Evidence coverage disclosure
El sistema SHALL mostrar para cada análisis cantidad de canales y videos válidos, formatos, ventanas temporales, campos faltantes, exclusiones y fecha de actualización. El total estimado por una búsqueda SHALL NOT presentarse como censo verificado del nicho.

#### Scenario: Search reports more results than returned
- **WHEN** el proveedor informa un total de coincidencias pero solo entrega una parte
- **THEN** el análisis identifica la muestra efectivamente recibida y no usa el total como denominador de una tasa de éxito

### Requirement: Bounded complementary YouTube enrichment
El sistema SHALL poder enriquecer por ID los videos candidatos descubiertos por vidIQ mediante `videos.list`, sin usar YouTube como búsqueda temática. SHALL agrupar como máximo 50 IDs por solicitud, contabilizar la cuota separadamente, conservar procedencia de ambas fuentes y mantener la clasificación de formato del descubrimiento cuando YouTube no la confirme. La integración SHALL permanecer sin llamadas cuando esté deshabilitada o en modo sintético.

#### Scenario: Candidate enriched by the canonical source
- **WHEN** vidIQ entrega un candidato y YouTube devuelve el mismo ID con estadísticas o idioma declarado más recientes
- **THEN** el sistema mantiene una sola identidad de video, usa los campos complementarios compatibles y enlaza la evaluación con ambas observaciones

#### Scenario: Enrichment is disabled or lacks quota
- **WHEN** YouTube está deshabilitado, su política está pendiente o el límite de cuota no admite otra solicitud
- **THEN** el sistema no llama a YouTube y conserva el resultado de vidIQ como deshabilitado, aplazado o parcial según corresponda

#### Scenario: Non-authorized YouTube metadata reaches retention deadline
- **WHEN** una observación de YouTube cumple su plazo configurado, nunca superior a 30 días
- **THEN** el sistema la elimina mediante la limpieza común y no conserva sus campos dentro de derivados o explicaciones vigentes
