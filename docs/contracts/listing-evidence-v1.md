# listing-evidence-v1

Estado: **propuesto, sin implementar** (2026-10-28). Pendiente de aprobación del propietario.
Dirección: **extractor (lectura de capturas con visión + API de YouTube + texto de la ficha) →
NicheRadar**. Sustituye al borrador manual `schema_ficha.md` usado en la prueba de 15 fichas del
2026-10-27.

## 1. Qué es y por qué existe

El resultado estructurado y verificable de revisar **una ficha** de DealBaron (un canal en venta).
Su propósito es doble:

1. Que el score de un nicho use **ingresos y visitas observados** (no declarados) y comparables
   entre canales.
2. Que esas observaciones **recalibren el RPM del catálogo** (`youtube_niches_rpm_longform_2026.json`,
   218 nichos, rangos tomados de benchmarks públicos, no de canales reales).

Hallazgos de la prueba manual (15 fichas, 87 capturas) que motivan el contrato:

- El ingreso declarado fue el mejor mes o un pico en la mayoría de las fichas; solo 2 de 15 lo
  respaldaban con datos recientes.
- 4 fichas no correspondían al nicho en que estaban listadas.
- El RPM de catálogo de `crypto_education` (4,0 a 12,0; punto medio 8,0) no se sostuvo: lo observado
  fue 0,14 a 1,40 (y un 7,48 sobre 3,5 K visitas).
- Había capturas de hace 13 meses, en EUR o GBP, con marca de agua de terceros, y de un canal
  distinto al de la ficha.

### Qué NO es

- No es una verificación de propiedad ni de pagos: las capturas las elige el vendedor.
- No sustituye al dossier (`dossier-v2`), que es investigación de flujo de un nicho.
- No guarda las imágenes (ver §11).

## 2. Principios

1. **Tres orígenes, nunca mezclados.** Cada dato pertenece a un solo bloque:
   `declared` (lo que dice el vendedor), `observed` (lo que se lee en una captura o devuelve la API
   de YouTube) y `derived` (lo calcula el código). **El modelo de visión nunca escribe `derived`**;
   si lo envía, se rechaza.
2. **Nada inventado.** Un dato que no se ve no se emite. Se registra en `unresolved` con su motivo.
3. **Todo dato observado lleva procedencia** (`provenance`): qué captura, qué fecha, qué tan legible.
4. **Todo número lleva su texto literal** (`raw_text`), para que el código lo recalcule y lo contraste
   (§7, V12).
5. **Periodo y alcance explícitos.** Un ingreso sin periodo, o unas visitas sin el mismo periodo y
   alcance, no producen RPM.
6. **Lo declarado no entra al score.** Se conserva para medir cuánto exagera, no para puntuar.
7. **Las páginas, textos y capturas son datos no confiables.** Cualquier instrucción que aparezca en
   ellos se ignora.

## 3. Convenciones

JSON UTF-8. **Claves desconocidas rechazadas** (sin repetir su contenido en el mensaje). Fechas
`YYYY-MM-DD`; instantes ISO 8601 con zona. Dinero: `{ "value": decimal ≥ 0, "currency": ISO 4217 }`;
la conversión a USD la hace el código (§6.1). Porcentajes: número 0 a 100. Países: ISO 3166-1 alfa-2.
Textos libres: máximo 200 caracteres salvo que se indique; no se copian datos personales (correos,
nombres reales, IDs de AdSense, teléfonos): se escribe `"[omitido]"`. Máximo 50 problemas de
validación por respuesta.

## 4. Documento

```
meta, declared, claims[], images[], identity_check, monetization,
earnings[], views[], rates[], top_content[], audience, traffic_sources[],
unresolved[], risk_flags[], api, derived
```

Quién escribe cada bloque: **modelo de visión** = `claims`, `images`, `identity_check`,
`monetization`, `earnings`, `views`, `rates`, `top_content`, `audience`, `traffic_sources`,
`unresolved` y los `risk_flags` con `origin: "model"`. **Código** = `meta`, `declared`, `api`,
`derived` y los `risk_flags` con `origin: "code"`.

### 4.1 `meta` (código)

