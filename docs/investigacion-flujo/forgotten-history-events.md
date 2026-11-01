# Dossier de viabilidad: "Forgotten History Events" (YouTube, formato largo, inglés)

Fecha de investigación: 2026-11-01. Formato inspirado en `docs/contracts/dossier-v2.md`. Páginas web tratadas como datos no confiables. No es asesoría legal. Etiquetas: **[V]** verificado en fuente oficial leída hoy; **[E]** estimado o supuesto; **[T]** dato de tercero no verificado.

Punto de partida (NicheRadar, API de YouTube, 2026-10-31/11-01, no se repite el detalle): 25 videos largos, 10 estables / 15 con pico reciente, 11 canales pequeños con un video >=5x sus suscriptores, ingreso mensual estimado por canal estable (mediana) US$1.629–3.724/mes (RPM heredado del nicho padre, estimación).

## 1. Veredicto

**GO CONDICIONADO** — confianza **media-baja**.

Razones: la tracción de canales pequeños medida por NicheRadar es la señal más fuerte. El riesgo principal no es la demanda sino (a) la política de contenido inauténtico/reutilizado si el flujo se vuelve una presentación de imágenes con voz sintética, (b) la exactitud histórica y (c) que mis datos de competidores son de terceros y no pude verificarlos en YouTube.

Condiciones para pasar a la Fase 1: ver sección 6. Condición innegociable: cada video con investigación propia, comentario/análisis original y verificación humana de hechos; sin imágenes de IA realistas de eventos reales.

`unknowns`:
1. Suscriptores, cadencia y vistas reales de los competidores: las páginas de YouTube no devolvieron métricas (solo marco de navegación); las cifras vienen de listados de terceros marcados "legacy / en revisión".
2. RPM real del subnicho "eventos olvidados" (el 2026 heredado del nicho padre es estimación). Sin dato verificado.
3. Precio actual de Canva, Midjourney y OpenAI TTS: las páginas devolvieron 403; no se usan en el presupuesto.
4. Costo real de un editor/verificador freelance: sin fuente; los montos son supuestos del propietario.
5. Si YouTube trata la narración 100% sintética con más escrutinio que voz humana en revisión de YPP: la política leída no lo dice; incertidumbre abierta.
6. Si los canales pequeños con picos usan voz IA, archivo o animación: no verificado.
7. Cuánto tarda la revisión manual de YPP en este nicho.

## 2. Competidores directos en inglés

Nota: ninguna métrica pudo leerse del propio YouTube. Tamaños de la tabla provienen del listado de terceros de 2025-12-10 (marcado legacy, bajo re-revisión) salvo indicación. Todo tamaño y frecuencia es **[T]/[E]**. Lo único **[V]**: que el canal existe y la URL carga.

| Canal | URL | Tamaño aprox. | Frecuencia | Formato | Qué lo haría funcionar |
|---|---|---|---|---|---|
| Little Known History | https://www.youtube.com/@LittleKnownHistory | sin dato | sin dato | Episodios sobre figuras y eventos poco conocidos [T] | Premisa idéntica al subnicho; confirma demanda de "poco conocido" [E] |
| The Forgotten | https://www.youtube.com/@TheForgotten | sin dato | "varias veces por semana" [T, blog] | Documentales largos medievales / Roma [T] | Volumen alto y títulos de lo "mal contado" [E] |
| History's Forgotten People | https://app.thoughtleaders.io/youtube/historys-forgotten-people (ficha de tercero, no el canal) | sin dato | sin dato | Videos largos, hasta ~1 h, figuras olvidadas [T] | Nicho de ángulo biográfico/mujeres [E] |
| Historian Sleepy | sin URL verificada (fuente: listado autonolab) | ~189k [T] | "consistente" [T] | Deep dives de 1,5–3 h [T] | Watch time alto en escucha de fondo/sueño [E] |
| History With Hilbert | sin URL verificada | ~492k [T] | sin dato | Larga duración, historia oscura/etimología [T] | Curiosidad y voz propia [E] |
| Beginning To Now | sin URL verificada | ~288k [T] | sin dato | Documentales de 45–90 min [T] | Profundidad y sesiones largas [E] |
| Chat History | sin URL verificada | ~927k [T] | sin dato | Narración sobre archivo, historia oscura [T] | Imágenes de archivo + narración: el modelo más cercano al flujo propuesto [E] |

