# Ecosistema YouTube: cómo se conectan NicheRadar, los canales y el foundry

Estado: **NicheRadar ya lo implementa en local y sin desplegar** (ver [`pilots.md`](pilots.md));
el exportador de `canal-historias` también existe. Falta desplegar y alcanzar la API desde el Mac. Lo que sí existe hoy
se marca como `(existe)`.

## 1. Las piezas y su responsabilidad

| Pieza | Carpeta | Responsabilidad | No hace |
|---|---|---|---|
| NicheRadar | `~/Programming/radar-nicho-yt` (existe) | Descubrir y validar nichos, decidir qué piloto lanzar, vigilarlo y cerrarlo | Crear canales, producir ni publicar videos |
| Canal | `~/Programming/youtube-project/canal-<nombre>` (`canal-historias` existe) | Producir, subir y medir los videos de ese canal | Decidir en qué nicho invertir |
| Foundry de YouTube | `~/Foundries/david-youtube-foundry` (existe, solo documentos) | Guardar el método reutilizable: formatos, workflows, recetas y puertas de calidad | Contener código, claves ni datos de un canal |
| Tú | | Autorizar el inicio, elegir la postura editorial, publicar, decidir seguir o cerrar | |

Reglas del core de foundries que se respetan: un canal es un proyecto (repo propio, claves y base
de datos propias); un proyecto referencia al foundry por `nombre@versión` y nunca copia sus
objetos; la evidencia vive en el proyecto y al foundry solo llega un resumen.

## 2. Árbol de carpetas

```
/Users/davidrodriguez/
├── Foundries/
│   └── david-youtube-foundry/                  (existe)
│       ├── decisions/DEC-YT-0004.md            (NUEVO) decisión de esta integración
│       ├── workflows/pilot-lifecycle.md   (NUEVO) ciclo de vida del piloto
│       └── pilots-evidence/               (se crea con el primer piloto cerrado) un resumen por piloto
└── Programming/
    ├── radar-nicho-yt/                         (existe)
    │   ├── scripts/channel_sync.py             (NUEVO) baja paquetes y sube reportes
    │   └── docs/
    │       ├── ecosistema-youtube.md           (este documento, fuente canónica)
    │       └── contracts/
    │           ├── pilot-package-v1.md    (NUEVO)
    │           └── channel-report-v1.md        (NUEVO)
    └── youtube-project/                        (carpeta, no es repo)
        ├── README.md                           (NUEVO) mapa corto con enlaces
        ├── canal-historias/                    (existe)
        │   ├── .foundry/manifest.yaml          (borrador creado 2026-10-25)
        │   └── .nicheradar/{README.md,inbox/,outbox/}   (README creado 2026-10-25; inbox/ y outbox/ con la sincronización)
        └── canal-<nombre>/                     (futuro, misma forma)
```

Nada se mueve. En `youtube-project/` el documento se llama `README.md` y **no** `CLAUDE.md`,
porque Claude Code carga los `CLAUDE.md` de las carpetas padre en cada sesión de los canales y
mezclaría contextos.

## 3. Dónde vive cada documento

Regla del core: una sola fuente canónica por tipo de información; lo demás son enlaces.

| Documento | Dónde | Qué dice | Es fuente canónica de |
|---|---|---|---|
| `docs/ecosistema-youtube.md` | NicheRadar | Este mapa completo | El diseño de la integración |
| `docs/contracts/*.md` | NicheRadar | Formato exacto de los archivos | Los contratos (NicheRadar es dueño del formato) |
| `youtube-project/README.md` | Carpeta padre | 15 líneas: qué es cada carpeta y enlaces a este documento | Nada, solo enlaza |
| `canal-*/.nicheradar/README.md` | Cada canal | Cómo correr `channel_sync.py` desde ese canal | El uso del buzón en ese canal |
| `canal-*/.foundry/manifest.yaml` | Cada canal | Qué receta y qué puertas usa, por versión | Qué método usa ese canal |
| `DEC-YT-0004.md` | Foundry | Por qué se decidió este reparto | La decisión (no se versiona) |
| `workflows/pilot-lifecycle.md` | Foundry | Los estados del piloto como método reutilizable | El método |

## 4. Ciclo de vida de un piloto

Los estados los guarda NicheRadar. Cada transición indica quién la provoca.

```
dossier listo ──(tú: «Lanzar»)──▶ autorizado ──(canal: fetch)──▶ entregado
   ──(canal: primer reporte)──▶ preparando ──(canal: primer video)──▶ en_ejecución ──(videos medidos ≥ umbral)──▶ decisión_pendiente
   ──(tú)──▶ seguir  (vuelve a en_ejecución hasta el video 10 / 20)
   ──(tú)──▶ cerrado (se escribe el resumen en el foundry)
```

