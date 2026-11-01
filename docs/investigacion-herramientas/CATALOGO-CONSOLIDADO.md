# Catálogo consolidado de herramientas por etapa (2026-11-01)

Siete etapas de producción para canales de narración larga sin rostro (inglés; español secundario), investigadas por siete
agentes con búsqueda web. Cada etapa se incluye **completa** más abajo. Prioridad del orden: gratis y local primero
(Mac M4 Max de 64 GB, sin NVIDIA), luego gratis con límites, luego bajo costo, luego pago.

Tipos de dato en cada informe: **medido** (corrida real del propietario), **web** (fuente oficial leída; caduca a 90 días,
es decir el 2027-01-30), **tercero** (blog o agregador) y **supuesto**. **Casi todo lo de abajo es web, tercero o
supuesto; lo único medido es lo que ya estaba en el Foundry y una prueba sintética de ffmpeg.** Este resumen lo armé
con los resúmenes de los agentes, no leí los siete informes completos ni verifiqué sus fuentes.

## Recomendación por etapa y nivel

| Etapa | A: gratis y local | B: gratis con límites o bajo costo | C: pago |
|---|---|---|---|
| 01 Guion | Gemma 4 31B (4-bit MLX) o Qwen3.8-27B con `mlx-lm` + script de similitud y verificador de citas | Claude Haiku 5.5 o Gemini 3.1 Flash-Lite para volumen, Sonnet 5.5 para la redacción final, Tavily (1.000 créditos/mes gratis) | Opus 5.5 o Fable 5, Perplexity Search API, Copyscape/Originality.ai |
| 02 Voz | Qwen3-TTS-1.7B (ya medido; probar variante MLX) + WhisperX; Kokoro de complemento | Fish Audio (US$0,41/video, medido); OpenAI tts-1 como respaldo sin clonación | ElevenLabs (US$22/mes) o Cartesia Pro (US$5/mes) |
| 03 Visuales | `mflux` con FLUX.2 klein 4B (Apache-2.0) + footage libre (Pexels, Pixabay, NASA, NOAA, Wikimedia, Smithsonian, LoC, Internet Archive) + mapas con Natural Earth | Gemini Image por API (~US$0,034–0,067/imagen); Cloudflare FLUX.1 schnell para borradores | Clips Veo 3.1 solo en 5–10 % del metraje |
| 04 Edición | ffmpeg 9.0.1 desde Python (ya instalado) | Remotion solo para gráficos animados; Shotstack (nube) sin ventaja sobre el Mac | DaVinci Resolve Studio (US$236 una vez) |
| 05 Miniaturas | Pillow con plantillas + FLUX.2 klein 4B (`mflux`) para fondos + A/B nativo de YouTube | Nivel A + Gemini Nano Banana 2.1 (US$0,0336/imagen) + vidIQ Free | thumbnailtest.com (US$29/mes) o TubeBuddy, solo para decidir por CTR |
| 06 Música/SFX/subtítulos | YouTube Audio Library + Pixabay con ducking en ffmpeg; Freesound CC0; `mlx-whisper` y WhisperX; Argos Translate | Uppbeat (condiciones sin verificar) o Suno Pro; `whisper.cpp` con Core ML | Epidemic Sound o Artlist (no recomendados) |
| 07 Publicación | Script propio sobre YouTube Data API (privado + `publishAt`, `containsSyntheticMedia`), Studio para Test & Compare, Analytics y Reporting API | A + vidIQ gratis o Metricool gratis | vidIQ Boost (US$19/mes) o TubeBuddy, solo si prueban subir el CTR |

## Minutos humanos por video: la cuenta que importa para la compuerta

Compuerta de NicheRadar: máximo **60 minutos humanos por video** y mínimo 90 % de automatización. Cifras de los propios
informes (todas supuestos, nadie las cronometró):

| Etapa | A (min humanos) | B (min humanos) |
|---|---|---|
| 01 Guion | 20–30 | 12–20 |
| 02 Voz | 5–10 | 5–10 |
| 03 Visuales | 25–35 | 20–30 |
| 04 Edición | 2–3 | 2–3 |
| 05 Miniaturas | 5–12 | 5–12 |
| 06 Música/subtítulos | 0–3 | 0–3 |
| 07 Publicación | 5–10 | 5–10 |
| **Total** | **62–103** | **49–88** |

**Lectura:** con todo en el nivel A, ni el mejor caso cumple los 60 minutos; con el B solo se cumple en el mejor caso.
La etapa que más pesa es **Visuales** (revisión de derechos y marcas por imagen), seguida del **Guion**. Si la
compuerta se mantiene, habrá que automatizar la revisión visual (por muestreo) o negociar la compuerta; el cálculo por
etapa dice dónde está el esfuerzo. Son supuestos: el primer paso es cronometrar un video real.

**Dinero por video (nivel B, según los informes):** guion ~US$0,02–0,33, voz ~US$0,41, visuales ~US$7–14 (150–200
imágenes por API), miniatura centavos: del orden de **US$8–15 por video**, dominado por las imágenes. En el nivel A es
US$0 de dinero y se paga en tiempo de máquina (visuales 1,5–2,5 h; voz 47–90 min; guion 20–60 min; edición 3–15 min).

## Hallazgos que cambian decisiones

1. **Umbral de monetización:** la ayuda oficial de YouTube (consultada hoy) sigue mostrando 1.000 suscriptores y 4.000
   horas, pero el blog oficial de Google (edición MENA, 2026-08-11) indica 8.000 horas (o 20 M de vistas de Shorts) para
   solicitantes nuevos desde 2027-02-01. Planificar con 8.000 horas.
2. **A/B de YouTube (Test & Compare) decide por cuota de tiempo de visualización, no por CTR.** Hay que decidir si el CTR
   sigue siendo la métrica del canal.
3. **Licencias que descartan herramientas en un canal monetizado:** F5-TTS (pesos CC-BY-NC), MusicGen (CC-BY-NC), NLLB
   (CC-BY-NC), FLUX.2 9B (no comercial). PlayHT cerró el 2025-12-31 (tercero).
4. **`videos.insert` tiene cubo propio de cuota desde 2026-06-01:** las subidas ya no limitan.
5. **CTR:** disponible por la Reporting API (`channel_reach_basic_a1`), no visto en la Analytics API.
6. **El riesgo común de política** es el patrón de producción en masa con plantillas idénticas (edición, guion,
   miniaturas): hay que variar estructura y mantener valor propio por video.

## Principales incógnitas (a resolver con experimentos baratos)

- **Cronometrar minutos humanos reales** de un video completo: es el dato que decide la compuerta.
- **Tiempos de máquina en el M4 Max** sin medir para imágenes (FLUX.2 klein 4B con `mflux`), LLM locales (Gemma 4,
  Qwen3.8), Qwen3-TTS bajo MLX, `mlx-whisper`.
- **Términos comerciales de salida** sin leer para Gemini Image, ElevenLabs, OpenAI, Google, Azure, Fish Audio (el plan
  gratis se contradice), Figma AI y varias músicas (Uppbeat, Epidemic, Artlist, Udio).
- **Si el bloqueo de subidas "privadas" de proyectos de API no verificados sigue activo** (las fuentes se contradicen) y
  si un uso personal exige verificar la app de OAuth (el token en estado "Testing" caduca a 7 días).
- **Divulgación de contenido sintético:** reglas exactas para imágenes ilustradas, música generada por IA y SynthID.

## Contenido

1. 01 Guion e investigación
2. 02 Voz y narración
3. 03 Visuales
4. 04 Edición y render
5. 05 Miniaturas, títulos y packaging
6. 06 Música, efectos y subtítulos
7. 07 Publicación y analítica


---

# Parte 1

## Etapa 01: Guion e investigación (herramientas)

Fecha de consulta de todas las fuentes `web`: **2026-11-01** (caducan a los 90 días: 2027-01-30). Alcance: investigar el tema con fuentes, esquema, guion largo (~4.700 palabras, 18 a 28 min), verificación de hechos, control de originalidad/plagio y estructura de retención, para canales en inglés (secundario: español), sin rostro.

Tipos de dato: `medido`, `web`, `tercero`, `supuesto` (brief común). Aviso de método: las páginas se leyeron con WebFetch, que devuelve un resumen hecho por un modelo pequeño, no el texto íntegro. Las cifras clave (precios, licencias) conviene reconfirmarlas en la página antes de gastar dinero. Varias páginas devolvieron 404 o no mostraban el dato; eso va en `unknowns`.

El Foundry del propietario (`~/Foundries/...`) existe. **No contiene ninguna ficha ni stack de esta etapa** (solo voz, miniaturas, imágenes y alineación). Esta etapa parte de cero en medición: todo lo local de LLM es `web`/`tercero`/`supuesto`, nada es `medido`.

---

### 1. Resumen y recomendación

#### Tabla de decisión

| Nivel | Qué usar | Por qué | Dinero por video | Tiempo de máquina por video | Minutos humanos por video |
|---|---|---|---|---|---|
| **A: gratis y local** | **Gemma 4 31B-it (4-bit MLX, 18,4 GB, Apache-2.0)** o **Qwen3.8-27B / Qwen3-32B (Apache-2.0)** servidos con `mlx_lm.server` + una búsqueda sin costo (Wikipedia, Semantic Scholar, fuentes que pegue el propietario) + script propio de similitud n-gram | Licencia permisiva con salida libre de restricciones, cabe en 64 GB con holgura, contexto largo (256K), API local compatible con OpenAI, 0 USD | 0 USD de API | ~20 a 60 min con varias pasadas (esquema, 8 a 10 secciones, revisión, extracción de afirmaciones, verificación). `supuesto`: ancho de banda 546 GB/s del M4 Max sobre 18,4 GB da del orden de 20 a 30 tok/s de generación; ~6.500 tokens por borrador final | **20 a 30** (el modelo local alucina más y la verificación pesa más) |
| **B: gratis con límites o bajo costo** | **Claude Haiku 5.5 (0,10 / 0,50 USD por MTok) o Gemini 3.1 Flash-Lite / 3.5 Flash-Lite para volumen**, y **Claude Sonnet 5.5 (2 / 10 USD por MTok) solo para la pasada de redacción final**; **Tavily (1.000 créditos/mes gratis)** para recuperar fuentes | Calidad de redacción y citas mucho mayor que un 31B local; coste de centavos por video | ~0,02 a 0,35 USD (`supuesto`, ver §2) | 5 a 15 min (esperas de API) | **12 a 20** |
| **C: pago** | **Claude Fable 5 / Opus 5.5 para la redacción + Perplexity Search API (5 USD/1.000 búsquedas) o Tavily de pago + Copyscape/Originality.ai** | Máxima calidad de prosa y menos correcciones; plagio verificable contra la web | ~1 a 3 USD de modelo (`supuesto`) + 0,5 a 2 USD de verificación | <10 min | **10 a 15** |

**Recomendación principal: Nivel B en la práctica, con Nivel A como respaldo.** Motivo: la redacción larga con hechos citados es la etapa donde un modelo local pequeño falla más (alucinación de datos, repetición, prosa genérica) y donde un error cuesta más (afirmación falsa publicada, contenido que YouTube lee como genérico). Un video de ~4.700 palabras cuesta céntimos con una API barata. Nivel A es viable y cumple "0 USD", pero hay que **medir** si su calidad evita que los minutos humanos suban por encima de 30 (experimento en §5).

#### Qué automatiza la etapa y cuánto cuesta en minutos humanos

Automatizable (≥90 % del trabajo de escritura): recopilar fuentes, resumir, esquema, borrador, estructura de retención, tabla de afirmaciones con cita, verificación cruzada, similitud con fuentes. **No automatizable sin riesgo** (y por eso se cuentan minutos): elegir la tesis y el ángulo propio, validar una muestra de afirmaciones contra la fuente original, y una lectura final que aporte voz y juicio. Presupuesto recomendado a contar en las compuertas de NicheRadar: **15 minutos humanos por video (`supuesto`)** repartidos así: 3 min tesis/ángulo, 7 min revisar la tabla de afirmaciones de mayor riesgo, 5 min lectura y retoque. Esto deja 45 min del tope de 60 para las demás etapas. Si la etapa de guion cuesta más de 25 min, consume el margen de las otras.

#### Cuánto del guion se puede automatizar sin caer en "contenido inauténtico"

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

### 2. Catálogo de candidatos

Convención de costo por video: **supuesto de tokens** para un video típico = 40.000 tokens de entrada acumulados (fuentes + prompts de varias pasadas) y 25.000 de salida (esquema, borrador ~6.500 tokens, revisiones, tabla de afirmaciones). Es un supuesto mío, no una medición. Costo = entrada x precio + salida x precio.

#### 2.1 Modelos y motores (redacción)

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

#### 2.2 Investigación, citas y búsqueda

| # | Herramienta | Tipo | Costo | Min humanos | Licencia/uso | Calidad/defectos | Dato | Fuente |
|---|---|---|---|---|---|---|---|---|
| 13 | **Tavily Search/Extract/Research** | API | Gratis: 1.000 créditos/mes sin tarjeta. Búsqueda básica 1 crédito, avanzada 2; extracción 1 crédito por 5 URLs; investigación 4 a 110 créditos (mini) o 15 a 250 (pro). Pago por uso: 0,008 USD/crédito | 1 a 3 (elegir fuentes) | Términos de uso no leídos | Un video con ~25 búsquedas básicas + 10 extracciones cuesta ~30 créditos (`supuesto`): ~30 videos/mes gratis | web | https://docs.tavily.com/documentation/api-credits |
| 14 | **Perplexity Search API** | API | 5 USD por 1.000 solicitudes exitosas; 1 USD por 1.000 con Fast Search. Precios de Sonar no vistos | 1 a 3 | n/v | Devuelve resultados con fuente; el precio es pago desde el primer uso (no vi nivel gratis) | web | https://docs.perplexity.ai/getting-started/pricing |
| 15 | **Brave Search API** | API | Página de precios sin datos legibles (solo encabezados) | n/d | n/v | No se pudo verificar nivel gratis ni términos de almacenamiento | **no verificado** | https://api-dashboard.search.brave.com/documentation/pricing |
| 16 | **Semantic Scholar API** | API | Gratis; sin clave: 1.000 solicitudes/segundo compartidas entre todos los anónimos; con clave: 1 req/s inicial | 0 a 2 | Acuerdo de licencia de API aparte (no leído); datasets abiertos S2AG, S2ORC, SUPP.AI | Útil solo si el nicho es científico o histórico con literatura | web | https://www.semanticscholar.org/product/api |
| 17 | **Búsqueda manual y fuentes primarias que el propietario pega** | humano | 0 USD | 3 a 8 | Cada fuente tiene su propia licencia | Es el insumo que más diferencia un guion de uno genérico | supuesto | n/a |

#### 2.3 Verificación de hechos

| # | Herramienta | Tipo | Costo | Min humanos | Notas | Dato | Fuente |
|---|---|---|---|---|---|---|---|
| 18 | **Google Fact Check Tools API** (`claims:search`) | API | No leí cuota ni costo (la página no los traía) | 0 a 1 | Solo encuentra afirmaciones **ya verificadas por terceros**; no verifica un dato nuevo. Sirve para afirmaciones virales o políticas, no para cifras de nicho | web (función) | https://developers.google.com/fact-check/tools/api/reference/rest |
| 19 | **Verificación propia por pasos** (script con LLM local o de API) | local/API | 0 a 0,10 USD | 5 a 10 | Ver §3 ficha: extraer cada afirmación verificable, buscarla en las fuentes recuperadas, exigir **cita textual**, marcar "sin respaldo" lo que el verificador no encuentre | supuesto (diseño) | n/a |

#### 2.4 Plagio y originalidad

| # | Herramienta | Tipo | Costo | Notas | Dato | Fuente |
|---|---|---|---|---|---|---|
| 20 | **Script de similitud n-gram contra las fuentes recuperadas** | local | 0 USD; segundos de CPU | Detecta copia literal o paráfrasis pegada respecto de **las fuentes que usamos**, no contra toda la web. Umbral sugerido: ningún tramo de 8 palabras consecutivas copiado sin comillas (`supuesto`) | supuesto | n/a |
| 21 | **Copyscape** (API/Premium) | servicio | Capterra lista un paquete Premium de 3 USD; no pude leer la página oficial de precios (404). Quejas de usuarios sobre caducidad de créditos y subidas | tercero | https://www.capterra.com/p/179608/Copyscape/ (vía búsqueda) |
| 22 | **Originality.ai** | servicio | Créditos: 100 palabras por crédito (IA) o 2 créditos por 100 palabras (IA + plagio); Pro 14,95 USD/mes ~200.000 palabras según CASRAI | tercero | https://www.casrai.org/guides/copyleaks-pricing (vía búsqueda) |
| 23 | **Copyleaks** | servicio | Capterra: 8,99 USD/mes (plagio) o 13,99 USD/mes (IA + plagio) por usuario; API como complemento aparte; datos discrepan | tercero | https://www.capterra.com/p/185429/Copyleaks/pricing/ (vía búsqueda) |

Un guion de 4.700 palabras cuesta ~94 créditos en Originality.ai con IA + plagio (2 créditos por 100 palabras). Con la cifra `tercero` de ~200.000 palabras/mes del plan Pro alcanzarían ~42 guiones/mes (`supuesto` de cálculo; no confirmado si esa cifra cuenta ambos chequeos). **Los detectores de "IA" no se recomiendan** como compuerta: no hay evidencia aquí de que YouTube los use, y sus falsos positivos no se midieron en esta investigación.

---

### 3. Fichas breves (recomendados y finalistas)

#### 3.1 Pipeline recomendado (Nivel B con respaldo A)

Un solo orquestador en Python (o un skill de Claude Code) con **cinco pasadas**, cada una con salida estructurada en JSON/Markdown para que pueda auditarse:

1. **Recuperación**: 15 a 25 consultas a Tavily (o fuentes pegadas) → texto extraído de 10 a 20 fuentes, guardado con URL y fecha. Sin fuentes guardadas no hay guion.
2. **Tesis y esquema** (humano 3 min): el modelo propone 3 ángulos con las pruebas que cada uno tendría; el propietario elige o reescribe uno. Luego esquema por actos con **arquitectura de retención** (ver §3.4).
3. **Redacción por secciones** (8 a 10 secciones de ~500 palabras) con las fuentes relevantes en contexto. Cada afirmación factual sale con marcador `[S3]` hacia una fuente. Por secciones, no de una vez: reduce repetición y alucinación y respeta los límites de TPM de los niveles gratis.
4. **Verificación**: otro paso extrae cada afirmación con marcador y comprueba que la fuente citada la respalda (cita textual obligatoria). Lo que no tenga respaldo se reescribe o se elimina. Para modelos locales, usar **un modelo distinto** del que redactó.
5. **Control de originalidad**: n-gram contra las fuentes recuperadas; reportar tramos copiados; reescribir esos tramos.

Salida para humano: guion limpio (sin marcadores) + tabla de afirmaciones con estado `verificada / débil / sin respaldo` + lista de tramos similares. El humano solo lee lo marcado "débil/sin respaldo" y 5 min de lectura.

#### 3.2 Local: mlx-lm + Gemma 4 31B (4-bit) o Qwen3.8-27B

- **Qué es**: motor MLX (MIT) con servidor local compatible con OpenAI; modelo Apache-2.0.
- **Integración**: `mlx_lm.server --model mlx-community/gemma-4-31b-it-4bit` (comando de la tarjeta del modelo) y el orquestador llama a `http://localhost:8080/v1` (puerto por confirmar al ejecutar). CLI: `mlx_lm.generate`, `mlx_lm.chat`; `mlx_lm.cache_prompt` guarda el prefijo de fuentes y evita reprocesarlo entre secciones, que es útil porque cada sección reutiliza el mismo bloque de investigación.
- **Límites**: macOS 15 o superior. Para un modelo grande, puede hacer falta subir el límite de memoria de GPU con `sudo sysctl iogpu.wired_limit_mb=N` (requiere sudo; el propietario debe hacerlo él). `--max-kv-size` limita la memoria a costa de calidad. El propio Foundry registró una corrida atípica de TTS que sobrepasó 64 GB: **no correr el LLM y el TTS a la vez.**
- **Riesgos**: no hay evidencia verificada de calidad de prosa larga ni de velocidad real en el M4 Max (solo guías de terceros). Alucinación de datos superior a la de un modelo de pago `supuesto`. Gemma 3 y anteriores tienen términos propios; Gemma 4 aparece como Apache-2.0 en su tarjeta, pero la página de términos de Google remite a "otra licencia" para Gemma 4: **verificar el texto de licencia antes de comercializar**.

#### 3.3 API: Haiku 5.5 / Flash-Lite para volumen y Sonnet 5.5 para redactar

- **Integración**: SDK oficial (Python/TypeScript) o HTTP; Batch API con 50 % de descuento si no importa esperar; caché de prompt para el bloque de fuentes que se repite en cada sección (lecturas de caché: 0,10 USD/MTok en Sonnet 5.5 frente a 2 USD de entrada normal).
- **Riesgos**: cambios de modelo y de precio (algunos precios de Gemini vencen en 2026-11-30 y 2026-12-31). Nivel gratis de Gemini: Google puede usar el contenido y personas pueden leerlo; para guiones propios esto no importa, pero no pegar material de terceros bajo confidencialidad.

