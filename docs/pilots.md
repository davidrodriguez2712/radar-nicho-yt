# Pilotos de canal: guía de implementación

Diseño y reparto de responsabilidades: [`ecosistema-youtube.md`](ecosistema-youtube.md).
Alta de un canal operado por el agente: [`contracts/channel-onboarding-v1.md`](contracts/channel-onboarding-v1.md) y
[`runbook-canal-piloto.md`](runbook-canal-piloto.md).
Formatos exactos (fuente única): [`contracts/pilot-package-v1.md`](contracts/pilot-package-v1.md)
[`contracts/channel-report-v1.md`](contracts/channel-report-v1.md) (formato largo) y
[`contracts/channel-report-v2.md`](contracts/channel-report-v2.md) (Shorts) y
[`contracts/channel-report-v3.md`](contracts/channel-report-v3.md) (v1/v2 más minutos humanos). Este documento no los repite:
dice **dónde está el código, cómo se usa y en qué se aparta o completa el contrato**.

Estado (2026-10-25): **desplegado** en producción (release
[013](release-20261025-013.md), migración `0015`, sin pilotos reales todavía). La API no tiene
dominio público: el Mac entra por túnel SSH (ver «Alcanzar la API desde el Mac»).

## Mapa del código

| Pieza | Archivo |
|---|---|
| Contratos y huella canónica | `src/nicheradar/pilots/contracts.py` |
| Tabla de traducción `source_state` → `stage` | `src/nicheradar/pilots/translation.py` |
| Reglas de parada y propuesta (`seguir` / `cerrar` / sin datos suficientes) | `src/nicheradar/pilots/rules.py` |
| Servicio (autorizar, entregar, reportar, decidir, cancelar, resumen) | `src/nicheradar/pilots/service.py` |
| Tokens por canal (solo se guarda el SHA-256) | `src/nicheradar/pilots/tokens.py` |
| Rutas HTTP | `src/nicheradar/pilots_api.py` (registradas en `api.py`) |
| Panel «Portafolio» de solo lectura | `src/nicheradar/pilots_dashboard.py` |
| Acciones del humano | `scripts/pilots.py` (`src/nicheradar/pilots/cli.py`) |
| Sincronización desde el Mac | `scripts/channel_sync.py` (solo biblioteca estándar) |
| Tablas | migración `0015_pilots.py`: `pilots`, `pilot_videos`, `pilot_events`, `channel_tokens` |

## Estados

El estado se guarda con códigos **ASCII**; los documentos usan la forma con tilde.

| En los documentos | En la API y la base |
|---|---|
| autorizado, entregado | `autorizado`, `entregado` |
| en ejecución | `en_ejecucion` |
| decisión pendiente | `decision_pendiente` |
| cerrado | `cerrado` |
| (cancelado antes de ejecutar, o reemplazado por `supersedes`) | `cancelado` |

`cancelado` es una adición de esta implementación: el contrato habla de reemplazo con
`supersedes` y de cierre, pero no dice cómo se descarta un piloto que nunca arrancó.

## Rutas

| Ruta | Quién | Nota |
|---|---|---|
| `POST /api/v1/pilots`, `GET /api/v1/pilots` | Humano (token de servicio) | «Lanzar» y listar; cada item de la lista incluye además `valid_until`, `delivered_at` (`null` sin entregar) y `channel` (último bloque reportado: `reported_at`, `channel_status`, `checks`, `note`; `null` sin reportes) |
| `POST /api/v1/pilots/{id}/decision`, `/cancel`, `GET …/closing-summary` | Humano | `seguir` / `cerrar`; el resumen es markdown `EVD-…` |
| `GET /api/v1/pilots/pending?channel=` | Canal o humano | Autorizados, vigentes, sin entregar |
| `GET …/{id}/videos` | Canal o humano | `{"items": [...]}` con los videos reportados (`video_id`, `source_state`, `stage`, `visibility`, `published_at`, `cost_usd`, `cost_equivalent_usd`, `machine_minutes`, `human_minutes`, `human_minutes_method`, `failure_code`, `measurement`), por `published_at` ascendente (sin fecha al final) y luego `video_id`; `measurement` es `null` o solo sus campos con valor (los de Shorts incluidos). Misma visibilidad que el detalle: lo ajeno o inexistente responde `404` |
| `GET …/{id}/package`, `POST …/{id}/delivery`, `POST …/{id}/reports`, `GET …/{id}` | Canal o humano | Un token de canal ve solo lo suyo; lo ajeno responde `404` |
| `POST/GET /api/v1/channel-tokens`, `DELETE …/{token_id}` | Humano | El token se muestra una sola vez |

