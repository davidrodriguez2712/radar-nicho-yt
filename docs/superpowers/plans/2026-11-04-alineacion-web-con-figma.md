# Alineación de la web móvil con el Figma ordenado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las pantallas ya construidas de la web (Nichos, Subnichos, Hoy, Informe, Autorizar y Panel del piloto) coincidan con el Figma ordenado del 2026-11-04, y que nichos y subnichos compartan el mismo «Recorrido hasta el piloto», la misma forma de «Decisión» y el mismo informe, para que sean comparables.

**Architecture:** Cambios solo en `src/nicheradar/web/` (rutas, vistas puras, plantillas, CSS) más pruebas y documentación. Una pieza compartida nueva (`journey.py` + macro `journey`) calcula los 6 pasos desde datos que la API ya entrega. Una pantalla nueva, el **detalle de nicho** (`/nichos/ver`), reutiliza `GET /market/niches/{label}` que la web ya consume. Ninguna tarea cambia la API, la base de datos ni contenedores.

**Tech Stack:** FastAPI, Jinja2 (autoescape, nunca `|safe`), HTMX vendorizado, httpx `MockTransport` en pruebas, pytest, ruff, mypy. Sin Postgres.

**Spec:** `docs/superpowers/specs/2026-11-03-rediseno-movil-corte3-paridad-design.md` y la auditoría de brechas del 2026-11-04 (resumida abajo). Diseño: Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil»: M2 `19:118`, M19 `47:37` (detalle de nicho), M9 `29:2`, M10 `30:2` (ficha del subnicho), M14 `36:2` (Hoy), M11 `31:2` (informe), M12 `32:2` (autorizar), M13 `35:2` y M6 `20:246` (panel).

## Hallazgos de la auditoría que condicionan el plan

- **No existe ninguna ruta de detalle de nicho.** El detalle sale de `GET /api/v1/market/niches/{label}?format=` (forma: `{niche:{niche_label, format, opportunity{value,...}, automation{value, policy_risk{level}}, confidence, metrics{n_listings, n_income, income_median, multiple_median,...}, rpm_mid, rpm_state, decision{decision,note,decided_at}, trend}, listings[], language_mix[{language, share_pct}], history[]}`; `label` de 1 a 140 caracteres; 404 si no existe). Las etiquetas pueden traer `/` o `other:`: la ruta usa **parámetros de consulta**, como `/nichos/investigar`.
- **El informe y la autorización ya son una sola pantalla para nichos y subnichos** (`routes_reports.py:27`, `routes_pilots.py:189`): M11 y M12 son ajustes de contenido.
- **La API de subnichos no permite aprobar, pausar ni archivar** (eso lo trae el plan `2026-11-04-api-propuestas-de-subnicho.md`): en este plan la tarjeta de decisión del subnicho es de **solo lectura**.
- `trend` del nicho es un número (delta de puntos), no un texto: se traduce a «sube», «baja», «estable» o «sin dato».
- Todas las entradas del «Recorrido» existen en los payloads actuales: decisión y puntajes del nicho, `/flow-research` (investigación), `/subniches` (estado, medición, investigación) y `/pilots` cruzado por `niche_label` y `format` (para un subnicho, `niche_label = "subniche:<slug>"`).

## Global Constraints

- Todo lo de los planes anteriores sigue vigente: cookie firmada, CSRF antes de llamar a la API en todo POST, CSP propia, escape de todo texto de la API, `shape_guard` en los GET (y `SHAPE_ERRORS` a mano en los POST), ids y etiquetas validados antes de usarse, avisos desde claves fijas, números no finitos como «—», fechas sin zona como UTC, tope de 100 elementos con aviso, nada de `|safe`, sin estilos ni scripts en línea, toda clase nueva con regla en `static/css/app.css`.
- **Ninguna acción nueva sin confirmación cuando gasta o cambia estado real.** La decisión del nicho (Sin decidir, Tentativo, Descartado) ya es una acción reversible del propietario y no gasta: se hace con POST y CSRF, sin pantalla de confirmación aparte.
- **Retorno seguro:** el parámetro `volver` de las acciones solo admite rutas internas de una lista blanca (`/nichos`, `/nichos/ver?...`), nunca una URL externa.
- **Solo datos reales de la API.** Lo que el Figma muestra y la API no entrega (cadencia y días de preparación de M12, filtro e idioma por nicho en M2 y Hoy, «Fit») **queda fuera** (ver «Fuera de este plan»).
- Nada se despliega con este plan.

## Rulings de diseño

1. **Regla del Recorrido:** cada paso es `done` (✓), `now` (●) o `pending` (○); `now` es el **primer paso no hecho**; si todos están hechos, el último paso (Piloto) es `now` con el texto «Piloto en marcha» si existe un piloto abierto o «Decide si lo lanzas» si hay informe listo y no hay piloto.
2. **Nicho descartado:** el paso «Decisión» es `now` con el texto «Descartado: se oculta de la lista» y los siguientes `pending`.
3. **Subnicho pausado o archivado:** «Decisión» es `done` con «Pausada» si está pausada (y «Listo para investigar» queda `pending` con «Reanúdala para medirla»), y `now` con «Archivada: se descarta» si está archivada.
4. **Tendencia:** `trend > 0` → «sube», `< 0` → «baja», `== 0` → «estable», nulo o no numérico → «sin dato».
5. **Detalle de nicho:** ruta `GET /nichos/ver?etiqueta=<label>&formato=<long|shorts>`; «Ver más fichas» muestra 10 más por toque sobre las ya cargadas (sin llamada extra); hasta 100 fichas con aviso si el detalle trae más.
6. **Fit:** se quitó del Figma de M2 el 2026-11-04 (no existe para nichos de mercado; el propietario puede revertirlo). Idioma por nicho en lista: fase posterior (el chip y el filtro de idioma siguen en M2 como diseño pendiente).

