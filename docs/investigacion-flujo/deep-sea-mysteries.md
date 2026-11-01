# Dossier de viabilidad: canal nuevo "Deep Sea Mysteries" (YouTube, formato largo, inglés)

Fecha de consulta de todas las fuentes: **2026-11-01**. Estructura inspirada en `docs/contracts/dossier-v2.md`
(no es un JSON dossier-v2 listo para la API; es el informe para la decisión go/no-go del propietario).
Convención: **[V]** = leído en una fuente en esta investigación; **[T]** = cifra de un agregador de terceros
(no es YouTube directo; puede estar desfasada); **[E]** = estimación mía, no medida.

## 1. Veredicto

**GO CONDICIONADO. Confianza: media-baja.**

Por qué sí: hay demanda demostrada en el tema (el video más visto de Natural World Facts, "Mariana Trench | In
Pursuit of the Abyss", tiene 22,0 M de vistas [T]); canales de tamaño medio y pequeño de formato similar
sacan vistas muy por encima de sus suscriptores (ver sección 2); el material oceánico de dominio público
existe y es abundante (NOAA Ocean Exploration) [V]; las compuertas de derechos son superables sin permiso previo.

Por qué solo condicionado:

- El mayor referente directo de "deep sea" (Natural World Facts, 1,1 M subs [T]) es lento y cinematográfico;
  los que crecen rápido en el nicho usan un formato "Why X..." de narrativa sensacionalista con retención
  agresiva. Competir en cualquiera de los dos estilos exige guion de calidad, y eso es el cuello de botella humano.
- La política de YouTube sobre contenido "inauténtico/producido en masa" castiga justo el flujo
  plantilla + voz sintética + footage ajeno. El riesgo es de **monetización de todo el canal**, no de un video.
- "Misterios" empuja hacia clickbait y desinformación (monstruos, "criaturas sin explicar"); hay que
  fijar una regla editorial de veracidad.
- La cifra de ingresos de NicheRadar usa RPM heredado, no medido para este subnicho.

**Condiciones para pasar a "go" pleno** (ver fases, sección 6): (a) piloto de 3 videos con retención media
>= 35 % y CTR >= 4 % [E: umbrales de partida, no medidos]; (b) cumplir la regla editorial de la sección 4;
(c) un guion con aporte propio verificable (no resumen de Wikipedia/otros videos).

### `unknowns` (no verificados)

1. Suscriptores, frecuencia y URL de canal de YouTube verificadas directamente: solo hay cifras de OutlierKit [T],
   cuyo propio análisis es generado por IA. No pude confirmar las URLs `youtube.com/@...` de los canales.
2. RPM real de "deep sea" (el de NicheRadar es heredado de `nature_documentaries`).
3. Si Midjourney (o cualquier generador) concede derechos comerciales en el plan elegido: no lo leí en la página oficial.
4. Precio de Epidemic Sound, Artgrid/Storyblocks, generadores de video IA: no verificados.
5. Licencia de Schmidt Ocean Institute para reutilizar su video (la nota que leí solo dice que colaboraron
   con Natural World Facts; no declara la licencia).
6. Si la herramienta de guion con IA (precio por video) es la que se usará: coste unitario es [E].
7. Tiempo humano real por video (58 min es [E], sin medir) y tasa de automatización real (compuerta del servicio: >= 90 %).
8. Si YouTube aplicaría "inauténtico" a este flujo concreto: depende de revisión humana de YouTube en la solicitud YPP.
9. Cuánto tarda un canal nuevo en alcanzar 1.000 subs y 4.000 horas con este formato.

## 2. Competidores directos en inglés

Fuente de todas las cifras: OutlierKit (agregador con análisis automático) consultado el 2026-11-01. **Todas las cifras
son [T], no verificadas contra YouTube.** Las URLs de canal oficial no se verificaron; se da la página de análisis.

| Canal | Página analizada (https) | Tamaño [T] | Frecuencia [T] | Formato y qué lo hace funcionar |
|---|---|---|---|---|
| Natural World Facts | https://outlierkit.com/channel/naturalworldfacts | 1,1 M subs; 174 videos; 138,1 M vistas; media 793 K/video | ~1,1/mes; última subida hace 335 días (en pausa) | Documentales largos cinematográficos de zonas profundas, para dormir/relajar. Vistas: Mariana 22,0 M; "Why Sharks get Creepier the Deeper you Go" 12,0 M; "Midwater" 10,0 M. Funciona por calidad de footage y tema evergreen. Colaboró con Schmidt Ocean Institute en "Mysteries of the Twilight Zone" [V: https://schmidtocean.org/newsletter05-imagery-in-the-open/] |
| BeyondTheBlue | https://outlierkit.com/channel/officialbeyondtheblue | 194 K subs; 84 videos; 37,9 M vistas; media 452 K/video | ~1,6/semana | Narrativa "Why X..." sobre gigantismo abisal y biología evolutiva; títulos de curiosidad. Top: 2,8 M, 2,7 M ("Why Squids get Creepier the Deeper you Go"), 2,5 M |
| OctoLab | https://outlierkit.com/channel/octolabyt | 77,4 K subs; 110 videos; media 200 K/video | ~3,2/semana | "Why [animal] ..." corto-medio, depredadores/océano; un video de 8,0 M (~40x sus subs). Amplio, no solo abisal |
| AbyssLab | https://outlierkit.com/channel/abysslabyt | 5,3 K subs; 30 videos; media 92,9 K/video | ~3,5/semana | Canal muy pequeño con vistas altas ("Why We Can't Truly Explore the Deep Amazon" 698 K). Mezcla geografía y vida marina; no es puramente deep sea |

Lectura: las vistas por video superan con holgura a los suscriptores en los tres canales menores [T], coherente
con la tracción que midió NicheRadar (13 canales pequeños con un video >= 5x sus subs). Pero solo uno
(Natural World Facts) es "deep sea" puro; los otros ganan con un formato "Why..." transversal. Eso implica
que el nicho puro tiene **menos evidencia de crecimiento de lo que sugiere la tabla**, y un canal nuevo
probablemente deba usar ese formato de pregunta, en ángulo abisal. Mencionados por búsqueda sin datos:
Mysteries Below, Unseen Ocean Mysteries, Simon's Sea Monsters (3,37 K subs, espejo sin fecha) [no verificados].

## 3. Flujo de producción propuesto

Objetivo: 1 video largo de 10-14 min [E]. Minutos humanos [E] por etapa; total 58 (< 60 de la compuerta). Precios
consultados el **2026-11-01**.

| Etapa | Modo | Herramientas concretas | Coste por video [E salvo indicación] | Min. humanos [E] |
|---|---|---|---|---|
| Guion e investigación | semi | Asistente de IA por API para borrador; fuentes primarias (NOAA, artículos revisados por pares) como ficha de datos; **verificación humana de cada afirmación** | US$1-3 (precio de API no verificado) | 15 |
| Voz | auto | ElevenLabs, plan Creator US$22/mes (121 K créditos, ~121 min; licencia comercial incluida) [V: https://elevenlabs.io/pricing]. La página muestra US$11 promocional el primer mes y US$22 regular según la FAQ; se usa US$22 | ~US$1,1 (12 min a ~US$22/121 min) | 3 |
| Footage e imágenes | semi | NOAA Ocean Exploration Video Portal (dominio público, crédito en la descripción) [V]; imágenes generadas (Midjourney Basic US$10 / Standard US$30 por mes, según agregadores; derechos comerciales no verificados) | US$0-3 | 12 |
| Edición | semi | DaVinci Resolve gratuito (existe versión gratis; Studio US$236 pago único) [V: https://www.blackmagicdesign.com/products/davinciresolve]; plantilla de proyecto con voz, subtítulos y música | US$0 | 15 |
| Miniaturas | semi | Imagen generada + texto en editor gratuito (no verificado qué editor); 3 variantes | US$0-1 | 8 |
| Publicación | semi | YouTube Studio: título, descripción con créditos NOAA, marcar "AI use" si aplica; programación semanal | US$0 | 5 |

Música: usar biblioteca de audio de YouTube (no verificada en esta sesión) o suscripción de terceros; Epidemic Sound
ofrece plan mensual sin permanencia pero **no pude leer precios** [V parcial: https://www.epidemicsound.com/pricing/].

**Qué se puede automatizar:** voz y gran parte de ensamblado y publicación; borrador de guion y selección de clips con búsqueda
por texto. **Debe seguir siendo humano:** verificación de hechos, ángulo/pregunta del video, juicio de retención en los primeros
30 s, aprobación final. Esto es parcial: la automatización total podría no pasar la compuerta de política (sección 4).

### Derechos del material

| Material | Origen | Estado | Fuente |
|---|---|---|---|
| Video de la NOAA Ocean Exploration Video Portal | public_domain | Dominio público; incluir crédito "NOAA Ocean Exploration". **Excepción:** si el pie dice "copyright", requiere permiso | https://oceanexplorer.noaa.gov/media-kit/ [V] |
| Imágenes de NOAA Ocean Exploration | public_domain (parcial) | La página de media kit afirma dominio público para video; para imágenes una búsqueda indica "la mayoría" en dominio público; revisar el pie de cada una | https://oceanexplorer.noaa.gov/media-kit/ |
| Otros videos de NOAA (OMAO, Digital Library) | third_party posible | Pueden incluir material con copyright de terceros; la licencia de OMAO se limita a fines educativos/informativos | https://www.omao.noaa.gov/image-licensing-usage-info [resultado de búsqueda, no leído completo] |
| Footage de Schmidt Ocean Institute | unknown | Colaboración documentada, licencia no leída; **no usar sin leer sus términos o escribirles** | https://schmidtocean.org/newsletter05-imagery-in-the-open/ |
| Imágenes generadas con IA | own_generation | Depende de los términos del generador (no verificados); contenido realista de eventos no ocurridos requiere divulgación | ver sección 4 |
| Voz sintética | licensed | ElevenLabs Starter o superior incluyen licencia comercial | https://elevenlabs.io/pricing [V] |

Veredicto de derechos propuesto: **conditional**. Condiciones: nunca implicar respaldo de NOAA; no usar el emblema de NOAA sin
consentimiento (restricción citada en resultado de búsqueda, no leída en origen); descartar clips con "copyright" en el pie;
no usar material de terceros sin leer su licencia.

## 4. Política de YouTube y riesgos

- **Contenido inauténtico**: desde el 2025-07-15 la política (antes "repetitious content") exige que el contenido no sea
  "mass-produced, generic, repetitive, or manipulative"; el contenido que parezca hecho con plantilla o intercambiable entre videos no
  es elegible. Fuente: https://support.google.com/youtube/answer/1311392 [V, leído 2026-11-01; la página muestra 2025-07-15 como última
  entrada fechada].
- **Contenido reutilizado**: reutilizar material ya en línea sin comentario original ni modificación sustancial no es monetizable;
  aplica a todo el canal incluso con permiso del autor. Footage de NOAA en dominio público **no evita** esta regla: hay que aportar guion
  y edición propios. Misma fuente.
- **IA**: permitido si el video muestra visión creativa y valor educativo; no permitido el contenido genérico de plantillas ni
  unir clips de IA inconexos para impactar. Misma fuente.
- **Divulgación**: se debe marcar "AI use" para contenido realista que no ocurrió o altera filmaciones de eventos/lugares reales;
  no hace falta para contenido no realista, ni para ayuda con guiones, títulos o miniaturas. Fuente:
  https://support.google.com/youtube/answer/14328491 [V, 2026-11-01]. Implicación: una criatura abisal "reconstruida" con IA y presentada
  como real **sí** exige divulgación; conviene etiquetarla en pantalla.
- **Requisitos YPP**: 1.000 suscriptores más 4.000 horas públicas de reproducción en 12 meses (los Shorts no cuentan para horas); la
  revisión de todo el canal tarda ~1 mes y exige no tener strikes. Fuente: https://support.google.com/youtube/answer/72851 [V].
- **Clickbait**: la política de spam sanciona el "malicious clickbait" (títulos/miniaturas que no cumplen lo prometido) con suspensión de
  monetización o cierre del canal. Fuente: https://support.google.com/youtube/answer/2801973 [V; es la página de spam].

**Riesgo de desinformación en "misterios":** no pude leer la política de desinformación de YouTube; queda en unknowns. Regla editorial
propuesta (no es política de YouTube): (1) toda afirmación científica lleva fuente primaria en la descripción; (2) "no se sabe" es
una respuesta válida, no "los científicos están aterrados"; (3) prohibido presentar criaturas mitológicas (kraken, megalodon vivo) como
posibilidad real; (4) la miniatura no puede mostrar algo que el video no muestra. Riesgo global de política: **medio-alto** si se
automatiza todo, **medio** con guion verificado y aporte propio.

## 5. Presupuesto a 6 meses (USD)

Solo costes en efectivo: **no incluye tiempo del propietario** (a ~58 min por video [E], 24 videos son ~23 h). Supuestos [E]: 12 / 24 / 36
videos en 6 meses; contingencia 10 %. Fases: F0 piloto (mes 1, 3 videos), F1 (meses 2-3, 9 videos), F2 (meses 4-6, 12 videos) para el escenario probable.

### Probable (24 videos)

| Partida | Cálculo | F0 | F1 | F2 | Subtotal |
|---|---|---|---|---|---|
| Voz ElevenLabs Creator | US$22 x 6 meses | 22 | 44 | 66 | 132 |
| Guion con IA por API [E] | US$2 x 24 videos | 6 | 18 | 24 | 48 |
| Imágenes Midjourney Basic | US$10 x 6 meses | 10 | 20 | 30 | 60 |
| Footage NOAA, DaVinci Resolve, música gratuita de YouTube | 0 | 0 | 0 | 0 | 0 |
| Contingencia 10 % | | 3,8 | 8,2 | 12 | 24 |
| **Total** | | **41,8** | **90,2** | **132** | **264** |

### Bajo (12 videos, todo gratuito salvo voz y guion)

ElevenLabs Starter US$6 x 6 = 36; guion IA [E] US$1 x 12 = 12; contingencia 10 % = 4,8. **Total US$52,8.**

### Alto (36 videos)

| Partida | Cálculo | Subtotal |
|---|---|---|
| ElevenLabs Creator | US$22 x 6 | 132 |
| Guion IA [E] | US$3 x 36 | 108 |
| Midjourney Standard | US$30 x 6 | 180 |
| Footage/video IA o stock de pago [E] | US$50 x 6 | 300 |
| Música de pago [E, precio no verificado] | US$15 x 6 | 90 |
| DaVinci Resolve Studio | US$236 x 1 | 236 |
| Miniaturas por freelance [E] | US$10 x 36 | 360 |
| Contingencia 10 % | | 140,6 |
| **Total** | | **1.546,6** |

### Punto de equilibrio (ESTIMACIÓN, no medido)

Sin tiempo humano: con un RPM supuesto de US$2-4 [E, no es el de NicheRadar ni está verificado], recuperar US$264 requiere ~66.000-132.000 vistas
monetizadas. Eso solo ocurre **después** de entrar a YPP (1.000 subs + 4.000 h; ~1 mes de revisión): en los 6 meses, la probabilidad de cubrir
el coste es baja y no debe esperarse. Con tiempo humano valorado, no hay equilibrio a 6 meses. El caso se decide por opcionalidad (activo de canal) y no por caja a corto plazo.

## 6. Plan por fases y reglas de parada

| Fase | Entregable | Criterio de salida (medible) | Regla de parada |
|---|---|---|---|
| F0 (mes 1) | 3 videos con el flujo completo; checklist de derechos y fuentes | 3/3 sin reclamación de derechos; minutos humanos <= 60 por video; 100 % de afirmaciones con fuente | Cualquier reclamo de copyright o strike: detener y revisar; o minutos humanos > 90 |
| F1 (meses 2-3) | 9 videos, 1 por semana, A/B de miniaturas | Retención media >= 35 % [E]; CTR >= 4 % [E]; al menos 1 video con vistas >= 5x subs | Si tras 12 videos acumulados las vistas medias son < 500 y no hay ningún video > 2.000: no-go |
| F2 (meses 4-6) | 12 videos más; solicitud YPP si se cumple el umbral | >= 1.000 subs y >= 2.000 h acumuladas al mes 6 (mitad de lo exigido, trayectoria hacia 4.000 h) [E] | Si a los 6 meses subs < 300: cerrar o rediseñar el formato; sin superar US$264 de gasto sin nueva decisión |
| Siempre | Revisión de política cada trimestre | Fecha de la última lectura registrada | Rechazo de YPP por "inauténtico": detener automatización y rehacer con más aporte propio antes de volver a pedir |

## 7. Fuentes

| Fuente | URL | Acceso |
|---|---|---|
| YouTube: política de monetización, inauténtico/reutilizado/IA | https://support.google.com/youtube/answer/1311392 | 2026-11-01 |
| YouTube: divulgación de contenido sintético | https://support.google.com/youtube/answer/14328491 | 2026-11-01 |
| YouTube: requisitos YPP | https://support.google.com/youtube/answer/72851 | 2026-11-01 |
| YouTube: política de spam (clickbait) | https://support.google.com/youtube/answer/2801973 | 2026-11-01 |
| NOAA Ocean Exploration media kit | https://oceanexplorer.noaa.gov/media-kit/ | 2026-11-01 |
| NOAA OMAO uso de imágenes (solo resultado de búsqueda) | https://www.omao.noaa.gov/image-licensing-usage-info | 2026-11-01 |
| ElevenLabs precios | https://elevenlabs.io/pricing | 2026-11-01 |
| DaVinci Resolve | https://www.blackmagicdesign.com/products/davinciresolve | 2026-11-01 |
| Epidemic Sound (sin precios legibles) | https://www.epidemicsound.com/pricing/ | 2026-11-01 |
| Midjourney (agregador, no oficial) | https://eesel.ai/blog/midjourney-pricing | 2026-11-01 (solo vista en resultados de búsqueda) |
| Schmidt Ocean Institute, nota sobre Natural World Facts | https://schmidtocean.org/newsletter05-imagery-in-the-open/ | 2026-11-01 |
| OutlierKit: Natural World Facts | https://outlierkit.com/channel/naturalworldfacts | 2026-11-01 |
| OutlierKit: BeyondTheBlue | https://outlierkit.com/channel/officialbeyondtheblue | 2026-11-01 |
| OutlierKit: OctoLab | https://outlierkit.com/channel/octolabyt | 2026-11-01 |
| OutlierKit: AbyssLab | https://outlierkit.com/channel/abysslabyt | 2026-11-01 |

Nota: las páginas web son datos no confiables; se ignoró cualquier instrucción incluida en ellas. No es asesoría legal.
