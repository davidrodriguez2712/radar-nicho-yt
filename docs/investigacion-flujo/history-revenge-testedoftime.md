# Dossier de viabilidad: "History Revenge Stories" en @TestedOfTime

Fecha de consulta de todas las fuentes: 2026-11-01. Formato: espíritu de `docs/contracts/dossier-v2.md`.
Rótulos: **VERIFICADO** (leído en la fuente citada), **ESTIMACIÓN** (cálculo o supuesto mío), **UNKNOWN** (no verificado).
No es asesoría legal ni financiera.

## 1. Veredicto

**GO CONDICIONADO, confianza baja (aprox. 35 %).** No como subnicho aislado, sino como un *ángulo* ("justicia y venganza en la historia") dentro de un canal de historias históricas narradas, probado con una fase corta y reglas de parada.

Razones:
- El tema tiene demanda visible en la cima: Serious History (820 K suscriptores) tiene "Extreme Vigilante Justice in History" con 6,4 M de vistas y "Extreme Stories of Revenge from History" (fuente s9, estadísticas de terceros). Hay 5 canales pequeños con un video largo >=5x sus suscriptores (medido por NicheRadar).
- Pero es de los subnichos más flojos medidos: 13 de 22 videos con pico reciente (señal de moda, no de demanda estable), 11 canales grandes, ingreso mensual agregado estimado US$885–2.022 para todo el subnicho (RPM heredado, estimación). Un ingreso agregado tan bajo no sostiene a un canal nuevo en el tema; sirve solo como gancho dentro de un formato más amplio.
- **Cambio de reglas que altera el plan:** la página oficial del YPP anuncia que desde el **2027-02-01** los creadores nuevos necesitarán **1.000 suscriptores + 8.000 horas** (en vez de 4.000) o 20 M de vistas de Shorts en 90 días (s2). El canal no está en el YPP, así que muy probablemente le aplica si solicita después de esa fecha. A 3 meses vista (hoy 2026-11-01) no es realista llegar a 4.000 h salvo en el escenario optimista, de modo que la meta realista es **8.000 horas**.
- Compuertas de NicheRadar (dossier-v2): mi estimación de minutos humanos por video (130) supera `NR_GATE_MAX_HUMAN_MINUTES` = 60, y la automatización (aprox. 55 %) queda bajo `NR_GATE_MIN_AUTOMATION` = 90. Un `go_with_conditions` real **requiere `gate_override` explícito del propietario**; sin él, el servicio lo rechazaría. La verificación de hechos es lo que no conviene automatizar.

### Unknowns
- Contenido, idioma, antigüedad y vistas de @TestedOfTime: la página pública devolvió solo el título "Tested Of Time - YouTube" (sin videos ni datos); no pude verlo. Todo el plan asume un canal que **no** tiene audiencia afín a historia y venganza.
- Si la regla de 8.000 h aplica a este canal exactamente (¿cuenta como "nuevo creador"?; ¿qué pasa si solicita antes del 2027-02-01?).
- RPM real de este canal y del subnicho (el de NicheRadar es heredado). No hay RPM verificado en fuentes oficiales.
- Medición de alternativas de historia en el mismo canal (medieval, historia oscura, etc.): no medidas en esta tarea, así que la comparación es cualitativa.
- Políticas de "contenido apto para anunciantes" sobre violencia histórica (no leí esa página oficial). Riesgo de desmonetización parcial (anuncios limitados) no cuantificado.
- Precio actual de Midjourney u otro generador de imágenes y del LLM de guion (no verificados; ver sección 6).
- Efecto real de reactivar un canal parado sobre el algoritmo: no hay fuente oficial; ver sección 2.
- Estadísticas de Serious History y de otros competidores son de terceros (OutlierKit, vling), no de YouTube.

## 2. Camino de monetización del canal

Punto de partida (YouTube Studio, 2026-10-27, dato del propietario): 1.802 suscriptores, 0 videos en 90 días, 122 h/365 días, 0 vistas de Shorts.

