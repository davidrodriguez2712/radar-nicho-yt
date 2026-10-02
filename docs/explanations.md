# Explicaciones estructuradas e IA opcional

Tarea 6.7, método `explanation-v2`. Cada evaluación nueva contiene una explicación
determinista en español con los componentes disponibles/ausentes, cobertura, Mercado,
Creator Fit, puntuación combinada, confianza, recursos y condiciones pendientes.
El dashboard la muestra en **Backlog → Análisis**, con referencias por afirmación.

## Alcance de la IA

El enriquecimiento opcional ordena el énfasis de afirmaciones ya calculadas, priorizando
carencias de investigación y límites. No es redacción libre, generación de números ni
investigación adicional. La respuesta debe ser una permutación completa de IDs conocidos;
se rechazan IDs ajenos, duplicados, omisiones y campos adicionales. El código mantiene
los textos, valores, referencias y puntuaciones originales. No se alteran decisiones.

Al modelo solo llegan IDs de afirmaciones y frases producidas por el servidor. No se
envían títulos, descripciones, URLs, notas libres, recetas, credenciales ni IDs de
observaciones. Las frases se transmiten como datos no confiables, separados de las
instrucciones. No hay herramientas, navegación, ejecución de código ni acciones
delegadas al modelo. No se considera el prompt una defensa suficiente: la validación
local de la lista de IDs es obligatoria incluso con salida estructurada.

Este alcance permite conservar una explicación útil sin IA. Su mejora de presentación
no está validada con un piloto y no justifica por sí sola comprar una suscripción.

## Adaptador y configuración

