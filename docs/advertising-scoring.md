# Publicidad, puntuación combinada y confianza

Implementación de la tarea 6.6. Métodos `advertising-v1`, `market-v2` y
`opportunity-v2`. Son heurísticas reproducibles, no probabilidades de éxito ni
certificaciones de monetización. No hay benchmarks ni referencias reales precargados.

## Qué se estima

Solo se acepta una tasa publicitaria neta para el creador, expresada en USD por
1.000 vistas para vídeos largos o por 1.000 **engaged views** para Shorts.
No se extrapolan automáticamente las vistas observadas del nicho a un canal nuevo.
No se generan proyecciones de cobros ni se restan ingresos hipotéticos del presupuesto.

El RPM total de YouTube puede incluir anuncios, Premium, membresías y otras fuentes;
el CPM representa gasto publicitario y no ingreso neto del creador. Ninguno se convierte
automáticamente a esta tasa exclusivamente publicitaria. Definiciones contrastadas con
[YouTube Analytics](https://support.google.com/youtube/answer/9314357?hl=en).
La monetización depende de elegibilidad, revisión y activación, no solo de obtener
vistas: [YouTube Partner Program](https://support.google.com/youtube/answer/72851?hl=en) y
[monetización de Shorts](https://support.google.com/youtube/answer/12504220?hl=en).
Consulta: 2026-09-14; estas páginas no proporcionan un RPM aplicable a nuestros candidatos.
No se fijan umbrales de elegibilidad ni porcentajes de reparto en el código.

## Entrada manual y alcance

En **Backlog → detalle → Publicidad y puntuación** está el editor técnico JSON.
API privada: `GET /api/v1/opportunities/{id}/scoring` y `POST` al mismo recurso.
El POST recibe `{"configuration": {...}, "expected_version": 0}`; la versión esperada
debe coincidir con la última, o devuelve 409. Cada guardado crea una nueva versión.
Requiere la migración `0006`; no se ejecutó sobre el VPS.

La configuración agrupa:

- `format`, `language`, `audience_key`: deben coincidir con la oportunidad.
- `advertising`: benchmark documentado o `null` si no existe.
- `references`: referencias congeladas y revisadas por formato, o `null`.
- `relevance_review`: evidencia de revisión temática manual o `null`. No elimina
  exclusiones automáticas por ruido, ambigüedad o tema sin clasificar.
- `retention_basis`: justificación explícita de conservación autorizada.
- `retain_until`: fecha y hora con zona de caducidad de toda la configuración.

El editor no escoge un plazo de conservación por el usuario. Estos campos son para
supuestos originales, datos propios autorizados y referencias documentadas; no para
copiar respuestas restringidas de un proveedor. Registrar una nota no otorga permiso
sobre datos ajenos. No hay importación ni extracción automática de fuentes económicas.

### Contrato del benchmark

Los campos se documentan aquí sin cifras de ejemplo que puedan confundirse con RPM reales:

| Campo | Contenido requerido |
| --- | --- |
| `version`, `source`, `assumptions` | Versión, procedencia verificable y razonamiento del rango |
| `origin` | `manual_assumption`, `own_analytics` o `synthetic`; nunca ingresos privados inferidos de competidores |
| `format`, `language`, `audience_key` | Alcance idéntico a la oportunidad |
| `audience_geography` | Región o mezcla de espectadores explícitamente definida, o `null` |
| `geography_basis`, `geography_evidence` | `unknown`, `assumed` u `observed`, con justificación identificada |
| `unit` | `usd_ads_per_1000_views` para largos; `usd_ads_per_1000_engaged_views` para Shorts |
| `rate` | Objeto `low`/`high`, decimales finitos no negativos; bajo ≤ alto |
| `revenue_scope` | Exactamente `youtube_ads_only_after_revenue_share` |
| `observed_at`, `valid_until` | Fecha del supuesto/dato y vigencia; ambas con zona horaria |
| `usage`, `usage_evidence` | `pending` por defecto; `enabled` exige evidencia del uso habilitado |
| `monetization`, `monetization_evidence` | `new_channel` por defecto; `unknown` o `active`, este último con evidencia explícita |

Geografía desconocida impide calcular M. Una geografía **supuesta** y documentada permite
una estimación provisional, sin afirmar que sea la audiencia real. Ni inglés ni país
del canal completan esos campos. Cero explícito es válido; ausencia no se convierte en cero.

Un origen sintético no puede alimentar M en modo real. Un benchmark pendiente,
deshabilitado, fuera de vigencia o incompatible tampoco. El estado `documented` significa
datos propios declarados con geografía observada; no validación independiente del radar.
Incluso con monetización declarada activa, `projected_payout_usd` permanece `null`:
este módulo no es un pronosticador de ingresos.

## Cálculos y comparabilidad

M usa el extremo inferior del rango como elección conservadora explícita, **no** como
ingreso esperado: `100 * clamp(log1p(low) / log1p(monetization_p90), 0, 1)`.
La referencia debe incluir `monetization_unit` y `monetization_geography` idénticas al
benchmark, además de formato compatible, fuente, versión y revisión. Sin referencia
comparable, M permanece ausente aunque se pueda mostrar el supuesto económico.

Referencias D/T y condiciones mínimas del mercado se mantienen. Pesos:
D .25, B .30, C .20, T .15, M .10. Se divide la suma ponderada por el peso disponible
y se muestra `weight_coverage`; D/B/C y los mínimos de muestra son obligatorios.
Un mercado sin T/M no se presenta como equivalente a otro con los cinco componentes.
No se normaliza contra el lote actual. Referencias sintéticas nunca calibran mercado real.
La configuración manual permite cargar referencias revisadas, no crearlas a partir del
nombre del nicho; la calibración real sigue pendiente del piloto.

Puntuación combinada: `0.65 * Market Score + 0.35 * Creator Fit`, solo cuando ambos
cumplen sus mínimos. No se rellena el score que falta ni se redistribuyen esos pesos.
La función usada por las explicaciones comparte esta fórmula y sus validaciones.

Confianza se muestra aparte y no multiplica el score:

- `insufficient`: falla un mínimo esencial, incluido Fit incompleto.
- `provisional`: referencias/componentes/revisión incompletos, supuesto publicitario
  no observado o controles de producción/recursos pendientes o excedidos.
- `supported`: componentes, referencias, revisión temática y controles declarados
  completos. No significa confianza estadística ni garantía de inversión.

La confianza del mercado también se conserva por separado. El estado `uncalibrated`
se mantiene visible cuando faltan referencias de mercado, incluso si falta Fit.
Los límites duros se muestran en `resource_gate` y `blockers`, aunque el score sea alto.
`execution_authorized` siempre es `false`: ni guardar, puntuar ni seleccionar lanza
canales, consultas, publicaciones, compras o reservas. Para varios canales hay que
usar los escenarios conjuntos de recursos, no sumar scores ni viabilidades individuales.

## Historial y conservación

Guardar supuestos no reescribe evaluaciones anteriores ni dispara un job. El siguiente
análisis usa la configuración y receta disponibles, y conserva copias de inputs,
versiones, componentes, rango, limitaciones, confianza y resultado de recursos.
Las métricas y M se persisten también en `feature_values`.

La vigencia económica (`valid_until`) y la conservación (`retain_until`) son distintas:
un supuesto fuera de vigencia puede mantenerse para auditar el pasado, pero no puntúa
un análisis nuevo. La fecha de conservación de la evaluación no excede la más corta
entre sus fuentes y su configuración. Al vencer se eliminan explicaciones y scores;
también se vacían las configuraciones caducadas, dejando solo identificadores/versiones
y fechas. Una versión caducada no reactiva silenciosamente otra más antigua. Las
decisiones propias del usuario permanecen. Los respaldos requieren la limpieza ya
documentada; su destino/cifrado operativo todavía está pendiente.

## Referencias de demanda/tendencia calculadas sobre evidencia real

`scripts/compute_references.py` (acción `compute-references` en `easypanel_stage.mjs`)
calcula un percentil 90 real de `demand_by_age` y `trend_relative_change` a partir de las
evaluaciones no sintéticas ya acumuladas, sin inventar ninguna franja: una franja de edad
o la tendencia quedan ausentes del candidato si tienen menos de 5 muestras reales (mismo
umbral `baseline_minimum` que usa la clasificación de breakouts). El resultado se imprime
como `status: "candidate"` con `reviewed: false` y la fuente documentando cuántas muestras
reales respaldan cada número, o `status: "insufficient_real_evidence"` cuando ningún banda
alcanza el mínimo (es el caso actual de Shorts). Es de solo lectura: no guarda nada.

Para activarlo, el propietario copia el `references` candidato al editor de Puntuación de
una oportunidad (`Backlog → oportunidad → Puntuación`), revisa que las cifras sean
razonables y cambia `reviewed` a `true` antes de guardar; solo entonces
`evaluate_market` puede calibrar los componentes `D`/`T`. La tendencia se queda en `null`
mientras el sistema no acumule tres observaciones espaciadas del mismo video (0 muestras
reales hasta ahora); no se sustituye por una franja sintética.

Pruebas: `tests/test_advertising_scoring.py` cubre ausencia/cero, geografía, alcance,
unidades, fuente, vigencia, sintético/real, fórmulas, confianza, límites duros, API
autenticada, control de versiones, snapshots y caducidad. La navegación y guardado
desde el dashboard se prueban en `tests/test_dashboard_navigation.py`. Todas las
cifras económicas de los tests son inventadas y no se instalan como datos del producto.

## Ganancia mensual estimada (`scoring/profit.py`)

`GET /opportunities/{id}/profit` combina tres insumos reales, nunca una vista asumida:

1. **Velocidad de vistas por canal** (`best_channel_views_per_day` /
   `worst_channel_views_per_day` en `CohortMetrics`): mediana de vistas/día observada por
   canal dentro de la cohorte, igual método que `demand_by_age` pero agrupado por canal.
   El canal con mayor velocidad marca el límite superior del rango; el de menor, el
   inferior. Nunca extrapola a un canal nuevo: ambos límites son canales reales ya
   compitiendo.
2. **Cadencia real**: `videos_per_month` de la receta de producción ya asignada a la
   oportunidad (no un supuesto nuevo).
3. **Tasa publicitaria declarada**: el `advertising` de la configuración de puntuación
   (ver arriba), con el mismo contrato y controles de vigencia/origen.

`ganancia = (vistas mensuales × RPM) − costo real de producción` (`resources.monthly_usd`
de `evaluate_plan`). Si falta cualquiera de los tres insumos, devuelve
`status: "incomplete"` con la lista exacta de qué falta (`channel_view_rate`,
`videos_per_month`, `advertising_rate`, `production_cost`) — nunca un número a medias.
La ganancia puede ser negativa (pérdida); a diferencia de `EstimateRange`, usa
`SignedRange` porque un rango de ganancia no tiene piso en cero.

El rango siempre se muestra junto a su advertencia: el peor canal observado ya tiene
audiencia propia, así que un canal nuevo no tiene garantía de alcanzar ni siquiera el
límite inferior. No certifica elegibilidad de monetización ni ingresos de membresías o
Premium. Se muestra en el Home del dashboard, en la tarjeta "Hacia dónde ir ahora".

Pruebas: `tests/test_profit.py` (unidad de `estimate_profit` con datos de mano, estado
incompleto para cada insumo faltante, rango que cruza a pérdida) y una prueba de API end
to end contra datos reales del pipeline sintético.