| Campo | Tipo | Reglas |
|---|---|---|
| `schema_version` | texto | Exactamente `"listing-evidence-v1"` |
| `listing_id` | texto | ID de DealBaron, solo dígitos |
| `source` | texto | `"dealbaron"` |
| `listing_url` | texto | `https` |
| `extracted_at` | instante | Momento de la extracción |
| `extraction_state` | texto | `complete`, `partial`, `no_images`, `failed` (§9) |
| `extractor.model` | texto | Modelo fijado (hoy `gpt-6-luna`) |
| `extractor.tariff_version` | texto | Versión de tarifa usada para el costo |
| `extractor.prompt_version` | texto | Versión del prompt (parte de la clave de idempotencia) |
| `cost_usd` | decimal ≥ 0 | Costo real confirmado |
| `image_count_total` / `image_count_processed` | entero ≥ 0 | Adjuntos de la ficha / procesados |

### 4.2 `declared` (código, desde la ficha)

`title`, `category`, `price_usd`, `subscribers`, `income_monthly_usd`, `expense_monthly_usd`,
`monetization_declared` (`yes`/`no`/`unknown`), `content_type`, `published_text`. Todos pueden ser
`null`. Es la copia de lo ya guardado en `marketplace_listings`; no se vuelve a pedir al modelo.

### 4.3 `claims` (modelo, desde el texto de la descripción)

Lista (0 a 30). Afirmaciones numéricas del vendedor, para compararlas luego con lo observado.

| Campo | Tipo | Reglas |
|---|---|---|
| `kind` | texto | `income`, `revenue`, `views`, `watch_hours`, `rpm`, `cpm`, `subscribers`, `audience`, `growth`, `other` |
| `value` | número o `null` | |
| `unit` | texto | `usd`, `eur`, `views`, `hours`, `percent`, `count`, `other` |
| `period_text` | texto o `null` | Cómo lo dijo el vendedor («mensual», «lifetime», «junio») |
| `snippet` | texto ≤ 200 | Cita literal |

### 4.4 `images[]` (modelo)

Una entrada por adjunto, en el orden de la ficha. `index` empieza en 0.

| Campo | Tipo | Reglas |
|---|---|---|
| `index` | entero | Único |
| `sha256` | texto | Lo calcula el código; el modelo no lo envía |
| `kind` | texto | `studio_overview`, `studio_revenue`, `studio_analytics_content`, `studio_audience`, `studio_traffic`, `studio_earn_status`, `adsense_payments`, `video_detail`, `other_channel_or_account`, `chat_or_listing_screenshot`, `unrelated`, `unreadable` |
| `captured_on` | fecha o `null` | La fecha de la captura (§6.2) |
| `captured_on_basis` | texto | `visible_in_image`, `inferred_from_period_end`, `unknown` |
| `channel_name_visible` | texto o `null` | Nombre del canal tal como se ve |
| `currency_visible` | ISO 4217 o `null` | |
| `ui_language` | texto o `null` | Código de idioma de la interfaz |
| `third_party_watermark` | booleano | Marca de agua o logo ajeno |
| `partially_obscured` | booleano | Cifras tapadas o recortadas |
| `duplicate_of` | entero o `null` | `index` de una imagen idéntica (el código lo confirma con `sha256`) |

### 4.5 `identity_check` (modelo)

| Campo | Tipo | Reglas |
|---|---|---|
| `channel_name_in_images` | texto o `null` | |
| `matches_listing_title` | texto | `yes`, `no`, `cannot_tell` |
| `matches_api_channel` | texto | `yes`, `no`, `cannot_tell`. El modelo recibe el título del canal de la API y lo compara |
| `manager_not_owner_seen` | booleano | Studio muestra al usuario como «manager» |
| `notes` | texto ≤ 200 | |

Si `matches_api_channel = "no"` o `matches_listing_title = "no"` con `matches_api_channel =
"cannot_tell"`, el código marca `identity_mismatch` y el grado es `X` (§8).

### 4.6 `monetization` (modelo)

| Campo | Tipo | Reglas |
|---|---|---|
| `ypp_status` | texto | `active`, `applied_pending`, `base_terms_only`, `not_eligible`, `suspended`, `unknown` |
| `adsense_linked` | booleano o `null` | |
| `payments_status` | texto | `configured`, `setup_in_progress`, `disabled`, `unknown` |
| `monetized_since` | fecha o `null` | |
| `monetized_since_basis` | texto | `visible_in_image`, `inferred_first_revenue_day`, `unknown` |
| `restrictions[]` | lista (0 a 10) | `kind`: `ypp_suspended`, `limited_ads`, `demonetized_videos`, `copyright_claim`, `strike`, `reused_content_notice`, `invalid_traffic`, `other`; `detail` ≤ 200; `image_index` |
| `evidence_images` | lista de enteros | Capturas que lo sostienen; cada índice debe existir en `images` |

### 4.7 `earnings[]` (modelo)