## Piloto sin canal asignado

Con `target_channel = null` el piloto aparece en `pending` de **cualquier** canal que tenga token.
El primero que confirma la entrega lo recibe: NicheRadar guarda ese canal en la base (el paquete
congelado no cambia, su huella tampoco) y desde entonces nadie más lo ve. Si ese canal ya tiene
otro piloto abierto, la confirmación responde `409 channel_busy` y el piloto sigue `autorizado`
y sin asignar. Lo garantiza un índice único parcial, no solo una comprobación previa.

## Traducción de estados

El canal manda su estado interno (`source_state`); NicheRadar lo traduce con
`translation.py`. Para `canal-historias` es la tabla del contrato. Decisiones de implementación:

- Un estado ausente de la tabla, o un canal sin tabla, da `stage = unknown`: se acepta, hay
  advertencia («N video(s) con un estado del canal sin traducir») y queda a revisión humana.
- `PUBLICADO` con `visibility = unknown` también da `unknown`; no se adivina.
- Las reglas de coherencia se comprueban **después** de traducir: `published` y `measuring`
  exigen `published_at` y `visibility = public`.
- `checks` es opcional (ausente = lista vacía), como dice el contrato desde 2026-10-25.

Para alta de otro canal: añadir su tabla en `TABLES` (y su estado «publicado» en
`PUBLISHED_STATE` si depende de la visibilidad) y una prueba.

`canal-speedrun-ledger` ya está dado de alta y comparte la tabla de `canal-historias` (copia su máquina
de estados); `tests/test_channel_onboarding.py` fija los 16 estados. Proceso completo de alta de un canal:
[`contracts/channel-onboarding-v1.md`](contracts/channel-onboarding-v1.md) y [`runbook-canal-piloto.md`](runbook-canal-piloto.md).

## Cómo se usa

```bash
# 1. Humano: emitir un token para el canal (se imprime una vez)
uv run python scripts/pilots.py token-issue --channel canal-historias --label mac
# 2. Humano: lanzar un piloto desde un dossier listo (el idioma ya viene del dossier: se eligió al iniciar la investigación)
uv run python scripts/pilots.py authorize --niche-label "…" --format long \
  --dossier-id <uuid> --low 3 --likely 19 --high 41 --max-videos 10 --basis "…" \
  --authorized-by david
#    (si el piloto no pasa las compuertas de selección falla con gate_failed; --accept-gate-failure
#     lo acepta de forma explícita y queda registrado: ver docs/flow-research.md)
# 3. Mac: bajar y reportar (el token es el del canal, no el de servicio)
export NR_SYNC_URL=http://127.0.0.1:18000 NR_SYNC_TOKEN=nrc_…
uv run python scripts/channel_sync.py fetch  --channel-dir ~/Programming/youtube-project/canal-historias
uv run python scripts/channel_sync.py report --channel-dir ~/Programming/youtube-project/canal-historias
# 4. Humano: cuando el piloto esté en decisión pendiente
uv run python scripts/pilots.py show <pilot_id>
uv run python scripts/pilots.py decide <pilot_id> cerrar --note "…"
uv run python scripts/pilots.py summary <pilot_id> --out resumen.md   # evidencia para el foundry
```

`channel_sync.py` rechaza `http` fuera de localhost, no sigue redirecciones, recalcula la huella
del paquete y no imprime el token. El reporte lo genera el script del canal
(`canal-historias/scripts/reporte_nicheradar.py`), que lee su base en solo lectura.

