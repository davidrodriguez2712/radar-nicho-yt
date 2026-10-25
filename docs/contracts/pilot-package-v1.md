# pilot-package-v1

Estado: **implementado en local y sin desplegar** (guía y diferencias en [`../pilots.md`](../pilots.md)). Dirección: **NicheRadar → canal**.
Contexto y reparto de responsabilidades: [`../ecosistema-youtube.md`](../ecosistema-youtube.md).
Contrato hermano: [`channel-report-v1.md`](channel-report-v1.md).

## Qué es

El paquete que NicheRadar entrega a un canal cuando el humano autoriza un piloto sobre un
nicho. Es una **foto congelada** de la decisión: qué nicho, con qué evidencia, qué presupuesto y
bajo qué reglas de parada. El canal lo lee y produce; no puede modificarlo.

## Convenciones (las mismas que `dossier-v1`)

- JSON UTF-8. Todas las claves de este contrato son obligatorias salvo que se diga lo contrario.
- **Claves desconocidas se rechazan** (`extra="forbid"`): cualquier campo nuevo implica `v2`.
- Fechas ISO 8601 **con zona horaria** (`2026-11-01T12:00:00Z`).
- Dinero en USD, como número decimal con dos decimales como máximo, `0 ≤ x ≤ 1.000.000`.
- El paquete es **inmutable**. Un cambio de reglas o presupuesto crea otro paquete con otro
  `pilot_id` que lo reemplaza (`supersedes`).

## Campos

| Campo | Tipo | Reglas |
|---|---|---|
| `contract` | texto | Siempre `"pilot-package-v1"` |
| `pilot_id` | texto | Patrón `^pil_[0-9]{8}_[a-z0-9-]{1,40}$`. Lo genera NicheRadar al autorizar. Único y estable |
| `supersedes` | texto o `null` | `pilot_id` del paquete que reemplaza |
| `authorized_by` | texto | 1 a 160 caracteres |
| `authorized_at` | fecha | No futura (tolerancia de 5 min) |
| `valid_until` | fecha | Posterior a `authorized_at`. **Por defecto `authorized_at` + 14 días**; el humano puede cambiarla al autorizar. Pasada esa fecha el paquete ya no se entrega |
| `niche` | objeto | Ver abajo |
| `evidence` | objeto | Ver abajo |
| `dossier` | objeto | Resumen del dossier de investigación (ver abajo) |
| `budget` | objeto | Ver abajo |
| `stop_rules` | lista | De 1 a 10 reglas (ver abajo) |
| `planned_cadence_per_week` | entero | 1 a 14. Videos por semana que se planean. Se elige al autorizar; sirve solo para **estimar fechas** de los hitos por número de video |
| `preparation_days` | entero | 1 a 60, por defecto 14. Plazo para dejar el canal listo, contado desde la entrega |
| `close_after_failed_milestones` | entero | 1 a 5, por defecto 2 (el valor de `canal-historias`). Se elige al autorizar y **no puede cambiarse después**: las reglas de parada se fijan antes de empezar |
| `target_channel` | texto o `null` | Patrón `^canal-[a-z0-9-]{1,40}$`. `null` si el piloto crea un canal nuevo |
| `recipe` | objeto o `null` | `{ "name": texto, "version": "X.Y.Z" }` de `david-youtube-foundry` |
| `package_sha256` | texto | Huella (ver «Integridad») |

### `niche`

| Campo | Tipo | Reglas |
|---|---|---|
| `label` | texto | Etiqueta del nicho en el backlog de Mercado, 1 a 160 caracteres |
| `format` | texto | `"long"` o `"shorts"` (el mismo vocabulario de `dossier-v1`) |
| `language` | texto | Patrón `^[a-z]{2}(-[A-Z]{2})?$`. **Sin valor por defecto**. Se elige **al iniciar la investigación de flujo** (no al autorizar) y llega fijo desde el dossier; al autorizar solo se muestra, no se cambia |

El idioma no se asume porque la competencia, los precios y las herramientas cambian por idioma, y
porque en `canal-historias` un texto en otro idioma dentro del guion distorsionó la voz.

Al iniciar la investigación, NicheRadar calcula `language_mix` desde las fichas del nicho y
muestra el idioma dominante como **sugerencia**. Si hay empate o predomina `unknown`, no
preselecciona nada. La clave de la investigación es **nicho + formato + idioma**: un nicho con
fichas en dos idiomas genera dos investigaciones y dos dossiers independientes. Para autorizar,
el piloto toma el idioma del dossier; un piloto no puede cambiarlo sin una investigación nueva.

### `evidence` (foto congelada del backlog)

