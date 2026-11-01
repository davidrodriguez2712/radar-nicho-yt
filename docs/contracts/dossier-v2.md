# dossier-v2

> **Legado:** `dossier-v2` solo se conserva para leer dossiers guardados. Los encargos nuevos usan
> [`dossier-v3`](dossier-v3.md).

Estado: **implementado en la rama `feat/niche-gates-dossier-v2`, sin desplegar** (2026-10-26).
Dirección: **investigador (Claude Code) → NicheRadar**. Contexto operativo y compuertas:
[`../flow-research.md`](../flow-research.md). Código: `src/nicheradar/flow_research/contracts.py`,
`gates.py` y `service.py`.

## Qué es y por qué existe

El resultado estructurado de una investigación de flujo. `dossier-v2` conserva todo `dossier-v1`
(competencia, flujo de producción, hoja de ruta, presupuesto, herramientas, mapa de automatización,
riesgo de política, punto de equilibrio, fuentes) y añade dos secciones **obligatorias**, pedidas por
el propietario el 2026-10-26 para que ningún nicho avance sin saber (1) si el material visual y de
audio se puede usar y (2) cómo se automatizaría cada etapa del canal.

| Versión | Estado |
|---|---|
| `dossier-v1` | **Histórico, solo lectura.** Existe para leer dossiers guardados antes del 2026-10-26. Un encargo nuevo que lo envíe recibe `422` («dossier-v1 ya no se acepta en encargos nuevos: usa dossier-v2») |
| `dossier-v2` | **Legado, solo lectura.** Vigente hasta dossier-v3; `schema_version` es `"dossier-v2"` |

Un dossier `dossier-v1` guardado se muestra en el panel con un aviso y falla la compuerta de derechos
al autorizar un piloto, salvo `accept_gate_failure`. No se migra ni se reescribe: el dossier es
inmutable.

## Convenciones

Las de `dossier-v1`: JSON UTF-8, **claves desconocidas rechazadas** (sin repetirlas en el mensaje),
fechas ISO 8601 con zona, dinero en USD, URLs `https`, errores sin repetir valores enviados,
máximo 50 problemas por respuesta.

## Campos nuevos

### `rights`

| Campo | Tipo | Reglas |
|---|---|---|
| `verdict` | texto | `"cleared"`, `"conditional"` o `"blocked"` |
| `summary` | texto | 1 a 1500 caracteres |
| `materials` | lista (1 a 20) | Un elemento por tipo de material. Debe haber al menos uno `visual` y uno `audio` o `voice` |
| `conditions` | lista (0 a 20) | Obligatoria y no vacía si `verdict = "conditional"` |

`materials[]`:

| Campo | Tipo | Reglas |
|---|---|---|
| `kind` | texto | `"visual"`, `"audio"`, `"voice"` o `"text"` |
| `description` | texto | Qué material es |
| `origin` | texto | `own_capture`, `own_generation`, `licensed`, `platform_policy`, `public_domain`, `third_party` o `unknown` |
| `license_or_policy` | texto | La licencia o la política del editor que lo cubre, en palabras |
| `source_id` | texto o `null` | **Obligatoria** si `origin` es `licensed`, `platform_policy`, `public_domain` o `third_party`: apunta a `sources` (que ya lleva URL y `accessed_on`) |
| `requires_permission` | booleano | `true` si hay que pedir permiso a alguien |
| `permission_plan` | texto o `null` | Obligatoria si `requires_permission` es `true` |

Reglas de coherencia:

- `cleared` no admite ningún material con `requires_permission = true` ni con `origin` `third_party` o
  `unknown`.
- `conditional` exige `conditions`.
- `blocked` exige `verdict.recommendation = "no_go"`. **No se puede forzar con una excepción.**
- Toda `source_id` citada existe en `sources`.

### `automation_plan`

| Campo | Tipo | Reglas |
|---|---|---|
| `summary` | texto | **120 a 1500 caracteres**: la visión global, no una lista |
| `stages` | lista (3 a 15) | Una etapa por **cada** paso de `production_flow` (mismo nombre) |
| `milestones` | lista (2 a 20) | El orden de implementación |

`stages[]`:

| Campo | Tipo | Reglas |
|---|---|---|
| `step` | texto | Nombre de un paso de `production_flow`; uno por paso, sin repetir |
| `mode` | texto | `manual`, `semi` o `auto`. Igual al `automation` del mismo paso de `production_flow` |
| `approach` | texto | **120 a 1500 caracteres.** Cómo se automatiza la etapa: qué hace qué, con qué herramienta o API, cómo se conecta con la anterior y la siguiente |
| `tools` | lista (0 a 8) | `{name, interface, cost_usd_per_video}`; `name` existe en `tools` del dossier |
| `inputs`, `outputs` | texto | Qué entra y qué sale |
| `quality_gate` | texto | Qué se mide para pasar o no a la etapa siguiente |
| `failure_mode`, `retry_policy` | texto | Cómo falla y cómo se reintenta |
| `human_minutes_per_video` | entero | Igual al del mismo paso de `production_flow` |
| `stays_human` | texto o `null` | Obligatorio si `human_minutes_per_video` > 0: qué sigue siendo humano y por qué |

`milestones[]`: `order` (1..n sin saltos), `name`, `description` (120 a 1500 caracteres),
`acceptance_criteria` (1 a 10) y `depends_on` (solo órdenes anteriores que existan).

### Minutos humanos por video: se derivan, no se declaran

No hay un campo con el total. Se **calcula** como la suma de `production_flow[].human_minutes_per_video`
(`DossierV2.human_minutes_per_video`). Las etapas de `automation_plan` deben coincidir paso a paso con
`production_flow`, de modo que una cifra optimista en un solo lado no pasa la validación.

## Compuertas que valida el servicio

Además del contrato, el servicio compara el dossier con los umbrales vigentes
(`NR_GATE_MIN_AUTOMATION` = 90, `NR_GATE_MAX_HUMAN_MINUTES` = 60, `NR_GATE_BLOCK_HIGH_POLICY_RISK` =
`true`; **supuestos iniciales, no medidos**). Un dossier con `recommendation` `go` o
`go_with_conditions` se rechaza (`422`, ruta `verdict.recommendation`) si:

1. `rights.verdict` es `blocked` (en el contrato; no admite excepción), o
2. los minutos humanos por video superan el máximo, o
3. la automatización conocida del nicho es menor que el mínimo, o su riesgo de política es alto,

y en los casos 2 y 3 el encargo **no** tiene `evidence.gate_override`. `no_go` siempre se acepta.
Al autorizar el piloto se repiten las comprobaciones (`gate_failed`); ver
[`pilot-package-v1.md`](pilot-package-v1.md).

## Qué NO garantiza

Que los derechos sean ciertos: solo que cada afirmación está citada, fechada y es coherente con el
resto del dossier. Las políticas de los editores cambian y las páginas se leyeron con búsqueda web;
no es asesoría legal. El plan de automatización es una propuesta verificada contra documentación
pública, no una prueba de que el pipeline funcione.

## Ejemplo mínimo de las secciones nuevas

```json
{
  "schema_version": "dossier-v2",
  "rights": {
    "verdict": "conditional",
    "summary": "Capturas propias de juegos cuyo editor permite monetizar.",
    "materials": [
      {"kind": "visual", "description": "Capturas propias de gameplay",
       "origin": "platform_policy",
       "license_or_policy": "El editor permite videos monetizados con su contenido",
       "source_id": "s4", "requires_permission": false},
      {"kind": "voice", "description": "Narración sintética", "origin": "licensed",
       "license_or_policy": "El plan incluye licencia comercial", "source_id": "s2",
       "requires_permission": false},
      {"kind": "audio", "description": "Música de la biblioteca de YouTube",
       "origin": "platform_policy", "license_or_policy": "Uso libre en YouTube",
       "source_id": "s3", "requires_permission": false}
    ],
    "conditions": ["Solo juegos de la lista blanca de editores con política explícita"]
  },
  "automation_plan": {
    "summary": "…(120 caracteres o más)…",
    "stages": [
      {"step": "Guion", "mode": "semi", "approach": "…(120 caracteres o más)…",
       "tools": [{"name": "Asistente de IA", "interface": "API", "cost_usd_per_video": 0.5}],
       "inputs": "Ficha de datos con fuentes", "outputs": "Guion aprobado",
       "quality_gate": "Cada cifra tiene fuente", "failure_mode": "Cifra inventada",
       "retry_policy": "Regenerar con la ficha corregida, máximo 2 veces",
       "human_minutes_per_video": 20, "stays_human": "Verificar hechos y escribir el análisis"}
    ],
    "milestones": [
      {"order": 1, "name": "Guion y voz automatizados", "description": "…(120 caracteres o más)…",
       "acceptance_criteria": ["Un video de prueba sin edición manual de la voz"],
       "depends_on": []}
    ]
  }
}
```

(Ejemplo recortado: un dossier real incluye todas las secciones de `dossier-v1`, una etapa por cada
paso de `production_flow` y al menos 2 hitos.)
