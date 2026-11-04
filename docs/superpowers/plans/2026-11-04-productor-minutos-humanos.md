# Productor de minutos humanos (`scripts/channel_human_minutes.py`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un script de este repositorio convierta los reportes de `outbox/` de un canal (v1 o v2) en `channel-report-v3` con los minutos humanos por video, para que la calibración de la web (M13/M14) deje de decir «Aún sin minutos medidos».

**Architecture:** Script nuevo `scripts/channel_human_minutes.py`, solo biblioteca estándar (corre en el Mac, igual que `scripts/channel_sync.py`). Lee en **solo lectura** (1) los registros de sesión de Claude Code de la carpeta del canal y (2) la base del canal (`datos/pipeline.db`, tabla `eventos`); calcula el tiempo humano activo con tope por hueco, lo reparte entre los videos «en producción» en ese momento, suma el supuesto fijo declarado por canal para lo que no deja rastro (validación en YouTube Studio) y reescribe cada archivo del `outbox` como v3. Después `channel_sync.py report` lo sube tal cual. No se modifica nada de `canal-historias` ni se guarda texto de las conversaciones.

**Tech Stack:** Python 3.13 (solo `json`, `sqlite3`, `argparse`, `datetime`, `pathlib`, `re`), pytest, ruff, mypy. Sin red, sin base de NicheRadar.

**Spec:** `docs/superpowers/specs/2026-11-02-rediseno-movil-corte2-design.md` (sección 5, «Hallazgo del 2026-11-03» y «Decisiones cerradas (2026-11-03)»: método C medido + B supuesto, tope de 15 min por hueco). Contrato: `docs/contracts/channel-report-v3.md`.

## Hechos medidos (2026-11-04, solo lectura sobre `canal-historias`)

- Registros: `~/.claude/projects/-Users-davidrodriguez-Programming-youtube-project-canal-historias/*.jsonl` (6 archivos) y la misma ruta bajo `~/.claude-alt/projects/` (3 archivos). El nombre de carpeta es la ruta absoluta del canal con todo carácter fuera de `[A-Za-z0-9-]` cambiado a `-`.
- Cada línea es un JSON con `type` (`user`, `assistant`, `system`, `attachment`, …), `timestamp` ISO con `Z`, `sessionId`, `isSidechain`, `isMeta` y `message.content` (texto o lista de bloques). Un mensaje `user` es **humano** solo si: `type == "user"`, no `isMeta`, no `isSidechain`, sin `toolUseResult`, y su contenido es una cadena o una lista con algún bloque `text` y ningún bloque `tool_result`.
- Prototipo sobre los datos reales: 568 mensajes humanos y 3 905 minutos de hueco humano (con tope de 15 min) en 45 días, para 36 videos publicados. Solo 15 de 562 mensajes nombran un `video_id`: **la asociación por texto no sirve**, se usa por ventana de tiempo.
- Base del canal: tabla `eventos(id, video_id, de_estado, a_estado, rama, motivo, actor, creado_en)`; `video_id` con forma `v_AAAAMMDD_xxxx`; estados incluyen `IDEA_VALIDADA`, `PROGRAMADO`, `PUBLICADO`. Las ventanas de producción de videos distintos **se solapan** durante días.
- El `outbox` (`.nicheradar/outbox/*.json`) es hoy el que `channel_sync.py report` sube verbatim; `video_id` del reporte es el mismo identificador de `eventos`.

## Global Constraints

