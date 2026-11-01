# Etapa 03: Visuales (imágenes IA, footage y archivo libre, mapas y líneas de tiempo, animación, video IA)

Fecha de consulta: 2026-11-01. Los datos `web` caducan a los 90 días (2027-01-30). Hardware de referencia: Mac Apple M4 Max, 64 GB, GPU `mps`/Metal, sin CUDA. Nadie instaló ni descargó nada para este informe; todo es lectura de fuentes.

Tipos de dato: **medido** (corrida real del propietario), **web** (fuente oficial leída hoy), **tercero** (blog, agregador, reseña, no oficial), **supuesto** (mío, con razón).

---

## 1. Resumen y recomendación

**Qué automatiza la etapa:** del guion con marcas de escena a un conjunto de planos (stills con movimiento, footage libre, mapas, clips IA) listos para el editor. La parte que NO se automatiza sola es la revisión humana de derechos y de marcas registradas en cada imagen generada (el Foundry ya lo midió con `gemini-image`: apareció el logo real de L.L.Bean).

**Cantidad necesaria (supuesto):** 20 a 28 min de video = 1.200 a 1.680 s. Con un plano nuevo cada 7 a 10 s (ritmo documental con movimiento Ken Burns) son **120 a 240 planos**. Reparto propuesto: ~60 % stills generados, ~25 % archivo/footage libre y mapas, ~10 % animación simple (líneas de tiempo, mapas), ~5 % clips IA. Para estimar costos uso **150 planos únicos** por video, con 1,3 intentos por plano aceptado (supuesto) ≈ 200 generaciones.

### Tabla de decisión

| Nivel | Recomendación | Por qué | Dinero por video (supuesto sobre datos citados) | Máquina por video | Minutos humanos por video (supuesto) |
|---|---|---|---|---|---|
| **A: gratis/local** | **mflux (MLX) con FLUX.2 klein 4B (Apache-2.0)** para stills; **Pexels/Pixabay/NASA/NOAA/Wikimedia/LoC/Smithsonian/Internet Archive** para footage y archivo; **Natural Earth + ffmpeg/Manim** para mapas y líneas de tiempo | Licencia comercial clara (Apache-2.0 en el modelo y MIT en mflux), nativo de Apple Silicon, 0 USD de API | 0 USD | Stills: ~1,5 a 2,5 h si 25 a 40 s por imagen (supuesto; ver 2, no hay medición M4 Max). Corre sin supervisión de noche | 25 a 35 (revisar 150 planos en una cuadrícula de contactos, descartar defectos y marcas, aprobar licencias del archivo) |
| **B: gratis con límites / bajo costo** | **Gemini Image "Nano Banana 2.1" por API (ya en el stack)**: ~0,034 USD por imagen 1K; con `gemini-3.1-flash-image-preview` medido en 0,067 USD. Complemento: Cloudflare Workers AI FLUX.1 schnell (10.000 neuronas/día gratis) para borradores | Mejor adherencia al prompt y a referencias de personaje, sin tiempo de máquina local; el propietario ya lo tiene integrado | ~7 a 14 USD (150 a 200 imágenes × 0,034 a 0,067) | ~10 a 20 min de espera de red | 20 a 30 |
| **C: pago** | **Clips IA con Veo 3.1 Fast/Lite (0,05 a 0,12 USD/s, tercero)** solo para el ~5 a 10 % del metraje que no se puede cubrir con stills ni archivo | Es lo único que da movimiento real; el costo escala con los segundos, así que se acota | +6 a 22 USD por 2 a 3 min de clip aceptado, ×2 a ×3 por clips rechazados (supuesto) | Mínima | +10 a 15 (ver cada clip) |

**Minutos humanos totales de la etapa a contar: 25 a 35 (nivel A) o 20 a 30 (B); +10 a 15 si hay clips IA (C).** Esto consume entre un tercio y la mitad del presupuesto de 60 min por video de NicheRadar, así que la etapa no es "casi gratis" en tiempo humano: la compuerta se gana o se pierde en cuánta revisión se pueda automatizar (cuadrícula de contactos, filtros de marca, lista de licencias generada por script).