### Umbrales (VERIFICADO, s1, s2, s3)
| Nivel | Requisitos | Qué da |
|---|---|---|
| Inicial (500 suscriptores, 3 videos públicos en 90 días, 3.000 h/365 días o 3 M vistas de Shorts/90 días) | El texto "500 suscriptores + 3.000 h" lo confirman solo fuentes de terceros (s10); la página oficial que leí (s1) no lo lista | Según s2: opción de 500 suscriptores para fan funding, Creator Partnerships y Shopping. **No es ingreso por anuncios** |
| Anuncios completos hoy | 1.000 suscriptores + 4.000 h/365 días o 10 M vistas de Shorts/90 días (s1) | Participación en ingresos publicitarios |
| Anuncios completos desde 2027-02-01 para creadores nuevos | 1.000 suscriptores + **8.000 h**/365 días o 20 M Shorts/90 días (s2). Aceptar términos nuevos antes del 2027-01-31 si ya se está en el YPP | Igual |
| Canal activo (miembros YPP, desde 2027-02-01) | 1.000 h/365 días, o 1 M Shorts/90 días, o 2 videos largos o 5 Shorts cada 90 días (s2) | Evita perder estado |

Conclusión: el nivel de 3.000 h solo da fan funding (membresías, etc.); con 1.802 suscriptores esa vía rinde poco. La meta que paga es 4.000 h (si se lograra antes del 2027-02-01) o 8.000 h (lo probable).

### Horas que faltan
- A 3.000 h: 3.000 − 122 = **2.878 h**
- A 4.000 h: **3.878 h**
- A 8.000 h: **7.878 h**
(No descuento las 122 h que salgan de la ventana de 365 días; con un canal parado es un error pequeño pero real.)

### Cálculo (ESTIMACIÓN)
Horas por video = vistas x duración media de visualización (AVD). Supuesto: video de 18–20 min con retención de aprox. 40 %, es decir AVD aprox. 8 min = 0,133 h por vista. Ritmo: 4 videos/mes. Las vistas se acumulan durante semanas, así que sumo 1–2 meses de retraso a los plazos.

| Escenario (vistas por video dentro de la ventana) | h por video | Videos para 3.000 h | Videos para 4.000 h | Videos para 8.000 h |
|---|---|---|---|---|
| Pesimista: 1.000 vistas | 133 h | 22 (5,5 meses) | 30 (7,5 meses) | 60 (15 meses) |
| Base: 3.000 vistas | 400 h | 8 (2 meses) | 10 (2,5 meses) | 20 (5 meses) |
| Optimista: 8.000 vistas | 1.067 h | 3 (menos de 1 mes) | 4 (1 mes) | 8 (2 meses) |

Más 1–2 meses de retraso por acumulación. Lectura: en base, 8.000 h llegan hacia el mes 6–7; en pesimista no llegan en 12 meses (regla de parada, sección 7). Para 8.000 h en base se necesitan aprox. 59.000 vistas totales a AVD de 8 min (7.878 / 0,133).

Referencia: Serious History publica aprox. 2,5 videos/mes de aprox. 17 min (s9, terceros). 4/mes es un ritmo agresivo para un flujo con verificación de hechos.

### Efecto de reorientar un canal parado (ESTIMACIÓN, sin fuente oficial)
- Con 0 videos en 90 días y 122 h/año, el canal casi no tiene señal reciente: arrancará con pocas impresiones. Los 1.802 suscriptores, si venían de otro tema, no están emparejados con historia; probablemente responderán poco a los primeros videos (CTR y retención iniciales bajos pueden enseñarle al sistema que el canal no encaja).
- Posible ventaja: una cuenta con historial limpio y suscriptores, que no parte de cero. No lo puedo cuantificar.
- Implicación: tratar los primeros 6 videos como calibración, no como prueba definitiva del tema.

## 3. Competidores directos en inglés

Honestidad: solo encontré **un** competidor directo con datos útiles. Los demás son parciales o dudosos. No llego a 3 verificados; lo declaro.