| Campo | Tipo | Reglas |
|---|---|---|
| `captured_at` | fecha | Momento de la foto |
| `scores` | objeto | `opportunity`, `automation`, `creator_fit`, `market`: entero 0 a 100 o `null` |
| `confidence` | texto | `"low"`, `"medium"` o `"high"` |
| `listings_with_income` | entero | ≥ 0 |
| `language_mix` | lista (0 a 10) | Idioma de las fichas del nicho: `{ "language": "en" \| "es" \| … \| "unknown", "share_pct": 0 a 100 }`. Los porcentajes suman 100 (± 1). `unknown` agrupa las fichas sin idioma detectado |
| `figures` | lista (0 a 30) | `{ "name": texto, "value": número, "unit": texto, "origin": "seller_declared" \| "estimate" \| "verified" }` |

`origin` es obligatorio en cada cifra: una cifra declarada por un vendedor nunca debe leerse
como verificada.

### `dossier` (resumen; el dossier completo se queda en NicheRadar)

| Campo | Tipo | Reglas |
|---|---|---|
| `request_id` | UUID | Encargo de investigación de flujo de origen |
| `schema` | texto | `"dossier-v1"` |
| `recommendation` | texto | `"go"`, `"go_with_conditions"` o `"no_go"` |
| `confidence` | texto | `"low"`, `"medium"` o `"high"` |
| `thesis` | texto | 1 a 1500 caracteres |
| `unknowns` | lista (0 a 20) | Lo que el dossier declaró no saber. Obligatoria si `confidence` del nicho es `low` |

Un paquete con `recommendation = "no_go"` solo se emite si el humano lo autoriza explícitamente;
NicheRadar lo marca en `thesis`.

### `budget`

| Campo | Tipo | Reglas |
|---|---|---|
| `currency` | texto | Siempre `"USD"` |
| `low`, `likely`, `high` | dinero | `low ≤ likely ≤ high` |
| `max_videos` | entero | 1 a 50. Tope del piloto |
| `basis` | texto | 1 a 1500 caracteres: de dónde salen las cifras (medido, estimado, de qué canal) |

El piloto no debe superar `budget.high` sin una nueva autorización.

### `stop_rules[]`

Cada regla es verificable por máquina cuando se puede, y siempre legible por una persona.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | texto | Patrón `^[A-Za-z0-9_-]{1,40}$`, único en el paquete |
| `text` | texto | La regla en lenguaje llano, 1 a 500 caracteres |
| `metric` | texto | `"pipeline_e2e"`, `"avd_pct"`, `"browse_share_pct"`, `"revenue_vs_cost"` o `"manual"` |
| `comparator` | texto | `">="` |
| `threshold` | número o `null` | Umbral. `null` si `metric` es `"manual"` o `"pipeline_e2e"` |
| `min_cases` | entero o `null` | Cuántos videos deben cumplirlo (ej. 3). `null` si no aplica |
| `milestone` | objeto | `{ "kind": "week" \| "video" \| "month", "value": entero ≥ 1 }` |

Las métricas `"manual"` las juzga el humano; NicheRadar solo las muestra. Las demás, NicheRadar las
compara con lo que reporta el canal.

## Integridad

`package_sha256` es el SHA-256 en hexadecimal del JSON **canónico** del paquete sin el propio
campo `package_sha256`: claves ordenadas alfabéticamente, sin espacios, UTF-8. El canal lo
recalcula al recibir el paquete y rechaza el archivo si no coincide. Detecta corrupción en el
transporte; **no** prueba autoría (la autenticación la da el token del canal).

## Un piloto activo por canal

Un canal no puede tener más de un piloto activo. Son **activos** los estados `autorizado`,
`entregado`, `en_ejecución` y `decisión_pendiente`. Un piloto nuevo para ese canal solo avanza
cuando el anterior está `cerrado`.

Motivo: con dos pilotos en el mismo canal las métricas de cada video se mezclan y no se podría
saber qué nicho funcionó.

- Si `target_channel` ya tiene un piloto activo, NicheRadar rechaza la autorización con `409`
  y el código `channel_busy`.
- Si `target_channel` es `null` (canal nuevo), la comprobación se hace al entregar: la entrega
  responde `409` con `channel_busy` si ese canal ya tiene otro piloto activo.

## Entrega (propuesta de API)

Reutiliza las convenciones de `flow-research` (token de servicio, errores `409`/`422`).