#### 3.4 Estructura de retención (esquema, no herramienta)

No encontré en esta investigación una herramienta con evidencia medida de retención; el postmortem de retención real del propietario (skill `youtube-retention-postmortem`) es la fuente correcta una vez haya métricas. Mientras tanto, usar una plantilla de actos **parametrizada**, no fija (`supuesto`): gancho de 30 a 45 s con la promesa y un dato específico; 3 a 5 "bucles abiertos" resueltos a lo largo del video; un giro o revelación a ~60 % de la duración; cierre sin resumen repetitivo. Rotar 4 a 6 variantes de arquitectura entre videos para no producir un patrón idéntico (§1, política de contenido producido en masa).

#### 3.5 Verificación y plagio propios

- **Verificación**: tabla `afirmación | fuente | cita textual | estado`. Regla dura: una afirmación sin cita textual de una fuente recuperada **no entra** al guion final. Verificador distinto del redactor. Los números, fechas, nombres y citas son lo que más se alucina; son los que el humano revisa por muestreo (`supuesto`: 10 afirmaciones de mayor riesgo, 7 min).
- **Plagio**: n-gram (p. ej. 8 palabras) contra las fuentes guardadas; reescribir tramos que coincidan. Para chequeo contra toda la web usar Copyscape u Originality.ai en lote solo si el canal ya publica con regularidad, no en el piloto.

---

### 4. Riesgos de política y de derechos

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

### 5. Comparación con lo medido por el propietario y qué falta medir

**Lo ya medido** (Foundry): nada de esta etapa. El stack `voice-narration` mide voz y reutiliza ~4.670 palabras por video; esto confirma el tamaño objetivo del guion pero no su producción. Dato útil heredado: el agente que escribe debe **fijar el idioma de salida** (un desajuste de idioma generó WER 0,714 en voz); incluir `language` explícito en cada prompt de redacción. Dato `medido` del stack de voz: la síntesis se hace en trozos de máximo 450 palabras con corte en límite de oración; conviene que el guion llegue con párrafos que respeten ese corte.

**Experimentos baratos que puede correr el propietario** (en orden de valor):

1. **Calidad y minutos humanos, 3 modelos, 1 mismo tema** (30 min cada uno): Gemma 4 31B (4-bit MLX), Qwen3.8-27B y Claude Haiku 5.5 o Sonnet 5.5. Para cada uno medir: palabras entregadas (¿cumple 4.700?), número de afirmaciones sin respaldo según la tabla del verificador, minutos humanos hasta dejar el guion publicable, tiempo de máquina y dólares. Resultado: decide Nivel A vs B con datos propios.
2. **Velocidad real en el M4 Max**: tokens/s de `mlx_lm.generate` con el modelo de 31B (4-bit) en un prompt de 30K tokens. Anotar memoria máxima. Valida mi supuesto de 20 a 30 tok/s.
3. **Tasa de alucinación**: tomar 30 afirmaciones de un guion generado, buscar a mano la fuente de cada una; comparar contra lo que dijo el verificador automático. Mide la confiabilidad del verificador (falsos "verificada").
4. **Similitud**: pegar 3 guiones en Copyscape (gratis o 3 USD) o Originality.ai y comparar con el script n-gram propio. Mide si el n-gram local alcanza.
5. **Variedad entre videos**: generar 5 guiones del mismo nicho con la rotación de arquitectura y medir si abrir/cerrar/transiciones son distinguibles (lectura del propietario, 10 min). Es la defensa práctica contra "contenido en masa".

---

### 6. Unknowns

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

#### Tabla de fuentes (acceso 2026-11-01)

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


---

# Parte 2

## Etapa 02: Voz y narración

Fecha de consulta: 2026-11-01. Video típico de referencia: ~4.700 palabras, ~26.000 caracteres (supuesto: ~5,5 caracteres por palabra con espacios), 18–28 min.
Tipos de dato: **medido** (corrida del propietario), **web** (fuente oficial leída hoy; caduca a 90 días), **tercero** (agregador/blog/reseña), **supuesto** (mío).
Alcance: solo investigación. No se instaló ni se descargó nada; "corre en Apple Silicon" se apoya en README/issues, no en pruebas mías.

### 1. Resumen y recomendación

La etapa (guion aprobado a audio con tiempo por palabra, verificado y normalizado) ya está casi 100 % automatizada en `canal-historias`. Los minutos humanos reales son: elegir/validar la voz de referencia (una vez por canal), oír una muestra de arranque y atender los retries que falla el gate de WER. **Contar 5 a 10 minutos humanos por video** una vez estabilizado el canal (supuesto: el propietario no midió minutos humanos de voz; ver sección 5).

| Nivel | Recomendada | Por qué | Dinero / video | Máquina / video |
|---|---|---|---|---|
| **A: gratis y local** | **Qwen3-TTS-1.7B-Base** (ya medido) vía `mlx-audio` o PyTorch `mps`, con WhisperX/Whisper para alineación y WER | Apache-2.0 (web), clona voz propia con referencia corta, único local que el propietario midió limpio en 20+ min (WER 0,058). Prueba pendiente: la variante MLX de `mlx-audio` para bajar los 47–90 min | 0 USD | 47–90 min (medido, n pequeño); un atípico de 6 h 40 min (medido, n = 1) |
| **B: gratis con límites o bajo costo** | **Fish Audio por API** (ya medido, 0,41 USD) como principal; **OpenAI `tts-1`** (~0,39 USD, supuesto de cálculo) o **Google Chirp 3 HD / Azure Neural** (nivel gratis mensual de caracteres, tercero) como respaldo sin clonación | Fish: medido, clona, devuelve tiempo por palabra. Google/Azure: cuota gratis mensual alcanzaría varios videos, pero sin clonación propia y sin medir | 0,41 USD (medido) / 0–0,8 USD (supuesto) | Minutos |
| **C: pago** | **ElevenLabs** (Creator 22 USD/mes, web) o **Cartesia Pro** (5 USD/mes, web) | ElevenLabs: voz y ecosistema más maduros, licencia comercial explícita desde Starter. No probado por el propietario. Cartesia: más barato, clonación instantánea desde Pro | 2–5 USD por video con API Flash/v2 (cálculo, ver nota) | Minutos |

Nota de cálculo (supuesto, ~26.000 caracteres): ElevenLabs API 0,04 USD/1K caracteres Flash = ~1,04 USD y 0,08 USD/1K v2 = ~2,08 USD (web); por suscripción, Creator con 121.000 créditos alcanza ~4 videos/mes si 1 crédito = 1 carácter (supuesto, no confirmado en la página).

**Veredicto de la compuerta (60 min humanos máx., 90 % automatización):** la voz no es el cuello de botella. El riesgo de la etapa es el **tiempo de máquina** del nivel A y la **divulgación/inautenticidad**, no los minutos humanos. Un presupuesto que ponga ElevenLabs "por defecto" ignora que el propietario ya produce con 0 USD de API.

### 2. Catálogo de candidatos

Columnas abreviadas: Apple Si = soporte en Apple Silicon; Cal = calidad y defectos; Idiomas; Dato = tipo.

| # | Herramienta | Tipo | Costo en dinero | Máquina / humanos | Licencia y uso comercial | Apple Si | Cal / defectos | Idiomas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Qwen3-TTS 1.7B Base** | Local | 0 USD | 47–90 min; atípico 6 h 40 min / ~5–10 min | Apache-2.0 (model card). Clonación con referencia + transcripción | Sí: `mps` (medido). MLX vía `mlx-audio` (README) | WER 0,058 medido; volumen bajo (−21 LUFS), sin control de velocidad, depende del idioma del texto. Tope por defecto ~500 tokens (~40 s) en una guía de tercero | 10 (EN, ES, ZH, JA, KO, DE, FR, RU, PT, IT) | web [HF Qwen3-TTS], medido [ficha qwen3-tts], tercero [soniqo] |
| 2 | **Fish Audio (API)** | API | 0,41 USD/video medido (n = 1). Planes: Free 0 (8.000 créditos, 7 min, 500 caracteres/generación), Plus 11 USD/mes, Pro 75 USD/mes (anuales) | Minutos / ~5 min | Pesos abiertos: Fish Audio Community/Research License (no verificada su cláusula comercial). API: la página se contradice (Free "uso comercial" vs FAQ "solo personal y no comercial"); exigir plan de pago | N/A (nube) | Bucle de repetición en trozo de 627 palabras (WER 0,311, medido). Mitigación: trozos de 450 palabras | ~100 (S2-Pro, web) | web [fish.audio/plan], [GitHub fish-speech], medido [ficha] |
| 3 | **ElevenLabs** | API | Free 10.000 créditos/mes; Starter 6 USD/mes (1 el primer mes) 30.000 créditos; Creator 22 USD/mes (11 el primer mes) 121.000 créditos; API Flash 0,04 / v2 0,08 USD por 1K caracteres | Minutos / ~5 min | Licencia comercial listada desde Starter (web); Free no la lista. Clonación instantánea desde Starter, profesional desde Creator | N/A | No probado por el propietario. Defecto de bucles "del mismo tipo" afirmado por el canal sin leer su fuente: no verificado | Multilingüe (lista no leída) | web [elevenlabs.io/pricing], [pricing/api] |
| 4 | **Kokoro-82M** | Local | 0 USD | Supuesto: mucho más rápido que 47 min (82M parámetros), sin medir / ~5 min | Apache-2.0 (README). Voces predefinidas, sin clonación documentada | Sí: M1–M4 con `PYTORCH_ENABLE_MPS_FALLBACK=1` (README); MLX vía `mlx-audio` | Reseña de tercero: artefactos leves en límites de párrafo a 10+ min; entrega plana en ficción. Buen candidato para narración informativa, sin voz propia | EN (US/UK), ES, FR, HI, IT, JA, PT-BR, ZH | web [GitHub kokoro], tercero [aivideosensei, texttolab] |
| 5 | **Chatterbox (Resemble)** | Local | 0 USD | Sin medir / ~5 min | MIT (README). Marca de agua PerTh en toda la salida (inaudible; pasa a MP3) | `mps` como opción en el código y `example_for_mac.py`; sin detalle de rendimiento | **Medido por el propietario: omisión de oraciones, reproducible** (ficha qwen3-tts). V3 afirma menos alucinación (vendedor) | Turbo/Nano solo EN; V3 23+ | web [GitHub chatterbox], medido [ficha] |
| 6 | **F5-TTS** | Local | 0 USD | Sin medir | Código MIT, **pesos preentrenados CC-BY-NC** (datos Emilia): **no usable comercialmente** sin reentrenar | PyTorch estándar; port MLX de tercero (`f5-tts-mlx`) acreditado | Clonación con referencia + texto; "chunk inference" en la interfaz. Sin datos de estabilidad larga | EN/ZH (modelo Emilia ZH-EN) | web [GitHub F5-TTS] |
| 7 | **XTTS-v2 (Coqui / fork idiap)** | Local | 0 USD | Sin medir | **CPML** (Coqui Public Model License): la página no resume uso comercial; verificar el texto antes. Empresa original cerrada; el fork idiap es el mantenido (PyPI `coqui-tts`) | Sin mención de MPS en el fork; ruedas macOS | Modelo de 2023-24, superado en calidad por los nuevos (juicio mío, sin fuente) | 17 | web [HF XTTS-v2], [GitHub idiap] |
| 8 | **Piper (OHF-Voice/piper1-gpl)** | Local | 0 USD | CPU, rápido (supuesto, sin medir) | **GPL-3.0** (barra lateral del repositorio); cada voz tiene su licencia aparte (no leída) | Sin mención de macOS en la página | Sin clonación; naturalidad inferior a los modelos neuronales grandes (juicio mío) | Muchos (lista no leída) | web [GitHub piper1-gpl] |
| 9 | **Dia (Nari Labs)** | Local | 0 USD | Sin medir | Apache-2.0, con usos prohibidos (suplantación, engaño) | **No**: probado solo en CUDA, CPU "planeado" (README) | Entradas de más de 20 s salen aceleradas: pensado para diálogo corto. Descartado para narración larga | Solo EN | web [GitHub dia] |
| 10 | **Orpheus-TTS (Canopy)** | Local | 0 USD | Sin medir | Apache-2.0 | No mencionado; opción sin GPU vía llama.cpp (no confirmada en Apple) | Base Llama-3B, clonación con pares texto-voz; Colab de clonación marcado pendiente | EN principal; familia multilingüe de investigación | web [GitHub Orpheus] |
| 11 | **Sesame CSM-1B** | Local | 0 USD | Sin medir | Apache-2.0, pero exige acceso (gated) a Llama-3.2-1B y CSM-1B; prohíbe suplantar sin consentimiento | Requiere CUDA según README (el código comprueba MPS pero no lo declara soportado); el propietario lo marcó **bloqueado** | Generación pensada para turnos cortos | EN | web [GitHub csm], medido [ficha] |
| 12 | **MLX-Audio (marco)** | Local (librería) | 0 USD | Depende del modelo | MIT (librería); cada modelo con su licencia | **Nativo Apple Silicon (MLX)**; requiere Apple Silicon | Sirve Kokoro, Qwen3-TTS, CSM y más; `--join_audio` une segmentos; servidor compatible con OpenAI `/v1/audio/speech`; incluye Qwen3-ForcedAligner (tiempo por palabra) y Whisper/Parakeet | Según modelo | web [GitHub mlx-audio] |
| 13 | **OpenAI TTS** | API | tts-1 15 USD/M caracteres (~0,39 USD/video, cálculo); tts-1-hd 30 USD/M (~0,78); gpt-4o-mini-tts 0,60 USD/M tokens de entrada + 12 USD/M tokens de audio | Minutos / ~5 min | Términos de salida no leídos (no verificado). Sin clonación de voz propia en la API pública (no verificado hoy) | N/A | Sin datos propios de estabilidad larga | Multilingüe (lista no leída) | web [OpenAI pricing] |
| 14 | **Google Cloud TTS** | API | Chirp 3 HD ~30 USD/M; Standard/WaveNet ~4 USD/M; Neural2 ~16; cuota gratis ~1 M (HD) / 4 M (Standard) de caracteres al mes | Minutos / ~5 min | Términos no leídos | N/A | La página oficial no cargó precios; cifras de agregadores | Muchos | tercero [diyai.io, costbench] (oficial no verificado) |
| 15 | **Azure AI Speech** | API | Neural ~15 USD/M; HD ~22–30 USD/M; gratis 0,5 M caracteres/mes (F0); voz personal "limited access" | Minutos / ~5 min | Voz personal/custom: acceso restringido por Microsoft (web); términos de salida no leídos | N/A | Precios en blanco en la página oficial; cifras de terceros | Muchos | web (estructura) + tercero (cifras) |
| 16 | **Cartesia Sonic** | API | Free 0 (20K créditos, sin licencia comercial); Pro 5 USD/mes (100K créditos, licencia comercial + clonación instantánea); Startup 49 USD/mes; 1 crédito = 1 carácter (~750–800 créditos/min de audio) | Minutos / ~5 min | Licencia comercial desde Pro (web) | N/A | Evaluada por el canal; decidió no migrar (sin detalle) | No leído | web [cartesia.ai/pricing], medido [ficha fish-audio] |
| 17 | **Murf** | API/estudio | No verificado (página sin cifras) | — | No verificado | N/A | No evaluado | — | web (sin datos útiles) |
| 18 | **PlayHT** | Servicio | **Cerrado** el 2025-12-31 tras la compra de Meta (julio 2025) | — | — | — | No usar | — | tercero [anyspeech, texttolab, hpcwire] |
| 19 | **WhisperX** (alineación/WER) | Local | 0 USD | Incluido en los 47–90 min | BSD-2-Clause (README); modelo de diarización aparte (CC-BY-4.0) | README solo indica CPU en Mac (`--device cpu --compute_type int8`) | Palabras con dígitos o símbolos sin timing; necesita modelo wav2vec2 por idioma. Defectos medidos en la ficha | EN, FR, DE, ES, IT por defecto; otros vía Hugging Face | web [GitHub whisperX], medido [ficha] |
| 20 | **mlx-whisper** (alternativa para WER) | Local | 0 USD | Sin medir | Licencia no indicada en la página consultada (repositorio mlx-examples) | MLX nativo | Soporta `word_timestamps=True` | Multilingüe | web [mlx-examples/whisper] |

### 3. Fichas breves

**Qwen3-TTS (nivel A, finalista).** Modelo local de Alibaba, Apache-2.0. Se integra como librería Python (`create_voice_clone_prompt` permite reusar la voz de referencia) o, probablemente más rápido, vía `mlx-audio` (lo lista como modelo soportado). Límites: sin control de velocidad, volumen bajo, el texto debe coincidir con el idioma, el model card no declara longitud máxima de entrada. Riesgo: la corrida atípica de 6 h 40 min con 66–78 GB de memoria; antes de lanzar canales en paralelo hay que medir si el trozo de 450 palabras en MLX evita la fuga. Una guía de tercero advierte que subir el tope de tokens puede activar el watchdog de Metal (riesgo de reinicio del sistema): no subir el tope sin probar.

**Fish Audio (nivel B, finalista).** API con SSE que devuelve audio y tiempo por palabra (medido). Automatizable por completo. Riesgos: bucle de repetición (mitigado con trozos y WER), codificación UTF-8 del stream, contradicción de la página sobre uso comercial en Free: **comprar/usar plan de pago o confirmar por escrito**. Tarifa por millón de bytes no leída aquí.

**ElevenLabs (nivel C).** Referencia comercial, licencia comercial desde Starter, clonación instantánea desde Starter y profesional desde Creator (web). No probado por el propietario. Antes de presupuestarlo, correr el experimento de la sección 5. Su coste mensual no escala bien con varios canales: 121.000 créditos son ~4 videos si 1 crédito = 1 carácter (supuesto).

**Kokoro (nivel A, complemento).** 82M parámetros, Apache-2.0, voces predefinidas. Útil como "voz gratis rápida" sin clonación: sirve para borradores, pruebas de guion y quizá para canales cuya identidad no dependa de una voz propia. Su estabilidad en 20+ min no está medida; cambio de tono en límites de párrafo reportado por tercero.

**MLX-Audio (infraestructura).** Una sola interfaz y servidor local OpenAI-compatible para TTS, STT y alineación con Qwen3-ForcedAligner. Si el propietario migra a MLX puede reemplazar WhisperX (que en Mac corre solo en CPU según su README) por el alineador de mlx-audio: **no probado**, comparar tiempos y exactitud antes.

**Google Chirp 3 HD / Azure Neural / OpenAI tts-1 (nivel B, respaldo).** Sin clonación propia verificada; sirven si el canal acepta una voz de catálogo. Cuota gratis mensual (Google ~1 M caracteres HD, Azure 0,5 M) alcanza ~19–38 videos/mes según el proveedor (cálculo sobre cifras de terceros). Hay que verificar en cada consola; Google exige cuenta de facturación aun en nivel gratis (tercero).

### 4. Riesgos de política y de derechos

1. **Divulgación de contenido sintético (YouTube).** La página oficial exige divulgar contenido realista alterado o sintético, p. ej. cuando "un persona real parece decir algo que no dijo". Lista como **menor, no divulgable**: clonar la **propia voz** para voz en off/doblaje, reparar o mejorar audio y subtítulos. La página dice también que puede etiquetar "audio no musical generado por IA" y que divulgar no limita la audiencia ni la monetización. Lectura (mía, no jurídica): una voz sintética genérica o la voz propia en narración **no** obliga a divulgar; **clonar a otra persona sí**. Fuente: https://support.google.com/youtube/answer/14328491.
2. **Contenido inauténtico (YPP).** Desde 2025-07-15 cubre contenido "repetitivo o producido en masa" y prohíbe contenido IA hecho con "plantillas genéricas o poco originales" y lecturas de material ajeno (feeds de noticias, texto de sitios). La página **no** distingue voz IA de voz humana; lo que se juzga es valor propio (guion, comentario, narrativa). Varios canales con el mismo pipeline y la misma voz son la señal de riesgo. Fuente: https://support.google.com/youtube/answer/1311392. Personas IA como expertos en salud, legal, finanzas o política: sin monetización.
3. **Consentimiento de la voz clonada.** Dia y Sesame prohíben suplantar sin consentimiento (README). ElevenLabs y Cartesia condicionan la clonación a plan y a verificación (web, detalle de los términos no leído). **Regla propia sugerida:** clonar solo la voz del propietario o de un locutor con contrato escrito; nunca voz de terceros. La voz de referencia es identidad del canal.
4. **Licencia de pesos.** F5-TTS (pesos CC-BY-NC) no es usable en un canal monetizado. XTTS-v2 (CPML) y Fish `S2-Pro` (Research License) requieren leer sus textos. Piper es GPL-3.0 (afecta si se redistribuye código, no el audio generado, interpretación mía no jurídica). Qwen3-TTS, Kokoro, Chatterbox (MIT, con marca de agua), Orpheus, Dia, CSM: sin restricción de uso comercial en README, pero las salidas heredan las restricciones de uso prohibido.
5. **Marca de agua.** Chatterbox incrusta PerTh en toda salida. No es un problema de política, pero un tercero puede detectar que el audio es sintético.
6. **Proveedores que desaparecen.** PlayHT cerró (tercero) y borró voces: no depender de un proveedor sin copia local de la voz de referencia.

