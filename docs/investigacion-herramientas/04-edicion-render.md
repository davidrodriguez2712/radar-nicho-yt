# Etapa 04: Edición y render automatizado

Fecha de consulta: 2026-11-01. Alcance: ensamblar audio de narración + imágenes/clips + subtítulos + música en un video final (1080p/4K) por código, sin editar a mano, para videos de ~4.700 palabras (18 a 28 min) en un Mac M4 Max de 64 GB.

Tipos de dato: **medido** (corrida real; aquí solo hay una prueba sintética mía, ver sección 5), **web** (leído en fuente, con URL y fecha; caduca a 90 días), **tercero**, **supuesto**.

---

## 1. Resumen y recomendación

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

## 2. Catálogo de candidatos

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

## 3. Fichas breves

### ffmpeg (recomendada nivel A)
- **Qué es:** el estándar de facto para codificar y filtrar video. Versión local verificada: 9.0.1, compilado con `--enable-libass` y `--enable-libfreetype`, con codificadores `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox`, `libx264`, `libx265` y filtros `zoompan`, `xfade`, `subtitles`, `ass`, `drawtext` (comando `ffmpeg -encoders/-filters` ejecutado en el Mac del propietario, 2026-11-01: **medido**).
- **Integración Python:** `subprocess.run([...])` con un grafo de filtros generado desde un manifiesto JSON (`escenas: [{imagen, inicio, duración, zoom}]`), o la librería `ffmpeg-python` (**no verificada** su mantenimiento). Un solo comando puede: encadenar imágenes con `zoompan` + `xfade`, mezclar la narración con música usando `sidechaincompress`, normalizar con `loudnorm` (el stack de voz ya normaliza a −14 LUFS) e incrustar subtítulos.
- **Efectos:** Ken Burns con `zoompan`; transiciones con `xfade`; lower thirds simples con `drawtext`/`drawbox` o superponiendo un PNG con `overlay`. Los lower thirds animados complejos no son cómodos aquí: usar Remotion o prerenderizar un clip con canal alfa.
- **Subtítulos:**
  - *Incrustados (burn-in):* filtro `subtitles=archivo.srt:force_style=...` o `ass=archivo.ass` (libass). Para estilo "palabra a palabra" conviene generar un `.ass` a partir de los tiempos de WhisperX.
  - *Archivo `.srt` aparte:* se genera desde el mismo alineamiento y se sube a YouTube como pista de subtítulos. Esto es lo recomendable por defecto: YouTube permite activarlos/desactivarlos y el texto es indexable. Incrustarlos solo si se quiere el estilo visual fijo.
- **Calidad y bitrate (medido sintético):** `h264_videotoolbox -b:v 12M` produjo ~90 MB por 60 s de 1080p30 sobre una carta de ajuste muy detallada (≈12 Mb/s, es decir, el bitrate pedido); `libx264 -crf 18` produjo ~75 MB sobre el mismo origen. Para contenido real de imágenes quietas con zoom, el tamaño será muy inferior (el mismo origen estático con zoompan salió en ~1 MB con libx264 CRF 18 por 60 s, **medido**, aunque un fotograma sintético plano no es representativo).
- **Límites:** `zoompan` es de un solo hilo; videotoolbox ofrece menos eficiencia por bit que libx264/libx265 (conocimiento general, **sin fuente aquí**); H.264/HEVC conllevan cuestiones de patentes (ver licencia).
- **Riesgos:** filtergraphs largos son difíciles de depurar; conviene renderizar por escenas y concatenar.

### MoviePy 2.x (A2)
Librería Python (MIT) para componer clips, texto y audio. Buena para prototipar y para efectos programados cuadro a cuadro. Más lenta y con más memoria que ffmpeg directo. Riesgo: la ruptura entre v1 y v2 hace que los ejemplos de internet fallen.

### Editly (A2)
Define el video en JSON (capas `image`, `title`, `subtitle`, transiciones). Cubre Ken Burns y transiciones sin escribir filtergraphs. Riesgo: mantenimiento por una persona y dependencia de `headless-gl`, que puede dar problemas de compilación en macOS (no verificado).

