# Etapa 05: Miniaturas, títulos y packaging

Fecha de consulta: 2026-11-01. Tipos de dato: **medido** (corrida del propietario), **web** (fuente oficial leída hoy; caduca a 90 días, es decir 2027-01-30), **tercero** (blog, agregador), **supuesto** (mío, con razón).
Cobertura: miniatura 1280x720, títulos, descripciones, tags, capítulos, prueba A/B (Test & Compare de YouTube) y medición de CTR. Solo lectura e investigación: no se instaló ni se ejecutó nada.

## 1. Resumen y recomendación

**Hallazgo central.** Esta etapa casi no tiene costo en dinero. Los costos reales son el tiempo humano y el hecho de que nadie ha medido todavía qué miniatura rinde (el Foundry lo dice: CTR mediana 2,6 % en 20 miniaturas, variación casi nula, correlación de texto −0,12 con n = 20, todo `medido` en un canal). La inversión útil no es una herramienta nueva: es **variar ejes a propósito y medir con la prueba A/B nativa de YouTube, que es gratis**.

**Dato que cambia el diseño del experimento.** La prueba A/B oficial de YouTube elige al ganador por **cuota de tiempo de visualización, no por CTR** (web, [support.google.com/youtube/answer/13861714](https://support.google.com/youtube/answer/13861714), 2026-11-01). Esto la hace más segura frente al clickbait, pero el CTR no sale como criterio de decisión. Hay que decidir si el CTR sigue siendo la métrica del canal (ver sección 5).

| Nivel | Recomendación | Por qué |
|---|---|---|
| **A: gratis / local** | **Pillow (composición, ya en el canal) + plantillas de parámetros + FLUX.2 [klein] 4B vía mflux (fondos y elementos, Apache 2.0) + A/B nativo de YouTube (Test & Compare)**. Los candidatos y la crítica los siguen haciendo los agentes `empaquetador` y `critico_empaquetado` | Licencias permisivas verificadas, todo corre en local o es gratis. Pillow ya existe: hay que extenderlo de un molde a varias plantillas, no sustituirlo. mflux es MLX nativo para Mac (web). El A/B es gratis y no necesita tarjeta |
| **B: gratis con límites / bajo costo** | **Nivel A + Gemini 3.1 Flash Lite Image o Nano Banana 2.1 por API para elementos puntuales (0,0336 USD por imagen 1K, 0,0168 en batch) + vidIQ Free solo para investigación de títulos** | Precio verificado en la página oficial. No hay nivel gratis de imagen en la API (web). Se descarta pagar vidIQ o TubeBuddy: lo que dan es investigación, que ya cubre el agente |
| **C: pago** | **thumbnailtest.com Basic (29 USD/mes) o TubeBuddy Legend (A/B)** solo si el A/B nativo resulta insuficiente (por ejemplo, se necesita decidir por CTR) | Son los únicos que ofrecen otro criterio de decisión. Los precios de ambas páginas salieron inconsistentes: confirmar antes de comprar |

**Qué automatiza la etapa.** Generación de 3 candidatos de título y miniatura, composición de las imágenes, crítica, subida de la miniatura (`thumbnails.set`), título, descripción, tags y capítulos por la API de YouTube, y lectura de resultados. **No es automatizable con seguridad** el veredicto editorial final (el Foundry lo exige con el gate G1) ni la revisión visual de marcas registradas en imágenes generadas.

**Minutos humanos por video a contar: 8 a 12 (supuesto).** Desglose: revisar 3 candidatos y confirmar el veredicto editorial (3 a 5), revisar a mano marcas, texto y desborde en la miniatura elegida (2 a 3), lanzar el test en Studio (2; el A/B es solo de escritorio y desde Studio, no vi una vía por API: ver unknowns), leer el resultado a los 3 a 14 días (1 a 2). Sin A/B baja a 5 a 8. Estos minutos son supuesto: ningún canal lo ha medido.

## 2. Catálogo de candidatos

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

## 3. Fichas de las recomendadas o finalistas

### Pillow + plantillas (nivel A, base)
- **Qué es.** Librería Python de imágenes con licencia MIT-CMU (web). Ya compone las miniaturas del canal con un solo molde.
- **Integración.** Una función `componer(plantilla, titulo_corto, rostro, fondo) -> PNG 1280x720`. Cada plantilla es un archivo de parámetros (posición del texto, tamaño, luminosidad del fondo, con o sin rostro). Es lo que permite variar los ejes que el canal quiere probar (cantidad de texto, luminosidad, rostro) sin tocar código.
- **Límites.** Texto sin efectos finos. Si las plantillas necesitan sombras, degradados o capas complejas, Satori ofrece diseño en JSX/CSS, o ImageMagick para lotes.
- **Riesgos.** Bibliotecas de rostros reutilizadas en todos los videos: el Foundry ya midió 58 rostros, casi todos mujeres en angustia. Eso alimenta el riesgo de "contenido interchangeable" (sección 4).

### FLUX.2 [klein] 4B vía mflux (nivel A, fondos)
- **Qué es.** Modelo de imágenes de 4B con licencia Apache 2.0 (web) que corre en MLX con `mflux`, MIT (web). El README lo describe como el más rápido y pequeño con buena calidad y edición (tercero del autor de mflux).
- **Integración.** CLI (`mflux-generate-...`) o API Python, según el README. Se instala con `uv tool install mflux` (web, no ejecutado).
- **Límites.** Sin benchmark propio en el M4 Max. No generar texto en la imagen: el texto lo pone Pillow. Si falla `hf_transfer`, reinstalar con esa dependencia (web).
- **Riesgos.** Marcas registradas y rostros reconocibles aparecen en salidas de modelos de imágenes (el canal lo sufrió con Gemini; en modelos locales **no medido**). Revisión humana obligatoria. No usar el 9B: licencia no comercial (web).

### YouTube Test & Compare / A/B (nivel A y B, medición)
Ver sección 5.

### Gemini Image (nivel B, opcional)
- **Qué es.** API por tokens. Precios actuales en la tabla; el canal ya paga 0,067 USD con el modelo que usa (medido, n pequeño).
- **Opción barata.** Nano Banana 2.1 a 0,0336 USD (1K), la mitad en batch (web). No medido por el propietario.
- **Riesgo.** La licencia de la salida sigue sin determinar. Mientras no se verifique, usar esta ruta solo en elementos sueltos que se transformen mucho, o preferir la ruta local con licencia Apache.

### vidIQ Free (nivel B, investigación)
- **Qué es.** Investigación de tendencias e ideas con 150 créditos de IA al mes (web). Incluye servidor MCP que gasta esos créditos (web).
- **Integración.** MCP, que podría usarse desde los agentes. No verifiqué qué herramientas expone ni si cubre títulos.
- **Límites.** El nivel gratis no incluye la creación de miniaturas (solo Boost, web).

## 4. Riesgos de política y de derechos

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

## 5. Comparación con lo medido y qué falta medir

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

## 6. Unknowns

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

## 7. Tabla de fuentes (todas accedidas el 2026-11-01)

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
