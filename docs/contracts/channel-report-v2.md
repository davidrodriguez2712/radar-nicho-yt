# channel-report-v2

Estado: **implementado en local y sin desplegar** (propuesto el 2026-10-25; implementado después, rama `feat/channel-report-v2`). Dirección: **canal → NicheRadar**.
Nace de la decisión del propietario: el reporte de los pilotos de **Shorts** es una `v2`; el [`v1`](channel-report-v1.md)
queda como el reporte del formato largo. Sustento de las métricas: [`../bench-shorts-metrics.md`](../bench-shorts-metrics.md).
Contexto: [`../ecosistema-youtube.md`](../ecosistema-youtube.md) y [`../pilots.md`](../pilots.md).
Contrato hermano: [`pilot-package-v1.md`](pilot-package-v1.md).

## Qué es

El mismo reporte que `v1` (qué videos hay, en qué punto están, cuánto costaron y qué midieron), pero con una
`measurement` pensada para Shorts. NicheRadar **solo lee**: no corrige ni inventa cifras, y calcula los totales por su
cuenta.

## Alcance: solo Shorts, no un contrato por formato genérico

- **`v2` cubre únicamente Shorts.** `format` es siempre `"shorts"`.
- El formato largo se queda en `v1`. Si más adelante hace falta mejorar el largo, será otra versión; no se mezclan
  formatos en un mismo reporte.
- Un reporte debe coincidir con el formato del piloto: `niche.format` de su `pilot-package-v1` tiene que ser `"shorts"`.
- Se descarta, por ahora, el «mapa genérico de métricas» (la otra opción de las preguntas abiertas de `v1`): obliga a
  validar nombres libres y rompe la regla de que una clave desconocida se rechaza.

## Convenciones

Las mismas que `v1`: JSON UTF-8; claves desconocidas rechazadas; fechas ISO 8601 con zona; dinero en USD con dos
decimales y `0 ≤ x ≤ 1.000.000`; contenido tratado como no confiable (los errores no repiten valores); cuerpo máximo
256 KiB; máximo 100 videos por reporte.

## Campos del reporte

Igual que `v1`, con estas diferencias marcadas en **negrita**.

| Campo | Tipo | Reglas |
|---|---|---|
| `contract` | texto | **Siempre `"channel-report-v2"`** |
| **`format`** | texto | **Nuevo. Siempre `"shorts"`** |
| `pilot_id` | texto | Patrón `^pil_[0-9]{8}_[a-z0-9-]{1,40}$`. Debe existir **y ser de formato Shorts** |
| `channel_id` | texto | Patrón `^canal-[a-z0-9-]{1,40}$`. Debe coincidir con el canal del token |
| `reported_at` | fecha | No futura (tolerancia de 5 min) |
| `channel_status` | texto | `"active"`, `"paused"` o `"closed"` |
| `videos` | lista | De 0 a 100 objetos `Video` |
| `checks` | lista | Opcional, igual que `v1` (0 a 20 comprobaciones) |
| `note` | texto o `null` | Hasta 1500 caracteres |

Sin campo de totales: NicheRadar suma desde `videos`.

### `Video`

Idéntico a `v1` (`video_id`, `source_state`, `visibility`, `published_at`, `cost_usd`, `cost_equivalent_usd`,
`machine_minutes`, `failure_code`), **salvo `measurement`**, que usa el objeto de abajo. La traducción de
`source_state` a `stage` y sus reglas no cambian; la tabla por canal de un canal de Shorts la define NicheRadar con el
canal, como en `v1`.

### `measurement` (Shorts)

| Campo | Tipo | Reglas | De dónde sale |
|---|---|---|---|
| `measured_at` | fecha | Posterior a `published_at`, no futura | |
| `window_days` | entero | ≥ 1. Días de ventana desde la publicación | |
| `views` | entero | ≥ 0. Inicios y repeticiones, sin mínimo de tiempo | API: `views` |
| `engaged_views` | entero | ≥ 0 y **≤ `views`** | API: `engagedViews` |
| `engaged_view_ratio_pct` | decimal | 0 a 100. Si `views` > 0, debe ser `engaged_views / views × 100` con tolerancia de 0,1; si `views` = 0, debe ser `null` | Derivado |
| `avg_view_pct` | decimal o `null` | 0 a 100. Retención media de quien se queda (si la API devolviera más de 100, el exportador lo limita a 100; ver preguntas abiertas) | API: `averageViewPercentage` |
| `shorts_feed_share_pct` | decimal o `null` | 0 a 100. Vistas con fuente de tráfico `SHORTS` sobre `views` | API: `insightTrafficSourceType=SHORTS`. Requiere dos consultas con `views` (una con la fuente, otra total) |
| `shares` | entero o `null` | ≥ 0 | API: `shares` |
| `subscribers_gained` | entero o `null` | ≥ 0 | API: `subscribersGained` |
| `stayed_to_watch_pct` | decimal o `null` | 0 a 100. **Solo Studio**, cargado a mano | Studio: «Viewed vs swiped away» |
| `early_retention_pct` | decimal o `null` | 0 a 100. **Experimental**: retención a ~3 s según la curva | API: `audienceWatchRatio` por `elapsedVideoTimeRatio` |
| `early_retention_second` | decimal o `null` | Segundo al que corresponde `early_retention_pct`. Obligatorio si ese campo no es `null`; `null` si lo es | |

