## Context

Ver [proposal.md](proposal.md) para motivación y alcance. El repositorio contiene dos documentos conceptuales y OpenSpec, sin aplicación existente. Los PDF son contexto, no contratos ya implementados: la conversación añadió descubrimiento desde cero, Shorts, exploración periódica, presupuesto compartido y futuros experimentos paralelos.

El usuario dispone de un Mac Studio y un VPS Contabo compartido (6 CPU, 12 GB RAM, 400 GB SSD) administrado con Easypanel y despliegues por imágenes Docker. No se ha inspeccionado la capacidad libre del VPS. El presupuesto de operación y producción es US$100–150 al mes; Claude, ChatGPT y Google AI Pro existentes están excluidos. La disponibilidad base es 15 horas semanales, ampliable por decisión expresa del usuario. No se presume que suscripciones de chat incluyan saldo de API ni que un crédito promocional esté activado.

Actualización de integración (2026-09-21): la documentación oficial de vidIQ MCP
admite claves API Bearer propias además de OAuth. Se prepara esa vía dentro del
mecanismo oficialmente admitido, sin credenciales del conector de conversación.
El diagnóstico de conexión solo usa inicialización y catálogo MCP; no autoriza
investigación, conservación ni gasto. Ver `docs/vidiq-connection.md`.

### Evidencia de la prueba exploratoria

Prueba del conector disponible en la conversación, con un tema ilustrativo de astronomía; no se trató de una recomendación de nicho ni de una validación desde el VPS:

| Operación | Observación | Créditos |
|---|---|---:|
| Búsqueda de canales, inglés, faceless, hasta 50.000 suscriptores | 20 canales; 10 sin clasificación de formato; 20 sin estimación de ingresos en esa respuesta | 5 |
| Publicaciones recientes de un canal, formato largo | 31 videos, con éxitos y publicaciones habituales; 13 sin breakout score | 5 |
| Outliers Shorts con consulta amplia `space` | 20 resultados, incluyendo coincidencias ajenas a astronomía | 5 |

Saldo antes/después: 170/155 créditos. La cuenta informó 150 créditos renovables y 20 adicionales inicialmente, y 135 renovables más 20 adicionales después. Estos números describen la prueba, no constantes de implementación. No se debe inferir cobertura total ni paginación completa de `channel_videos` a partir de esos 31 elementos. Las unidades y semántica de crecimiento del proveedor también deben comprobarse.

## Goals / Non-Goals

**Goals:**

- Construir un monolito modular con procesos separados para interfaz, solicitudes y trabajo periódico.
- Mantener trazabilidad de muestras, cálculos, gasto y decisiones, compatible con plazos de conservación por fuente.
- Separar el desarrollo verificable con datos sintéticos de la habilitación operativa de proveedores reales.
- Permitir calibrar políticas de descubrimiento y puntuación sin cambiar contratos o migraciones.
- Preparar identidades y escenarios de recursos que puedan conectar con experimentos posteriores.

**Non-Goals:**

- No construir todavía una plataforma distribuida entre VPS y Mac, una cola de producción multimedia o un optimizador de carteras.
- No exigir GPU, búsqueda vectorial remota ni entrenamiento supervisado para ejecutar el radar.
- No garantizar ejecución exactamente una vez en proveedores que no admiten idempotencia.
- No prometer reproducibilidad indefinida si la evidencia debe expirar.

## Decisions

### 1. Monolito Python y cuatro servicios de Easypanel

Usar Python con uv, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL y Streamlit. Seleccionar versiones estables compatibles y fijarlas en lockfile al implementar.

```text
Navegador autenticado
         |
         v
Proxy HTTPS de Easypanel --> Dashboard (Streamlit)
                                  |
                                  v
                              API (FastAPI)
                                  |
                                  v
                              PostgreSQL
                                  ^
                                  |
                       Worker + planificador
                                  |
                                  v
                       Adaptadores de proveedores
```

API y worker comparten una imagen y el mismo paquete de dominio, con comandos distintos. El dashboard usa una imagen propia. Solo el dashboard necesita dominio público; API, worker y PostgreSQL se comunican por la red interna. El worker no necesita un servidor HTTP público para ejecutar o reportar salud.

