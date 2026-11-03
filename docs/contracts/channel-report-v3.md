# channel-report-v3

Estado: **implementado en local y sin desplegar** (rama `feat/web-corte2b`; migración `0021`). Dirección: **canal → NicheRadar**.
Es el reporte de [`v1`](channel-report-v1.md) (formato largo) y de [`v2`](channel-report-v2.md) (Shorts) con **una sola
adición**: los minutos de trabajo humano por video y el método con el que se midieron.
Contexto: [`../ecosistema-youtube.md`](../ecosistema-youtube.md) y [`../pilots.md`](../pilots.md).
Decisión del método: [`../superpowers/specs/2026-11-02-rediseno-movil-corte2-design.md`](../superpowers/specs/2026-11-02-rediseno-movil-corte2-design.md)
(«Decisiones cerradas (2026-11-03)»).

## Qué es

El mismo reporte que `v1`/`v2` (videos, etapas, costos, mediciones, `checks`), más `human_minutes` en cada video y
`human_minutes_method` en el reporte. NicheRadar **solo lee**: no corrige ni inventa cifras y suma los totales por su
cuenta. El contrato es **neutral respecto al método**: valida la forma de los datos, no cómo se obtuvieron.

## Alcance: largo y Shorts

- `v3` cubre **ambos formatos**: `format` es `"long"` o `"shorts"` y debe coincidir con el formato del piloto
  (`niche.format` de su `pilot-package-v1`). Si no coincide: `422` con `problems[0].path = "contract"`, como en `v2`.
- Según `format`, cada video lleva la `measurement` de `v1` (largo) o la de `v2` (Shorts), sin cambios.
- Un reporte `v1` o `v2` sigue aceptándose; `v3` no los reemplaza.

## Convenciones

Las mismas que `v1`: JSON UTF-8; claves desconocidas rechazadas; fechas ISO 8601 con zona; dinero en USD con dos
decimales y `0 ≤ x ≤ 1.000.000`; contenido tratado como no confiable (los errores no repiten valores); cuerpo máximo
256 KiB; máximo 100 videos por reporte.

## Campos del reporte

Igual que `v1`/`v2`, con estas diferencias marcadas en **negrita**.

| Campo | Tipo | Reglas |
|---|---|---|
| `contract` | texto | **Siempre `"channel-report-v3"`** |
| **`format`** | texto | **`"long"` o `"shorts"`.** Debe coincidir con el formato del piloto |
| `pilot_id` | texto | Patrón `^pil_[0-9]{8}_[a-z0-9-]{1,40}$`. Debe existir |
| `channel_id` | texto | Patrón `^canal-[a-z0-9-]{1,40}$`. Debe coincidir con el canal del token |
| `reported_at` | fecha | No futura (tolerancia de 5 min) |
| `channel_status` | texto | `"active"`, `"paused"` o `"closed"` |
| **`human_minutes_method`** | texto | **Nuevo, obligatorio.** Patrón `^[a-z0-9_]{1,60}$` |
| `videos` | lista | De 0 a 100 objetos `Video` (largo o Shorts según `format`) |
| `checks` | lista | Opcional (0 a 20 comprobaciones) |
| `note` | texto o `null` | Hasta 1500 caracteres |

Sin campo de totales: NicheRadar suma desde `videos`.

### `Video`

Idéntico al de `v1` (largo) o `v2` (Shorts), **más**:

| Campo | Tipo | Reglas |
|---|---|---|
| **`human_minutes`** | entero o `null` | **Nuevo. La clave es obligatoria**: un video `v3` sin ella se rechaza (`422`). Entero estricto de **0 a 100000**; no se aceptan decimales, booleanos ni texto. `null` = **no medido** |

`null` y `0` no significan lo mismo: `null` es «no se midió»; `0` es «se midió y fueron cero minutos». Un exportador que
no mide **no debe rellenar con 0**.

## Método (`human_minutes_method`)

Texto libre con patrón `^[a-z0-9_]{1,60}$` (por ejemplo `claude_sessions_plus_assumed`). El contrato **no tiene una lista
cerrada de métodos**: guarda lo declarado y lo muestra junto a los minutos. Se guarda **por video, junto con los
minutos**, para saber con qué método se obtuvo cada cifra.

Método decidido por el propietario (2026-11-03), a modo de referencia y no como parte del contrato: tiempo activo leído
de los registros de sesión de Claude Code de la carpeta del canal (solo lectura, tope de 15 minutos por hueco entre
eventos) **más** un supuesto fijo declarado por canal para lo que no deja rastro (validación en YouTube Studio). Se
muestra como «medido X · supuesto Y».

**Advertencia (hallazgo):** un método que solo mide esperas en compuertas (el tiempo hasta que alguien aprueba)
**subestima** el trabajo humano real. Quien lea la cifra debe conocer el método declarado antes de compararla con costos
o con otros canales.

## Qué cambia respecto a v1/v2

| Tema | v1 (largo) / v2 (Shorts) | v3 |
|---|---|---|
| `contract` | `channel-report-v1` / `channel-report-v2` | `channel-report-v3` |
| `format` | no existe en v1; `"shorts"` en v2 | `"long"` o `"shorts"` |
| `human_minutes` por video | no existe | Entero 0..100000 o `null`; clave obligatoria |
| `human_minutes_method` | no existe | Obligatorio por reporte |
| Todo lo demás | | Igual: videos, `measurement`, `checks`, estados, costos, envío |

`v3` es **aditivo**: no quita ni cambia ningún campo de `v1`/`v2`.

## Reglas de coherencia