## Review Focus

1. Etiquetas de nicho hostiles o raras (`other:xyz`, con `/`, `%2F`, `<script>`, 140 caracteres, Unicode): el detalle las escapa, no colisiona con `/nichos/decidir` ni `/nichos/investigar`, y una etiqueta inexistente da 404 en español (Task 2).
2. El Recorrido con datos incompletos o malformados (decisión ausente, puntajes nulos, investigación de otro formato, piloto cerrado, listas truncadas a 100): nunca 500 y el texto dice qué falta (Task 1).
3. El retorno seguro de la decisión: `volver` con `https://…`, `//host`, `javascript:` o `/nichos/../x` se ignora y vuelve a `/nichos` (Task 3).
4. Hoy con menos tarjetas que el máximo, con fuentes caídas y con textos hostiles: títulos dinámicos correctos y degradación por tarjeta (Task 9).
5. El informe y la autorización con evidencia de nicho y de subnicho, dossier antiguo (v1/v2), `calibration` ausente o malformada: sin 500 y con el rótulo de origen correcto (Tasks 6 y 7).

---

### Task 1: Recorrido hasta el piloto (`journey.py` y macro)

**Files:**
- Create: `src/nicheradar/web/journey.py`, `tests/test_web_journey.py`
- Modify: `src/nicheradar/web/templates/components.html` (macro `journey(steps)`), `src/nicheradar/web/static/css/app.css`, `tests/test_web_assets.py` (el recorrido de clases CSS ya cubre `components.html`; confirmar)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Step: state: str  # "done" | "now" | "pending"`, `name: str`, `detail: str`.
  - `niche_journey(niche: object, research: object, pilot: object) -> list[Step]` con `niche` = entrada del backlog o `detail["niche"]`, `research` = el encargo de investigación más reciente del nicho (`{"status","language"}` o `None`), `pilot` = el piloto abierto cruzado por etiqueta y formato (`{"status"}` o `None`).
  - `subniche_journey(item: object, pilot: object, tz: str) -> list[Step]` con `item` = elemento de `GET /subniches` (`status`, `measurement{measured_at}`, `research{status,language}`).
  - Ambas **nunca lanzan** ante datos mal formados: devuelven los 6 pasos con textos de «falta» en lugar de fallar.
  - Los nombres de paso, en orden: «Candidato», «Decisión», «Listo para investigar», «Investigación de flujo», «Informe», «Piloto».
  - Macro `journey(steps)` que pinta una tarjeta «Recorrido hasta el piloto» con una fila por paso: marca `✓` verde, `●` rojo o `○` gris, nombre y detalle.

Textos del Figma (M19 y M10): Nicho: «Viene del scraper de mercado»; «Marcado «Tentativo»»; «Tiene puntajes de Opportunity y de automatización»; «Hecha por Claude Code en {idioma}»; «Dossier listo»; «Decide si lo lanzas». Subnicho: «Propuesta de la hipótesis»; «Aprobada: activa»; «Medido el {dd/mm/aaaa}»; «Falta iniciarla (abajo)»; «Dossier con veredicto, tiempo y presupuesto»; «Autorizas y se produce». Otros estados: ver Rulings 1 a 3 y la tabla de la Task.

Tabla de estados (para nicho; `d` = `niche["decision"]["decision"]`):

| Paso | done | now | pending |
|---|---|---|---|
| Candidato | siempre | — | — |
| Decisión | `d == "tentativo"` | `d` en `nuevo` o ausente: «Marca «Tentativo» para poder investigarlo»; `d == "descartado"`: «Descartado: se oculta de la lista» | — |
| Listo para investigar | `opportunity.value` y `automation.value` no nulos | — | «Necesita puntajes de Opportunity y de automatización (al menos 3 fichas con ingreso)» |
| Investigación de flujo | `research.status == "listo"` | `pendiente`/`en_curso`: «En curso: Claude Code la está haciendo» / «Pendiente: esperando a Claude Code»; `rechazado`: «Rechazada: vuelve a iniciarla» | sin investigación y el paso anterior no está hecho: «Se inicia desde el detalle» |
| Informe | `research.status == "listo"`: «Dossier listo» | — | «Dossier con veredicto, tiempo y presupuesto» |
| Piloto | piloto abierto: `now` «Piloto {estado}» | Ruling 1 | «Autorizas y se produce» |