Usar autenticación de acceso en el proxy para el dashboard personal, HTTPS y credenciales de servicio para llamadas dashboard/API. La API también valida ese acceso de servicio: compartir red con otras aplicaciones no se considera autenticación. El panel administrativo de Easypanel mantiene sus propios controles.

Decisión de despliegue autorizada: por el límite de proyectos del plan actual, crear
`nicheradar-api`, `nicheradar-worker`, `nicheradar-dashboard` y `nicheradar-db` dentro
de `proy1-credito-riesgo`. Mantener credenciales, almacenamiento, límites y ciclo de
despliegue propios; no reutilizar bases ni modificar servicios, variables compartidas
o ajustes globales existentes. Se acepta compartir la red interna del proyecto, no
se afirma aislamiento de red frente a sus otras aplicaciones. La autenticación de
API y PostgreSQL sigue siendo obligatoria. No ampliar la licencia automáticamente.

Alternativas: Streamlit llamando directamente al dominio simplificaría procesos, pero mezclaría interacción y operación; React agregaría trabajo de interfaz sin resolver la incertidumbre de datos; microservicios y Redis no aportan una necesidad demostrada en esta escala.

### 2. Dominio y persistencia orientados a evidencia

Organización propuesta: `apps/api`, `apps/dashboard`, `src/nicheradar/{domain,integrations,discovery,features,topics,scoring,recommendations,repositories,services,workers}`, `migrations` y `tests`. Los módulos no acceden directamente a credenciales ni a respuestas específicas del proveedor.

Entidades iniciales:

| Grupo | Entidades y contenido |
|---|---|
| Perfil | `creator_profiles`, `budget_policies`, `production_recipes`: recursos, exclusiones y supuestos versionados |
| Exploración | `seed_families`, `discovery_queries`, `analysis_runs`, `jobs`: catálogo, consultas, cobertura y progreso |
| Fuentes | `provider_policies`, `provider_requests`, `provider_cache`, `raw_observations`: usos habilitados, coste, caché y respuestas permitidas |
| Datos | `channels`, `videos`, `channel_observations`, `video_observations`: identidad externa separada de valores observados |
| Muestras | `cohorts`, `cohort_memberships`, `topics`: criterio de selección, formato, idioma, ventana, inclusión y exclusión |
| Evaluación | `opportunities`, `evaluation_versions`, `feature_values`, `evidence_links`: identidad, puntuaciones y referencias |
| Decisiones | `opportunity_decisions`, `budget_scenarios`, `scenario_items`: decisiones del usuario y combinaciones hipotéticas |
| Recursos | `cost_ledger`, `credit_balances`, `cost_reservations`: consumo, saldos, conciliación y límites |

Usar UUID internos e identificadores externos únicos por plataforma/recurso. Las relaciones tema/video permiten pertenecer a varios temas, pero cada video se cuenta una vez por cohorte. Separar cuenta proveedora y ámbito de autorización cuando afecten a datos o caché. Los textos originales, embeddings y explicaciones que incorporen datos externos tienen también procedencia y caducidad.

Una oportunidad representa tema/subtema + audiencia + idioma + formato; cambiar una etiqueta no cambia el UUID. Si un agrupamiento nuevo parece corresponder al existente, registrar evidencia de correspondencia. Las fusiones ambiguas no son automáticas. Una futura propuesta de canal puede agrupar oportunidades de distintos formatos para una audiencia coherente: seleccionar dos formatos no equivale a crear dos canales.

Alternativa descartada: una fila mutable por video como único histórico; impediría atribuir cambios a observaciones y hacer seguimiento coherente. Guardar cada respuesta para siempre tampoco es un requisito: se aplica la política de la fuente.

### 3. Proveedores intercambiables y condiciones explícitas de uso

Definir operaciones de búsqueda de canales, publicaciones de canal por formato, outliers, keywords, estadísticas y consulta de saldo, con resultados tipados que incluyan cobertura, unidades y coste. vidIQ MCP es el primer adaptador candidato: se ha probado su utilidad, no su funcionamiento desde una aplicación independiente. El cliente MCP se autentica mediante un mecanismo oficialmente admitido para la cuenta; no reutiliza credenciales internas de esta conversación.