Las de `v1` (y las de `v2` para Shorts), más:

- `format` debe coincidir con el formato del piloto.
- `human_minutes` presente en cada video, como entero estricto de 0 a 100000 o `null`.
- `human_minutes_method` presente y con el patrón indicado, incluso si todos los `human_minutes` son `null` o la lista
  de videos está vacía.

## Idempotencia, orden y envío

Igual que `v1`/`v2`: clave `(pilot_id, video_id)`, un reporte no borra videos que no menciona, NicheRadar nunca edita lo
reportado. Misma ruta `POST /api/v1/pilots/{pilot_id}/reports`; el campo `contract` decide el validador. Códigos
`401/403/404/409/413/422` como antes. Sobre los minutos humanos, dos reglas:

- **Gana el reporte más reciente, también cuando trae `null`.** Un `v3` con `reported_at` más nuevo y
  `human_minutes = null` **sobrescribe con `NULL`** los minutos medidos antes: el último reporte es la verdad.
- **Un `v3` con `reported_at` igual o anterior no cambia nada**: ni los minutos ni el método (se conservan juntos).
- **`v1` y `v2` nunca tocan** los minutos ni el método guardados: un `v1`/`v2` posterior no los borra.

## Totales

`totals` añade dos campos, calculados por NicheRadar:

| Campo | Significado |
|---|---|
| `human_minutes` | Suma de los `human_minutes` no nulos de los videos del piloto. **Es 0 cuando ninguno está medido** |
| `human_minutes_complete` | `true` solo si **todos** los videos tienen dato |

Para un piloto sin mediciones, el total es `0` con `human_minutes_complete = false` y **debe leerse como «sin medir», nunca
como 0 minutos**. El resumen de cierre muestra «Minutos humanos» y, si falta algún dato, «(incompleto: faltan videos sin
dato)».

## Migración

- Migración `0021` (aditiva): columnas `human_minutes` y `human_minutes_method` en `pilot_videos`, con `CHECK` de rango.
  Los videos existentes quedan en `NULL` («no medido»).
- Los canales actuales siguen con `v1`/`v2` sin cambios; pasan a `v3` cuando su exportador sepa medir.
- `channel_sync.py report` sube el archivo tal cual, así que no cambia.

## Ejemplo largo (datos de ejemplo, no reales)

```json
{
  "contract": "channel-report-v3",
  "format": "long",
  "pilot_id": "pil_20261201_historias-largas",
  "channel_id": "canal-historias",
  "reported_at": "2026-12-12T09:30:00Z",
  "channel_status": "active",
  "human_minutes_method": "claude_sessions_plus_assumed",
  "videos": [
    {
      "video_id": "v_20261203_a1b2", "source_state": "EN_MEDICION", "visibility": "public",
      "published_at": "2026-12-04T10:00:00Z", "cost_usd": 1.20, "cost_equivalent_usd": 6.50,
      "machine_minutes": 95, "human_minutes": 42,
      "measurement": {
        "measured_at": "2026-12-11T10:00:00Z", "window_days": 7,
        "avd_pct": 34.5, "views": 820, "browse_share_pct": 41.0, "subscribers_gained": 5
      },
      "failure_code": null
    },
    {
      "video_id": "v_20261205_c3d4", "source_state": "PUBLICADO", "visibility": "public",
      "published_at": "2026-12-10T10:00:00Z", "cost_usd": 1.10, "cost_equivalent_usd": 6.10,
      "machine_minutes": 88, "human_minutes": null,
      "measurement": null,
      "failure_code": null
    }
  ],
  "checks": [],
  "note": null
}
```

## Ejemplo Shorts (datos de ejemplo, no reales)

```json
{
  "contract": "channel-report-v3",
  "format": "shorts",
  "pilot_id": "pil_20261201_curiosidades-shorts",
  "channel_id": "canal-shorts",
  "reported_at": "2026-12-12T09:30:00Z",
  "channel_status": "active",
  "human_minutes_method": "claude_sessions_plus_assumed",
  "videos": [
    {
      "video_id": "s_20261203_a1b2", "source_state": "EN_MEDICION", "visibility": "public",
      "published_at": "2026-12-04T10:00:00Z", "cost_usd": 0.10, "cost_equivalent_usd": 0.40,
      "machine_minutes": 20, "human_minutes": 9,
      "measurement": {
        "measured_at": "2026-12-11T10:00:00Z", "window_days": 7,
        "views": 2400, "engaged_views": 1560, "engaged_view_ratio_pct": 65.0,
        "avg_view_pct": 71.5, "shorts_feed_share_pct": 88.0,
        "shares": 14, "subscribers_gained": 6,
        "stayed_to_watch_pct": null,
        "early_retention_pct": null, "early_retention_second": null
      },
      "failure_code": null
    }
  ],
  "checks": [],
  "note": null
}
```

## Quién genera el reporte

El **método está decidido** (ver arriba) pero el **productor está pendiente**: `scripts/channel_human_minutes.py` todavía
necesita su propio plan y no existe. Mientras tanto, los canales siguen con `v1`/`v2`. El contrato es neutral: cualquier
productor que declare su método y respete la forma de los datos es válido.

## Qué NO cubre v3

- Evaluar reglas de parada con minutos humanos: se guardan, se suman y se muestran, pero no son métrica de parada.
- Una lista cerrada de métodos ni validar que el número sea verosímil para el método declarado.
- Desglose de los minutos (p. ej. «medido» y «supuesto» por separado): el contrato lleva una sola cifra por video.
- Los mismos límites de `v1`/`v2`: CTR e ingresos automáticos, secretos, dirección inversa.