Para subnicho: «Candidato» siempre; «Decisión» `done` con «Aprobada: activa» si `status == "active"`, «Pausada» si `paused`; `now` «Falta aprobarla» si `proposed`; `now` «Archivada: se descarta» si `archived`; «Listo para investigar» `done` «Medido el {fecha local}» si hay `measurement.measured_at` y `status == "active"`, `pending` «Se mide sola, a más tardar en 3 días» en otro caso; los pasos 4 a 6 como en nicho con `item["research"]`.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_journey.py`, sin API; escribir completas):

```python
from nicheradar.web.journey import Step, niche_journey, subniche_journey


def states(steps: list[Step]) -> list[str]:
    return [s.state for s in steps]


def names(steps: list[Step]) -> list[str]:
    return [s.name for s in steps]


NAMES = ["Candidato", "Decisión", "Listo para investigar", "Investigación de flujo", "Informe", "Piloto"]


def niche(decision: str = "tentativo", opp: float | None = 72, auto: float | None = 64) -> dict:
    return {"decision": {"decision": decision}, "opportunity": {"value": opp}, "automation": {"value": auto}}


def test_a_new_niche_stops_at_the_decision() -> None:
    steps = niche_journey(niche("nuevo"), None, None)
    assert names(steps) == NAMES
    assert states(steps) == ["done", "now", "done", "pending", "pending", "pending"]
    assert "Tentativo" in steps[1].detail


def test_a_tentative_niche_with_scores_waits_for_the_research() -> None:
    steps = niche_journey(niche(), None, None)
    assert states(steps) == ["done", "done", "done", "now", "pending", "pending"]


def test_the_research_in_progress_and_rejected_texts() -> None:
    assert "En curso" in niche_journey(niche(), {"status": "en_curso", "language": "en"}, None)[3].detail
    assert "Pendiente" in niche_journey(niche(), {"status": "pendiente", "language": "en"}, None)[3].detail
    assert "Rechazada" in niche_journey(niche(), {"status": "rechazado", "language": "en"}, None)[3].detail


def test_a_ready_dossier_without_pilot_points_at_the_pilot() -> None:
    steps = niche_journey(niche(), {"status": "listo", "language": "en"}, None)
    assert states(steps) == ["done", "done", "done", "done", "done", "now"]
    assert steps[3].detail == "Hecha por Claude Code en inglés"
    assert steps[5].detail == "Decide si lo lanzas"


def test_an_open_pilot_is_the_current_step() -> None:
    steps = niche_journey(niche(), {"status": "listo", "language": "en"}, {"status": "en_ejecucion"})
    assert states(steps)[-1] == "now" and "en ejecución" in steps[5].detail.lower()


def test_a_discarded_niche_stops_at_the_decision() -> None:
    steps = niche_journey(niche("descartado"), None, None)
    assert states(steps) == ["done", "now", "done", "pending", "pending", "pending"]
    assert "se oculta" in steps[1].detail


def test_a_niche_without_scores_is_not_ready_to_research() -> None:
    steps = niche_journey(niche(opp=None), None, None)
    assert steps[2].state == "pending" and "puntajes" in steps[2].detail


def test_malformed_input_never_raises() -> None:
    for bad in (None, "x", 7, [], {}, {"decision": "x"}, {"opportunity": 5}):
        assert len(niche_journey(bad, bad, bad)) == 6


def sub(status: str = "active", measured: str | None = "2026-10-31T12:00:00+00:00", research: dict | None = None) -> dict:
    return {"status": status, "measurement": {"measured_at": measured} if measured else None, "research": research}


def test_an_approved_measured_subniche_waits_for_the_research() -> None:
    steps = subniche_journey(sub(), None, "America/Lima")
    assert states(steps) == ["done", "done", "done", "now", "pending", "pending"]
    assert steps[1].detail == "Aprobada: activa" and steps[2].detail == "Medido el 31/10/2026"


def test_a_proposed_subniche_waits_for_approval() -> None:
    steps = subniche_journey(sub("proposed", None), None, "UTC")
    assert states(steps) == ["done", "now", "pending", "pending", "pending", "pending"]
    assert steps[1].detail == "Falta aprobarla"


def test_paused_and_archived_subniches() -> None:
    paused = subniche_journey(sub("paused"), None, "UTC")
    assert paused[1].detail == "Pausada" and paused[2].state == "pending"
    archived = subniche_journey(sub("archived"), None, "UTC")
    assert archived[1].state == "now" and "se descarta" in archived[1].detail


def test_subniche_garbage_never_raises() -> None:
    for bad in (None, "x", 7, [], {}, {"status": 5, "measurement": "x", "research": 3}):
        assert len(subniche_journey(bad, bad, "UTC")) == 6