YouTube Data API se conecta como enriquecimiento complementario por ID después del descubrimiento de vidIQ. La V1 operativa usa `videos.list` en lotes de hasta 50 candidatos, con cuota, caché, políticas, ámbito de cuenta y conservación separados. Los IDs entregados por vidIQ y YouTube comparten la identidad canónica de plataforma `youtube`, mientras cada observación conserva su proveedor. Los metadatos directos pueden completar título, descripción, vistas, fecha, duración e idioma declarado; no sustituyen categorías o formato de vidIQ por coincidencia de nombre. Esto no garantiza identificación exacta de Shorts: la duración sola no determina el formato. La integración es opcional, no se ejecuta en modo sintético y su ausencia deja utilizable la evidencia primaria.

Google Trends, análisis visual costoso y transcripciones masivas no son dependencias obligatorias de la V1. Las señales correspondientes pueden quedar ausentes. Esto reduce proveedores y llamadas iniciales, manteniendo interfaces extensibles.

**Decisión operativa sobre condiciones pendientes:** desarrollar contratos, flujo y pruebas con datos sintéticos; habilitar cada uso real mediante una política explícita con estado `pending`, `enabled` o `disabled`, fuente de la condición y alcance. Una política pendiente no equivale a permiso confirmado. La respuesta del proveedor puede afectar qué capacidades de ese adaptador se habilitan, sin cambiar los contratos del dominio; si ningún proveedor habilitado permite una capacidad esencial, el modo real de esa capacidad se declara no disponible y se replanifica la integración, no se falsean resultados.

Se ha enviado a vidIQ una consulta sobre consultas programadas, almacenamiento local, históricos y derivados. El conector devolvió `submitted`, sin ticket, plazo o confirmación de permiso. No se espera esa respuesta para terminar planificación o desarrollo independiente del proveedor.

Alternativa descartada: sustituir automáticamente datos de vidIQ por YouTube para toda métrica. Diferencias de definición, cobertura y condiciones hacen necesario declarar cada uso, no intercambiar valores por nombre.

### 4. Caché, conservación y datos incompletos

Clave de caché: proveedor + operación + parámetros canónicos + versión de contrato + ámbito de autorización, sin secretos. Un acierto conserva la fecha original y cuesta cero llamadas; un vencimiento no autoriza gastar ni extiende el plazo de conservación.

Separar `fetched_at`, `observed_at`, `cache_valid_until` y `retain_until`. Las respuestas originales se guardan solo si la política lo permite. Las observaciones y derivados referencian su política y fuentes. Una tarea de limpieza aplica vencimientos también a explicaciones, vectores y respaldos; no conservar estadísticas expiradas dentro de logs o textos. Las decisiones propias pueden conservarse sin copiar la evidencia eliminada, si su política lo permite.

Valores nulos permanecen nulos. Crecimiento porcentual y absoluto son métricas distintas. Registrar contradicciones sin asumir que una eliminación de videos, actualización tardía o error del proveedor tiene una causa conocida. La clasificación faceless se considera señal del proveedor, no comprobación de automatización ni derechos sobre material.

Alternativa descartada: convertir todos los nulos a cero para simplificar cálculos; daría conclusiones falsas y penalizaría proveedores con menor cobertura.

### 5. Descubrimiento por catálogo, expansión y cohortes

El usuario no proporciona nichos. El sistema comienza con un catálogo pequeño, amplio y versionado de familias, por ejemplo ciencia, historia, tecnología, naturaleza, educación, cultura y entretenimiento. Sus etiquetas sirven como entradas de búsqueda y no como recomendaciones. Ampliar el catálogo y sus consultas sin alterar código.

Flujo: seleccionar familias pendientes → buscar canales/temas → filtrar relevancia → expandir subtemas → reunir publicaciones recientes y ejemplos de outliers → deduplicar → construir cohortes → evaluar → actualizar backlog.