| Campo | Tipo | Reglas |
|---|---|---|
| `image_index` | entero | Debe existir |
| `scope` | texto | `all`, `long`, `shorts`, `live`, `other` |
| `metric` | texto | `estimated_revenue`, `ad_revenue`, `premium_revenue`, `membership_revenue`, `supers_revenue`, `shopping_revenue`, `adsense_payment_received`, `other` |
| `period.kind` | texto | `last_7d`, `last_28d`, `last_90d`, `last_365d`, `calendar_month`, `lifetime`, `custom` |
| `period.start` / `period.end` | fecha o `null` | `start ≤ end`. Obligatorias salvo `lifetime` sin fechas visibles |
| `amount.value` | decimal ≥ 0 | |
| `amount.currency` | ISO 4217 | Obligatoria. Si no se ve, la medida va a `unresolved` (`ambiguous_currency`) |
| `raw_text` | texto ≤ 40 | El valor literal visto, p. ej. `"$295.18"`, `"£0.04"` |
| `legibility` | texto | `clear` o `partial` (lo `unreadable` no se emite) |

### 4.8 `views[]` (modelo)

| Campo | Tipo | Reglas |
|---|---|---|
| `image_index` | entero | |
| `scope` | texto | `all`, `long`, `shorts`, `live`, `other` |
| `metric` | texto | `views`, `engaged_views`, `watch_hours`, `impressions`, `unique_viewers`, `subscribers_net`, `subscribers_gained`, `subscribers_lost` |
| `period` | objeto | Igual que en `earnings[]` |
| `value` | número ≥ 0 | (`subscribers_net` puede ser negativo) |
| `previous_value` | número o `null` | El valor del periodo anterior, si Studio lo muestra |
| `raw_text` | texto ≤ 40 | Literal, p. ej. `"69.7K"` |
| `legibility` | texto | `clear` o `partial` |

### 4.9 `rates[]` (modelo): lo que Studio calcula

`metric`: `rpm`, `playback_cpm`, `cpm`, `ctr_pct`, `avg_view_duration_seconds`, `avg_percentage_viewed`.
Mismos `image_index`, `scope`, `period`, `raw_text`, `legibility`; `value` número ≥ 0 y, si es dinero,
`currency`. **El RPM que muestra Studio se guarda aquí y nunca sustituye al calculado** (§6.3); sirve
para contrastarlo.

### 4.10 `top_content[]` (modelo; 0 a 20)

`rank` (entero), `title` (≤ 120), `published_on` (fecha o `null`), `views` (número o `null`),
`revenue` (`amount` o `null`), `period` (objeto), `image_index`. Permite medir la concentración.

### 4.11 `audience` (modelo)

`scope` (`channel`, `video`, `unknown`), `period` (objeto o `null`), `countries[]` (máx. 10: `code`,
`pct`), `age_groups[]` (`range`, `pct`), `gender` (`male_pct`, `female_pct`, `other_pct`; cada uno
puede ser `null`), `returning_viewers_pct`, `image_index`. La suma de `countries[].pct` no puede
superar 100,5.

### 4.12 `traffic_sources[]` (modelo)

`source`: `browse`, `suggested`, `search`, `external`, `direct`, `shorts_feed`, `notifications`,
`playlists`, `channel_pages`, `other`; `pct`, `scope`, `period`, `image_index`.

### 4.13 `unresolved[]` (modelo)

Lo que se buscó y no se pudo leer. Obligatorio explicarlo, para distinguir «no estaba» de «no se vio».

| Campo | Tipo | Reglas |
|---|---|---|
| `topic` | texto | `revenue`, `views`, `rpm`, `audience`, `monetization`, `identity`, `dates`, `currency` |
| `reason` | texto | `not_in_images`, `unreadable`, `cropped`, `watermark`, `ambiguous_currency`, `ambiguous_period`, `contradictory` |
| `image_index` | entero o `null` | |
| `note` | texto ≤ 200 | |

### 4.14 `risk_flags[]` (modelo o código)

| Campo | Tipo | Reglas |
|---|---|---|
| `code` | texto | Ver tabla |
| `severity` | texto | `low`, `medium`, `high` |
| `origin` | texto | `model` o `code` |
| `evidence` | lista | Enteros (`image_index`), `"api"` o `"listing_text"` |
| `note` | texto ≤ 200 | |

Códigos y quién los emite:

| Código | Origen | Condición |
|---|---|---|
| `identity_mismatch` | código | §4.5 |
| `niche_mismatch` | modelo | El contenido visto no corresponde al nicho de la ficha |
| `text_contradiction` | modelo | El texto se contradice (p. ej. «monetización: no» y «monetizado») |
| `edited_or_inconsistent_numbers` | modelo | Cifras que no cuadran entre sí o rastros de edición |
| `third_party_watermark` | código | Alguna imagen lo tiene |
| `foreign_currency` | código | Alguna medida usada no está en USD |
| `stale_capture` | código | Edad de la captura > 120 días |
| `payments_not_configured` | código | `payments_status` ≠ `configured` |
| `ypp_suspended` | código | `ypp_status = suspended` o `not_eligible` tras haber estado activo |
| `limited_ads` | modelo | Aviso de anuncios limitados |
| `recently_monetized` | código | `monetized_since` hace menos de 90 días |
| `new_channel` | código | Edad del canal (API) < 180 días |
| `declining_traffic` | código | Visitas del periodo vs. el anterior < −25 % |
| `single_video_dependence` | código | `top1_revenue_share` o `top1_views_share` > 0,5 |
| `declared_income_unsupported` | código | `declared_vs_observed_ratio` < 0,5 |
| `audience_concentrated` | código | Un país > 85 % de las visitas |
| `shorts_dominant` | código | Shorts > 50 % de las visitas del alcance `all` |
| `reused_or_inauthentic_risk` | modelo | Voz o presentador sintéticos, plantillas repetidas, compilaciones |
| `copyright_risk` | modelo | Música, clips o material de terceros |
| `manager_not_owner` | código | `manager_not_owner_seen = true` |
| `low_sample_period` | código | El conjunto primario tiene menos de 10 000 visitas |

### 4.15 `api` (código)

Datos de la API de YouTube (`channels.list`, `playlistItems.list`, `videos.list`), con costo de cuota
de unas 100 unidades para 4 800 canales más unas 5 800 unidades para sus últimos videos.

| Campo | Tipo |
|---|---|
| `fetched_at` | instante |
| `channel_id`, `title`, `handle`, `country` | texto (pueden ser `null`) |
| `created_at` | instante |
| `subscribers` (`null` si ocultos), `total_views`, `video_count` | entero |
| `recent_videos[]` (hasta 30 más recientes) | `video_id`, `title` (≤ 120), `published_at`, `duration_seconds`, `is_short`, `views`, `likes`, `comments` |

`is_short = duration_seconds ≤ 180`. Si la API no encuentra el canal, `api` es `null` y la ficha
queda `partial`.

## 5. Escenarios de extracción: qué pasa cuando falta información crítica

«Crítico» = la información que se necesita para calcular un ingreso mensual comparable y un RPM.
Hay 5 piezas: **(a)** identidad del canal, **(b)** ingreso observado con periodo y moneda,
**(c)** visitas observadas del mismo periodo y alcance, **(d)** estado de monetización, **(e)** fecha
de la captura.

| # | Situación | Qué se hace | Grado | RPM calculado |
|---|---|---|---|---|
| S1 | Todo presente (a–e) | Conjunto primario completo | A (o B por antigüedad/tamaño) | Sí |
| S2 | Ingreso sin visitas de ese periodo | Ingreso mensual normalizado; sin RPM | C | No |
| S3 | Visitas sin ingreso, canal con YPP activo | Ingreso modelado = visitas mensuales × RPM del nicho (marcado `modeled`) | D | No |
| S4 | Sin capturas (`no_images`), con API | Visitas de los últimos 90 días de los videos recientes (cota inferior) × RPM del nicho | D | No |
| S5 | Sin capturas ni API | Solo `declared`; no entra al score | E | No |
| S6 | Identidad no coincide | Toda la evidencia de imagen se excluye | X | No |
| S7 | Identidad `cannot_tell` | Se usa para el ingreso, con grado máximo C y marcada | ≤ C | No (la regla R8 exige identidad confirmada) |
| S8 | Moneda no visible o ambigua | La medida va a `unresolved`; no se usa | según resto | No para esa medida |
| S9 | Moneda ≠ USD | Conversión con la tasa del día `period.end` (§6.1). Sin tasa disponible: se trata como S8 | según resto | Con tasa, sí |
| S10 | Fecha de captura no visible | `captured_on = period.end`, `basis = inferred_from_period_end` | máx. B | Sí |
| S11 | Sin fecha ni periodo | La medida va a `unresolved` (`ambiguous_period`) | — | No |
| S12 | Varios periodos disponibles | Selección del conjunto primario (§6.2) | según resto | Un RPM por conjunto elegible |
| S13 | Solo cifras lifetime | Se guarda, no se normaliza a mensual | C | No (§6.4: sesgo de pre-monetización) |
| S14 | Canal no monetizado o YPP suspendido en el periodo | Ingreso observado = 0 es esperado; fuera de la muestra de RPM | E para ingresos | No |
| S15 | Solo Shorts (o mayoría Shorts) | El RPM se guarda con `scope = shorts` y **no entra** a la recalibración de formato largo (§7) | según resto | Sí, por alcance |
| S16 | Imágenes duplicadas | Solo la primera cuenta (`sha256`) | — | — |
| S17 | Marca de agua o cifras tapadas | Lo ilegible va a `unresolved`; `third_party_watermark` se marca | baja un grado si afecta a ingresos o visitas | Solo con cifras claras |
| S18 | Monetización con pago «en configuración» | Se guarda; riesgo `payments_not_configured`; el ingreso observado sigue contando | sin cambio | Sí |
| S19 | Datos contradictorios entre capturas | Ambos van a `unresolved` (`contradictory`); se marca `edited_or_inconsistent_numbers` | X si afecta al conjunto primario | No |
| S20 | Más de 12 imágenes | Se procesan las 12 de mayor prioridad (§9.2); el resto se registra como no procesado | `partial` | según resto |
| S21 | La ficha ya no existe o no tiene adjuntos nuevos | No se reextrae; se conserva la última extracción vigente | — | — |
| S22 | Falla del modelo o JSON inválido tras reintento | `extraction_state = failed`; no se guarda evidencia parcial | — | — |