Lectura: el listado de terceros muestra canales pequeños (<20k) y medianos (~190k–490k) con formatos largos narrados sobre archivo, coherente con las 11 señales de canales pequeños de NicheRadar. Esto no prueba que sean replicables ni rentables.

## 3. Flujo de producción propuesto

Meta: 1 video/semana de 12–18 min. Precios consultados el **2026-11-01** (dentro de 90 días).

| Etapa | Modo | Herramienta y precio | Min. humanos/video [E] |
|---|---|---|---|
| Selección de tema y ficha de hechos | semi | Datos de NicheRadar + fuentes primarias/enciclopédicas; gratis | 10 |
| Guion | semi | Claude Pro, US$20/mes mensual (US$17 anual, US$200/año) [V], [fuente s5] | 15 (reescribir y añadir análisis propio) |
| Verificación de hechos | manual | Contraste de cada fecha, nombre y cifra con 2 fuentes; gratis | 15 |
| Voz | auto | ElevenLabs Creator: página muestra US$11 promocional y FAQ US$22; se usa US$22/mes, 121.000 créditos (~121 min); licencia comercial desde Starter [V], [s6] | 2 |
| Imágenes/archivo/animación | semi | Library of Congress, Wikimedia Commons, mapas propios; gratis [V] | 10 |
| Edición | semi | DaVinci Resolve gratis; Studio US$236 (promo, antes US$295), opcional [V], [s7] | 8 |
| Miniatura y título | manual | Herramienta gratuita o freelance (supuesto US$10) [E]; Canva sin precio verificado | 5 |
| Publicación | semi | YouTube Studio; incluye ajuste "AI use" si procede [V] | 3 |

Total humano **~68 min/video [E]**. Supera el umbral de compuerta de NicheRadar (60 min). Hay que bajar a <=60 con plantillas y práctica antes de pedir "go"; si no, requiere `gate_override`. Automatización global ~55–65% [E], por debajo del mínimo 90 de la compuerta: **este nicho probablemente falla la compuerta de automatización sin excepción**, y es un punto a decidir por el propietario. El valor del canal está en investigación y exactitud, que no conviene automatizar.

Qué se puede automatizar: borrador de guion desde una ficha de hechos con fuentes (con humano revisando), voz (API/plan), descarga y catalogación de metadatos y créditos de imágenes, ensamblado base de la línea de tiempo, subida con metadatos. Se mantiene humano: elección del ángulo, verificación de hechos, análisis original, selección de imágenes por derechos.

### Derechos del material
- **Library of Congress**: el repositorio no concede derechos; "es obligación del investigador determinar y satisfacer las restricciones" de copyright. "Sin restricciones conocidas" **no** equivale a dominio público. Obras publicadas hace más de 95 años son dominio público en EE. UU.; obras de agencias del gobierno de EE. UU. no tienen copyright. Pedir crédito con "Library of Congress", colección y número de reproducción [V, s3]. Hay que registrar el estatus de cada imagen.
- **Wikimedia Commons**: cada archivo tiene su licencia; la verificación es del usuario; dominio público no exige atribución (se recomienda); CC BY-SA exige crédito y licencia compartida en derivados; pueden aplicar derechos de imagen/marcas [V, s4].
- **Música**: YouTube Audio Library, sin reclamaciones de Content ID; pistas Creative Commons exigen crédito en la descripción [V, s8]. No usar música "royalty-free" de otras fuentes sin licencia propia.
- **Voz sintética**: el plan de ElevenLabs incluye licencia comercial desde Starter [V, s6], con términos finos no leídos (unknown).
- **IA para imágenes**: evitar imágenes realistas de eventos reales: exigen divulgación [V] y arriesgan exactitud y política. Permitido para ilustración claramente no realista, con divulgación según el caso.

`rights.verdict` sugerido: **conditional**: solo material con estatus documentado; nada de `unknown` ni `third_party`.

### Exactitud histórica
Riesgo: alto (alucinación de LLM en fechas, cifras y atribuciones; temas poco conocidos tienen pocas fuentes). Mitigación: ficha de hechos con fuente por afirmación; el LLM solo redacta desde la ficha; verificación humana con 2 fuentes independientes; evitar eventos con una sola fuente; fe de erratas en el comentario fijado; revisar con experto externo los primeros 6 videos; lenguaje de incertidumbre ("según X").

