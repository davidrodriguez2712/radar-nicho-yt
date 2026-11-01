# 06 Música, efectos de sonido y subtítulos/transcripción

Fecha de consulta: 2026-11-01. Tipos de dato: medido / web (caduca a 90 días, es decir 2027-01-30) / tercero / supuesto. Hardware de referencia: Mac M4 Max 64 GB. No se instaló ni descargó nada; todo es lectura de fuentes.

Punto de partida del Foundry: solo existe `whisperx.md` (estado experimental, un canal, inglés). No hay ficha de música ni de SFX; esa parte es campo nuevo.

## 1. Resumen y recomendación

| Nivel | Música | SFX | Subtítulos / transcripción | Traducción (canal ES) |
|---|---|---|---|---|
| A: gratis y local | Biblioteca de YouTube Audio Library (descarga manual, sin API) + Pixabay Music como respaldo; mezcla y ducking con ffmpeg (`sidechaincompress`) | Audio Library SFX + Freesound CC0 | **mlx-whisper** (large-v3-turbo) para transcribir; alineación con **WhisperX** sobre el guion real (ya medido); salida .srt/.vtt generada por código desde los tiempos por palabra | Argos Translate (MIT/CC0, offline) como borrador; LLM si se acepta costo |
| B: gratis con límites o bajo costo | Uppbeat (plan gratis con límites; condiciones sin verificar) o Suno Pro/Premier (comercial solo con descarga dentro del cupo) | Freesound con API (requiere cuenta, no verificado) | whisper.cpp con Core ML si se prefiere un binario sin Python | LLM por API para traducir el .srt conservando tiempos |
| C: pago | Epidemic Sound / Artlist (no verificado, sin acceso a las páginas) | Epidemic/Artlist (no verificado) | No se necesita | Servicios de traducción de pago, no se necesitan |

Recomendación por nivel: **A = YouTube Audio Library + mlx-whisper/WhisperX**; **B = Uppbeat o Suno Pro (solo si se quiere música a medida)**; **C = no recomendable en esta etapa**, porque A resuelve el problema.

Automatización: subtítulos 100 % automáticos (supuesto razonable, el propietario ya automatizó WhisperX). La música es el cuello de botella: la Audio Library no tiene API pública conocida (no se halló en esta investigación), así que elegir y descargar pistas es manual salvo que se arme una biblioteca previa reutilizable. Estrategia: **curar una sola vez 15 a 25 pistas por canal** (una hora humana, una vez) y después asignarlas por código según estado de ánimo. Minutos humanos por video: **0 a 3** con biblioteca curada (supuesto); 10 a 15 si se elige pista a mano en cada video (supuesto).

## 2. Catálogo de candidatos

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

## 3. Fichas breves

- **YouTube Audio Library**: la opción más segura frente a reclamos. Se integra a mano: descargar MP3, guardar en una carpeta por estado de ánimo con un JSON de metadatos (título, artista, si pide crédito). Si una pista es CC, el pipeline debe agregar el crédito a la descripción por código. Riesgo: sin API hallada, el catálogo se cura una vez.
- **Mezcla y ducking por código**: ffmpeg, filtro `sidechaincompress` (voz como señal de control) o `amix` con volumen fijo bajo la voz, más `loudnorm` a un objetivo de volumen. Esto es conocimiento general de ffmpeg y no se verificó contra su documentación en esta corrida (supuesto). Costo: segundos de máquina por video.
- **mlx-whisper + WhisperX**: el propietario ya alinea con WhisperX sobre el guion real (medido). Para subtítulos, la ruta recomendada es no transcribir el audio sino usar los tiempos por palabra del guion y escribir el .srt/.vtt por código (el VTT es un formato de texto simple). mlx-whisper queda para transcribir competidores o medir WER donde WhisperX en CPU resulte lento.
- **Suno Pro/Premier**: solo si se quiere música original; exige descargar dentro del cupo y no garantiza copyright. Verificar con política de YouTube (sección 4).

## 4. Riesgos de política y derechos

- **Contenido inauténtico** (política YPP, [soporte YouTube](https://support.google.com/youtube/answer/1311392), 2026-11-01): marca como no permitido el contenido genérico, hecho con plantilla o repetitivo, y las presentaciones de imágenes con poco valor narrativo. Permite intros/outros compartidos si el contenido principal difiere. Para música: no permite compilaciones de canciones de artistas distintos ni cambiar solo tono o velocidad. Implicación: la música de fondo no es el riesgo principal; lo es el conjunto del canal. Un tercero de blogs sugiere que audio autogenerado con imagen estática es el ejemplo típico de demonetización (tercero, sin cita oficial).
- **Divulgación de contenido sintético** ([soporte YouTube](https://support.google.com/youtube/answer/14328491), 2026-11-01): exige divulgar música generada por IA solo cuando es el foco principal del video; no exige divulgar subtítulos/captions, scripts, ni clonar la propia voz. Música de fondo generada por IA no queda claramente cubierta: **no verificado**; en la duda, divulgar.
- **Content ID**: YouTube garantiza ausencia de reclamos solo para la Audio Library. Para Pixabay, FMA y Uppbeat no se verificó política sobre reclamos. Incompetech entrega ISRC por pista para disputar. Guardar siempre el comprobante de licencia (URL y fecha) por pista.
- **¿Es monetizable la música IA?** Suno: solo en planes Pro/Premier y por descargas dentro del cupo. MusicGen: pesos NC, no usar. Stable Audio Open: depende de la licencia comunitaria de Stability, no leída.
- **Atribución**: CC BY (Audio Library CC, Incompetech, Freesound) exige crédito; automatizar su inserción en la descripción.
- **Traducción**: NLLB está prohibido para uso comercial; Argos es libre.

## 5. Comparación con lo medido y qué falta medir

Medido (de `whisperx.md`): WhisperX local, 0 USD, un canal, inglés; alinear sobre el texto del ASR es un error, hay que alinear el guion real; fijar el idioma; normalizar puntuación para el WER. No hay medición de música, SFX, ni de subtítulos en español.

Experimentos baratos:
1. Cronometrar mlx-whisper large-v3-turbo contra WhisperX en CPU sobre un audio de 20 min en el M4 Max (resultado: segundos por video).
2. Generar .srt y .vtt desde los tiempos del guion y comprobar que YouTube los acepta (cargar en un video no listado).
3. Curar 20 pistas de la Audio Library, aplicar ducking con ffmpeg y escuchar el resultado; contar minutos humanos reales.
4. Traducir un .srt con Argos al español y revisar 50 líneas a mano para medir la tasa de errores.
5. Subir un video de prueba no listado con pistas de Pixabay y ver si aparece un reclamo.

## 6. Unknowns

- Si la Audio Library tiene API o descarga programable (no se halló).
- Términos, límites y política de Content ID de Free Music Archive, Uppbeat, Epidemic Sound, Artlist y Udio (no accesibles: 429/404 o sin acceso).
- Licencia de mlx-whisper/mlx-examples y de los pesos Whisper en su ficha (no leída).
- Si whisper.cpp emite .srt/.vtt (el README leído no lo dice) y si WhisperX corre con MPS en el M4 Max.
- Velocidad real en M4 Max de cada herramienta (el único dato es de M1 Max y de un tercero).
- Si la música de fondo generada por IA exige divulgación; si Stable Audio Open permite uso comercial en el caso del propietario.
- Calidad de Argos en español de narración larga.

## Tabla de fuentes (acceso 2026-11-01)

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
