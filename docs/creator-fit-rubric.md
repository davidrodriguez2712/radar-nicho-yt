# Creator Fit v2 (estimación manual, no validación predictiva)

Cada dimensión exige una valoración manual con evidencia y una receta completa de
ideación, investigación, guion, voz, visuales, edición y revisión. No se deriva
automatización de una etiqueta faceless. Cada etapa declara coste variable y horas
por video, herramienta/capacidad, fuente del supuesto y margen de repeticiones.

| Ancla | Automatización (30%) | Esfuerzo humano (25%) | Coste (25%) | Recursos visuales (20%) |
|---:|---|---|---|---|
| 0 | Producción manual indispensable | No cabe en horas disponibles | No cabe en presupuesto | Recursos imprescindibles no disponibles |
| 25 | IA solo auxilia tareas aisladas | Cabe únicamente reduciendo mucho el volumen | Solo cabe reduciendo mucho el volumen | Recursos escasos y adquisición difícil |
| 50 | Varias etapas semiautomáticas | Cabe con poco margen para revisión | Cabe con poco margen para repeticiones | Recursos posibles con adquisición manual |
| 75 | Mayoría de etapas automatizables, revisión humana | Cabe con margen documentado | Cabe incluyendo repeticiones y reserva | Recursos suficientes con revisión de uso pendiente |
| 100 | Flujo completo probado con revisión humana acotada | Piloto confirma holgura al volumen declarado | Piloto confirma costes con holgura | Recursos propios/licenciados suficientes y documentados |

No basta marcar un número: el ancla debe corresponder a un piloto, ensayo manual o
estimación identificada. Sin dimensiones o costes esenciales, Fit queda desconocido.
Los controles de horas, dinero y capacidad del escenario siguen siendo obligatorios
aunque Fit sea alto. Derechos, originalidad y repetición mantienen revisiones propias;
la puntuación no certifica copyright ni elegibilidad de monetización.

## Completitud y recursos

La ponderación de las anclas no cambió respecto a v1. La versión `creator-fit-v2`
añade el contexto completo: audiencia, idioma, formato, volumen mensual, repeticiones,
herramientas compartidas, coste fijo, capacidad y perfil de recursos. La suma de anclas
por sí sola (`rubric_score`) ya no se presenta como un Creator Fit completo.

`evaluate_plan` devuelve `incomplete` y score nulo si faltan etapas, fuentes, costes,
horas, modo de automatización, herramientas necesarias o cualquiera de las cuatro
anclas. Cada etapa con IA o semiautomática requiere una herramienta identificada. La
capacidad debe declararse en unidades compatibles con su herramienta; minutos y créditos
no se convierten implícitamente. Un cero puede ser una estimación explícita; un nulo no
se sustituye por cero. Fuentes o evidencias en blanco no completan una dimensión.

Los rangos de costes variables y horas se multiplican por `videos_per_month ×
(1 + rework_margin)`. Los consumos de capacidad se acumulan con ese mismo margen.
Cada herramienta compartida se declara y cobra una vez por escenario. No incluir de
nuevo su suscripción en el coste variable por video: éste representa únicamente costes
adicionales no cubiertos por el fijo declarado. Radar y reserva entran en el total;
la reserva aplicada no puede ser menor que la del perfil.

Las horas mensuales disponibles usan `horas semanales × 52/12`. La viabilidad se decide
con el extremo superior de los rangos, el techo mensual y la capacidad declarada. Se
reporta por separado como `viable`, `not_viable` o `not_evaluable`. Un Fit estimado alto
no cambia ese resultado. Las anclas son juicios manuales, no una comprobación automática
de su evidencia; revisarlas si cambian costes, volumen o disponibilidad personal.

Claude, ChatGPT y Google AI Pro existentes solo se excluyen del coste fijo cuando se
declara la exclusión admitida por el perfil. No se les asignan créditos API ni capacidad
ilimitada. Si su capacidad necesaria es desconocida, el Fit permanece incompleto.

Derechos, originalidad y repetición mantienen sus notas propias. Un pendiente se muestra
como advertencia y puede coexistir con un Fit estimado: el score describe la receta, no
autoriza su uso ni garantiza monetización. No se ejecuta ningún servicio multimedia.

