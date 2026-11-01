# Etapa 01: Guion e investigación (herramientas)

Fecha de consulta de todas las fuentes `web`: **2026-11-01** (caducan a los 90 días: 2027-01-30). Alcance: investigar el tema con fuentes, esquema, guion largo (~4.700 palabras, 18 a 28 min), verificación de hechos, control de originalidad/plagio y estructura de retención, para canales en inglés (secundario: español), sin rostro.

Tipos de dato: `medido`, `web`, `tercero`, `supuesto` (brief común). Aviso de método: las páginas se leyeron con WebFetch, que devuelve un resumen hecho por un modelo pequeño, no el texto íntegro. Las cifras clave (precios, licencias) conviene reconfirmarlas en la página antes de gastar dinero. Varias páginas devolvieron 404 o no mostraban el dato; eso va en `unknowns`.

El Foundry del propietario (`~/Foundries/...`) existe. **No contiene ninguna ficha ni stack de esta etapa** (solo voz, miniaturas, imágenes y alineación). Esta etapa parte de cero en medición: todo lo local de LLM es `web`/`tercero`/`supuesto`, nada es `medido`.

---

## 1. Resumen y recomendación

### Tabla de decisión

| Nivel | Qué usar | Por qué | Dinero por video | Tiempo de máquina por video | Minutos humanos por video |
|---|---|---|---|---|---|
| **A: gratis y local** | **Gemma 4 31B-it (4-bit MLX, 18,4 GB, Apache-2.0)** o **Qwen3.8-27B / Qwen3-32B (Apache-2.0)** servidos con `mlx_lm.server` + una búsqueda sin costo (Wikipedia, Semantic Scholar, fuentes que pegue el propietario) + script propio de similitud n-gram | Licencia permisiva con salida libre de restricciones, cabe en 64 GB con holgura, contexto largo (256K), API local compatible con OpenAI, 0 USD | 0 USD de API | ~20 a 60 min con varias pasadas (esquema, 8 a 10 secciones, revisión, extracción de afirmaciones, verificación). `supuesto`: ancho de banda 546 GB/s del M4 Max sobre 18,4 GB da del orden de 20 a 30 tok/s de generación; ~6.500 tokens por borrador final | **20 a 30** (el modelo local alucina más y la verificación pesa más) |
| **B: gratis con límites o bajo costo** | **Claude Haiku 5.5 (0,10 / 0,50 USD por MTok) o Gemini 3.1 Flash-Lite / 3.5 Flash-Lite para volumen**, y **Claude Sonnet 5.5 (2 / 10 USD por MTok) solo para la pasada de redacción final**; **Tavily (1.000 créditos/mes gratis)** para recuperar fuentes | Calidad de redacción y citas mucho mayor que un 31B local; coste de centavos por video | ~0,02 a 0,35 USD (`supuesto`, ver §2) | 5 a 15 min (esperas de API) | **12 a 20** |
| **C: pago** | **Claude Fable 5 / Opus 5.5 para la redacción + Perplexity Search API (5 USD/1.000 búsquedas) o Tavily de pago + Copyscape/Originality.ai** | Máxima calidad de prosa y menos correcciones; plagio verificable contra la web | ~1 a 3 USD de modelo (`supuesto`) + 0,5 a 2 USD de verificación | <10 min | **10 a 15** |

**Recomendación principal: Nivel B en la práctica, con Nivel A como respaldo.** Motivo: la redacción larga con hechos citados es la etapa donde un modelo local pequeño falla más (alucinación de datos, repetición, prosa genérica) y donde un error cuesta más (afirmación falsa publicada, contenido que YouTube lee como genérico). Un video de ~4.700 palabras cuesta céntimos con una API barata. Nivel A es viable y cumple "0 USD", pero hay que **medir** si su calidad evita que los minutos humanos suban por encima de 30 (experimento en §5).

### Qué automatiza la etapa y cuánto cuesta en minutos humanos

Automatizable (≥90 % del trabajo de escritura): recopilar fuentes, resumir, esquema, borrador, estructura de retención, tabla de afirmaciones con cita, verificación cruzada, similitud con fuentes. **No automatizable sin riesgo** (y por eso se cuentan minutos): elegir la tesis y el ángulo propio, validar una muestra de afirmaciones contra la fuente original, y una lectura final que aporte voz y juicio. Presupuesto recomendado a contar en las compuertas de NicheRadar: **15 minutos humanos por video (`supuesto`)** repartidos así: 3 min tesis/ángulo, 7 min revisar la tabla de afirmaciones de mayor riesgo, 5 min lectura y retoque. Esto deja 45 min del tope de 60 para las demás etapas. Si la etapa de guion cuesta más de 25 min, consume el margen de las otras.