## 6. Cálculos del código (`derived`)

El modelo no calcula nada de esta sección.

### 6.1 Normalización de dinero

`usd_value = amount.value × tasa(currency → USD, fecha = period.end)`. Si `currency = USD`, tasa 1.
Cada conversión guarda `fx_rate`, `fx_date` y `fx_source`. Sin tasa disponible para esa moneda y
fecha: `usd_value = null` y la medida no se usa.

### 6.2 Conjuntos de observación

Un **conjunto** (`observation_set`) une un ingreso y unas visitas que cumplen todo esto:

1. Mismo `image_index` o imágenes del mismo `studio_*` con la misma `captured_on`.
2. Mismo `scope`.
3. Mismo `period` (`start` y `end` idénticos, o `kind` igual con fechas que difieren ≤ 1 día).
4. Ingreso con `metric ∈ {estimated_revenue, ad_revenue}`; visitas con `metric = views`.
5. Ambos con `legibility = clear` o `partial`.

Atributos de cada conjunto: `revenue_usd`, `views`, `watch_hours` (si existe), `days` (duración del
periodo), `capture_age_days = extracted_at − captured_on`, `monthly_revenue_usd = revenue_usd ×
30,4375 / days`, `monthly_views = views × 30,4375 / days`, `rpm_usd = revenue_usd / views × 1000`.
Con `period.kind = lifetime` no se calculan los valores mensuales.

**Selección del conjunto primario** (el que alimenta el score), en este orden:

1. Solo conjuntos con `scope ∈ {all, long}`.
2. Preferir el periodo `last_28d`, luego `last_90d`, luego `calendar_month`, luego `last_365d`.
3. A igual periodo, el de menor `capture_age_days`.
4. A igual edad, el de mayor `views`.

`lifetime` nunca es primario.

### 6.3 RPM calculado

`rpm_usd = revenue_usd / views × 1000`, siempre con ingreso y visitas del **mismo conjunto**. Studio
define RPM sobre todas las visitas; así se calcula aquí, y coincide con el `rpm` de Studio cuando
Studio lo muestra (el contraste vive en `derived.rpm_check`, con diferencia relativa).

### 6.4 Elegibilidad para la recalibración de RPM

Un conjunto entra a la muestra de RPM de un nicho solo si cumple **todas**:

| Regla | Condición |
|---|---|
| R1 | Grado A o B |
| R2 | `scope = long`, o `scope = all` con Shorts < 10 % de las visitas |
| R3 | Periodo de 28 a 365 días (`days`) |
| R4 | `views ≥ 10 000` |
| R5 | `capture_age_days ≤ 365` |
| R6 | Monetizado todo el periodo (`monetized_since ≤ period.start`, o `ypp_status = active` sin reciente alta) |
| R7 | `revenue_usd` y `views` convertidos a USD con tasa válida |
| R8 | Identidad confirmada (`matches_api_channel = yes`) |
| R9 | Una sola muestra por ficha (la del conjunto primario) |

Se excluyen explícitamente los **lifetime** (sesgados a la baja por visitas anteriores a la
monetización) y los periodos con una sola pieza viral que supere el 80 % de las visitas.

### 6.5 Otros derivados

