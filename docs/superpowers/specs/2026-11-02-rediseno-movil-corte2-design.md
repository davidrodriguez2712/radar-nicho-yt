# Rediseño móvil, corte 2: pilotos, preparación y minutos humanos automáticos

Estado: borrador para revisión del propietario (2026-11-02). Continúa
[`2026-11-02-rediseno-movil-web-design.md`](2026-11-02-rediseno-movil-web-design.md) (corte 1, ya en `main`).
Diseño: Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil»: M5 `20:111`, M6 `20:246`, M7 `20:410`, M13 `35:2`, M14 `36:2`.

## Problema

El corte 1 termina cuando el propietario autoriza un piloto. Después de eso la web no muestra nada: el seguimiento (¿dónde
está el piloto?, ¿qué lo frena?, ¿cuándo hay decisión?) sigue en Streamlit, y el Figma de calibración (M13) pide un dato
que hoy no existe en ninguna parte: **los minutos humanos por video**. Hoy esos minutos son «declarados por el
propietario, no cronometrados» (`docs/contracts/dossier-v3.md`), y el propietario decidió que **no registrará nada a
mano**.

## Objetivo

1. Que el propietario siga sus pilotos desde el teléfono: lista (M5), panel (M6), preparación del canal (M7),
   calibración (M13) y el «Hoy» completo (M14), y que pueda decidir `seguir`, `cerrar` o `cancelar` desde ahí.
2. Que los minutos humanos por video lleguen **solos** desde el canal, con un método declarado y honesto sobre su
   precisión.
3. Que la pantalla de calibración compare esos minutos contra el criterio de salida del informe (por ejemplo, «3 videos
   seguidos bajo 60 minutos») sin que nadie los teclee.

## Hechos comprobados (leídos del código el 2026-11-02)

- `GET /pilots` y `GET /pilots/{id}` ya entregan estado, `needs_decision`, `proposal`, `totals`, `evaluation` (reglas e
  hitos), `events`, `acknowledged`, `delivered_at`, `valid_until`, `channel_last_contact_at` y `channel` (`checks[]`,
  `note`). **No entregan los videos del piloto** (solo agregados).
- No hay estado «preparando» en el servicio. La preparación se puede **derivar**: `autorizado` → `entregado`
  (`delivered_at`), `checks[]` que informa el canal (`youtube_oauth`, `youtube_upload_scope`, `phone_verified`,
  `api_audit`, `rights_cleared`, `voice_ref`, `visual_assets`, cada uno con `ok`, `detail` y `expires_at`), y
  `preparation_days` del paquete.
- El contrato del reporte de canal (`channel-report-v1` largos, `-v2` shorts) trae `machine_minutes` por video y **ningún
  campo de minutos humanos**. La evaluación del piloto no conoce la calibración (el paquete congelado solo lleva el
  resumen del dossier, sin `calibration`).
- El productor de reportes **no está en este repositorio**: vive en cada canal (`~/Programming/youtube-project/canal-historias`,
  `pipeline/reporte_canal.py` y `scripts/reporte_nicheradar.py`). Este repositorio solo tiene el cargador
  (`scripts/channel_sync.py`), que sube el archivo sin tocarlo.
- El pipeline del canal ya registra cada transición de estado con hora y actor en la tabla `eventos` (por ejemplo
  `VEREDICTOS_PENDIENTES` → acción de un actor `humano:*`, elección de miniatura, `PROGRAMADO`, `PUBLICADO`). Hoy esa
  espera **no se cuenta** como tiempo de máquina y tampoco como tiempo humano.
- `canal-historias` está **en producción publicando videos**; cualquier cambio de su pipeline es de alto impacto.

## Diseño

### 1. Dos entregas

El corte 2 se parte en dos para que lo visible no espere a lo difícil.

**2a. Seguimiento de pilotos (sin cambio de contratos):** M5, M6, M7, M14 y las acciones `seguir`/`cerrar`/`cancelar`,
con lo que la API ya entrega más **un endpoint nuevo de solo lectura** para los videos (sección 3). Habilita la pestaña
«Pilotos». M13 queda fuera hasta 2b; el panel de un piloto en calibración se muestra como M6 con lo que haya.

**2b. Minutos humanos automáticos y calibración:** contrato `channel-report-v3`, ingestión, productor en el canal, y la
pantalla M13 con la racha de calibración.

2b depende de que el propietario apruebe el método (sección 5) y de tocar el pipeline del canal; 2a no depende de eso.

### 2. Pantallas de 2a

