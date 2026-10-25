# channel-report-v1

Estado: **implementado en local y sin desplegar** (guía y diferencias en [`../pilots.md`](../pilots.md)). Dirección: **canal → NicheRadar**.
Contexto y reparto de responsabilidades: [`../ecosistema-youtube.md`](../ecosistema-youtube.md).
Contrato hermano: [`pilot-package-v1.md`](pilot-package-v1.md).

## Qué es

El reporte que un canal envía a NicheRadar para que este vigile un piloto: qué videos hay,
en qué punto están, cuánto costaron y qué retención midieron. NicheRadar **solo lee**: no corrige
ni inventa cifras, y calcula los totales por su cuenta.

## Convenciones (las mismas que `dossier-v1`)

- JSON UTF-8. **Claves desconocidas se rechazan**: cualquier campo nuevo implica `v2`.
- Fechas ISO 8601 con zona horaria.
- Dinero en USD, decimal con dos decimales como máximo, `0 ≤ x ≤ 1.000.000`.
- El contenido del reporte se trata como **no confiable**: se valida la forma y la coherencia, y
  los mensajes de error no repiten los valores enviados.
- Tamaño máximo del cuerpo: 256 KiB. Máximo 100 videos por reporte.

## Campos

| Campo | Tipo | Reglas |
|---|---|---|
| `contract` | texto | Siempre `"channel-report-v1"` |
| `pilot_id` | texto | `pilot-package-v1`: patrón `^pil_[0-9]{8}_[a-z0-9-]{1,40}$`. Debe existir |
| `channel_id` | texto | Patrón `^canal-[a-z0-9-]{1,40}$`. Debe coincidir con el canal del token |
| `reported_at` | fecha | No futura (tolerancia de 5 min) |
| `channel_status` | texto | `"active"`, `"paused"` o `"closed"` |
| `videos` | lista | De 0 a 100 objetos `Video` |
| `checks` | lista | **Opcional** (ausente equivale a lista vacía). De 0 a 20 comprobaciones de preparación del canal (ver abajo) |
| `note` | texto o `null` | Hasta 1500 caracteres. Texto libre del canal |

No hay campo de totales: NicheRadar suma desde `videos`.

### `Video`

| Campo | Tipo | Reglas |
|---|---|---|
| `video_id` | texto | Patrón `^[A-Za-z0-9_-]{1,60}$`. Identificador del canal (en `canal-historias`, p. ej. `v_20261024_bc75`). Único en el reporte |
| `source_state` | texto | Patrón `^[A-Za-z0-9_]{1,40}$`. El estado interno del canal **tal cual** (en `canal-historias`, p. ej. `EN_MEDICION`). NicheRadar lo traduce a una etapa gruesa |
| `visibility` | texto | `"private"`, `"public"` o `"unknown"` |
| `published_at` | fecha o `null` | Cuándo pasó a público. `null` si aún no lo es |
| `cost_usd` | dinero | **Dinero realmente gastado** en ese video (API de pago) |
| `cost_equivalent_usd` | dinero o `null` | Lo que habría costado el uso de LLM por API cuando lo cubre una suscripción |
| `machine_minutes` | entero o `null` | Minutos de máquina del pipeline, ≥ 0 |
| `measurement` | objeto o `null` | Ver abajo. `null` mientras no haya medición |
| `failure_code` | texto o `null` | Código corto del motivo si el estado se traduce a `killed` o `blocked` |

`cost_usd` y `cost_equivalent_usd` van separados a propósito: no se suman para hablar de dinero
gastado.

### `checks[]`: preparación del canal

La lista de pasos para dejar un canal listo **cambia según el canal y su receta**, así que la
define el canal y NicheRadar no la fija. Cada elemento:

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | texto | Patrón `^[A-Za-z0-9_-]{1,40}$`, único en el reporte (p. ej. `youtube_oauth`, `voice_ref`, `visual_assets`) |
| `label` | texto | 1 a 160 caracteres, en lenguaje llano |
| `ok` | booleano | `true` si está listo |
| `detail` | texto o `null` | Hasta 300 caracteres |
| `expires_at` | fecha o `null` | Cuándo caduca, si caduca (p. ej. la autorización de YouTube en modo prueba) |