### 5. Comparación con lo que mide el propietario y qué falta medir

- Medido (ficha): Qwen3-TTS 0,058 WER, FireRedTTS3 0,053, Chatterbox omite oraciones, TADA-1B inserta leve, Zonos descartado; NeuTTS Air, VibeVoice y Sesame bloqueados. Esta investigación **confirma** los bloqueos de Sesame (CUDA/acceso gated) y **no contradice** nada. FireRedTTS3 no se cataloga aquí (no investigado: no tengo fuente leída) y empata con Qwen3 en WER medido; **falta su tiempo y su licencia**.
- La ficha de ElevenLabs está **desactualizada pero compatible**: el precio de 22/11 USD coincide con la página (web, hoy). La página oficial confirma que los 11 USD son el primer mes. El Starter es 6 USD (1 el primer mes), no 11.
- La ficha de Fish Audio omite que su página de planes se contradice sobre uso comercial en Free: añadirlo.
- La ficha de WhisperX dice "BSD-2-Clause (según el canal)": **confirmado** en su README. Añadir que en Mac su README muestra solo CPU.

**Experimentos baratos que puede correr (cada uno <1 h humana):**
1. Mismo trozo de 450 palabras y mismas 3 pasadas: Qwen3-TTS vía `mlx-audio` frente a `mps` PyTorch. Medir tiempo, memoria pico y WER. Objetivo: bajar de 47–90 min y evitar el atípico.
2. Kokoro y (si procede) otro modelo de `mlx-audio` sobre el **mismo video de 4.700 palabras**: tiempo total, WER por beat, y seams en límites de párrafo. Ver si la naturalidad basta sin clonación.
3. ElevenLabs con **plan Free** (10.000 créditos, sin tarjeta) solo como prueba **no publicable** de calidad y WER del mismo trozo; no usar el audio en un canal sin plan comercial.
4. Escucha a ciegas (3 muestras de 2 min, ordenadas al azar) entre Qwen3, Fish y la mejor opción nueva: lo que falta es una medición de gusto/retención, no solo WER.
5. Minutos humanos reales por video de voz (cronómetro durante dos videos): hoy es un supuesto.
6. Alineación: `mlx-audio` Qwen3-ForcedAligner frente a WhisperX en CPU: tiempo y error de timing en subtítulos.

### 6. Unknowns

- Tiempo de máquina de Kokoro, F5-TTS, Chatterbox, Orpheus, Piper y XTTS en el M4 Max con un video de 4.700 palabras: ninguno medido ni encontrado.
- Estabilidad de Qwen3-TTS en 20+ min bajo MLX: no hay cifras publicadas (búsqueda sin resultado).
- Precios oficiales de Google y Azure: sus páginas devolvieron cifras vacías; solo hay agregadores. Murf: sin datos útiles.
- Términos de uso de salida y de clonación de ElevenLabs, OpenAI, Google, Azure: no leídos.
- Cláusula comercial de la licencia de Fish Audio (Community/Research License) y de su API Free (contradictoria en la propia página).
- Texto de CPML (XTTS-v2) y licencias por voz de Piper.
- Causa de la corrida atípica de 6 h 40 min y de si ocurre con trozos <=450 palabras.
- Si "1 crédito = 1 carácter" en ElevenLabs aplica a la API de Creator (la página dice que la API se cobra en USD, no en créditos).
- Soporte de Dia/Orpheus/CSM en Apple Silicon: ninguno confirmado.
- Si existe un modelo local estable en español comparable en calidad (idioma secundario): no investigado a fondo (Qwen3-TTS, Kokoro, XTTS y Chatterbox V3 lo declaran, sin medición).

### Tabla de fuentes (acceso 2026-11-01 salvo nota)

| Tema | URL |
|---|---|
| Política YouTube, contenido sintético | https://support.google.com/youtube/answer/14328491 |
| Política YouTube, contenido inauténtico | https://support.google.com/youtube/answer/1311392 |
| Kokoro | https://github.com/hexgrad/kokoro |
| MLX-Audio | https://github.com/Blaizzy/mlx-audio |
| Chatterbox | https://github.com/resemble-ai/chatterbox |
| F5-TTS | https://github.com/SWivid/F5-TTS |
| Qwen3-TTS (model card) | https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base |
| Dia | https://github.com/nari-labs/dia |
| Orpheus-TTS | https://github.com/canopyai/Orpheus-TTS |
| Sesame CSM | https://github.com/SesameAILabs/csm |
| Piper | https://github.com/OHF-Voice/piper1-gpl |
| Coqui fork idiap | https://github.com/idiap/coqui-ai-TTS |
| XTTS-v2 | https://huggingface.co/coqui/XTTS-v2 |
| ElevenLabs precios | https://elevenlabs.io/pricing y https://elevenlabs.io/pricing/api |
| Fish Audio planes | https://fish.audio/plan/ |
| Fish Speech (repositorio) | https://github.com/fishaudio/fish-speech |
| OpenAI precios | https://developers.openai.com/api/docs/pricing |
| Cartesia | https://cartesia.ai/pricing |
| Azure Speech (cifras en blanco) | https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/ |
| Google TTS (agregadores, tercero) | https://diyai.io/ai-tools/audio-generation/google-cloud-text-to-speech-pricing/ y https://costbench.com/software/ai-voice-tools/google-cloud-text-to-speech/ |
| Cierre de PlayHT (tercero) | https://anyspeech.io/playht-alternatives y https://www.hpcwire.com/aiwire/2025/07/16/meta-picks-up-voice-startup-play-ai-as-it-rebuilds-around-genai/ |
| WhisperX | https://github.com/m-bain/whisperX |
| mlx-whisper | https://github.com/ml-explore/mlx-examples/tree/main/whisper |
| Qwen3-TTS en Apple Silicon (tercero) | https://soniqo.audio/benchmarks |
| Reseñas Kokoro/Chatterbox/XTTS (tercero) | https://aivideosensei.com/compare/kokoro-vs-chatterbox-vs-xtts y https://texttolab.com/blog/kokoro-tts-review |
| Medido (propietario) | `~/Foundries/david-foundry-core/tool-registry/{qwen3-tts,fish-audio,elevenlabs,whisperx}.md` y `~/Foundries/david-youtube-foundry/stacks/voice-narration.md` |


---

# Parte 3

## Etapa 03: Visuales (imágenes IA, footage y archivo libre, mapas y líneas de tiempo, animación, video IA)

Fecha de consulta: 2026-11-01. Los datos `web` caducan a los 90 días (2027-01-30). Hardware de referencia: Mac Apple M4 Max, 64 GB, GPU `mps`/Metal, sin CUDA. Nadie instaló ni descargó nada para este informe; todo es lectura de fuentes.

Tipos de dato: **medido** (corrida real del propietario), **web** (fuente oficial leída hoy), **tercero** (blog, agregador, reseña, no oficial), **supuesto** (mío, con razón).

---

### 1. Resumen y recomendación

**Qué automatiza la etapa:** del guion con marcas de escena a un conjunto de planos (stills con movimiento, footage libre, mapas, clips IA) listos para el editor. La parte que NO se automatiza sola es la revisión humana de derechos y de marcas registradas en cada imagen generada (el Foundry ya lo midió con `gemini-image`: apareció el logo real de L.L.Bean).

**Cantidad necesaria (supuesto):** 20 a 28 min de video = 1.200 a 1.680 s. Con un plano nuevo cada 7 a 10 s (ritmo documental con movimiento Ken Burns) son **120 a 240 planos**. Reparto propuesto: ~60 % stills generados, ~25 % archivo/footage libre y mapas, ~10 % animación simple (líneas de tiempo, mapas), ~5 % clips IA. Para estimar costos uso **150 planos únicos** por video, con 1,3 intentos por plano aceptado (supuesto) ≈ 200 generaciones.

#### Tabla de decisión

| Nivel | Recomendación | Por qué | Dinero por video (supuesto sobre datos citados) | Máquina por video | Minutos humanos por video (supuesto) |
|---|---|---|---|---|---|
| **A: gratis/local** | **mflux (MLX) con FLUX.2 klein 4B (Apache-2.0)** para stills; **Pexels/Pixabay/NASA/NOAA/Wikimedia/LoC/Smithsonian/Internet Archive** para footage y archivo; **Natural Earth + ffmpeg/Manim** para mapas y líneas de tiempo | Licencia comercial clara (Apache-2.0 en el modelo y MIT en mflux), nativo de Apple Silicon, 0 USD de API | 0 USD | Stills: ~1,5 a 2,5 h si 25 a 40 s por imagen (supuesto; ver 2, no hay medición M4 Max). Corre sin supervisión de noche | 25 a 35 (revisar 150 planos en una cuadrícula de contactos, descartar defectos y marcas, aprobar licencias del archivo) |
| **B: gratis con límites / bajo costo** | **Gemini Image "Nano Banana 2.1" por API (ya en el stack)**: ~0,034 USD por imagen 1K; con `gemini-3.1-flash-image-preview` medido en 0,067 USD. Complemento: Cloudflare Workers AI FLUX.1 schnell (10.000 neuronas/día gratis) para borradores | Mejor adherencia al prompt y a referencias de personaje, sin tiempo de máquina local; el propietario ya lo tiene integrado | ~7 a 14 USD (150 a 200 imágenes × 0,034 a 0,067) | ~10 a 20 min de espera de red | 20 a 30 |
| **C: pago** | **Clips IA con Veo 3.1 Fast/Lite (0,05 a 0,12 USD/s, tercero)** solo para el ~5 a 10 % del metraje que no se puede cubrir con stills ni archivo | Es lo único que da movimiento real; el costo escala con los segundos, así que se acota | +6 a 22 USD por 2 a 3 min de clip aceptado, ×2 a ×3 por clips rechazados (supuesto) | Mínima | +10 a 15 (ver cada clip) |

**Minutos humanos totales de la etapa a contar: 25 a 35 (nivel A) o 20 a 30 (B); +10 a 15 si hay clips IA (C).** Esto consume entre un tercio y la mitad del presupuesto de 60 min por video de NicheRadar, así que la etapa no es "casi gratis" en tiempo humano: la compuerta se gana o se pierde en cuánta revisión se pueda automatizar (cuadrícula de contactos, filtros de marca, lista de licencias generada por script).

**Veredicto de consistencia visual:** el riesgo real no es calidad por imagen sino coherencia entre 150 planos. Solución recomendada (supuesto, a validar con el experimento 5.1): un bloque de estilo fijo en cada prompt + semilla/LoRA de estilo + referencias de personaje (Nano Banana acepta imágenes de referencia; FLUX.2 y Qwen Image tienen modos de edición con referencia en mflux). Un estilo ilustrado/gráfico (grabado, collage, acuarela) oculta mejor las variaciones que el fotorrealismo, y además reduce el riesgo de divulgación (ver 4).

---

### 2. Catálogo de candidatos

Costos de dinero, tiempo de máquina y minutos humanos van por separado. "Tiempo de máquina" es por video típico (~4.700 palabras, 18 a 28 min) salvo que se diga otra cosa.

#### 2.1 Generación de imágenes

| # | Herramienta | Tipo | Dinero | Tiempo de máquina | Min. humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **mflux + FLUX.2 klein 4B** | local (CLI/Python) | 0 USD | ~25 a 40 s/imagen 1024 px en M4 Max (supuesto). Referencia tercero: 30 a 40 s en M1 Max con mflux; un blog sin método da ~85 s en M4 Max para un modelo no especificado | 25 a 35 (revisión) | mflux: MIT. Pesos klein 4B: Apache-2.0, "open weights available for commercial use". La tarjeta no dice nada específico sobre los derechos de la salida. **El 9B es no comercial** | Sí, MLX nativo (port línea a línea); `-q 8`/cuantización; fp16 en M1 con `--compute-precision float16` | Rápido, edición con referencia. Menor adherencia a prompts largos que modelos de 12B+; sin medición propia | Prompt en inglés mejor; texto dentro de imagen poco fiable (supuesto) | web: https://github.com/filipstrand/mflux ; https://huggingface.co/black-forest-labs/FLUX.2-klein-4B (2026-11-01). Tiempos: tercero (lilting.ch), supuesto |
| 2 | **mflux + Z-Image Turbo (6B)** | local | 0 USD | 8 pasos; sin medición M4 Max (desconocido) | 25 a 35 | Pesos: Apache-2.0 (tarjeta HF). Repositorio: Apache-2.0 | Sí, comando `mflux-generate-z-image-turbo` en el README de mflux | Descrito por el propio README como rápido y muy bueno en realismo (autodescripción) | Inglés y chino | web: https://huggingface.co/Tongyi-MAI/Z-Image-Turbo ; https://github.com/Tongyi-MAI/Z-Image (2026-11-01) |
| 3 | **mflux + FLUX.1 schnell** | local | 0 USD | 10 a 15 s/imagen en M4 Pro 24 GB (tercero, sin método); 30 a 50 s en otro blog | 25 a 35 | Apache-2.0, "personal, científico y comercial"; la tarjeta no regula la salida; exige aceptar condiciones en HF con login (no verificado por mí) | Sí (mflux lo trata como opción heredada "legacy") | Calidad decente, heredada por FLUX.2 | Inglés | web: https://huggingface.co/black-forest-labs/FLUX.1-schnell ; tercero: https://itnext.io/generate-images-free-locally-on-your-mac-with-ai-312382bc7754 (resultado de búsqueda) |
| 4 | FLUX.1 dev / FLUX.2 klein 9B | local | 0 USD | más lento | 25 a 35 | **Licencia no comercial (FLUX Non-Commercial).** La tarjeta de dev dice que la salida puede usarse comercialmente "como describe la licencia", pero no reproduce el texto; no lo pude resolver. **No usar para un canal monetizado hasta leer LICENSE.md** | Sí | Mejor calidad que schnell | Inglés | web: https://huggingface.co/black-forest-labs/FLUX.1-dev (2026-11-01). Klein 9B no comercial: tercero (lilting.ch) |
| 5 | **Draw Things** (app y CLI) | local | 0 USD | similar a mflux, sin cifras verificadas | 25 a 35 | Repositorio comunitario GPL-3.0 (el código); la licencia de cada modelo es la del modelo. La app no la verifiqué | Sí, app nativa Metal; `draw-things-cli generate`; servidor gRPC | Buena para uso manual. Automatización por CLI menos documentada que mflux | Inglés | web: https://github.com/drawthingsai/draw-things-community (2026-11-01) |
| 6 | **ComfyUI en `mps`** | local | 0 USD | 10 a 15 s (schnell) y 30 a 50 s (dev) según blogs sin chip fijo | 30 a 40 (montar flujos, depurar) | ComfyUI: GPL-3.0 (supuesto, no verificado en esta investigación); modelos según cada uno | Sí, PyTorch MPS; consejos contradictorios sobre BF16/FP16 y VAE negro | Máxima flexibilidad (ControlNet, LoRA); más frágil en Mac y más trabajo humano de mantenimiento | Inglés | tercero: https://insiderllm.com/guides/stable-diffusion-mac-mlx/ (resultado de búsqueda) |
| 7 | Stable Diffusion 3.5 / SDXL (Stability AI Community License) | local | 0 USD si el ingreso anual es menor a 1 M USD | SDXL 1024 px ~37 s en M2 Max (Apple Core ML, tercero) | 25 a 35 | Comunidad: gratis comercial bajo 1 M USD de ingreso anual; usted posee las salidas "entre usted y Stability" | Sí (Core ML, Draw Things, ComfyUI) | Ecosistema grande de LoRA de estilo; calidad por debajo de FLUX.2 en texto y manos (supuesto) | Inglés | web: https://stability.ai/license (2026-11-01) |
| 8 | **Gemini Image (Nano Banana 2 / 2.1)** | API | 2.1: 0,0336 USD 1K, 0,0504 2K, 0,113 4K. NB2 (`3.1 Flash Image`): 0,067 USD 1K. Batch a la mitad. **Sin nivel gratis de API** para imágenes; AI Studio es gratis para pruebas manuales | red, ~5 a 15 s/imagen (supuesto) | 20 a 30 | Google no reclama la propiedad según fuentes secundarias; **términos oficiales no verificados**. Ficha del Foundry: licencia "no determinada" | n/a (API) | Medido: 0,067 USD/retrato, pero generó el logo real de L.L.Bean sin pedirlo. Imágenes llevan SynthID | Prompts multilingües | web: https://ai.google.dev/gemini-api/docs/pricing (2026-11-01). medido: `~/Foundries/david-foundry-core/tool-registry/gemini-image.md` (n pequeño). Marca de agua/derechos: tercero |
| 9 | **Figma AI images** | servicio dentro de Figma | créditos del plan, monto no medido | n/a | alto en revisión manual | No determinada | n/a | Medido en una sola ocasión (27 variantes); enlaces expiran a 7 días; no es producción | n/a | medido: `~/Foundries/david-foundry-core/tool-registry/figma-ai-images.md` |
| 10 | **Cloudflare Workers AI (FLUX.1 schnell)** | API | 10.000 neuronas/día gratis, luego 0,011 USD por 1.000. 512×512×4 pasos ≈ 43 neuronas, ~230 imágenes/día gratis (cálculo mío sobre cifras oficiales; imágenes de 1024 px consumen más) | red | 25 a 35 | Pesos Apache-2.0; términos de Cloudflare no revisados | n/a | Resolución baja por defecto: sirve para borradores | Inglés | web: https://developers.cloudflare.com/workers-ai/platform/pricing/ (2026-11-01). Requiere cuenta (no creada) |

#### 2.2 Generación de video IA

| # | Herramienta | Tipo | Costo | Límites | Min. humanos | Licencia/uso | Notas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|
| 11 | **Veo 3.1 Lite / Fast / Standard** (Gemini API) | API | Lite 0,05 USD/s (720p), 0,08 (1080p); Fast 0,10 / 0,12 / 0,30 (4K); Standard 0,40 / 0,60. Sin nivel gratis | por segundo de salida. Un video 100 % IA de 20 min = 60 a 144 USD en Lite/Fast, más descartes | 10 a 15 | No verificado oficialmente | La página oficial de precios que leí **no lista Veo**; cifras de terceros. Un tercero dice que los endpoints preview vencían el 2026-10-22: **verificar los IDs vigentes** | tercero: https://the-decoder.com/googles-veo-3-1-lite-cuts-video-generation-costs-by-more-than-half/ ; https://benchlm.ai/md/media-pricing/veo.md (2026-11-01) |
| 12 | Gemini Omni Flash (video) | API | ~0,10 USD/s (5.792 tokens de salida por s a 17,50 USD/M) | pago, sin gratis | 10 a 15 | No verificado | | web: https://ai.google.dev/gemini-api/docs/pricing (2026-11-01) |
| 13 | Kling, Runway Gen-4.5, Hailuo, Seedance (agregadores como fal.ai) | API | rango tercero 0,03 a 0,15 USD/s; Runway Gen-4.5 0,12 USD/s | créditos de prueba, no confirmados | 10 a 15 | No verificado | Los clips fallidos también consumen créditos | tercero: https://www.atlascloud.ai/blog/cheapest-ai-video-generation-api-2026 (2026-11-01) |
| 14 | **LTX-2.3 / Wan 2.2 en Mac (MLX)** | local | 0 USD | M1 Max 64 GB: LTX-2 ~7 min para 1,3 s; Wan 2.2 GGUF 82 min para 2 s (tercero). LTX-2.3 completo pesa ~66 GB (necesita ≥64 GB; justo en este Mac), cuantizado a 4 bits cabe en 32 GB. Sin cifra M4 Max verificada | 10 a 15 | Licencias de pesos **no verificadas** | Impracticable para más de 1 a 3 clips de pocos segundos por video | tercero: https://lilting.ch/en/articles/ltx2-wan22-mac-local-video-gen ; https://github.com/Blaizzy/mlx-video |
| 15 | Higgsfield (conector disponible en la sesión) | servicio | no leí precios | no autenticado, no se usó | | | Solo se menciona porque hay un conector; sin datos | no verificado |

#### 2.3 Footage, archivo y datos de dominio público o licencia libre