| Estado | Lo provoca | Qué pasa |
|---|---|---|
| autorizado | Tú, al pulsar «Lanzar» | NicheRadar congela el dossier, el presupuesto y las reglas de parada, y crea el paquete |
| entregado | El canal, al correr `fetch` | El paquete queda en `inbox/` del canal. Es idempotente |
| preparando | El canal, con su primer reporte | El canal reporta qué le falta para estar listo (`checks`). Hay un plazo de preparación (`preparation_days`) |
| en_ejecución | El canal, al reportar su primer video | NicheRadar empieza a recibir métricas |
| decisión_pendiente | NicheRadar, al comparar con las reglas | Propone «seguir» o «parar» con los números; no decide solo |
| seguir / cerrado | Tú | Cerrar genera el resumen de evidencia para el foundry |

### 4.1 Estado, bloqueos y fechas de un piloto

Cada piloto muestra siempre tres cosas: **dónde está** (el estado), **si algo lo frena**
(bloqueos) y **cuándo habrá decisión** (fechas tentativas).

**Bloqueos.** Los calcula NicheRadar; el canal no declara bloqueos, solo hechos.

| Condición | Mensaje | Quién lo resuelve |
|---|---|---|
| Un `check` de preparación no está en `ok` | «Falta: <paso>» | Tú, o el Mac, según el paso |
| La autorización de YouTube vence en menos de 3 días o ya venció (`expires_at`) | «La autorización de YouTube vence el <fecha>» | Tú, en el Mac |
| No hay reporte hace más de 72 h | «Sin contacto con el canal desde <fecha>» | Tu Mac |
| Un video llegó con un estado que no está en la tabla del canal | «Estado desconocido: <estado>» | Tú y NicheRadar |
| El gasto real se acerca al tope o lo supera | «Gasto al X% del tope» | Tú |
| Venció el plazo de preparación sin canal listo | «Preparación fuera de plazo» | Tú |
| Venció `valid_until` sin entregarse | «Autorización vencida» | Tú |
| Un video espera la postura editorial | «Esperando tu decisión en el canal» (frena el avance, no es un fallo) | Tú, en el canal |

**Fechas tentativas.** NicheRadar las deriva y siempre las marca «tentativa» con su base:

| Fecha | Cómo se calcula |
|---|---|
| Inicio (`started_at`) | Fecha del primer video reportado. Antes de eso, las fechas cuentan desde la entrega |
| Hito «semana N» | Inicio + N semanas |
| Hito «mes N» | Inicio + N meses |
| Hito «video N» | Inicio + N ÷ cadencia, en semanas. Usa la cadencia planificada; cuando hay al menos 3 videos usa la real de los últimos 14 días |
| **Próxima revisión** | El hito más cercano que aún no se resolvió |
| **Plazo final** | El hito más lejano de las reglas de parada |

**Qué cambia de un canal a otro.** El panel tiene un marco común (estado, bloqueos, fechas,
propuesta y reglas) y **módulos que dependen de la receta y el formato**: las métricas, la lista
de preparación (`checks`) y las etapas de producción no son las mismas en un canal largo que en
uno de Shorts. Hoy el reporte solo cubre el formato largo (ver preguntas abiertas del contrato).

**Dónde se configura el canal de YouTube.** NicheRadar no guarda claves: solo el enlace público del
canal y el estado de cada paso, que informa el canal.

| Paso | Dónde se hace | Cómo se entera NicheRadar |
|---|---|---|
| Crear el canal en YouTube | Tú, en YouTube Studio | Tú registras el enlace del canal en la pestaña «Preparación» del piloto |
| Crear la carpeta del canal (copia de `canal-historias`) | Tu Mac | `check` de la carpeta del canal |
| Autorizar subida y medición | Tu Mac, con el script de autorización del canal | `check` `youtube_oauth`, con fecha de caducidad |
| Voz de referencia | Tu Mac, en el canal | `check` `voice_ref` |
| Visuales del nicho | Tu Mac, en el canal | `check` `visual_assets` |
| Idioma y formato | Ya definidos en el paquete (el idioma se fijó al iniciar la investigación) | No hace falta |

La lista exacta la define cada canal en `checks`; no es fija.

## 5. Los dos archivos de intercambio

El formato exacto vive en una sola fuente por contrato. Este documento no los repite.

| Dirección | Contrato | Qué lleva |
|---|---|---|
| NicheRadar → canal | [`contracts/pilot-package-v1.md`](contracts/pilot-package-v1.md) | Nicho, evidencia congelada, resumen del dossier, presupuesto, reglas de parada, idioma y huella de integridad |
| Canal → NicheRadar | [`contracts/channel-report-v1.md`](contracts/channel-report-v1.md) | Por video: etapa, costo real, minutos de máquina y retención medida |

Ambos siguen las convenciones de `dossier-v1`: claves desconocidas se rechazan, fechas con zona
horaria, errores sin repetir valores, y todo cambio incompatible crea una versión nueva.

## 6. Cómo se transportan (el Mac va a buscar)

NicheRadar está en el servidor y los canales en el Mac. Solo el Mac inicia conexiones.
`channel_sync.py` reutiliza el patrón de la investigación de flujo (reclamo con tiempo límite):