NicheRadar usa `checks` para el estado `preparando` y para avisar de bloqueos, sin guardar
ninguna clave.

### `measurement`

| Campo | Tipo | Reglas |
|---|---|---|
| `measured_at` | fecha | Posterior a `published_at` |
| `window_days` | entero | Días de ventana desde la publicación, ≥ 1 |
| `avd_pct` | decimal | Retención media del video, 0 a 100 |
| `views` | entero | ≥ 0 |
| `browse_share_pct` | decimal o `null` | Tráfico de exploración, 0 a 100 |
| `subscribers_gained` | entero o `null` | ≥ 0 |

CTR e impresiones **no existen** en v1: la Analytics API no las entrega.

### De `source_state` a `stage`: lo hace NicheRadar

El canal manda su estado interno sin traducirlo. NicheRadar mantiene **una tabla de traducción
por canal** y la aplica al recibir el reporte. Así el canal no necesita conocer el vocabulario de
NicheRadar, y los cambios de estados del canal se corrigen en un solo lugar.

Para `canal-historias` (propuesta, **por verificar con el canal**):

| `stage` (lo asigna NicheRadar) | `source_state` de `canal-historias` |
|---|---|
| `in_production` | `IDEA_CRUDA`, `IDEA_VALIDADA`, `GUION_BORRADOR`, `GUION_APROBADO`, `GUION_FINAL`, `ASSETS_LISTOS`, `RENDER_COMPLETO`, `QA_APROBADO`, `EMPAQUETADO` |
| `awaiting_human` | `VEREDICTOS_PENDIENTES` |
| `uploaded` | `PROGRAMADO`, y `PUBLICADO` cuando `visibility` sigue siendo `private` |
| `published` | `PUBLICADO` con `visibility = public` |
| `measuring` | `EN_MEDICION` |
| `killed` | `KILL` |
| `blocked` | `BLOQUEADO_POLITICA`, `FALLO_QA` |

Enumeración de `stage`: `in_production`, `awaiting_human`, `uploaded`, `published`, `measuring`,
`killed`, `blocked` y `unknown`.

- Un `source_state` que no está en la tabla del canal se traduce a **`unknown`**: el reporte se
  acepta, se devuelve una advertencia y el piloto queda marcado para revisión humana.
- La tabla vive en NicheRadar, no en este contrato. La de arriba es el contenido inicial.

## Reglas de coherencia

- `measurement` solo puede existir si `published_at` no es `null`.
- Si el estado se traduce a `published` o `measuring`, exige `published_at` no `null` y `visibility = "public"`.
- Si se traduce a `killed` o `blocked`, exige `failure_code`.
- Estas dos reglas se comprueban **después** de traducir; un `source_state` desconocido no puede violarlas.
- `video_id` no se repite dentro del reporte.
- Si el reporte trae más videos publicados que `budget.max_videos` del paquete, se **acepta**
  con una advertencia (`warnings`); el piloto pasa a revisión humana.

## Idempotencia y orden

- La clave es `(pilot_id, video_id)`: reenviar un reporte no duplica nada.
- Por video gana el reporte con `reported_at` más reciente. Si empata, se conserva lo guardado.
- Un reporte nunca borra videos que no menciona; un video que desaparece del reporte se conserva.
- NicheRadar **nunca edita** lo reportado. Si el canal corrige una cifra, envía otro reporte.

## Envío (propuesta de API)

| Método y ruta | Quién | Uso |
|---|---|---|
| `POST /api/v1/pilots/{pilot_id}/reports` | Canal | Envía un reporte |
| `GET /api/v1/pilots/{pilot_id}` | Dashboard o canal | Estado, totales calculados y propuesta (de solo lectura) |

Respuesta `200`:

```json
{ "accepted": true, "videos_upserted": 2, "warnings": [], "pilot_status": "en_ejecución" }
```

Respuesta `422`: `{ "accepted": false, "problems": [{ "path": "videos[1].measurement.avd_pct", "message": "…" }] }`,
con un máximo de 50 problemas y sin repetir los valores enviados.

