# Subnichos en el dashboard y encargos de investigación desde una hipótesis

Fecha: 2026-11-01. Estado: borrador para revisión del propietario. Decisión de origen: el propietario aprobó la opción
completa («lo completo», 2026-11-01) y el diseño del enfoque A; este spec lo concreta con lo aprendido después
(dossier-v3, catálogo de herramientas, régimen y calibración).

## Problema

Los subnichos que se miden y se eligen para pilotos (hipótesis de `niche_hypotheses`, 60 medidas, 9 finalistas) solo se ven por
comandos y markdown. El dashboard solo muestra el backlog de Mercado, y los encargos de investigación de flujo
(`create_request`) solo aceptan un nicho del backlog (`niche_detail`): con una hipótesis responden `404`. Las cuatro
investigaciones de piloto tuvieron que hacerse a mano, fuera del sistema.

## Objetivo

1. Ver en el dashboard las hipótesis con sus mediciones y su estado de investigación.
2. Poder ordenar una investigación de flujo desde una hipótesis, con sus mediciones congeladas como evidencia, y leer
   el dossier (`dossier-v3`) en su ficha.

## Diseño

### 1. Identidad del encargo: sin migración

Un encargo de subnicho usa `niche_label = "subniche:<slug>"` (prefijo reservado). Eso evita colisiones con etiquetas del
backlog, mantiene intactos el índice `uq_flow_research_active (niche_label, format, language)` y las tablas, y no necesita
migración. `format` e `language` salen de la hipótesis (`niche_hypotheses.format` y `.language`); el cliente no los
elige, salvo que el propietario pida otro idioma explícitamente (misma clave del encargo).

El prefijo `subniche:` queda reservado: un `niche_label` del backlog que lo use se rechaza en `create_request`.

### 2. Evidencia congelada

`build_subniche_evidence(hypothesis, snapshot, channels)` (módulo nuevo en `flow_research/`) congela:
- `source: "subniche"`, `slug`, `label`, `family`, `parent_niche_slug`, `language`, `format`, `finalist`, `queries`;
- de la última `hypothesis_snapshots`: `measured_at`, `stable_channels`, `traction_channels`, `median_income_low/high` y
  `profile` (incluye volátiles, grandes, exclusiones por idioma y RPM de origen);
- los canales más relevantes del último `discovery_channel_snapshots` (solo datos vigentes por retención de 30 días;
  los vencidos se omiten y se declara en la evidencia: `channels_available: false`);
- `gate`: anotación de compuertas aplicable (ver §3) y, si hay excepción, `gate_override`.

Elegibilidad: la hipótesis debe estar `active` y tener al menos una medición (`last_measured_at` no nulo); si no,
`ineligible` con mensaje claro. No exige `tentativo` ni los scores de Opportunity/Automatización del backlog.

### 3. Compuertas

- La compuerta de nicho (`niche_reasons`: automatización del backlog y riesgo de política) **no aplica** a subnichos: no
  existe ese score. En la evidencia se anota `automation_known: false` y, como ya hace el sistema, el valor desconocido
  no falla.
- Siguen aplicando, al entregar el dossier, la de **minutos de régimen**, la de **horas de calibración** y la de
  **derechos** (contrato `dossier-v3`), con el tope vigente al enviar y la misma excepción registrada
  (`gate_override`) creada con el encargo.
- La autorización del piloto desde un dossier de subnicho **entra en este spec** (decisión del propietario,
  2026-11-01): ver §7.

### 4. API

- `POST /api/v1/flow-research` acepta `niche_label` con el prefijo `subniche:` (sin campos nuevos): detecta el prefijo,
  arma la evidencia con `build_subniche_evidence` y crea el encargo; `language` y `format` deben coincidir con los de la
  hipótesis.
- Nuevo `GET /api/v1/subniches` (solo lectura, mismo token de servicio): ranking de hipótesis con `slug`, `label`,
  `family`, `status`, `finalist`, mediciones de la última corrida, y el estado de su última investigación de flujo.
- Nuevo `GET /api/v1/subniches/{slug}`: ficha con mediciones, canales relevantes vigentes y la última investigación.

### 5. Dashboard

Página nueva **Subnichos** en el selector lateral (junto a Mercado):
- Tabla con las hipótesis (filtros por familia, estado y finalista), con columnas: ingreso estimado (bajo-alto), tracción,
  estables, grandes, exclusiones por idioma, y estado de la investigación.
- Ficha de la hipótesis seleccionada: mediciones, canales relevantes con enlace (texto plano, nunca Markdown) y botón
  **Iniciar investigación de flujo** (con confirmación del idioma, igual que Mercado). Reutiliza `render_dossier`.
