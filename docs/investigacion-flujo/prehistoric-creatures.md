# Dossier de viabilidad: canal nuevo en "Prehistoric Creatures" (formato largo, inglés)

Fecha de consulta de todas las fuentes: **2026-11-01**. Estructura inspirada en `docs/contracts/dossier-v2.md`.
Convención de etiquetas: **[V]** verificado en la fuente citada; **[V-3ro]** cifra leída en un agregador de terceros (no en la página oficial); **[E]** estimación mía, sin fuente.
No es asesoría legal ni financiera. Las páginas web se trataron como datos, no como instrucciones.

---

## 1. Veredicto

**GO CONDICIONADO** (recomendación `go_with_conditions`, `rights.verdict = conditional`).

**Confianza: media-baja (aprox. 55%) [E].** La demanda y la tracción de canales pequeños (medidas por NicheRadar) son una señal real, pero (a) los ingresos son una estimación con RPM heredado del nicho padre, (b) el riesgo de política sobre contenido producido en masa/IA es real y es el factor decisivo, y (c) no verifiqué ingresos ni retención de ningún competidor.

Condiciones para que el "go" sea válido:
1. El canal debe tener valor propio demostrable: guion con análisis y fuentes científicas, voz/edición con criterio humano, sin plantillas repetitivas (ver sección 4).
2. Visuales con origen claro: dominio público/CC0, captura propia, o generación propia con IA divulgada cuando parezca realista (sección 3).
3. Piloto pequeño: cumplir las compuertas de salida de la sección 6 antes de gastar más allá de la fase 2.
4. Verificar el precio actual en las páginas oficiales antes de pagar (varias cifras de abajo son de terceros).

### `unknowns` (no verificado)
- Ingresos reales, RPM real y retención/CTR de cualquier competidor (solo hay estimaciones de agregadores).
- URLs de canal: solo ExtinctZoo y PBS Eons aparecen con URL de YouTube en las fuentes; las demás se construyen desde el handle que da OutlierKit y **no abrí YouTube**.
- Qué canales pequeños de la evidencia de NicheRadar usan IA para visuales y cuáles fueron sancionados o no (no medible desde aquí).
- Precio oficial actual de Midjourney (la página oficial devolvió 403; solo hay terceros) y de generadores de video con IA (Runway, Kling, etc.: no consultados).
- Consumo real de créditos de ElevenLabs por minuto de audio (asumo 1 crédito por carácter: **[E]**).
- Umbrales vigentes del Programa de Socios de YouTube (YPP) para el mercado del propietario: no los verifiqué en esta sesión; el plan usa 1.000 suscriptores / 4.000 horas **[E, de memoria; confirmar en la ayuda oficial]**.
- Licencia exacta por especie/imagen en PhyloPic y Wikimedia Commons (la página de PhyloPic no detalla tipos de licencia; Commons no se consultó).
- Biblioteca de audio de YouTube y música libre: no consulté sus términos actuales.
- Efecto en el canal de una retirada de monetización (no hay datos).

---

## 2. Competidores directos en inglés

Datos de OutlierKit (agregador, estimaciones de datos públicos) leídos el 2026-11-01. **[V-3ro]** = cifra del agregador; la interpretación de "qué los hace funcionar" es **[E]** salvo que se indique.