| Código | Cuándo |
|---|---|
| `401` o `403` | Token ausente, inválido, o de otro canal |
| `404` | El piloto no existe o no es de ese canal |
| `409` | El piloto está `cerrado`, o `channel_id` no coincide con el canal asignado |
| `413` | Cuerpo mayor de 256 KiB |
| `422` | Incumple este contrato |

## Qué hace NicheRadar con un reporte

1. Valida, traduce `source_state` a `stage` con la tabla del canal y guarda por `(pilot_id, video_id)`.
2. Pasa el piloto a `en_ejecución` con el primer reporte que traiga un video.
3. Calcula los totales: videos por etapa, dinero gastado (`cost_usd`), equivalente de LLM,
   minutos de máquina.
4. Compara las mediciones con las `stop_rules` del paquete cuando el hito llegó
   (`milestone`) y hay al menos `min_cases` videos medidos.
5. Si faltan casos, la propuesta dice **«sin datos suficientes»** y no concluye nada.
6. Cuando hay base, propone `seguir` o `cerrar` con los números a la vista. **No decide**: el
   humano confirma.

## Ejemplo (datos de ejemplo, no reales)

```json
{
  "contract": "channel-report-v1",
  "pilot_id": "pil_20261101_historia-militar",
  "channel_id": "canal-historias",
  "reported_at": "2026-11-12T09:30:00Z",
  "channel_status": "active",
  "videos": [
    {
      "video_id": "v_20261103_a1b2", "source_state": "EN_MEDICION", "visibility": "public",
      "published_at": "2026-11-04T10:00:00Z", "cost_usd": 0.32, "cost_equivalent_usd": 1.53,
      "machine_minutes": 67,
      "measurement": { "measured_at": "2026-11-11T10:00:00Z", "window_days": 7,
        "avd_pct": 22.1, "views": 140, "browse_share_pct": null, "subscribers_gained": 0 },
      "failure_code": null
    },
    {
      "video_id": "v_20261110_c3d4", "source_state": "VEREDICTOS_PENDIENTES", "visibility": "private",
      "published_at": null, "cost_usd": 0.20, "cost_equivalent_usd": 1.10,
      "machine_minutes": 58, "measurement": null, "failure_code": null
    }
  ],
  "checks": [
    { "id": "youtube_oauth", "label": "Autorización de YouTube", "ok": true,
      "detail": "Modo prueba: caduca a los 7 días", "expires_at": "2026-11-17T00:00:00Z" },
    { "id": "voice_ref", "label": "Voz de referencia", "ok": true, "detail": null, "expires_at": null },
    { "id": "visual_assets", "label": "Visuales del nicho", "ok": false,
      "detail": "Faltan loops y retratos", "expires_at": null }
  ],
  "note": null
}
```

## Quién genera el reporte

Un **script aparte, dentro del canal**, que lee la base de datos del canal en **modo solo lectura**
y escribe el reporte en `outbox/`. No modifica el pipeline del canal: en `canal-historias`, que
produce a diario, un fallo del script no puede afectar la producción.

## Qué NO cubre v1

- CTR, impresiones ni ingresos automáticos (la Analytics API no los entrega y el canal no los mide).
- Curva de retención por video.
- Secretos de ningún tipo.
- Dirección inversa: NicheRadar no manda órdenes al canal por este contrato.
- Métricas propias de Shorts (p. ej. vistas atractivas): `measurement` es el de formato largo. Ver preguntas abiertas.

## Decisiones tomadas (2026-10-25)

- `checks` es opcional: así el exportador de un canal que aún no lo calcula sigue siendo válido.
- Quién genera el reporte: un script aparte del canal, con la base en solo lectura.
- Quién traduce los estados: NicheRadar, con una tabla por canal. El reporte lleva `source_state`.
- Ingresos: no entran en `v1`. Queda **sin responder** la pregunta de cuándo sumarlos (se
  decidirá cuando el canal los mida; sería `v2`).

## Preguntas abiertas

- ¿Cómo se miden los pilotos de **Shorts**? `measurement` usa la retención media del formato largo; Shorts necesita otras métricas (p. ej. vistas atractivas). Opciones: un mapa genérico de métricas, o una `v2` por formato.
