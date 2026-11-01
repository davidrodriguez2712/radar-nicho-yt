# Investigación de flujo

Desde un nicho `tentativo` del backlog de Mercado, el botón **Iniciar investigación de
flujo** crea un encargo. Claude Code lo atiende con búsqueda web (con la membresía del
propietario, sin gasto de API) y entrega un dossier `dossier-v3` (derechos del material y plan de automatización incluidos) que
la app valida y guarda. `dossier-v1` solo se conserva para leer dossiers guardados antes.

## Cómo se opera

1. En **Mercado**, marca el nicho como `tentativo` y pulsa **Iniciar investigación de flujo**.
   El botón se deshabilita mientras haya un encargo `pendiente` o `en_curso`.
2. En Claude Code, desde la raíz del repo, invoca el skill `flow-research`. Necesita
   `NR_API_URL` y `NR_SERVICE_TOKEN` en el entorno o en `.env`; nunca los imprime.
3. El skill reclama el encargo (lease de 60 minutos), investiga, valida el dossier con
   `scripts/flow_research.py validate` y lo envía con `submit`.
4. El dashboard muestra el estado y, cuando está `listo`, el dossier completo.

## Estados

`pendiente` → `en_curso` → `listo` | `rechazado`.

- Un lease vencido devuelve el encargo a `pendiente`; un dossier tardío recibe `409`.
- El primer dossier inválido recibe `422` y deja el encargo `en_curso` para un reintento; el
  segundo lo deja `rechazado` con el motivo. Reintentar es crear un encargo nuevo.
- Una nueva investigación del mismo nicho crea una versión nueva; la anterior se conserva.

## Qué valida la app

Solo URLs `https`; el `schema_version` debe ser `dossier-v3`; precios con `price_checked_on` de máximo 90 días; totales recalculados
(`subtotal = unitario × cantidad`, costo de fase = suma de sus partidas,
`totals.likely` = suma de subtotales); fuentes, herramientas y fases citadas deben existir;
cada fase con criterios de salida; el dossier debe corresponder al encargo. Si la confianza
del nicho es `baja`, `verdict.unknowns` no puede ir vacío. Contrato completo de v2:
[`contracts/dossier-v3.md`](contracts/dossier-v3.md).

## Qué no garantiza

Que los datos sean ciertos: solo que están citados, fechados y son coherentes. Los precios y
las cifras son orientativos y el punto de equilibrio es siempre una estimación que hereda las
cifras declaradas por vendedores del backlog.

## Datos y respaldos

Retención de 183 días, igual que los datos de mercado. Las tablas
`flow_research_requests` y `flow_research_dossiers` cuentan como datos de investigación y se respaldan cifrados en el Mac (decisión 9.4,
opción A) con retención local acotada; ver [backup-restore.md](backup-restore.md).
Un encargo no usa `provider_requests`, presupuesto, vidIQ ni crea canales.

## API

| Método y ruta | Uso |
| --- | --- |
| `POST /api/v1/flow-research` | Crear (201) o devolver el activo (200). Cuerpo: `niche_label`, `format`, `language` (código `en`, `es`…; `unknown` se rechaza) y, opcional, `gate_override` (`reason` de 10 a 500 caracteres y `by`). Si el nicho no pasa una compuerta responde `409 gate_failed` con `reasons` |
| `GET /api/v1/flow-research` | Listar (`niche_label`, `format`, `language`, `status`, `limit`) |
| `GET /api/v1/flow-research/pending` | Pendientes (libera leases vencidos) |
| `GET /api/v1/flow-research/{id}` | Encargo, evidencia y dossier |
| `POST /api/v1/flow-research/{id}/claim` | Reclamar con `{"owner": ...}` |
| `POST /api/v1/flow-research/{id}/dossier` | Enviar `{"owner": ..., "dossier": {...}}` |

## Cambio acordado: el idioma entra en la clave (2026-10-25, implementado en la rama, sin desplegar)

Decisión del propietario: el idioma se elige **al iniciar la investigación**, no al autorizar el
piloto. La clave del encargo pasa de `(niche_label, format)` a `(niche_label, format, language)`.

Qué cambia al implementarlo:

- `flow_research_requests` y `flow_research_dossiers` ganan `language` (patrón `^[a-z]{2}(-[A-Z]{2})?$` o `unknown`), el índice único activo y el de búsqueda lo incluyen (migración nueva, `down_revision` = la cabeza actual).
- `POST /api/v1/flow-research` exige `language`; el dashboard la preselecciona con el idioma dominante de `language_mix` y no preselecciona si hay empate o predomina `unknown`.
- `dossier-v1` copia `language` del encargo, como ya hace con `niche_label` y `format`; la skill `flow-research` investiga competidores y precios en ese idioma.
- El paquete del piloto toma el idioma del dossier (ver [`contracts/pilot-package-v1.md`](contracts/pilot-package-v1.md)).
- Encargos existentes: la migración los marca `unknown`. Los `pendiente` o `en_curso` se cierran como `rechazado` (hay que iniciarlos de nuevo con idioma); los `listo` se conservan, pero no pueden convertirse en piloto (`language_unknown`).

Migración `0016`: cierra (`rechazado`, con el motivo en `rejection`) los encargos `pendiente` o `en_curso` sin idioma y no toca los `listo`. `dossier-v1` gana el campo `language` (obligatorio): se verificó el 2026-10-25 (solo lectura) que producción no tiene dossiers; si los hubiera, se conservan tal cual. Desplegado el 2026-10-25 en la release [014](release-20261025-014.md). Es un cambio de esquema en producción: requiere migración y despliegue aprobados por el propietario.


## Compuertas de selección (2026-10-26)

Decisión del propietario: los nichos que se investiguen deben ser casi automatizables, con poca
intervención humana. Los scores del backlog solo ordenan y no restan riesgo de política
([market-intel.md](market-intel.md)); las compuertas son el freno real. **Los umbrales son
supuestos iniciales del agente, no datos medidos**: se ajustan con evidencia.

| Compuerta | Umbral por defecto | Variable de entorno |
|---|---|---|
| Automatización mínima del nicho | 90 | `NR_GATE_MIN_AUTOMATION` |
| Riesgo de política `alto` bloquea | sí | `NR_GATE_BLOCK_HIGH_POLICY_RISK` |
| Minutos humanos máximos por video (suma de `production_flow`) | 60 | `NR_GATE_MAX_HUMAN_MINUTES` |
| Derechos resueltos (`rights.verdict` distinto de `blocked`) | siempre | (no configurable) |

Se aplican en tres puntos:

1. **Al pedir la investigación** (`POST /flow-research`): si la automatización del nicho es
   **conocida** y menor que el mínimo, o su riesgo de política es alto, responde `409 gate_failed`
   con los motivos. Una automatización desconocida no bloquea aquí (el encargo ya exige que
   exista score de automatización: `no_evidence`). Cada encargo congela en `evidence.gate` los
   umbrales usados y lo que el nicho obtuvo.
2. **Al entregar el dossier**: uno que recomiende `go` o `go_with_conditions` se rechaza si
   `rights.verdict` es `blocked`, si los minutos humanos superan el máximo o si el nicho no pasa
   (salvo excepción registrada). `no_go` siempre se acepta. Con `blocked`, el único veredicto
   válido es `no_go`, y eso no se puede forzar.
3. **Al autorizar el piloto**: se repiten las comprobaciones sobre el dossier guardado. Falla con
   `409 gate_failed` salvo `accept_gate_failure: true` (`--accept-gate-failure` en
   `scripts/pilots.py lanzar`); eso queda en el evento `gate_failure_accepted` y en el prefijo
   `[COMPUERTAS NO CUMPLIDAS aceptadas por el humano: …]` de `thesis`. Un dossier `dossier-v1`
   guardado no evalúa derechos ni plan de automatización, así que falla la compuerta de derechos
   hasta que un humano lo acepte.

**Excepción al pedir la investigación** (decisión humana, registrada): `gate_override` con
`reason` y `by`; se congela en `evidence.gate_override` con la hora y levanta las compuertas de
nicho y de minutos en la entrega del dossier de ese encargo. Solo se registra si la compuerta
realmente falló. Desde la línea de comandos:

```sh
uv run python scripts/flow_research.py create gaming_general --format long --language en \
  --gate-override-reason "Experimento barato decidido por el propietario" --gate-override-by david
```

La skill nunca pide ni usa excepciones; si el nicho no pasa, entrega `no_go` razonado.
