# Etapa 02: Voz y narración

Fecha de consulta: 2026-11-01. Video típico de referencia: ~4.700 palabras, ~26.000 caracteres (supuesto: ~5,5 caracteres por palabra con espacios), 18–28 min.
Tipos de dato: **medido** (corrida del propietario), **web** (fuente oficial leída hoy; caduca a 90 días), **tercero** (agregador/blog/reseña), **supuesto** (mío).
Alcance: solo investigación. No se instaló ni se descargó nada; "corre en Apple Silicon" se apoya en README/issues, no en pruebas mías.

## 1. Resumen y recomendación

La etapa (guion aprobado a audio con tiempo por palabra, verificado y normalizado) ya está casi 100 % automatizada en `canal-historias`. Los minutos humanos reales son: elegir/validar la voz de referencia (una vez por canal), oír una muestra de arranque y atender los retries que falla el gate de WER. **Contar 5 a 10 minutos humanos por video** una vez estabilizado el canal (supuesto: el propietario no midió minutos humanos de voz; ver sección 5).

| Nivel | Recomendada | Por qué | Dinero / video | Máquina / video |
|---|---|---|---|---|
| **A: gratis y local** | **Qwen3-TTS-1.7B-Base** (ya medido) vía `mlx-audio` o PyTorch `mps`, con WhisperX/Whisper para alineación y WER | Apache-2.0 (web), clona voz propia con referencia corta, único local que el propietario midió limpio en 20+ min (WER 0,058). Prueba pendiente: la variante MLX de `mlx-audio` para bajar los 47–90 min | 0 USD | 47–90 min (medido, n pequeño); un atípico de 6 h 40 min (medido, n = 1) |
| **B: gratis con límites o bajo costo** | **Fish Audio por API** (ya medido, 0,41 USD) como principal; **OpenAI `tts-1`** (~0,39 USD, supuesto de cálculo) o **Google Chirp 3 HD / Azure Neural** (nivel gratis mensual de caracteres, tercero) como respaldo sin clonación | Fish: medido, clona, devuelve tiempo por palabra. Google/Azure: cuota gratis mensual alcanzaría varios videos, pero sin clonación propia y sin medir | 0,41 USD (medido) / 0–0,8 USD (supuesto) | Minutos |
| **C: pago** | **ElevenLabs** (Creator 22 USD/mes, web) o **Cartesia Pro** (5 USD/mes, web) | ElevenLabs: voz y ecosistema más maduros, licencia comercial explícita desde Starter. No probado por el propietario. Cartesia: más barato, clonación instantánea desde Pro | 2–5 USD por video con API Flash/v2 (cálculo, ver nota) | Minutos |

Nota de cálculo (supuesto, ~26.000 caracteres): ElevenLabs API 0,04 USD/1K caracteres Flash = ~1,04 USD y 0,08 USD/1K v2 = ~2,08 USD (web); por suscripción, Creator con 121.000 créditos alcanza ~4 videos/mes si 1 crédito = 1 carácter (supuesto, no confirmado en la página).

**Veredicto de la compuerta (60 min humanos máx., 90 % automatización):** la voz no es el cuello de botella. El riesgo de la etapa es el **tiempo de máquina** del nivel A y la **divulgación/inautenticidad**, no los minutos humanos. Un presupuesto que ponga ElevenLabs "por defecto" ignora que el propietario ya produce con 0 USD de API.

## 2. Catálogo de candidatos

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

## 3. Fichas breves

**Qwen3-TTS (nivel A, finalista).** Modelo local de Alibaba, Apache-2.0. Se integra como librería Python (`create_voice_clone_prompt` permite reusar la voz de referencia) o, probablemente más rápido, vía `mlx-audio` (lo lista como modelo soportado). Límites: sin control de velocidad, volumen bajo, el texto debe coincidir con el idioma, el model card no declara longitud máxima de entrada. Riesgo: la corrida atípica de 6 h 40 min con 66–78 GB de memoria; antes de lanzar canales en paralelo hay que medir si el trozo de 450 palabras en MLX evita la fuga. Una guía de tercero advierte que subir el tope de tokens puede activar el watchdog de Metal (riesgo de reinicio del sistema): no subir el tope sin probar.