```

  y pruebas de plantilla/macro: la tarjeta pinta «Recorrido hasta el piloto», una fila por paso con `✓`, `●` o `○`, escapa un `detail` hostil y no usa `|safe`.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_journey.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** `journey.py` con funciones puras y defensivas (`isinstance` antes de cada acceso; idioma por nombre: `en` «inglés», `es` «español», `pt` «portugués», `ru` «ruso», `de` «alemán», `fr` «francés», otro valor «su idioma»), el macro y las reglas CSS (`.journey`, `.journey__row`, `.journey__mark--done|now|pending`, `.journey__name`, `.journey__detail`; `done` verde, `now` color primario, `pending` gris; objetivos táctiles no aplican porque no son controles).
- [ ] **Step 4:** `uv run pytest tests/test_web_journey.py tests/test_web_assets.py -q`; ruff; mypy — PASS.
- [ ] **Step 5: Commit** `feat: recorrido hasta el piloto compartido por nichos y subnichos`.

---

### Task 2: Detalle de nicho (M19), solo lectura

**Files:**
- Create: `src/nicheradar/web/niche_detail.py`, `src/nicheradar/web/templates/nichos/detalle.html`, `tests/test_web_niche_detail.py`
- Modify: `src/nicheradar/web/routes_niches.py` (nueva ruta), `src/nicheradar/web/static/css/app.css`, `tests/web_helpers.py` (builder `niche_detail(**over)` con la forma exacta de arriba), `tests/test_web_assets.py` (la carpeta `templates/nichos` ya debe estar en el recorrido de clases CSS; añadirla si falta)

**Interfaces:**
- Consumes: `ApiClient.request`, `render`, `shape_guard`, `current_session`, `journey.niche_journey`, `format.es_int/money_amount/local_datetime`, `research.language_options` (para el texto de idioma), `/flow-research?niche_label=&format=`, `/pilots`.
- Produces:
  - Ruta `GET /nichos/ver?etiqueta=&formato=` (`active_tab="nichos"`); `etiqueta` de 1 a 140 caracteres y `formato` en `long|shorts`; cualquier otra cosa → 404 con `error.html`.
  - `detail_view(detail: object, research: object, pilot: object, tz: str) -> dict` con: `title`, `chips` (formato, decisión, investigación), `journey` (pasos), `scores` (Opportunity, Automatización, Confianza, Riesgo de política, Tendencia con el texto del Ruling 4), `market` (Fichas, Con ingreso, Ingreso mediano «US$ 1.350 al mes», «Precio / ingreso anual» «2,4×», «RPM de referencia» o «sin calibrar» para shorts, «Idioma de las fichas» «Inglés 80 % · Español 15 % · Sin dato 5 %»), `how` (texto fijo con los pesos 30/30/25/15 y 30/25/20/15/10, la nota «Un puntaje necesita al menos 3 fichas con ingreso; sin eso se muestra «sin evidencia».» y, si la API trae `components`, nada más), `listings` (hasta 100, cada una con título, estado «Activa»/«Desapareció», precio, suscriptores declarados y en YouTube, chip de verificación «verificado»/«no coincide»/«canal no encontrado»/«no verificable»/«sin verificar», ingreso y gasto declarados, `url` solo si empieza por `https://`), `listings_total`, `truncated`, `warnings`.
  - Aviso fijo: «Las cifras salen de fichas de canales en venta y las declaran los vendedores: no son ingresos verificados.»
  - Enlace «‹ Nichos» arriba (a `/nichos`), tarjetas «Puntajes», «Investigación de flujo» (estado y enlace «Ver dossier» a `/informes/{id}` cuando está listo, o «Investigar» a `/nichos/investigar?...` cuando es elegible), «Mercado», «Cómo se calculó», «Fichas del nicho (N)» con botón «Ver más fichas» (10 por toque, sin llamada extra) y el Recorrido.

- [ ] **Step 1: Pruebas que fallan** (`tests/test_web_niche_detail.py`, completas): requiere sesión (303 a `/login`); con el detalle del builder renderiza los textos del Figma (puntajes «72», «64», «alta», «bajo», «sube»; «Fichas», «Ingreso mediano», «2,4×», «US$ 3,10»; «Cómo se calculó» con los pesos; la primera ficha con «verificado» y «Ver anuncio»); el Recorrido aparece con los pasos reales; `trend` `5.0`/`-3`/`0`/`None`/`"x"` → «sube»/«baja»/«estable»/«sin dato»/«sin dato»; en shorts el RPM dice «sin calibrar»; etiqueta inexistente (la API da 404) → 404 en español; API caída → 503 «no disponible» y sin traza; `formato` inválido o `etiqueta` de 141 caracteres → 404 sin llamar a la API; etiquetas `other:xyz`, con `/`, con `%2F` y con `<script>` se piden a la API con el parámetro exacto y se escapan al pintar; fichas con `url` que no es `https://` no generan enlace; 101 fichas → 100 mostradas y aviso de tope; formas rotas (`listings` como cadena, `niche` sin `metrics`, números `NaN`/`inf`, fechas sin zona) → 200 o 503 y nunca 500; «Ver más fichas» solo aparece con más de 10 fichas; la ruta no colisiona con `/nichos/decidir` ni `/nichos/investigar` (sus pruebas existentes siguen verdes); las llamadas a `/flow-research` y `/pilots` van con `limit` y su fallo no impide pintar el resto (el Recorrido muestra «No se pudo leer el estado de la investigación»).
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_niche_detail.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** (patrón de `routes_subniches.py`: tres lecturas independientes con `try/except ApiError`, `shape_guard`, `Vary`, `render` sin radar).
- [ ] **Step 4:** pruebas del archivo, `tests/test_web_niches.py`, `tests/test_web_assets.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: detalle de nicho con puntajes, mercado, fichas y recorrido`.

---

### Task 3: Decisión del nicho con nota (M19)

