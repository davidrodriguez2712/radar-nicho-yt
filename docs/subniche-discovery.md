# Descubrimiento de subnichos en YouTube (subproyecto B)

Estado: **implementado, sin desplegar**. Diseño: `docs/superpowers/specs/2026-10-31-subniche-discovery-youtube-design.md`;
plan: `docs/superpowers/plans/2026-10-31-subniche-discovery-youtube.md`.

El propietario da hipótesis de subnicho (una consulta, un video o un canal). Un LLM (Anthropic) solo
**propone** etiqueta, familia, nicho padre y 2 o 3 consultas; el propietario las aprueba y un proceso
del worker mide cada hipótesis contra la API de YouTube: busca videos recientes, lee los canales,
estima visitas e ingreso y guarda un perfil agregado. No crea canales ni elige oportunidades.

## Qué es y qué no es

- Todo ingreso es una **estimación en rango** [bajo, alto], con un error típico de factor 2 a 10.
  Nunca es un ingreso verificado.
- El RPM se hereda del nicho padre (`advertising_benchmarks`, formato `long`) y se marca
  `inherited:<nicho>`. **Sin nicho padre no hay ingreso.**
- Solo se mide formato largo en inglés. Un Short (≤ 180 s) no cuenta para el ingreso.
- El texto de YouTube es dato no confiable: el LLM solo puede devolver una propuesta que valide
  contra listas cerradas (nichos del catálogo, consultas limpias); nada de lo que dice se ejecuta.

## Cómo se usa

Todos los comandos corren donde la base de producción es alcanzable y con las variables del worker
(`NR_DATABASE_URL`, etc.). Cada uno imprime una línea JSON y sale con código 1 si hay un error declarado,
salvo `export` sin `--out`, que imprime el YAML en crudo (con `--out` escribe el archivo y sí imprime una línea JSON).

```sh
# Alta: consulta, video o canal (el LLM propone; la hipótesis queda `proposed`).
# Con un video o un canal como entrada `add` construye el lector de YouTube: exige
# NR_YOUTUBE_API_KEY y NR_YOUTUBE_AUTH_SCOPE (no comprueba NR_YOUTUBE_LIVE_ENABLED).
uv run python scripts/subniche.py add "faceless history documentary"
uv run python scripts/subniche.py add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
uv run python scripts/subniche.py add "@nombredelcanal"          # o la URL / el id UC… del canal
# Alta sin LLM (exige --label y --family, y una consulta como entrada; --parent es opcional)
uv run python scripts/subniche.py add "ancient rome facts" --manual --label "Ancient Rome" --family history --parent <etiqueta-de-nicho>
# Opciones de origen: --origin manual|catalog|marketplace|lead

uv run python scripts/subniche.py list [--status proposed|active|paused|archived]
uv run python scripts/subniche.py approve <slug>     # proposed -> active (solo `active` gasta cuota)
uv run python scripts/subniche.py pause <slug>
uv run python scripts/subniche.py resume <slug>
uv run python scripts/subniche.py archive <slug>
uv run python scripts/subniche.py finalist <slug> [--off]   # finalista: se refresca a los 7 días
uv run python scripts/subniche.py measure <slug>     # exige `active` (si no: invalid_transition); agenda re-medir en la próxima corrida (no mide al instante)
uv run python scripts/subniche.py export [--out hipotesis.yaml]
uv run python scripts/subniche.py import <ruta.yaml> [--dry-run]     # carga masiva desde el formato de `export`
uv run python scripts/subniche.py import --b64 <texto-en-base64> [--dry-run]
```

### Carga masiva (`import`)

Carga hipótesis desde un archivo con el formato exacto de `export` (el repo trae `config/subniche_hypotheses.yaml`,
60 hipótesis con 2 consultas cada una). Acepta una ruta o el contenido en base64 (`--b64`); exactamente una de las dos.
En producción el script entra por stdin al contenedor del worker, así que el archivo no es alcanzable por ruta: se usa `--b64`.
Pruebe primero con `--dry-run` (valida todo y reporta lo mismo que la corrida real, sin escribir nada):