Notas:

- **La retención temprana es el eje de la medición.** En el borrador, la candidata automatizable es
  `engaged_view_ratio_pct`; `stayed_to_watch_pct` es el dato directo de Studio y `early_retention_pct` el intento de
  medirla en segundos. Los tres pueden convivir; ninguno es obligatorio salvo `engaged_view_ratio_pct`.
- `engaged_view_ratio_pct` es **obligatorio** (puede ser `null` solo si `views` = 0). Los demás, salvo `views`,
  `engaged_views` y `measured_at`/`window_days`, son opcionales.
- Ninguna métrica de bucle o rewatch: la API no la entrega.
- CTR e impresiones: no aplican a Shorts. La Analytics API directa no las entrega; la Reporting API masiva trae `video_thumbnail_impressions` y `..._ctr` desde 2026-01-15, y no se sabe si cubre Shorts.
- Con `views` por debajo de un mínimo (`MIN_SHORTS_VIEWS = 100` en `pilots/rules.py`), la medición se **guarda pero no cuenta** para una regla de parada (ver abajo).

## Qué cambia respecto a v1

| Tema | v1 (formato largo) | v2 (Shorts) |
|---|---|---|
| `contract` | `channel-report-v1` | `channel-report-v2` |
| `format` | no existe | `"shorts"` |
| Retención | `avd_pct` | `engaged_view_ratio_pct` (principal), `avg_view_pct`, `stayed_to_watch_pct`, `early_retention_pct` |
| Tráfico | `browse_share_pct` | `shorts_feed_share_pct` |
| Resonancia | no existe | `engaged_views`, `shares` |
| Crecimiento | `subscribers_gained` | `subscribers_gained` (igual) |
| Todo lo demás | | Igual: videos, `checks`, estados, costos, idempotencia, envío |

`avd_pct` y `browse_share_pct` **desaparecen** de `measurement`: son del largo y un campo desconocido se rechaza.

## Reglas de coherencia

Las de `v1` (sobre `measurement`, `published`/`measuring`, `killed`/`blocked`, `video_id` único y el máximo de videos
del paquete), más:

- `format` debe ser `"shorts"` y coincidir con el formato del piloto.
- `engaged_views ≤ views`, y `engaged_view_ratio_pct` consistente con ambos (ver tabla).
- `early_retention_second` obligatorio si hay `early_retention_pct`.
- Un video con `measurement` y `published_at = null` es inválido, como en `v1`.

## Reglas de parada y mínimo de vistas