**Files:**
- Modify: `src/nicheradar/web/routes_niches.py` (`POST /nichos/decidir`: campo `nota`, retorno seguro), `src/nicheradar/web/templates/nichos/detalle.html` (tarjeta «Decisión del nicho»), `src/nicheradar/web/niches.py` si el POST existente valida los valores
- Test: `tests/test_web_niche_decision.py` (nuevo); ajustar `tests/test_web_niches.py`

**Interfaces:**
- Consumes: `POST /api/v1/market/niches/{label}/decisions` con cuerpo `{format, decision, note?}` (201).
- Produces: `POST /nichos/decidir` acepta `etiqueta`, `formato`, `decision` (`nuevo|tentativo|descartado`), `nota` (opcional, hasta 1000 caracteres), `volver` y `csrf`; en éxito 303 a `volver` si está en la lista blanca (`/nichos` o `/nichos/ver?etiqueta=…&formato=…&aviso=decidido`) y a `/nichos` en otro caso; tarjeta con tres píldoras (radio) y el texto «Tentativo: lo quieres investigar. Descartado: se oculta de la lista. Solo un nicho tentativo y con puntajes se puede investigar.», campo «Nota (opcional)» («Hasta 1000 caracteres.») prellenado con `niche.decision.note`, botón «Guardar decisión». Avisos fijos: `decidido` «Decisión guardada.», `error` «No se pudo guardar la decisión.».

- [ ] **Step 1: Pruebas que fallan:** sin CSRF → 403 y ninguna llamada a la API; decisión válida con nota → un solo `POST` a la API con `{format, decision, note}` y redirect 303 al detalle con `aviso=decidido`; sin nota → el cuerpo no trae `note`; nota de 1001 caracteres → se re-muestra el detalle con el error «La nota admite hasta 1000 caracteres.» sin llamar a la API y conservando lo escrito; decisión fuera de la lista (`"x"`) → 422/400 sin llamada; `volver` con `https://evil`, `//evil`, `javascript:alert(1)`, `/nichos/../x` y `/pilotos` → redirect a `/nichos` (nunca fuera); `volver` válido a `/nichos` y a `/nichos/ver?...` se respeta; un 404 de la API (nicho inexistente) → mensaje en español; un 409 o 422 → mensaje fijo y 503 sin traza; la API caída → mensaje y sin pérdida de lo escrito; los botones «Marcar tentativo» de la lista siguen funcionando (prueba existente) y siguen volviendo a `/nichos`; la nota hostil se guarda tal cual y se pinta escapada al recargar.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_niche_decision.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar.** La decisión y el formato salen de la lista blanca, no se confía en el formulario para nada más; la nota se recorta de espacios y se rechaza si tiene caracteres de control (misma regla que la nota de pilotos).
- [ ] **Step 4:** pruebas del archivo y `tests/test_web_niches.py tests/test_web_niche_detail.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: decidir un nicho con nota desde su detalle`.

---

### Task 4: Enlaces al detalle y control Nichos | Subnichos con conteos (M2 y M9)

**Files:**
- Modify: `src/nicheradar/web/templates/nichos/_lista.html`, `templates/nichos/lista.html`, `templates/subnichos/lista.html`, `src/nicheradar/web/niches.py`, `src/nicheradar/web/subniches.py`, `src/nicheradar/web/routes_niches.py`, `src/nicheradar/web/routes_subniches.py`, `templates/components.html` (macro `segmented` si hay que pasar los conteos)
- Test: `tests/test_web_niches.py`, `tests/test_web_subniches_list.py`, `tests/test_web_segmented.py` (nuevo)

**Interfaces:**
- Produces: el nombre de cada tarjeta de nicho enlaza a `/nichos/ver?etiqueta=…&formato=…` (la etiqueta y el formato codificados con `urllib.parse.urlencode`); el control muestra «Nichos {n}» y «Subnichos {m}» en las dos listas: en Nichos, `n = total` de `/market/niches` y `m = len(items)` de `GET /subniches` (solo activos y propuestos); en Subnichos, al revés; si la otra fuente falla, ese conteo se omite sin romper la pantalla.

- [ ] **Step 1: Pruebas que fallan:** el enlace del nombre lleva la etiqueta y el formato codificados (etiqueta con `/`, `&`, `other:x` y `<script>` no rompen el HTML ni el enlace); ambos conteos aparecen («Nichos 6», «Subnichos 60»); con `/subniches` caído la lista de nichos sigue y solo omite el conteo; con `/market/niches` caído la de subnichos igual; el fragmento htmx conserva los conteos; los botones existentes no cambian.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_segmented.py -q 2>&1 | tail -6`.
- [ ] **Step 3: Implementar** (una lectura extra por pantalla, con timeout corto y degradación local).
- [ ] **Step 4:** pruebas de los tres archivos, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: enlace al detalle de nicho y conteos en el control Nichos | Subnichos`.

---

### Task 5: Ficha del subnicho con recorrido y «Ver dossier» (M10 y M9)

**Files:**
- Modify: `src/nicheradar/web/subniches.py` (`detail_view`, botón de la tarjeta con dossier listo, quitar la nota «El informe móvil llega en el siguiente corte»), `src/nicheradar/web/routes_subniches.py` (leer `/pilots` para el Recorrido), `src/nicheradar/web/templates/subnichos/ficha.html`, `templates/subnichos/_lista.html`
- Test: `tests/test_web_subniche_card.py`, `tests/test_web_subniches_list.py`