| Canal | URL | Tamaño | Frecuencia | Formato | Qué parece hacerlos funcionar |
|---|---|---|---|---|---|
| ExtinctZoo | https://www.youtube.com/@ExtinctZoo [V-3ro] | 1,5 M subs; media ~2,1 M vistas/video | ~1,2 videos/semana | ~19:41 min por video | [E] Un animal extinto por video, títulos de curiosidad, alto reparto a no suscriptores (muchas vistas por suscriptor) |
| Spinosnack | https://www.youtube.com/@Spinosnack (construida desde handle) | 582 K subs; media ~395,8 K vistas; 471 videos | ~2,3 videos/semana | ~32:08 min | [E] Volumen alto y videos largos; catálogo grande |
| Mr. Science | https://www.youtube.com/@mr.scienceYT (construida desde handle) | 224 K subs; mediana ~940 K vistas | ~1,7 videos/mes | ~21:00 min | [E] Pocos videos con enorme apalancamiento de vistas sobre suscriptores; estilo documental de "monstruos prehistóricos" |
| WUFO Earth | https://www.youtube.com/@wufoearth (construida desde handle) | 18,4 K subs; mediana reciente ~25 K vistas (cálculo mío desde multiplicadores de OutlierKit) | ~6 videos/semana (~25/mes) | ~1:00:20 h, paleontología y evolución humana | [E] Videos de una hora, estilo atmosférico; el único con tamaño comparable a un canal piloto exitoso, y con ratio vistas/suscriptor cercano a 1,4 |
| Paleo Analysis | https://www.youtube.com/channel/UCQoaCXh2vU2_qeUDt25LY-Q [V-3ro, ytubeinfluencers] | 231 K subs | no verificada | no verificado | Solo se verificó el tamaño; formato y frecuencia desconocidos |
| PBS Eons (referencia, no competidor realista) | https://www.youtube.com/channel/UCzR-rom72PHN9Zg7RML9EbA [V-3ro] | 3,16 M subs | no verificada | no verificado | Producción institucional; sirve como techo de calidad, no como modelo replicable |

Observaciones:
- Hay solo 3 a 4 canales grandes y mucha heterogeneidad (de 18 K a 1,5 M), consistente con la medición de NicheRadar (solo 4 canales grandes, 19 pequeños con tracción).
- Un candidato que apareció en la búsqueda (BeforeUsTold) tiene 2 suscriptores y ~9 vistas/video: **descartado** como competidor.
- Una fuente de listados (Autonolab) menciona un canal sin nombre de 112 K subs y 2,0 M de vistas medias hecho con stock o visuales de IA **[V-3ro, sin canal identificable]**: no se usa como evidencia.
- Frecuencia de los líderes: de ~0,4/semana a ~6/semana; no hay una cadencia única que explique el éxito.

---

## 3. Flujo de producción propuesto

Precios consultados el 2026-11-01 (dentro de 90 días). Sin horas humanas valoradas en dinero (trabajo del propietario).

| Etapa | Herramienta concreta | Precio | Fuente | Automatización | Minutos humanos/video [E] |
|---|---|---|---|---|---|
| Guion e investigación | Claude (API) Sonnet 5.5, con ficha de datos y papers/fuentes citadas | US$2 / M tokens entrada y US$10 / M salida [V]; ~US$0,14 por video con ~30 K entrada + ~8 K salida, ~US$0,50 con reintentos [E] | https://claude.com/pricing | semi (IA redacta, humano verifica cada cifra y añade análisis) | 25 |
| Voz | ElevenLabs Creator | US$22/mes, 121.000 créditos, licencia comercial [V]. Starter US$6/mes, 30.000 créditos [V] | https://elevenlabs.io/pricing | auto (API/TTS) | 5 |
| Imágenes / animación | Midjourney (ilustración propia) + capturas de dominio público + clips cortos de IA opcionales | Basic US$10, Standard US$30, Pro US$60, Mega US$120 por mes [V-3ro]; video con IA: sin precio verificado | https://eesel.ai/blog/midjourney-pricing | semi | 20 |
| Edición | DaVinci Resolve (gratis) o Studio US$236 pago único [V] | gratis / US$236 | https://www.blackmagicdesign.com/products/davinciresolve | semi (plantilla, subtítulos automáticos) | 20 |
| Miniaturas | Midjourney + editor gratuito (no cotizado) | incluido en Midjourney | ver arriba | semi | 8 |
| Publicación | YouTube Studio (título, descripción, divulgación de contenido sintético) | gratis | https://support.google.com/youtube/answer/14328491 | manual con plantilla | 7 |

Total estimado: ~85 minutos humanos por video **[E]**, por encima del máximo de 60 de la compuerta `NR_GATE_MAX_HUMAN_MINUTES` mencionada en `dossier-v2.md`. Para pasar la compuerta habría que reducir a <=60 (p. ej. plantillas de edición y flujo de imágenes reutilizable) o pedir excepción `gate_override`. Esto es un riesgo abierto, no resuelto.