- **Solo lectura** sobre `datos/pipeline.db` (`sqlite3.connect("file:…?mode=ro", uri=True)`) y sobre los `.jsonl`; el único archivo que se escribe es el del `outbox` que se convierte (y su copia `*.json.orig`, que `channel_sync.py` no sube porque solo toma `*.json`).
- **Privacidad:** del `.jsonl` se extraen solo marca de tiempo, tipo, `sessionId` y la clasificación humano/no humano; **nunca** se guarda, imprime ni escribe el texto de las conversaciones ni rutas de archivos de tu equipo en el reporte. La salida del script son solo cifras.
- **Honestidad del método:** `human_minutes_method = "claude_sessions_plus_assumed"`. La cifra por video es `ceil(medido_en_minutos) + supuesto`, con el supuesto por defecto de 10 min (tu validación en YouTube Studio, que no deja rastro) configurable con `--assumed-minutes`; el contrato v3 solo lleva una cifra, así que el desglose «medido X · supuesto Y» se imprime en la salida del script y se documenta, no viaja en el reporte.
- **Tope por hueco:** 15 minutos (`--cap-minutes`, por defecto 15), aplicado al hueco entre un mensaje humano y el evento anterior de su misma sesión. El primer mensaje de una sesión no tiene hueco (cuenta 0).
- **Solo videos publicados** reciben minutos: un video del reporte con `published_at` nulo conserva `human_minutes = null`. Un `video_id` ausente de `eventos` también queda en `null` (nunca 0 por defecto).
- Tope del contrato: `0..100000` por video (`channel-report-v3`); el script nunca emite un valor fuera de rango.
- Un archivo del `outbox` que ya es v3, que no es JSON, que no es objeto o cuyo `contract` no es v1/v2 **se deja intacto** y se informa; el script no falla por uno malo y el código de salida es 1 si alguno quedó sin convertir.
- Idempotente: ejecutar dos veces no cambia un archivo ya convertido (queda v3 y se omite).
- Estilo del repositorio: tipado estricto (mypy), `ruff format`, mensajes en español, sin dependencias nuevas.

## Rulings de diseño

1. **Reparto entre videos solapados:** el hueco humano de un mensaje en el instante `t` se reparte **a partes iguales** entre los videos cuya ventana `[primer evento, evento PROGRAMADO o PUBLICADO si existe; si no, último evento]` contiene `t`. Tiempo fuera de toda ventana (construir el pipeline, otras tareas) **no se atribuye a ningún video** y se informa como «sin atribuir». Costo si es incorrecto: cifras por video distintas; el método sigue declarado como estimado.
2. **Redondeo:** minutos medidos por video se redondean hacia arriba al minuto (`math.ceil`), para no declarar 0 donde hubo actividad.
3. **El supuesto se suma solo a videos con `published_at`** (ya validados en Studio), no a los demás.
4. **Un solo script, núcleo puro:** las funciones de cálculo no tocan disco ni reloj (reciben datos), para probarlas sin archivos; solo `main` y los lectores abren archivos.

## Review Focus

1. `.jsonl` corrupto: líneas truncadas, sin `timestamp`, con zona ausente, tipos erróneos, `message.content` nulo o enorme: se ignoran sin excepción y sin imprimir contenido (Task 1).
2. Mensajes de herramienta (`tool_result`), meta, subagentes y comandos locales NO cuentan como humanos; una sesión con 1 solo mensaje cuenta 0 (Task 1).
3. Ventanas solapadas y mensajes fuera de toda ventana: el total atribuido nunca supera el total medido, y lo no atribuido se informa (Task 2).
4. Reportes que no se pueden convertir (v3, JSON roto, `contract` desconocido, `video_id` desconocido, `published_at` nulo): intactos o con `null`, nunca un 0 inventado ni una excepción (Task 3).
5. El archivo convertido valida con `nicheradar.pilots.contracts.validate_report` para largos y shorts, y `channel_sync.py report` lo acepta sin cambios (Task 3).

---

### Task 1: Lector de registros de sesión

**Files:**
- Create: `scripts/channel_human_minutes.py` (solo la parte de sesiones y el núcleo de huecos), `tests/test_channel_human_minutes.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class HumanPrompt: at: datetime; gap_seconds: float` (UTC, con zona; `gap_seconds` ya limitado por el tope).
  - `session_dirs(channel_dir: Path, homes: Sequence[Path]) -> list[Path]`: para cada `home` (por ejemplo `~/.claude`, `~/.claude-alt`) devuelve `home/"projects"/encoded` si existe, con `encoded = re.sub(r"[^A-Za-z0-9-]", "-", str(channel_dir.resolve()))`.
  - `read_human_prompts(files: Iterable[Path], cap_seconds: float) -> list[HumanPrompt]`: ordenados por `at`.
  - `is_human_prompt(record: Mapping[str, object]) -> bool` (reglas de «Hechos medidos»).