| Pantalla | Ruta | API |
|---|---|---|
| M5 Lista de pilotos | `/pilotos` | `GET /pilots?limit=100` |
| M6 Panel (pestañas Resumen · Preparación · Videos · Reglas · Historial) | `/pilotos/{pilot_id}` | `GET /pilots/{id}`, `GET /pilots/{id}/videos` (nuevo), `GET /flow-research/{dossier_request_id}` solo para el título |
| M7 Preparación del canal | `/pilotos/{pilot_id}/preparacion` | `GET /pilots/{id}` (`channel.checks`, `delivered_at`, `package.preparation_days`, `events`) |
| Decidir / cerrar / cancelar | `POST /pilotos/{pilot_id}/decidir`, `/cancelar` | `POST /pilots/{id}/decision`, `/cancel` |
| Resumen de cierre | `/pilotos/{pilot_id}/cierre` | `GET /pilots/{id}/closing-summary` (texto) |
| M14 Hoy completo | `/` | lo del corte 1 más la tarjeta «pilotos que necesitan algo» con acciones reales |

Reglas de datos (se omite lo que la API no entrega, igual que en el corte 1):

- **Estados de la lista:** `autorizado` → «Autorizado», `entregado` → «Preparando», `en_ejecucion` → «En ejecución»,
  `decision_pendiente` → «Decisión pendiente», `cerrado`, `cancelado`. Filtros del Figma: Todos, Activos, Con bloqueo,
  Cerrados. «Con bloqueo» = el piloto tiene al menos un bloqueo derivado (abajo).
- **Bloqueos y avisos** (se derivan en el servidor web, nunca se inventan): un `check` con `ok = false` («Falta: …» con su
  `detail`), un `check` con `expires_at` en los próximos 7 días («vence el …»), `valid_until` próximo sin entrega, ningún
  contacto del canal hace más de 48 h (`channel_last_contact_at`), videos en estado `unknown` (`totals.by_stage`), y
  `needs_decision`.
- **Siguiente acción tuya:** solo las que se pueden afirmar: `needs_decision` («Decide si sigue o cierra»),
  `by_stage.awaiting_human > 0` («N videos esperan tu veredicto en el canal»), `autorizado` sin entrega («Falta que tu Mac
  baje el paquete»). La frase del Figma «Elegir la postura editorial del video 4» no se puede derivar y se omite.
- **Fechas:** «Próxima revisión (tentativa)» solo si hay base: el hito de semana o de mes se calcula desde
  `authorized_at`; un hito de video se calcula si el paquete trae cadencia planificada; si no, se muestra «al llegar al
  video N». El plazo de preparación es `delivered_at + preparation_days`. Todas se rotulan «tentativa».
- **Costos y tiempos:** `totals.spent_usd` contra `budget.high` del paquete, `equivalent_usd` («no se suma») y
  `machine_minutes` (con «incompleto» si `machine_minutes_complete` es falso).
- **M7:** pasos = `checks[]` que informa el canal; no hay pasos fijos. Cada paso muestra `label`, estado y `detail`;
  los datos de proveedor son del canal, no de NicheRadar. La pantalla dice qué guarda NicheRadar (enlace público, estado de
  pasos) y que **ninguna clave ni token pasa por la web**. La **emisión del token del canal sigue en la línea de
  comandos** (`scripts/pilots.py token-issue`): mostrar un secreto una sola vez en una web con sesión de contraseña es un
  riesgo que no se justifica.
- **Acciones:** `seguir` y `cerrar` exigen una nota de 1 a 1500 caracteres y una **pantalla de confirmación** (es
  irreversible: un piloto cerrado no se reabre). `cancelar` solo existe en `autorizado` y `entregado`. Los tres son POST con
  CSRF; la nota se escapa siempre.

### 3. Cambios en la API privada (2a)

Uno solo, de solo lectura y sin migración: `GET /pilots/{pilot_id}/videos` → `{items: [{video_id, source_state, stage,
visibility, published_at, cost_usd, cost_equivalent_usd, machine_minutes, failure_code, measurement}]}`, con las mismas
reglas de autorización que `GET /pilots/{id}` (service token; un token de canal solo ve los suyos). Los datos ya están en
`pilot_videos`. Sin este endpoint no hay pestaña «Videos» ni, después, racha de calibración.

Además, `GET /pilots` añade a cada item tres campos **aditivos** que ya existen en el detalle (`valid_until`, `delivered_at` y
`channel`), para que la lista muestre los bloqueos del canal sin hacer una llamada de detalle por piloto.

### 4. `channel-report-v3` (2b)

Contrato nuevo, **aditivo**: igual que v1 (largos) o v2 (shorts) más, por video, `human_minutes` (entero ≥ 0 o `null`) y,
a nivel de reporte, `human_minutes_method` (cadena corta que nombra el método, p. ej. `gate_waits_capped_v1`). Valor
`null` = «el canal no pudo medirlo» (nunca 0 por defecto). v1 y v2 siguen aceptándose; los pilotos antiguos no cambian.