- `pilot-package-v1` admite, según `niche.format`, las métricas `engaged_view_ratio_pct`, `avg_view_pct` y
  `shorts_feed_share_pct` en un piloto de Shorts (PR #10). Con este contrato dejan de ser `no_evaluable`:
  `engaged_view_ratio_pct` y `avg_view_pct` se evalúan como «al menos `min_cases` videos con la métrica ≥ umbral» y
  `shorts_feed_share_pct` con el último valor contado, igual que sus equivalentes del largo. `shares` y
  `subscribers_gained` se guardan y se muestran, pero todavía no son métricas de parada.
- Un video solo cuenta para `min_cases` si su `measurement.views` alcanza el mínimo (**100 vistas**, constante
  `MIN_SHORTS_VIEWS`; a confirmar con los primeros datos). Por debajo, la medición se guarda y la regla queda
  `sin_datos_suficientes`.
- No hay umbrales oficiales de YouTube para estas métricas. Los umbrales de cada piloto los fija el paquete, tras
  calibrar con los primeros Shorts. Ver el bench.

## Estados

Los del piloto (`en_ejecución`, `cerrado`, etc.) y los de etapa (`stage`) no cambian. Estado del contrato:

| Estado del contrato | Significado |
|---|---|
| `borrador` | Propuesta inicial |
| `aprobado` | El propietario lo revisó. Falta código |
| `implementado` | **Hoy.** Validador, almacenamiento (migración `0017`) y reglas listos; falta desplegar y probar con un canal real |
| `desplegado` | En producción |

## Idempotencia, orden y envío

Igual que `v1`: clave `(pilot_id, video_id)`, gana el `reported_at` más reciente, un reporte no borra videos que no
menciona, NicheRadar nunca edita lo reportado. Misma ruta `POST /api/v1/pilots/{pilot_id}/reports`; el campo
`contract` decide qué validador se usa. Códigos `401/403/404/409/413/422` como en `v1`, con una adición:

| Código | Cuándo |
|---|---|
| `422` | El `contract` no corresponde al formato del piloto (un reporte `v1` a un piloto de Shorts, o `v2` a uno de formato largo): `problems[0].path = "contract"`, sin repetir valores |

## Migración desde v1

- **No hay datos de Shorts en `v1`**: hoy no hay pilotos de Shorts en marcha, así que no hay nada que convertir.
- Los pilotos de formato largo siguen con `v1`, sin cambios.
- **Almacenamiento (decidido al implementar):** **tabla propia** `pilot_shorts_measurements` (migración `0017`, aditiva),
  una fila por video (`pilot_video_id`, con borrado en cascada). `measured_at`, `window_days`, `views` y
  `subscribers_gained` siguen en `pilot_videos`; en la tabla nueva van `engaged_views`, `engaged_view_ratio_pct`,
  `avg_view_pct`, `shorts_feed_share_pct`, `shares`, `stayed_to_watch_pct`, `early_retention_pct` y
  `early_retention_second`, con `CHECK` de rango y de la pareja de retención temprana. Un reporte más reciente
  reemplaza la fila entera; si ya no trae `measurement`, la fila se borra. La tabla se respalda con las demás de pilotos
  (revisión esperada `0017`).
- `rules.py` y el cálculo de totales (`measured`) eligen la métrica según la regla; un video con medición de v2 cuenta como medido.
- El exportador de cada canal de Shorts cambia a `channel-report-v2`; `v1` sigue aceptándose para el largo. El
  `channel_sync.py report` sube el archivo tal cual, así que no cambia.

## Ejemplo (datos de ejemplo, no reales)

```json
{
  "contract": "channel-report-v2",
  "format": "shorts",
  "pilot_id": "pil_20261201_curiosidades-shorts",
  "channel_id": "canal-shorts",
  "reported_at": "2026-12-12T09:30:00Z",
  "channel_status": "active",
  "videos": [
    {
      "video_id": "s_20261203_a1b2", "source_state": "EN_MEDICION", "visibility": "public",
      "published_at": "2026-12-04T10:00:00Z", "cost_usd": 0.10, "cost_equivalent_usd": 0.40,
      "machine_minutes": 20,
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

Un script aparte dentro del canal, como en `v1`, que lee la base del canal en solo lectura **y consulta la YouTube
Analytics API** con `creatorContentType==SHORTS` (que sea filtro válido en el reporte por video no está confirmado: probarlo con un canal autorizado). Calcula `engaged_view_ratio_pct`. `stayed_to_watch_pct` no sale de la
API: si alguien lo carga a mano desde Studio, el canal lo pasa tal cual.

## Qué NO cubre v2

- Formato largo (sigue en `v1`).
- CTR, impresiones, ingresos automáticos, rewatch o bucle.
- «Shown in feed» ni «viewed vs swiped away» automáticos: no existen en la API.
- Curva de retención completa por video (solo el punto experimental de ~3 s).
- Secretos de ningún tipo, ni dirección inversa.

## Preguntas abiertas

- ¿Qué umbral usa `engagedViews`? La API dice «más allá del primer fotograma»; Help (Studio) dice «más allá de los
  primeros segundos, sin bucles»; «30 s o final» es solo prensa. Cambia la lectura de `engaged_view_ratio_pct`. Se
  resuelve contrastando la API con Studio en un canal real.
- Desde 2026-08-27 YouTube cuenta las vistas desde que empieza la reproducción en todos los formatos: las vistas del
  formato largo (v1) anteriores y posteriores pueden no ser comparables.
- ¿Funciona `audienceWatchRatio` por `elapsedVideoTimeRatio` en Shorts, y cómo trata los bucles? Define si
  `early_retention_pct` pasa de experimental a oficial, y si `avg_view_pct` puede pasar de 100.
- ¿Mínimo de vistas por video (100 propuesto) y ventana (`window_days`) para considerar válida una medición?
- Reglas de parada de Shorts: **resuelto**: enumeración por `niche.format` (PR #10) y evaluación con este contrato.
- Tabla propia o columnas nuevas: **resuelto**, tabla propia (`0017`).
- Rango de `early_retention_second`: se acepta de 0 a 180 s (un Short puede durar hasta 3 min); ajustar si hace falta.