| # | Fuente | Licencia y uso comercial | API y límites | Notas y riesgos | Fuente (2026-11-01) |
|---|---|---|---|---|---|
| 16 | **Pexels** (foto y video) | Gratis para cualquier uso, se pueden modificar; atribución no obligatoria. Prohibido mostrar personas identificables de forma ofensiva, sugerir respaldo de personas o marcas, usar como marca | `GET https://api.pexels.com/v1/videos/search` (`size`, `orientation`, `per_page` hasta 80); 200 solicitudes/hora y 20.000/mes por defecto; subir el límite es gratis bajo petición. Exige enlace visible a Pexels si se muestra la búsqueda | Material genérico tipo stock: **repetitivo entre canales** (riesgo "inauténtico") | web: https://www.pexels.com/api/documentation/ ; https://www.pexels.com/license/ |
| 17 | **Pixabay** | Content License de Pixabay (API gratis). Atribución pedida solo al mostrar resultados | `GET https://pixabay.com/api/videos/`; 100 solicitudes/60 s por clave; caché obligatoria de 24 h; sin descargas masivas sistemáticas; sin hotlink permanente; URL completa (`imageURL`, `fullHDURL`) solo con acceso API completo aprobado | La licencia completa no se leyó, solo la página de API | web: https://pixabay.com/api/docs/ |
| 18 | **NASA Image and Video Library** | En general sin copyright de EE. UU.; la insignia/logotipo NASA no es dominio público; las personas identificables pueden requerir permiso (comercial); no sugerir respaldo; algunas imágenes son de terceros con copyright | API pública en images.nasa.gov (el PDF de la API no se pudo leer; autenticación y límites **no verificados**) | **Marcar las imágenes con copyright de terceros**. NASA no permite atribuir contenido generado por IA a NASA ni mostrar su insignia con imágenes generadas por IA | web: https://www.nasa.gov/nasa-brand-center/images-and-media/ |
| 19 | **NOAA Photo Library** | Imágenes en dominio público según NOAA; pide crédito a NOAA y al fotógrafo. Algunas en Flickr van en CC BY 2.0; imágenes de sitios de programas pueden tener permiso de terceros | API no verificada | Revisar cada imagen | tercero (búsqueda): https://photolib.noaa.gov/About ; https://www.noaa.gov/noaa-collections/photo-library |
| 20 | **Wikimedia Commons** | Licencias abiertas por archivo (CC BY, CC BY-SA, CC0, PD). CC BY exige crédito; **BY-SA exige compartir igual en obras derivadas** | API MediaWiki (no verificada en detalle); hay herramienta oficial para generar la atribución | Elegir solo PD/CC0/CC BY para evitar SA; verificar el estado de copyright de cada archivo | tercero (búsqueda): https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia |
| 21 | **Library of Congress (loc.gov)** | Cada ítem lleva su declaración de derechos; la categoría "Free to Use and Reuse" **no se verificó** | `loc.gov` JSON/YAML sin clave; **20 solicitudes/min, bloqueo de 1 hora si se excede**; puede haber CAPTCHA/429 | Muchos materiales tienen derechos no resueltos: leer la declaración | tercero (búsqueda): https://www.loc.gov/apis/json-and-yaml/working-within-limits/ |
| 22 | **Smithsonian Open Access** | Metadatos CC0; **solo los objetos de dominio público traen archivo de imagen**; los demás no | `https://api.si.edu/openaccess/api/v1.0/search`, requiere clave gratis de api.data.gov; volcado JSON semanal en GitHub | La documentación directa devolvió 403; datos desde la página de herramientas | tercero (búsqueda): https://www.si.edu/openaccess/devtools |
| 23 | **Europeana** | Declaraciones por objeto: libre con atribución (CC0, CC BY, CC BY-SA), con restricciones (CC BY-NC), solo con permiso | API con `wskey`; parámetro `reusability=open`; clave de demostración compartida y clave gratis registrada | La documentación oficial devolvió 403; datos por blog de Europeana y un envoltorio de terceros; registrar la clave **requiere crear cuenta (no hecho)** | tercero: https://pro.europeana.eu/blog/can-i-use-it |
| 24 | **Internet Archive** | Varía por ítem; tener acceso a la metadata no da derecho de reuso; campo de licencia por ítem | Advanced Search y Metadata sin clave; 100 ítems por página, ~10.000 resultados por consulta (tercero) | Prelinger y similares: verificar el ítem; no asumir dominio público | tercero (búsqueda): https://apify.com/lulzasaur/archive-org-scraper |

#### 2.4 Mapas, líneas de tiempo y animación simple

| # | Herramienta | Tipo | Costo | Licencia | Notas | Fuente (2026-11-01) |
|---|---|---|---|---|---|---|
| 25 | **Natural Earth** (datos) | local | 0 USD | Dominio público, uso comercial permitido sin atribución; algunos componentes son de terceros con licencia propia a Natural Earth | Base ideal para mapas animados con Python/ffmpeg | web: https://www.naturalearthdata.com/about/terms-of-use/ |
| 26 | **OpenStreetMap** (datos) | local/API | 0 USD | ODbL: atribución obligatoria; obras derivadas bajo la misma licencia; **OSM no ofrece tiles gratis a terceros** | Usar datos descargados, no tiles públicos | web: https://www.openstreetmap.org/copyright |
| 27 | **Remotion** (video por código React) | local | 0 USD si individuo, no lucrativa o empresa lucrativa de **3 o menos empleados**; Creators 25 USD/asiento/mes | licencia propia (no OSI) | Líneas de tiempo y gráficos reproducibles; licencia cambia en Remotion 5.0 | tercero (búsqueda): https://www.remotion.dev/docs/pricing (el texto de licencia no se pudo leer en la página) |
| 28 | **ffmpeg (zoompan) / Manim** | local | 0 USD | licencias no verificadas aquí (ffmpeg LGPL/GPL, Manim MIT, según mi conocimiento previo; **no verificado hoy**) | Ken Burns sobre stills y animación 2D programática | supuesto |

---

### 3. Fichas de las recomendadas

#### 3.1 mflux + FLUX.2 klein 4B (nivel A, stills)
- **Qué es:** port MLX de modelos de difusión; MIT. README: `uv tool install --upgrade mflux`; CLI como `mflux-generate-flux2 ... -q 8`; API Python `generate_image(prompt, seed, num_inference_steps, width, height)`. Fuente: https://github.com/filipstrand/mflux.
- **Integración:** un script que lea las escenas del guion (JSON), construya el prompt = bloque de estilo fijo + descripción de escena + semilla derivada de la escena, y genere en lote nocturno. Reanudable: saltar archivos existentes.
- **Límites:** sin medición propia en M4 Max; el nombre exacto del comando cambió entre versiones (un tercero menciona que la ruta genérica falló y requirió `mflux-generate-flux2`); requiere mflux ≥ 0.16.0 según una tarjeta de terceros. Descargar pesos requiere cuenta/aceptación en Hugging Face (no hecho aquí).
- **Riesgos:** la licencia Apache-2.0 cubre los pesos, no garantiza que el modelo no reproduzca marcas, rostros o estilos de artistas; la revisión humana sigue siendo necesaria.

#### 3.2 Gemini Image por API (nivel B, ya en el stack)
- **Qué es:** HTTP directo, sin SDK, medido en `canal-historias`. Pasar de `3.1 Flash Image` (0,067 USD) a `Nano Banana 2.1` (0,0336 USD) reduciría el costo a la mitad según la tabla oficial; **no probado**.
- **Integración:** misma que arriba, con el costo parcial contabilizado si falla (defecto ya corregido en el canal).
- **Límites:** el costo no se puede estimar antes de la llamada (medido); sin nivel gratis de API; Gemini 2.5 Flash Image se retira el 2027-03-15 (web).
- **Riesgos:** logos reales; SynthID (marca invisible) significa que YouTube puede etiquetar el contenido aunque el creador no lo declare (ver 4); términos de salida sin verificar en fuente oficial.

#### 3.3 Archivo libre con API (Pexels, Smithsonian, Wikimedia, NASA, LoC, Internet Archive)
- **Qué es:** un módulo de búsqueda que, por escena, consulta 3 a 4 fuentes, filtra por licencia (solo CC0/PD/CC BY o equivalentes), descarga y escribe una **hoja de atribuciones** con URL, licencia y fecha.
- **Automatiza:** búsqueda y ranking por palabras clave; **no automatiza** el juicio de relevancia ni la confirmación de derechos de personas retratadas (minutos humanos).
- **Límites:** Pexels 200/hora y 20.000/mes; LoC 20/min con bloqueo de 1 h; Pixabay caché 24 h.
- **Riesgos:** material de stock repetido entre canales; ítems "de dominio público" con derechos de terceros en NASA y NOAA.

#### 3.4 Veo 3.1 Lite/Fast (nivel C, clips IA)
- Solo para planos imposibles de cubrir (reconstrucciones animadas, movimiento). Presupuestar con tope por video (por ejemplo, 2 min = 6 a 14 USD en Lite/Fast sin descartes). Confirmar IDs de modelo vigentes antes de integrar.

---

### 4. Riesgos de política y de derechos

1. **Contenido inauténtico (YouTube Partner Program).** YouTube renombró la política el 2025-07-15; el contenido repetitivo o de plantilla no es monetizable; cada video debe tener historia y enfoque propios. Permite explícitamente usar IA para "visualizar un personaje original y una historia". No permite "clips IA pegados sin historia coherente" ni visuales engañosos (por ejemplo, desastres falsos). Fuente: https://support.google.com/youtube/answer/1311392 (2026-11-01). Implicación: 150 stills con el mismo estilo y una narración con aporte humano (investigación, guion, criterio) está en el lado permitido; lo que expone al canal es la **uniformidad de plantilla** y la falta de aporte humano verificable.
2. **Divulgación de contenido alterado o sintético.** Obligatoria para contenido **realista** (persona que parece decir o hacer lo que no hizo, evento o lugar real alterado, escena realista que no ocurrió). No necesaria para contenido claramente irreal o animado. YouTube puede aplicar la etiqueta automáticamente (herramientas propias, metadatos C2PA, detección); falta repetida de divulgación puede llevar a eliminación o suspensión del YPP. Fuente: https://support.google.com/youtube/answer/14328491 (2026-11-01). Implicación: **un estilo claramente ilustrado reduce la obligación de marcar; reconstrucciones fotorrealistas de hechos reales históricos sí la activan.** Regla propuesta (supuesto): marcar "Sí" siempre que haya imagen fotorrealista de personas o eventos reales reconstruidos, y registrar la decisión por video.
3. **Personas IA en temas sensibles** (salud, legal, finanzas, política) no son monetizables según la misma política; no se aplica a narración sin rostro si no se presenta como experto humano, pero conviene no sugerir un presentador humano.
4. **Derechos de autor de lo generado.** La Oficina de Derechos de Autor de EE. UU. (informe Parte 2, 2025-01-29) concluyó que los prompts solos no bastan para ser autor; sí protege la selección, la disposición y las modificaciones humanas creativas. Fuente: comentarios de despachos (tercero), no el informe, que no pude leer: https://www.ballardspahr.com/insights/alerts-and-articles/2025/01/copyright-office-issues-report-on-copyrightability-of-ai-content. Implicación: **las imágenes del canal pueden no ser protegibles**; otros pueden copiarlas.
5. **Marcas y rostros en salidas de modelos.** Medido: Gemini generó el logo de L.L.Bean. Mantener lista de revisión y el filtro humano.
6. **Licencias de pesos.** Evitar FLUX.1 dev y FLUX.2 klein 9B (no comerciales). Preferir Apache-2.0 (klein 4B, schnell, Z-Image). Stability Community: gratis solo bajo 1 M USD de ingresos.
7. **Footage y archivo:** NASA (logos, personas, terceros), Pexels (personas identificables en mala luz), Wikimedia BY-SA (compartir igual), OSM (ODbL), LoC e Internet Archive (derechos por ítem). Guardar la hoja de atribuciones por video.
8. **Política de NASA sobre IA:** no mostrar su insignia con imágenes generadas ni atribuirle contenido generado.
9. **Marca de agua SynthID y visibilidad de la etiqueta:** quitarla puede violar los términos (tercero, conflictivo).

---

### 5. Comparación con lo medido por el propietario y qué falta medir

**Lo medido (n pequeño, un canal):** Gemini Image 0,067 USD por retrato; defecto del logo real; costo parcial perdido en fallos; Figma AI con enlaces que expiran a 7 días; las miniaturas se componen con Pillow y una biblioteca de rostros, no con IA. Nada medido para imágenes de escena, local ni video.

**Contraste:** el stack actual usa IA de pago solo en retratos (unas pocas imágenes). Este informe plantea 150 imágenes por video: a 0,067 USD son ~10 USD/video; es barato en dinero pero multiplica la revisión humana por ~30.

**Experimentos baratos que puede correr el propietario (no los ejecuté):**
1. **Consistencia (1 h).** Un guion corto de 20 escenas; generar con (a) FLUX.2 klein 4B local y (b) Nano Banana 2.1, mismo bloque de estilo y semillas fijas; pedir a 3 personas que digan cuáles parecen del mismo video. Mide si el estilo se sostiene.
2. **Tiempo real en M4 Max (15 min).** Cronometrar 10 imágenes 1024 px con `mflux-generate-flux2` a 4 pasos, `-q 8`, y con Z-Image Turbo. Reemplaza mi supuesto de 25 a 40 s.
3. **Minutos de revisión (30 min).** Revisar una cuadrícula de contactos de 150 imágenes cronometrando; contar cuántas se descartan y cuántas traen marcas o texto defectuoso.
4. **Costo real Nano Banana 2.1 (5 min).** 20 imágenes en la API y leer los tokens reportados.
5. **Ken Burns (30 min).** Probar `ffmpeg zoompan` sobre 10 stills y mirar si el movimiento se siente "de plantilla" (riesgo de inauténtico).
6. **Etiqueta de YouTube (1 video no listado).** Subir con "AI use = No" un video con estilo ilustrado y ver si YouTube aplica la etiqueta automática (SynthID/C2PA).

---

### 6. Unknowns

1. **Tiempo por imagen en M4 Max** con mflux/FLUX.2 klein 4B y Z-Image: no hay medición verificada (solo M1 Max, tercero).
2. **Términos oficiales de uso comercial de la salida de Gemini Image** y de los pesos Qwen/FLUX en el flujo completo: no los leí en fuente oficial; la ficha del Foundry también dice "no determinada".
3. **Precios y vigencia de Veo 3.1** en la página oficial de Google (no está en la página que leí; terceros se contradicen: 0,05 a 0,12 vs 0,75 USD/s; un tercero apunta a vencimiento de endpoints preview el 2026-10-22).
4. Autenticación y límites de la API de NASA, de la API de Wikimedia, y la categoría "Free to Use and Reuse" de la LoC.
5. Documentación oficial de Europeana y Smithsonian (devolvieron 403); datos por terceros.
6. Licencias de ffmpeg, Manim y ComfyUI, y de pesos Wan/LTX: no verificadas hoy.
7. Si YouTube etiqueta automáticamente imágenes con SynthID de la API de Gemini, y cómo afecta a un canal con estilo ilustrado.
8. Texto completo de la licencia FLUX.1 dev (LICENSE.md) sobre salidas comerciales; no leído.
9. Texto del informe de la Oficina de Derechos de Autor: solo comentarios de terceros.
10. Pesos de HF requieren aceptar condiciones con login (FLUX.1 schnell); no se hizo.

### Tabla de fuentes (acceso 2026-11-01)

| Tema | URL | Tipo |
|---|---|---|
| mflux (modelos, licencia MIT, CLI) | https://github.com/filipstrand/mflux | web |
| FLUX.1 schnell | https://huggingface.co/black-forest-labs/FLUX.1-schnell | web |
| FLUX.1 dev | https://huggingface.co/black-forest-labs/FLUX.1-dev | web |
| FLUX.2 klein 4B | https://huggingface.co/black-forest-labs/FLUX.2-klein-4B | web |
| Z-Image Turbo | https://huggingface.co/Tongyi-MAI/Z-Image-Turbo | web |
| Z-Image repositorio | https://github.com/Tongyi-MAI/Z-Image | web |
| Draw Things comunitario | https://github.com/drawthingsai/draw-things-community | web |
| Stability AI Community License | https://stability.ai/license | web |
| Gemini API precios | https://ai.google.dev/gemini-api/docs/pricing | web |
| Cloudflare Workers AI precios | https://developers.cloudflare.com/workers-ai/platform/pricing/ | web |
| YouTube divulgación de contenido sintético | https://support.google.com/youtube/answer/14328491 | web |
| YouTube contenido inauténtico y reutilizado | https://support.google.com/youtube/answer/1311392 | web |
| Pexels API | https://www.pexels.com/api/documentation/ | web |
| Pexels licencia | https://www.pexels.com/license/ | web |
| Pixabay API | https://pixabay.com/api/docs/ | web |
| NASA uso de medios | https://www.nasa.gov/nasa-brand-center/images-and-media/ | web |
| Natural Earth | https://www.naturalearthdata.com/about/terms-of-use/ | web |
| OpenStreetMap copyright | https://www.openstreetmap.org/copyright | web |
| LoC límites | https://www.loc.gov/apis/json-and-yaml/working-within-limits/ | tercero (búsqueda) |
| Smithsonian herramientas | https://www.si.edu/openaccess/devtools | tercero (búsqueda) |
| Europeana reusabilidad | https://pro.europeana.eu/blog/can-i-use-it | tercero |
| Wikimedia Commons reutilización | https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia | tercero (búsqueda) |
| NOAA Photo Library | https://photolib.noaa.gov/About | tercero (búsqueda) |
| Internet Archive (APIs) | https://apify.com/lulzasaur/archive-org-scraper | tercero |
| Veo 3.1 precios | https://the-decoder.com/googles-veo-3-1-lite-cuts-video-generation-costs-by-more-than-half/ ; https://benchlm.ai/md/media-pricing/veo.md | tercero |
| Precios de video IA (agregadores) | https://www.atlascloud.ai/blog/cheapest-ai-video-generation-api-2026 | tercero |
| Video local en Mac | https://lilting.ch/en/articles/ltx2-wan22-mac-local-video-gen ; https://github.com/Blaizzy/mlx-video | tercero |
| FLUX.2 en Mac | https://lilting.ch/en/articles/flux2-klein-4b-mflux-iris-m1-max | tercero |
| ComfyUI/MPS | https://insiderllm.com/guides/stable-diffusion-mac-mlx/ | tercero |
| Oficina de Derechos de Autor Parte 2 | https://www.ballardspahr.com/insights/alerts-and-articles/2025/01/copyright-office-issues-report-on-copyrightability-of-ai-content | tercero |
| Remotion precios | https://www.remotion.dev/docs/pricing | tercero (búsqueda) |
| Gemini y SynthID | https://terms.law/ai-output-rights/gemini/ | tercero |
| Foundry: gemini-image, figma-ai-images, thumbnails-packaging | `~/Foundries/david-foundry-core/tool-registry/*.md`, `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md` | medido |


---

# Parte 4

## Etapa 04: Edición y render automatizado

Fecha de consulta: 2026-11-01. Alcance: ensamblar audio de narración + imágenes/clips + subtítulos + música en un video final (1080p/4K) por código, sin editar a mano, para videos de ~4.700 palabras (18 a 28 min) en un Mac M4 Max de 64 GB.

Tipos de dato: **medido** (corrida real; aquí solo hay una prueba sintética mía, ver sección 5), **web** (leído en fuente, con URL y fecha; caduca a 90 días), **tercero**, **supuesto**.

---

### 1. Resumen y recomendación

La etapa es **automatizable al 100 % con ffmpeg** (cero herramientas de pago). El trabajo real no está en el render sino en generar el *plan de edición* (qué imagen va en qué segundo, qué zoom, qué subtítulo), que sale de los tiempos por palabra que ya produce WhisperX.

| Nivel | Recomendación | Por qué | Dinero | Tiempo de máquina / video de 20 min (supuesto, ver §5) | Minutos humanos / video |
|---|---|---|---|---|---|
| **A: gratis y local** | **ffmpeg** (CLI, invocado desde Python con `subprocess`), con `h264_videotoolbox` o `libx264`, filtros `zoompan`, `xfade`, `subtitles` (libass), `amix`/`sidechaincompress`, y `.srt` aparte | Ya instalado en el Mac (v9.0.1, con VideoToolbox, libass y freetype: **medido** localmente); determinista; sin licencia de uso por seat; es la base de casi todas las demás herramientas | 0 USD | ~3 a 15 min (ver §5) | **1 a 3** (ver el video, revisar 2 o 3 puntos) |
| **A2: alternativa local con más expresividad** | **MoviePy 2.x** (Python) para prototipar composiciones y **Editly** (Node) si se quiere JSON declarativo con Ken Burns/transiciones GL | MoviePy: API Python nativa, MIT; Editly: Ken Burns y transiciones listos, MIT. Ambos son capas sobre ffmpeg | 0 USD | MoviePy es más lento que ffmpeg directo (la propia documentación lo dice) | 2 a 5 |
| **B: gratis con límites / bajo costo** | **Shotstack** (API, pago por uso) solo si se quiere render en nube y 0 mantenimiento; **Remotion** si se necesitan lower thirds/gráficos complejos en React (gratis para ≤3 personas) | El Mac ya es más barato que cualquier API para video largo; B solo tiene sentido para gráficos animados (Remotion) | Shotstack ~0,10 a 0,20 USD/min renderizado ⇒ ~2 a 4 USD por video de 20 min (web); Remotion 0 USD si el equipo ≤3 | Remotion en local: no medido, mayor que ffmpeg (renderiza con Chromium) | 2 a 5 |
| **C: pago** | **DaVinci Resolve Studio** (236 USD una vez) con scripting Python, o Creatomate/Shotstack a escala | Solo si aparece la necesidad de corrección de color, ruido, o plantillas visuales editables por un humano. No reduce minutos humanos frente a A | 236 USD (web) / suscripción | Resolve renderiza por hardware; no medido | 5 a 15 (se abre la GUI) |

**Cuántos minutos humanos contar:** **2 minutos por video** en el flujo recomendado (visionado rápido de verificación). Esto es un **supuesto**: nadie lo midió en el canal. Con presupuesto prudente, contar 3.

**Qué automatiza la etapa:** concatenación de escenas a partir de un manifiesto (JSON) con duraciones derivadas del audio; Ken Burns por imagen; transiciones; mezcla de música con ducking bajo la voz; normalización de loudness; subtítulos incrustados y `.srt`; codificación final.

---

### 2. Catálogo de candidatos