- El dossier `dossier-v3` muestra calibración, régimen y su evidencia (ya implementado en el panel de Mercado).

### 7. Autorización del piloto desde un subnicho

Hoy `pilots.service.authorize` exige el nicho del backlog (`niche_detail`) para armar la evidencia del paquete y pasa
`request["evidence"]["niche"]` a `authorization_reasons`. Cambios:
- **Evidencia del paquete** (`pilot-package-v1`, sin versión nueva): para un encargo con `evidence.source = "subniche"`,
  `_evidence` se arma desde la evidencia congelada, mapeada a la forma existente:
  `scores` todo `null` (no hay score de backlog; no se inventan), `listings_with_income` = 0 (no hay fichas de
  vendedores), `language_mix` = `[{language: <de la hipótesis>, share_pct: 100}]`, `figures` con origen `estimate`
  (`income_estimate_low` y `income_estimate_high` en `usd_per_month`, `traction_channels`, `stable_channels`,
  `large_channels`, `volatile_channels` en `channels`), y `confidence` derivada del tamaño de la muestra
  (`low` si hay menos de 10 canales incluidos; `medium` desde 10; `high` no se usa: no hay verificación independiente).
- **Compuertas al autorizar:** `authorization_reasons(dossier, niche, gates)` recibe `niche = None` para subnichos y
  omite la compuerta de nicho (automatización del backlog y riesgo de política), pero repite minutos de régimen,
  horas de calibración y derechos del dossier guardado. `accept_gate_failure` funciona igual y queda registrado.
- **`niche_label` del piloto:** `subniche:<slug>`; el `pilot_id` se genera con el slug (sin el prefijo) y el panel de
  pilotos muestra la etiqueta de la hipótesis. `niche_mismatch` sigue comprobando `(niche_label, format)` del encargo.
- **Qué NO cambia:** el contrato `pilot-package-v1`, las reglas de parada por defecto y la entrega al canal.
  Un consumidor del paquete ve `scores` nulos y cifras con origen `estimate`: es la forma ya permitida.

### 6. Catálogo de herramientas

El spec no incluye cambios al catálogo (`docs/investigacion-herramientas/`): la skill `flow-research` ya lo cita como
fuente de herramientas por etapa. Mostrar el catálogo en el dashboard queda como seguimiento.

## Fuera de alcance

- Un contrato `pilot-package` nuevo o campos nuevos en él (se reutiliza la forma v1).
- Editar, aprobar o pausar hipótesis desde el dashboard (siguen en `scripts/subniche.py`).
- Cambiar las mediciones o el descubrimiento.
- Mostrar el catálogo de herramientas en el dashboard.

## Compatibilidad y despliegue

- Sin cambios de esquema de base de datos. Cambios en API y dashboard; release nuevo con aprobación del propietario.
- Los encargos y dossiers existentes del backlog no cambian.

## Riesgos y casos a probar

1. Crear un encargo con `subniche:<slug>` de una hipótesis `proposed`, `paused`, `archived` o sin medición: rechazo claro.
2. Hipótesis cuya medición más reciente tiene más de 30 días: la evidencia se crea sin canales y lo declara.
3. Un `niche_label` del backlog que empieza con `subniche:` se rechaza.
4. `language` o `format` distintos de los de la hipótesis: rechazo.
5. Un encargo activo para el mismo `subniche:<slug>`, formato e idioma no se duplica (devuelve el activo).
6. Texto de canales o consultas hostil (`**x**`, HTML, enlaces) se muestra como texto plano.
7. Un dossier entregado para un encargo de subnicho debe corresponder al `niche_label`, `format` y `language` del
   encargo, como hoy.
8. Autorizar un piloto de subnicho: el paquete valida contra `pilot-package-v1` con `scores` nulos, cifras `estimate`
   y `confidence` `low` con menos de 10 canales; autorizar un dossier cuyo régimen o calibración falla las compuertas
   da `gate_failed` y solo pasa con `accept_gate_failure` registrado.
9. Un encargo de subnicho cuya hipótesis ya no está `active` al autorizar: se autoriza igual (la evidencia está
   congelada), pero el paquete indica `measured_at` de la medición usada.

## Decisiones del propietario y supuestos (2026-11-01)

1. **Autorizar el piloto desde un subnicho entra en este spec** (decisión del propietario): ver §7.
2. **La lista de la página Subnichos** muestra por defecto las hipótesis `active` y `proposed`; una casilla «Mostrar
   pausadas y archivadas» las incluye (mismo patrón que «Mostrar descartados» en Mercado). Supuesto de bajo impacto,
   reversible; hoy las 60 están `active`.