Aplicar verificación temática con títulos, descripciones y categorías disponibles. Un clasificador o LLM opcional devuelve etiqueta, evidencia y confianza; una coincidencia ambigua se excluye del cálculo hasta verificarse. No interpretar un filtro de idioma como garantía del audio del video.

Muestrear por estratos de tamaño, no únicamente canales exitosos ni únicamente pequeños. Valor inicial propuesto de canal pequeño: hasta 50.000 suscriptores, configurable. Incluir canales mayores para contextualizar concentración y competencia. Las consultas de publicaciones recientes son el camino inicial para formar denominadores; los outliers amplían descubrimiento y no constituyen por sí solos una muestra de tasas.

Ventana inicial propuesta: 90 días de publicación, con franjas de antigüedad de 0–2, 3–7, 8–30 y 31–90 días. Mantener Shorts y long-form separados. Datos anteriores solo entran en un baseline explícito, si están disponibles y su conservación está habilitada. Si una respuesta no permite completar una ventana, registrar cobertura parcial.

**Subnichos de V1:** agrupación inicial por embeddings de títulos/descripciones con modelo versionado, umbral de similitud configurable y tamaño mínimo de grupo. Etiquetado posterior opcional con LLM. Conservar grupo desconocido y detectar duplicados por miembros/centroides sin identificar el grupo por su etiqueta. No exigir UMAP/HDBSCAN, transcripciones o pgvector para el primer flujo; embeddings pueden calcularse por lotes en CPU y guardarse en PostgreSQL si la política lo permite. Introducir pgvector cuando la búsqueda por similitud medida lo justifique. Fallback sin presupuesto/modelo: categorías del proveedor identificadas como tales, sin presentarlas como clustering propio validado.

Alternativas: explorar todo diariamente es inviable con el presupuesto inicial; usar únicamente tendencias favorecería resultados ya exitosos; imponer clustering complejo desde el arranque dificultaría aislar problemas de datos.

### 6. Programación gradual y límites

Valores iniciales propuestos, editables antes de activar el radar:

- Zona horaria de presentación y programación: `America/Lima`; almacenamiento temporal en UTC.
- Planificador revisa trabajo cada hora. La comprobación interna no requiere llamadas al proveedor.
- Actualización de candidatos seleccionados: objetivo diario; candidatos en seguimiento: objetivo semanal. Se aplazan si faltan recursos.
- Exploración del catálogo: repartir lotes durante la semana; reservar inicialmente 25% de las llamadas asignadas a descubrimiento para familias nuevas o menos recientemente exploradas. Rotación persistente evita concentrarlo todo en favoritos.
- Concurrencia inicial: un trabajo externo activo. Esto limita carga de investigación y no el número de canales que pueden contemplarse en escenarios.
- Perfil gratuito: límite inicial propuesto de 5 créditos por ejecución pagada, 25 por semana y 100 por ciclo renovable del proveedor, siempre limitado además por saldo real. El usuario puede editarlo; es una configuración de arranque prudente, no la capacidad recomendada definitiva.
- Radar inicialmente pausado hasta configurar credenciales, políticas y presupuesto. La prueba exploratoria de 15 créditos ya realizada no autoriza barridos nuevos desde este cambio documental.

Separar calendario financiero mensual, ventanas de planificación semanales y renovación propia de cada proveedor. Los valores por defecto son decisiones de diseño propuestas, no preferencias confirmadas del usuario. Si una operación requiere más recursos que el perfil, mostrarla aplazada para ajustar la configuración, sin fragmentarla para eludir límites.

Una ejecución puede terminar como parcial por su propio límite y conservar la cobertura pendiente. Ejecuciones futuras pueden ampliar la muestra reutilizando observaciones permitidas; no se reinicia artificialmente un run ni se crean runs adicionales inmediatos para evitar el límite. Alcanzar el mínimo de evaluación puede requerir varios ciclos.

### 7. Puntuación interpretable y calibración explícita

Implementar primero métricas observables y después puntuaciones. Cada evaluación referencia una cohorte, observaciones retenidas, versión de transformaciones, baseline y configuración. Las transformaciones usan referencias congeladas por formato: no min/max del lote actual.