**Fish Audio (nivel B, finalista).** API con SSE que devuelve audio y tiempo por palabra (medido). Automatizable por completo. Riesgos: bucle de repetición (mitigado con trozos y WER), codificación UTF-8 del stream, contradicción de la página sobre uso comercial en Free: **comprar/usar plan de pago o confirmar por escrito**. Tarifa por millón de bytes no leída aquí.

**ElevenLabs (nivel C).** Referencia comercial, licencia comercial desde Starter, clonación instantánea desde Starter y profesional desde Creator (web). No probado por el propietario. Antes de presupuestarlo, correr el experimento de la sección 5. Su coste mensual no escala bien con varios canales: 121.000 créditos son ~4 videos si 1 crédito = 1 carácter (supuesto).

**Kokoro (nivel A, complemento).** 82M parámetros, Apache-2.0, voces predefinidas. Útil como "voz gratis rápida" sin clonación: sirve para borradores, pruebas de guion y quizá para canales cuya identidad no dependa de una voz propia. Su estabilidad en 20+ min no está medida; cambio de tono en límites de párrafo reportado por tercero.

**MLX-Audio (infraestructura).** Una sola interfaz y servidor local OpenAI-compatible para TTS, STT y alineación con Qwen3-ForcedAligner. Si el propietario migra a MLX puede reemplazar WhisperX (que en Mac corre solo en CPU según su README) por el alineador de mlx-audio: **no probado**, comparar tiempos y exactitud antes.

**Google Chirp 3 HD / Azure Neural / OpenAI tts-1 (nivel B, respaldo).** Sin clonación propia verificada; sirven si el canal acepta una voz de catálogo. Cuota gratis mensual (Google ~1 M caracteres HD, Azure 0,5 M) alcanza ~19–38 videos/mes según el proveedor (cálculo sobre cifras de terceros). Hay que verificar en cada consola; Google exige cuenta de facturación aun en nivel gratis (tercero).

## 4. Riesgos de política y de derechos

1. **Divulgación de contenido sintético (YouTube).** La página oficial exige divulgar contenido realista alterado o sintético, p. ej. cuando "un persona real parece decir algo que no dijo". Lista como **menor, no divulgable**: clonar la **propia voz** para voz en off/doblaje, reparar o mejorar audio y subtítulos. La página dice también que puede etiquetar "audio no musical generado por IA" y que divulgar no limita la audiencia ni la monetización. Lectura (mía, no jurídica): una voz sintética genérica o la voz propia en narración **no** obliga a divulgar; **clonar a otra persona sí**. Fuente: https://support.google.com/youtube/answer/14328491.
2. **Contenido inauténtico (YPP).** Desde 2025-07-15 cubre contenido "repetitivo o producido en masa" y prohíbe contenido IA hecho con "plantillas genéricas o poco originales" y lecturas de material ajeno (feeds de noticias, texto de sitios). La página **no** distingue voz IA de voz humana; lo que se juzga es valor propio (guion, comentario, narrativa). Varios canales con el mismo pipeline y la misma voz son la señal de riesgo. Fuente: https://support.google.com/youtube/answer/1311392. Personas IA como expertos en salud, legal, finanzas o política: sin monetización.
3. **Consentimiento de la voz clonada.** Dia y Sesame prohíben suplantar sin consentimiento (README). ElevenLabs y Cartesia condicionan la clonación a plan y a verificación (web, detalle de los términos no leído). **Regla propia sugerida:** clonar solo la voz del propietario o de un locutor con contrato escrito; nunca voz de terceros. La voz de referencia es identidad del canal.
4. **Licencia de pesos.** F5-TTS (pesos CC-BY-NC) no es usable en un canal monetizado. XTTS-v2 (CPML) y Fish `S2-Pro` (Research License) requieren leer sus textos. Piper es GPL-3.0 (afecta si se redistribuye código, no el audio generado, interpretación mía no jurídica). Qwen3-TTS, Kokoro, Chatterbox (MIT, con marca de agua), Orpheus, Dia, CSM: sin restricción de uso comercial en README, pero las salidas heredan las restricciones de uso prohibido.
5. **Marca de agua.** Chatterbox incrusta PerTh en toda salida. No es un problema de política, pero un tercero puede detectar que el audio es sintético.
6. **Proveedores que desaparecen.** PlayHT cerró (tercero) y borró voces: no depender de un proveedor sin copia local de la voz de referencia.

## 5. Comparación con lo que mide el propietario y qué falta medir

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

## 6. Unknowns

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

## Tabla de fuentes (acceso 2026-11-01 salvo nota)

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