Cambios en este repositorio: modelo en `pilots/contracts.py` (`AnyReport`, `REPORT_FORMAT`, `validate_report`),
columnas `human_minutes` (int, nullable) y `human_minutes_method` (texto, nullable) en `pilot_videos` por **migración
nueva** (se aplica en producción en una release con aprobación), totales `human_minutes` y `human_minutes_complete` en
`_totals` (mismo patrón que `machine_minutes`), y documentación `docs/contracts/channel-report-v3.md`. `channel_sync.py`
no cambia (es neutral al contrato).

### 5. Cómo se miden los minutos humanos sin que nadie los teclee

No existe una medida perfecta del esfuerzo humano: lo que el pipeline puede observar son **esperas en las compuertas
humanas**, no atención. El método propuesto lo dice con honestidad y limita el error:

**Método `gate_waits_capped_v1` (recomendado).** Por video, los minutos humanos son la suma de las ventanas de atención
humana que el pipeline ya delimita con eventos: (a) desde que el video entra a una compuerta humana
(`VEREDICTOS_PENDIENTES`, elección de miniatura/empaquetado) hasta el evento del actor `humano:*`; (b) desde que el video
queda subido en privado hasta que se programa (`PROGRAMADO`). **Cada ventana se limita a un tope** (por defecto 15 min,
configurable en el canal) para no contar esperas largas en las que el propietario no estaba mirando. El reporte declara
el método y el tope usados. Es una **estimación**: la pantalla M13 la rotula «estimado» y no la mezcla con minutos
declarados.

Alternativas evaluadas:

- **Hooks de Claude Code en la carpeta del canal** (`UserPromptSubmit` y `Stop` registran la hora; el hueco entre el fin de
  un turno del agente y el siguiente mensaje, con tope, es tiempo humano). Más fiel para el tiempo de dar instrucciones,
  pero no ve la validación en YouTube Studio y exige instalar y mantener hooks en cada canal. Se deja como mejora futura
  sobre el mismo campo `human_minutes_method`.
- **Leer los registros de sesión de Claude Code.** Máxima fidelidad, pero asocia sesiones a videos con heurísticas
  frágiles y toca archivos privados del usuario. Descartado.

**Dónde vive el proceso (decisión del propietario, 2026-11-02):** en **este** repositorio, sin modificar nada de
`canal-historias`. Un script nuevo, `scripts/channel_human_minutes.py`, abre en **solo lectura** la base del canal
(`datos/pipeline.db`, tabla `eventos`), calcula los minutos humanos por video con el método elegido, y los añade al archivo
de reporte que el canal ya deja en su `outbox` (v1 o v2), convirtiéndolo en `channel-report-v3`; después `channel_sync.py`
lo sube como hoy. El canal no necesita saber que existe. Límites que se aceptan: el script depende del **esquema de
lectura** de la tabla `eventos` (columnas `video_id`, `de_estado`, `a_estado`, `actor`, `creado_en`), así que un cambio de
ese esquema en el canal exige actualizar el script, y el reporte lo arma el script de este repositorio, no el canal.

**Hallazgo del 2026-11-03 sobre el método `gate_waits_capped_v1` (leído de la base real de `canal-historias`).** Antes de
implementar se midió qué dicen los eventos del canal. Resultado: (1) la única compuerta humana del pipeline es
`VEREDICTOS_PENDIENTES` → `humano:aprobar-veredicto`, y su espera real tiene mediana de **menos de 1 minuto** (13 valores
entre 0,1 y 0,2 min; colas de 13 a 286 min); (2) la elección de miniatura la hace el humano solo en 10 de 36 videos, y su
ventana incluye tiempo de máquina del agente; (3) **no existe** ningún evento de «subido en privado → programado»: la
validación en YouTube Studio no deja rastro, y la instrucción que se escribe en Claude Code tampoco. Consecuencia: las
esperas en compuertas **subestiman por un orden de magnitud** el tiempo humano declarado (≈1 a 5 min medidos contra ≈20
declarados), así que una racha «3 videos seguidos bajo 60 minutos» se cumpliría siempre y la calibración no informaría
nada. Por eso el método de esperas **no se implementa tal cual**: la decisión sobre el método queda reabierta (ver «Decisiones
pendientes»). Lo que **no** depende del método (contrato v3, migración, ingestión, API y pantalla M13) sí se hace, con
`human_minutes_method` declarando siempre cómo se obtuvo cada cifra.

### 6. Calibración (M13, 2b)

