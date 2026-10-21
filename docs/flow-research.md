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
| `POST /api/v1/flow-research` | Crear (201) o devolver el activo (200) |
| `GET /api/v1/flow-research` | Listar (`niche_label`, `format`, `status`, `limit`) |
| `GET /api/v1/flow-research/pending` | Pendientes (libera leases vencidos) |
| `GET /api/v1/flow-research/{id}` | Encargo, evidencia y dossier |
| `POST /api/v1/flow-research/{id}/claim` | Reclamar con `{"owner": ...}` |
| `POST /api/v1/flow-research/{id}/dossier` | Enviar `{"owner": ..., "dossier": {...}}` |