Modelo inicial propuesto:

- Demanda `D`: mediana de vistas por día desde publicación por franja comparable, normalizada logarítmicamente contra una referencia por formato. Es un promedio acumulado, no VPH observado.
- Breakout `B`: proporción de videos de canales pequeños que superan el umbral declarado respecto a un baseline comparable del canal. Baseline propio: mediana excluyendo el video evaluado, mismo formato y franja de antigüedad, mínimo inicial de 5 publicaciones comparables; umbral inicial 5x. No combinar ese cálculo con `breakoutScore` del proveedor como si fueran equivalentes. El score del proveedor se puede mostrar como evidencia con su propia definición.
- Competencia `C`: atractivo por concentración de vistas de la muestra, con HHI normalizado para el número de canales e invertido. Mostrar también top-5 share; etiquetar como proxy de concentración, no dificultad real de entrada ni cuota total de mercado. Con menos de dos canales no se calcula.
- Tendencia `T`: cambio de vistas entre observaciones comparables de la misma cohorte, con ventana y cobertura explícitas, normalizado contra una referencia congelada. No usar vistas acumuladas divididas por antigüedad como sustituto de crecimiento observado.
- Potencial publicitario `M`: solo cuando exista benchmark/estimación con fuente, formato, supuestos y uso habilitado. Sin esa información queda desconocido. No usar automáticamente el país del canal como audiencia real.

Mostrar además oferta observada: publicaciones en 7/30/90 días y canales activos de la muestra, sin afirmar que equivalen al total del nicho. Evergreen queda como evidencia temporal opcional cuando exista historia suficiente; no se deduce únicamente de que un tema parezca atemporal.

Normalizador inicial para D y un benchmark económico comparable de M: `100 * clamp(log1p(x) / log1p(reference_p90), 0, 1)`. Para B usar `100 * breakout_rate`; para C, `100 * (1 - (HHI - 1/n) / (1 - 1/n))`, con n mayor que uno y total de vistas positivo. Para T comparar velocidades observadas entre dos intervalos equivalentes de la misma cohorte y usar `50 + 50 * tanh(relative_change / reference_p90_abs_change)`; si faltan intervalos o el denominador base es cero, T queda desconocido. Referencias deben ser positivas, finitas y válidas para el formato. El baseline de referencia se obtiene de un piloto documentado por formato, se congela y se versiona. Los parámetros de pruebas sintéticas no pueden habilitar recomendaciones reales. Hasta disponer de referencias reales revisadas, mostrar métricas y estado `uncalibrated` sin Market Score numérico.

Pesos iniciales propuestos: D 0,25; B 0,30; C 0,20; T 0,15; M 0,10. Fórmula: suma ponderada de componentes disponibles dividida por suma de sus pesos. Mostrar esa cobertura y la falta de T/M. D, B y C son obligatorios para un Market Score provisional; exigir inicialmente 20 videos válidos de 5 canales, y para B al menos 10 videos de 3 canales pequeños con clasificación posible para al menos 80% de sus publicaciones elegibles. Estos mínimos son controles de muestra, no garantías estadísticas. Una tasa con clasificación parcial declara su denominador efectivo y cobertura. No comparar rangos como plenamente equivalentes cuando utilizan conjuntos distintos de componentes.

**Creator Fit:** recetas de producción versionadas por audiencia/formato, con etapas, volumen propuesto, herramientas, coste fijo/variable, capacidad de generación, margen de repeticiones y horas humanas. Cada etapa requiere fuente o estimación manual identificada. Rúbrica inicial propuesta: automatización 30%, esfuerzo humano 25%, coste 25%, disponibilidad de recursos visuales 20%; cada dimensión se valora con anclas explícitas 0/25/50/75/100 y evidencias. Umbrales y anclas se documentan junto al piloto. Una dimensión esencial desconocida impide completar Fit; costes y horas siguen mostrándose como rangos, sin falsa precisión.