**Interfaces:**
- Consumes: `journey.subniche_journey`, `GET /pilots?limit=100` (cruce por `niche_label == "subniche:<slug>"` y `format`).
- Produces: la ficha muestra el Recorrido tras los chips de cabecera; la tarjeta «Decisión de la hipótesis» **de solo lectura** con cuatro píldoras (Propuesta, Activa, Pausada, Archivada) con la actual marcada y sin botones, más el texto del Figma («Activa: se mide sola y se puede investigar. Pausada: deja de medirse. Archivada: se descarta. Solo una hipótesis activa y con al menos una medición se puede investigar.») y la nota «Aprobar, pausar o archivar se hará desde aquí cuando esté disponible.» **(esa nota se retira cuando llegue la API de ciclo de vida)**; con investigación lista, la tarjeta «Investigación de flujo» muestra «Ver dossier» (a `/informes/{research.id}`) en lugar de la nota obsoleta; en la lista, con dossier listo el botón dice «Ver dossier» y enlaza al informe; el enlace «← Volver a Subnichos» del pie se quita (la barra superior lo cubre).

- [ ] **Step 1: Pruebas que fallan:** la ficha muestra el Recorrido con los estados del subnicho de la prueba (aprobado y medido → «Aprobada: activa», «Medido el 31/10/2026», investigación `now`); el piloto abierto cruzado cambia el último paso; las píldoras de solo lectura marcan el estado y no existen botones de cambio; con dossier listo aparece «Ver dossier» con el `href` correcto (id validado como UUID antes de usarlo) y desaparece la nota obsoleta; la lista muestra «Ver dossier» solo con dossier listo; `/pilots` caído → el Recorrido dice «No se pudo leer el estado del piloto» y el resto se pinta; formas rotas → 200 o 503 sin 500; textos hostiles escapados.
- [ ] **Step 2: Ejecutar y verificar que fallan:** `uv run pytest tests/test_web_subniche_card.py tests/test_web_subniches_list.py -q 2>&1 | tail -8`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4:** pruebas de esos archivos y `tests/test_web_journey.py`, ruff, mypy — PASS.
- [ ] **Step 5: Commit** `feat: ficha del subnicho con recorrido, decisión visible y enlace al dossier`.

---

### Task 6: Informe alineado (M11)

**Files:**
- Modify: `src/nicheradar/web/report.py`, `src/nicheradar/web/templates/informes/informe.html`, `_resumen.html`, `estado.html`, `static/css/app.css`
- Test: `tests/test_web_report.py`

**Interfaces:**
- Produces: título con el nombre real de la hipótesis cuando es subnicho (si el informe no lo trae, se conserva `subject_label`); «Qué tan firme es» con «{N} canales medidos el {fecha}» cuando la evidencia trae `measurement.included` (verificar el nombre del campo en `report.py` antes de usarlo; si no existe, omitir la línea sin inventar); rótulos alineados con el Figma («Tu tiempo por video», «Total de los {N} videos», «Preparación del canal (una vez)», «Horas de calibración», «Cuando ya está en marcha (régimen)»); barras de dos filas (calibración y régimen) por paso (Guion, Voz, Visuales, Edición, Publicación) hechas con CSS (`<div>` con ancho en `%` mediante clases `bar--p0` a `bar--p100` de 5 en 5, **sin estilos en línea**), a la misma escala, con la leyenda «mismos colores en las dos barras, a la misma escala»; para subnicho, el enlace de vuelta de `estado.html` va a `/subnichos` en lugar de «Volver a Nichos»; «Descartar» sigue oculto para subnicho (la API aún no puede archivar).

- [ ] **Step 1: Pruebas que fallan:** informe de nicho y de subnicho con dossier v3: rótulos nuevos presentes; las barras tienen las 5 etapas y los mismos colores, y la escala común (la fila más larga ocupa 100 %); minutos nulos o negativos → barra vacía y texto «sin dato»; `calibration` ausente (dossier v1/v2) → no aparecen las barras ni «Cuando pasas a régimen» y sí el aviso existente de dossier antiguo; `calibration` malformada → 200 sin barras; el enlace de vuelta depende del origen; el título de subnicho usa el nombre real si está y el slug capitalizado si no; sin `<style` ni `style=` en el HTML (prueba existente); texto hostil escapado.
- [ ] **Step 2–5:** ejecutar `uv run pytest tests/test_web_report.py -q` (falla), implementar, volver a ejecutar más `tests/test_web_assets.py`, ruff, mypy. **Commit** `feat: informe con barras por paso y rótulos alineados para nichos y subnichos`.

---

### Task 7: Autorizar piloto alineado (M12)

**Files:**
- Modify: `src/nicheradar/web/routes_pilots.py` (`_subniche_block`, bloque de evidencia), `src/nicheradar/web/templates/pilotos/autorizar.html`, `src/nicheradar/web/pilots_form.py` si hace falta
- Test: `tests/test_web_pilot_authorize.py`