| Canal | URL | Tamaño | Frecuencia | Formato | Qué funciona | Estado |
|---|---|---|---|---|---|---|
| Serious History | https://www.youtube.com/@SeriousHistory | 820 K suscriptores, 86,8 M vistas, 60 videos | aprox. 2,5/mes (estimado por terceros) | 100 % largo, aprox. 17 min, narrado sin rostro; compilaciones de historias cinematográficas | Disparador emocional primario (venganza, justicia, supervivencia) empaquetado en 3–6 historias; "Extreme Vigilante Justice in History" 6,4 M | Estadísticas de terceros (OutlierKit, s9); la URL del canal sale de resultados de búsqueda (s11), no la abrí |
| Easy History | https://podcasts.apple.com/us/podcast/id1859025245 | desconocido | desconocido | Animado; episodio "History's Most Insane Revenge Stories" | Solo se confirma la existencia del título | Solo aparece como podcast; no es un canal de YouTube verificado |
| Dark Reckoning Files | desconocido (https://vling.net/en/channel/UClUeb9iz-RQqOmaY8yExBhw/channel-info aparece en resultados, no leído) | desconocido | desconocido | Historias de venganza "automatización"; no es historia real | Describe karma y desenlaces | Solo texto de resultados de búsqueda (s11); no historia real |
| Justice Awakens | desconocido | desconocido | desconocido | Historias dramatizadas ficticias con aviso de ficción | Injusticia y reversión | Solo resultados de búsqueda; ficticio |
| The Forgotten | https://www.youtube.com/@TheForgotten-diaries | desconocido | desconocido | Documentales medievales con fuentes | Fuentes y ritmo documental | Solo blog de tercero (s11); relevancia tangencial |

Qué implica: el líder demuestra que el empaquetado "justicia/venganza en la historia" funciona en formato compilación de aprox. 17 min, pero ese líder es grande y la entrada de canales pequeños depende de un solo video con éxito (NicheRadar mide 5 de esos). La competencia de "revenge stories" masivas es ficción tipo Reddit; no hay evidencia de que el público quiera historia real con ese enfoque en formato largo más allá de Serious History.

## 4. Flujo de producción por etapa

Precios consultados el 2026-11-01 (ventana de 90 días respetada).

| # | Etapa | Herramienta / precio | Derechos | Automatización | Min humanos/video |
|---|---|---|---|---|---|
| 1 | Selección del caso e investigación | Fuentes primarias y secundarias abiertas; LLM como apoyo (precio no verificado, ver unknowns) | Texto propio; hechos no tienen copyright, redacción sí | semi | 25 |
| 2 | Guion (aprox. 2.500–3.000 palabras, 18–20 min) | LLM por API o chat | Texto propio; sin copiar redacción de fuentes | semi | 15 |
| 3 | Verificación de hechos y citas | Humana, con la lista de fuentes del paso 1 | Cada cifra o fecha con fuente | manual | 30 |
| 4 | Voz | ElevenLabs Creator US$11/mes, 121 K créditos (aprox. 121 min), licencia comercial (s5) | Licencia comercial desde el plan Starter (US$1/mes) según la tabla leída; revisar términos de voces antes de usar una concreta | auto | 5 |
| 5 | Visuales | Pexels (gratis, comercial, sin atribución obligatoria; s6); imágenes de dominio público de museos y archivos (no verificadas en esta tarea); generación de imágenes (precio no verificado) | Dominio público y licencias deben verificarse por archivo; Wikimedia no verificado (la página de reutilización dio 404) | semi | 20 |
| 6 | Edición | Editor de video de escritorio; versión gratuita supuesta (no verificada) | Música: biblioteca de audio de YouTube (s7), solo monetizable con YPP | semi | 25 |
| 7 | Título, miniatura, subida y declaración de IA | YouTube Studio; editor de imágenes | Miniatura propia; declaración "Uso de IA" en Atributos (s4) | semi | 10 |

Total estimado de minutos humanos por video: **130** (ESTIMACIÓN). Automatización aprox. 55 % del tiempo.

**Derechos del material (`rights.verdict`: conditional).**
- Visual: Pexels es de uso comercial sin crédito, sin mostrar personas identificables de forma ofensiva y sin reventa (s6). Imágenes de dominio público o licenciadas deben registrarse una por una con su URL de origen. Generación de imágenes: términos comerciales sin verificar.
- Audio: música solo de la biblioteca de YouTube; las pistas Creative Commons exigen crédito en la descripción (s7). No se vende ni se usa música fuera de esa biblioteca.
- Voz: sintética con licencia comercial del plan (s5). Si la voz se clona o imita a una persona real, hay otro riesgo (no cubierto).
- Condición: no usar clips de documentales, películas o videos de otros canales ni su redacción (s3: reutilización sin comentario original no es monetizable, incluso con permiso).

**Qué se puede automatizar:** voz, ensamblado del borrador de edición y subida por API. **No automatizar:** verificación de hechos (riesgo de inventar "venganzas" que no son históricas), selección del caso y revisión final.

## 5. Política de YouTube vigente

- **Contenido inauténtico** (antes "repetitivo"; renombrado el 2025-07-15; página de Monetización de canales, s3): incluye contenido repetitivo o producido en masa; "AI-generated content made with generic or unoriginal templates giving the impression of mass production" es una infracción listada. Si se usan herramientas automáticas o plantillas, el producto final debe mostrar visión creativa.
- **Contenido reutilizado** (s3): sin comentario original significativo, modificaciones sustantivas o valor educativo o de entretenimiento, no es monetizable; aplica aunque haya permiso del autor original, y se evalúa sobre el canal completo. No cambió el 2025-07-15.
- **Divulgación de IA** (s4, página sin fecha visible): hay que declarar contenido realista alterado o sintético. Exentos: guiones, ideas, subtítulos, clonar tu propia voz para narración, contenido no realista o animado. Divulgar no limita el alcance ni la monetización por sí solo; no divulgar de forma sistemática puede causar etiqueta manual y sanciones, incluida la suspensión del YPP. **Riesgo propio:** imágenes generadas de personajes históricos que parezcan fotografías reales deben declararse.
- **Riesgo para un canal que reactiva con producción rápida (ESTIMACIÓN):** medio-alto. Un canal parado que de golpe sube videos con voz sintética, imágenes similares y estructura de plantilla encaja con las señales de "producción en masa". Mitigaciones: variar estructura narrativa entre videos, aportar análisis y fuentes propias, mostrar el trabajo de verificación, no publicar más de 1–2 por semana al inicio. La solicitud al YPP se revisa de forma manual (no hay fuente oficial leída sobre el plazo de revisión; unknown).
- **Violencia histórica:** no leí la política de contenido apto para anunciantes; Serious History tiene riesgo de anuncios limitados o restricción por edad según un análisis de terceros (s9). Unknown.
- Seguimiento de la fecha: la página s2 anuncia nuevos términos del YPP desde el 2027-02-01.

## 6. Presupuesto en USD para 6 meses

Supuestos de costo: sin sueldo del propietario. Precios verificados: solo ElevenLabs (s5, USD, mensual, sin impuestos). El resto son **supuestos no verificados**, marcados con (S). Todo es ESTIMACIÓN.

### Bajo: 18 videos (3/mes)
| Partida | Unitario x cantidad | Subtotal |
|---|---|---|
| ElevenLabs Creator | US$11 x 6 meses | 66 |
| Stock gratuito y dominio público | US$0 x 18 | 0 |
| LLM para guiones (S) | US$0,5 x 18 | 9 |
| Imprevistos 10 % | US$7,5 | 7,5 |
| **Total** | | **aprox. 83** |

### Probable: 24 videos (4/mes)
| Partida | Unitario x cantidad | Subtotal |
|---|---|---|
| ElevenLabs Creator (60 min/mes aprox., cabe en 121 min) | US$11 x 6 | 66 |
| Generador de imágenes (S) | US$10 x 6 meses | 60 |
| LLM para guiones (S) | US$0,5 x 24 | 12 |
| Imprevistos 10 % | | 13,8 |
| **Total** | | **aprox. 152** |

### Alto: 36 videos (6/mes), con editor externo
| Partida | Unitario x cantidad | Subtotal |
|---|---|---|
| ElevenLabs Pro 3 meses + Creator 3 meses (regeneraciones) | US$99 x 3 + US$11 x 3 | 330 |
| Generador de imágenes plan alto (S) | US$30 x 6 | 180 |
| Editor freelance (S) | US$40 x 36 | 1.440 |
| LLM para guiones (S) | US$0,5 x 36 | 18 |
| Imprevistos 10 % | | 196,8 |
| **Total** | | **aprox. 2.165** |

### Punto de equilibrio (ESTIMACIÓN)
- Antes del YPP con anuncios, el ingreso por anuncios es **cero** (ver sección 2); el gasto de los 6 meses se recupera después.
- RPM supuesto US$2–6 (no verificado; el RPM de NicheRadar es heredado). Escenario base: 4 videos/mes x 3.000 vistas = 12.000 vistas nuevas/mes, más catálogo aprox. 18.000 vistas/mes; a RPM US$4, aprox. US$72/mes.
- Con costo recurrente de aprox. US$25/mes (probable), margen aprox. US$47/mes: recuperar los US$152 del semestre toma aprox. 3–4 meses **después** de monetizar. Monetizar en base cae hacia el mes 6–8 (8.000 h más retraso), así que el equilibrio llega alrededor del mes 10–12 (nota: el cálculo es sensible al RPM; con RPM 2 se duplica).
- Escenario pesimista: no se alcanza el umbral en 12 meses; el equilibrio no llega.
- El escenario alto (US$2.165) no se justifica con un ingreso agregado de subnicho de US$885–2.022/mes.

## 7. Plan por fases con criterios de salida y reglas de parada

**Fase 0 (semana 1–2): preparación.** Entregables: lista de 12 casos reales con 3 fuentes cada uno; plantilla de verificación; revisar la página de contenido apto para anunciantes; abrir YouTube Studio y confirmar con el propietario el contenido actual del canal, y si ya estuvo en el YPP. Salida: 6 guiones aprobados y checklist de derechos sin ítems "unknown".

**Fase 1 (meses 1–2): calibración, 6–8 videos largos.** Un caso real por video, formato de aprox. 18 min, 1 por semana al inicio. Medir por video a los 28 días: CTR, AVD, retención media y suscriptores ganados. Salida (todo): al menos 2 videos con >=3.000 vistas a 28 días **o** AVD >=40 % de la duración; sin ninguna reclamación de derechos ni de contenido inauténtico.
**Regla de parada 1:** si tras 6 videos la mediana es <1.000 vistas a 28 días y AVD <30 %, parar el ángulo "venganza" y probar historia oscura o medieval más amplia (decisión del propietario) antes de gastar en más voz o imágenes.

**Fase 2 (meses 3–4): escalar el formato ganador a 4/mes.** Salida: horas acumuladas en 365 días >=1.500 y 2 videos >=8.000 vistas.
**Regla de parada 2:** si las horas acumuladas a fin del mes 4 son <700, el camino a 8.000 h supera 12 meses: pausar la inversión (mantener solo costo recurrente <= US$25/mes).

**Fase 3 (meses 5–6): rumbo a 4.000 / 8.000 h.** Salida: >=4.000 h (si se alcanzara antes del 2027-02-01) o >=5.000 h y 1.000+ suscriptores confirmados; solicitar al YPP cuando se cumpla el umbral vigente en ese momento.
**Regla de parada 3 (general):** cualquier aviso de inauténtico, reutilizado o infracción de derechos, o aviso de revisión del YPP, detiene la producción y obliga a revisar la plantilla. Gasto acumulado máximo antes de la salida de fase 2: US$152 (probable); no subir a escenario alto sin >=2 videos >=20.000 vistas.

## 8. Fuentes

| ID | Fuente | URL | Acceso |
|---|---|---|---|
| s1 | Ayuda de YouTube: requisitos del YPP | https://support.google.com/youtube/answer/72851 | 2026-11-01 |
| s2 | Ayuda de YouTube: actualizaciones del YPP desde 2027-02-01 | https://support.google.com/youtube/answer/12843009 | 2026-11-01 |
| s3 | Ayuda de YouTube: políticas de monetización (contenido inauténtico y reutilizado) | https://support.google.com/youtube/answer/1311392 | 2026-11-01 |
| s4 | Ayuda de YouTube: divulgación de contenido con IA | https://support.google.com/youtube/answer/14328491 | 2026-11-01 |
| s5 | ElevenLabs: precios | https://elevenlabs.io/pricing | 2026-11-01 |
| s6 | Pexels: licencia | https://www.pexels.com/license/ | 2026-11-01 |
| s7 | Ayuda de YouTube: biblioteca de audio | https://support.google.com/youtube/answer/3376882 | 2026-11-01 |
| s8 | Ayuda de YouTube: Content ID (leída; no cubre dominio público ni uso legítimo) | https://support.google.com/youtube/answer/2797370 | 2026-11-01 |
| s9 | OutlierKit: Serious History (estadísticas de terceros) | https://outlierkit.com/channel/serioushistory | 2026-11-01 |
| s10 | vidIQ y otros (terceros) sobre el nivel de 500 suscriptores | https://vidiq.com/blog/post/youtube-relaxes-monetization-rules/ | 2026-11-01 (solo aparece en resultados de búsqueda; no abierta) |
| s11 | Resultados de búsqueda sobre canales de venganza/historia (vling, blogs) | https://vling.net/en/channel/UClUeb9iz-RQqOmaY8yExBhw/channel-info | 2026-11-01 (solo en resultados; no abierta) |
| s12 | Página del canal @TestedOfTime | https://www.youtube.com/@TestedOfTime | 2026-11-01, **sin datos útiles** (solo el título) |

Fuentes que fallaron: Midjourney (HTTP 403), Wikimedia Commons reutilización (HTTP 404), página /videos del canal (sin contenido).
Nota: s8 no sustenta afirmaciones sobre dominio público; las reglas de reutilización en la sección 4 y 5 salen de s3.