```sh
/tmp/nr/on_server.sh worker scripts/subniche.py import --b64 "$(base64 < config/subniche_hypotheses.yaml | tr -d '\n')" --dry-run
/tmp/nr/on_server.sh worker scripts/subniche.py import --b64 "$(base64 < config/subniche_hypotheses.yaml | tr -d '\n')"
```

- Todo o nada: si algún elemento es inválido (campo mal formado, nicho padre que no está en el catálogo, slug o consulta
  repetidos dentro del archivo) no se escribe nada y sale con código 1: `{"error": "invalid_import", "invalid": [{"slug", "error"}]}`.
  Un formato ilegible o un base64 inválido da `{"error": "invalid_format", "detail": ...}`; una ruta ilegible, `{"error": "file_not_found"}`.
- Es idempotente: lo que ya existe (mismo slug, consulta o canal semilla en una hipótesis viva) se salta y se reporta en
  `skipped` con su razón; no es un error. Resultado: `{"ok": true, "dry_run", "imported": [slugs], "skipped": [{"slug","reason"}], "total"}`.
- Los campos `status` y `finalist` del archivo se IGNORAN: todo lo importado queda `proposed` y no finalista.
  Cada hipótesis importada debe aprobarse una por una con `subniche approve <slug>` antes de que gaste cuota.
- Toda la importación es una sola transacción. Nunca imprime el contenido del archivo.

Flujo: `add` → `proposed` → `approve` → `active` → la próxima corrida del worker la mide (en 3 días como
máximo; las nuevas se miden primero, ordenadas por fecha de aprobación) → `scripts/subniche_report.py`.

- Un canal o video dados como entrada se guardan además como **canal semilla** de la hipótesis.
- Una consulta o un canal semilla ya presentes en una hipótesis no archivada se rechazan como duplicado.
- Un tweet (`x.com/.../status/N`) se reconoce pero **aún no se soporta** (`tweet_not_supported_yet`;
  subproyecto C).
- Si el LLM no está disponible o no valida, `add` falla con una razón estable (`llm_disabled`,
  `configuration_missing`, `llm_tariff_not_current`, `policy_not_enabled`, …) y sugiere `--manual`.

## Cadencia del worker

- Un tick cada **3 días** (`CADENCE`), con un cerrojo asesor de Postgres. Mide primero las hipótesis
  `active` sin medir (por `approved_at`) y luego las **finalistas con más de 7 días** desde la última medición.
- Una corrida `partial` (cuota agotada) o `failed` **continúa el día de cuota siguiente**. El día de
  cuota es el día del **Pacífico** (`NR_SUBNICHE_QUOTA_TIMEZONE`, defecto `America/Los_Angeles`)
  porque Google reinicia la cuota de la YouTube Data API a medianoche del Pacífico (07:00 UTC en
  horario de verano, 08:00 UTC en invierno), no a medianoche de Lima. El mismo día de cuota rige el
  tope diario de búsquedas. Una hipótesis se guarda completa o no se guarda; la siguiente corrida no
  repite las ya medidas.
- Incidente del 2026-11-01: con el día de Lima, el reintento de una corrida `partial` se abrió a la
  medianoche de Lima (05:00 UTC), antes del reinicio real de Google; respondió `quotaExceeded`, la
  corrida volvió a `partial` y quedó bloqueada hasta el siguiente día de Lima, perdiendo un día de cuota.
- Una corrida `running` con más de 6 h se considera muerta y se reanuda al día de cuota siguiente.
- Límites conocidos:
  - Las ventanas **semanal y mensual** del ledger (`_PER_WEEK`, `_PER_MONTH`) siguen calculándose con la zona
    horaria general (`NR_TIMEZONE`, Lima); solo el tope diario y el reintento usan el día del Pacífico.
  - La comprobación previa (`insufficient_search_cap`) valida solo el tope de **búsqueda**. Si el tope de
    **detalle** (`NR_SUBNICHE_DETAIL_QUOTA_*`) se agota, la corrida queda `partial` con `period_budget_exhausted`
    (como en la primera corrida); se sube el tope y la corrida continúa el siguiente día de cuota.
