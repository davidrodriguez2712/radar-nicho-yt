# Comandos de NicheRadar

Referencia operativa. Todo se ejecuta desde la raíz del repo. Las acciones de producción exigen aprobación del
propietario; el detalle de cada release está en `docs/release-*.md`.

## Desarrollo y validación local

| Comando | Qué hace |
|---|---|
| `uv run pytest` | Suite completa (necesita Postgres local para los tests de base de datos) |
| `uv run ruff check . && uv run mypy` | Lint y tipos (los mismos que corre CI) |
| `uv run python scripts/smoke_compose.py` | Prueba de humo aislada: construye imágenes y levanta compose |

## Release (imágenes)

```
git archive HEAD | docker buildx build --platform linux/amd64 --target backend|worker|dashboard --load -t davidrodriguez2712/nicheradar-<destino>:v1-candidate-AAAAMMDD-NNN -
for t in backend worker dashboard; do docker push davidrodriguez2712/nicheradar-$t:v1-candidate-AAAAMMDD-NNN; done   # lo corre el propietario
```

Luego: digests como constantes y acción de despliegue en `scripts/easypanel_stage.mjs`, nota en `docs/release-*.md`,
PR, CI y fusión.

## Producción: `node scripts/easypanel_stage.mjs <acción> [app]`

Apps válidas: `nicheradar-api`, `nicheradar-worker`, `nicheradar-dashboard`.

| Acción | Uso |
|---|---|
| `probe` | Estado de salud (API, base, modo, claves configuradas) |
| `inspect`, `rollouts` | Configuración y despliegues de las apps |
| `migrate-live-00NN` | Migración de esquema en vivo (la última: `migrate-live-0020`) |
| `deploy-subniche-code <app>` | Release 031 (subnichos) |
| `deploy-subniche-import-code <app>` | Release 032 (`subniche import`) |
| `deploy-subniche-quota-day-code <app>` | Release 033 (día de cuota en hora del Pacífico) |
| `set-subniche-env` | Variables `NR_ANTHROPIC_*` y topes `NR_SUBNICHE_*` del worker (lee la clave del worker o de `.env`) |
| `set-subniche-enabled <true\|false> [dry]` | Enciende o apaga el descubrimiento de subnichos |
| `set-radar-paused`, `restart-apps`, `start-apps` | Pausa del radar y reinicio de apps |
| `set-llm-limits`, `set-market-caps`, `set-youtube-enrich-caps`, `set-evidence-cap`, `set-batch-size` | Topes de gasto y tamaño de lote |

(La lista completa de acciones está en `scripts/easypanel_stage.mjs`; las `deploy-*-code` antiguas quedan como historial.)

## Producción: scripts dentro del contenedor

`/tmp/nr/on_server.sh <servicio> <archivo.py> [args...]` ejecuta un `.py` local por `docker exec` en el contenedor del
servicio (`worker` o `api`). Es un script local del propietario (no está en el repo); usa SSH al servidor.
Ejemplo: `/tmp/nr/on_server.sh worker scripts/subniche.py list --status active`.

## Subnichos: `scripts/subniche.py` (`docs/subniche-discovery.md`)

| Comando | Qué hace |
|---|---|
| `add <entrada> [--manual --label --family --parent --origin]` | Propone una hipótesis (consulta, video o canal); queda `proposed` |
| `approve <slug>` | `proposed` → `active` (solo `active` gasta cuota) |
| `pause <slug>` / `resume <slug>` | Pausa y reactiva una hipótesis |
| `archive <slug>` | Archiva |
| `finalist <slug> [--off]` | Marca o desmarca finalista (se remide cada 7 días) |
| `measure <slug>` | Pide medir esa hipótesis en el siguiente tick |
| `list [--status <estado>]` | Lista hipótesis |
| `export [--out archivo]` | Exporta hipótesis a YAML |
| `import <archivo> \| --b64 <base64> [--dry-run]` | Carga en lote como `proposed` (todo o nada, idempotente) |
| `uv run python scripts/subniche_report.py` | Ranking y reporte de medición |
| `uv run python scripts/subniche_spend_report.py` | Gasto de cuota y USD del descubrimiento |
| `uv run python scripts/seed_subniche_policy.py` | Siembra la política de subnichos (una vez) |
| `GET /api/v1/subniches` (y `/subniches/{slug}`) | API privada de lectura: listado (`include_inactive`) y ficha con canales |

`scripts/pilots.py lanzar` acepta `--niche-label subniche:<slug>` (con el `--dossier-id` de una investigación `listo`).

## Investigación y datos

| Comando | Qué hace |
|---|---|
| `uv run python scripts/flow_research.py pending\|claim\|schema\|validate\|submit` | Encargos de investigación de flujo (skill `flow-research`) |
| `uv run python scripts/read_backlog_ranking.py` | Ranking del backlog de nichos |
| `uv run python scripts/pilots.py`, `pilots_tunnel.py` | Canales piloto |
| `uv run python scripts/backup_mac.py`, `backup_snapshot.py` | Respaldo (ver `docs/backup-restore.md`) |