### Derechos del material

| Material | Origen | Licencia/política | Fuente | Requiere permiso |
|---|---|---|---|---|
| Imágenes de colecciones (Smithsonian) | `public_domain` solo para ítems marcados CC0 | Uso comercial sin atribución ni tarifa para ítems CC0 [V]; los no CC0 requieren permiso escrito; otras leyes (derechos de imagen, marcas) pueden aplicar | https://www.si.edu/newsdesk/releases/smithsonian-releases-28-million-free-images-broader-public-use | No para CC0 |
| Siluetas PhyloPic | `third_party` | Reutilizables bajo licencias Creative Commons, tipo y atribución varían por imagen [V parcial: la página no detalla] | https://www.phylopic.org/ | Depende de la licencia: **condición** |
| Ilustraciones generadas con Midjourney | `own_generation` / `licensed` | Terceros dicen que todos los planes pagos incluyen derechos comerciales y que empresas con ingresos >US$1 M deben usar Pro/Mega [V-3ro]; verificar términos oficiales | https://eesel.ai/blog/midjourney-pricing | No, tras verificar términos |
| Voz sintética | `licensed` | Planes Starter o superior incluyen licencia comercial; evitar voces de la biblioteca con términos propios [V / V-3ro] | https://elevenlabs.io/pricing | No |
| Música | `unknown` | No verificada (usar solo biblioteca con licencia comprobada) | n/d | Pendiente |
| Texto (guion) | `own_generation` | Producción propia con asistencia de IA | https://support.google.com/youtube/answer/14328491 | No |

`rights.verdict`: **conditional**. Condiciones: usar solo ítems CC0 o con licencia comprobada y guardar prueba de cada imagen; no usar clips de terceros de YouTube (política de contenido reutilizado, sección 4); resolver la música antes de publicar; leer los términos oficiales de Midjourney.

### Qué se puede automatizar
Auto: voz (API), subtítulos, exportación. Semi: borrador de guion, generación de imágenes, edición con plantilla, miniaturas. Manual: verificación de hechos científicos, decisiones de tema, revisión final de calidad, divulgación en YouTube. Automatización global estimada ~65% **[E]**: por debajo del umbral de 90 de `NR_GATE_MIN_AUTOMATION`. Es coherente con la política de YouTube (sección 4): automatizar de más aumenta el riesgo de monetización.

---

## 4. Política de YouTube vigente y riesgo de monetización

Fuentes oficiales leídas el 2026-11-01:

- **Política de monetización del canal** (https://support.google.com/youtube/answer/1311392; última entrada fechada en la página: 15 de julio de 2025) [V]:
  - "Repetitious content" se renombró "inauthentic content": incluye contenido repetitivo o producido en masa, que ya era no elegible para monetizar.
  - El contenido repetitivo es el que parece hecho con plantilla. Ejemplo no elegible: contenido generado con IA con plantillas genéricas o poco originales que da impresión de producción en masa, sin aportar ideas originales.
  - Contenido reutilizado: canales que reutilizan contenido ya existente en YouTube no son elegibles, incluso con permiso del creador original.
  - Si se usan herramientas automáticas o plantillas, el producto final debe mostrar visión creativa del autor. Permitido: usar IA para editar guiones o generar visuales de fondo.
  - Personas de IA que dan información sobre temas sensibles no pueden monetizar (no aplica a paleontología).
- **Divulgación de contenido alterado o sintético** (https://support.google.com/youtube/answer/14328491) [V]:
  - Obligatoria cuando el contenido es realista (escena que no ocurrió, alteración de un lugar real, etc.).
  - No requiere divulgación: contenido no realista, ediciones menores, y ayuda de IA en guion, título, miniatura o infografías.
  - Divulgar no limita el alcance ni la elegibilidad de monetización; no divulgar de forma consistente puede traer etiqueta manual, retiro o suspensión del YPP.

Riesgos para este nicho:
1. **Riesgo alto de "producido en masa"** si el canal usa guion de IA sin análisis, voz sintética y imágenes genéricas con estructura idéntica en cada video **[E, interpretación mía de la política]**. Mitigación: variar estructura, citar papers, aportar análisis propio, cadencia moderada.
2. **Reconstrucciones realistas de animales extintos**: una escena fotorrealista generada puede requerir divulgación; ilustraciones obviamente no realistas no.
3. Reutilizar clips de documentales existentes: excluido.
4. La política puede cambiar; el 15 de julio de 2025 fue la última entrada fechada que vi.

Riesgo de política agregado: **medio-alto** [E].

---

## 5. Presupuesto (6 meses, USD)

Supuestos: se excluye el tiempo humano. Imprevistos 10% de cada fase. Precios de la sección 3. Costos de video con IA y externos son **[E]**.

### Bajo (12 videos, 2 por mes)

| Partida | Unitario | Cantidad | Subtotal |
|---|---|---|---|
| Guion (API) | 0,50 | 12 | 6,00 |
| ElevenLabs Starter | 6 | 6 meses | 36,00 |
| Midjourney Basic [V-3ro] | 10 | 6 meses | 60,00 |
| DaVinci Resolve gratis | 0 | 1 | 0,00 |
| Subtotal | | | 102,00 |
| Imprevistos 10% (redondeado) | | | 10,00 |
| **Total** | | | **112,00** |

### Probable (24 videos, 1 por semana, ~4 por mes)

| Partida | Unitario | Cantidad | Subtotal |
|---|---|---|---|
| Guion (API) | 0,50 | 24 | 12,00 |
| ElevenLabs Creator | 22 | 6 meses | 132,00 |
| Midjourney Standard [V-3ro] | 30 | 6 meses | 180,00 |
| Clips de IA opcionales [E] | 5 | 24 | 120,00 |
| DaVinci Resolve gratis | 0 | 1 | 0,00 |
| Subtotal | | | 444,00 |
| Imprevistos 10% (redondeado) | | | 44,00 |
| **Total** | | | **488,00** |

### Alto (40 videos)

| Partida | Unitario | Cantidad | Subtotal |
|---|---|---|---|
| Guion (API, más reintentos) | 1,00 | 40 | 40,00 |
| ElevenLabs Creator | 22 | 6 meses | 132,00 |
| Midjourney Pro [V-3ro] | 60 | 6 meses | 360,00 |
| Clips de IA [E] | 10 | 40 | 400,00 |
| DaVinci Resolve Studio | 236 | 1 | 236,00 |
| Miniaturas externas [E] | 15 | 40 | 600,00 |
| Revisión científica externa [E] | 25 | 40 | 1.000,00 |
| Subtotal | | | 2.768,00 |
| Imprevistos 10% (redondeado) | | | 277,00 |
| **Total** | | | **3.045,00** |

Presupuesto por fase (probable): fase 1 (mes 1) ~US$96; fase 2 (meses 2 a 3) ~US$195; fase 3 (meses 4 a 6) ~US$197 **[E, reparto proporcional de US$488]**.

### Punto de equilibrio (ESTIMACIÓN, etiqueta [E])
- Costo acumulado probable a 6 meses: US$488.
- Con RPM supuesto de US$3 por mil vistas monetizadas [E, no verificado; NicheRadar hereda RPM del nicho padre wildlife_documentaries y estima una mediana de US$673 a US$1.682/mes por canal estable, no ingresos reales de un canal nuevo], se necesitan ~163.000 vistas monetizadas acumuladas para recuperar US$488 (488 / 3 x 1.000).
- Sin YPP no hay ingresos por anuncios: es probable que los meses 1 a 4 den ingreso cero **[E]**. Si el YPP se alcanza hacia el mes 5 a 6, el equilibrio dentro de los 6 meses es poco probable; plan de recuperación realista: 9 a 12 meses **[E]**.

---

## 6. Plan por fases y reglas de parada

Umbrales **[E]**: son supuestos de piloto, no medidos.

| Fase | Duración | Entregables | Criterio de salida (medible) | Gasto máx. [E] |
|---|---|---|---|---|
| 1. Prueba de flujo | Mes 1 | 3 videos de 10 a 15 min publicados; plantilla de guion con fuentes; prueba de derechos por imagen | 3 videos publicados; <=60 min humanos por video en el último; 0 reclamos de derechos; divulgación de contenido sintético aplicada en todos | US$100 |
| 2. Validación de demanda | Meses 2 a 3 | 8 a 10 videos más (total 11 a 13) | Mediana de vistas >=1.000 por video a los 28 días **o** al menos 1 video >=5x los suscriptores del canal; CTR >=4% y retención media >=35% en YouTube Studio; >=200 suscriptores | US$200 |
| 3. Escala moderada | Meses 4 a 6 | Hasta 24 videos totales | >=1.000 suscriptores y 4.000 horas de reproducción (umbral YPP a confirmar) o proyección verificable de lograrlo en 60 días | US$190 |

### Reglas de parada
1. Fin de fase 2 sin cumplir **ninguno** de los criterios de vistas/retención: parar, no pasar a la fase 3.
2. Cualquier aviso de YouTube por contenido inauténtico/reutilizado: pausar subidas, revisar los últimos 5 videos y reabrir el plan antes de seguir.
3. Un reclamo de derechos de autor por material propuesto como libre: pausar y auditar todo el catálogo.
4. Gasto acumulado >120% del presupuesto de la fase: congelar.
5. Mes 6 con menos de 300 suscriptores y mediana <500 vistas: cierre del piloto.

---

## 7. Fuentes (acceso 2026-11-01)

| Fuente | URL | Qué se tomó | Fiabilidad |
|---|---|---|---|
| Ayuda de YouTube: política de monetización | https://support.google.com/youtube/answer/1311392 | Contenido inauténtico, reutilizado, IA (entrada 15-jul-2025) | Oficial |
| Ayuda de YouTube: contenido alterado o sintético | https://support.google.com/youtube/answer/14328491 | Cuándo divulgar | Oficial |
| ElevenLabs precios | https://elevenlabs.io/pricing | Planes, créditos, licencia comercial | Oficial |
| Claude precios | https://claude.com/pricing | Precio por tokens y plan Pro | Oficial |
| Blackmagic DaVinci Resolve | https://www.blackmagicdesign.com/products/davinciresolve | Gratis / Studio US$236 | Oficial |
| Smithsonian Open Access | https://www.si.edu/newsdesk/releases/smithsonian-releases-28-million-free-images-broader-public-use | CC0, uso comercial | Oficial (vía resultado de búsqueda; página oficial directa devolvió 403) |
| PhyloPic | https://www.phylopic.org/ | Siluetas reutilizables bajo licencias CC | Oficial, sin detalle |
| Midjourney precios (terceros) | https://eesel.ai/blog/midjourney-pricing | Planes y términos comerciales | Tercero; confirmar oficial |
| OutlierKit ExtinctZoo | https://outlierkit.com/channel/extinctzoo | Subs, frecuencia, duración, vistas | Agregador |
| OutlierKit Spinosnack | https://outlierkit.com/channel/spinosnack | Ídem | Agregador |
| OutlierKit Mr. Science | https://outlierkit.com/channel/mr-scienceyt | Ídem | Agregador |
| OutlierKit WUFO Earth | https://outlierkit.com/channel/wufoearth | Ídem | Agregador |
| OutlierKit BeforeUsTold | https://outlierkit.com/channel/beforeustold | Descartado (2 subs) | Agregador |
| Listado paleontología (ytubeinfluencers) | https://ytubeinfluencers.com/category/paleontology/country/united-states/ | Tamaños de Paleo Analysis y PBS Eons | Agregador |
| Cobertura de la política de julio 2025 | https://www.searchenginejournal.com/youtube-monetization-update-spam-not-reaction-channels/550755/ | Contexto (solo apareció en resultados de búsqueda, no abierta) | Tercero |

Páginas con 403 no abiertas: Midjourney oficial, si.edu/openaccess, Smithsonian Magazine.