- Puertas: `NR_SUBNICHE_ENABLED=true` (defecto `false`), `NR_MODE=live` y `NR_YOUTUBE_LIVE_ENABLED=true`.
  Si falta cualquiera, el tick informa `disabled`, `synthetic_mode` o `youtube_not_enabled` y no hace nada.
  Sin `NR_YOUTUBE_API_KEY` o `NR_YOUTUBE_AUTH_SCOPE` informa `youtube_not_configured`, también sin crear corrida.

### Regla de cuota de búsqueda

Una hipótesis cuesta `consultas × páginas × 100` unidades de búsqueda (una consulta × una página = 100).
Debe cumplirse `NR_SUBNICHE_SEARCH_UNITS_PER_DAY >= consultas × páginas × 100` y lo mismo con
`NR_SUBNICHE_SEARCH_QUOTA_PER_RUN`. **Con los defectos (100 / 100) solo completan hipótesis de 1 consulta × 1 página**
(con `NR_SUBNICHE_SEARCH_PAGES=2` ya son 200); las propuestas por el LLM llevan 2 o 3 consultas (hasta 600 con 2 páginas).

- Si ninguna hipótesis pendiente cabe nunca en el tope, el tick responde `insufficient_search_cap` (con `needed` y `cap`)
  **sin crear corrida ni reservar nada**; las que no caben se omiten con la razón en `stats.skipped` y se miden las demás.
- Si cabe en el tope pero hoy ya se gastó parte del cupo diario, la corrida queda `partial` **antes** de la primera
  búsqueda de esa hipótesis (no se gasta nada) y continúa al día de cuota siguiente. `stats.stopped_slug` dice dónde paró.

## Variables de entorno del worker

Leídas de `src/nicheradar/config.py` (prefijo `NR_`).

| Variable | Defecto / rango | Para qué |
|---|---|---|
| `NR_ANTHROPIC_ENABLED` | `false` | Activa la propuesta con LLM (`add` sin `--manual`) |
| `NR_ANTHROPIC_API_KEY` | sin valor | Credencial; el propietario ya la cargó en el worker. **Nunca va en el repo ni en este documento** |
| `NR_ANTHROPIC_CONFIGURATION` | sin valor | JSON `LLMConfiguration`: tarifa, límites y timeout (ver abajo) |
| `NR_SUBNICHE_ENABLED` | `false` | Interruptor del tick de descubrimiento |
| `NR_SUBNICHE_QUOTA_TIMEZONE` | `America/Los_Angeles` | Zona IANA que define el día de cuota de YouTube (tope diario y reintento tras `partial`); Google reinicia a medianoche del Pacífico |
| `NR_SUBNICHE_SEARCH_UNITS_PER_DAY` | 100 (0–100.000) | Tope diario de unidades de `search.list` (100 por búsqueda), por día de cuota del Pacífico |
| `NR_SUBNICHE_SEARCH_PAGES` | 2 (1–3) | Páginas de resultados por consulta |
| `NR_SUBNICHE_CHANNELS_PER_HYPOTHESIS` | 30 (1–100) | Canales distintos que se leen por hipótesis |
| `NR_SUBNICHE_SEARCH_QUOTA_PER_RUN` / `_PER_WEEK` / `_PER_MONTH` | 100 / 700 / 3000 | Topes del ledger de búsqueda (unidades) |
| `NR_SUBNICHE_DETAIL_QUOTA_PER_RUN` / `_PER_WEEK` / `_PER_MONTH` | 5000 / 10.000 / 30.000 | Topes del ledger de detalle: canales y videos (unidades) |

### `NR_ANTHROPIC_CONFIGURATION`

Ejemplo **validado** con `LLMConfiguration.model_validate_json` (reserva por propuesta
`maximum_usd()` = US$0,04):

```json
{
  "auth_scope": "anthropic-owner",
  "tariff": {
    "version": "anthropic-sonnet-5-5-2026-10-31",
    "model": "claude-sonnet-5-5",
    "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    "verified_at": "2026-10-31T00:00:00Z",
    "valid_until": "2027-01-29T00:00:00Z",
    "context_window_tokens": 16000,
    "output_tokens": 800,
    "input_usd_per_million": "2",
    "cached_input_usd_per_million": "0.10",
    "output_usd_per_million": "10"
  },
  "limits": {"operation": "100", "run": "1000", "week": "10000", "period": "100000"},
  "timeout_seconds": 20
}
```