### Remotion (B, solo si hacen falta gráficos)
Video como componentes React; gratis para ≤3 personas. Útil si el canal necesita lower thirds, contadores o gráficos con marca. Hay que contar el coste de escribir y mantener código React y que renderiza con Chromium.

### Shotstack (B, nube)
API JSON de edición con sandbox gratuito y marca de agua. Calcula ~0,10 a 0,20 USD/min; un video de 20 min cuesta 2 a 4 USD **solo en render**. No aporta nada que el Mac no haga gratis; su valor es no depender de la máquina.

### DaVinci Resolve Studio (C)
Solo si se quiere corrección de color y limpieza y se acepta pagar 236 USD. El scripting externo en Python exige Studio (tercero). No reduce minutos humanos frente a ffmpeg y añade dependencia de GUI.

---

## 4. Riesgos de política y de derechos

- **Contenido inauténtico (monetización):** YouTube renombró la política "repetitious content" a "inauthentic content" el 15 de julio de 2025. Señala como problema el contenido que "looks like it's made with a template", presentaciones de imágenes con poca narrativa o valor, y contenido con IA genérica con apariencia de producción en masa. **Permite** repetir intro/outro si la mayor parte del contenido es distinta, y series con elementos recurrentes si cada video tiene historia propia. Implicación para esta etapa: un montaje 100 % idéntico (mismo Ken Burns, misma transición, mismas imágenes de archivo) en cada video es exactamente la señal de "plantilla". **Mitigación:** variar zoom/dirección/ritmo por escena, asegurar que las imágenes sean relevantes al guion, y que el valor original esté en la narración. Fuente: https://support.google.com/youtube/answer/1311392 (acceso 2026-11-01).
- **Divulgación de contenido alterado o sintético:** no verificada en esta etapa (corresponde a las etapas de voz e imagen); se indica aquí por completitud.
- **Música:** la mezcla automatizada exige que la pista tenga licencia comercial. Esta etapa solo la ensambla; el catálogo de música debería tratarse en su propia etapa. **No verificado.**
- **Patentes de códecs:** ffmpeg advierte que H.264/HEVC pueden tener tasas de patentes para quien distribuye productos comerciales (https://ffmpeg.org/legal.html). Subir videos a YouTube no es distribuir un codificador; riesgo bajo, pero no es asesoría legal.
- **Licencia de Remotion:** si el equipo pasa de 3 personas con fines de lucro, exige Company License (mínimo 100 USD/mes en Automators).
- **Marca de agua en sandbox de APIs:** no usar sandbox de Shotstack para videos publicables.

---

## 5. Comparación con lo que ya mide el propietario y qué falta medir

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

## 6. Unknowns

1. **Rendimiento real** con escenas reales (20 min, ~100 imágenes, `xfade`, música): solo hay datos sintéticos.
2. **Calidad por bitrate de `h264_videotoolbox`** frente a `libx264` en contenido real; y cuál bitrate acepta YouTube sin degradar (no leí la recomendación oficial de bitrate de YouTube en esta investigación).
3. **Soporte de Editly/headless-gl y Remotion en arm64** y tiempos de render de ambos: no verificados.
4. **Precio mensual exacto de Creatomate** (la página oficial no mostró importes) y **precios de Remotion** (el widget oficial no cargó; cifras de un resumen de búsqueda sobre remotion.dev).
5. **Licencia de Blender, Kdenlive/Shotcut y MLT por componente**, y términos comerciales de CapCut y Resolve Free: no verificados.
6. **Scripting de Resolve Free** desde el menú: fuentes contradictorias.
7. **Licencia de música** y **política de divulgación de contenido sintético** en el montaje final: fuera del alcance de esta etapa pero necesarias antes de publicar.
8. Si YouTube considera "plantilla" un montaje con variación mínima de Ken Burns: no hay evidencia cuantitativa.

---

## Tabla de fuentes

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