**Interfaces:**
- Produces: tarjeta «Nicho» con «{nombre} · Subnicho · Largo» (o «· Nicho · Largo»); tarjeta única **«Evidencia»** con una rama por origen (nicho: «vienen las fichas verificadas, y se aplican las compuertas de Opportunity y de automatización, además de las de tiempo y derechos»; subnicho: «viene de la medición de YouTube del {fecha} … no hay puntajes, así que esa compuerta no aplica (sí las de tiempo y derechos)»); los rótulos de «Tu tiempo» alineados con el informe (Task 6); las **reglas de parada por defecto del formato** como texto («Retención ≥ 18 % en 3 de los primeros 10 videos: se compara sola», «Exploración ≥ 30 % al video 20: se compara sola», «Ingresos ≥ costos al mes 6: la juzgas tú») **solo si** el formato es el de esas reglas (verificar `default_stop_rules` en `pilots/service.py`; si difieren, mostrar el texto fijo genérico existente) y la receta por defecto visible (`faceless-storytelling@0.1.0`, «Experimental: sin evidencia de rendimiento todavía.») **solo como lectura**: el formulario no envía receta ni reglas nuevas, no cambia lo que se autoriza. **Cadencia y días de preparación no se incluyen** (la API no los soporta).

- [ ] **Step 1: Pruebas que fallan:** autorizar desde un informe de nicho y desde uno de subnicho: la tarjeta «Evidencia» correcta en cada caso y la marca «Subnicho» solo en el segundo; los rótulos de tiempo alineados; reglas y receta visibles como lectura y **ausentes del cuerpo** del POST (comparar el cuerpo enviado a la API con el de antes: no cambia); la autorización sigue exigiendo CSRF, canal y compuertas como hoy (pruebas existentes); informe con dossier v1/v2 → sin bloque de tiempo, sin 500; texto hostil escapado.
- [ ] **Step 2–5:** ejecutar `uv run pytest tests/test_web_pilot_authorize.py -q` (falla), implementar, volver a ejecutar, ruff, mypy. **Commit** `feat: autorizar piloto con evidencia unificada y reglas visibles`.

---

### Task 8: Panel del piloto alineado (M13 y M6)

**Files:**
- Modify: `src/nicheradar/web/pilot_panel.py` (orden de pestañas y línea de estados), `src/nicheradar/web/routes_pilot_panel.py`, `src/nicheradar/web/templates/pilotos/panel.html`, `_resumen.html`
- Test: `tests/test_web_pilot_panel.py`, `tests/test_web_calibration.py`

**Interfaces:**
- Produces: orden de pestañas Resumen, Preparación, **Calibración**, Videos, Reglas, Historial (Calibración solo con dossier v3 legible, como hoy); línea de estados de calibración para pilotos con calibración legible: «autorizado · entregado · preparado · en calibración · pasa a régimen · decisión pendiente» (derivada del estado de la API y de `passes` de `calibration.view`; nunca inventa un estado que la API no tenga: si la calibración no se puede leer se usa la línea actual); el Resumen de un piloto en calibración muestra «Día N desde el primer video · X de Y videos de calibración publicados» y la tarjeta compacta «Calibración: tu tiempo por video» (reutiliza `calibration.view`, con el rótulo de «mínimo estimado» y la racha «posible» ya implementados); las reglas de parada del Resumen muestran las tres con su avance («1 de 3 medidos») cuando `evaluation.rules` lo trae.

- [ ] **Step 1: Pruebas que fallan:** orden de pestañas con y sin calibración; la línea de calibración solo con calibración legible y la línea normal en otro caso; el Resumen en calibración muestra «Día 9 desde el primer video» y el recuento de videos publicados; con dossier ausente, caído o malformado el Resumen sigue (sin 500) y dice «No se pudo leer el informe de calibración»; las lecturas extra (dossier y videos) se piden solo si el piloto tiene calibración posible y su fallo no impide el resto; las reglas con avance; texto hostil escapado.
- [ ] **Step 2–5:** `uv run pytest tests/test_web_pilot_panel.py tests/test_web_calibration.py -q` (falla), implementar, volver a ejecutar, ruff, mypy. **Commit** `feat: panel del piloto con calibración en el resumen y pestañas en el orden del diseño`.

---

### Task 9: Hoy alineado (M14)

**Files:**
- Modify: `src/nicheradar/web/today.py` (`SHOWN`, títulos dinámicos, tarjetas), `src/nicheradar/web/routes_today.py`, `src/nicheradar/web/templates/hoy.html`
- Test: `tests/test_web_today.py`

**Interfaces:**
- Produces: **una** sección de pendientes «{N} cosas necesitan algo de ti» que fusiona los pilotos que necesitan algo y los informes listos (cada fila con su chip: «listo para decidir», «antes de producir», …) y el enlace «Ver pendientes» a `/pilotos`; calibración con chip «En calibración», «Video N de M · último video X min», la racha ya rotulada y el botón «Ver piloto»; «**{n} nichos que merecen tu atención**» y «**{m} subnichos que merecen tu atención**» con título dinámico (singular y plural correctos; corrige el «3» fijo) y 2 tarjetas de cada tipo como máximo; tarjeta de nicho con chips de formato, puntajes («Opportunity 78 · Automatización 64 · Confianza media») y botones «Marcar tentativo» (el POST existente, con retorno a Hoy en la lista blanca) y «Ver nicho» (al detalle); tarjeta de subnicho con chips (Finalista, familia, idioma), «Ingreso típico por canal al mes», Despegaron/Constantes/Grandes y botones «Investigar» (cuando aplica) y «Ver subnicho». El modelo ya trae `button_label` y `href`: la plantilla los dibuja.