| Campo | Fórmula |
|---|---|
| `observed_monthly_income_usd` | `monthly_revenue_usd` del conjunto primario; si no hay conjunto (S2), el ingreso aislado normalizado; si no hay ingreso (S3/S4), `null` |
| `income_level` | `L1` conjunto primario (ingreso y visitas); `L2` ingreso sin visitas; `L3` modelado (visitas × RPM); `L4` solo declarado; `L5` nada |
| `modeled_monthly_income_usd` | `monthly_views_lower_bound × rpm_niche_usd / 1000`, solo en `L3` |
| `monthly_views_lower_bound` | Suma de `views` de los videos de la API publicados en los últimos 90 días, ÷ 3. Es cota inferior: las vistas acumuladas de videos más antiguos no se cuentan |
| `declared_vs_observed_ratio` | `observed_monthly_income_usd / declared.income_monthly_usd` (`null` si falta alguno) |
| `trend.views_pct_change` | `(value − previous_value) / previous_value × 100` de `views` del conjunto primario |
| `trend.revenue_pct_change` | Ídem con ingreso, si Studio muestra el periodo anterior |
| `concentration.top1_revenue_share`, `top1_views_share` | De `top_content[]`, sobre el mismo periodo |
| `audience.tier1_share` | Suma de `pct` de US, CA, GB, AU, DE, NL, SE, NO, DK, CH, AT, IE, NZ |
| `channel_age_days` | `extracted_at − api.created_at` |
| `uploads_per_month_90d` | Videos de `recent_videos` publicados en 90 días ÷ 3 |
| `shorts_share_of_videos` | Proporción de `is_short` en `recent_videos` |
| `rpm_check` | `(rpm calculado − rpm de Studio) / rpm de Studio`; marca `edited_or_inconsistent_numbers` si el valor absoluto supera 0,15 |

## 7. Recalibración del RPM

El catálogo actual queda como **prior** y no se sobrescribe. Las observaciones se guardan aparte
(tabla `niche_rpm_observed`, propuesta) y el score lee, por nicho y formato, este estado:

| Estado | Condición | RPM usado |
|---|---|---|
| `catalog` | menos de 3 muestras elegibles | Punto medio actual (`(rate_low + rate_high) / 2`) |
| `blended` | 3 o 4 muestras | `(n × mediana_observada + k × punto_medio) / (n + k)`, con `k = 5` |
| `observed` | 5 o más muestras | Mediana ponderada observada |

- **Ponderación de cada muestra** `w = min(views / 100 000, 1) × (1 − capture_age_days / 365) ×
  gradeFactor`, con `gradeFactor = 1,0` para A y `0,7` para B.
- **Intervalo:** percentiles 25 y 75 ponderados, más `n` y `updated_at`.
- **Fuera de rango:** si la mediana queda fuera de `[rate_low, rate_high]` del catálogo, el nicho se
  marca `rpm_out_of_catalog_range` y se muestra en el panel, sin ajustar el valor.
- **Solo formato largo.** Hoy el catálogo es solo `long`; las muestras `shorts` se guardan pero no
  recalibran.
- **Estacionalidad.** Se guarda el mes de `period.end`. En v1 solo se marca (`q4_sample`: octubre a
  diciembre); el ajuste por mes llega cuando haya muestras de más de un trimestre.
- **Mezcla de países.** Se guarda `tier1_share`. En v1 el RPM es por canal completo; separar por
  país queda para una versión posterior.
- **Trazabilidad.** Cada estado guarda los `listing_id` que lo sostienen y la versión del contrato.
- **Reversible.** Borrar las observaciones devuelve el nicho a `catalog`.

## 8. Calidad de la evidencia

| Grado | Condiciones |
|---|---|
| **A** | Identidad `yes`; `ypp_status = active`; conjunto primario (§6.2) con `days` 28 a 365, `views ≥ 10 000`, `capture_age_days ≤ 120`, moneda resuelta |
| **B** | Como A, pero incumple **una** de estas: edad 121 a 365 días, `views` 1 000 a 9 999, `days` 7 a 27 |
| **C** | Hay ingreso observado sin visitas del mismo periodo (S2), o solo conjuntos lifetime, o la identidad es `cannot_tell`, o la edad supera 365 días |
| **D** | Sin ingreso observado; solo visitas de la API (S3/S4) |
| **E** | Solo lo declarado (S5), canal no monetizado o YPP suspendido en el periodo (S14) |
| **X** | `identity_mismatch`, contradicciones en el conjunto primario (S19), o `edited_or_inconsistent_numbers` en severidad `high` |