## Alcanzar la API desde el Mac

La API de NicheRadar **no tiene dominio público** (regla del repositorio). Decidido el
2026-10-25: el Mac la alcanza por **túnel SSH**, sin publicar nada. `channel_sync.py` funciona con
cualquier URL alcanzable; `scripts/pilots_tunnel.py` abre el túnel y deja la API en
`http://127.0.0.1:<puerto local>` (http solo se admite en localhost). Publicar un subdominio
queda descartado por ahora: exigiría quitar el Basic Auth del proxy, que chocaría con el `Bearer`.

## Respaldos (tarea 9.4)

Decidido el 2026-10-25: las tablas de pilotos se respaldan. `scripts/backup_snapshot.py` las
admite con filas (`PILOT_TABLES`) y reporta `scope = "bootstrap+pilots"`; `channel_tokens` solo
guarda hashes. Los datos de investigación de mercado y de flujo siguen bloqueando el respaldo.
La revisión esperada es `0020` (la migración `0017` añadió `pilot_shorts_measurements`; la `0018`, `listing_channel_snapshots`, evidencia de proveedor sin filas en el respaldo; la primera se
respalda con el resto de las tablas de pilotos; la `0020` añade las tablas del descubrimiento de subnichos y la guarda del respaldo se fijó en esa revisión).

## Diferencias con el contrato

| Tema | Contrato | Implementación |
|---|---|---|
| Código de estado | `en_ejecución` (texto) | `en_ejecucion` (código ASCII) |
| `cancelado` | No existe | Existe (ver arriba) |
| `PUBLICADO` + visibilidad `unknown` | No dicho | `unknown` + advertencia |
| Reglas de parada por defecto | Ejemplos en el contrato | `DEFAULT_STOP_RULES` en `service.py` (semana 6, retención 18 % en 3 de 10, exploración 30 % al video 20, ingresos ≥ costo al mes 6) |

## Pruebas

`tests/test_pilot_contracts.py`, `test_pilot_rules.py`, `test_pilots_api.py`,
`test_channel_sync.py`, `test_pilots_dashboard.py`, `test_pilots_cli.py`, `test_pilots_schema.py`
(las de API y esquema usan PostgreSQL temporal: `NR_TEST_POSTGRES_BIN`).

## Minutos humanos (channel-report-v3)

Contrato: [`contracts/channel-report-v3.md`](contracts/channel-report-v3.md). Solo `channel-report-v3` trae `human_minutes` por video (entero 0..100000 o `null` = no medido, clave obligatoria) y `human_minutes_method` por reporte (migración `0021`).

| Caso | Efecto sobre lo guardado |
|---|---|
| `v3` con `reported_at` más nuevo | Reemplaza minutos y método, también con `null` (sobrescribe con NULL: el último reporte es la verdad) |
| `v3` con `reported_at` igual o anterior | No cambia nada (minutos y método se conservan juntos). Se evalúa por video contra el `reported_at` guardado de cualquier versión: un `v3` más viejo que un `v1`/`v2` posterior del mismo video se ignora |
| `v1` / `v2` | Nunca tocan los minutos ni el método guardados |

`totals` añade `human_minutes` (suma de los no nulos, 0 si ninguno está medido) y `human_minutes_complete` (verdadero solo si todos los videos tienen dato; con cero videos es vacuamente verdadero y el total es 0). Con un piloto con al menos un video y sin mediciones el total es 0 con `complete = false`: léase «sin medir», nunca 0 minutos. La migración añade un `CHECK` de no negatividad (`human_minutes IS NULL OR >= 0`); el rango 0..100000 lo exige el contrato. El resumen de cierre muestra «Minutos humanos» con «(incompleto…)» en ese caso.

Método decidido (2026-11-03): tiempo activo de los registros de sesión de Claude Code más un supuesto fijo por canal, «medido X · supuesto Y»; el productor es `scripts/channel_human_minutes.py` (sección siguiente).


### Productor de minutos humanos: `scripts/channel_human_minutes.py`

Flujo completo, en el Mac del propietario:

```bash
uv run python scripts/channel_sync.py fetch --channel-dir ~/Programming/youtube-project/canal-historias
# … trabajo en el canal con Claude Code …
uv run python scripts/channel_human_minutes.py --channel-dir ~/Programming/youtube-project/canal-historias --dry-run   # solo muestra
uv run python scripts/channel_human_minutes.py --channel-dir ~/Programming/youtube-project/canal-historias
uv run python scripts/channel_sync.py report --channel-dir ~/Programming/youtube-project/canal-historias
```

Lee en solo lectura los registros de sesión de Claude Code de la carpeta del canal y `datos/pipeline.db`, y reescribe los reportes `v1`/`v2` del outbox como `channel-report-v3` (método `claude_sessions_plus_assumed`). Los que ya son v3 se omiten. Cada original se conserva como `*.json.orig`.

| Parámetro | Efecto |
|---|---|
| `--channel-dir` | Carpeta del canal (obligatorio) |
| `--assumed-minutes` | Supuesto fijo por video para la validación en YouTube Studio (por defecto 10) |
| `--cap-minutes` | Tope por hueco entre mensajes (por defecto 15) |
| `--sessions-home` | Carpeta base de Claude Code (repetible; por defecto `~/.claude` y `~/.claude-alt`) |
| `--sessions-dir` | Carpeta de sesiones explícita (repetible; sustituye a la deducida del canal) |
| `--db` | Base del canal (por defecto `<canal>/datos/pipeline.db`) |
| `--dry-run` | Calcula e imprime sin escribir nada |

**Qué mide.** Tiempo activo humano en Claude Code: el hueco entre el evento previo de cualquier tipo (respuesta de Claude, resultado de herramienta, sistema) de la misma sesión y cada mensaje humano, con tope de 15 min por hueco. Solo cuenta lo que el humano tarda en leer y escribir: excluye el tiempo mientras Claude trabaja, así que la cifra es un piso del tiempo humano. Cada mensaje se reparte en partes iguales entre los videos en producción cuya ventana contiene su hora; la ventana va del primer evento del video al primer estado PROGRAMADO/PUBLICADO (o al último evento si no hay). Un video cuya ventana empieza antes del primer registro disponible queda en `null` («sin cobertura de registros»); uno con la ventana cubierta pero sin mensajes mide 0 real (más el supuesto). Sin registros de sesión o sin mensajes humanos el script no convierte nada y sale con código 1.

**Qué NO mide.** La validación en YouTube Studio (se suma el supuesto fijo de 10 min por video), el trabajo fuera de Claude Code, ni el tiempo que cae fuera de toda ventana: eso se informa como «sin atribuir».

**Por qué es una estimación.** Los videos se solapan y el tiempo se reparte a partes iguales; el primer mensaje de cada archivo cuenta 0; y una parte grande del tiempo puede caer fuera de las ventanas. En una corrida en seco real sobre el canal del propietario, la mayor parte del tiempo medido quedó sin atribuir, así que las cifras por video deben leerse como cota inferior más el supuesto, no como tiempo exacto.

**Salida.** Por video, «medido X · supuesto Y = Z min» (el contrato lleva solo Z; el desglose no viaja). Al principio imprime los totales y el porcentaje «sin atribuir»; imprime también «archivos de sesión ilegibles o truncados: N»; con más del 60 % sin atribuir o con N > 0 avisa de que las cifras por video subestiman el tiempo medido.

**Privacidad.** Usa marcas de tiempo, tipos de registro y `sessionId`; además lee `isMeta`, `isSidechain` y `toolUseResult` y analiza `message.content` solo en memoria para clasificar el mensaje, sin guardarlo ni imprimirlo nunca. Una sesión reanudada en otro archivo de registro pierde su primer hueco.

**Rollback.** Restaurar `*.json.orig` sobre el `*.json` del outbox (el script no sobrescribe un `.orig` existente; si se reutiliza el nombre de un reporte, queda el `.orig` antiguo). Solo sirve ANTES de `channel_sync.py report`: después el archivo está en `outbox/sent/` y el servidor ya guardó los valores.