La receta incluye revisión de originalidad, dependencia de material ajeno y posibilidad de contenido repetitivo, con evidencia y cuestiones pendientes; una etiqueta faceless o AI-friendly no equivale a elegibilidad de monetización. No ofrecer certificaciones automáticas de copyright o cumplimiento. Para medidas basadas en suscriptores actuales, declarar ese instante de observación: no se conoce necesariamente el tamaño del canal cuando publicó el video.

Final Score propuesto: `0,65 * Market Score + 0,35 * Creator Fit`, solo con ambos válidos. Confianza se muestra aparte: `insufficient` si falla un mínimo esencial; `provisional` si se cumplen mínimos pero faltan componentes, referencias revisadas o verificación de relevancia; `supported` cuando los componentes declarados, referencias y controles están completos. Ninguna etiqueta equivale a confianza estadística o validación predictiva. Confianza no multiplica silenciosamente el score. Un candidato de score alto no pasa controles duros de presupuesto, producción o condiciones de uso solo por su puntuación.

Estados de evaluación: `insufficient_evidence`, `uncalibrated`, `provisional`, `ready_for_review`; no equivalen a decisiones del usuario ni a permisos para lanzar canales. No adoptar umbrales universales ENTER/WATCH/AVOID de los PDF sin validación. La explicación usa componentes y evidencias; ante fallo del LLM, una plantilla determinista sigue siendo útil.

Alternativas: un score único mezclaría mercado con restricciones personales; aprender pesos sin resultados históricos no tiene etiquetas válidas; permitir al LLM completar valores faltantes produciría números sin evidencia.

### 8. Backlog y escenarios compartidos

Separar estado de evaluación de estado de revisión: `new`, `watching`, `selected`, `dismissed`. Las decisiones son eventos del usuario con notas. Una actualización añade una evaluación y no sustituye un descarte. La vista compara últimas evaluaciones compatibles y explica cambios en métricas, método o posición relativa.

Escenarios de V1 son selecciones manuales de propuestas de canal; cada una agrupa oportunidades/formatos y una receta/volumen de producción. Calcular:

`gasto mensual estimado = costes del radar + herramientas compartidas + consumos variables de todos los canales + reserva`.

Cada herramienta compartida se cuenta una vez, pero su capacidad se consume por todas las propuestas. Comparar horas en la misma unidad temporal (si se convierten semanas a mes, usar y mostrar 52/12). No extrapolar coste por video sin indicar volumen y repeticiones. Usar el extremo superior del rango para declarar que un escenario cabe; si hay costes esenciales desconocidos, marcar no evaluable. Registrar valor bajo/alto para comparación, no como gasto ejecutado.

No crear aún una entidad de experimento activo ni un optimizador. Las identidades de oportunidad, decisiones, versiones de receta y escenario ofrecen el punto de conexión posterior. En futuras fases una aprobación deberá fijar hipótesis, gasto, plazo y criterios; cerrar significará detener inversión y no borrar automáticamente canales o contenido.

Alternativa descartada: tomar los N primeros del ranking hasta sumar US$150. Ignoraría suscripciones compartidas, capacidad de herramientas y horas de supervisión.

### 9. Ejecución durable y contabilidad del gasto

PostgreSQL mantiene cola, programación y reservas. Clave única por ocurrencia programada; planificador único mediante lease/lock. Worker reclama jobs transaccionalmente con bloqueo de fila y lease con heartbeat. Etapas: planificación, consulta, enriquecimiento opcional, normalización, formación de muestra, métricas, evaluación y actualización. El enriquecimiento guarda recibos por lote antes de avanzar, por lo que un reinicio reutiliza caché y no repite a ciegas una solicitud. Estado de cada etapa se confirma antes de avanzar.

Antes de una solicitud externa: validar usos habilitados → consultar caché → verificar coste máximo → reservar USD/créditos transaccionalmente → enviar solicitud → persistir resultado permitido y conciliar coste → confirmar etapa. Mantener orden de bloqueos consistente para evitar deadlocks entre límites concurrentes. No convertir créditos incluidos en suscripción a un gasto USD duplicado: la compra se registra como fijo y el consumo como agotamiento de capacidad.