## 4. Política de YouTube vigente

- **Inauthentic content** (antes "repetitious"): renombrada el **2025-07-15** [V, s1]. No es monetizable el contenido repetitivo o producido en masa: videos intercambiables, historias con plantilla, presentaciones de imágenes con poco valor narrativo o educativo, contenido de IA con plantilla sin visión original. Intro y outro iguales están permitidos si el contenido principal difiere.
- **Reused content**: material de otras fuentes sin comentario significativo ni cambios sustanciales; aplica a todo el canal, que puede perder monetización completa [V, s1].
- **Uso de IA**: herramientas automatizadas permitidas, pero "el producto final debe mostrar su visión creativa" [V, s1]. Divulgación obligatoria del contenido sintético realista: persona real diciendo/haciendo algo, metraje alterado de un evento real, escena realista que no ocurrió; **no** hace falta para generar guion, esquema, título o miniatura, ni para clonar la propia voz en narración [V, s2]. La página no muestra fecha de efectividad.
- **YPP**: 1.000 suscriptores y 4.000 horas públicas en 12 meses (o 10M vistas de Shorts en 90 días), más revisión de política del canal completo [V, s9].

Riesgos de monetización: (1) rechazo de YPP por "slideshow con voz sintética" (alto si no hay análisis original), (2) desmonetización de todo el canal por reutilización de fuentes sin aporte, (3) falta de divulgación en imágenes realistas de IA, (4) cambios de política sin aviso. Mitigaciones: guion con tesis propia, citas de fuentes en pantalla, variedad de visuales (mapas, líneas de tiempo, archivo con anotaciones), sin plantilla idéntica de estructura, divulgación activada ante la duda.

## 5. Presupuesto 6 meses (USD)

Supuesto: 24 videos (4/mes) en tres fases: F0 mes 1 (4 videos), F1 meses 2–3 (8), F2 meses 4–6 (12). Precios con fuente indicadas; las filas marcadas **[E]** son supuestos sin fuente.

**Bajo (todo hecho por el propietario)**

| Partida | Unit. x cantidad | Subtotal | F0 | F1 | F2 |
|---|---|---|---|---|---|
| Claude Pro mensual | 20 x 6 | 120 | 20 | 40 | 60 |
| ElevenLabs Creator | 22 x 6 | 132 | 22 | 44 | 66 |
| Resolve, LOC, Wikimedia, Audio Library | 0 | 0 | 0 | 0 | 0 |
| **Total** |  | **252** | 42 | 84 | 126 |

**Probable**

| Partida | Unit. x cantidad | Subtotal | F0 | F1 | F2 |
|---|---|---|---|---|---|
| Claude Pro | 20 x 6 | 120 | 20 | 40 | 60 |
| ElevenLabs Creator | 22 x 6 | 132 | 22 | 44 | 66 |
| Verificación de hechos freelance [E] (la mitad de videos) | 25 x 12 | 300 | 100 | 100 | 100 |
| Miniaturas freelance [E] | 10 x 24 | 240 | 40 | 80 | 120 |
| **Total** |  | **792** | 182 | 264 | 346 |

Comprobación fases F0: 20+22+100+40=182; F1: 40+44+100+80=264; F2: 60+66+100+120=346; suma 792.

**Alto**

| Partida | Unit. x cantidad | Subtotal | F0 | F1 | F2 |
|---|---|---|---|---|---|
| Claude Pro | 20 x 6 | 120 | 20 | 40 | 60 |
| ElevenLabs Creator | 22 x 6 | 132 | 22 | 44 | 66 |
| Editor freelance [E] | 60 x 24 | 1.440 | 240 | 480 | 720 |
| Verificación de hechos [E] (todos los videos) | 25 x 24 | 600 | 100 | 200 | 300 |
| Miniaturas freelance [E] | 10 x 24 | 240 | 40 | 80 | 120 |
| DaVinci Resolve Studio | 236 x 1 | 236 | 236 | 0 | 0 |
| **Total** |  | **2.768** | 658 | 844 | 1.266 |

Comprobación: F0 20+22+240+100+40+236=658; F1 40+44+480+200+80=844; F2 60+66+720+300+120=1.266; suma 2.768.