Columnas: tipo | dinero | tiempo de máquina | minutos humanos | licencia / uso comercial | Apple Silicon | calidad y defectos | idiomas | tipo de dato | fuente.

| # | Herramienta | Tipo | Dinero | Tiempo de máquina | Min. humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Tipo de dato | Fuente (acceso 2026-11-01) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **ffmpeg** | Local (CLI) | 0 | 60 s de 1080p30 con zoompan ≈ 9,5 s (⇒ ~3 min por 20 min, **supuesto** de extrapolación) | 1 a 3 | LGPL 2.1+; partes GPL si se activan (libx264 y libx265 son GPL). No ofrece licencia comercial distinta. La página **no dice** nada sobre obligaciones de los archivos de salida; su preocupación comercial son las patentes (H.264/HEVC). | Sí: binario nativo `arm64` (Homebrew), con `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox` | Control total. Curva de aprendizaje de filtergraph; `zoompan` tiene temblor (jitter) si no se hace escalado previo ×4 (conocido en la comunidad, **tercero**, sin fuente propia aquí). | N/A | licencia: web; rendimiento: medido (sintético) | https://ffmpeg.org/legal.html |
| 2 | **MoviePy 2.x** | Local (librería Python) | 0 | Más lento que ffmpeg directo (convierte cuadros a numpy) | 2 a 5 | MIT | Sí (Python 3.9+, usa ffmpeg) | v2.0 con cambios incompatibles; v1 sin mantenimiento. Lento en videos largos y consume memoria | N/A | web | https://github.com/Zulko/moviepy |
| 3 | **Editly** | Local (CLI/Node, JSON) | 0 | No medido | 2 a 5 | MIT | Requiere Node y ffmpeg; soporte Apple Silicon por `headless-gl`: **no verificado** | Ken Burns (`zoomDirection`, `zoomAmount` 0,1), transiciones gl-transitions (0,5 s por defecto), capas `title`, `subtitle`, `news-title`. Mantenido por una sola persona; 73 issues abiertos | N/A | web | https://github.com/mifi/editly |
| 4 | **Remotion** | Local (React/Node, Chromium) o nube (Lambda) | Gratis para individuos, ≤3 empleados con fines de lucro, y sin fines de lucro; Automators 0,01 USD/render con mínimo 100 USD/mes; Creators 25 USD/seat/mes; Enterprise mínimo 500 USD/mes | No medido (renderiza cuadro a cuadro con navegador; más lento que ffmpeg) | 3 a 8 (hay que escribir componentes React una vez) | **Licencia propia, no OSI**: gratis hasta 3 personas; más allá exige Company License | Sí en teoría (Node/Chromium arm64); no medido por mí | Mejor opción para lower thirds, gráficos animados y plantillas. Exige conocimiento de React | N/A | web (licencia: GitHub LICENSE.md; precios: búsqueda con páginas oficiales de remotion.dev) | https://github.com/remotion-dev/remotion/blob/main/LICENSE.md ; https://www.remotion.dev/docs/license/pricing (widget de precios no cargó; cifras del resumen de búsqueda sobre remotion.dev) |
| 5 | **Motion Canvas** | Local (TypeScript, navegador/Vite) | 0 | No medido | 3 a 8 | MIT (también su exportador FFmpeg) | Navegador + ffmpeg; no verificado en detalle | Animación vectorial/diagramas, no ensamblador de clips largos. Solo renderiza contenido canvas | N/A | tercero (alternativeto, comparación de Remotion) | https://github.com/motion-canvas/exporters ; https://www.remotion.dev/docs/compare/motion-canvas |
| 6 | **auto-editor** | Local (CLI en Nim) | 0 | Rápido (cortes por silencio) | 1 a 2 | Dominio público (Unlicense) en el repositorio; binarios pueden usar otras licencias | No verificado | Sirve para **cortar silencios en audio grabado**, no para ensamblar narración sintética sin silencios. Exporta a Premiere, Resolve, Final Cut, Shotcut. Poca utilidad en este canal | N/A | web | https://github.com/WyattBlue/auto-editor |
| 7 | **MLT / melt / Shotcut / Kdenlive** | Local (framework C, CLI `melt`, bindings Python, XML) | 0 | No medido | 3 a 6 | Paquetes Alpine indican GPL-2.0+, LGPL-2.1+ y GPL-3.0+ (mezcla por componente). Licencia exacta por componente: **no verificada** en el repositorio | Existen builds de Shotcut para macOS; rendimiento arm64 no verificado | Proyecto XML editable a mano o por script y abrible en Shotcut para retoque (ventaja híbrida). Documentación menos extensa que ffmpeg | N/A | tercero | https://pkgs.alpinelinux.org/package/edge/community/x86_64/py3-mlt |
| 8 | **DaVinci Resolve (Free)** | Local GUI | 0 | Render por hardware | 10 a 20 (manual) | Licencia propietaria de Blackmagic; términos de uso comercial **no verificados** aquí | Sí (nativo) | Gratis hasta UHD 3840×2160 a 60 fps y 8 bits. **Scripting externo no disponible** en Free según hilo del foro oficial (2020, Resolve 16); scripts desde el menú pueden funcionar (fuente de tercero, no confirmado) | N/A | web (página oficial) + tercero (scripting) | https://www.blackmagicdesign.com/products/davinciresolve ; https://forum.blackmagicdesign.com/viewtopic.php?p=670352 |
| 9 | **DaVinci Resolve Studio** | Local GUI + API Python (scripting externo) | 236 USD una vez (precio con descuento sobre 295 USD) | Render por hardware | 5 a 15 | Propietaria; pago único | Sí | Scripting Python/Lua externo es **solo Studio** (tercero). Añade 10 bits, >UHD, 120 fps, IA | N/A | web (precio) + tercero (scripting) | https://www.blackmagicdesign.com/products/davinciresolve ; https://thepostflow.com/post-production/video-editing/resolve-studio-vs-free/ |
| 10 | **Blender VSE** | Local (Python `bpy`) | 0 | No medido | 4 a 8 | GPL (conocimiento general; **no verificado** en esta investigación) | Sí (nativo, Metal) | Posible por scripting `bpy`, pero la API del secuenciador es poco ergonómica y el binario pesado. Sin ventajas sobre ffmpeg para este uso | N/A | supuesto | n/d |
| 11 | **Shotstack** | API (nube) | Sandbox gratis con 10 créditos y 30 días de validez; pago por uso 10 USD por 50 min (0,20 USD/min); Starter 39 USD/mes (250 min, 1080p); Pro 99 USD/mes (750 min, 4K); Scale 199 USD/mes (2.000 min, 4K) | Render remoto (minutos) | 2 a 4 (plantilla JSON, subida de activos) | Servicio comercial; términos de contenido **no verificados** | N/A (nube) | Salida en sandbox con marca de agua (comunidad Shotstack). 20 min de video ≈ 2 a 4 USD. Hay que subir audio e imágenes a una URL accesible | N/A | web | https://shotstack.io/pricing/ ; https://community.shotstack.io/t/how-to-remove-the-shotstack-watermark-logo-from-the-video/540 |
| 12 | **Creatomate** | API (nube) | Prueba gratis con 50 créditos sin tarjeta; planes Essential (2.000 créditos), Growth (10.000 a 40.000), Beyond (50.000 a 200.000). **Precios mensuales no leídos** en la página oficial (contradicciones entre agregadores: Essential 29 o 54 USD/mes) | Render remoto | 2 a 4 | Servicio comercial | N/A | Alrededor de 14 créditos por minuto de 720p y ~37 por minuto de 1080p30 (tercero) ⇒ un video de 20 min consumiría ~740 créditos: el plan básico alcanza para ~2 videos al mes (**supuesto** derivado de cifra de tercero). Poco adecuado para video largo | N/A | web (estructura) + tercero (consumo) | https://creatomate.com/pricing ; https://creatomate.com/docs/account/how-are-credits-calculated |
| 13 | **CapCut** | GUI (escritorio/móvil) | Plan gratis con limitaciones; condiciones comerciales y de exportación 4K **no verificadas** (la página de términos devolvió 404) | Local | 15 a 40 (manual) | **No verificada** | Sí (app nativa) | Sin API pública de automatización verificada. No cumple el requisito de edición por código | N/A | no verificado | https://www.capcut.com/clause/commercial-use (404) |

---

### 3. Fichas breves

#### ffmpeg (recomendada nivel A)
- **Qué es:** el estándar de facto para codificar y filtrar video. Versión local verificada: 9.0.1, compilado con `--enable-libass` y `--enable-libfreetype`, con codificadores `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox`, `libx264`, `libx265` y filtros `zoompan`, `xfade`, `subtitles`, `ass`, `drawtext` (comando `ffmpeg -encoders/-filters` ejecutado en el Mac del propietario, 2026-11-01: **medido**).
- **Integración Python:** `subprocess.run([...])` con un grafo de filtros generado desde un manifiesto JSON (`escenas: [{imagen, inicio, duración, zoom}]`), o la librería `ffmpeg-python` (**no verificada** su mantenimiento). Un solo comando puede: encadenar imágenes con `zoompan` + `xfade`, mezclar la narración con música usando `sidechaincompress`, normalizar con `loudnorm` (el stack de voz ya normaliza a −14 LUFS) e incrustar subtítulos.
- **Efectos:** Ken Burns con `zoompan`; transiciones con `xfade`; lower thirds simples con `drawtext`/`drawbox` o superponiendo un PNG con `overlay`. Los lower thirds animados complejos no son cómodos aquí: usar Remotion o prerenderizar un clip con canal alfa.
- **Subtítulos:**
  - *Incrustados (burn-in):* filtro `subtitles=archivo.srt:force_style=...` o `ass=archivo.ass` (libass). Para estilo "palabra a palabra" conviene generar un `.ass` a partir de los tiempos de WhisperX.
  - *Archivo `.srt` aparte:* se genera desde el mismo alineamiento y se sube a YouTube como pista de subtítulos. Esto es lo recomendable por defecto: YouTube permite activarlos/desactivarlos y el texto es indexable. Incrustarlos solo si se quiere el estilo visual fijo.
- **Calidad y bitrate (medido sintético):** `h264_videotoolbox -b:v 12M` produjo ~90 MB por 60 s de 1080p30 sobre una carta de ajuste muy detallada (≈12 Mb/s, es decir, el bitrate pedido); `libx264 -crf 18` produjo ~75 MB sobre el mismo origen. Para contenido real de imágenes quietas con zoom, el tamaño será muy inferior (el mismo origen estático con zoompan salió en ~1 MB con libx264 CRF 18 por 60 s, **medido**, aunque un fotograma sintético plano no es representativo).
- **Límites:** `zoompan` es de un solo hilo; videotoolbox ofrece menos eficiencia por bit que libx264/libx265 (conocimiento general, **sin fuente aquí**); H.264/HEVC conllevan cuestiones de patentes (ver licencia).
- **Riesgos:** filtergraphs largos son difíciles de depurar; conviene renderizar por escenas y concatenar.

#### MoviePy 2.x (A2)
Librería Python (MIT) para componer clips, texto y audio. Buena para prototipar y para efectos programados cuadro a cuadro. Más lenta y con más memoria que ffmpeg directo. Riesgo: la ruptura entre v1 y v2 hace que los ejemplos de internet fallen.

#### Editly (A2)
Define el video en JSON (capas `image`, `title`, `subtitle`, transiciones). Cubre Ken Burns y transiciones sin escribir filtergraphs. Riesgo: mantenimiento por una persona y dependencia de `headless-gl`, que puede dar problemas de compilación en macOS (no verificado).

#### Remotion (B, solo si hacen falta gráficos)
Video como componentes React; gratis para ≤3 personas. Útil si el canal necesita lower thirds, contadores o gráficos con marca. Hay que contar el coste de escribir y mantener código React y que renderiza con Chromium.

#### Shotstack (B, nube)
API JSON de edición con sandbox gratuito y marca de agua. Calcula ~0,10 a 0,20 USD/min; un video de 20 min cuesta 2 a 4 USD **solo en render**. No aporta nada que el Mac no haga gratis; su valor es no depender de la máquina.

#### DaVinci Resolve Studio (C)
Solo si se quiere corrección de color y limpieza y se acepta pagar 236 USD. El scripting externo en Python exige Studio (tercero). No reduce minutos humanos frente a ffmpeg y añade dependencia de GUI.

---

### 4. Riesgos de política y de derechos