| Método y ruta | Quién | Uso |
|---|---|---|
| `GET /api/v1/pilots/pending?channel=<id>` | Canal | Lista los paquetes autorizados, vigentes y no entregados a ese canal |
| `GET /api/v1/pilots/{pilot_id}/package` | Canal | Devuelve el paquete |
| `POST /api/v1/pilots/{pilot_id}/delivery` | Canal | Confirma recepción: `{ "channel_id": …, "package_sha256": … }` |

- La confirmación **es idempotente**: repetirla con el mismo canal y la misma huella responde
  `200` sin cambios. Con otra huella, `409`.
- Al confirmar, el piloto pasa de `autorizado` a `entregado`.
- Un paquete con `target_channel` distinto del canal que consulta no se lista y su descarga
  responde `404`.
- Un paquete con `valid_until` vencido no se lista y responde `410`.

## Errores

| Código | Cuándo |
|---|---|
| `401` o `403` | Token ausente, inválido, o de otro canal |
| `404` | El piloto no existe o no es para ese canal |
| `409` | Huella distinta a la entregada, piloto ya cerrado, o `channel_busy` (el canal ya tiene otro piloto activo) |
| `410` | `valid_until` vencido |
| `422` | (Solo al crear el paquete en NicheRadar) incumple este contrato. Lista `problems` con `path` y `message`, máximo 50, **sin repetir los valores enviados** |

## Ejemplo (datos de ejemplo, no reales)

```json
{
  "contract": "pilot-package-v1",
  "pilot_id": "pil_20261101_historia-militar",
  "supersedes": null,
  "authorized_by": "david",
  "authorized_at": "2026-11-01T12:00:00Z",
  "valid_until": "2026-11-15T12:00:00Z",
  "niche": { "label": "Historia militar explicada", "format": "long", "language": "en" },
  "evidence": {
    "captured_at": "2026-11-01T11:55:00Z",
    "scores": { "opportunity": 78, "automation": 64, "creator_fit": 71, "market": 69 },
    "confidence": "medium",
    "listings_with_income": 5,
    "language_mix": [
      { "language": "en", "share_pct": 80 },
      { "language": "es", "share_pct": 15 },
      { "language": "unknown", "share_pct": 5 }
    ],
    "figures": [
      { "name": "income_median", "value": 1450, "unit": "usd_per_month", "origin": "seller_declared" }
    ]
  },
  "dossier": {
    "request_id": "00000000-0000-4000-8000-000000000001",
    "schema": "dossier-v1",
    "recommendation": "go_with_conditions",
    "confidence": "medium",
    "thesis": "Demanda sólida, ingresos solo declarados por vendedores.",
    "unknowns": ["Ingresos reales del nicho", "Licencias de imágenes"]
  },
  "budget": {
    "currency": "USD", "low": 3, "likely": 19, "high": 41, "max_videos": 10,
    "basis": "10 videos × costo medido en canal-historias; el peor caso suma visuales nuevos estimados"
  },
  "stop_rules": [
    { "id": "retencion-v10", "text": "Retención media ≥ 18% en al menos 3 de los primeros 10 videos",
      "metric": "avd_pct", "comparator": ">=", "threshold": 18, "min_cases": 3,
      "milestone": { "kind": "video", "value": 10 } },
    { "id": "browse-v20", "text": "Tráfico de exploración ≥ 30% y no decreciente al video 20",
      "metric": "browse_share_pct", "comparator": ">=", "threshold": 30, "min_cases": null,
      "milestone": { "kind": "video", "value": 20 } },
    { "id": "viabilidad-m6", "text": "Ingresos ≥ costo en efectivo del stack al mes 6",
      "metric": "revenue_vs_cost", "comparator": ">=", "threshold": 1, "min_cases": null,
      "milestone": { "kind": "month", "value": 6 } }
  ],
  "planned_cadence_per_week": 3,
  "preparation_days": 14,
  "close_after_failed_milestones": 2,
  "target_channel": null,
  "recipe": { "name": "faceless-storytelling", "version": "0.1.0" },
  "package_sha256": "6fa2c4af280684df60aa9aaa71315ae2d662b9e54ad7a0c17cacb97ca0cd3e0e"
}
```

## Qué NO cubre v1

- El dossier completo (competidores, fases, fuentes): se queda en NicheRadar.
- Secretos de ningún tipo: no hay claves, tokens ni rutas de carpetas personales.
- Producción de videos concretos ni cola de encargos por video.
- Ingresos como métrica automática: `revenue_vs_cost` la reporta el canal y hoy `canal-historias`
  no la mide.

## Decisiones tomadas (2026-10-25)

- `valid_until`: 14 días por defecto, editable al autorizar.
- `target_channel`: un piloto activo por canal (`channel_busy`).
- `close_after_failed_milestones`: editable solo al autorizar, nunca después.