- **Tarifa verificada** para `claude-sonnet-5-5` en https://platform.claude.com/docs/en/about-claude/pricing,
  consultada el **2026-10-31** (la página no tiene fecha): entrada US$2, lectura de caché US$0,10 y
  salida US$10 por millón de tokens (escritura de caché 5 min US$2,50 y 1 h US$4: no se usan).
  `valid_until` es 90 días después; con una tarifa vencida la propuesta se rechaza con
  `llm_tariff_not_current`. Hay que volver a verificar la página y renovar `verified_at`/`valid_until`.
- `context_window_tokens: 16000` es el **tope operativo de entrada**, no la ventana real del modelo:
  `maximum_usd()` reserva toda esa capacidad más `output_tokens`, y con la ventana real la reserva sería de dólares.
  Las propuestas usan entradas de unos pocos cientos de tokens.
- `output_tokens: 800` va como `max_tokens`; la herramienta de propuesta devuelve un objeto pequeño
  (etiqueta, familia, nicho padre, 2 o 3 consultas). El contrato admite 128 a 2048.
- `limits` son holgados porque el propietario decidió **no poner topes en dólares por ahora**. Pero el tope
  efectivo es `min(limits, radar_usd_per_*)` del perfil (`services/budget.py::reserve`): las propuestas
  comparten el tope del perfil (US$5/semana hoy) con el resto del gasto en dólares. Con decenas de
  propuestas por semana (≈ centavos cada una) no estorba. Si se agota, `add` falla con el código del presupuesto.
- Cabecera `anthropic-version: 2023-06-01` (versión estable documentada; el SDK más nuevo envía
  2026-10-21). **Si la primera llamada real devuelve un error HTTP, revisar primero la constante
  `ANTHROPIC_VERSION` en `src/nicheradar/integrations/anthropic.py`.**
- **Cada `llm_http_error` / `llm_invalid_response` deja una reserva `unknown_charge` por el máximo de la propuesta**
  (US$0,04 con la tarifa documentada), que cuenta como pasivo sin límite de período hasta conciliarse. Por eso
  intentos repetidos de `add` que fallan (p. ej. depurando la cabecera de versión) consumen el tope semanal en
  dólares del perfil (US$5/semana) hasta que alguien concilie. Es el mismo comportamiento que el adaptador de OpenAI.

## Cupo de búsqueda de YouTube (verificado el 2026-10-31)

**Verificado por el propietario en Google Cloud Console → YouTube Data API v3 → Cuotas:**
"Search Queries per day" = **100** y "Search Queries per minute" = 100 (ajustables), con uso actual 0;
"Queries per day" (pool general) = 10.000. Es decir, **100 búsquedas por día**, no una. El ledger modela cada
búsqueda como 100 unidades, así que el tope diario equivale a `NR_SUBNICHE_SEARCH_UNITS_PER_DAY=10000`.
Los topes de 1 búsqueda por día del análisis de canales (`youtube_search_quota_*`, 100/700/3000) son solo conservadores.

**Recomendación para el primer día:** empezar con `NR_SUBNICHE_SEARCH_UNITS_PER_DAY=5000` (50 búsquedas) y mirar
en la consola el "Uso actual" de las dos filas ("Search Queries per day" y "Queries per day"). La consola no
aclara si cada búsqueda también descuenta unidades del pool general de 10.000; si lo hace, 100 búsquedas lo agotarían
por completo y dejarían sin cupo a las lecturas de detalle (1 unidad cada una). Si tras el primer día solo sube
"Search Queries per day", se puede subir a 10000. Con 50 búsquedas por día, la corrida inicial (≈ 240 búsquedas)
tarda unos 5 días.