`scoring_eligible_income` = `true` para A, B y C; `modeled` para D; `false` para E y X. El score
recibe `income_level`, el ingreso usado, el grado y los `risk_flags`; la confianza de un nicho pasa
a depender del grado de sus fichas, no del número de fichas con ingreso declarado.

## 9. Extracción

### 9.1 Orden

1. Texto de la ficha → `declared`, `claims`.
2. API de YouTube (canal y últimos videos) → `api` (sin costo monetario).
3. Descarga de adjuntos (cada uno con el mismo `User-Agent` y pausa que el scraper) → `sha256`,
   duplicados.
4. Una llamada de visión por ficha, con las imágenes no duplicadas (máximo 12), el título del canal
   de la API y el título de la ficha → bloques del modelo (`images`, `identity_check`, `monetization`, `earnings`, `views`, `rates`, `top_content`, `audience`, `traffic_sources`, `unresolved`, `risk_flags`), con **salida estructurada estricta**.
5. Validación (§10) y derivados (§6). Las imágenes no se guardan.

### 9.2 Prioridad con más de 12 imágenes

`studio_revenue` > `studio_overview` > `studio_earn_status` > `studio_analytics_content` >
`studio_audience` > `studio_traffic` > `adsense_payments` > `video_detail` > el resto.

### 9.3 Idempotencia, costos y reintentos

- **Clave:** `(listing_id, conjunto de sha256, prompt_version, schema_version)`. Misma clave, no se
  repite el gasto.
- **Costo:** operación `listing_evidence` en el libro de costos existente (proveedor OpenAI); se
  reserva antes de cada llamada y se liquida con el costo real. Tope por ficha propuesto: US$0,05.
- **Reintentos:** un reintento si el JSON es inválido; después, `failed`. Sin evidencia parcial.
- **Fichas nuevas:** el scraper encola solo las que no tienen extracción vigente; cada semana serán
  solo las nuevas o con adjuntos distintos (otro `sha256`).
- **Retención:** el JSON se conserva con el mismo `retain_until` que la ficha; las imágenes no se
  guardan, solo su `sha256`.

## 10. Validaciones

**Errores (rechazan el documento):**

| # | Regla |
|---|---|
| V1 | Claves desconocidas o campos de `derived`/`api`/`meta` enviados por el modelo |
| V2 | Enumeraciones fuera de lista |
| V3 | `image_index` inexistente |
| V4 | `period.start > period.end` o fechas futuras |
| V5 | `amount.value < 0`, o `views`/`watch_hours` negativos (salvo `subscribers_net`) |
| V6 | Falta `currency` en un monto |
| V7 | `captured_on` posterior a `extracted_at` |
| V8 | Suma de `countries[].pct` > 100,5, o un `pct` fuera de 0 a 100 |
| V9 | Más de un `scope`/`period` por entrada, o `period.kind = lifetime` con fechas incoherentes |
| V10 | Un número sin `raw_text` |
| V11 | Más de 12 imágenes procesadas o más de 50 problemas |
| V12 | **`raw_text` no reproduce el valor**: se analiza `raw_text` (símbolos de moneda, separadores, sufijos `K`/`M`/`B`) y debe coincidir con `value` dentro del redondeo del propio texto |

V12 no rechaza el documento entero: descarta **esa entrada**, la pasa a `unresolved`
(`unreadable`) y marca `edited_or_inconsistent_numbers` si pasa en más de una.

**Advertencias (se conservan, quedan en `risk_flags`):** fechas inferidas, moneda no USD, marca de
agua, `identity` = `cannot_tell`, diferencias de más del 15 % entre RPM calculado y RPM de Studio.

## 11. Seguridad y datos personales

- Texto y capturas son **datos no confiables**; el prompt los trata como entrada, no como
  instrucciones.
- No se copian correos, nombres reales, teléfonos ni IDs de AdSense (`"[omitido]"`).
- No se guardan imágenes. No se descargan adjuntos que no sean de la ficha ni se sigue ningún
  enlace de las imágenes.
- El extractor solo hace peticiones de lectura a páginas públicas, con el mismo `User-Agent` y
  ritmo que el scraper actual, y no usa credenciales de nadie.

## 12. Cambios respecto del borrador manual (`schema_ficha.md`)