Se preparó un adaptador HTTP para Responses API de OpenAI, usando el cliente HTTP ya
presente en el proyecto. No se añadieron SDKs ni se hicieron llamadas reales. Se
consultaron [Responses API](https://developers.openai.com/api/reference/typescript/resources/responses/methods/create)
y [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
el 2026-09-14 para los campos de solicitud y respuesta.

Configuración por entorno, no por credenciales del chat:

- `NR_LLM_ENABLED=false` por defecto.
- `NR_LLM_API_KEY`: secreto de API independiente. No se muestra en estado, logs ni UI.
- `NR_LLM_CONFIGURATION`: JSON del contrato `LLMConfiguration` con estos campos:
  - `auth_scope`: identificador estable no secreto de la cuenta.
  - `tariff`: configuración descrita abajo.
  - `limits`: topes USD `operation`, `run`, `week`, `period`.
  - `timeout_seconds`: 20 por defecto; entre 1 y 30 segundos.

`tariff` exige:

| Campo | Significado |
| --- | --- |
| `version`, `source` | Versión y evidencia de precios/contexto revisados para la cuenta |
| `model` | Identificador fijado del modelo; la respuesta debe identificar exactamente el mismo |
| `verified_at`, `valid_until` | Fechas con zona; fuera de vigencia no se envía |
| `context_window_tokens` | Capacidad máxima documentada del modelo, no tamaño deseado del prompt |
| `output_tokens` | Tope de salida, 512 por defecto, entre 128 y 2048 |
| `input_usd_per_million` | Tarifa de entrada aplicable a todo el contexto permitido |
| `cached_input_usd_per_million` | Tarifa de entrada cacheada, no mayor que la normal |
| `output_usd_per_million` | Tarifa de salida, incluido razonamiento facturable |

No hay modelo ni precios reales precargados. Deben verificarse compatibilidad con
salida estructurada, contexto, nivel `default` y tarifas para la cuenta. Para modelos
con tramos de precio, la tarifa debe cubrir todo el contexto configurado; si no hay
una tarifa única aplicable, este adaptador no debe habilitarse con un precio parcial.
Una suscripción existente de chat no confirma créditos ni acceso API.

El proveedor y cada fuente deben tener políticas habilitadas antes de enviar:

- Proveedor `openai`, operación `explanation`, tipo `explanation`: usos `query`,
  `storage`, `derived`, `llm_processing`; `storage` requiere plazo de conservación.
- Para ejecución programada: también `scheduled`.
- Cada fuente de evidencia: uso explícito `llm_processing` para su operación/tipo.
  Este permiso no se deduce del permiso de almacenamiento o cálculo de métricas.
- Perfil: `paid_limits_confirmed=true`, con sublímites USD y techo compartido suficientes.

No se instalaron políticas que autoricen usos reales. `store=false`, modo síncrono y
ausencia de herramientas reducen persistencia y superficie de acción, pero **no son una
garantía de retención cero en el proveedor**. Deben revisarse los controles de la cuenta
y condiciones compatibles con las fuentes:
[controles de datos de OpenAI](https://developers.openai.com/api/docs/guides/your-data).

El modo sintético nunca envía solicitudes reales, aun con la opción activada. El
pipeline de descubrimiento real sigue pendiente de habilitación general; no se elude
ese bloqueo para usar este adaptador. La ruta de transporte se verifica con fixtures
y `httpx.MockTransport`, no con credenciales ni consumo reales.

## Presupuesto y confirmación del consumo

Antes del envío se reserva de forma transaccional:

`(context_window_tokens * input_rate + output_tokens * output_rate) / 1_000_000`

Se usa el contexto completo documentado como cota conservadora, no una estimación
informal del tokenizador. Puede reservar bastante más que el coste probable de este
prompt pequeño; si no cabe, se omite la IA y se conserva la explicación determinista.
No se aumentan topes ni se recorta artificialmente el contexto declarado para que quepa.

La reserva reutiliza los controles comunes por operación, ejecución, semana y mes,
incluyendo obligaciones pendientes, costes registrados y reserva mensual del usuario.
Los límites del LLM no constituyen otro presupuesto separado de los US$100–150.

Tras una respuesta se calcula consumo mediante tokens reportados de entrada normal,
entrada cacheada y salida, con la tarifa configurada. Se redondea hacia arriba a seis
decimales, acorde a la precisión de SQL. Es conciliación de uso por tarifa, **no una
factura ni verificación del cargo bancario**, y así queda etiquetado en los metadatos.
Un modelo/nivel diferente, uso ausente/inconsistente o consumo fuera de los límites
verificados deja el cobro incierto en vez de atribuir coste cero.

## Recuperación y alternativa determinista

Las métricas y la explicación base se confirman antes del enriquecimiento. La reserva
y el estado `sent` se confirman antes de ceder control a HTTP. No se mantiene una
transacción SQL abierta durante la llamada. Hay un timeout global y por transporte;
se limita la solicitud a 32 KB y la respuesta a 128 KB. No se siguen redirecciones,
no se usan proxies heredados del entorno ni hay reintentos automáticos del adaptador.

Cada evaluación admite un único intento lógico. Resultados finales se reutilizan al
reanudar; no se paga otra vez por recargar el dashboard. Si se reinicia tras `sent`,
se conserva la reserva incierta y se utiliza la explicación base. Una cuenta con
solicitudes `sent`/`unknown_charge` pendientes no inicia otro enriquecimiento hasta
revisión; 401, 429 o timeout no crean un bucle. Un fallo del modelo no elimina métricas.
Si la respuesta trae tokens verificables pero orden inválido, se registra el consumo
sin usar su contenido. La alternativa queda visible con un código, nunca con el texto
de una excepción o respuesta que pudiera contener secretos.

La señal de vida del worker se renueva antes de cada enriquecimiento. Las selecciones
manuales o cambios de configuración no disparan llamadas retroactivas sobre resultados
finalizados: solo las nuevas evaluaciones consideran la configuración vigente.

## Procedencia y conservación

Cada afirmación referencia una ruta `snapshot:<evaluation_id>:<campo>`; los componentes
observados también enlazan observaciones originales. Las condiciones y supuestos
económicos se trazan hasta la configuración de la propia evaluación.

Solo se guarda el orden de IDs validado como respuesta del proveedor; no el texto
bruto ni el prompt. La observación se enlaza a su política y a la evaluación. El plazo
de esta se reduce al menor entre fuentes, configuración y almacenamiento del LLM.
La limpieza existente elimina explicación, orden y puntuaciones cuando corresponde;
las decisiones propias se preservan. Una caducidad o revocación durante la llamada
no permite resucitar evidencia ni conservar el orden generado.

No se añadió una migración: se usan observaciones, enlaces, versiones de evaluación,
reservas y contabilidad existentes. No hubo cambios en el VPS.

Pruebas: `tests/test_explanations.py`, más flujo sintético, dashboard, presupuestos y
conservación existentes. Incluyen fuentes por afirmación, contenido externo hostil,
números inmutables, validación estricta, límites, permisos, incertidumbre, reinicio,
concurrencia y caducidad. Las tarifas y modelos de fixtures son inventados y no se
configuran en producción.