**Topes de detalle (lectura de canales y videos, 1 unidad cada una).** El ledger suma todo el uso del perfil de
la unidad `youtube_quota` en la semana y el mes, incluido el enriquecimiento del mercado, que ya ronda las 10.000
unidades por semana. Con los defectos (`NR_SUBNICHE_DETAIL_QUOTA_PER_WEEK=10000`) el tope estaba lleno antes de empezar y
la primera corrida terminó `partial` con `period_budget_exhausted` **después de gastar 4 búsquedas** (400 unidades) sin
guardar nada. En producción se subieron a `_PER_WEEK=50000` y `_PER_MONTH=150000` (`set-subniche-env`); el límite real
de Google es 10.000 por día. Conviene que la comprobación previa también mire estos topes (pendiente).

### Historial: la verificación que estaba pendiente

`docs/channel-analysis.md` y el plan del 2026-10-01 dicen que `search.list` tiene un cupo propio
("Search queries per day = 100" en Google Cloud Console), distinto del pool de 10.000/día. El ledger
modela cada búsqueda como 100 unidades y los topes semanal/mensual actuales (700/3000) equivalen a 7 y
30 búsquedas. El spec asumió 100 unidades por búsqueda contra un pool diario de 10.000 (≈100 búsquedas/día).

El propietario debe leer el límite y el uso actuales en **Google Cloud Console → YouTube Data API v3 →
Cuotas ("Search queries per day")** antes de subir `NR_SUBNICHE_SEARCH_UNITS_PER_DAY`. Hasta entonces el
defecto es 100 (1 búsqueda por día: ver la regla de cuota de búsqueda, solo caben hipótesis de 1 consulta × 1 página).

| Resultado de la verificación | Valores recomendados |
|---|---|
| **100 búsquedas por día** (o el pool general de 10.000 unidades) | `NR_SUBNICHE_SEARCH_UNITS_PER_DAY=10000`; `NR_SUBNICHE_SEARCH_QUOTA_PER_RUN=10000`; `_PER_WEEK=70000`; `_PER_MONTH=300000` (los topes del ledger deben acompañar o seguirán frenando antes). Una hipótesis cuesta `consultas × páginas` búsquedas (hasta 3 × 2 = 6 con los defectos), es decir hasta 600 unidades: el tope diario y el de `_PER_RUN` deben ser al menos `consultas × páginas × 100` |
| **Otro valor N de búsquedas por día** | `NR_SUBNICHE_SEARCH_UNITS_PER_DAY = N × 100`, con `_PER_RUN` igual y `_PER_WEEK`/`_PER_MONTH` = 7× y 30× ese valor. Bajar `NR_SUBNICHE_SEARCH_PAGES` a 1 para medir el doble de hipótesis por día |
| **1 búsqueda por día** (se queda en 100 unidades) | Solo caben hipótesis de 1 consulta × 1 página (`NR_SUBNICHE_SEARCH_PAGES=1`); las del LLM (2 o 3 consultas) se omiten con `insufficient_search_cap`. La corrida inicial (≈ 240 búsquedas, unas 40 hipótesis) es **inviable** en plazos razonables y hay que rediseñarla (menos consultas por hipótesis, 1 página, lista inicial más corta o pedir ampliación de cuota a Google). No subir el tope |

No subir los topes antes de leer el valor real: un tope por encima del cupo de Google solo produce
errores `quotaExceeded` a mitad de corrida (la corrida queda `partial` y no pierde datos, pero gasta el día).

## Retención y respaldo

- Los datos de la API de YouTube (`discovery_channel_snapshots`, `hypothesis_channel_hits`) se conservan
  **30 días** (`retain_until`; la política de la API no permite más) y **no se respaldan** (esquema sí, filas no).
- Los agregados `hypothesis_snapshots` son permanentes, y el grupo revisado `DISCOVERY_TABLES`
  (`niche_hypotheses`, `hypothesis_seed_channels`, `discovery_runs`, `hypothesis_snapshots`) **sí se respalda**.
  Ver `docs/backup-restore.md`. La guarda del respaldo exige la revisión `0020`.

## Informes (solo lectura)

```sh
uv run python scripts/subniche_report.py                 # ranking de hipótesis medidas (JSON)
uv run python scripts/subniche_spend_report.py [--days 30]   # gasto por proveedor y operación (defecto 30 días)
```

El informe de gasto **subestima** las solicitudes con cargo desconocido (`unknown_charge`): cuentan como
solicitudes, no como dólares.