- **Contenido inauténtico (monetización):** YouTube renombró la política "repetitious content" a "inauthentic content" el 15 de julio de 2025. Señala como problema el contenido que "looks like it's made with a template", presentaciones de imágenes con poca narrativa o valor, y contenido con IA genérica con apariencia de producción en masa. **Permite** repetir intro/outro si la mayor parte del contenido es distinta, y series con elementos recurrentes si cada video tiene historia propia. Implicación para esta etapa: un montaje 100 % idéntico (mismo Ken Burns, misma transición, mismas imágenes de archivo) en cada video es exactamente la señal de "plantilla". **Mitigación:** variar zoom/dirección/ritmo por escena, asegurar que las imágenes sean relevantes al guion, y que el valor original esté en la narración. Fuente: https://support.google.com/youtube/answer/1311392 (acceso 2026-11-01).
- **Divulgación de contenido alterado o sintético:** no verificada en esta etapa (corresponde a las etapas de voz e imagen); se indica aquí por completitud.
- **Música:** la mezcla automatizada exige que la pista tenga licencia comercial. Esta etapa solo la ensambla; el catálogo de música debería tratarse en su propia etapa. **No verificado.**
- **Patentes de códecs:** ffmpeg advierte que H.264/HEVC pueden tener tasas de patentes para quien distribuye productos comerciales (https://ffmpeg.org/legal.html). Subir videos a YouTube no es distribuir un codificador; riesgo bajo, pero no es asesoría legal.
- **Licencia de Remotion:** si el equipo pasa de 3 personas con fines de lucro, exige Company License (mínimo 100 USD/mes en Automators).
- **Marca de agua en sandbox de APIs:** no usar sandbox de Shotstack para videos publicables.

---

### 5. Comparación con lo que ya mide el propietario y qué falta medir

**Lo que ya existe (Foundry):** `voice-narration.md` menciona ffmpeg como pieza del stack de voz (compresor, normalización a −14 ± 1 LUFS, `atempo` 0,90) y lo marca "aún sin ficha en el registro" (`~/Foundries/david-youtube-foundry/stacks/voice-narration.md`). WhisperX ya entrega la alineación palabra a palabra sobre el guion (`tool-registry/whisperx.md`), que es exactamente la entrada para generar `.srt`/`.ass` y para cronometrar escenas. No hay ficha de edición ni de render en el registro: esta etapa no tiene dato `medido` del propietario.

**Mi prueba sintética (única corrida de esta investigación; no es del canal):** ejecuté ffmpeg local en el M4 Max con orígenes sintéticos (`testsrc2` y una imagen 4K generada), sin instalar nada, y borré los archivos temporales después. Resultados (**medido**, n = 1 por caso, orígenes no representativos):

| Caso | Duración de salida | Tiempo de pared |
|---|---|---|
| Imagen 4K estática, `zoompan` a 1080p30, `libx264 -preset medium -crf 18` | 60 s | 9,7 s |
| Lo mismo, `h264_videotoolbox -b:v 12M` | 60 s | 9,2 s |
| `testsrc2` 1080p30 a `h264_videotoolbox -b:v 12M` | 60 s | 4,1 s |
| `testsrc2` 1080p30 a `libx264 -crf 18` | 60 s | 4,2 s |
| `testsrc2` 4K30 a `hevc_videotoolbox -b:v 30M` | 30 s | 8,1 s |
| Quemar subtítulos con `subtitles=` y `h264_videotoolbox` | 60 s | 4,1 s |

Lectura: con `zoompan` el cuello de botella es el filtro (un hilo), no el codificador, por lo que videotoolbox no mejoró el tiempo (9,2 frente a 9,7 s). Extrapolación lineal a 20 min: **~3 min** con Ken Burns en 1080p (60 s ⇒ ~9,5 s ⇒ 1.200 s ⇒ ~190 s), **~1,5 min** para solo codificar 1080p. Es un **supuesto**: el contenido real (escenas con `xfade`, varias imágenes en alta resolución, mezcla de audio) será más lento. El rango razonable es **3 a 15 min** por video de 20 min.

**Experimentos baratos que el propietario puede correr:**
1. Con 20 imágenes reales (2K a 4K) y la narración de un video ya producido, construir un manifiesto JSON y un script Python que genere un filtergraph con `zoompan` + `xfade` + `subtitles`; cronometrar el video completo con `libx264` frente a `h264_videotoolbox`.
2. Comparar calidad visual y tamaño: `libx264 -crf 18/20`, `h264_videotoolbox -b:v 8M/12M/16M` y `hevc_videotoolbox`; subir un fragmento a YouTube privado y comparar tras su recodificación.
3. Probar un `.srt` generado desde WhisperX: subtítulo incrustado (`subtitles`) frente a pista subida a YouTube.
4. Mezclar música con `sidechaincompress` y verificar −14 ± 1 LUFS final con `loudnorm`.
5. Si se necesitan lower thirds: prerenderizar uno con Remotion (licencia gratuita para ≤3 personas) o con `drawtext` y comparar el esfuerzo.
6. Medir **minutos humanos reales** de revisión en 3 videos (el 2 por video del resumen es supuesto).

---

### 6. Unknowns

1. **Rendimiento real** con escenas reales (20 min, ~100 imágenes, `xfade`, música): solo hay datos sintéticos.
2. **Calidad por bitrate de `h264_videotoolbox`** frente a `libx264` en contenido real; y cuál bitrate acepta YouTube sin degradar (no leí la recomendación oficial de bitrate de YouTube en esta investigación).
3. **Soporte de Editly/headless-gl y Remotion en arm64** y tiempos de render de ambos: no verificados.
4. **Precio mensual exacto de Creatomate** (la página oficial no mostró importes) y **precios de Remotion** (el widget oficial no cargó; cifras de un resumen de búsqueda sobre remotion.dev).
5. **Licencia de Blender, Kdenlive/Shotcut y MLT por componente**, y términos comerciales de CapCut y Resolve Free: no verificados.
6. **Scripting de Resolve Free** desde el menú: fuentes contradictorias.
7. **Licencia de música** y **política de divulgación de contenido sintético** en el montaje final: fuera del alcance de esta etapa pero necesarias antes de publicar.
8. Si YouTube considera "plantilla" un montaje con variación mínima de Ken Burns: no hay evidencia cuantitativa.

---

### Tabla de fuentes

| Fuente | Dato | Tipo | Acceso |
|---|---|---|---|
| https://ffmpeg.org/legal.html | Licencia LGPL/GPL; patentes | web | 2026-11-01 |
| https://github.com/Zulko/moviepy | MIT, v2.0, rendimiento | web | 2026-11-01 |
| https://github.com/mifi/editly | MIT, Ken Burns, transiciones, subtítulos | web | 2026-11-01 |
| https://github.com/WyattBlue/auto-editor | Unlicense, exportaciones | web | 2026-11-01 |
| https://github.com/remotion-dev/remotion/blob/main/LICENSE.md | Gratis para ≤3 empleados | web | 2026-11-01 |
| https://www.remotion.dev/docs/license/pricing | Creators/Automators/Enterprise (importes no visibles en la página) | web (parcial) | 2026-11-01 |
| https://www.remotion.dev/docs/compare/motion-canvas | Motion Canvas solo canvas | tercero | 2026-11-01 |
| https://github.com/motion-canvas/exporters | Exportador ffmpeg MIT | tercero | 2026-11-01 |
| https://pkgs.alpinelinux.org/package/edge/community/x86_64/py3-mlt | Licencias de MLT (paquete) | tercero | 2026-11-01 |
| https://www.blackmagicdesign.com/products/davinciresolve | Precio Studio 236 USD; Free hasta UHD 8 bits | web | 2026-11-01 |
| https://forum.blackmagicdesign.com/viewtopic.php?p=670352 | Scripting externo no disponible en Free (2020) | tercero | 2026-11-01 |
| https://thepostflow.com/post-production/video-editing/resolve-studio-vs-free/ | Scripting solo Studio | tercero | 2026-11-01 |
| https://shotstack.io/pricing/ | Planes y precio por minuto | web | 2026-11-01 |
| https://community.shotstack.io/t/how-to-remove-the-shotstack-watermark-logo-from-the-video/540 | Marca de agua en sandbox | tercero | 2026-11-01 |
| https://creatomate.com/pricing | Estructura de planes, prueba de 50 créditos | web | 2026-11-01 |
| https://creatomate.com/docs/account/how-are-credits-calculated | Créditos por minuto | tercero (resultado de búsqueda) | 2026-11-01 |
| https://support.google.com/youtube/answer/1311392 | Política de contenido inauténtico | web | 2026-11-01 |
| https://www.capcut.com/clause/commercial-use | 404 | no verificado | 2026-11-01 |
| `~/Foundries/david-youtube-foundry/stacks/voice-narration.md`; `~/Foundries/david-foundry-core/tool-registry/whisperx.md` | ffmpeg en el stack de voz; alineación por palabra | medido (del propietario) | 2026-11-01 |
| Ejecución local de ffmpeg 9.0.1 en M4 Max | Codificadores, filtros y tiempos sintéticos | medido (sintético) | 2026-11-01 |


---

# Parte 5

## Etapa 05: Miniaturas, títulos y packaging

Fecha de consulta: 2026-11-01. Tipos de dato: **medido** (corrida del propietario), **web** (fuente oficial leída hoy; caduca a 90 días, es decir 2027-01-30), **tercero** (blog, agregador), **supuesto** (mío, con razón).
Cobertura: miniatura 1280x720, títulos, descripciones, tags, capítulos, prueba A/B (Test & Compare de YouTube) y medición de CTR. Solo lectura e investigación: no se instaló ni se ejecutó nada.

### 1. Resumen y recomendación

**Hallazgo central.** Esta etapa casi no tiene costo en dinero. Los costos reales son el tiempo humano y el hecho de que nadie ha medido todavía qué miniatura rinde (el Foundry lo dice: CTR mediana 2,6 % en 20 miniaturas, variación casi nula, correlación de texto −0,12 con n = 20, todo `medido` en un canal). La inversión útil no es una herramienta nueva: es **variar ejes a propósito y medir con la prueba A/B nativa de YouTube, que es gratis**.

**Dato que cambia el diseño del experimento.** La prueba A/B oficial de YouTube elige al ganador por **cuota de tiempo de visualización, no por CTR** (web, [support.google.com/youtube/answer/13861714](https://support.google.com/youtube/answer/13861714), 2026-11-01). Esto la hace más segura frente al clickbait, pero el CTR no sale como criterio de decisión. Hay que decidir si el CTR sigue siendo la métrica del canal (ver sección 5).

| Nivel | Recomendación | Por qué |
|---|---|---|
| **A: gratis / local** | **Pillow (composición, ya en el canal) + plantillas de parámetros + FLUX.2 [klein] 4B vía mflux (fondos y elementos, Apache 2.0) + A/B nativo de YouTube (Test & Compare)**. Los candidatos y la crítica los siguen haciendo los agentes `empaquetador` y `critico_empaquetado` | Licencias permisivas verificadas, todo corre en local o es gratis. Pillow ya existe: hay que extenderlo de un molde a varias plantillas, no sustituirlo. mflux es MLX nativo para Mac (web). El A/B es gratis y no necesita tarjeta |
| **B: gratis con límites / bajo costo** | **Nivel A + Gemini 3.1 Flash Lite Image o Nano Banana 2.1 por API para elementos puntuales (0,0336 USD por imagen 1K, 0,0168 en batch) + vidIQ Free solo para investigación de títulos** | Precio verificado en la página oficial. No hay nivel gratis de imagen en la API (web). Se descarta pagar vidIQ o TubeBuddy: lo que dan es investigación, que ya cubre el agente |
| **C: pago** | **thumbnailtest.com Basic (29 USD/mes) o TubeBuddy Legend (A/B)** solo si el A/B nativo resulta insuficiente (por ejemplo, se necesita decidir por CTR) | Son los únicos que ofrecen otro criterio de decisión. Los precios de ambas páginas salieron inconsistentes: confirmar antes de comprar |

**Qué automatiza la etapa.** Generación de 3 candidatos de título y miniatura, composición de las imágenes, crítica, subida de la miniatura (`thumbnails.set`), título, descripción, tags y capítulos por la API de YouTube, y lectura de resultados. **No es automatizable con seguridad** el veredicto editorial final (el Foundry lo exige con el gate G1) ni la revisión visual de marcas registradas en imágenes generadas.

**Minutos humanos por video a contar: 8 a 12 (supuesto).** Desglose: revisar 3 candidatos y confirmar el veredicto editorial (3 a 5), revisar a mano marcas, texto y desborde en la miniatura elegida (2 a 3), lanzar el test en Studio (2; el A/B es solo de escritorio y desde Studio, no vi una vía por API: ver unknowns), leer el resultado a los 3 a 14 días (1 a 2). Sin A/B baja a 5 a 8. Estos minutos son supuesto: ningún canal lo ha medido.

### 2. Catálogo de candidatos

Tiempo de máquina: no medido por el propietario para ninguna herramienta nueva; las cifras son **supuesto** salvo indicación. Idioma de interfaz o salida indicado cuando aplica.

| # | Herramienta | Tipo | Costo en dinero | Tiempo de máquina | Minutos humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Dato | Fuente (acceso 2026-11-01) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Pillow** (compositor actual del canal) | Local, librería Python | 0 USD | Menos de 1 s por miniatura (supuesto) | 0 al automatizarse; el trabajo es diseñar plantillas | MIT-CMU: uso, copia y modificación para cualquier fin, sin costo; conserva el aviso (web) | Sí. Hay ruedas macOS y CI en macOS (tercero: el README solo muestra insignia de ruedas); lo usa hoy el canal en el Mac del propietario | Hoy solo un molde. Texto con kerning básico, sin efectos avanzados (supuesto) | Cualquier texto con fuente que lo soporte | web (licencia), medido (uso en canal) | [LICENSE](https://raw.githubusercontent.com/python-pillow/Pillow/main/LICENSE) |
| 2 | **ImageMagick** | Local, CLI | 0 USD | Menos de 1 s (supuesto) | 0 | Licencia propia tipo Apache: uso personal, interno o comercial; atribución en redistribución (web) | Binario nativo por Homebrew (no verificado en esta investigación) | Útil para lotes, recortes, viñetas y comprobar contraste; peor para maquetar texto | Los de la fuente | web | [license](https://imagemagick.org/license/) |
| 3 | **Satori (HTML/CSS a SVG) + Sharp** | Local, Node | 0 USD | Menos de 1 s (supuesto) | 0 al tener plantilla | MPL-2.0 (web, página del repositorio); uso comercial permitido por la licencia, con obligación de compartir cambios a los archivos MPL | Node corre nativo en Mac (supuesto) | Plantillas en JSX/CSS, más fáciles de variar que Pillow; subconjunto de CSS (supuesto). Para PNG se usa Sharp, no se documenta resvg | Cualquiera con fuente | web | [github.com/vercel/satori](https://github.com/vercel/satori) |
| 4 | **FLUX.2 [klein] 4B vía mflux** | Local, MLX | 0 USD | Sin cifra publicada; 13 GB de VRAM (web, tarjeta del modelo) caben en 64 GB. Segundos a minuto por imagen (supuesto) | 2 a 3 si se revisa a mano | Pesos Apache 2.0, uso comercial (web). La tarjeta no trata la propiedad de la salida. **El 9B es no comercial: no usarlo** (web) | mflux es "MLX native" y MIT (web). No vi benchmark en M4 | Calidad "muy buena" según el README de mflux (tercero respecto del modelo); sin evidencia propia. Riesgo de marcas y texto torcido | Inglés; texto en imagen no verificado | web | [mflux](https://github.com/filipstrand/mflux), [klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B), [klein-9B](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B) |
| 5 | **Z-Image-Turbo vía mflux** | Local, MLX | 0 USD | 6B parámetros, cabe en 16 GB (web); el ejemplo del README usa 9 pasos y `-q 8` | 2 a 3 | Apache-2.0 (web) | Soportado por mflux con compute float16 (web) | Presume buen texto en inglés y chino (afirmación del autor, no verificada) | Inglés y chino | web | [Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo), [mflux](https://github.com/filipstrand/mflux) |
| 6 | **Stable Diffusion en MLX (mlx-examples)** | Local, MLX | 0 USD | Sin cifra; corre SDXL-Turbo en un Mac mini de 8 GB (web) | 2 a 3 | La página no declara licencia; **no verificada** | Sí, MLX | Modelos más viejos que 4 y 5; solo como respaldo | Inglés | web | [mlx-examples](https://github.com/ml-explore/mlx-examples/tree/main/stable_diffusion) |
| 7 | **Gemini Image (API)**, ya en el Foundry | API | Nano Banana 2.1: 0,0336 USD (1K), 0,0168 en batch. Nano Banana 2 (el 3.1 Flash Image que usa el canal): 0,067 USD (1K). Sin nivel gratis para imágenes (web) | Segundos por llamada, sin carga local | 2 a 3 (revisar marcas) | La ficha del Foundry dice "no determinada"; sigue **sin verificar** | No aplica (nube) | Generó un logo real sin pedirlo; riesgo residual (medido, `gemini-image`). Nano Banana 2.5 se retira el 2027-03-15 (web) | Multilingüe, texto en imagen no verificado | web, medido (0,067) | [precios](https://ai.google.dev/gemini-api/docs/pricing) |
| 8 | **Figma AI (imágenes en Figma)**, ya en el Foundry | Servicio | Créditos del plan; monto no medido (supuesto) | No aplica | 5 a 10 por video si se maqueta a mano (supuesto) | No determinada | No aplica | Enlaces expiran a los 7 días; solo maquetas (medido, `figma-ai-images`) | Los del modelo | medido | Ficha del Foundry |
| 9 | **Canva Connect API (autofill)** | API | Autofill disponible para apps que actúan en nombre de usuarios de Canva Pro, Teams o Enterprise; Pro es de pago (web). Límites de uso "futuros" | Nube | 3 a 5 | Términos de Canva no revisados | No aplica | Rellena plantillas de marca con datos. Documentación avisa que las APIs en vista previa no son para producción (web) | Los de Canva | web | [Connect](https://www.canva.dev/docs/connect/), [autofill](https://www.canva.dev/docs/connect/api-reference/autofills/) |
| 10 | **YouTube Test & Compare / A/B de títulos y miniaturas** | Servicio nativo, gratis | 0 USD | No aplica | 2 min para lanzar + 1 a 2 para leer | Parte de YouTube Studio | No aplica | Ver sección 5 | Cualquiera | web | [A/B test](https://support.google.com/youtube/answer/13861714) |
| 11 | **vidIQ Free / Boost** | Servicio | Free 0 USD con 150 créditos de IA al mes; Boost 19 USD/mes (199/año); MAX 49 USD/mes. La miniatura con IA solo aparece en Boost (web); página incoherente (39 vs 49) | No aplica | 2 a 3 | Términos no revisados | No aplica | El nivel gratis ofrece tendencias, ideas y un entrenador de IA; no listó herramientas de título o miniatura. Incluye servidor MCP en todos los planes (web) | Inglés sobre todo (supuesto) | web | [pricing](https://www.vidiq.com/pricing/) |
| 12 | **TubeBuddy Pro / Legend** | Servicio | Precios no legibles en la captura. A/B solo en Legend y Enterprise; no en Pro. Excluye canales de 50.000+ suscriptores o con 3+ gestores (web) | No aplica | 2 a 3 | Licencia por canal | No aplica | Sin nivel gratis confirmado en la página | Inglés sobre todo (supuesto) | web | [pricing](https://www.tubebuddy.com/pricing) |
| 13 | **thumbnailtest.com** | Servicio | Basic 29 USD/mes, Pro 49, Business 99; sin nivel gratis, 14 días de reembolso. Cifras anuales incoherentes (web, vendedor) | No aplica | 2 | Términos no revisados | No aplica | Competidor comercial de YouTube; sus guías contra el A/B nativo son parciales (tercero) | Cualquiera | web | [pricing](https://thumbnailtest.com/pricing) |
| 14 | **Agentes `empaquetador` y `critico_empaquetado` (Claude)** | Local, agentes del canal | Costo real o equivalente por suscripción; no leído (Foundry) | Minutos | 3 a 5 (veredicto G1) | Términos de Anthropic: no revisados | No aplica | Sin evidencia de que elijan mejor que el azar | Inglés, español | medido (uso), no leído (costo) | `thumbnails-packaging.md` |

Descartado sin verificar: tecnologías sin fuente oficial leída hoy (Photopea, Krita, Adobe Firefly, Midjourney, Ideogram). Aparecen en `unknowns`.

### 3. Fichas de las recomendadas o finalistas

#### Pillow + plantillas (nivel A, base)
- **Qué es.** Librería Python de imágenes con licencia MIT-CMU (web). Ya compone las miniaturas del canal con un solo molde.
- **Integración.** Una función `componer(plantilla, titulo_corto, rostro, fondo) -> PNG 1280x720`. Cada plantilla es un archivo de parámetros (posición del texto, tamaño, luminosidad del fondo, con o sin rostro). Es lo que permite variar los ejes que el canal quiere probar (cantidad de texto, luminosidad, rostro) sin tocar código.
- **Límites.** Texto sin efectos finos. Si las plantillas necesitan sombras, degradados o capas complejas, Satori ofrece diseño en JSX/CSS, o ImageMagick para lotes.
- **Riesgos.** Bibliotecas de rostros reutilizadas en todos los videos: el Foundry ya midió 58 rostros, casi todos mujeres en angustia. Eso alimenta el riesgo de "contenido interchangeable" (sección 4).

#### FLUX.2 [klein] 4B vía mflux (nivel A, fondos)
- **Qué es.** Modelo de imágenes de 4B con licencia Apache 2.0 (web) que corre en MLX con `mflux`, MIT (web). El README lo describe como el más rápido y pequeño con buena calidad y edición (tercero del autor de mflux).
- **Integración.** CLI (`mflux-generate-...`) o API Python, según el README. Se instala con `uv tool install mflux` (web, no ejecutado).
- **Límites.** Sin benchmark propio en el M4 Max. No generar texto en la imagen: el texto lo pone Pillow. Si falla `hf_transfer`, reinstalar con esa dependencia (web).
- **Riesgos.** Marcas registradas y rostros reconocibles aparecen en salidas de modelos de imágenes (el canal lo sufrió con Gemini; en modelos locales **no medido**). Revisión humana obligatoria. No usar el 9B: licencia no comercial (web).

#### YouTube Test & Compare / A/B (nivel A y B, medición)
Ver sección 5.

#### Gemini Image (nivel B, opcional)
- **Qué es.** API por tokens. Precios actuales en la tabla; el canal ya paga 0,067 USD con el modelo que usa (medido, n pequeño).
- **Opción barata.** Nano Banana 2.1 a 0,0336 USD (1K), la mitad en batch (web). No medido por el propietario.
- **Riesgo.** La licencia de la salida sigue sin determinar. Mientras no se verifique, usar esta ruta solo en elementos sueltos que se transformen mucho, o preferir la ruta local con licencia Apache.

#### vidIQ Free (nivel B, investigación)
- **Qué es.** Investigación de tendencias e ideas con 150 créditos de IA al mes (web). Incluye servidor MCP que gasta esos créditos (web).
- **Integración.** MCP, que podría usarse desde los agentes. No verifiqué qué herramientas expone ni si cubre títulos.
- **Límites.** El nivel gratis no incluye la creación de miniaturas (solo Boost, web).

### 4. Riesgos de política y de derechos

| Riesgo | Qué dice la fuente | Implicación |
|---|---|---|
| **Clickbait malicioso** | YouTube prohíbe "maliciously misleading titles, thumbnails, descriptions, or imagery" para engañar a quien hace clic; las sanciones van de retirada a terminación, con 3 avisos en 90 días (web, [spam policy](https://support.google.com/youtube/answer/2801973)) | Reglas en el agente crítico: la miniatura y el título deben ser cumplibles por el video; no prometer lo que el guion no entrega. Un eje de la crítica ya es "gancho sin spoiler" (Foundry) |
| **Imagen engañosa y monetización** | Contenido con "imágenes o narrativas engañosas" no es apto para monetizar (web, [política de canal](https://support.google.com/youtube/answer/1311392)) | Igual que el anterior |
| **Contenido inauténtico (plantillas)** | Desde 2025-07-15 el contenido que "parece producido con una plantilla", intercambiable de video en video, o IA masiva sin aporte original no se monetiza (web, [política](https://support.google.com/youtube/answer/1311392)) | Aplica sobre todo al video, pero miniaturas con **un solo molde y los mismos rostros** (medido) refuerzan la señal de plantilla. Hacer 3 a 5 plantillas distintas es también mitigación |
| **Divulgación de contenido sintético** | Usar IA generativa para crear o mejorar un guion, miniatura, título o infografía figura como asistencia de producción que **no exige divulgar** (web, [divulgación](https://support.google.com/youtube/answer/14328491)). Sí exige para realismo que pueda confundirse con real (no leído en detalle aquí) | Una miniatura con una persona sintética que parezca real y se refiera a un hecho real: revisar la regla completa antes de usarla. No mostrar rostros reales generados |
| **Marcas registradas en imágenes generadas** | Pasó con el logo de L.L.Bean (medido, n pequeño) | Revisión humana, también con los modelos locales |
| **Licencia de salida de Gemini y Figma AI** | Sin determinar (Foundry) | No contarlas como cubiertas hasta leer los términos |
| **FLUX.2 9B no comercial** | FLUX Non-Commercial License (web) | Fijar en el compositor el nombre del modelo permitido (4B) |
| **Tags** | No hallé una política vigente de tags en esta investigación | Ver unknowns |
| **A/B no se puede probar con Shorts, niños, mayores ni privados** | web, página A/B | Solo videos largos públicos |

### 5. Comparación con lo medido y qué falta medir

**Lo que el propietario ya sabe (medido, 1 canal):** CTR propio 2,6 % de mediana, pero la columna de impresiones salió vacía; variación casi nula; texto frente a CTR −0,12 con n = 20 (sin valor); competidores: rostro grande casi siempre, 4 de 6 con fondo claro o saturado (describe, no prueba).

**Qué aporta esta investigación**
1. **El A/B nativo resuelve la variación, pero cambia la métrica.** Gana por cuota de tiempo de visualización; se chequea con un grupo de control pequeño que se excluye; da "Winner", "Performed Same" o "Inconclusive"; termina en menos de dos semanas, antes con más impresiones; hasta 3 variantes de título y/o miniatura; solo escritorio; cambiar título o miniatura durante el test lo detiene; si una miniatura mide menos de 720p todas bajan a 480p (web, página A/B). **Todas las miniaturas deben ser exactamente 1280x720.**
2. **Con pocas vistas, un canal nuevo tarda.** Los tests terminan antes con más impresiones (web). Un canal nuevo tendrá muchos "Inconclusive": hay que tratarlos como "sin diferencia", no como fallo.
3. **Cómo obtener el CTR para decidir.** Existe `videoThumbnailImpressions` en la API de Analytics (web, [resultado de búsqueda sobre las métricas](https://developers.google.com/youtube/analytics/metrics)), y la API de Reporting lista `video_thumbnail_impressions_ctr` (web, mismo enlace de la búsqueda de métricas, no leído en la página completa). **No verifiqué si el CTR sale por la API de Analytics**: el propietario ya importa el CSV de Studio (`importar-ctr`). Mantener esa ruta y corregir el CSV de impresiones vacío.
4. **Subida automática.** `thumbnails.set` cuesta unas 50 unidades de cuota por llamada, admite JPEG y PNG hasta 50 MB y pide uno de los alcances `youtube`, `youtube.upload`, `youtube.force-ssl` o `youtubepartner` (web, [documentación](https://developers.google.com/youtube/v3/docs/thumbnails/set)).

**Experimentos baratos que puede correr**
1. **E1, cero costo (1 tarde).** Producir 3 plantillas de Pillow que difieran en un solo eje (por ejemplo, con o sin rostro) para el próximo video y lanzarlas en el A/B nativo. Anotar resultado ("Winner", "Same", "Inconclusive") y días hasta el final. Pregunta: ¿cuántas impresiones necesita un canal pequeño para que el test concluya?
2. **E2, cero costo.** Arreglar el CSV: que `importar-ctr` incluya impresiones. Sin impresiones, el CTR de 20 miniaturas no se puede ponderar.
3. **E3, 1 USD.** Generar 10 fondos con FLUX.2 [klein] 4B en el M4 Max y anotar segundos por imagen, memoria usada y cuántos pasan la revisión de marcas y texto. Rellena el hueco de tiempo de máquina.
4. **E4, cero costo.** Revisar si el A/B se puede iniciar por API o solo en Studio (confirmarlo con la documentación o probando una vez). Decide si el paso se puede automatizar del todo.
5. **E5 (propuesta del canal, ~8 videos por variante).** Con la regla de que el A/B puede aplicarse al mismo video, cada video entrega una comparación sin gastar 8 videos por variante. Es una ventaja frente a la propuesta actual del canal.

### 6. Unknowns

1. ¿El A/B de títulos y miniaturas se puede lanzar y leer por API, o solo desde Studio de escritorio? No hallé documentación de API; la página oficial habla de Studio (web).
2. Licencia y propiedad de las **salidas** de FLUX.2 4B, Z-Image-Turbo y Gemini Image: las tarjetas dicen Apache 2.0 para los pesos, pero la tarjeta no trata la propiedad de la salida. Términos de Gemini y Figma AI sin leer.
3. Tiempo de máquina real en el M4 Max (mflux, FLUX.2 4B, Z-Image): sin benchmark leído.
4. Disponibilidad exacta de CTR por la API de Analytics y por la de Reporting: sin confirmar en la página completa.
5. Precios actuales de TubeBuddy (la captura salió sin cifras) y la contradicción de vidIQ MAX (39 vs 49 USD) y de thumbnailtest.com (anual más caro que mensual).
6. Reglas actuales de longitud de título, descripción y tags, y de capítulos (formato de marcas de tiempo): no leí una fuente oficial en esta investigación. No usar cifras de memoria.
7. Regla completa de divulgación de contenido sintético para miniaturas con personas realistas: solo leí la excepción de "asistencia de producción".
8. Términos de Canva Connect, límites de uso futuros y si compensa frente a Pillow.
9. Herramientas no investigadas: Photopea, Krita, Firefly, Midjourney, Ideogram, Figma API (plantillas), Playwright (HTML a PNG).
10. Si los títulos largos o con etiqueta de formato («FULL STORY») cambian el CTR: no hay datos.

### 7. Tabla de fuentes (todas accedidas el 2026-11-01)

| Dato | URL |
|---|---|
| A/B de títulos y miniaturas (elegibilidad, métrica, 720p, duración) | https://support.google.com/youtube/answer/13861714 |
| Resumen de búsqueda sobre Test & Compare (tercero para fechas de despliegue) | https://support.google.com/youtube/answer/16391400 |
| Divulgación de IA; excepción de miniatura y título | https://support.google.com/youtube/answer/14328491 |
| Política de canal e inauténtico | https://support.google.com/youtube/answer/1311392 |
| Spam y clickbait malicioso | https://support.google.com/youtube/answer/2801973 |
| `thumbnails.set` | https://developers.google.com/youtube/v3/docs/thumbnails/set |
| Métricas de Analytics API (búsqueda; página sin la métrica de CTR en lo leído) | https://developers.google.com/youtube/analytics/metrics |
| Precios de Gemini | https://ai.google.dev/gemini-api/docs/pricing |
| mflux (MIT, modelos) | https://github.com/filipstrand/mflux |
| FLUX.2 klein 4B (Apache 2.0) | https://huggingface.co/black-forest-labs/FLUX.2-klein-4B |
| FLUX.2 klein 9B (no comercial) | https://huggingface.co/black-forest-labs/FLUX.2-klein-9B |
| Z-Image-Turbo | https://huggingface.co/Tongyi-MAI/Z-Image-Turbo |
| MLX stable diffusion | https://github.com/ml-explore/mlx-examples/tree/main/stable_diffusion |
| Pillow (MIT-CMU) | https://raw.githubusercontent.com/python-pillow/Pillow/main/LICENSE |
| ImageMagick | https://imagemagick.org/license/ |
| Satori (MPL-2.0) | https://github.com/vercel/satori |
| Canva Connect | https://www.canva.dev/docs/connect/ y https://www.canva.dev/docs/connect/api-reference/autofills/ |
| vidIQ | https://www.vidiq.com/pricing/ |
| TubeBuddy | https://www.tubebuddy.com/pricing |
| thumbnailtest.com | https://thumbnailtest.com/pricing |
| Foundry (medido) | `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md`; `~/Foundries/david-foundry-core/tool-registry/gemini-image.md`, `figma-ai-images.md` |


---

# Parte 6

## 06 Música, efectos de sonido y subtítulos/transcripción

Fecha de consulta: 2026-11-01. Tipos de dato: medido / web (caduca a 90 días, es decir 2027-01-30) / tercero / supuesto. Hardware de referencia: Mac M4 Max 64 GB. No se instaló ni descargó nada; todo es lectura de fuentes.

Punto de partida del Foundry: solo existe `whisperx.md` (estado experimental, un canal, inglés). No hay ficha de música ni de SFX; esa parte es campo nuevo.

### 1. Resumen y recomendación

| Nivel | Música | SFX | Subtítulos / transcripción | Traducción (canal ES) |
|---|---|---|---|---|
| A: gratis y local | Biblioteca de YouTube Audio Library (descarga manual, sin API) + Pixabay Music como respaldo; mezcla y ducking con ffmpeg (`sidechaincompress`) | Audio Library SFX + Freesound CC0 | **mlx-whisper** (large-v3-turbo) para transcribir; alineación con **WhisperX** sobre el guion real (ya medido); salida .srt/.vtt generada por código desde los tiempos por palabra | Argos Translate (MIT/CC0, offline) como borrador; LLM si se acepta costo |
| B: gratis con límites o bajo costo | Uppbeat (plan gratis con límites; condiciones sin verificar) o Suno Pro/Premier (comercial solo con descarga dentro del cupo) | Freesound con API (requiere cuenta, no verificado) | whisper.cpp con Core ML si se prefiere un binario sin Python | LLM por API para traducir el .srt conservando tiempos |
| C: pago | Epidemic Sound / Artlist (no verificado, sin acceso a las páginas) | Epidemic/Artlist (no verificado) | No se necesita | Servicios de traducción de pago, no se necesitan |

Recomendación por nivel: **A = YouTube Audio Library + mlx-whisper/WhisperX**; **B = Uppbeat o Suno Pro (solo si se quiere música a medida)**; **C = no recomendable en esta etapa**, porque A resuelve el problema.

Automatización: subtítulos 100 % automáticos (supuesto razonable, el propietario ya automatizó WhisperX). La música es el cuello de botella: la Audio Library no tiene API pública conocida (no se halló en esta investigación), así que elegir y descargar pistas es manual salvo que se arme una biblioteca previa reutilizable. Estrategia: **curar una sola vez 15 a 25 pistas por canal** (una hora humana, una vez) y después asignarlas por código según estado de ánimo. Minutos humanos por video: **0 a 3** con biblioteca curada (supuesto); 10 a 15 si se elige pista a mano en cada video (supuesto).

### 2. Catálogo de candidatos

Música

| Herramienta | Tipo | Costo | Tiempo de máquina | Min. humanos/video | Licencia y uso comercial | Apple Silicon | Calidad / defectos | Dato y fuente |
|---|---|---|---|---|---|---|---|---|
| YouTube Audio Library | servicio, descarga MP3 | 0 USD | 0 | 0 con biblioteca curada | Miembros del YPP pueden monetizar; sus pistas no se reclaman por Content ID; CC requiere crédito en la descripción, la licencia estándar se puede filtrar para no pedirlo | n/a | Catálogo genérico, muy repetido entre canales; sin API hallada | web, [soporte YouTube](https://support.google.com/youtube/answer/3376882), 2026-11-01 |
| Pixabay Music | servicio | 0 USD | 0 | 0 con biblioteca curada | Uso comercial, sin atribución, modificable; prohíbe vender sin aportar y exige revisar derechos de terceros. La página no habla de Content ID | n/a | Riesgo de reclamos: no verificado (ver sección 4) | web, [Pixabay licencia](https://pixabay.com/service/license-summary/), 2026-11-01 |
| Incompetech (Kevin MacLeod) | servicio | 0 USD con crédito; licencia de pago sin crédito | 0 | 1 (pegar crédito) | CC BY 4.0, monetizado permitido, crédito en descripción con formato fijo. Cada pista tiene ISRC para disputar reclamos | n/a | Estilo muy reconocido/repetido | web, [FAQ Incompetech](https://incompetech.com/music/royalty-free/faq.html), 2026-11-01 |
| Free Music Archive | servicio | 0 USD | 0 | 1 a 2 | Mezcla de licencias CC (algunas NC): hay que filtrar. **No verificado**: la página de términos dio 404 | n/a | Varía por pista | no verificado |
| Uppbeat | servicio | plan gratis con cupo | 0 | 1 | **No verificado** (página 429/404) | n/a | n/d | no verificado |
| Epidemic Sound / Artlist | servicio de pago | suscripción | 0 | 1 | **No verificado**: no se accedió a términos. Habitualmente licencia por canal; confirmar | n/a | Mayor catálogo | no verificado |
| Suno | API/servicio (IA) | planes | 0 local | 3 a 5 (prompts y selección) | Gratis/Basic: solo uso personal no comercial. Pro/Premier: cesión de derechos y uso comercial solo de salidas descargadas por canal aprobado y dentro del cupo; sin garantía de copyright | n/a (nube) | Otros usuarios pueden recibir salidas similares | web, [Suno términos](https://suno.com/terms), 2026-11-01 |
| Udio | servicio (IA) | n/d | 0 local | n/d | **No verificado** | n/a | n/d | no verificado |
| Stable Audio Open 1.0 | local (modelo) | 0 USD | n/d | 3 a 5 | Stability AI Community License; la ficha remite a stability.ai/license para uso comercial y no da umbrales. Entrenado con CC0/CC BY/CC Sampling+ de Freesound y FMA. Máx. 47 s | La ficha solo muestra CUDA/CPU; MPS no verificado | Clips de 47 s: hay que unirlos | web, [Hugging Face](https://huggingface.co/stabilityai/stable-audio-open-1.0), 2026-11-01 |
| MusicGen (AudioCraft) | local (modelo) | 0 USD | n/d | 3 a 5 | Código MIT; **pesos CC-BY-NC 4.0, es decir no comercial** | MPS no mencionado | No usar en un canal monetizado | web, [GitHub AudioCraft](https://github.com/facebookresearch/audiocraft), 2026-11-01 |

SFX

| Herramienta | Costo | Licencia | Fuente |
|---|---|---|---|
| YouTube Audio Library (sonidos) | 0 | Igual que su música: monetizable, sin Content ID | web, soporte YouTube arriba |
| Freesound | 0 | CC0 (libre), CC BY (crédito), CC BY-NC (prohibido monetizar). Filtrar a CC0 para no llevar créditos. Acceso a la API: no verificado | web, [Freesound FAQ](https://freesound.org/help/faq/), 2026-11-01 |

Subtítulos y transcripción

| Herramienta | Tipo | Costo | Licencia | Apple Silicon | Formatos y calidad | Fuente |
|---|---|---|---|---|---|---|
| mlx-whisper | librería/CLI local | 0 | El README no declara licencia (el repo mlx-examples: no verificado en esta lectura) | Nativo MLX/Metal. Un tercero midió ~2x la velocidad de whisper.cpp con large-v3-turbo en M1 Max (13 s frente a ~26 s sobre un clip no especificado) | Bandera `-f` para formato (lista no leída); `word_timestamps=True` | web/tercero, [GitHub mlx-examples](https://github.com/ml-explore/mlx-examples/tree/main/whisper) y [Bill Mill](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html), 2026-11-01 |
| whisper.cpp | binario nativo | 0 | MIT | Metal en GPU; Core ML en el Neural Engine (>3x frente a CPU según el README) | Texto con tiempos, palabra a palabra con `-ml 1`; el README leído no cita SRT/VTT (no verificado si los emite) | web, [GitHub whisper.cpp](https://github.com/ggml-org/whisper.cpp), 2026-11-01 |
| WhisperX | librería/CLI | 0 | BSD-2-Clause (repositorio) | La documentación solo cita CPU para macOS (`--device cpu --compute_type int8`); sin MPS documentado | Salida .srt; VTT no mencionado; alineación por palabra en inglés, francés, alemán, español, italiano y otros vía Hugging Face; claims de 70x tiempo real son de GPU | web, [GitHub WhisperX](https://github.com/m-bain/whisperX), 2026-11-01 |
| faster-whisper | librería | 0 | MIT | Solo CPU en Mac según el README (int8); sin Metal | Benchmarks del README son de NVIDIA o Intel; ninguno en Apple Silicon | web, [GitHub faster-whisper](https://github.com/SYSTRAN/faster-whisper), 2026-11-01 |

Traducción

| Herramienta | Licencia | Notas | Fuente |
|---|---|---|---|
| Argos Translate | MIT o CC0 | Offline, `pip install argostranslate`, en->es; calidad no evaluada; Apple Silicon no documentado (usa CTranslate2, CPU) | web, [GitHub](https://github.com/argosopentech/argos-translate), 2026-11-01 |
| NLLB-200 600M | **CC-BY-NC 4.0; "no para producción"** | Descartado para canal monetizado | web, [Hugging Face](https://huggingface.co/facebook/nllb-200-distilled-600M), 2026-11-01 |
| LLM por API | según proveedor | No evaluado aquí | n/a |

### 3. Fichas breves

- **YouTube Audio Library**: la opción más segura frente a reclamos. Se integra a mano: descargar MP3, guardar en una carpeta por estado de ánimo con un JSON de metadatos (título, artista, si pide crédito). Si una pista es CC, el pipeline debe agregar el crédito a la descripción por código. Riesgo: sin API hallada, el catálogo se cura una vez.
- **Mezcla y ducking por código**: ffmpeg, filtro `sidechaincompress` (voz como señal de control) o `amix` con volumen fijo bajo la voz, más `loudnorm` a un objetivo de volumen. Esto es conocimiento general de ffmpeg y no se verificó contra su documentación en esta corrida (supuesto). Costo: segundos de máquina por video.
- **mlx-whisper + WhisperX**: el propietario ya alinea con WhisperX sobre el guion real (medido). Para subtítulos, la ruta recomendada es no transcribir el audio sino usar los tiempos por palabra del guion y escribir el .srt/.vtt por código (el VTT es un formato de texto simple). mlx-whisper queda para transcribir competidores o medir WER donde WhisperX en CPU resulte lento.
- **Suno Pro/Premier**: solo si se quiere música original; exige descargar dentro del cupo y no garantiza copyright. Verificar con política de YouTube (sección 4).

### 4. Riesgos de política y derechos

- **Contenido inauténtico** (política YPP, [soporte YouTube](https://support.google.com/youtube/answer/1311392), 2026-11-01): marca como no permitido el contenido genérico, hecho con plantilla o repetitivo, y las presentaciones de imágenes con poco valor narrativo. Permite intros/outros compartidos si el contenido principal difiere. Para música: no permite compilaciones de canciones de artistas distintos ni cambiar solo tono o velocidad. Implicación: la música de fondo no es el riesgo principal; lo es el conjunto del canal. Un tercero de blogs sugiere que audio autogenerado con imagen estática es el ejemplo típico de demonetización (tercero, sin cita oficial).
- **Divulgación de contenido sintético** ([soporte YouTube](https://support.google.com/youtube/answer/14328491), 2026-11-01): exige divulgar música generada por IA solo cuando es el foco principal del video; no exige divulgar subtítulos/captions, scripts, ni clonar la propia voz. Música de fondo generada por IA no queda claramente cubierta: **no verificado**; en la duda, divulgar.
- **Content ID**: YouTube garantiza ausencia de reclamos solo para la Audio Library. Para Pixabay, FMA y Uppbeat no se verificó política sobre reclamos. Incompetech entrega ISRC por pista para disputar. Guardar siempre el comprobante de licencia (URL y fecha) por pista.
- **¿Es monetizable la música IA?** Suno: solo en planes Pro/Premier y por descargas dentro del cupo. MusicGen: pesos NC, no usar. Stable Audio Open: depende de la licencia comunitaria de Stability, no leída.
- **Atribución**: CC BY (Audio Library CC, Incompetech, Freesound) exige crédito; automatizar su inserción en la descripción.
- **Traducción**: NLLB está prohibido para uso comercial; Argos es libre.

### 5. Comparación con lo medido y qué falta medir

Medido (de `whisperx.md`): WhisperX local, 0 USD, un canal, inglés; alinear sobre el texto del ASR es un error, hay que alinear el guion real; fijar el idioma; normalizar puntuación para el WER. No hay medición de música, SFX, ni de subtítulos en español.

Experimentos baratos:
1. Cronometrar mlx-whisper large-v3-turbo contra WhisperX en CPU sobre un audio de 20 min en el M4 Max (resultado: segundos por video).
2. Generar .srt y .vtt desde los tiempos del guion y comprobar que YouTube los acepta (cargar en un video no listado).
3. Curar 20 pistas de la Audio Library, aplicar ducking con ffmpeg y escuchar el resultado; contar minutos humanos reales.
4. Traducir un .srt con Argos al español y revisar 50 líneas a mano para medir la tasa de errores.
5. Subir un video de prueba no listado con pistas de Pixabay y ver si aparece un reclamo.

### 6. Unknowns

- Si la Audio Library tiene API o descarga programable (no se halló).
- Términos, límites y política de Content ID de Free Music Archive, Uppbeat, Epidemic Sound, Artlist y Udio (no accesibles: 429/404 o sin acceso).
- Licencia de mlx-whisper/mlx-examples y de los pesos Whisper en su ficha (no leída).
- Si whisper.cpp emite .srt/.vtt (el README leído no lo dice) y si WhisperX corre con MPS en el M4 Max.
- Velocidad real en M4 Max de cada herramienta (el único dato es de M1 Max y de un tercero).
- Si la música de fondo generada por IA exige divulgación; si Stable Audio Open permite uso comercial en el caso del propietario.
- Calidad de Argos en español de narración larga.

### Tabla de fuentes (acceso 2026-11-01)

| URL | Usada para |
|---|---|
| https://support.google.com/youtube/answer/3376882 | Audio Library |
| https://support.google.com/youtube/answer/1311392 | Contenido inauténtico |
| https://support.google.com/youtube/answer/14328491 | Divulgación de contenido sintético |
| https://pixabay.com/service/license-summary/ | Pixabay |
| https://incompetech.com/music/royalty-free/faq.html | Incompetech |
| https://suno.com/terms | Suno |
| https://huggingface.co/stabilityai/stable-audio-open-1.0 | Stable Audio Open |
| https://github.com/facebookresearch/audiocraft | MusicGen |
| https://freesound.org/help/faq/ | Freesound |
| https://github.com/m-bain/whisperX | WhisperX |
| https://github.com/ggml-org/whisper.cpp | whisper.cpp |
| https://github.com/ml-explore/mlx-examples/tree/main/whisper | mlx-whisper |
| https://github.com/SYSTRAN/faster-whisper | faster-whisper |
| https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html | Benchmark de tercero |
| https://github.com/argosopentech/argos-translate | Argos Translate |
| https://huggingface.co/facebook/nllb-200-distilled-600M | NLLB |


---

# Parte 7

## Etapa 07: Publicación, programación y analítica

Fecha de consulta: 2026-11-01. Todo dato `web` caduca a 90 días (2027-01-30). Las páginas se leyeron con WebFetch (un modelo pequeño resume la página, así que las citas literales son del resumen y no de la página completa; las páginas largas se leyeron truncadas). No se instaló nada, no se creó ninguna cuenta ni proyecto de Google Cloud, y no se subió ningún video.

Tipos de dato: **medido**, **web** (URL y fecha), **tercero**, **supuesto**.

---

### 1. Resumen y recomendación

#### Hallazgos que cambian el plan

1. **Los umbrales de monetización de un canal nuevo cambian el 2027-02-01.** Dos fuentes oficiales de YouTube dicen cosas distintas y hay que leerlas juntas:
   - La página de ayuda de elegibilidad al YPP sigue mostrando 1.000 suscriptores + 4.000 horas públicas de los últimos 12 meses (o 10 millones de vistas de Shorts en 90 días). Solo agrega el aviso "Starting February 1, 2027, we are introducing updates to the YouTube Partner Program" y pide aceptar los términos nuevos en Studio antes del 2027-01-31. No menciona 8.000 horas. (web, https://support.google.com/youtube/answer/72851, consultada 2026-11-01; sin fecha de actualización visible, solo "©2026 Google").
   - El anuncio en el blog de Google (fecha 11 de agosto de 2026) dice que los solicitantes nuevos necesitarán "8,000 qualified watch hours in the last 365 days, or 20M qualified Shorts views in the last 90 days", más 1.000 suscriptores; y que "This update won't impact creators already in YPP". (web, https://blog.google/intl/en-mena/product-updates/connect-communicate/new-opportunities-to-earn-and-changes-to-the-youtube-partner-program/, consultada 2026-11-01.) Es el blog de la región MENA; no encontré la misma entrada en el blog global.
   - Por tanto el "8.000 horas desde 2027-02-01" del informe **está respaldado por el blog oficial de Google, no por la página de ayuda**. El umbral aplica a solicitantes nuevos; quien ya esté en el YPP no se ve afectado.
   - Resumen de NewsShooter (tercero que cita el anuncio, https://www.newsshooter.com/2026/08/10/youtube-updates-its-partner-program/, 2026-11-01): fan funding, Creator Partnerships y Shopping se mantienen en 500 suscriptores + 3.000 horas (o 3 millones de vistas de Shorts); el reparto de Shorts exige 10 millones de vistas en 90 días solo para quien ya cobra por Shorts.
   - **Consecuencia para NicheRadar**: un canal que aún no existe no puede juntar 4.000 horas antes del 2027-02-01 (quedan 3 meses). Hay que planificar el hito de monetización con **8.000 horas + 1.000 suscriptores** (supuesto de planificación prudente). A 22 min por video, 8.000 h son 21.800 reproducciones completas equivalentes; con retención media del 40 % son unas 54.500 vistas. Es un cálculo mío (supuesto), no una estadística de YouTube.
2. **La cuota de subida cambió y ahora es muy holgada.** Desde 2026-06-01 `videos.insert` tiene su propio cubo: **100 llamadas/día a 1 unidad**; `search.list` otro cubo de 100/día; el resto comparte 10.000 unidades/día. Antes de 2025-12-04 una subida costaba ~1.600 unidades. (web, https://developers.google.com/youtube/v3/determine_quota_cost y https://developers.google.com/youtube/v3/revision_history, 2026-11-01.) Para 1 a 3 videos por semana la cuota no es un límite.
3. **Contradicción sin resolver sobre el bloqueo a "privado" de proyectos no verificados.**
   - Las páginas actuales de `videos` y `videos.insert` dicen textualmente: "Videos uploaded from unverified API projects are not restricted to private viewing mode." (web, https://developers.google.com/youtube/v3/docs/videos/insert, 2026-11-01).
   - El historial de revisiones conserva la entrada de 2020-07-28 que imponía el bloqueo (web, https://developers.google.com/youtube/v3/revision_history), y la ayuda de Studio sigue diciendo que un video "locked" por subirse con un servicio de API no verificado no se puede apelar y hay que re-subirlo desde un servicio verificado o desde la web (web, https://support.google.com/youtube/answer/7300965, 2026-11-01).
   - Lo más probable es que la restricción se haya retirado en la documentación de desarrolladores y la página de ayuda esté desactualizada, pero **no está verificado**. Experimento barato en la sección 5.
4. **La API de Analytics no expone impresiones ni CTR en las páginas leídas; la API de Reporting sí** (reportes `channel_reach_basic_a1` con `video_thumbnail_impressions` y `video_thumbnail_impressions_ctr`). (web, https://developers.google.com/youtube/reporting/v1/reports/channel_reports, 2026-11-01.) La página de métricas de Analytics no lista `videoThumbnailImpressions` (web, https://developers.google.com/youtube/analytics/metrics; la página se leyó truncada, así que "no aparece" es "no lo vi"). Esto concuerda con lo medido por el propietario: la columna de impresiones del CSV de Studio salió vacía con pocas vistas (medido, `stacks/thumbnails-packaging.md`).

#### Tabla de decisión

| Nivel | Recomendación | Por qué | Minutos humanos por video |
|---|---|---|---|
| A: gratis y local | Script propio en Python (`google-api-python-client`, OAuth de escritorio con `youtube.upload` y `youtube.readonly`/`yt-analytics.readonly`) que sube **privado + `publishAt`**, pone miniatura, capítulos, lista de reproducción y "AI use"; más YouTube Studio para Test & Compare y revisión final | 0 USD, cuota sobrada, corre en macOS (Python puro). Studio hace lo que la API no hace (Test & Compare es solo escritorio en Studio) | 5 a 10 (supuesto): revisar video privado en Studio, confirmar la programación, mirar el reporte semanal |
| B: gratis con límites / bajo costo | Lo mismo que A + **vidIQ gratis** (150 créditos de IA/mes) o **Metricool gratis** (1 marca, 20 posts/mes) solo como extras | Aportan ideas o calendario multired, no la publicación de YouTube larga | +0 a 5 |
| C: pago | **vidIQ Boost 19 USD/mes** o **TubeBuddy Pro/Legend** | Solo si se prueba que mueven CTR; no son necesarios para publicar ni medir | +5 a 10 (supuesto) |

**Qué automatiza la etapa**: subida, metadatos, programación, miniatura, capítulos, lista de reproducción, divulgación de contenido sintético, y descarga de métricas. **No automatizable** (decisión humana): la revisión de que el video no es contenido inauténtico, la respuesta a comentarios y la lectura del Test & Compare. **Cuenta 5 a 10 minutos humanos por video** para esta etapa (supuesto: no medido todavía).

---

### 2. Catálogo de candidatos

Costo en dinero / tiempo de máquina / minutos humanos van por separado. Tiempo de máquina de subida: depende de la red, un archivo de ~1-3 GB tarda minutos de subida resumable (supuesto, no medido).

| # | Herramienta | Tipo | Dinero | Tiempo de máquina | Min. humanos | Licencia y uso comercial | Apple Silicon | Calidad y defectos | Idiomas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **YouTube Data API v3** (`videos.insert`, `thumbnails.set`, `playlistItems.insert`, `videos.update`) | API | 0 USD. Cuota por defecto: 100 `videos.insert`/día (1 unidad) + 10.000 unidades/día resto; `thumbnails.set` 50, `playlistItems.insert` 50, `videos.update` 50, `captions.insert` 400 | Minutos de subida (supuesto) | 2 a 5 una vez montado (supuesto) | Sujeto a YouTube API Services Terms y Developer Policies; cuotas extra solo tras auditoría | Sí, es HTTP (cualquier cliente) | Resumible, reintentos recomendados con backoff en 500/502/503/504 | Metadatos multi-idioma | web, https://developers.google.com/youtube/v3/determine_quota_cost y https://developers.google.com/youtube/v3/guides/uploading_a_video, 2026-11-01 |
| 2 | **google-api-python-client + google-auth-oauthlib** | Librería Python | 0 USD | n/a | n/a | No verifiqué la licencia en esta investigación (el ejemplo oficial lo usa). Marca: licencia **no verificada** | Sí (Python puro) | El ejemplo oficial es antiguo ("Python 2.5 o superior" en la página) pero la librería sigue vigente | n/a | web, https://developers.google.com/youtube/v3/guides/uploading_a_video, 2026-11-01 |
| 3 | **YouTube Studio** (programación, Test & Compare, "AI use", capítulos) | Servicio | 0 USD | n/a | 3 a 8 si es manual | Términos de YouTube | Navegador | Test & Compare: hasta 3 títulos o miniaturas, gana por **tiempo de visualización** (no CTR), solo escritorio, termina en ~2 semanas, no sirve para Shorts, Premieres ni videos para niños; cambiar título/miniatura durante la prueba la detiene | n/a | web, https://support.google.com/youtube/answer/13861714, 2026-11-01 |
| 4 | **YouTube Analytics API** (`reports.query`) | API | 0 USD | Segundos | 0 una vez automatizado | Términos de la API | Sí (HTTP) | Tiene `views`, `estimatedMinutesWatched`, `averageViewDuration`, `averageViewPercentage`, `subscribersGained`; retención con `elapsedVideoTimeRatio` + `audienceWatchRatio`/`relativeRetentionPerformance` (un solo video por consulta); ingresos con `yt-analytics-monetary.readonly`. Impresiones y CTR no figuran en lo leído. Cuota de Analytics: **no verificada** | n/a | web, https://developers.google.com/youtube/analytics/channel_reports y https://developers.google.com/youtube/analytics/metrics, 2026-11-01 |
| 5 | **YouTube Reporting API** (reportes masivos) | API | 0 USD | Los reportes se generan por lotes; disponibilidad y retención de datos **no verificadas** | 0 una vez montado | Términos de la API | Sí | `channel_reach_basic_a1`: impresiones y CTR por video/día; `channel_basic_a3`: vistas, `watch_time_minutes`, `subscribers_gained`. No hay informe de retención dedicado (solo duración media y porcentaje medio) | n/a | web, https://developers.google.com/youtube/reporting/v1/reports/channel_reports, 2026-11-01 |
| 6 | **CSV de YouTube Studio** (importación manual) | Manual | 0 USD | n/a | 2 a 3 (supuesto) | n/a | Navegador | Es lo que el propietario ya usa (`importar-ctr`); con pocas vistas la columna de impresiones salió vacía | n/a | medido, `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md` |
| 7 | **vidIQ** | Servicio / extensión | Gratis: 0 USD con 150 créditos IA/mes. Boost 19 USD/mes (199/año). MAX 49 USD/mes (468/año) | n/a | 5 a 10 si se usa | Términos comerciales de vidIQ (no revisados); no sube videos | Navegador | Ideas, tendencias, coach IA; trae un servidor MCP en todos los planes que consume créditos. No es publicador | Inglés principalmente (supuesto) | web, https://vidiq.com/pricing/, 2026-11-01 |
| 8 | **TubeBuddy** | Servicio / extensión | La página no mostró precios ni los límites del plan gratis (marcadores vacíos). Planes Pro, Star, Legend; 20 % de descuento anual; 50 % con el cupón RisingStarBuddy si <1.000 suscriptores. **Precio no verificado** | n/a | 5 a 10 si se usa | No disponible para canales de más de 50.000 suscriptores ni empresas; licencia por canal | Navegador | Legend trae pruebas A/B y seguimiento de ranking; las pruebas A/B ya existen gratis en Studio | n/a | web, https://www.tubebuddy.com/pricing, 2026-11-01 |
| 9 | **Metricool** | Servicio | Gratis: 1 marca, 20 posts programados/mes, 30 días de analítica, 5 competidores. Starter desde 20 USD/mes (anual) o 25 (mensual) | n/a | 3 a 5 | Términos de Metricool (no revisados) | Navegador | Programador multired con YouTube; si programa video largo vía API de YouTube **no se verificó** (la página no lo dice) | n/a | web, https://metricool.com/pricing/, 2026-11-01 |
| 10 | **Buffer** | Servicio | Gratis: 3 canales, 10 posts programados por canal. Essentials 5 USD/canal/mes, Team 10 USD | n/a | 3 a 5 | Términos de Buffer (no revisados) | Navegador | **Solo YouTube Shorts**: su ayuda dice que no soporta videos largos (reporte de búsqueda sobre el artículo oficial de Buffer; la página oficial en sí no se abrió) | n/a | web, https://buffer.com/pricing y https://support.buffer.com/article/562-using-youtube-shorts-with-buffer, 2026-11-01 |
| 11 | **Script propio de automatización** (cron/launchd + Python, o Claude Code) | Local | 0 USD | Segundos de CPU más red | 1 a 2 | Código propio | Sí | Hay que mantener el OAuth y los tokens (ver riesgos) | n/a | supuesto |

Notas de cada fila sobre Buffer: la fila dice "reporte" porque la lectura vino de un resumen de búsqueda; marcada como `tercero` hasta abrir el artículo.

---

### 3. Fichas de las herramientas recomendadas

#### Script propio sobre la YouTube Data API (nivel A)

- **Qué es**: un programa local que sube el MP4 con subida resumable y rellena `snippet` (título, descripción con capítulos, idioma), `status` (`privacyStatus: private`, `publishAt` ISO 8601, `selfDeclaredMadeForKids`, `containsSyntheticMedia`) y luego llama a `thumbnails.set` y `playlistItems.insert`.
- **Reglas verificadas**:
  - `publishAt` solo se puede fijar si el video está `private`; al actualizar hay que reenviar `privacyStatus: private`; una hora pasada publica de inmediato. (web, https://developers.google.com/youtube/v3/docs/videos, 2026-11-01.)
  - Si se omite `privacyStatus`, el video sale público por defecto (algunas cuentas privado). Subir siempre con el campo explícito. (misma fuente.)
  - `containsSyntheticMedia` existe en `videos.insert` y `videos.update` (entrada del historial del 2024-10-30). (web, https://developers.google.com/youtube/v3/revision_history.)
  - Miniatura: máximo 50 MB desde 2026-09-14, JPEG o PNG, 50 unidades. (web, https://developers.google.com/youtube/v3/docs/thumbnails/set y revision_history.) Ojo: la API devuelve 403 si la cuenta no tiene permiso de miniaturas personalizadas; el requisito de verificación del canal **no aparece en esa página**, sí suele exigirlo Studio (no verificado aquí).
  - Capítulos: lista de marcas de tiempo en la descripción; la primera en 00:00, mínimo 3, cada capítulo de al menos 10 s; sustituyen a los automáticos. Son texto, así que se generan desde el guion sin API aparte. (web, https://support.google.com/youtube/answer/9884579, 2026-11-01.)
  - Presupuesto de cuota por video (web + cálculo): insert 1 (cubo propio) + miniatura 50 + lista 50 + update 50 = ~150 unidades del cubo de 10.000; con subtítulos propios (`captions.insert`, 400) ~550. Sobra para decenas de videos por día.
- **OAuth**: alcance `https://www.googleapis.com/auth/youtube.upload` para subir (permite subir al canal y nada más). (web, guía de subida.) Un proyecto de Google Cloud con tipo de usuario externo y estado "Testing" recibe un refresh token que **caduca a los 7 días** (web, https://developers.google.com/identity/protocols/oauth2, 2026-11-01). Para un script desatendido hay que dejar la app en estado de producción (con pantalla de "app no verificada" para uno mismo) o aceptar re-autorizar cada semana. El límite de 100 usuarios de prueba y la necesidad de verificación para un solo usuario propietario **no se verificaron** (la página leída no los menciona).
- **Riesgos**: el bloqueo a privado (hallazgo 3), tokens caducados que dejan la programación sin ejecutarse, y subir con "No" en AI use un video con voz sintética realista de otra persona.

#### YouTube Studio: Test & Compare y revisión (nivel A)

Sin API. Se usa con el video ya subido; 3 minutos humanos para iniciar la prueba. Con un canal pequeño habrá pocas impresiones, así que las pruebas pueden quedar "Inconclusive" (supuesto razonado a partir de la regla de que termina por impresiones; el propietario midió que con pocas vistas el CTR es ruidoso: medido, stack de miniaturas).

#### YouTube Analytics API + Reporting API (nivel A)

- **Retención y duración**: `reports.query` con `dimensions=elapsedVideoTimeRatio`, filtro `video==ID`, métricas `audienceWatchRatio` y `relativeRetentionPerformance`. Una consulta por video.
- **Horas de reproducción y suscriptores** para los hitos del YPP: `estimatedMinutesWatched` / 60 y `subscribersGained` por día. Ojo: las "horas calificadas" del YPP no tienen por qué coincidir con las horas totales de la API (por ejemplo, las horas del feed de Shorts no cuentan para las 4.000: web, página de elegibilidad); la comprobación oficial es la pestaña de monetización de Studio.
- **Impresiones y CTR**: `channel_reach_basic_a1` en la API de Reporting (hay que crear un "reporting job" y esperar a que se generen los lotes; el retraso no se verificó).
- **Ingresos**: `estimatedRevenue` requiere el alcance `yt-analytics-monetary.readonly` y se ajusta a fin de mes. (web, métricas de Analytics.)

#### vidIQ gratis o Metricool gratis (nivel B, opcional)

- vidIQ gratis: ideas de contenido y coach de IA con 150 créditos al mes; no publica ni reemplaza el script. Su MCP puede integrarse con agentes pero cada llamada gasta créditos.
- Metricool gratis: calendario para 1 marca y 20 posts/mes; sirve si algún día se reparte el contenido en otras redes. No se recomienda para la publicación larga de YouTube hasta comprobar que programa videos largos.

---

### 4. Riesgos de política y de derechos

- **Contenido inauténtico (YPP)**: la política renombrada el 2025-07-15 excluye contenido "mass-produced, generic, repetitive" y menciona expresamente "AI-generated content built on generic or unoriginal templates", presentaciones de imágenes y texto con poca narrativa. Permite mismas intro/outro y series con historias distintas. (web, https://support.google.com/youtube/answer/1311392, 2026-11-01.) Un canal "sin rostro" con narración de IA y imágenes generadas es exactamente el perfil que se revisa al pedir la monetización; automatizar la **publicación** no es el riesgo, automatizar la **originalidad** sí. Esto exige una revisión humana mínima de cada video.
- **Divulgación de contenido alterado o sintético**: se exige para contenido realista (persona real diciendo algo que no dijo, evento o lugar real alterado, escena realista que no ocurrió, música como foco). **No** se exige para: guion, esquema, miniatura, título o infografía asistidos por IA; animación o escenas irreales; mejoras técnicas de audio; clonar la propia voz para locuciones. Se marca en Studio, sección Atributos, "AI use", o con `status.containsSyntheticMedia` por API. (web, https://support.google.com/youtube/answer/14328491, 2026-11-01.) Una narración con voz sintética genérica no suplanta a una persona real, por lo que normalmente no requiere el sí; imágenes fotorrealistas de **eventos históricos o personas reales** sí lo requieren. Decisión por video, hecha por el humano.
- **Cuota y auditoría**: pedir más cuota exige una auditoría de cumplimiento; no es necesario con el uso previsto (web, https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
- **Términos 2027**: hay que aceptar los módulos nuevos de monetización en Studio antes del 2027-01-31 o se pierden ingresos de esas funciones desde 2027-02-01 (web, página de elegibilidad; NewsShooter, tercero). Aplica a cuentas ya en el YPP.
- **Programación y bots**: no encontré una regla oficial que prohíba programar con API; el riesgo es de abuso de cuota, no aplica a este volumen.
- **Terceros**: vidIQ y TubeBuddy exigen conectar el canal con OAuth; concede acceso a datos del canal (privacidad); no revisé sus términos.

---

### 5. Comparación con lo que ya mide el propietario y qué falta medir

- **Medido por el propietario** (`~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md`): un canal, 20 miniaturas, mediana de CTR 2,6 %, con CTR e impresiones importados desde CSV de Studio; la columna de impresiones salió vacía; no hay datos de subida, programación ni retención. No existe en el Foundry un stack de publicación (`stacks/` solo tiene `thumbnails-packaging.md` y `voice-narration.md`).
- **Experimentos baratos que puede correr** (todos sin gasto):
  1. **Probar el bloqueo a privado**: crear un proyecto de Google Cloud, habilitar la API, subir un video corto **privado** con el script y comprobar si Studio muestra el aviso de "locked". Responde el hallazgo 3 en 15 minutos. (No lo ejecuté: el brief prohíbe crear cuentas y proyectos.)
  2. **Medir la caducidad del token**: dejar la app en "Testing" y comprobar a los 8 días si el token falla; luego pasar a producción y repetir.
  3. **Reportes de alcance**: crear un job `channel_reach_basic_a1` y anotar cuántas horas tardan los primeros datos con el canal nuevo.
  4. **Retención real**: ejecutar `audienceWatchRatio` en el primer video y registrar el resultado en el Foundry como dato `medido`.
  5. **Horas calificadas frente a la API**: cada semana comparar `estimatedMinutesWatched/60` con el contador de Studio.
- **Minutos humanos de la etapa**: hoy no hay dato `medido`; las cifras de este documento son `supuesto` hasta cronometrar tres videos.

---

### 6. Unknowns y fuentes

#### Unknowns

1. Si el bloqueo a privado de proyectos no verificados sigue activo (docs de desarrolladores dicen que no; la ayuda de Studio y el historial dicen que existió).
2. Si un proyecto externo en producción con el alcance `youtube.upload` necesita verificación de la app de Google para un único usuario propietario, y el límite de 100 usuarios; la página de OAuth leída no lo dice.
3. Cuota y límites de la YouTube Analytics API y retraso/retención de los reportes de la Reporting API.
4. Si el anuncio de 8.000 horas del blog MENA coincide con el blog global y con cómo se aplica a un canal que ya reúne 1.000 suscriptores y 4.000 horas antes del 2027-02-01 pero solicita después.
5. Precios y plan gratis de TubeBuddy (la página mostró marcadores vacíos); licencias y términos de vidIQ, TubeBuddy, Metricool y Buffer; si Metricool programa videos largos de YouTube.
6. Licencia de `google-api-python-client` y requisito de canal verificado para miniaturas personalizadas.

#### Tabla de fuentes

| Fuente | URL | Acceso |
|---|---|---|
| Costos de cuota de la API | https://developers.google.com/youtube/v3/determine_quota_cost | 2026-11-01 |
| Historial de revisiones de la API | https://developers.google.com/youtube/v3/revision_history | 2026-11-01 |
| Recurso `videos` | https://developers.google.com/youtube/v3/docs/videos | 2026-11-01 |
| `videos.insert` | https://developers.google.com/youtube/v3/docs/videos/insert | 2026-11-01 |
| `thumbnails.set` | https://developers.google.com/youtube/v3/docs/thumbnails/set | 2026-11-01 |
| Guía de subida | https://developers.google.com/youtube/v3/guides/uploading_a_video | 2026-11-01 |
| Auditoría y cuota extra | https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits | 2026-11-01 |
| Formulario de auditoría | https://support.google.com/youtube/contact/yt_api_form | 2026-11-01 |
| Ayuda: videos bloqueados por API no verificada | https://support.google.com/youtube/answer/7300965 | 2026-11-01 |
| OAuth 2.0 de Google (caducidad de tokens) | https://developers.google.com/identity/protocols/oauth2 | 2026-11-01 |
| Elegibilidad al YPP | https://support.google.com/youtube/answer/72851 | 2026-11-01 |
| Anuncio de cambios al YPP (blog Google MENA, 2026-08-11) | https://blog.google/intl/en-mena/product-updates/connect-communicate/new-opportunities-to-earn-and-changes-to-the-youtube-partner-program/ | 2026-11-01 |
| NewsShooter (tercero) | https://www.newsshooter.com/2026/08/10/youtube-updates-its-partner-program/ | 2026-11-01 |
| Contenido inauténtico | https://support.google.com/youtube/answer/1311392 | 2026-11-01 |
| Divulgación de contenido alterado o sintético | https://support.google.com/youtube/answer/14328491 | 2026-11-01 |
| Test & Compare | https://support.google.com/youtube/answer/13861714 | 2026-11-01 |
| Capítulos | https://support.google.com/youtube/answer/9884579 | 2026-11-01 |
| Analytics API, informes de canal | https://developers.google.com/youtube/analytics/channel_reports | 2026-11-01 |
| Analytics API, métricas | https://developers.google.com/youtube/analytics/metrics | 2026-11-01 |
| Reporting API, informes de canal | https://developers.google.com/youtube/reporting/v1/reports/channel_reports | 2026-11-01 |
| vidIQ precios | https://vidiq.com/pricing/ | 2026-11-01 |
| TubeBuddy precios | https://www.tubebuddy.com/pricing | 2026-11-01 |
| Metricool precios | https://metricool.com/pricing/ | 2026-11-01 |
| Buffer precios | https://buffer.com/pricing | 2026-11-01 |
| Buffer: Shorts solo (vía búsqueda; artículo no abierto) | https://support.buffer.com/article/562-using-youtube-shorts-with-buffer | 2026-11-01 |
| Stack de miniaturas del propietario (medido) | `~/Foundries/david-youtube-foundry/stacks/thumbnails-packaging.md` | 2026-11-01 |