La calibración **se calcula al leer**, no se guarda ni se congela en el paquete (sin cambio del contrato
`pilot-package-v1`): la web toma `calibration` del dossier (`GET /flow-research/{dossier_request_id}`), los
`human_minutes` por video de `GET /pilots/{id}/videos` y calcula: videos publicados de calibración, minutos por video, racha
actual de videos seguidos bajo `exit_criterion.max_minutes_per_video`, horas de calibración acumuladas (más
`setup_hours`) contra las previstas, y «pasa a régimen» cuando la racha llega a `consecutive_videos`. Videos sin
`human_minutes` (`null`) **no cuentan en la racha** y se marcan «sin medir». Es una **sugerencia de la web**, no un estado
del piloto: pasar a régimen no cambia nada en el servicio. Si en la práctica se quiere una regla de parada o un hito
evaluado por el servidor (`human_minutes` como métrica de `stop_rules`), es un cambio de contrato posterior y separado.

### 7. Seguridad

Todo lo del corte 1 sigue vigente (cookie firmada, CSRF, CSP propia, escape, identificadores validados con `fullmatch`,
errores de API en español, `shape_guard` en las pantallas). Específico de este corte: los tres POST nuevos (`decidir`,
`cancelar` y la confirmación) validan CSRF antes de llamar a la API; la nota del propietario y todo texto de `checks[]`,
`note` o `events[].detail` (los escribe el canal) se tratan como no confiables; el `pilot_id` se valida con
`^pil_\d{8}_[a-z0-9_-]+$` (`fullmatch`) antes de usarse; ningún token de canal ni clave se muestra.

## Compatibilidad y despliegue

- Nada de lo de este corte modifica el repositorio del canal: el cálculo de minutos humanos corre desde este repositorio.

- 2a no cambia contratos ni base de datos; añade una ruta de lectura a la API. Se despliega con la imagen de la API y la del
  dashboard (release con aprobación).
- 2b añade una migración de base de datos y toca el pipeline de un canal en producción: se despliega en dos pasos
  (primero la API acepta v3 y guarda minutos, después el canal empieza a enviarlos); un reporte v1/v2 sigue siendo válido.
- `NR_DASHBOARD_UI` sigue en `streamlit` por defecto hasta la paridad (corte 3).

## Riesgos y casos a probar

1. Pilotos con `checks[]` vacíos, `channel` nulo, fechas sin zona, estados desconocidos y listas de 100 elementos (aviso de
   recorte): ninguna pantalla da 500.
2. Texto hostil en `note`, `checks[].label/detail`, `events[].detail`, `close_reason` y títulos: escapado en M5, M6 y M7.
3. `seguir`/`cerrar`/`cancelar` sin CSRF, con nota fuera de rango, sobre un piloto en estado incorrecto (409 de la API):
   mensaje claro, sin doble envío, y la API no recibe nada si falla la validación local.
4. Reporte v3 con `human_minutes` nulos, negativos, enormes o en un piloto de otro formato; v1/v2 siguen válidos.
5. Racha de calibración con videos sin medir, con empates en el umbral (`≤` o `<`: se sigue el texto del criterio), con
   menos videos que `consecutive_videos`, y con un dossier v1/v2 sin `calibration` (M13 no aparece; se muestra M6).
6. Móvil a 360 y 390 px sin desplazamiento horizontal; pestañas del panel accesibles con teclado; objetivos táctiles de
   al menos 44 px.
7. Con el pipeline del canal sin actualizar (reportes v1), M6 y M7 funcionan y M13 dice «aún sin minutos medidos».

## Fuera de alcance

Emisión de tokens de canal desde la web; reabrir un piloto cerrado; una regla de parada evaluada por el servidor con
minutos humanos; hooks de Claude Code o lectura de registros de sesión como fuente de minutos; las pantallas de
paridad con Streamlit (corte 3); desplegar nada.

## Decisiones del propietario (2026-11-02)

2. **Dónde vive el proceso de minutos humanos:** en este repositorio, sin tocar `canal-historias` (ver sección 5). Resuelto.
3. **Orden:** 2a primero, 2b después. Resuelto.

## Decisiones cerradas (continuación)

4. **Tope de cada espera humana:** 15 minutos, configurable (aplica a cualquier método basado en ventanas). Resuelto.

## Decisiones cerradas (2026-11-03)

1. **Método de minutos humanos: (C) más (B) como suelo.** El tiempo activo se lee de los registros de sesión de Claude Code
   de la carpeta del canal (solo lectura, desde este repositorio, tope de 15 min por hueco) y se suma el supuesto fijo
   declarado por canal para lo que no deja rastro (validación en YouTube Studio). Ambos números son visibles
   («medido X · supuesto Y») y `human_minutes_method` lo declara siempre. Resuelto; el productor
   `scripts/channel_human_minutes.py` ya no está bloqueado (necesita su propio plan).