**Veredicto de consistencia visual:** el riesgo real no es calidad por imagen sino coherencia entre 150 planos. Solución recomendada (supuesto, a validar con el experimento 5.1): un bloque de estilo fijo en cada prompt + semilla/LoRA de estilo + referencias de personaje (Nano Banana acepta imágenes de referencia; FLUX.2 y Qwen Image tienen modos de edición con referencia en mflux). Un estilo ilustrado/gráfico (grabado, collage, acuarela) oculta mejor las variaciones que el fotorrealismo, y además reduce el riesgo de divulgación (ver 4).

---

## 2. Catálogo de candidatos

Costos de dinero, tiempo de máquina y minutos humanos van por separado. "Tiempo de máquina" es por video típico (~4.700 palabras, 18 a 28 min) salvo que se diga otra cosa.

### 2.1 Generación de imágenes

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

### 2.2 Generación de video IA

| # | Herramienta | Tipo | Costo | Límites | Min. humanos | Licencia/uso | Notas | Dato y fuente |
|---|---|---|---|---|---|---|---|---|
| 11 | **Veo 3.1 Lite / Fast / Standard** (Gemini API) | API | Lite 0,05 USD/s (720p), 0,08 (1080p); Fast 0,10 / 0,12 / 0,30 (4K); Standard 0,40 / 0,60. Sin nivel gratis | por segundo de salida. Un video 100 % IA de 20 min = 60 a 144 USD en Lite/Fast, más descartes | 10 a 15 | No verificado oficialmente | La página oficial de precios que leí **no lista Veo**; cifras de terceros. Un tercero dice que los endpoints preview vencían el 2026-10-22: **verificar los IDs vigentes** | tercero: https://the-decoder.com/googles-veo-3-1-lite-cuts-video-generation-costs-by-more-than-half/ ; https://benchlm.ai/md/media-pricing/veo.md (2026-11-01) |
| 12 | Gemini Omni Flash (video) | API | ~0,10 USD/s (5.792 tokens de salida por s a 17,50 USD/M) | pago, sin gratis | 10 a 15 | No verificado | | web: https://ai.google.dev/gemini-api/docs/pricing (2026-11-01) |
| 13 | Kling, Runway Gen-4.5, Hailuo, Seedance (agregadores como fal.ai) | API | rango tercero 0,03 a 0,15 USD/s; Runway Gen-4.5 0,12 USD/s | créditos de prueba, no confirmados | 10 a 15 | No verificado | Los clips fallidos también consumen créditos | tercero: https://www.atlascloud.ai/blog/cheapest-ai-video-generation-api-2026 (2026-11-01) |
| 14 | **LTX-2.3 / Wan 2.2 en Mac (MLX)** | local | 0 USD | M1 Max 64 GB: LTX-2 ~7 min para 1,3 s; Wan 2.2 GGUF 82 min para 2 s (tercero). LTX-2.3 completo pesa ~66 GB (necesita ≥64 GB; justo en este Mac), cuantizado a 4 bits cabe en 32 GB. Sin cifra M4 Max verificada | 10 a 15 | Licencias de pesos **no verificadas** | Impracticable para más de 1 a 3 clips de pocos segundos por video | tercero: https://lilting.ch/en/articles/ltx2-wan22-mac-local-video-gen ; https://github.com/Blaizzy/mlx-video |
| 15 | Higgsfield (conector disponible en la sesión) | servicio | no leí precios | no autenticado, no se usó | | | Solo se menciona porque hay un conector; sin datos | no verificado |

### 2.3 Footage, archivo y datos de dominio público o licencia libre

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

### 2.4 Mapas, líneas de tiempo y animación simple