- [ ] **Step 1: Pruebas que fallan** (`tests/test_channel_human_minutes.py`, sin DB; `from scripts import channel_human_minutes as hm`). Escribir completas con un ayudante `jsonl(tmp_path, name, records)` que escribe una línea JSON por registro:
  - `is_human_prompt`: verdadero para `{"type":"user","message":{"content":"hola"}}` y para contenido lista con un bloque `text`; falso para `isMeta`, `isSidechain`, `toolUseResult` presente, bloque `tool_result`, `type` `assistant`/`system`, `content` nulo o lista vacía, `content` no cadena ni lista.
  - Huecos: sesión A con eventos a las 10:00:00 (assistant), 10:00:30 (user humano), 10:20:00 (assistant), 10:50:00 (user humano) y tope 900 s → dos `HumanPrompt` con `gap_seconds` 30 y 900 (el tope se aplica al segundo).
  - El primer mensaje de una sesión (sin evento previo) produce `gap_seconds == 0`.
  - Dos sesiones intercaladas no se mezclan (el hueco se mide dentro de su `sessionId`).
  - Líneas corruptas (JSON truncado, objeto sin `timestamp`, `timestamp` basura, `timestamp` sin zona = UTC) no lanzan; las válidas se leen; el resultado queda ordenado por `at`.
  - Un registro con `message.content` de 5 MB no rompe y no aparece en ninguna salida.
  - `session_dirs` con una carpeta que solo existe en uno de los dos `home` devuelve solo esa; el nombre codificado de `/tmp/x/canal-ab.c` es `-tmp-x-canal-ab-c` (con `resolve()` sobre `tmp_path`, compararlo contra la misma expresión).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_channel_human_minutes.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar.** Esqueleto exacto (completar solo con lo indicado por las pruebas):

```python
#!/usr/bin/env python3
"""Calcula los minutos humanos por video y convierte el outbox de un canal a channel-report-v3.

Solo biblioteca estándar. Lee en solo lectura los registros de sesión de Claude Code de la
carpeta del canal y ``datos/pipeline.db``; nunca guarda ni imprime el texto de las conversaciones.
Ver docs/contracts/channel-report-v3.md.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

METHOD = "claude_sessions_plus_assumed"
CAP_SECONDS = 15 * 60
ASSUMED_MINUTES = 10
MAX_MINUTES = 100_000


@dataclass(frozen=True)
class HumanPrompt:
    at: datetime
    gap_seconds: float


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def is_human_prompt(record: Mapping[str, object]) -> bool:
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    if record.get("toolUseResult") is not None:
        return False
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        kinds = [block.get("type") for block in content if isinstance(block, Mapping)]
        return "text" in kinds and "tool_result" not in kinds
    return False


def session_dirs(channel_dir: Path, homes: Sequence[Path]) -> list[Path]:
    encoded = re.sub(r"[^A-Za-z0-9-]", "-", str(channel_dir.resolve()))
    found = [home / "projects" / encoded for home in homes]
    return [path for path in found if path.is_dir()]


def read_human_prompts(files: Iterable[Path], cap_seconds: float) -> list[HumanPrompt]:
    prompts: list[HumanPrompt] = []
    for path in files:
        last: dict[str, datetime] = {}
        try:
            lines = path.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            at = _moment(record.get("timestamp"))
            session = record.get("sessionId")
            if at is None or not isinstance(session, str):
                continue
            if record.get("type") in ("user", "assistant") and is_human_prompt(record):
                previous = last.get(session)
                gap = 0.0 if previous is None else (at - previous).total_seconds()
                prompts.append(HumanPrompt(at, min(max(gap, 0.0), cap_seconds)))
            if record.get("type") in ("user", "assistant", "system"):
                last[session] = at
    return sorted(prompts, key=lambda prompt: prompt.at)
```

  (El `last` es por archivo para acotar memoria; si una misma sesión se reparte en varios archivos, el primer mensaje de cada archivo cuenta 0, aceptado y documentado.)
