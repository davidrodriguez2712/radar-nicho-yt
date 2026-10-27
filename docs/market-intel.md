# Inteligencia de mercado: backlog de nichos desde marketplaces de canales

Paso previo a la inspección por URL o canal. Un proceso diario recorre las fichas de canales
de YouTube en venta de DealBaron, las clasifica en la taxonomía de nichos del radar y arma un
backlog de nichos ordenado por **Opportunity Score**, con **Automation Score**, riesgo de
política y confianza por separado. Diseño: `docs/superpowers/specs/2026-10-19-market-intel-backlog-design.md`.

## Qué es y qué no es

- Es evidencia **autodeclarada por vendedores**: precio, suscriptores, ingreso y gasto
  mensual. Nada de eso es un ingreso verificado. Cada cifra se guarda como `seller_declared`.
- No gasta créditos de vidIQ, no crea canales y no elige oportunidades. Un nicho `tentativo`
  es una nota del propietario, no una decisión automática.
- Una ficha que desaparece puede haberse vendido o retirado: el sitio solo muestra las
  activas. Por eso la señal de dinámica es débil (pesa 15 de 100).

## Cómo funciona

```text
recorrido completo de /youtube?created_at=0&page=N   (~169 páginas, ~5.400 fichas, 1 petición/s)
  → upsert de fichas y observación diaria
  → detalle de las nuevas o con cambio de precio, con tope por corrida (prioriza las que declaran ingreso)
  → reconcile: tras 2 recorridos completos sin ver una ficha pasa a `disappeared`
  → clasificación con LLM acotado: nicho (lista cerrada de 218), formato, idioma, rasgos de automatización
  → verificación de suscriptores contra YouTube (solo las de mayor ingreso, TTL de 30 días)
  → snapshot diario de agregados por nicho
```

Cada corrida es una fila de `market_scrape_runs` con lease, etapa y checkpoints; una caída
del proceso se reanuda en la etapa guardada (hasta 3 intentos). Un fallo transitorio de la
fuente deja el día en `failed` y se reintenta al día siguiente. Un 403/429 persistente deja la
corrida en `blocked` y **pausa el scraper**.

## Scores (todos calculados al vuelo; versiones `opp-v1` y `auto-v1`)

**Opportunity (0-100)** por nicho y formato, ventana de 90 días:

| Bloque | Peso | Cálculo |
|---|---|---|
| Rentabilidad | 30 | 70 % ingreso mediano (escala log, US$50 → 0, US$3.000 → 100) + 30 % margen mediano |
| Eficiencia | 30 | media de: ingreso por 1.000 suscriptores (log, 0,5 → 0, 50 → 100) y RPM de referencia del nicho (1 → 0, 12 → 100; **solo long**) |
| Validación | 25 | 60 % precio / ingreso anual (0,5 años → 0, 2,5 años → 100) + 40 % nº de fichas (10 o más → 100) |
| Dinámica | 15 | tasa de desaparición (30 % o más → 100) |

- Solo cuentan fichas con **ingreso declarado > 0** (`$0` significa "no informado"), sin
  `mismatch`/`not_found` en la verificación y sin atípicos (MAD, modificado z > 3,5).
- Con menos de 3 fichas válidas el nicho es `insufficient_evidence` y se ordena después de los
  demás. Los bloques sin dato se omiten y el resto se reponderan.
- **Confianza** (`alta` ≥ 0,7, `media` ≥ 0,4, `baja`): 50 % nº de fichas válidas (10 = completo),
  30 % proporción verificada, 20 % fichas vistas en los últimos 14 días.

**Automation (0-100)**: rasgos 0-2 etiquetados por el LLM y combinados con pesos
`faceless 30`, `scriptable 25`, `visuals_automatable 20`, `synthetic_voice_ok 15`,
`low_copyright_dependence 10`; un rasgo `null` se completa con el prior del nicho
(`niche_automation_priors`). Se necesitan al menos 3 rasgos. `policy_risk` se muestra aparte
(`bajo` < 0,67 ≤ `medio` < 1,34 ≤ `alto`) y nunca se resta.

**Los scores siguen siendo solo un orden**: no bloquean nada. Lo que frena el flujo son las
[compuertas de selección](flow-research.md#compuertas-de-selección-2026-10-26) de la investigación de
flujo, que leen estos scores sin cambiarlos (automatización mínima, riesgo de política alto, minutos
humanos por video y derechos).

Long y Shorts se puntúan por separado. Shorts no tiene benchmark de RPM (`uncalibrated`).

## Operación

- **Pausa propia**: tabla `market_intel_schedule` (nace pausada). Se controla desde
  Dashboard → Operación → "Operación del scraper de mercado" o con `PUT /api/v1/market/schedule`.
  Es independiente de `NR_RADAR_PAUSED`: reanudar uno nunca reanuda ni pausa al otro.
- **Compuerta live**: en `NR_MODE=live` el scraper no corre ni se reanuda hasta que el
  propietario revise los Términos de Servicio de la fuente y ponga
  `NR_MARKET_INTEL_LIVE_ENABLED=true`.
- **Backfill**: la primera semana el detalle y la clasificación van por lotes
  (`NR_MARKET_INTEL_DETAIL_CAP_PER_RUN`, `..._CLASSIFY_CAP_PER_RUN`). Con los valores por
  defecto (300 y 100) las ~5.400 fichas tardan semanas en clasificarse; subir el tope de
  clasificación sube el gasto del LLM y sale del mismo tope USD semanal que el resto.
- **API**: `GET /api/v1/market/niches`, `/niches/{label}?format=`, `/listings`, `/runs`,
  `/schedule`; `POST /niches/{label}/decisions`.
- **Modo sintético** (arranque local): la fuente sirve HTML de fixtures en el propio proceso y
  la clasificación usa un mapa categoría → nicho marcado `synthetic_category_map`.

## Datos y retención

Fichas, observaciones, clasificaciones, verificaciones y snapshots se conservan **183 días**
(`retain_until`); `expire()` los purga y las observaciones, clasificaciones y verificaciones
caen en cascada con su ficha. Las decisiones del propietario no caducan. Estos datos **sí
entran en el respaldo cifrado del Mac** (decisión 9.4, opción A), con una copia que se destruye
al vencer su dato más próximo; ver [backup-restore.md](backup-restore.md).

## Límites conocidos

- Datos autodeclarados y de calidad dispar: la verificación cubre solo los suscriptores.
- Una sola fuente en el v1 (el contrato `ListingSource` deja lista la puerta a otras).
- El HTML de DealBaron puede cambiar: el parser falla con `layout_changed` y la corrida queda
  `failed`, sin escribir datos a medias.
- La construcción real del `Gateway` de YouTube solo se ejerce en el piloto live.
- El tick del scraper corre en el mismo proceso que el worker del radar: un recorrido largo
  retrasa el siguiente tick del radar (hoy en pausa).