Los jobs son al menos una vez; solicitudes con idempotencia del proveedor reutilizan su identificador. Sin ella, timeout tras envío produce `unknown_charge` y no reintento automático hasta conciliación. Los errores inequívocos previos al envío pueden reintentarse; respuestas de autenticación/cuota o condiciones pendientes requieren corrección y no un bucle. Backoff con jitter y máximo propuesto de 3 intentos para fallos transitorios seguros. El saldo remoto puede bajar por uso fuera del radar: conciliar al inicio de un lote y antes de llamadas si la observación está desactualizada.

Al reiniciar: recuperar leases vencidos, respetar las operaciones de cobro incierto y consolidar las ocurrencias perdidas en un trabajo de recuperación por programa, no en una ráfaga ilimitada. Una copia restaurada arranca pausada y no comparte el planificador activo del entorno original.

Alternativa: cron dentro del contenedor sin registro durable o tareas largas dentro de peticiones HTTP perderían progreso y dificultarían atribuir consumo.

### 10. API, interfaz y operación

Superficie inicial propuesta bajo `/api/v1`: perfil y políticas de presupuesto; control/estado del radar; ejecuciones y sus etapas; oportunidades y detalle de evidencia; decisiones de revisión; escenarios de recursos; consumo y estado de proveedores. Listados paginados. Acciones manuales idempotentes no bloquean hasta completar el análisis: devuelven identificador de ejecución. Ningún endpoint de V1 crea canales o publica videos.

Pantallas: resumen, backlog filtrable, detalle de oportunidad, escenarios, configuración/operación. La interfaz diferencia sin datos, pendiente de configuración, falta de presupuesto, datos caducados y error técnico. Navegación en español; evidencia en idioma original. Exponer fecha de última ejecución exitosa, antigüedad de datos y consumo, sin publicar secretos.

Desarrollo local con datos sintéticos y PostgreSQL aislado. Pruebas de contrato de proveedor con fixtures sintéticos; pruebas reales opt-in, con tope explícito de llamadas. Docker Compose para desarrollo; producción puede usar servicios App y Postgres de Easypanel sin depender de su modalidad Compose. Fijar etiquetas de imagen/digest, verificar arquitectura CPU del VPS y construir para ella desde el Mac.

## Risks / Trade-offs

- [Uso de históricos y derivados pendiente por proveedor] → Políticas por operación/tipo de dato y activación explícita; desarrollo sintético independiente; no atribuir permiso al uso personal.
- [Sesgo de descubrimiento y clasificación imprecisa] → Estratos de tamaño, publicaciones recientes además de éxitos, desconocidos explícitos, revisión de relevancia y cobertura visible.
- [Solo hay evidencia de un tema en la prueba] → El piloto de calibración debe cubrir distintas familias y ambos formatos antes de presentar puntuaciones como calibradas.
- [Coste y semántica de herramientas pueden cambiar] → Versionar contratos/tarifas, conciliar saldo y bloquear una operación cuyo máximo sea desconocido.
- [Presupuesto gratuito pequeño] → Reparto semanal, caché y prioridad por ganancia de información; evaluar planes pagos después de medir rendimiento por crédito y precio real de la cuenta.
- [Recetas con costes inciertos o ingresos aún inexistentes] → Rangos y origen del supuesto, prueba posterior de producción; no confundir tracción inicial con rentabilidad.
- [Conservación limita reconstrucción de evaluaciones] → Mostrar evidencia expirada; eliminar también derivados según política; conservar decisiones propias sin copiar datos externos restringidos.
- [VPS comparte recursos] → Inspección previa, límites por servicio, worker de baja concurrencia y pruebas de carga moderada antes de activar programación.
- [Fallo entre cobro y persistencia] → Reservas durables, idempotencia cuando exista y conciliación de cobros inciertos; no prometer exactamente una vez.
- [Clustering o embeddings consumen memoria] → Lotes pequeños, modelo CPU acotado, descarga durante preparación, fallback explícito y medición antes de introducir búsquedas vectoriales.

## Migration Plan