- [ ] **Step 4:** `uv run pytest tests/test_channel_human_minutes.py -q; uv run ruff format scripts tests -q; uv run ruff check . && uv run mypy` — PASS.
- [ ] **Step 5: Commit** `feat: lector de registros de sesión para minutos humanos`.

---

### Task 2: Ventanas de producción, reparto y minutos por video

**Files:**
- Modify: `scripts/channel_human_minutes.py`, `tests/test_channel_human_minutes.py`

**Interfaces:**
- Consumes: `HumanPrompt`, `METHOD`, `ASSUMED_MINUTES`, `MAX_MINUTES`, `_moment`.
- Produces:
  - `read_windows(db_path: Path) -> dict[str, tuple[datetime, datetime]]`: abre la base **solo lectura**; para cada `video_id`, inicio = primer `creado_en`; fin = el primer evento con `a_estado in ("PROGRAMADO","PUBLICADO")` si existe, si no el último `creado_en`. Fila con fecha ilegible se ignora. Si la tabla o el archivo no existe, lanza `HumanMinutesError` (subclase de `Exception` con mensaje en español).
  - `attribute(prompts: Sequence[HumanPrompt], windows: Mapping[str, tuple[datetime, datetime]]) -> Attribution` con `@dataclass(frozen=True) class Attribution: by_video: dict[str, float]` (segundos) y `unattributed: float` (segundos) y `total: float`; invariante `sum(by_video.values()) + unattributed == total` (tolerancia 1e-6). Un mensaje en `t` se reparte a partes iguales entre los videos con `start <= t <= end`; sin ninguno, va a `unattributed`.
  - `video_minutes(attribution: Attribution, video_id: str, published: bool, assumed: int) -> tuple[int, int] | None`: `None` si `video_id not in attribution.known`; si no, `(measured, assumed_applied)` con `measured = math.ceil(seconds / 60)` y `assumed_applied = assumed if published else 0`; el total `measured + assumed_applied` se limita a `MAX_MINUTES`. Para distinguir «video conocido sin actividad» (medido 0) de «desconocido» (None), `Attribution` lleva también `known: frozenset[str]` (todos los ids de `windows`).

- [ ] **Step 1: Pruebas que fallan:**
  - `read_windows` con una base SQLite temporal (crear la tabla `eventos` con las columnas reales): ventana de `v_a` = primer evento → primer `PROGRAMADO`; video sin `PROGRAMADO`/`PUBLICADO` usa el último evento; fila con `creado_en` basura ignorada; archivo inexistente y base sin tabla → `HumanMinutesError`; **la base no cambia** (comparar `PRAGMA data_version` o el hash del archivo antes y después) y abrir en solo lectura impide escribir (un intento de `INSERT` por la misma ruta con `mode=ro` falla).
  - `attribute`: un mensaje dentro de una sola ventana va entero a ese video; dentro de dos solapadas se reparte mitad y mitad; fuera de toda ventana va a `unattributed`; borde exacto (`t == start`, `t == end`) cuenta dentro; invariante de suma con 50 mensajes aleatorios (semilla fija).
  - `video_minutes`: 90 s → `measured=2` (ceil); `published=False` → `assumed_applied=0`; video conocido sin actividad y publicado → `(0, 10)`; video desconocido → `None`; resultado limitado a 100 000; `assumed` negativo se rechaza con `ValueError`.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_channel_human_minutes.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** con `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` (escapar con `urllib.parse.quote` la ruta), `try/finally` para cerrar, y el reparto por una pasada ordenada (mensajes y ventanas son pocos: bucle simple `O(prompts × videos)` es suficiente; no optimizar).