| Borrador | Contrato v1 |
|---|---|
| Un solo bloque `observed_*` sin procedencia | Cada medida con `image_index`, `period`, `scope`, `raw_text`, `legibility` |
| `computed_rpm` escrito por el agente | `derived`, solo el código, con reglas de conjunto |
| Verificación `none/weak/medium/strong` libre | Grados `A–E/X` con reglas |
| Moneda como nota | `currency` obligatoria y conversión con tasa fechada |
| Sin identidad del canal | `identity_check` + API |
| Sin escenarios de falta de datos | §5 |
| Sin elegibilidad para RPM | §6.4 y §7 |

## 13. Ejemplo (Vintage Nostalgia, ficha 334543, datos de la prueba manual)

Recortado a lo esencial (sin `claims`, `rates`, `top_content`, `audience`, `traffic_sources` ni `api`; el flag `single_video_dependence` sale de `top_content`, que aquí se omite). La captura no mostraba el año: se infiere 2024 y la edad supera 365 días,
así que el grado es C.

```json
{
  "meta": {"schema_version": "listing-evidence-v1", "listing_id": "334543", "source": "dealbaron",
           "listing_url": "https://dealbaron.com/listing/334543", "extracted_at": "2026-10-28T12:00:00Z",
           "extraction_state": "complete",
           "extractor": {"model": "gpt-6-luna", "tariff_version": "2026-09-27", "prompt_version": "ev-1"},
           "cost_usd": "0.0013", "image_count_total": 9, "image_count_processed": 9},
  "declared": {"title": "Vintage Nostalgia", "category": null, "price_usd": 1700, "subscribers": 2380,
               "income_monthly_usd": 375, "expense_monthly_usd": null, "monetization_declared": "yes",
               "content_type": null, "published_text": null},
  "images": [{"index": 0, "kind": "studio_revenue", "captured_on": "2024-07-18",
              "captured_on_basis": "inferred_from_period_end", "channel_name_visible": null,
              "currency_visible": "USD", "ui_language": "en", "third_party_watermark": false,
              "partially_obscured": false, "duplicate_of": null}],
  "identity_check": {"channel_name_in_images": null, "matches_listing_title": "cannot_tell",
                     "matches_api_channel": "cannot_tell", "manager_not_owner_seen": false},
  "monetization": {"ypp_status": "active", "adsense_linked": null, "payments_status": "unknown",
                   "monetized_since": "2024-04-01", "monetized_since_basis": "inferred_first_revenue_day",
                   "restrictions": [], "evidence_images": [0]},
  "earnings": [{"image_index": 0, "scope": "all", "metric": "estimated_revenue",
                "period": {"kind": "last_28d", "start": "2024-06-21", "end": "2024-07-18"},
                "amount": {"value": 295.18, "currency": "USD"}, "raw_text": "$295.18", "legibility": "clear"}],
  "views": [{"image_index": 0, "scope": "all", "metric": "views",
             "period": {"kind": "last_28d", "start": "2024-06-21", "end": "2024-07-18"},
             "value": 69700, "previous_value": null, "raw_text": "69.7K", "legibility": "clear"}],
  "unresolved": [{"topic": "identity", "reason": "not_in_images", "image_index": null,
                  "note": "no se ve el nombre del canal"}],
  "risk_flags": [{"code": "single_video_dependence", "severity": "high", "origin": "code",
                  "evidence": [0], "note": "un video aporta el 91 % del ingreso"}],
  "derived": {"primary_set": {"scope": "all", "days": 28, "revenue_usd": 295.18, "views": 69700,
                              "capture_age_days": 832, "rpm_usd": 4.235, "monthly_revenue_usd": 320.9},
              "income_level": "L1", "observed_monthly_income_usd": 320.9,
              "declared_vs_observed_ratio": 0.856, "evidence_grade": "C",
              "scoring_eligible_income": true, "rpm_sample_eligible": false}
}
```

## 14. Decisiones que necesito del propietario (con valor propuesto)

| # | Decisión | Propuesta |
|---|---|---|
| D1 | Fuente de tasas de cambio | Tasas de referencia diarias del BCE, guardadas con fecha |
| D2 | Tope de gasto por ficha y total | US$0,05 por ficha; tope del proceso US$15 (gasto esperado US$5 a 8) |
| D3 | Prior de la recalibración (`k`) y mínimos (3 y 5 muestras) | `k = 5`, mínimos 3 y 5 |
| D4 | Umbral de antigüedad máxima para entrar a la muestra de RPM | 365 días (y 120 para grado A) |
| D5 | Lista de países nivel 1 para `tier1_share` | La de §6.5 |
| D6 | ¿Guardar imágenes? | **No**: solo `sha256` y el JSON extraído |
| D7 | Orden de despliegue | 1) API de YouTube (`api`), 2) prueba con 100 fichas para medir costo real, 3) lanzamiento a todas |