### Cuánto del guion se puede automatizar sin caer en "contenido inauténtico"

Lectura de la política oficial (fuente: Centro de ayuda de YouTube, https://support.google.com/youtube/answer/1311392, leída 2026-11-01, `web`):

- El contenido debe "no ser producido en masa, genérico, repetitivo o manipulador". Ejemplos no elegibles: presentaciones de imágenes, historias con plantilla y "contenido generado con IA con plantillas genéricas o sin originalidad que da la impresión de producción en masa".
- Está permitido usar herramientas automáticas o plantillas, pero "el producto final debe seguir mostrando tu visión creativa" y valor educativo o de entretenimiento. Es explícito que se permite "contenido que usa herramientas creativas para ayudar a entregar una narrativa única, bien investigada o creativa", p. ej. usar IA para editar guiones.
- Permitido: una intro/outro constante con contenido central distinto, o una serie donde cada video tiene historia, enfoque o concepto propio.
- Canales con IA que se presenta como experto humano en salud, legal, finanzas o política no son monetizables.

Conclusión (inferencia mía, `supuesto`): **la política juzga el producto y el patrón del canal, no la herramienta.** Usar un LLM para investigar, estructurar y redactar no está prohibido. El riesgo es que 30 videos salgan con la misma estructura, el mismo tono y frases de relleno. Por eso:

1. Automatizar el 90 % del trabajo mecánico, pero **variar la estructura entre videos** (gancho, orden de actos, tipo de cierre) en lugar de usar una única plantilla fija. Una plantilla de retención puede ser un conjunto de 4 a 6 arquitecturas que el sistema rota, no una sola.
2. Exigir en cada video **una tesis propia y al menos N hechos específicos con fuente** que un resumen genérico no tendría (fechas, cifras, citas verificables).
3. No presentar al narrador como experto en salud, finanzas o derecho. Evitar los nichos de consejo sensible.
4. Divulgación de contenido sintético: no hace falta para guion asistido por IA. Fuente (https://support.google.com/youtube/answer/14328491, 2026-11-01, `web`): se exige divulgar contenido realista alterado o sintético (persona real diciendo algo que no dijo, evento real alterado, escena realista que no ocurrió, música como foco). Exento: "asistencia de producción", incluida la generación o mejora de esquemas y guiones, miniaturas, títulos, y clonar la propia voz. Aplica a esta etapa solo si el guion presenta un hecho inventado como real en imagen (etapa de imágenes), no por el texto.

---

## 2. Catálogo de candidatos

Convención de costo por video: **supuesto de tokens** para un video típico = 40.000 tokens de entrada acumulados (fuentes + prompts de varias pasadas) y 25.000 de salida (esquema, borrador ~6.500 tokens, revisiones, tabla de afirmaciones). Es un supuesto mío, no una medición. Costo = entrada x precio + salida x precio.

### 2.1 Modelos y motores (redacción)

| # | Herramienta | Tipo | Costo en dinero | Tiempo de máquina | Min humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Dato | Fuente (acceso 2026-11-01) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **mlx-lm** (motor) | local | 0 USD | depende del modelo | 0 | MIT (código) | Nativo en MLX; macOS 15+; `mlx_lm.server`, cache de prompt, `--max-kv-size` | Motor, no modelo | los del modelo | web | https://github.com/ml-explore/mlx-lm |
| 2 | **llama.cpp** (motor) | local | 0 USD | similar a MLX, algo menos en generación larga según guías | 0 | MIT | Metal, Accelerate, NEON; `llama-server` compatible con OpenAI | Motor | los del modelo | web (licencia, Metal); tercero (velocidad) | https://github.com/ggml-org/llama.cpp ; https://bestllmfor.com/guides/mlx-local-llm-apple-silicon/ |
| 3 | **Ollama** (motor/gestor) | local (con nube opcional) | 0 USD local; precios de nube no vistos | depende | 0 | MIT (según la página del repo; texto de licencia no incluido) | Instalador macOS; el repo tiene carpetas `mlx` y `mlxrunner`, sin explicación en la página | Cómodo (REST en `localhost:11434`); sin control tan fino de memoria como mlx-lm | los del modelo | web | https://github.com/ollama/ollama ; https://ollama.com/ |
| 4 | **Gemma 4 31B-it** (modelo) | local | 0 USD | ~20 a 60 min por video con pasadas (`supuesto`) | 20 a 30 | **Apache-2.0** (tarjeta del modelo). Gemma 3 y anteriores usan los Gemma Terms of Use, con política de uso prohibido y obligaciones al redistribuir; Google no reclama derechos sobre las salidas | Cuantización MLX 4-bit de 18,4 GB; ejecución con `mlx_lm.server` indicada en la tarjeta | Contexto 256K. Sin evidencia propia de calidad en prosa larga. No hay benchmark de escritura larga verificado (ver unknowns) | 35+ de serie, 140+ preentrenado | web (licencia, tamaño, contexto); supuesto (velocidad) | https://huggingface.co/google/gemma-4-31b-it ; https://huggingface.co/mlx-community/gemma-4-31b-it-4bit ; https://ai.google.dev/gemma/terms |
| 5 | **Qwen3.8-27B** (modelo) | local | 0 USD | similar | 20 a 30 | **Apache-2.0** (etiqueta de la tarjeta) | No verifiqué una cuantización MLX concreta de este modelo | Contexto 262.144 (hasta 1 M); Groq lo ofrece, lo que confirma que existe como servicio. Calidad en escritura larga sin verificar | la página no lo dice | web | https://huggingface.co/Qwen/Qwen3.8-27B |
| 6 | **Qwen3-32B** (modelo, generación previa) | local | 0 USD | similar | 20 a 30 | **Apache-2.0** | MLX 4-bit citado por guías de terceros como opción habitual | 32,8 B, 32K nativo y 131K con YaRN. Muestreo recomendado: temp 0,6/0,7, top-p 0,95/0,8, top-k 20; presence penalty 0 a 2 contra repetición (más alto mezcla idiomas) | 100+ idiomas | web (tarjeta); tercero (MLX) | https://huggingface.co/Qwen/Qwen3-32B |
| 7 | **gpt-oss-120b** (modelo) | local posible; no verificado en 64 GB | 0 USD | n/d | n/d | **Apache-2.0** | 117 B totales, 5,1 B activos, MXFP4, "cabe en una GPU de 80 GB". **No verifiqué que quepa en 64 GB de memoria unificada con contexto largo**; probablemente no sin recortes (`supuesto`) | n/d | n/d | web | https://huggingface.co/openai/gpt-oss-120b |
| 8 | **gpt-oss-120b / gpt-oss-20b / qwen3.8-27b vía Groq** | API | nivel gratis con límites; límites de la tabla "Developer": 30 RPM, 1.000 RPD, 8.000 TPM, 200.000 TPD | minutos | 12 a 20 | Términos de Groq no verificados | n/a | Con 8.000 TPM un borrador de 6.500 tokens de salida ya choca con el tope por minuto; hay que trocear en secciones. 200K tokens/día alcanza para ~4 videos de 25K tokens de salida (`supuesto`, la tabla no aclara si cuenta entrada) | n/d | web (parcial: la página no aclara qué plan muestra la tabla) | https://console.groq.com/docs/rate-limits |
| 9 | **OpenRouter modelos `:free`** | API | 0 USD; <10 USD de créditos comprados: 20 RPM y **50 solicitudes/día**; con ≥10 USD: 1.000/día | minutos | 12 a 20 | Depende de cada modelo y proveedor | n/a | Límite de 50/día solo alcanza para un video con pocas llamadas; no se verificó qué modelos `:free` existen hoy | n/d | web | https://openrouter.ai/docs/api-reference/limits |
| 10 | **Gemini API (Google)**: 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Pro, 3.6/3.8 Flash | API | **Nivel gratis = Sí** en esos modelos; de pago: 3.1 Flash-Lite 0,25/1,50 USD/MTok; 3.5 Flash-Lite 0,30/2,50; 3.8 Flash 0,75/3,75; 2.5 Pro 1,25/10. **3.1 Pro Preview y Gemini 4 Argon: sin nivel gratis** (precios de 3.8 Flash y Argon válidos solo hasta 2026-12-31 / 2026-11-30) | minutos | 12 a 20 | Términos: en servicios sin pago Google usa prompts y respuestas para mejorar productos y **revisores humanos pueden leerlos**; en servicios de pago no. Salidas: términos de uso de la API no leídos a fondo | n/a | Límites por modelo del nivel gratis **no publicados en la documentación** (se ven en AI Studio); guías de terceros discrepan | n/d | web (precios, política de datos); tercero (límites) | https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/gemini-api/terms |
| 11 | **Claude API** (Anthropic) | API | Sin nivel gratis visto. Haiku 5.5: 0,10/0,50 USD/MTok (≤100K tokens de prompt); Sonnet 5.5: 2/10; Opus 5.5: 4/20; Fable 5: 10/50. Batch: −50 %. Caché: lecturas a una fracción | minutos | 12 a 20 | Términos comerciales de Anthropic no leídos en esta investigación | n/a | Calidad de redacción en español e inglés típicamente alta; costo calculado abajo | multilingüe | web (precios) | https://platform.claude.com/docs/en/about-claude/pricing |
| 12 | **Mistral La Plateforme (plan Experiment)** | API | 0 USD, sin tarjeta, requiere verificación telefónica | minutos | 12 a 20 | Mistral **puede usar las solicitudes del plan gratis para mejorar sus modelos** (advertencia en su documentación, según el resultado de búsqueda) | n/a | Límites contradictorios entre fuentes (~500K TPM y ~1.000 M tokens/mes en varias; RPM entre 1 y 2); la consola es la fuente de verdad. La página de límites oficial devolvió 404 | francés/inglés/español, entre otros (no verificado aquí) | tercero (límites); web parcial (política) | https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key ; https://mintlify.com/cheahjs/free-llm-api-resources/providers/free/mistral-plateforme |

**Costo estimado por video con el supuesto de tokens (40K entrada, 25K salida)**, `supuesto` aplicado a precios `web`:

| Modelo | Entrada | Salida | Total |
|---|---|---|---|
| Claude Haiku 5.5 | 0,004 USD | 0,0125 USD | **~0,02 USD** |
| Gemini 3.1 Flash-Lite | 0,010 | 0,0375 | **~0,05 USD** |
| Claude Sonnet 5.5 | 0,08 | 0,25 | **~0,33 USD** |
| Claude Opus 5.5 | 0,16 | 0,50 | **~0,66 USD** |
| Claude Fable 5 | 0,40 | 1,25 | **~1,65 USD** |

Conclusión de costos: **el dinero de LLM en esta etapa es despreciable frente al presupuesto de minutos humanos.** Un modelo caro que ahorre 5 minutos de edición humana rinde más que un modelo gratis que los gasta. Esto es lo opuesto a lo que supusieron los dossiers previos de pago; aquí lo relevante es medir minutos, no dólares.

### 2.2 Investigación, citas y búsqueda

| # | Herramienta | Tipo | Costo | Min humanos | Licencia/uso | Calidad/defectos | Dato | Fuente |
|---|---|---|---|---|---|---|---|---|
| 13 | **Tavily Search/Extract/Research** | API | Gratis: 1.000 créditos/mes sin tarjeta. Búsqueda básica 1 crédito, avanzada 2; extracción 1 crédito por 5 URLs; investigación 4 a 110 créditos (mini) o 15 a 250 (pro). Pago por uso: 0,008 USD/crédito | 1 a 3 (elegir fuentes) | Términos de uso no leídos | Un video con ~25 búsquedas básicas + 10 extracciones cuesta ~30 créditos (`supuesto`): ~30 videos/mes gratis | web | https://docs.tavily.com/documentation/api-credits |
| 14 | **Perplexity Search API** | API | 5 USD por 1.000 solicitudes exitosas; 1 USD por 1.000 con Fast Search. Precios de Sonar no vistos | 1 a 3 | n/v | Devuelve resultados con fuente; el precio es pago desde el primer uso (no vi nivel gratis) | web | https://docs.perplexity.ai/getting-started/pricing |
| 15 | **Brave Search API** | API | Página de precios sin datos legibles (solo encabezados) | n/d | n/v | No se pudo verificar nivel gratis ni términos de almacenamiento | **no verificado** | https://api-dashboard.search.brave.com/documentation/pricing |
| 16 | **Semantic Scholar API** | API | Gratis; sin clave: 1.000 solicitudes/segundo compartidas entre todos los anónimos; con clave: 1 req/s inicial | 0 a 2 | Acuerdo de licencia de API aparte (no leído); datasets abiertos S2AG, S2ORC, SUPP.AI | Útil solo si el nicho es científico o histórico con literatura | web | https://www.semanticscholar.org/product/api |
| 17 | **Búsqueda manual y fuentes primarias que el propietario pega** | humano | 0 USD | 3 a 8 | Cada fuente tiene su propia licencia | Es el insumo que más diferencia un guion de uno genérico | supuesto | n/a |

### 2.3 Verificación de hechos

| # | Herramienta | Tipo | Costo | Min humanos | Notas | Dato | Fuente |
|---|---|---|---|---|---|---|---|
| 18 | **Google Fact Check Tools API** (`claims:search`) | API | No leí cuota ni costo (la página no los traía) | 0 a 1 | Solo encuentra afirmaciones **ya verificadas por terceros**; no verifica un dato nuevo. Sirve para afirmaciones virales o políticas, no para cifras de nicho | web (función) | https://developers.google.com/fact-check/tools/api/reference/rest |
| 19 | **Verificación propia por pasos** (script con LLM local o de API) | local/API | 0 a 0,10 USD | 5 a 10 | Ver §3 ficha: extraer cada afirmación verificable, buscarla en las fuentes recuperadas, exigir **cita textual**, marcar "sin respaldo" lo que el verificador no encuentre | supuesto (diseño) | n/a |

### 2.4 Plagio y originalidad

| # | Herramienta | Tipo | Costo | Notas | Dato | Fuente |
|---|---|---|---|---|---|---|
| 20 | **Script de similitud n-gram contra las fuentes recuperadas** | local | 0 USD; segundos de CPU | Detecta copia literal o paráfrasis pegada respecto de **las fuentes que usamos**, no contra toda la web. Umbral sugerido: ningún tramo de 8 palabras consecutivas copiado sin comillas (`supuesto`) | supuesto | n/a |
| 21 | **Copyscape** (API/Premium) | servicio | Capterra lista un paquete Premium de 3 USD; no pude leer la página oficial de precios (404). Quejas de usuarios sobre caducidad de créditos y subidas | tercero | https://www.capterra.com/p/179608/Copyscape/ (vía búsqueda) |
| 22 | **Originality.ai** | servicio | Créditos: 100 palabras por crédito (IA) o 2 créditos por 100 palabras (IA + plagio); Pro 14,95 USD/mes ~200.000 palabras según CASRAI | tercero | https://www.casrai.org/guides/copyleaks-pricing (vía búsqueda) |
| 23 | **Copyleaks** | servicio | Capterra: 8,99 USD/mes (plagio) o 13,99 USD/mes (IA + plagio) por usuario; API como complemento aparte; datos discrepan | tercero | https://www.capterra.com/p/185429/Copyleaks/pricing/ (vía búsqueda) |

Un guion de 4.700 palabras cuesta ~94 créditos en Originality.ai con IA + plagio (2 créditos por 100 palabras). Con la cifra `tercero` de ~200.000 palabras/mes del plan Pro alcanzarían ~42 guiones/mes (`supuesto` de cálculo; no confirmado si esa cifra cuenta ambos chequeos). **Los detectores de "IA" no se recomiendan** como compuerta: no hay evidencia aquí de que YouTube los use, y sus falsos positivos no se midieron en esta investigación.

---

## 3. Fichas breves (recomendados y finalistas)

### 3.1 Pipeline recomendado (Nivel B con respaldo A)

Un solo orquestador en Python (o un skill de Claude Code) con **cinco pasadas**, cada una con salida estructurada en JSON/Markdown para que pueda auditarse:

1. **Recuperación**: 15 a 25 consultas a Tavily (o fuentes pegadas) → texto extraído de 10 a 20 fuentes, guardado con URL y fecha. Sin fuentes guardadas no hay guion.
2. **Tesis y esquema** (humano 3 min): el modelo propone 3 ángulos con las pruebas que cada uno tendría; el propietario elige o reescribe uno. Luego esquema por actos con **arquitectura de retención** (ver §3.4).
3. **Redacción por secciones** (8 a 10 secciones de ~500 palabras) con las fuentes relevantes en contexto. Cada afirmación factual sale con marcador `[S3]` hacia una fuente. Por secciones, no de una vez: reduce repetición y alucinación y respeta los límites de TPM de los niveles gratis.
4. **Verificación**: otro paso extrae cada afirmación con marcador y comprueba que la fuente citada la respalda (cita textual obligatoria). Lo que no tenga respaldo se reescribe o se elimina. Para modelos locales, usar **un modelo distinto** del que redactó.
5. **Control de originalidad**: n-gram contra las fuentes recuperadas; reportar tramos copiados; reescribir esos tramos.

Salida para humano: guion limpio (sin marcadores) + tabla de afirmaciones con estado `verificada / débil / sin respaldo` + lista de tramos similares. El humano solo lee lo marcado "débil/sin respaldo" y 5 min de lectura.

### 3.2 Local: mlx-lm + Gemma 4 31B (4-bit) o Qwen3.8-27B

- **Qué es**: motor MLX (MIT) con servidor local compatible con OpenAI; modelo Apache-2.0.
- **Integración**: `mlx_lm.server --model mlx-community/gemma-4-31b-it-4bit` (comando de la tarjeta del modelo) y el orquestador llama a `http://localhost:8080/v1` (puerto por confirmar al ejecutar). CLI: `mlx_lm.generate`, `mlx_lm.chat`; `mlx_lm.cache_prompt` guarda el prefijo de fuentes y evita reprocesarlo entre secciones, que es útil porque cada sección reutiliza el mismo bloque de investigación.
- **Límites**: macOS 15 o superior. Para un modelo grande, puede hacer falta subir el límite de memoria de GPU con `sudo sysctl iogpu.wired_limit_mb=N` (requiere sudo; el propietario debe hacerlo él). `--max-kv-size` limita la memoria a costa de calidad. El propio Foundry registró una corrida atípica de TTS que sobrepasó 64 GB: **no correr el LLM y el TTS a la vez.**
- **Riesgos**: no hay evidencia verificada de calidad de prosa larga ni de velocidad real en el M4 Max (solo guías de terceros). Alucinación de datos superior a la de un modelo de pago `supuesto`. Gemma 3 y anteriores tienen términos propios; Gemma 4 aparece como Apache-2.0 en su tarjeta, pero la página de términos de Google remite a "otra licencia" para Gemma 4: **verificar el texto de licencia antes de comercializar**.

### 3.3 API: Haiku 5.5 / Flash-Lite para volumen y Sonnet 5.5 para redactar

- **Integración**: SDK oficial (Python/TypeScript) o HTTP; Batch API con 50 % de descuento si no importa esperar; caché de prompt para el bloque de fuentes que se repite en cada sección (lecturas de caché: 0,10 USD/MTok en Sonnet 5.5 frente a 2 USD de entrada normal).
- **Riesgos**: cambios de modelo y de precio (algunos precios de Gemini vencen en 2026-11-30 y 2026-12-31). Nivel gratis de Gemini: Google puede usar el contenido y personas pueden leerlo; para guiones propios esto no importa, pero no pegar material de terceros bajo confidencialidad.

### 3.4 Estructura de retención (esquema, no herramienta)

No encontré en esta investigación una herramienta con evidencia medida de retención; el postmortem de retención real del propietario (skill `youtube-retention-postmortem`) es la fuente correcta una vez haya métricas. Mientras tanto, usar una plantilla de actos **parametrizada**, no fija (`supuesto`): gancho de 30 a 45 s con la promesa y un dato específico; 3 a 5 "bucles abiertos" resueltos a lo largo del video; un giro o revelación a ~60 % de la duración; cierre sin resumen repetitivo. Rotar 4 a 6 variantes de arquitectura entre videos para no producir un patrón idéntico (§1, política de contenido producido en masa).

### 3.5 Verificación y plagio propios

- **Verificación**: tabla `afirmación | fuente | cita textual | estado`. Regla dura: una afirmación sin cita textual de una fuente recuperada **no entra** al guion final. Verificador distinto del redactor. Los números, fechas, nombres y citas son lo que más se alucina; son los que el humano revisa por muestreo (`supuesto`: 10 afirmaciones de mayor riesgo, 7 min).
- **Plagio**: n-gram (p. ej. 8 palabras) contra las fuentes guardadas; reescribir tramos que coincidan. Para chequeo contra toda la web usar Copyscape u Originality.ai en lote solo si el canal ya publica con regularidad, no en el piloto.

---

## 4. Riesgos de política y de derechos

| Riesgo | Detalle | Mitigación | Fuente |
|---|---|---|---|
| Contenido inauténtico / producido en masa | Plantillas fijas y guiones que "se sienten intercambiables" no son monetizables; el criterio es el canal en conjunto | Variar arquitecturas, exigir tesis y datos propios, no clonar el mismo esquema | support.google.com/youtube/answer/1311392 |
| Divulgación de contenido sintético | Guion asistido por IA está exento; la voz clonada propia también; lo realista alterado no | Mantener la divulgación en la etapa de imágenes/video, no en esta | support.google.com/youtube/answer/14328491 |
| Nichos de consejo sensible | IA como "experto humano" en salud, legal, finanzas o política no es monetizable | Evitar esos nichos o no personificar | misma fuente que el primero |
| Alucinación de hechos | Un dato falso publicado daña credibilidad y puede ser difamatorio si es sobre personas reales | Citas textuales obligatorias, verificador independiente, humano en lo más riesgoso | diseño propio |
| Copia de fuentes | Paráfrasis pegada de un artículo es plagio y puede ser infracción de derechos | n-gram, ninguna frase larga literal sin comillas | diseño propio |
| Derechos de la salida del modelo | Apache-2.0 (Gemma 4, Qwen, gpt-oss): permite uso comercial del software y sus salidas. Gemma 3 y anteriores: Google "no reclama derechos" sobre las salidas, sujeto a política de uso prohibido. APIs de pago: términos propios, **no leídos** aquí | Reconfirmar términos de la API elegida antes de monetizar | huggingface.co (tarjetas); ai.google.dev/gemma/terms |
| Privacidad de datos en niveles gratis | Gemini sin pago y Mistral Experiment usan el contenido para mejorar modelos; Gemini permite revisión humana | No enviar material confidencial ni datos del propietario por esos niveles | ai.google.dev/gemini-api/terms |
| Caducidad de datos | Los precios de 3 modelos de Gemini vencen o suben el 30/11/2026 y 31/12/2026 | Reverificar a los 90 días | pricing |

---

## 5. Comparación con lo medido por el propietario y qué falta medir

**Lo ya medido** (Foundry): nada de esta etapa. El stack `voice-narration` mide voz y reutiliza ~4.670 palabras por video; esto confirma el tamaño objetivo del guion pero no su producción. Dato útil heredado: el agente que escribe debe **fijar el idioma de salida** (un desajuste de idioma generó WER 0,714 en voz); incluir `language` explícito en cada prompt de redacción. Dato `medido` del stack de voz: la síntesis se hace en trozos de máximo 450 palabras con corte en límite de oración; conviene que el guion llegue con párrafos que respeten ese corte.

**Experimentos baratos que puede correr el propietario** (en orden de valor):

1. **Calidad y minutos humanos, 3 modelos, 1 mismo tema** (30 min cada uno): Gemma 4 31B (4-bit MLX), Qwen3.8-27B y Claude Haiku 5.5 o Sonnet 5.5. Para cada uno medir: palabras entregadas (¿cumple 4.700?), número de afirmaciones sin respaldo según la tabla del verificador, minutos humanos hasta dejar el guion publicable, tiempo de máquina y dólares. Resultado: decide Nivel A vs B con datos propios.
2. **Velocidad real en el M4 Max**: tokens/s de `mlx_lm.generate` con el modelo de 31B (4-bit) en un prompt de 30K tokens. Anotar memoria máxima. Valida mi supuesto de 20 a 30 tok/s.
3. **Tasa de alucinación**: tomar 30 afirmaciones de un guion generado, buscar a mano la fuente de cada una; comparar contra lo que dijo el verificador automático. Mide la confiabilidad del verificador (falsos "verificada").
4. **Similitud**: pegar 3 guiones en Copyscape (gratis o 3 USD) o Originality.ai y comparar con el script n-gram propio. Mide si el n-gram local alcanza.
5. **Variedad entre videos**: generar 5 guiones del mismo nicho con la rotación de arquitectura y medir si abrir/cerrar/transiciones son distinguibles (lectura del propietario, 10 min). Es la defensa práctica contra "contenido en masa".

---

## 6. Unknowns

- **Calidad real de escritura larga** de Gemma 4, Qwen3.8 y gpt-oss: el benchmark EQ-Bench Longform (https://eqbench.com/creative_writing_longform.html, última actualización v1.11, 2026-02-19) mide ficción, no ensayos con hechos, y su tabla no cargó (no vi puntuaciones). Sin evidencia propia.
- **Velocidad (tok/s) y memoria** en M4 Max 64 GB de los modelos de 27 a 32 B: solo estimación mía y guías de terceros sin verificar.
- **gpt-oss-120b en 64 GB**: no verificado que quepa; probablemente no.
- **Límites del nivel gratis de Gemini** por modelo: no publicados en la documentación (se ven en AI Studio); guías de terceros discrepan y pueden estar caducadas.
- **Límites del plan Experiment de Mistral** (RPM, TPM): fuentes contradictorias; página oficial devolvió 404.
- **Precios oficiales de Copyscape, Originality.ai y Copyleaks**: solo agregadores (`tercero`); la página de Copyscape devolvió 404.
- **Brave Search API**: sin datos legibles.
- **Términos comerciales de Anthropic, Groq, Tavily, Perplexity y OpenRouter** sobre propiedad y uso de la salida: no leídos.
- **Si la licencia de Gemma 4 es solo Apache-2.0**: la tarjeta lo dice; la página de términos de Google remite a "otra licencia" para Gemma 4 sin que yo la haya leído.
- **Fiabilidad de los verificadores automáticos con modelo** (qué porcentaje de afirmaciones falsas dejan pasar): sin medir.
- **Cómo evalúa YouTube en la práctica** el contenido producido en masa: la política lo describe, pero no hay umbral público; el riesgo se reduce, no se elimina.
- Los nombres de modelo y precios provienen de las páginas oficiales tal como las devolvió la herramienta de lectura; no los contrasté con una segunda lectura.

### Tabla de fuentes (acceso 2026-11-01)

| Dato | URL |
|---|---|
| Política de contenido inauténtico | https://support.google.com/youtube/answer/1311392 |
| Divulgación de contenido alterado o sintético | https://support.google.com/youtube/answer/14328491 |
| Precios Gemini API y nivel gratis | https://ai.google.dev/gemini-api/docs/pricing |
| Términos Gemini API (uso de datos) | https://ai.google.dev/gemini-api/terms |
| Términos Gemma (generaciones previas) | https://ai.google.dev/gemma/terms |
| Gemma 4 31B-it | https://huggingface.co/google/gemma-4-31b-it |
| Gemma 4 31B 4-bit MLX | https://huggingface.co/mlx-community/gemma-4-31b-it-4bit |
| Gemma 3 27B 4-bit MLX (licencia "gemma") | https://huggingface.co/mlx-community/gemma-3-27b-it-4bit |
| Qwen3-32B | https://huggingface.co/Qwen/Qwen3-32B |
| Qwen3.8-27B | https://huggingface.co/Qwen/Qwen3.8-27B |
| gpt-oss-120b | https://huggingface.co/openai/gpt-oss-120b |
| mlx-lm | https://github.com/ml-explore/mlx-lm |
| llama.cpp | https://github.com/ggml-org/llama.cpp |
| Ollama (repo) | https://github.com/ollama/ollama |
| Ollama (sitio) | https://ollama.com/ |
| Precios Claude API | https://platform.claude.com/docs/en/about-claude/pricing |
| Límites Groq | https://console.groq.com/docs/rate-limits |
| Límites OpenRouter | https://openrouter.ai/docs/api-reference/limits |
| Mistral: activar y clave | https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key |
| Créditos Tavily | https://docs.tavily.com/documentation/api-credits |
| Precios Perplexity (Search API) | https://docs.perplexity.ai/getting-started/pricing |
| Semantic Scholar API | https://www.semanticscholar.org/product/api |
| Google Fact Check Tools API | https://developers.google.com/fact-check/tools/api/reference/rest |
| EQ-Bench Longform | https://eqbench.com/creative_writing_longform.html |
| Guía MLX vs llama.cpp (tercero) | https://bestllmfor.com/guides/mlx-local-llm-apple-silicon/ |
| Mistral gratis, límites (tercero) | https://mintlify.com/cheahjs/free-llm-api-resources/providers/free/mistral-plateforme |
| Copyscape (tercero) | https://www.capterra.com/p/179608/Copyscape/ |
| Copyleaks (tercero) | https://www.capterra.com/p/185429/Copyleaks/pricing/ |
| Originality.ai (tercero) | https://www.casrai.org/guides/copyleaks-pricing |