- [ ] **Step 1: Pruebas que fallan:** títulos con 0, 1 y 2 elementos (singular, plural, y la sección oculta con 0); la sección de pendientes fusionada con los chips y el total correcto; calibración con «Video N de M» y «Ver piloto»; las tarjetas de nicho con «Marcar tentativo» y «Ver nicho» (el enlace al detalle con la etiqueta codificada); las de subnicho con sus botones; una fuente caída degrada solo su sección; más de 100 pilotos o informes → aviso existente de «registros más antiguos»; textos hostiles escapados; «Marcar tentativo» desde Hoy vuelve a Hoy y no a `/nichos`; el tope de lecturas de calibración (máximo 5 pilotos) sigue.
- [ ] **Step 2–5:** `uv run pytest tests/test_web_today.py -q` (falla), implementar, volver a ejecutar más `tests/test_web_assets.py`, ruff, mypy. **Commit** `feat: Hoy con pendientes fusionados, títulos dinámicos y tarjetas con acciones`.

---

### Task 10: Integración, capturas y documentación

**Files:**
- Modify: `tests/test_web_smoke_screens.py` (añadir `/nichos/ver?...` a `ROUTES`, `RESOURCES` si hace falta y los POST nuevos a `POSTS`), `scripts/web_preview.py`, `scripts/web_preview_data.py` (detalle de nicho y datos del Recorrido), `tests/test_web_preview.py`, `docs/web-movil.md`

- [ ] **Step 1:** Extender la prueba de humo con el detalle de nicho (texto hostil recursivo, API caída, formas mal hechas, fechas sin zona, `NaN` crudo, CSP y sin recursos externos) y con el POST de decisión (sin CSRF → 302/303/400/403 y ninguna escritura). Cada fallo es un defecto real: se corrige con su prueba (RED primero); no se debilita nada.
- [ ] **Step 2:** Datos y páginas de vista previa (`"nicho_detalle"`, y el Recorrido en la ficha); mirar cada PNG y listar defectos visibles (texto cortado, solapes, objetivos táctiles menores de 44 px, comparar con M19, M10, M14, M11, M12 y M13 en Figma); corregir los obvios.
- [ ] **Step 3:** `docs/web-movil.md`: el detalle de nicho, el Recorrido (con la regla de los pasos), la decisión, el control con conteos, el informe y la autorización unificados, el panel y Hoy; y la lista de lo que el diseño tiene y la web aún no (cadencia, preparación, idioma por nicho, «Fit», decisión de subnicho editable).
- [ ] **Step 4: Validación completa:** `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin PATH="$PWD/.venv/bin:$PATH" uv run pytest -q` (en primer plano, unos 400 s) — todo en verde.
- [ ] **Step 5: Commit** `docs: capturas, prueba de humo y documentación de la alineación`.

---

## Fuera de este plan

- **Decisión del subnicho editable** (aprobar, pausar, reanudar, archivar) y **«+ Proponer subnicho»**: dependen del plan de API `2026-11-04-api-propuestas-de-subnicho.md`; entran en el plan web de Proponer y Compartir.
- **Idioma por nicho** (chip «EN 80 %» y filtro «Idioma» en M2 y Hoy): exige ampliar `GET /market/niches` con un resumen de `language_mix`; fase posterior.
- **«Fit» de M2:** no existe para nichos de mercado; se quita del diseño (recomendado) o se define aparte.
- **Cadencia y días de preparación de M12:** no existen en el contrato de pilotos; cambiarlo es un corte propio (el contrato es inmutable tras autorizar).
- **Presupuesto «por suscripción / por API» de M12:** el dossier trae bajo, probable y alto; se conserva la presentación actual.
- Acciones por bloqueo del panel («Renovar paso a paso», «Revisar tabla») sin destino definido; diferencias finas de M7 (chips de responsable) y M8 (conteos de fichas): opcionales.
- Desplegar nada.

## Self-Review

- **Cobertura de la auditoría:** paquetes 1 a 10 mapeados a las Tasks 1 a 9 (recorrido, detalle, decisión, enlaces y conteos, ficha, informe, autorizar, panel, Hoy) y la Task 10 de integración; los paquetes 11 a 13 quedan en «Fuera de este plan» con su razón.
- **Marcadores de relleno:** ninguno en los textos y reglas; los casos de prueba están enumerados con sus resultados; los puntos que dependen de un campo por verificar (`measurement.included`, `default_stop_rules`) dicen cómo comportarse si no existe, sin inventar cifras.
- **Consistencia de tipos:** `Step`, `niche_journey`, `subniche_journey`, el macro `journey` y `detail_view` se nombran igual en las tareas que los consumen (Tasks 2, 5 y 9).
- **Review Focus:** 1 en Task 2; 2 en Task 1; 3 en Task 3; 4 en Task 9; 5 en Tasks 6 y 7.
