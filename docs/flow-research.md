# Investigación de flujo

Desde un nicho `tentativo` del backlog de Mercado, el botón **Iniciar investigación de
flujo** crea un encargo. Claude Code lo atiende con búsqueda web (con la membresía del
propietario, sin gasto de API) y entrega un dossier `dossier-v1` que la app valida y guarda.

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

Solo URLs `https`; precios con `price_checked_on` de máximo 90 días; totales recalculados
(`subtotal = unitario × cantidad`, costo de fase = suma de sus partidas,
`totals.likely` = suma de subtotales); fuentes, herramientas y fases citadas deben existir;
cada fase con criterios de salida; el dossier debe corresponder al encargo. Si la confianza
del nicho es `baja`, `verdict.unknowns` no puede ir vacío.

## Qué no garantiza

Que los datos sean ciertos: solo que están citados, fechados y son coherentes. Los precios y
las cifras son orientativos y el punto de equilibrio es siempre una estimación que hereda las
cifras declaradas por vendedores del backlog.

## Datos y respaldos

Retención de 183 días, igual que los datos de mercado. Las tablas
`flow_research_requests` y `flow_research_dossiers` cuentan como datos de investigación: el
respaldo inicial falla cerrado si tienen filas (decisión 9.4 del propietario pendiente).
Un encargo no usa `provider_requests`, presupuesto, vidIQ ni crea canales.

## API

| Método y ruta | Uso |
| --- | --- |
| `POST /api/v1/flow-research` | Crear (201) o devolver el activo (200). Cuerpo: `niche_label`, `format`, `language` (código `en`, `es`…; `unknown` se rechaza) |
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

Migración `0016`: cierra (`rechazado`, con el motivo en `rejection`) los encargos `pendiente` o `en_curso` sin idioma y no toca los `listo`. `dossier-v1` gana el campo `language` (obligatorio): se asumió que producción aún no tiene dossiers; si los hubiera, se conservan tal cual. Es un cambio de esquema en producción: requiere migración y despliegue aprobados por el propietario.