## Receta por defecto (autoaplicada)

Toda oportunidad nueva recibe automáticamente, en la etapa `evaluation` del worker, una
receta genérica por defecto si todavía no tiene ninguna asignada; nunca sobrescribe una
asignación manual existente. La receta declara las 7 etapas como IA local/API o código
determinista, sin horas humanas por video: `gpt-6-luna` (ideación, investigación, guion,
revisión), un modelo de voz local, `gemini-3.1-flash-image` (10 imágenes/video) y ffmpeg
local para edición. Los costes citan su fuente real (tarifa de `gpt-6-luna` verificada y
precio de Gemini consultado en `ai.google.dev/gemini-api/docs/pricing`); nada se inventa.

La plantilla por defecto vive en `production_recipe_defaults` (una fila por formato,
versionada) y se edita en **Configuración → Receta de producción por defecto**, o vía
`GET/POST /api/v1/defaults/production-recipes/{format}`. Editarla no cambia evaluaciones
ya calculadas ni recetas ya asignadas a una oportunidad; solo afecta a las siguientes
oportunidades sin receta propia. `videos_per_month` de la instancia autoaplicada usa `4`
(cadencia semanal declarada, no una métrica de negocio).

La plantilla también declara las 4 herramientas compartidas (`gpt-6-luna`,
`gemini-3.1-flash-image`, el modelo de voz local y ffmpeg local) con capacidad mensual
real: la del LLM y la de Gemini se derivan de un tope de gasto declarado por el
propietario (US$5/semana cada una, igual lógica que el tope del LLM) dividido por su
precio real por unidad; la de voz y edición local se declara sin cuello de botella a la
cadencia actual (30 videos/mes, un techo de holgura, no una métrica de negocio). Con eso,
`evaluate_plan` resuelve `score: "88.75"` y `resources.status: "viable"` desde la primera
evaluación, sin inventar ningún dato: todo número citado tiene una fuente real o es un
supuesto propio explícito. Ajustar cualquiera de estos topes en Configuración recalcula
la capacidad y el score de las siguientes oportunidades.

## Uso en el radar

En **Backlog → Producción** se puede guardar un borrador incompleto o una receta con
estimaciones manuales. El editor JSON inicial no contiene precios de herramientas ni
costes inventados. Cada etapa requiere `source`, rangos `low/high` y, si usa herramienta,
`tool_key`, `tool_units_per_video` y `tool_capacity_unit` iguales a la unidad de ésta.
Las cuatro anclas usan `grade` (0/25/50/75/100) y `evidence` no vacía.

La API privada expone GET/POST `/api/v1/opportunities/{id}/production`. POST recibe
`plan` y `expected_version`. Audiencia, idioma y formato deben ser compatibles con la
oportunidad; la audiencia puede quedar sin definir en un borrador incompleto.

Las recetas son inmutables por clave y versión, incluyendo herramientas y volumen.
Para modificar una guardada hay que usar una nueva `recipe.version`; una edición con
versión de asignación desactualizada se rechaza. Guardar no solicita otra exploración,
no cambia la decisión del usuario, no reserva dinero y no inicia producción.

La consulta muestra una simulación con el perfil actual. Cuando el worker realiza la
próxima evaluación, incorpora una instantánea de receta, anclas, perfil, costes y Fit a
esa nueva evaluación. Las anteriores no se reescriben. El score combinado y el componente
publicitario siguen pendientes en la tarea 6.6.

Una receta aislada evalúa un canal hipotético; no reserva capacidad frente a otros
canales. Para comprobar varios simultáneos hay que incluirlos en **Escenarios**, con
herramientas compartidas declaradas una sola vez. Las notas son supuestos propios: no
copiar a ellas evidencia externa que deba eliminarse según la política de su proveedor.

La migración `0005` añade asignaciones versionadas. Aplicar `uv run alembic upgrade head`
en la base del radar antes de usar esta versión. Las recetas antiguas de escenarios que
omitan unidades pueden requerir completar `tool_capacity_unit` para volver a ser evaluables.
Pruebas: `tests/test_production_plans.py`, `tests/test_default_recipes.py`, escenarios,
API y navegación del dashboard.