- [ ] **Step 4:** pruebas del archivo, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: ventanas de producción y reparto del tiempo humano por video`.

---

### Task 3: Conversión del outbox, CLI y comprobación con datos reales

**Files:**
- Modify: `scripts/channel_human_minutes.py`, `tests/test_channel_human_minutes.py`
- Create: `tests/test_channel_human_minutes_cli.py` (usa `validate_report` de `nicheradar.pilots.contracts` y `tests.pilot_samples`/`tests.shorts_report_samples`; sin Postgres)

**Interfaces:**
- Consumes: `read_human_prompts`, `session_dirs`, `read_windows`, `attribute`, `video_minutes`, `METHOD`, `CAP_SECONDS`, `ASSUMED_MINUTES`.
- Produces:
  - `convert_report(payload: Mapping[str, object], attribution: Attribution, assumed: int) -> tuple[dict[str, object], Summary] | None`: `None` si no se puede convertir (no es v1/v2); si no, el payload v3: `contract="channel-report-v3"`, `format="long"` para v1 y `"shorts"` para v2, `human_minutes_method=METHOD`, y a cada video `human_minutes` (`int` de `video_minutes`, o `None`); el resto del reporte **idéntico** (incluidos `reported_at` y el orden de claves). Un video con `published_at` nulo → `human_minutes: None`.
  - `@dataclass(frozen=True) class Summary: lines: tuple[tuple[str, int | None, int, int], ...]` = (`video_id`, `human_minutes`, `measured`, `assumed`).
  - `convert_outbox(channel_dir: Path, attribution: Attribution, assumed: int, out: Callable[[str], None]) -> int`: recorre `.nicheradar/outbox/*.json` (no `sent/`), convierte, guarda el original como `<nombre>.json.orig` **solo si no existe** y reescribe el archivo de forma atómica (`tmp` + `os.replace`); informa por archivo; devuelve 0 o 1.
  - `main(argv=None, homes=None) -> int` con `--channel-dir` (obligatorio), `--assumed-minutes` (por defecto 10, entero ≥ 0), `--cap-minutes` (por defecto 15, entero ≥ 1), `--sessions-home` (repetible; por defecto `~/.claude` y `~/.claude-alt`), `--sessions-dir` (repetible; si se da, se usa tal cual en lugar de deducir la carpeta desde `--sessions-home`), `--db` (ruta de `pipeline.db`; por defecto `<channel-dir>/datos/pipeline.db`), `--dry-run` (calcula e imprime, no escribe). La salida incluye: archivos convertidos/omitidos, minutos humanos medidos totales, **minutos sin atribuir**, y por video «`video_id`: medido X · supuesto Y = Z min». Nunca imprime texto de conversaciones.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_channel_human_minutes_cli.py`, completas):
  - largo: un reporte v1 de `tests.pilot_samples.report(...)` con dos videos (uno publicado y conocido, otro con `published_at` nulo) se convierte; `validate_report(convertido, ahora)` devuelve un `ReportV3` sin problemas; el publicado trae `human_minutes == ceil(medido/60) + 10`, el no publicado `None`; `format == "long"` y `human_minutes_method == "claude_sessions_plus_assumed"`; todo lo demás es igual al original (comparar sin las claves nuevas);
  - shorts: un v2 de `tests.shorts_report_samples.shorts_report(...)` → `format == "shorts"` y valida;
  - un `video_id` ausente de `eventos` → `human_minutes: None` (nunca 0);
  - archivos que se dejan intactos y cuentan como fallo (código 1): JSON roto, un arreglo en vez de objeto, `contract` desconocido; un archivo ya v3 se omite sin fallo y queda byte a byte igual;
  - idempotencia: correr `main` dos veces deja el mismo resultado y no sobrescribe `*.json.orig`;
  - `--dry-run` no cambia ningún archivo ni crea `.orig`;
  - el valor se limita a 100 000 aunque el medido sea gigantesco (un `HumanPrompt` sintético con cap enorme desde `--cap-minutes 999999999` y `--assumed-minutes 0`);
  - la salida de `main` (capturada) no contiene el texto de un mensaje de prueba con una cadena marcador (`"SECRETO-DE-PRUEBA"` dentro de `message.content`);
  - `channel_sync.report` (con el `adapter` de `tests/test_channel_sync.py` o un `Http` falso) acepta el archivo convertido sin cambios: el cuerpo enviado es el v3 y no hay errores de forma.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_channel_human_minutes_cli.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** `convert_report`, `convert_outbox`, `main` (`argparse`, `if __name__ == "__main__": raise SystemExit(main())`).
- [ ] **Step 4:** `uv run pytest tests/test_channel_human_minutes.py tests/test_channel_human_minutes_cli.py tests/test_channel_sync.py -q` (la última necesita `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin`, en primer plano); ruff; mypy — PASS.
- [ ] **Step 5: Comprobación con datos reales (solo lectura, `--dry-run`):** `uv run python scripts/channel_human_minutes.py --channel-dir ~/Programming/youtube-project/canal-historias --dry-run` (no hay reportes en el `outbox` hoy: para tener qué convertir, crear en un directorio temporal `tmp/canal-historias-fake/.nicheradar/outbox/` un reporte v1 mínimo con los `video_id` reales publicados de la base, y apuntar `--channel-dir` a la carpeta real solo para sesiones y base mediante `--db` y `--sessions-dir`; **no** escribir nada en `canal-historias`). Registrar en el informe de la tarea **solo cifras agregadas**: total medido, sin atribuir, mediana y rango de minutos por video, y cuántos videos quedaron en `null`. Si la mediana por video supera 120 min o la fracción sin atribuir supera el 60 %, anotarlo como hallazgo (el método sobreestima o subatribuye) sin cambiar el método.
- [ ] **Step 6: Commit** `feat: conversión del outbox a channel-report-v3 con minutos humanos`.

---

### Task 4: Documentación y uso

**Files:**
- Modify: `docs/contracts/channel-report-v3.md` («Quién lo genera»: el productor existe y cómo se usa), `docs/pilots.md`, `docs/comandos.md` (si existe la sección de scripts del canal; si no, `docs/pilots.md`), `docs/web-movil.md` (qué significa «estimado (método claude_sessions_plus_assumed)»)

- [ ] **Step 1:** Documentar: el flujo completo `fetch` → trabajo del canal → `uv run python scripts/channel_human_minutes.py --channel-dir …` → `channel_sync.py report`; qué mide (tiempo activo humano en Claude Code con tope de 15 min por hueco, repartido entre videos en producción), qué **no** mide (validación en YouTube Studio: se suma el supuesto de 10 min; trabajo fuera de Claude Code; tiempo fuera de toda ventana, que se informa como «sin atribuir»), por qué es una **estimación** (solapes entre videos, primer mensaje de cada archivo cuenta 0), el significado del método en la web, y la privacidad (no se guarda texto de conversaciones). Añadir los parámetros (`--assumed-minutes`, `--cap-minutes`, `--sessions-home`, `--dry-run`) y el rollback (`*.json.orig`).
- [ ] **Step 2:** `uv run ruff check . && uv run mypy`; `grep -rn "channel_human_minutes" docs scripts` sin referencias rotas; los ejemplos de comandos se ejecutan con `--help` sin error.
- [ ] **Step 3: Commit** `docs: uso del productor de minutos humanos`.

---

## Fuera de este plan

Hooks de Claude Code o cualquier cambio en `canal-historias`; asociar mensajes a videos por texto; llevar el desglose «medido X · supuesto Y» dentro del contrato (requiere `channel-report-v4` o un campo opcional aditivo, decisión posterior); automatizar la ejecución con `launchd`; desplegar nada (el script corre en el Mac del propietario, y la API ya acepta v3 tras la release de la migración `0021`, que necesita aprobación).

## Self-Review

- **Cobertura del spec (sección 5 y decisiones cerradas):** método C (Task 1-2) + B como suelo (supuesto en Task 2-3, `--assumed-minutes`), tope de 15 min por hueco (Task 1), en este repositorio y solo lectura (Global Constraints y Task 2), `human_minutes_method` siempre declarado (Task 3), ambos números visibles (salida de Task 3 y documentación de Task 4; no viajan en el reporte, declarado como límite).
- **Marcadores de relleno:** ninguno; el código del núcleo de sesiones está completo y las tareas 2-3 definen firmas, reglas exactas y pruebas con aserciones concretas.
- **Consistencia de tipos:** `HumanPrompt`, `Attribution(by_video, unattributed, total, known)`, `video_minutes(...) -> tuple[int, int] | None`, `Summary` y `convert_report`/`convert_outbox`/`main` se nombran igual en todas las tareas.
- **Review Focus:** 1-2 en Task 1, 3 en Task 2, 4-5 en Task 3.