| # | Herramienta | Tipo | Costo | Licencia | Notas | Fuente (2026-11-01) |
|---|---|---|---|---|---|---|
| 25 | **Natural Earth** (datos) | local | 0 USD | Dominio público, uso comercial permitido sin atribución; algunos componentes son de terceros con licencia propia a Natural Earth | Base ideal para mapas animados con Python/ffmpeg | web: https://www.naturalearthdata.com/about/terms-of-use/ |
| 26 | **OpenStreetMap** (datos) | local/API | 0 USD | ODbL: atribución obligatoria; obras derivadas bajo la misma licencia; **OSM no ofrece tiles gratis a terceros** | Usar datos descargados, no tiles públicos | web: https://www.openstreetmap.org/copyright |
| 27 | **Remotion** (video por código React) | local | 0 USD si individuo, no lucrativa o empresa lucrativa de **3 o menos empleados**; Creators 25 USD/asiento/mes | licencia propia (no OSI) | Líneas de tiempo y gráficos reproducibles; licencia cambia en Remotion 5.0 | tercero (búsqueda): https://www.remotion.dev/docs/pricing (el texto de licencia no se pudo leer en la página) |
| 28 | **ffmpeg (zoompan) / Manim** | local | 0 USD | licencias no verificadas aquí (ffmpeg LGPL/GPL, Manim MIT, según mi conocimiento previo; **no verificado hoy**) | Ken Burns sobre stills y animación 2D programática | supuesto |

---

## 3. Fichas de las recomendadas

### 3.1 mflux + FLUX.2 klein 4B (nivel A, stills)
- **Qué es:** port MLX de modelos de difusión; MIT. README: `uv tool install --upgrade mflux`; CLI como `mflux-generate-flux2 ... -q 8`; API Python `generate_image(prompt, seed, num_inference_steps, width, height)`. Fuente: https://github.com/filipstrand/mflux.
- **Integración:** un script que lea las escenas del guion (JSON), construya el prompt = bloque de estilo fijo + descripción de escena + semilla derivada de la escena, y genere en lote nocturno. Reanudable: saltar archivos existentes.
- **Límites:** sin medición propia en M4 Max; el nombre exacto del comando cambió entre versiones (un tercero menciona que la ruta genérica falló y requirió `mflux-generate-flux2`); requiere mflux ≥ 0.16.0 según una tarjeta de terceros. Descargar pesos requiere cuenta/aceptación en Hugging Face (no hecho aquí).
- **Riesgos:** la licencia Apache-2.0 cubre los pesos, no garantiza que el modelo no reproduzca marcas, rostros o estilos de artistas; la revisión humana sigue siendo necesaria.

### 3.2 Gemini Image por API (nivel B, ya en el stack)
- **Qué es:** HTTP directo, sin SDK, medido en `canal-historias`. Pasar de `3.1 Flash Image` (0,067 USD) a `Nano Banana 2.1` (0,0336 USD) reduciría el costo a la mitad según la tabla oficial; **no probado**.
- **Integración:** misma que arriba, con el costo parcial contabilizado si falla (defecto ya corregido en el canal).
- **Límites:** el costo no se puede estimar antes de la llamada (medido); sin nivel gratis de API; Gemini 2.5 Flash Image se retira el 2027-03-15 (web).
- **Riesgos:** logos reales; SynthID (marca invisible) significa que YouTube puede etiquetar el contenido aunque el creador no lo declare (ver 4); términos de salida sin verificar en fuente oficial.

### 3.3 Archivo libre con API (Pexels, Smithsonian, Wikimedia, NASA, LoC, Internet Archive)
- **Qué es:** un módulo de búsqueda que, por escena, consulta 3 a 4 fuentes, filtra por licencia (solo CC0/PD/CC BY o equivalentes), descarga y escribe una **hoja de atribuciones** con URL, licencia y fecha.
- **Automatiza:** búsqueda y ranking por palabras clave; **no automatiza** el juicio de relevancia ni la confirmación de derechos de personas retratadas (minutos humanos).
- **Límites:** Pexels 200/hora y 20.000/mes; LoC 20/min con bloqueo de 1 h; Pixabay caché 24 h.
- **Riesgos:** material de stock repetido entre canales; ítems "de dominio público" con derechos de terceros en NASA y NOAA.

### 3.4 Veo 3.1 Lite/Fast (nivel C, clips IA)
- Solo para planos imposibles de cubrir (reconstrucciones animadas, movimiento). Presupuestar con tope por video (por ejemplo, 2 min = 6 a 14 USD en Lite/Fast sin descartes). Confirmar IDs de modelo vigentes antes de integrar.

---

## 4. Riesgos de política y de derechos

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

## 5. Comparación con lo medido por el propietario y qué falta medir

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

## 6. Unknowns

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

## Tabla de fuentes (acceso 2026-11-01)

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