1. Implementar el dominio y flujo completo con fixtures sintéticos; verificar contratos de specs sin credenciales reales.
2. Preparar migraciones iniciales, imágenes reproducibles y configuración documentada; el proyecto actual no tiene datos que migrar.
3. Inspeccionar recursos, servicios, versión de Easypanel y arquitectura CPU del VPS mediante acceso de lectura. Elegir límites reales a partir de esa inspección. No eliminar aplicaciones.
4. Crear exclusivamente los servicios con prefijo `nicheradar-` en el proyecto existente `proy1-credito-riesgo`, PostgreSQL persistente y credenciales propias; desplegar dashboard/API/worker con programación pausada y autenticación activa. No modificar servicios ajenos; la red interna del proyecto es compartida según la decisión autorizada.
5. Validar persistencia, migración, salud, reinicio, copia y restauración en entorno aislado. No publicar la base de datos ni dejar fixtures accesibles como evidencia real.
6. Habilitar solo operaciones de proveedores con credenciales, condiciones y costes establecidos. Ejecutar un piloto con presupuesto explícito, verificar relevancia y tiempos, y congelar una primera referencia de calibración cuando haya evidencia suficiente. Si no la hay, usar vistas de métricas sin score calibrado.
7. Activar el calendario conservador y observar un ciclo; ajustar frecuencias dentro de los límites. Registrar métricas de calidad y coste para decidir si ampliar vidIQ.
8. Rollback: pausar worker, conservar respaldo coherente y volver al digest anterior si es compatible con el esquema. Para cambios incompatibles, restaurar en un volumen separado y verificar antes de cambiar tráfico. Nunca sobrescribir o borrar automáticamente la base activa.

La planificación no ejecuta despliegues ni autoriza compras o eliminación de aplicaciones. Los pasos anteriores forman parte del trabajo posterior de implementación y operación.

## Open Questions

Estos valores pueden resolverse durante configuración sin cambiar contratos: dominio privado, arquitectura/versiones efectivas del VPS, límites disponibles por servicio, referencia de imagen, precio vigente de un eventual plan vidIQ y beneficios de Google efectivamente activados. Cadencias, pesos, mínimos de muestra, recetas y límites iniciales son parámetros versionados propuestos en este diseño que se revisarán con el piloto.

Las condiciones de uso de proveedores no se tratan como una pregunta diferible sin consecuencias: la decisión de activación y el comportamiento de capacidades pendientes están definidos en la sección 3 y en las especificaciones.

## References

- Contexto local: `docs/NicheRadar.pdf` y `docs/Arquitectura V1.pdf`; cifras y fórmulas ilustrativas, no resultados validados del producto.
- [vidIQ MCP](https://support.vidiq.com/en/articles/15082430-vidiq-mcp): integración para desarrolladores; algunos detalles del artículo difieren de los contratos de herramientas observados, por lo que el coste debe verificarse por operación.
- [vidIQ Terms](https://vidiq.com/terms/): condiciones generales sobre recopilación y bases de datos; alcance del uso propuesto consultado al proveedor y pendiente.
- [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies): restricciones generales de conservación y métricas derivadas. [Condiciones adicionales](https://developers.google.com/youtube/terms/derived-metrics-policy): vía para casos aceptados de analítica con determinadas métricas y conservación estadística ampliada; no se presume aceptación del proyecto.
- [YouTube playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list): publicaciones por páginas. [channels.list](https://developers.google.com/youtube/v3/docs/channels/list): metadatos de canales. [videos.list](https://developers.google.com/youtube/v3/docs/videos/list): datos por video.
- [YouTube Partner Program](https://support.google.com/youtube/answer/72851) y [políticas de monetización](https://support.google.com/youtube/answer/1311392): fuentes para condiciones económicas y contenido; revisar vigencia antes de configurar estimaciones.
- [Easypanel App](https://easypanel.io/docs/services/app) y [Postgres](https://easypanel.io/docs/services/postgres): imágenes, redes internas y persistencia.

Las fuentes externas anteriores se revisaron durante la exploración de septiembre de 2026. No constituyen verificación permanente de precios, permisos de cuenta o comportamiento de futuras versiones.