| Comando | Qué hace |
|---|---|
| `channel_sync.py fetch --channel-dir <canal>` | Consulta pilotos autorizados para ese canal, los reclama y los guarda en `inbox/` |
| `channel_sync.py report --channel-dir <canal>` | Sube lo que haya en `outbox/` |

Requisito de seguridad: hoy NicheRadar tiene un solo token de servicio. Con varios canales hacen
falta **tokens por canal con permiso solo sobre sus propios pilotos**.

## 7. Credenciales y datos: qué nunca sale de cada sitio

| Dato | Vive en | Sale de ahí |
|---|---|---|
| Claves y token de YouTube de un canal | `canal-*/credentials/` | Nunca |
| Base de datos del canal | `canal-*/datos/pipeline.db` | Nunca; solo viaja el reporte |
| Claves de vidIQ, YouTube de NicheRadar y token de servicio | Servidor de NicheRadar | Nunca |
| Token de sincronización de un canal | Entorno de ese canal | Nunca |
| Paquete y reporte | `.nicheradar/` | Sí, sin secretos |

## 8. Qué pasa cuando algo falla

| Situación | Efecto | Respuesta |
|---|---|---|
| Mac apagado | `fetch` no corre; el piloto queda `autorizado` | Espera; NicheRadar muestra «sin contacto hace X» |
| Paquete bajado dos veces | Sin efecto | Es idempotente por `pilot_id` |
| Reporte repetido | Sin efecto | Idempotente por `(pilot_id, video_id)` |
| Token de YouTube caducado (7 días en modo prueba) | El canal no sube ni mide | Lo ve el canal; NicheRadar solo nota que no hay reportes |
| El canal no cumple el formato | NicheRadar rechaza el reporte con el motivo | El canal corrige y reenvía |
| Cambia un contrato | Se publica `v2` aparte | `v1` sigue válido mientras algún canal lo use |

## 9. Qué hay hoy y qué falta construir, en orden

1. `(existe)` Dossier de investigación y su API con reclamo y tiempo límite.
2. Contratos `pilot-package-v1` y `channel-report-v1` (documentos).
3. `(hecho en local, sin desplegar)` En NicheRadar: tabla de pilotos, estados y endpoints (`pending`, `package`, `delivery`, `reports`), y la **tabla de traducción de estados de cada canal** (decisión 7).
4. `(hecho)` `channel_sync.py`, los tokens por canal y el **script de reporte del canal** (lee su base en solo lectura; decisión 6).
5. Manifiesto y `.nicheradar/` en `canal-historias`, sin cambiar su código. **Hecho como borrador (2026-10-25)**: `.foundry/manifest.yaml` y `.nicheradar/README.md`; faltan `inbox/` y `outbox/`, que dependen del punto 4.
6. Decisión y workflow en el foundry. **Hecho como borrador (2026-10-25)**: `DEC-YT-0004` y `pilot-lifecycle@0.1.0` (`experimental`, sin ejecución real).
7. `(hecho)` Panel de portafolio en el dashboard (el D6 del rediseño, de solo lectura).
8. Canal 2 copiando `canal-historias`; después, extraer la plantilla genérica al foundry.

## 10. Límites que siguen valiendo

- Un solo Mac: cada video ocupa 65 a 85 min de máquina y no corren dos a la vez.
- Cuota de YouTube: con el cálculo del propio código son 5 subidas al día por proyecto de Google.
- Autorización de YouTube: en modo prueba caduca cada 7 días y se multiplica por canal.
- Tiempo y presupuesto: US$ 100 al mes de objetivo y 15 horas semanales para todo junto.
- Ningún canal tiene tracción demostrada todavía; no se debe abrir muchos canales antes de
  revisar la regla de retención de `canal-historias`.

## 11. Decisiones tomadas (2026-10-25)

| # | Tema | Decisión |
|---|---|---|
| 1 | Nombre | «Piloto» para la apuesta sobre un nicho (no «experimento», que en el foundry es otro objeto) |
| 2 | Exención del canal | `exempt: experiment` en el manifiesto de `canal-historias` |
| 3 | Vigencia de la autorización | `valid_until` de 14 días por defecto, editable al autorizar |
| 4 | Pilotos por canal | Uno activo por canal (`channel_busy`) |
| 5 | Hitos fallidos para cerrar | Editable solo al autorizar, nunca después |
| 6 | Quién genera el reporte | Un script aparte en el canal, con su base en solo lectura |
| 7 | Quién traduce los estados | NicheRadar, con una tabla por canal (el reporte lleva `source_state`) |

## 12. Preguntas abiertas

- ¿Cómo se miden los pilotos de **Shorts**? El reporte v1 es de formato largo (ver `channel-report-v1`).

- ¿Cuándo entran los ingresos al reporte? Se decidirá cuando el canal los mida (sería `v2`).
- ¿Los buzones `inbox/` y `outbox/` entran a git? Propuesta: no, solo el manifiesto y el README.