## Limitaciones conocidas

- El ingreso es un rango con error de factor 2 a 10; la clasificación entre hipótesis es más fiable que el nivel absoluto.
- RPM heredado del nicho padre; sin padre, sin ingreso.
- Tweets reconocidos pero no soportados (subproyecto C).
- Un canal sin videos recientes o cuya lectura de videos falló se guarda con `excluded_reason`
  `no_recent_videos` / `harvest_failed`: cuenta en `profile.excluded` y no entra en las medianas ni en los estables.
- La regla de subcadenas `www`/`http` en consultas rechaza algunas consultas legítimas (p. ej. una que contenga "www" dentro de otra palabra).

## Dashboard e investigación de flujo

- La página **Subnichos** del dashboard lista las hipótesis (casilla para mostrar pausadas y archivadas) y su ficha
  muestra la medición y los canales relevantes, con el botón «Iniciar investigación de flujo».
- El ingreso que muestra es la **mediana mensual estimada por canal estable**, con el RPM heredado del nicho padre:
  una estimación, no un agregado del subnicho ni ingresos verificados. No hay score de automatización de subnichos.
- El encargo usa `niche_label = subniche:<slug>` con el formato y el idioma de la hipótesis. Es elegible solo si la
  hipótesis está `active` y tiene al menos una medición (`subniche_not_ready` en otro caso).
- Los canales de la ficha salen de datos con retención de 30 días: vencidos, `evidence.channels` queda vacío
  (`channels_available` falso). Las compuertas de minutos de régimen, horas de calibración y derechos siguen aplicando.
- En un encargo de subnicho, el `gate_override` indicado al crearlo se congela siempre (el backlog solo lo congela si
  una compuerta falla) y, si existe, el dossier omite las compuertas de minutos de régimen y horas de calibración al
  entregarse; la autorización del piloto vuelve a comprobar todo y exige `accept_gate_failure`.
- Autorizar el piloto: `scripts/pilots.py authorize --niche-label subniche:<slug> --dossier-id ...` (resto de opciones
  como en cualquier piloto).
- En el paquete del piloto, la evidencia trae `scores` nulos, cifras con origen `estimate` y `confidence` `low` con
  menos de 10 canales incluidos (`medium` desde 10). `captured_at` es la fecha de la medición, no la de la autorización.

## Puesta en producción (no ejecutada aquí)

Sigue el flujo de releases existente (formato en `docs/release-20261030-030.md`):

1. Exportación limpia con `git archive`, imágenes `v1-candidate-YYYYMMDD-NNN` (API, worker, dashboard) y
   `scripts/smoke_compose.py`.
2. Publicar las imágenes **con aprobación del propietario** y registrar `docs/release-YYYYMMDD-NNN.md`
   (digests, suite, rollback sin `alembic downgrade`).
3. **Pendiente al hacer la release:** añadir una acción `migrate-live-0020` en `scripts/easypanel_stage.mjs`,
   siguiendo el patrón de `migrate-live-0019`, más una acción de despliegue. Hoy no existe.

Pasos del propietario tras el despliegue:

1. `migrate-live` de la 0020 (producción hoy está en una revisión anterior: aplicar también las intermedias
   que falten). Confirmar `alembic heads` = `0020`.
2. Variables del worker de la sección anterior (la clave ya está cargada). `NR_SUBNICHE_ENABLED` se queda en `false`
   hasta tener las variables de cuota (ver "Cupo de búsqueda de YouTube": empezar con 5000 unidades por día).
3. `uv run python scripts/seed_subniche_policy.py` (una vez, idempotente): habilita las políticas de Anthropic
   `hypothesis_proposal`. Exige `NR_ANTHROPIC_ENABLED=true`, `NR_MODE=live` y `NR_RADAR_PAUSED=true`; no toca presupuestos ni programaciones.
4. Revisar con el propietario la lista inicial de hipótesis **antes de gastar cuota**, aprobar y, solo entonces, activar
   `NR_SUBNICHE_ENABLED=true`.
5. Si la primera llamada al LLM devuelve un error HTTP, revisar `ANTHROPIC_VERSION` (ver arriba).