**Punto de equilibrio [ESTIMACIÓN, no medido]**: costo mensual probable ≈ 792/6 = US$132. Con un RPM supuesto de US$4–10 [E, sin verificar para este subnicho; el listado de terceros usa rangos similares], se necesitan ~13.200 (RPM 10) a ~33.000 (RPM 4) vistas monetizadas/mes solo para cubrir el gasto mensual. No hay ingresos antes de entrar a YPP (1.000 subs y 4.000 h), así que la recuperación del gasto acumulado (US$792) es **improbable dentro de los 6 meses** y más realista después del mes 9–12 [E]. La cifra agregada de NicheRadar (US$1.629–3.724/mes en 25 videos) no es ingreso de un canal nuevo.

## 6. Plan por fases

**F0 (mes 1) — Preparación y 4 videos**: crear canal, fichas de hechos, plantilla de guion con análisis propio, pipeline voz/imagen con créditos.
- Salida: 4 videos publicados; 100% de afirmaciones con 2 fuentes; 0 imágenes sin estatus documentado; <=70 min humanos por video.
- Parada: imposible documentar derechos en >20% de las imágenes, o un video con error factual grave no detectado antes de publicar.

**F1 (meses 2–3) — Iteración**: 8 videos, probar 3 ángulos de título/miniatura.
- Salida (medible en YouTube Studio): CTR medio >=4% y retención media >=35% en al menos 4 de 8 videos [E, umbrales propios]; >=1 video con vistas >=3x la mediana del canal; min humanos <=60.
- Parada: tras 12 videos, mediana de vistas <200 y 0 videos sobre 1.000 vistas; o aviso de política (contenido inauténtico) en cualquier video.

**F2 (meses 4–6) — Escala medida**: 12 videos, enfocarse en la serie ganadora.
- Salida: >=500 suscriptores y >=1.500 horas de visualización al final del mes 6 [E; ruta razonable hacia YPP], tasa de errores corregidos <=1 por video.
- Parada: gasto acumulado probable (US$792) superado en >50% sin crecer; o rechazo de YPP por contenido inauténtico sin posibilidad de remediar en 60 días.

Decisión al mes 6: seguir, pivotar el ángulo o cerrar.

## 7. Fuentes (acceso 2026-11-01)

| Id | Fuente | URL | Uso |
|---|---|---|---|
| s1 | YouTube: políticas de monetización del canal | https://support.google.com/youtube/answer/1311392 | Inauthentic/reused content (actualizada 2025-07-15) |
| s2 | YouTube: divulgación de contenido alterado/sintético | https://support.google.com/youtube/answer/14328491 | Cuándo divulgar |
| s3 | Library of Congress: riesgo y derechos | https://guides.loc.gov/p-and-p-rights-and-restrictions/risk-assessment | Responsabilidad de derechos y dominio público |
| s4 | Wikimedia Commons: reutilización | https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia | Atribución y licencias |
| s5 | Claude: precios | https://claude.com/pricing | Claude Pro US$20/mes (US$17 anual) |
| s6 | ElevenLabs: precios | https://elevenlabs.io/pricing | Planes y licencia comercial (página inconsistente) |
| s7 | Blackmagic Design: DaVinci Resolve | https://www.blackmagicdesign.com/products/davinciresolve | Gratis; Studio US$236 |
| s8 | YouTube Audio Library | https://support.google.com/youtube/answer/3376882 | Música sin reclamaciones |
| s9 | YouTube Partner Program | https://support.google.com/youtube/answer/72851 | Umbrales YPP |
| s10 | Listado autonolab (tercero, legacy) | https://blog.autonolab.com/niches/2025-12-10-faceless-youtube-history/ | Tamaños y formatos [T] |
| s11 | Búsqueda web general | https://www.youtube.com/@LittleKnownHistory | Canal existe; sin métricas |
| s12 | Canal The Forgotten | https://www.youtube.com/@TheForgotten | Canal existe; sin métricas |
| s13 | ThoughtLeaders | https://app.thoughtleaders.io/youtube/historys-forgotten-people | Ficha de tercero |

No consultados con éxito (403, 404 o sin dato): Canva, Midjourney, OpenAI API, LOC "Free to Use", páginas de métricas de YouTube. No se usan en cifras.
