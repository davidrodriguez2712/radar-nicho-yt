# Rediseño móvil, corte 1 (resto): Nichos, investigación, informe, autorizar piloto y Hoy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar el corte 1 del rediseño: las pantallas M2 (Nichos), M8 (iniciar investigación), M3/M11 (informe), M4/M12 (autorizar piloto) y M1/M14 (Hoy) sobre la web `nicheradar.web` ya fusionada, con datos reales de la API privada.

**Architecture:** Cada pantalla sigue el patrón ya probado en M9/M10: una ruta FastAPI delgada (sesión + CSRF) que pide datos a `ApiClient`, un módulo de modelo de vista que convierte la respuesta de la API en lo que muestra la plantilla (con textos en español y sin inventar cifras), y plantillas Jinja2 con autoescape que reutilizan las macros de `components.html`. Ningún cambio de API ni de base de datos.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, HTMX 2.0.4 (ya incluido), httpx (`MockTransport` en pruebas), pytest, ruff, mypy, Chrome sin interfaz para las capturas.

**Spec:** `docs/superpowers/specs/2026-11-02-rediseno-movil-web-design.md` (sección 5, «Corte 1»). Plan anterior (ya fusionado): `docs/superpowers/plans/2026-11-02-rediseno-movil-cimientos-subnichos.md`. Diseño: Figma `JmBvlfNURrV226WOZLuCEz`, página «M · Móvil»: M1 `19:3`, M2 `19:118`, M3 `19:305`, M4 `20:2`, M8 `23:32`, M11 `31:2`, M12 `32:2`, M14 `36:2` (el implementador puede pedir una captura con `get_screenshot`, pero no es obligatorio: los textos están en este plan).

## Código que ya existe y se reutiliza (no reescribir)

- `src/nicheradar/web/app.py` (`create_app(config, *, transport, clock)`, `app.state.{config,api,signer,limiter,templates,clock,radar_cache}`), `deps.py` (`current_session`, `render(request, name, context, *, status_code, session, with_radar)`, `safe_next`, `radar_state`), `client.py` (`ApiClient.request(method, path, *, params, body, timeout)` → `dict`; `ApiError(kind, status, detail)` con `.message`; tipos `not_configured|unavailable|unauthorized|not_found|conflict|invalid|error`), `security.py` (`SessionSigner.csrf/csrf_valid`), `format.py` (`es_int`, `usd_range`, `compact`, `local_datetime`), `subniches.py` (`FAMILIES`, `RESEARCH`, `card`, `list_view`, `detail_view`, `AVISOS`), `routes_subniches.py` (patrón de ruta, `VARY`, aviso por redirección), plantillas `base.html`, `components.html` (`chip`, `button`, `topbar`, `bottomnav`, `segmented`), CSS `static/css/app.css` (clases `.card .chip .btn .stack .rows .row .acc .note .tags .stats .segmented .pill .filters .countline .list`).
- Pruebas: `tests/web_helpers.py` (`settings`, `Api`, `make_client`, `csrf_of`, `subniche_item`, `subniche_card`, `HOSTILE`, …). **Se añaden fixtures, no se sobrescriben.**
- Dominio para reutilizar en el informe: `nicheradar.flow_research.contracts` (`calibration_total_hours`, modelos `DossierV3`) y `nicheradar.flow_research.gates`; el implementador los lee, no los duplica.

## Formas de la API verificadas (leídas del código el 2026-11-02; la API real manda sobre este resumen)

- `GET /status` → `radar_paused`, `timezone`. Errores: 401 `{"detail":"Acceso no autorizado"}`; los de flow-research/pilotos/subnichos traen `detail:{code,message,reasons?}`; los de mercado traen `detail` como texto.
- `GET /market/niches?format=&order=opportunity|automation&include_discarded=&limit=1..200&offset=` → `{items,total,limit,offset}`. Cada item: `niche_label`, `format` (`long|shorts`), `opportunity:{value:number|null, state:"scored"|"insufficient_evidence", …}`, `automation:{value:number|null, policy_risk:{level}}`, `confidence` (`alta|media|baja`), `metrics:{n_listings,n_active,n_income,income_median,…}`, `rpm_mid`, `decision:{decision:"nuevo|tentativo|descartado", note, decided_at}`, `trend`. **No trae** idioma, demanda, volumen ni estado de investigación.
- `GET /market/niches/{label}?format=long|shorts` (`format` obligatorio; 404 con `detail` texto) → `{niche, listings[], language_mix[{language, share_pct}], history[]}`; `language` es un código ISO o `"unknown"`.
- `POST /market/niches/{label}/decisions` cuerpo `{format, decision, note?}` → 201 `{niche_label, format, decision}`.
- `GET /flow-research?niche_label=&format=&language=&status=&limit≤100` → `{items}` (más recientes primero; sin `offset` ni `total`). Item: `id`, `niche_label`, `format`, `language`, `status` (`pendiente|en_curso|listo|rechazado`), `attempts`, `rejection:{problems[{path,message}],at}|null`, `created_at`, `updated_at`.
- `GET /flow-research/{id}` → item + `evidence` + `dossier` (dict|null, tal como se guardó; mirar `schema_version`: `dossier-v1|v2|v3`) + `dossier_created_at`. `evidence.gate`: `{min_automation, max_human_minutes, max_calibration_hours, block_high_policy_risk, passed, reasons[]}`; para subnichos `evidence.source == "subniche"` (leer `flow_research/subniche_evidence.py` para la fecha de la medición y la confianza).
- `POST /flow-research` cuerpo `{niche_label, format, language, gate_override?}` → 201 `{…, created:true}` o 200 `created:false`; 409 con `detail.code` ∈ `invalid_language|not_tentative|no_evidence|gate_failed(reasons[{gate,message}])|subniche_not_ready|format_mismatch|language_mismatch`; 404 `not_found`.
- dossier-v3 (claves de primer nivel): `verdict{recommendation go|go_with_conditions|no_go, confidence low|medium|high, thesis, main_risks[], unknowns[], conditions[]}`, `competitors[]`, `production_flow[{order,name,human_minutes_per_video,automation,tools[],stays_human}]`, `roadmap[]`, `budget{lines[], totals{low,likely,high}, assumptions[]}`, `tools[]`, `automation_map[]`, `policy_risk{level,summary,mitigations[]}`, `break_even`, `sources[{id,url,title,accessed_on}]`, `rights{verdict cleared|conditional|blocked, summary, materials[], conditions[]}`, `automation_plan`, `calibration{videos, setup_hours, exit_criterion{max_minutes_per_video, consecutive_videos, statement}, minutes_by_step[]}`, `steady_state_evidence{basis, reference_channel, reference_minutes_per_video, reference_sample_videos, format_match}`. v1 no tiene `rights`, `automation_plan`, `calibration`, `steady_state_evidence` ni `verdict.conditions`; v2 añade solo `rights` y `automation_plan`.
- `GET /pilots?status=&limit≤100` → `{items}`; item: `pilot_id`, `status` (`autorizado|entregado|en_ejecucion|decision_pendiente|cerrado|cancelado`), `niche_label`, `format`, `target_channel`, `authorized_at`, `needs_decision`, `proposal`, `totals`.
- `POST /pilots` (201) cuerpo: `niche_label`, `format`, `dossier_request_id`, `budget{currency:"USD",low,likely,high,max_videos 1..50,basis}`, `authorized_by`, `stop_rules?`, `close_after_failed_milestones 1..5 (def 2)`, `valid_days 1..60 (def 14)`, `target_channel?` (`^canal-[a-z0-9-]{1,40}$`), `recipe?`, `accept_no_go`, `accept_gate_failure`, `supersedes?`. Dinero con máximo 2 decimales. Respuesta `{pilot_id, status, package}`. Errores 409 `detail.code`: `dossier_not_ready|niche_mismatch|language_unknown|no_go_requires_acceptance|gate_failed(reasons)|bad_transition|channel_busy`; 404 `not_found`; 422 `{accepted:false, problems[{path,message}]}`.

## Global Constraints

- Todo lo del plan anterior sigue vigente: misma app y puerto; el contenedor solo conoce `NR_API_URL`, `NR_SERVICE_TOKEN`, `NR_DASHBOARD_PASSWORD`; `NR_DASHBOARD_UI=streamlit` por defecto; CSP `default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`; sin atributos `style=`, scripts en línea ni `on*=` en plantillas (una prueba existente lo exige); sin peticiones a terceros.
- Diseño móvil de 390 px de base con la paleta del Figma (Inter; fondo `#fff8f5`; primario `#be123c`; tarjetas blancas con borde `#f0e3dc` y radio 16; botones en píldora; etiquetas de 11 px; objetivos táctiles ≥ 44 px).
- Todo texto que venga de la API (etiquetas, títulos de canales, motivos, avisos, nombres de herramientas, URLs, errores) se muestra escapado: Jinja2 con autoescape; **nunca** `|safe` sobre datos de la API ni Markdown. Los enlaces a URLs de la API solo se emiten si empiezan por `https://` y llevan `rel="noopener noreferrer nofollow"` y `target="_blank"`; si no, se muestra el texto sin enlace.
- Los avisos tras una acción salen de un conjunto fijo de claves (`?aviso=<clave>`); el valor del query nunca se pinta. Los identificadores que se muestran o se usan en rutas (`id` de informe, `pilot_id`) se validan con expresión regular antes de usarlos (`^[0-9a-f-]{36}$`, `^pil_\d{8}_[a-z0-9_-]+$`).
- Todo POST que cambia datos exige sesión y token CSRF (`request.app.state.signer.csrf_valid(session, csrf)`); con token ausente o ajeno responde 403 y **no llama a la API**.
- Los datos que la API no entrega no se inventan: si el Figma pide una cifra que no existe (`Fit`, `Demanda (3 m)`, `Volumen`, idioma en la lista de nichos, `Cadencia` y `Preparación (días)` al autorizar), la tarjeta o el campo se omite.
- Una pantalla cuya llamada principal falla muestra un mensaje en español con estado 503 (200 si es un fragmento HTMX) y **no** vuelve a llamar a `/status` (`render(..., with_radar=False)`). «Hoy» degrada tarjeta por tarjeta.
- Las páginas que dependen del estado de una investigación o decisión envían `Vary: HX-Request, HX-History-Restore-Request` cuando sirven fragmentos HTMX (mismo patrón que `routes_subniches.py`).
- Dinero: se muestra en USD con puntos de millar (`US$ 1.234`); al enviar a la API se redondea a 2 decimales.
- Sin cambios de base de datos, de la API privada ni de contratos. Nada se despliega con este plan.

## Rulings de diseño

1. **Rutas con la etiqueta por query, no por ruta.** Las etiquetas de nicho pueden llevar `:` y `/` (`other:x`). En vez de `/nichos/{label}/investigar` se usa `/nichos/investigar?etiqueta=<etiqueta>&formato=<long|shorts>` y `POST /nichos/decidir`: así no hay problemas de codificación de `/` en la ruta. Costo si es incorrecto: cambiar tres rutas.
2. **Posponer y Descartar.** «Posponer» es un enlace de vuelta a la lista; «Descartar» solo existe para nichos del backlog (`POST /market/niches/{label}/decisions` con `descartado`); para subnichos no hay endpoint, y el botón no se muestra.
3. **Autorizar piloto sin cadencia ni preparación.** La API no tiene esos campos; se omiten y la pantalla dice solo lo que se fija de verdad (tope de videos, vigencia, hitos fallidos, canal destino, presupuesto, reglas de parada por defecto). El texto del Figma «Receta del método» se omite (no hay receta por defecto).
4. **Quién autoriza.** `authorized_by` fijo `"propietario (web)"`: la web tiene un único usuario autenticado por contraseña.
5. **«Hoy» sin Pilotos.** Los pilotos que necesitan algo se muestran como texto; el enlace «Ver pilotos» queda desactivado («Próximamente») hasta el corte 2.

## Review Focus

1. Etiquetas con `:`, `/`, `%`, `&` y texto hostil (`**x**`, `<script>`, `[x](https://evil.test)`) en nichos, informes, canales y motivos: se muestran escapados y no rompen rutas ni redirecciones (Tasks 1 a 5).
2. Un POST de decisión, de investigación o de autorización sin CSRF, con CSRF ajeno o con `volver`/`next` externo: 403 o redirección local, y la API no recibe ninguna llamada (Tasks 1, 2 y 4).
3. Un informe v1 o v2 guardado, uno `pendiente`, `en_curso` o `rechazado`, y uno v3 con campos opcionales nulos se abren sin error y con el aviso correcto (Task 3).
4. Idioma elegido inválido (`unknown`, `xx`, `EN`, vacío, o `en` cuando no está en la mezcla): el servidor rechaza antes de llamar a la API (Task 2).
5. Autorizar piloto con canal ocupado, compuerta fallida, no-go sin aceptación, dinero con más de 2 decimales y topes fuera de rango: mensaje claro, el formulario conserva lo escrito (Task 4).
6. API caída o lenta en cualquiera de las pantallas, y «Hoy» con una de cuatro fuentes caída (Tasks 1 a 5).

---

### Task 1: Nichos (M2), decisión «Marcar tentativo» y navegación

**Files:**
- Modify: `src/nicheradar/web/format.py` (añadir `usd`, `pct`), `src/nicheradar/web/templates/components.html` (la pestaña «Nichos» apunta a `/nichos`), `src/nicheradar/web/templates/subnichos/lista.html` (el segmento «Nichos» pasa a ser un enlace a `/nichos`), `src/nicheradar/web/app.py` (registrar router)
- Create: `src/nicheradar/web/niches.py`, `src/nicheradar/web/routes_niches.py`, `src/nicheradar/web/templates/nichos/lista.html`, `src/nicheradar/web/templates/nichos/_lista.html`
- Modify: `tests/web_helpers.py` (fixtures `niche_item`, `flow_item`)
- Create: `tests/test_web_niches.py`; Modify: `tests/test_web_format.py`

**Interfaces:**
- Consumes: `render`, `current_session`, `ApiClient`, macros `chip`, `button`, `segmented` (plan anterior).
- Produces: en `format.py`: `usd(value: float | str | None) -> str` (`"US$ 1.234"`, `"—"` si `None`), `pct(value: float | None) -> str` (`"80%"`); en `niches.py`: `DECISION_CHIP`, `RESEARCH_CHIP`, `NicheFilters(formato: str, alta: bool, ingresos: bool, orden: str)`, `parse_filters(params) -> NicheFilters`, `research_index(items: list[dict]) -> dict[tuple[str, str], dict]`, `card(item: dict, research: dict | None, rank: int) -> dict`, `list_view(items, research_items, filters) -> dict`, `investigate_href(label: str, fmt: str) -> str`, `AVISOS_NICHOS: dict[str, tuple[str, str]]`; rutas `GET /nichos` (página o fragmento HTMX) y `POST /nichos/decidir`; en pruebas `niche_item(label="historia-militar", fmt="long", **over)` y `flow_item(status="listo", **over)`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
def niche_item(label: str = "historia militar explicada", fmt: str = "long", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "niche_label": label,
        "format": fmt,
        "opportunity": {"version": "v1", "value": 78.0, "state": "scored", "components": {}, "components_used": []},
        "automation": {"version": "v1", "value": 64.0, "components": {"trait": 64.0},
                       "policy_risk": {"mean": 0.2, "level": "bajo"}},
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "nuevo", "note": None, "decided_at": None},
        "trend": 3.0,
    }
    return base | over


def flow_item(status: str = "listo", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "niche_label": "historia militar explicada",
        "format": "long",
        "language": "en",
        "status": status,
        "attempts": 1,
        "lease_until": None,
        "rejection": None,
        "created_at": "2026-11-02T02:05:45Z",
        "updated_at": "2026-11-02T03:00:00Z",
    }
    return base | over
```

Añadir a `tests/test_web_format.py`:

```python
from nicheradar.web.format import pct, usd


def test_usd_and_pct_format_for_spanish_readers() -> None:
    assert usd(1234.4) == "US$ 1.234" and usd("19.0") == "US$ 19" and usd(None) == "—"
    assert pct(80.0) == "80%" and pct(66.6) == "67%"
```

Crear `tests/test_web_niches.py`:

```python
# tests/test_web_niches.py
import json

import httpx

from tests.web_helpers import (
    HOSTILE, Api, csrf_of, flow_item, make_client, niche_item,
)

NICHES = ("GET", "/api/v1/market/niches")
FLOW = ("GET", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")


def api_with(*niches: dict[str, object], flows: list[dict[str, object]] | None = None) -> Api:
    return Api({
        NICHES: (200, {"items": list(niches), "total": len(niches), "limit": 200, "offset": 0}),
        FLOW: (200, {"items": flows or []}),
        STATUS: (200, {"radar_paused": True}),
    })


def test_the_list_needs_a_session() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    response = TestClient(create_app(settings()), follow_redirects=False).get("/nichos")
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_the_page_shows_the_title_the_count_and_one_card_per_niche() -> None:
    api = api_with(niche_item("a uno"), niche_item("b dos", "shorts"))
    text = make_client(api).get("/nichos").text
    assert "<h1" in text and ">Nichos<" in text
    assert "De mayor a menor por Opportunity (0 a 100)." in text
    assert text.count('class="card"') == 2
    assert "2 nichos" in text
    assert 'class="segmented__item segmented__item--on" href="/nichos"' in text
    assert 'href="/subnichos"' in text  # the selector links to the sub-niche list


def test_a_card_shows_the_real_scores_and_never_the_missing_ones() -> None:
    text = make_client(api_with(niche_item())).get("/nichos").text
    assert "<dt>Opportunity</dt><dd>78</dd>" in text
    assert "<dt>Automat.</dt><dd>64</dd>" in text
    assert "<dt>Confianza</dt><dd>Media</dd>" in text
    assert "Fit" not in text and "Demanda" not in text and "Volumen" not in text


def test_the_navigation_points_the_nichos_tab_to_the_niche_list() -> None:
    text = make_client(api_with(niche_item())).get("/nichos").text
    assert 'class="tab tab--on" href="/nichos" aria-current="page"' in text


def test_the_primary_button_follows_decision_and_research_state() -> None:
    api = api_with(
        niche_item("sin decidir"),
        niche_item("tentativo", decision={"decision": "tentativo", "note": None, "decided_at": "x"}),
        niche_item("con dossier", decision={"decision": "tentativo", "note": None, "decided_at": "x"}),
        niche_item("investigando", decision={"decision": "tentativo", "note": None, "decided_at": "x"}),
        niche_item("sin puntaje", opportunity={"version": "v1", "value": None, "state": "insufficient_evidence",
                                               "components": {}, "components_used": []}),
        flows=[
            flow_item("listo", niche_label="con dossier", id="11111111-1111-1111-1111-111111111111"),
            flow_item("en_curso", niche_label="investigando", id="22222222-2222-2222-2222-222222222222"),
        ],
    )
    text = make_client(api).get("/nichos").text
    assert text.count("Marcar tentativo</button>") == 1
    assert 'href="/nichos/investigar?etiqueta=tentativo&amp;formato=long">Investigar</a>' in text
    assert 'href="/informes/11111111-1111-1111-1111-111111111111">Ver dossier</a>' in text
    assert 'href="/informes/22222222-2222-2222-2222-222222222222">Ver estado</a>' in text
    assert "Falta puntaje</button>" in text and "disabled" in text


def test_the_research_state_chip_comes_from_the_matching_label_and_format() -> None:
    api = api_with(
        niche_item("mismo", "long"),
        niche_item("mismo", "shorts"),
        flows=[flow_item("listo", niche_label="mismo", format="long")],
    )
    text = make_client(api).get("/nichos").text
    assert text.count("Dossier listo") == 1


def test_format_chips_count_the_whole_list_and_filter_in_the_web_layer() -> None:
    api = api_with(niche_item("l1"), niche_item("l2"), niche_item("s1", "shorts"))
    web = make_client(api)
    full = web.get("/nichos").text
    assert "Todos" in full and "Largos" in full and "Shorts" in full
    shorts = web.get("/nichos", params={"formato": "shorts"}).text
    assert "s1" in shorts and "l1" not in shorts
    assert shorts.count('class="card"') == 1


def test_filters_confianza_alta_and_con_ingresos() -> None:
    api = api_with(
        niche_item("alta con", confidence="alta"),
        niche_item("media", confidence="media"),
        niche_item("alta sin", confidence="alta", metrics={"n_income": 0, "n_listings": 3}),
    )
    web = make_client(api)
    alta = web.get("/nichos", params={"alta": "1"}).text
    assert "alta con" in alta and "alta sin" in alta and ">media<" not in alta
    ingresos = web.get("/nichos", params={"ingresos": "1"}).text
    assert "alta sin" not in ingresos and "alta con" in ingresos


def test_the_order_is_passed_to_the_api_and_junk_is_ignored() -> None:
    api = api_with(niche_item())
    web = make_client(api)
    web.get("/nichos", params={"orden": "automation"})
    assert api.calls[-1].url.params["order"] == "automation" or any(
        c.url.params.get("order") == "automation" for c in api.calls if c.url.path.endswith("/niches")
    )
    for params in ({"orden": "zzz"}, {"formato": "<script>"}, {"alta": "9"}):
        response = web.get("/nichos", params=params)
        assert response.status_code == 200 and "<script>" not in response.text
    last = [c for c in api.calls if c.url.path.endswith("/niches")][-1]
    assert last.url.params["order"] == "opportunity"


def test_hostile_labels_are_escaped_and_the_link_is_encoded() -> None:
    label = "a/b:c&d " + HOSTILE
    api = api_with(niche_item(label, decision={"decision": "tentativo", "note": None, "decided_at": "x"}))
    text = make_client(api).get("/nichos").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "etiqueta=a%2Fb%3Ac%26d%20" in text


def test_an_htmx_request_gets_the_fragment_and_vary() -> None:
    api = api_with(niche_item("uno"))
    response = make_client(api).get("/nichos", headers={"hx-request": "true"})
    assert response.status_code == 200 and "uno" in response.text and "<html" not in response.text
    assert "HX-Request" in response.headers["vary"]


def test_an_unavailable_api_gives_a_clear_503_without_a_second_status_call() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({NICHES: boom, FLOW: (200, {"items": []}), STATUS: (200, {"radar_paused": False})})
    web = make_client(api)
    before = api.count(*STATUS)
    response = web.get("/nichos")
    assert response.status_code == 503 and "API no disponible" in response.text
    assert api.count(*STATUS) == before


def test_when_only_the_research_list_fails_the_niches_still_show_without_research_chips() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({
        NICHES: (200, {"items": [niche_item("uno")], "total": 1, "limit": 200, "offset": 0}),
        FLOW: boom, STATUS: (200, {"radar_paused": True}),
    })
    response = make_client(api).get("/nichos")
    assert response.status_code == 200 and "uno" in response.text
    assert "La lista de investigaciones no está disponible" in response.text


def test_an_empty_list_has_its_own_message() -> None:
    assert "Todavía no hay nichos" in make_client(api_with()).get("/nichos").text


def post_decide(web, token: str, **over: str):  # type: ignore[no-untyped-def]
    data = {"csrf": token, "etiqueta": "uno", "formato": "long", "decision": "tentativo", "volver": "/nichos"}
    return web.post("/nichos/decidir", data=data | over)


def test_marking_tentative_posts_the_decision_and_redirects_with_a_notice() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"niche_label": "uno", "format": "long", "decision": "tentativo"})

    api = api_with(niche_item("uno"))
    api.routes[("POST", "/api/v1/market/niches/uno/decisions")] = accept
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    response = post_decide(web, token)
    assert response.status_code == 303 and response.headers["location"] == "/nichos?aviso=marcado"
    assert json.loads(bodies[0]) == {"format": "long", "decision": "tentativo"}


def test_the_decision_label_is_quoted_in_the_api_path() -> None:
    seen: list[str] = []

    def accept(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        return httpx.Response(201, json={})

    api = api_with(niche_item("a/b"))
    api.routes[("POST", "/api/v1/market/niches/a/b/decisions")] = accept  # placeholder: must NOT be used
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    post_decide(web, token, etiqueta="a/b")
    assert not seen or "%2F" in seen[0]


def test_a_bad_csrf_or_decision_never_reaches_the_api() -> None:
    api = api_with(niche_item("uno"))
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    assert post_decide(web, "wrong").status_code == 403
    assert web.post("/nichos/decidir").status_code == 403
    assert post_decide(web, token, decision="borrar").status_code == 303  # ignored, notice only
    assert api.count("POST", "/api/v1/market/niches/uno/decisions") == 0


def test_the_return_path_must_stay_inside_the_niche_list() -> None:
    api = api_with(niche_item("uno"))
    api.routes[("POST", "/api/v1/market/niches/uno/decisions")] = (201, {})
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    for target in ("//evil.test", "https://evil.test", "/\\evil", "/subnichos"):
        response = post_decide(web, token, volver=target)
        assert response.headers["location"].startswith("/nichos")
        assert "evil" not in response.headers["location"]


def test_an_api_failure_on_decide_redirects_with_an_error_notice() -> None:
    api = api_with(niche_item("uno"))
    api.routes[("POST", "/api/v1/market/niches/uno/decisions")] = (404, {"detail": "Nicho no encontrado"})
    web = make_client(api)
    token = csrf_of(web.get("/nichos").text)
    assert post_decide(web, token).headers["location"] == "/nichos?aviso=error"


def test_the_notice_comes_only_from_fixed_keys() -> None:
    web = make_client(api_with(niche_item("uno")))
    assert "Marcado como tentativo" in web.get("/nichos", params={"aviso": "marcado"}).text
    page = web.get("/nichos", params={"aviso": HOSTILE})
    assert page.status_code == 200 and "evil.test" not in page.text
```

(La prueba `test_the_decision_label_is_quoted_in_the_api_path` registra una ruta a propósito incorrecta: el implementador debe sustituir el registro `a/b` por un manejador sobre la ruta cruda que el cliente realmente envía —`/api/v1/market/niches/a%2Fb/decisions`— si `Api` no la resuelve por `request.url.path`; lo importante que verifica la prueba es que el `/` de la etiqueta viaja codificado como `%2F`. Si la API de pruebas no puede casar rutas con `%2F`, usar un manejador de transporte propio en esa prueba y comprobar `request.url.raw_path`.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_niches.py tests/test_web_format.py -q 2>&1 | tail -6`
Expected: FAIL (`/nichos` da 404; `usd`/`pct` no existen).

- [ ] **Step 3: Implementar formato y modelo de vista**

En `src/nicheradar/web/format.py` añadir:

```python
def usd(value: float | str | None) -> str:
    return "—" if value is None else f"US$ {es_int(float(value))}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{round(value)}%"
```

Crear `src/nicheradar/web/niches.py`:

```python
# src/nicheradar/web/niches.py
"""View models for the niche list (M2): what the template shows, never raw API payloads."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

DECISION_CHIP = {
    "nuevo": ("Sin decidir", "neutral"),
    "tentativo": ("Tentativo", "rose"),
    "descartado": ("Descartado", "neutral"),
}
RESEARCH_CHIP = {
    "pendiente": ("En cola", "amber"),
    "en_curso": ("Investigando", "blue"),
    "listo": ("Dossier listo", "green"),
    "rechazado": ("Rechazada", "rose"),
}
CONFIDENCE = {"alta": "Alta", "media": "Media", "baja": "Baja"}
FORMATS = {"long": "Largos", "shorts": "Shorts"}
ORDERS = ("opportunity", "automation")
AVISOS_NICHOS = {
    "marcado": ("Marcado como tentativo.", "green"),
    "error": ("No se pudo guardar la decisión. Revisa la API e inténtalo de nuevo.", "rose"),
    "invalida": ("La decisión no es válida.", "amber"),
}


@dataclass(frozen=True)
class NicheFilters:
    formato: str = ""
    alta: bool = False
    ingresos: bool = False
    orden: str = "opportunity"


def parse_filters(params: Mapping[str, str]) -> NicheFilters:
    formato = params.get("formato", "")
    orden = params.get("orden", "")
    return NicheFilters(
        formato=formato if formato in FORMATS else "",
        alta=params.get("alta") == "1",
        ingresos=params.get("ingresos") == "1",
        orden=orden if orden in ORDERS else "opportunity",
    )


def investigate_href(label: str, fmt: str) -> str:
    return f"/nichos/investigar?etiqueta={quote(label, safe='')}&formato={quote(fmt, safe='')}"


def research_index(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Newest research per (label, format): the API lists newest first, so the first one wins."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        index.setdefault((item["niche_label"], item["format"]), item)
    return index


def _score(block: dict[str, Any] | None) -> int | None:
    value = (block or {}).get("value")
    return None if value is None else round(value)


def card(item: dict[str, Any], research: dict[str, Any] | None, rank: int) -> dict[str, Any]:
    decision = item["decision"]["decision"]
    state = research["status"] if research else None
    opportunity = _score(item["opportunity"])
    d_text, d_kind = DECISION_CHIP.get(decision, DECISION_CHIP["nuevo"])
    r_text, r_kind = RESEARCH_CHIP.get(state, (None, None)) if state else (None, None)
    label, fmt = item["niche_label"], item["format"]
    action: dict[str, Any]
    if opportunity is None:
        action = {"kind": "disabled", "label": "Falta puntaje"}
    elif state == "listo":
        action = {"kind": "link", "label": "Ver dossier", "style": "secondary", "href": f"/informes/{research['id']}"}
    elif state in ("pendiente", "en_curso"):
        action = {"kind": "link", "label": "Ver estado", "style": "secondary", "href": f"/informes/{research['id']}"}
    elif decision == "tentativo":
        action = {"kind": "link", "label": "Investigar", "style": "primary", "href": investigate_href(label, fmt)}
    else:
        action = {"kind": "decide", "label": "Marcar tentativo", "label_raw": label, "format": fmt}
    return {
        "rank": rank if opportunity is not None else "—",
        "label": label,
        "format": fmt,
        "format_text": "Shorts" if fmt == "shorts" else "Largo",
        "decision_text": d_text,
        "decision_kind": d_kind,
        "research_text": r_text,
        "research_kind": r_kind,
        "scores": [
            ("Opportunity", opportunity if opportunity is not None else "sin puntaje"),
            ("Automat.", _score(item["automation"]) if _score(item["automation"]) is not None else "—"),
            ("Confianza", CONFIDENCE.get(item["confidence"], "—")),
        ],
        "action": action,
    }


def list_view(
    items: list[dict[str, Any]], research_items: list[dict[str, Any]], filters: NicheFilters
) -> dict[str, Any]:
    index = research_index(research_items)
    shown = [
        item
        for item in items
        if (not filters.formato or item["format"] == filters.formato)
        and (not filters.alta or item["confidence"] == "alta")
        and (not filters.ingresos or (item.get("metrics") or {}).get("n_income", 0) > 0)
    ]
    counts = {fmt: sum(1 for item in items if item["format"] == fmt) for fmt in FORMATS}
    return {
        "cards": [
            card(item, index.get((item["niche_label"], item["format"])), rank)
            for rank, item in enumerate(shown, 1)
        ],
        "total": len(items),
        "shown": len(shown),
        "counts": counts,
        "filtros": filters,
    }
```

(El texto de la tarjeta usa `<dt>`/`<dd>` en un `<dl class="stats">`, como M9; la prueba pide exactamente `<dt>Opportunity</dt><dd>78</dd>`.)

- [ ] **Step 4: Implementar la ruta y las plantillas**

Crear `src/nicheradar/web/routes_niches.py`:

```python
# src/nicheradar/web/routes_niches.py
"""Niche list (M2) and the 'mark tentative' decision."""

from typing import Annotated
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render
from nicheradar.web.niches import AVISOS_NICHOS, ORDERS, list_view, parse_filters
from nicheradar.web.security import Session

router = APIRouter()
VARY = "HX-Request, HX-History-Restore-Request"
DECISIONS = ("nuevo", "tentativo", "descartado")
RESEARCH_DOWN = "La lista de investigaciones no está disponible: no se muestra su estado."


def _fragment(request: Request) -> bool:
    return bool(request.headers.get("hx-request")) and not request.headers.get(
        "hx-history-restore-request"
    )


def _back(volver: str, aviso: str) -> str:
    # Only the niche list itself: an open redirect through `volver` must be impossible.
    base = volver if volver == "/nichos" or volver.startswith("/nichos?") else "/nichos"
    path, _, query = base.partition("?")
    pairs = [(k, v) for k, _, v in (p.partition("=") for p in query.split("&") if p) if k != "aviso"]
    return path + "?" + urlencode([*pairs, ("aviso", aviso)])


@router.get("/nichos")
def niche_list(request: Request, session: Annotated[Session, Depends(current_session)]) -> Response:
    filters = parse_filters(request.query_params)
    htmx = _fragment(request)
    template = "nichos/_lista.html" if htmx else "nichos/lista.html"
    notice = AVISOS_NICHOS.get(request.query_params.get("aviso", ""))
    api = request.app.state.api
    try:
        niches = api.request(
            "GET", "/market/niches", params={"order": filters.orden, "limit": "200"}
        )
    except ApiError as error:
        response = render(
            request, template,
            {"active_tab": "nichos", "error": error.message, "view": None, "filtros": filters, "notice": None},
            status_code=200 if htmx else 503, session=session, with_radar=False,
        )
    else:
        warning: str | None = None
        try:
            research = api.request("GET", "/flow-research", params={"limit": "100"})["items"]
        except ApiError:
            research, warning = [], RESEARCH_DOWN
        view = list_view(niches["items"], research, filters)
        response = render(
            request, template,
            {"active_tab": "nichos", "error": None, "view": view, "filtros": filters,
             "notice": notice, "warning": warning},
            session=session,
        )
    response.headers["Vary"] = VARY
    return response


@router.post("/nichos/decidir")
def decide(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    etiqueta: Annotated[str, Form()] = "",
    formato: Annotated[str, Form()] = "",
    decision: Annotated[str, Form()] = "",
    volver: Annotated[str, Form()] = "/nichos",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request, "error.html", {"message": "La solicitud no es válida."},
            status_code=403, session=session,
        )
    if decision not in DECISIONS or formato not in ("long", "shorts") or not (1 <= len(etiqueta) <= 140):
        return RedirectResponse(_back(volver, "invalida"), status_code=303)
    try:
        request.app.state.api.request(
            "POST", f"/market/niches/{quote(etiqueta, safe='')}/decisions",
            body={"format": formato, "decision": decision},
        )
    except ApiError:
        return RedirectResponse(_back(volver, "error"), status_code=303)
    return RedirectResponse(_back(volver, "marcado"), status_code=303)
```

(`ORDERS` se importa por claridad; si ruff lo marca como no usado, quitarlo.) En `app.py` registrar `app.include_router(routes_niches.router)` junto a los otros.

Crear `src/nicheradar/web/templates/nichos/lista.html`:

```html
{% extends "base.html" %}
{% from "components.html" import segmented %}
{% block title %}Nichos · NicheRadar{% endblock %}
{% block content %}
{{ segmented([("Nichos", "/nichos", True, None), ("Subnichos", "/subnichos", False, None)]) }}
<h1 class="h1">Nichos</h1>
<p class="caption">De mayor a menor por Opportunity (0 a 100).</p>
<form class="filters" method="get" action="/nichos"
      hx-get="/nichos" hx-trigger="change" hx-target="#contenido" hx-swap="innerHTML" hx-push-url="true">
  <label class="pill"><input type="radio" name="formato" value=""{% if not filtros.formato %} checked{% endif %}>Todos{% if view %} {{ view.total }}{% endif %}</label>
  <label class="pill"><input type="radio" name="formato" value="long"{% if filtros.formato == "long" %} checked{% endif %}>Largos{% if view %} {{ view.counts.long }}{% endif %}</label>
  <label class="pill"><input type="radio" name="formato" value="shorts"{% if filtros.formato == "shorts" %} checked{% endif %}>Shorts{% if view %} {{ view.counts.shorts }}{% endif %}</label>
  <label class="pill"><input type="checkbox" name="alta" value="1"{% if filtros.alta %} checked{% endif %}>Confianza alta</label>
  <label class="pill"><input type="checkbox" name="ingresos" value="1"{% if filtros.ingresos %} checked{% endif %}>Con ingresos</label>
  <label class="pill"><input type="checkbox" name="orden" value="automation"{% if filtros.orden == "automation" %} checked{% endif %}>Más automatizables</label>
  <noscript><button class="btn btn--secondary" type="submit">Aplicar</button></noscript>
</form>
<div id="contenido" class="stack">
{% include "nichos/_lista.html" %}
</div>
{% endblock %}
```

Crear `src/nicheradar/web/templates/nichos/_lista.html`:

```html
{% from "components.html" import chip %}
{% if error %}
<div class="note note--rose" role="alert"><span class="note__title">No se pudo cargar</span>{{ error }}</div>
{% else %}
{% if notice %}<div class="note note--{{ notice[1] }}" role="status">{{ notice[0] }}</div>{% endif %}
{% if warning %}<div class="note note--amber">{{ warning }}</div>{% endif %}
{% if not view.total %}
<p class="lead">Todavía no hay nichos. Los crea el radar de mercado.</p>
{% else %}
<div class="countline"><span><strong>{{ view.shown }}</strong> nichos</span><span>{% if filtros.orden == "automation" %}Automatización ↓{% else %}Opportunity ↓{% endif %}</span></div>
{% for c in view.cards %}
<article class="card">
  <div class="card__title"><span class="rank">{{ c.rank }}</span><span class="card__name">{{ c.label }}</span></div>
  <div class="tags">{{ chip(c.format_text, "neutral") }}{{ chip(c.decision_text, c.decision_kind) }}{% if c.research_text %}{{ chip(c.research_text, c.research_kind) }}{% endif %}</div>
  <dl class="stats">{% for label, value in c.scores %}<div><dt>{{ label }}</dt><dd>{{ value }}</dd></div>{% endfor %}</dl>
  {% if c.action.kind == "link" %}<a class="btn btn--{{ c.action.style }}" href="{{ c.action.href }}">{{ c.action.label }}</a>
  {% elif c.action.kind == "decide" %}
  <form method="post" action="/nichos/decidir">
    <input type="hidden" name="csrf" value="{{ csrf_token }}">
    <input type="hidden" name="etiqueta" value="{{ c.label }}">
    <input type="hidden" name="formato" value="{{ c.format }}">
    <input type="hidden" name="decision" value="tentativo">
    <input type="hidden" name="volver" value="/nichos">
    <button class="btn btn--secondary" type="submit">{{ c.action.label }}</button>
  </form>
  {% else %}<button class="btn btn--secondary" type="button" disabled>{{ c.action.label }}</button>{% endif %}
</article>
{% else %}
<p class="lead">Ningún nicho coincide con los filtros.</p>
{% endfor %}
{% endif %}
{% endif %}
```

(Las tarjetas de la lista deben tener `class="card"` exacto para la prueba de conteo; el filtro de formato usa radios dentro de `.pill` y el CSS existente `.pill:has(input:checked)` marca el activo.) Cambiar en `components.html` la pestaña `("nichos", "▦", "Nichos", "/subnichos")` por `"/nichos"`, y en `subnichos/lista.html` el primer elemento del `segmented([...])` de `("Nichos", None, False, None)` a `("Nichos", "/nichos", False, None)`; ajustar las pruebas de `test_web_subniches_list.py` que dependan del segmento desactivado.

- [ ] **Step 5: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_web_niches.py tests/test_web_format.py tests/test_web_subniches_list.py tests/test_web_assets.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS; ruff y mypy sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_niches.py tests/test_web_format.py tests/test_web_subniches_list.py
git commit -m "feat: pantalla M2, lista de nichos con filtros y decisión de tentativo"
```

---

### Task 2: Iniciar investigación de un nicho (M8)

**Files:**
- Create: `src/nicheradar/web/research.py`, `src/nicheradar/web/routes_research.py`, `src/nicheradar/web/templates/nichos/investigar.html`
- Modify: `src/nicheradar/web/app.py` (router), `tests/web_helpers.py` (`niche_detail`)
- Create: `tests/test_web_research.py`

**Interfaces:**
- Consumes: `niches.investigate_href`, `render`, `current_session`, `ApiClient`, `ApiError` (`.kind`, `.detail`), macros `chip`, `button`.
- Produces: en `research.py`: `LANGUAGE_NAMES` (`en`→`inglés`, `es`→`español`, `pt`→`portugués`, `de`, `fr`, `ru`, `it`, `ja`, `ko`, `ar`, `hi`, `tr`), `LANG_RE` (`^[a-z]{2}(-[A-Z]{2})?$`), `language_options(mix: list[dict]) -> dict` → `{"options": [{"code","name","share","suggested"}], "unknown_share": float|None, "suggested": str|None, "no_choice": bool}`, `CONFLICT_MESSAGES: dict[str, str]` (por `detail.code`); rutas `GET /nichos/investigar?etiqueta=&formato=` y `POST /nichos/investigar`; en pruebas `niche_detail(label, fmt, mix)`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
def niche_detail(
    label: str = "historia militar explicada", fmt: str = "long",
    mix: list[tuple[str, float]] | None = None,
) -> dict[str, object]:
    mix = mix if mix is not None else [("en", 80.0), ("es", 15.0), ("unknown", 5.0)]
    return {
        "niche": niche_item(label, fmt),
        "listings": [],
        "language_mix": [{"language": code, "share_pct": share} for code, share in mix],
        "history": [],
    }
```

Crear `tests/test_web_research.py` con estas pruebas (cada una con su `Api`; el prefijo de ruta de la API es `/api/v1/market/niches/<etiqueta codificada>`):

```python
# tests/test_web_research.py
import json

import httpx
import pytest

from nicheradar.web.research import language_options
from tests.web_helpers import HOSTILE, Api, csrf_of, make_client, niche_detail

LABEL = "historia militar explicada"
DETAIL = ("GET", "/api/v1/market/niches/historia militar explicada")
ORDER = ("POST", "/api/v1/flow-research")
STATUS = ("GET", "/api/v1/status")
URL = "/nichos/investigar?etiqueta=historia%20militar%20explicada&formato=long"


def api_with(detail: dict[str, object] | None = None, **extra: object) -> Api:
    routes: dict[tuple[str, str], object] = {
        DETAIL: (200, detail or niche_detail()), STATUS: (200, {"radar_paused": True}),
    }
    routes.update(extra)  # type: ignore[arg-type]
    return Api(routes)  # type: ignore[arg-type]


def test_language_options_suggest_the_clear_leader_only() -> None:
    clear = language_options([{"language": "en", "share_pct": 80.0}, {"language": "es", "share_pct": 15.0},
                              {"language": "unknown", "share_pct": 5.0}])
    assert clear["suggested"] == "en" and clear["unknown_share"] == 5.0 and not clear["no_choice"]
    tie = language_options([{"language": "en", "share_pct": 45.0}, {"language": "es", "share_pct": 45.0},
                            {"language": "unknown", "share_pct": 10.0}])
    assert tie["suggested"] is None
    unknown_leads = language_options([{"language": "unknown", "share_pct": 60.0}, {"language": "en", "share_pct": 40.0}])
    assert unknown_leads["suggested"] is None
    only_unknown = language_options([{"language": "unknown", "share_pct": 100.0}])
    assert only_unknown["no_choice"] is True and only_unknown["options"] == []
    assert language_options([])["no_choice"] is True


def test_the_page_lists_languages_with_the_suggestion_and_the_explanations() -> None:
    text = make_client(api_with()).get(URL).text
    assert "Iniciar investigación de flujo" in text.replace("INICIAR", "Iniciar") or "INICIAR INVESTIGACIÓN" in text.upper()
    assert 'name="idioma" value="en" checked' in text and 'name="idioma" value="es"' in text
    assert "Sugerido" in text and "80%" in text and "15%" in text
    assert "Sin dato" in text and "no se puede elegir" in text
    assert "Qué pasa al iniciar" in text and 'name="csrf"' in text
    assert "Iniciar investigación en inglés" in text


def test_with_no_clear_leader_nothing_is_preselected_and_the_button_waits() -> None:
    detail = niche_detail(mix=[("en", 45.0), ("es", 45.0), ("unknown", 10.0)])
    text = make_client(api_with(detail)).get(URL).text
    assert " checked" not in text.split('name="idioma"', 1)[1].split("</form>")[0]
    assert "Elige un idioma" in text


def test_an_unknown_niche_or_format_is_a_404_and_junk_format_never_reaches_the_api() -> None:
    api = Api({DETAIL: (404, {"detail": "Nicho no encontrado"}), STATUS: (200, {"radar_paused": True})})
    web = make_client(api)
    assert web.get(URL).status_code == 404
    assert web.get("/nichos/investigar?etiqueta=x&formato=zzz").status_code == 404
    assert web.get("/nichos/investigar").status_code == 404
    assert api.count(*DETAIL) == 1


def test_an_unavailable_api_gives_503() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    response = make_client(Api({DETAIL: boom, STATUS: (200, {"radar_paused": False})})).get(URL)
    assert response.status_code == 503 and "API no disponible" in response.text


def test_the_label_is_escaped_in_the_page() -> None:
    label = "a:b " + HOSTILE
    api = Api({("GET", f"/api/v1/market/niches/{label}"): (200, niche_detail(label)),
               STATUS: (200, {"radar_paused": True})})
    text = make_client(api).get("/nichos/investigar", params={"etiqueta": label, "formato": "long"}).text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


def post(web, token: str, **over: str):  # type: ignore[no-untyped-def]
    data = {"csrf": token, "etiqueta": LABEL, "formato": "long", "idioma": "en"}
    return web.post("/nichos/investigar", data=data | over)


def test_starting_posts_the_chosen_language_and_redirects_to_the_report() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6", "created": True})

    web = make_client(api_with(**{ORDER: accept}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 303
    assert response.headers["location"] == "/informes/f0c90924-295a-4136-a0fb-d3fb2c3eacc6?aviso=creada"
    assert json.loads(bodies[0]) == {"niche_label": LABEL, "format": "long", "language": "en"}


def test_an_existing_order_goes_to_its_report_with_the_existing_notice() -> None:
    api = api_with(**{ORDER: (200, {"id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6", "created": False})})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, token).headers["location"].endswith("?aviso=existente")


@pytest.mark.parametrize("language", ["unknown", "xx1", "EN", "", "en-us", "<script>"])
def test_an_invalid_language_never_reaches_the_api(language: str) -> None:
    api = api_with(**{ORDER: (201, {"id": "x", "created": True})})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token, idioma=language)
    assert response.status_code == 422 and "Elige un idioma válido" in response.text
    assert api.count(*ORDER) == 0


def test_a_language_not_in_the_mix_is_rejected_before_the_api() -> None:
    api = api_with(**{ORDER: (201, {"id": "x", "created": True})})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, token, idioma="ru").status_code == 422
    assert api.count(*ORDER) == 0


def test_bad_or_missing_csrf_is_a_403_without_api_calls() -> None:
    api = api_with(**{ORDER: (201, {"id": "x", "created": True})})
    web = make_client(api)
    assert post(web, "wrong").status_code == 403 and web.post("/nichos/investigar").status_code == 403
    assert api.count(*ORDER) == 0


@pytest.mark.parametrize(
    ("code", "needle"),
    [("not_tentative", "tentativo"), ("no_evidence", "puntaje"), ("invalid_language", "idioma")],
)
def test_conflicts_map_to_clear_messages(code: str, needle: str) -> None:
    api = api_with(**{ORDER: (409, {"detail": {"code": code, "message": "x"}})})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and needle in response.text


def test_a_failed_gate_lists_the_api_reasons_escaped() -> None:
    detail = {"code": "gate_failed", "message": "x", "reasons": [{"gate": "automation", "message": HOSTILE}]}
    web = make_client(api_with(**{ORDER: (409, {"detail": detail})}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_an_api_outage_on_post_keeps_the_form_with_a_message() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    web = make_client(api_with(**{ORDER: boom}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 503 and "API no disponible" in response.text
```

(Si `Api` no casa rutas con espacios, codificar la etiqueta en las claves como lo hace `httpx` (`historia%20militar%20explicada`) y comparar con `request.url.raw_path`; ajustar solo el helper `api_with`, no las aserciones.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_research.py -q 2>&1 | tail -5`
Expected: FAIL (`ModuleNotFoundError: nicheradar.web.research`).

- [ ] **Step 3: Implementar**

Crear `src/nicheradar/web/research.py`:

```python
# src/nicheradar/web/research.py
"""View model of the 'start flow research' screen (M8)."""

import re
from typing import Any

LANG_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
LANGUAGE_NAMES = {
    "en": "Inglés", "es": "Español", "pt": "Portugués", "de": "Alemán", "fr": "Francés",
    "ru": "Ruso", "it": "Italiano", "ja": "Japonés", "ko": "Coreano", "ar": "Árabe",
    "hi": "Hindi", "tr": "Turco",
}
CONFLICT_MESSAGES = {
    "not_tentative": "Primero marca el nicho como tentativo para poder investigarlo.",
    "no_evidence": "El nicho todavía no tiene puntaje: falta evidencia para investigarlo.",
    "invalid_language": "El idioma no es válido: elige uno de la lista.",
    "gate_failed": "El nicho no pasa una compuerta de selección.",
    "not_found": "No se encontró el nicho.",
}


def language_options(mix: list[dict[str, Any]]) -> dict[str, Any]:
    known = [entry for entry in mix if entry["language"] != "unknown" and LANG_RE.match(entry["language"])]
    unknown = next((e["share_pct"] for e in mix if e["language"] == "unknown"), None)
    options = [
        {
            "code": e["language"],
            "name": LANGUAGE_NAMES.get(e["language"], e["language"]),
            "share": round(e["share_pct"]),
            "suggested": False,
        }
        for e in sorted(known, key=lambda e: -e["share_pct"])
    ]
    suggested: str | None = None
    if options:
        top = max(mix, key=lambda e: e["share_pct"])
        runner_up = sorted((e["share_pct"] for e in mix), reverse=True)[1:2]
        # No pre-selection on a tie or when "unknown" leads: the owner must choose.
        if top["language"] != "unknown" and (not runner_up or top["share_pct"] > runner_up[0]):
            suggested = top["language"]
            options[0]["suggested"] = True
    return {
        "options": options,
        "unknown_share": None if unknown is None else round(unknown),
        "suggested": suggested,
        "no_choice": not options,
    }
```

Crear `src/nicheradar/web/routes_research.py`:

```python
# src/nicheradar/web/routes_research.py
"""M8: choose the language and create a flow-research order for a backlog niche."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render
from nicheradar.web.research import CONFLICT_MESSAGES, LANG_RE, language_options
from nicheradar.web.security import Session

router = APIRouter()
FORMATS = ("long", "shorts")


def _missing(request: Request, session: Session, message: str, status: int) -> Response:
    return render(request, "error.html", {"message": message, "active_tab": "nichos"},
                  status_code=status, session=session, with_radar=False)


def _page(request: Request, session: Session, label: str, fmt: str, *, status: int = 200,
          error: str | None = None, reasons: list[str] | None = None, chosen: str | None = None) -> Response:
    try:
        detail = request.app.state.api.request(
            "GET", f"/market/niches/{quote(label, safe='')}", params={"format": fmt}
        )
    except ApiError as err:
        return _missing(request, session, err.message, 404 if err.kind == "not_found" else 503)
    view = language_options(detail["language_mix"])
    return render(
        request, "nichos/investigar.html",
        {"active_tab": "nichos", "label": label, "format": fmt,
         "format_text": "Shorts" if fmt == "shorts" else "Largos", "lang": view,
         "error": error, "reasons": reasons or [], "chosen": chosen or view["suggested"]},
        status_code=status, session=session,
    )


@router.get("/nichos/investigar")
def form(request: Request, session: Annotated[Session, Depends(current_session)],
         etiqueta: str = "", formato: str = "") -> Response:
    if not (1 <= len(etiqueta) <= 140) or formato not in FORMATS:
        return _missing(request, session, "No se encontró lo que buscabas.", 404)
    return _page(request, session, etiqueta, formato)


@router.post("/nichos/investigar")
def start(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    etiqueta: Annotated[str, Form()] = "",
    formato: Annotated[str, Form()] = "",
    idioma: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _missing(request, session, "La solicitud no es válida.", 403)
    if not (1 <= len(etiqueta) <= 140) or formato not in FORMATS:
        return _missing(request, session, "No se encontró lo que buscabas.", 404)
    api = request.app.state.api
    try:
        detail = api.request("GET", f"/market/niches/{quote(etiqueta, safe='')}", params={"format": formato})
    except ApiError as err:
        return _missing(request, session, err.message, 404 if err.kind == "not_found" else 503)
    allowed = {o["code"] for o in language_options(detail["language_mix"])["options"]}
    if not LANG_RE.match(idioma) or idioma not in allowed:
        return _page(request, session, etiqueta, formato, status=422,
                     error="Elige un idioma válido de la lista.")
    try:
        result = api.request(
            "POST", "/flow-research",
            body={"niche_label": etiqueta, "format": formato, "language": idioma},
        )
    except ApiError as err:
        code = err.detail.get("code") if isinstance(err.detail, dict) else None
        reasons = [str(r.get("message", "")) for r in (err.detail or {}).get("reasons", [])
                   if isinstance(r, dict)] if isinstance(err.detail, dict) else []
        if err.kind == "conflict":
            return _page(request, session, etiqueta, formato, status=409, chosen=idioma,
                         error=CONFLICT_MESSAGES.get(str(code), err.message), reasons=reasons)
        return _page(request, session, etiqueta, formato, status=503, chosen=idioma, error=err.message)
    aviso = "creada" if result.get("created") else "existente"
    return RedirectResponse(f"/informes/{quote(str(result['id']), safe='')}?aviso={aviso}", status_code=303)
```

(El `id` devuelto por la API pasa por `quote`; la validación estricta con expresión regular del `id` la hace la ruta `/informes/{id}` de la Task 3.) Registrar el router en `app.py`. Crear `src/nicheradar/web/templates/nichos/investigar.html`:

```html
{% extends "base.html" %}
{% block title %}Iniciar investigación · NicheRadar{% endblock %}
{% block content %}
<p class="eyebrow">Iniciar investigación de flujo</p>
<h1 class="h1 h1--md">{{ label }} · {{ format_text }}</h1>
<p class="lead">Elige el idioma de la investigación. La competencia, los precios y las herramientas cambian por idioma, y un dossier en el idioma equivocado cuesta una investigación entera.</p>
{% if error %}<div class="note note--rose" role="alert">{{ error }}{% if reasons %}<ul>{% for r in reasons %}<li>{{ r }}</li>{% endfor %}</ul>{% endif %}</div>{% endif %}
<form class="stack" method="post" action="/nichos/investigar">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <input type="hidden" name="etiqueta" value="{{ label }}">
  <input type="hidden" name="formato" value="{{ format }}">
  <section class="card">
    <h2 class="h2">Idioma de las fichas del nicho</h2>
    {% for o in lang.options %}
    <label class="row"><span><input type="radio" name="idioma" value="{{ o.code }}"{% if chosen == o.code %} checked{% endif %}> {{ o.name }}{% if o.suggested %} <span class="chip chip--green">Sugerido</span>{% endif %}</span><span class="row__value">{{ o.share }}%</span></label>
    {% endfor %}
    {% if lang.unknown_share is not none %}<div class="row"><span class="row__label">Sin dato</span><span class="row__value">{{ lang.unknown_share }}% · no se puede elegir como idioma</span></div>{% endif %}
    <p class="caption">Si hay empate o predomina «sin dato», no se preselecciona nada y debes elegir tú. Si el nicho tiene fichas en dos idiomas relevantes, inicia una investigación por cada uno.</p>
  </section>
  <section class="card">
    <h2 class="h2">Qué pasa al iniciar</h2>
    <p class="muted">Se crea un encargo con clave nicho + formato + idioma. Claude Code lo reclama (60 min) e investiga en ese idioma. El dossier y el piloto heredan el idioma; no se cambia después. Cambiar de idioma exige una investigación nueva.</p>
  </section>
  {% if lang.no_choice %}<div class="note note--amber">Este nicho no tiene fichas con idioma conocido: no se puede iniciar la investigación todavía.</div>
  {% elif not chosen %}<div class="note note--amber">Elige un idioma para continuar.</div>{% endif %}
  <button class="btn btn--primary" type="submit"{% if lang.no_choice %} disabled{% endif %}>Iniciar investigación{% if chosen %} en {{ lang.options | selectattr("code", "equalto", chosen) | map(attribute="name") | first | default(chosen) | lower }}{% endif %}</button>
  <a class="btn btn--secondary" href="/nichos">Cancelar</a>
</form>
{% endblock %}
```

(La prueba exige el texto «Iniciar investigación en inglés» y el radio `name="idioma" value="en" checked`; con empate no debe haber ningún `checked` en el formulario.)

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_research.py tests/test_web_niches.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_research.py
git commit -m "feat: pantalla M8, elegir idioma e iniciar la investigación de un nicho"
```

---

### Task 3: Informe del dossier (M3 y M11)

**Files:**
- Create: `src/nicheradar/web/report.py`, `src/nicheradar/web/routes_reports.py`, `src/nicheradar/web/templates/informes/informe.html`, `src/nicheradar/web/templates/informes/estado.html`
- Modify: `src/nicheradar/web/app.py` (router), `tests/web_helpers.py` (`dossier_v3`, `report_detail`)
- Create: `tests/test_web_report.py`

**Interfaces:**
- Consumes: `render`, `current_session`, `usd`, `pct`, `local_datetime`, `chip`, `niches.DECISION_CHIP`; dominio `nicheradar.flow_research.contracts.calibration_total_hours` (leer su firma antes de usarla).
- Produces: `report.py`: `RECOMMENDATION = {"go": ("sí", "green"), "go_with_conditions": ("sí, con condiciones", "amber"), "no_go": ("no", "rose")}`, `CONFIDENCE_DOSSIER = {"low": "Baja", "medium": "Media", "high": "Alta"}`, `RIGHTS = {"cleared": "resueltos", "conditional": "con condiciones", "blocked": "bloqueados"}`, `safe_url(url: object) -> str | None` (solo `https://`), `subject_label(niche_label: str) -> tuple[str, bool]` (nombre legible y si es subnicho: quita `subniche:` y sustituye `_` por espacio con capitalización), `report_view(detail: dict, timezone: str) -> dict`, `status_view(detail: dict) -> dict`, `AVISOS_INFORME` (`creada`, `existente`, `piloto`); rutas `GET /informes/{id}`; en pruebas `dossier_v3(**over)` y `report_detail(status="listo", dossier=..., **over)`.

- [ ] **Step 1: Pruebas que fallan**

Antes de escribir `dossier_v3`, buscar en `tests/` un fixture válido de dossier-v3 (`grep -rn "dossier-v3" tests | head`) y **reutilizarlo** (importarlo o copiarlo reducido) en vez de inventar uno; el que se añada a `tests/web_helpers.py` debe pasar `DossierV3.model_validate` (comprobarlo en una prueba). Añadir:

```python
def dossier_v3(**over: object) -> dict[str, object]:
    """A valid dossier-v3 built from the existing test fixture (see tests/test_flow_research*.py)."""
    from tests.test_flow_research_v3 import valid_dossier_v3  # adjust to the real fixture name

    return valid_dossier_v3() | over


def report_detail(status: str = "listo", dossier: dict[str, object] | None = None, **over: object) -> dict[str, object]:
    base: dict[str, object] = flow_item(status) | {
        "evidence": {"gate": {"min_automation": 90, "max_human_minutes": 60, "max_calibration_hours": 40,
                              "block_high_policy_risk": True, "passed": True, "reasons": []}},
        "dossier": dossier if status == "listo" else None,
        "dossier_created_at": "2026-11-02T03:00:00Z" if status == "listo" else None,
    }
    return base | over
```

(Si el fixture real tiene otro nombre o módulo, cambiar la importación y dejarlo documentado en el informe del implementador; si no existe ninguno reutilizable, construir uno mínimo que valide con `DossierV3`.) Crear `tests/test_web_report.py` con estas pruebas:

```python
# tests/test_web_report.py
import httpx
import pytest

from nicheradar.flow_research.contracts import DossierV3
from nicheradar.web.report import RECOMMENDATION, safe_url, subject_label
from tests.web_helpers import HOSTILE, Api, dossier_v3, make_client, report_detail

ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
GET = ("GET", f"/api/v1/flow-research/{ID}")
STATUS = ("GET", "/api/v1/status")


def api_with(detail: dict[str, object]) -> Api:
    return Api({GET: (200, detail), STATUS: (200, {"radar_paused": True})})


def test_the_helper_dossier_is_a_valid_v3() -> None:
    DossierV3.model_validate(dossier_v3())


def test_safe_url_only_allows_https() -> None:
    assert safe_url("https://example.com/a") == "https://example.com/a"
    for bad in ("http://x.test", "javascript:alert(1)", "//x.test", "data:text/html,x", "", None, 5):
        assert safe_url(bad) is None


def test_subject_label_humanizes_subniches_only() -> None:
    assert subject_label("subniche:prehistoric_creatures") == ("Prehistoric Creatures", True)
    assert subject_label("historia militar explicada") == ("historia militar explicada", False)


def test_a_v3_report_shows_verdict_time_gates_budget_and_actions() -> None:
    dossier = dossier_v3()
    text = make_client(api_with(report_detail(dossier=dossier))).get(f"/informes/{ID}").text
    assert "INFORME" in text.upper() and "Listo" in text
    headline = RECOMMENDATION[dossier["verdict"]["recommendation"]][0]  # type: ignore[index]
    assert f": {headline}" in text
    assert dossier["verdict"]["thesis"] in text  # type: ignore[index]
    assert "Primeros" in text and "videos (calibración)" in text and "Cuando ya está en marcha (régimen)" in text
    assert "permitidos" in text and "permitidas" in text and "Derechos del material" in text
    assert "Lo que gastarías" in text and "Peor caso" in text
    assert f'href="/pilotos/autorizar?informe={ID}"' in text and "Lanzar piloto" in text
    assert "Posponer" in text and "Detalle (toca para abrir)" in text


def test_the_calibration_numbers_come_from_the_domain_helper() -> None:
    from nicheradar.flow_research.contracts import calibration_total_hours

    dossier = dossier_v3()
    model = DossierV3.model_validate(dossier)
    hours = calibration_total_hours(model.calibration)  # adjust to the helper's real signature
    text = make_client(api_with(report_detail(dossier=dossier))).get(f"/informes/{ID}").text
    assert f"{hours:.1f}".replace(".", ",") in text or str(round(hours)) in text


def test_a_failing_gate_is_marked_and_a_passing_one_too() -> None:
    dossier = dossier_v3()
    detail = report_detail(dossier=dossier)
    detail["evidence"]["gate"]["max_human_minutes"] = 1  # type: ignore[index]
    text = make_client(api_with(detail)).get(f"/informes/{ID}").text
    assert 'class="chip chip--rose">no pasa<' in text and 'class="chip chip--green">pasa<' in text


def test_a_subniche_report_adds_the_confidence_notice_and_hides_discard() -> None:
    detail = report_detail(dossier=dossier_v3(niche_label="subniche:prehistoric_creatures"),
                           niche_label="subniche:prehistoric_creatures")
    detail["evidence"]["source"] = "subniche"  # type: ignore[index]
    text = make_client(api_with(detail)).get(f"/informes/{ID}").text
    assert "Prehistoric Creatures" in text and "Qué tan firme es" in text
    assert "Descartar" not in text


def test_a_backlog_report_offers_discard_as_a_post_with_csrf() -> None:
    text = make_client(api_with(report_detail(dossier=dossier_v3()))).get(f"/informes/{ID}").text
    assert 'action="/nichos/decidir"' in text and 'name="decision" value="descartado"' in text
    assert 'name="csrf"' in text


def test_a_v1_or_v2_report_opens_with_the_old_dossier_notice() -> None:
    old = dossier_v3()
    for key in ("calibration", "steady_state_evidence"):
        old.pop(key, None)
    old["schema_version"] = "dossier-v2"
    old["verdict"] = {k: v for k, v in old["verdict"].items() if k != "conditions"}  # type: ignore[union-attr]
    text = make_client(api_with(report_detail(dossier=old))).get(f"/informes/{ID}").text
    assert "Dossier anterior" in text and "no separa calibración" in text
    v1 = dict(old, schema_version="dossier-v1")
    v1.pop("rights", None)
    v1.pop("automation_plan", None)
    page = make_client(api_with(report_detail(dossier=v1))).get(f"/informes/{ID}")
    assert page.status_code == 200 and "Dossier anterior" in page.text and "Derechos del material" in page.text
    assert "sin evaluar" in page.text


def test_optional_null_fields_do_not_break_the_report() -> None:
    dossier = dossier_v3()
    dossier["steady_state_evidence"] = {"basis": "estimate", "reference_channel": None,
                                        "reference_minutes_per_video": None, "reference_sample_videos": None,
                                        "format_match": None}
    page = make_client(api_with(report_detail(dossier=dossier))).get(f"/informes/{ID}")
    assert page.status_code == 200 and "estimación" in page.text.lower()


def test_hostile_dossier_text_is_escaped_and_unsafe_links_are_plain_text() -> None:
    dossier = dossier_v3()
    dossier["verdict"]["thesis"] = HOSTILE  # type: ignore[index]
    dossier["verdict"]["main_risks"] = [HOSTILE]  # type: ignore[index]
    dossier["competitors"][0]["name"] = HOSTILE  # type: ignore[index]
    dossier["sources"] = [{"id": "s1", "url": "javascript:alert(1)", "title": HOSTILE, "accessed_on": "2026-11-01"},
                          {"id": "s2", "url": "https://ok.example/x", "title": "ok", "accessed_on": "2026-11-01"}]
    text = make_client(api_with(report_detail(dossier=dossier))).get(f"/informes/{ID}").text
    assert "<script>alert(1)</script>" not in text and text.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 3
    assert 'href="javascript:' not in text
    assert 'href="https://ok.example/x" rel="noopener noreferrer nofollow" target="_blank"' in text


@pytest.mark.parametrize("status", ["pendiente", "en_curso"])
def test_a_running_order_shows_its_state_and_no_report(status: str) -> None:
    text = make_client(api_with(report_detail(status))).get(f"/informes/{ID}").text
    assert ("En cola" if status == "pendiente" else "Investigando") in text
    assert "Lanzar piloto" not in text and "Claude Code" in text


def test_a_rejected_order_lists_the_problems_escaped() -> None:
    detail = report_detail("rechazado", rejection={"problems": [{"path": "budget", "message": HOSTILE}],
                                                    "at": "2026-11-02T03:00:00Z"})
    text = make_client(api_with(detail)).get(f"/informes/{ID}").text
    assert "Rechazada" in text and "&lt;script&gt;" in text and "<script>alert(1)</script>" not in text


def test_a_listo_order_without_a_dossier_is_handled() -> None:
    page = make_client(api_with(report_detail("listo", dossier=None))).get(f"/informes/{ID}")
    assert page.status_code == 200 and "no está disponible" in page.text


def test_a_bad_id_is_a_404_and_never_reaches_the_api() -> None:
    api = api_with(report_detail(dossier=dossier_v3()))
    web = make_client(api)
    for bad in ("../x", "abc", "f0c90924-295a-4136-a0fb-d3fb2c3eacc6/x", "%2e%2e"):
        assert web.get(f"/informes/{bad}").status_code == 404
    assert api.count(*GET) == 0


def test_unknown_id_and_api_outage() -> None:
    api = Api({GET: (404, {"detail": {"code": "not_found", "message": "x"}}), STATUS: (200, {"radar_paused": True})})
    assert make_client(api).get(f"/informes/{ID}").status_code == 404

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    down = make_client(Api({GET: boom, STATUS: (200, {"radar_paused": True})})).get(f"/informes/{ID}")
    assert down.status_code == 503 and "API no disponible" in down.text


def test_the_notice_comes_from_fixed_keys_and_the_pilot_id_is_validated() -> None:
    web = make_client(api_with(report_detail(dossier=dossier_v3())))
    assert "Investigación creada" in web.get(f"/informes/{ID}", params={"aviso": "creada"}).text
    ok = web.get(f"/informes/{ID}", params={"aviso": "piloto", "piloto": "pil_20261102_historia-militar"}).text
    assert "pil_20261102_historia-militar" in ok
    bad = web.get(f"/informes/{ID}", params={"aviso": "piloto", "piloto": HOSTILE}).text
    assert "evil.test" not in bad and "<script>" not in bad
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_report.py -q 2>&1 | tail -6`
Expected: FAIL (`ModuleNotFoundError: nicheradar.web.report`).

- [ ] **Step 3: Implementar el modelo de vista**

Crear `src/nicheradar/web/report.py`. Reglas del modelo de vista (el implementador las traduce a código, con los textos del Figma M3/M11 entre comillas):

- `safe_url(url)`: devuelve `url` solo si es `str`, empieza por `https://` y no contiene espacios ni caracteres de control; si no, `None`.
- `subject_label(niche_label)`: si empieza por `subniche:` → `(slug.replace("_", " ").title(), True)`; si no `(niche_label, False)`.
- `report_view(detail, timezone)` (solo `status == "listo"` y `dossier` no nulo; si falta el dossier devolver `{"missing": True}`), con estas secciones, todas tolerantes a campos ausentes (`.get`) y a v1/v2:
  - `eyebrow`: «INFORME · LISTO»; `title`: f«{nombre}: {frase}» con `RECOMMENDATION[recommendation][0]`; `thesis` (texto plano).
  - `firm` (solo si `evidence.get("source") == "subniche"`): «Qué tan firme es», confianza `CONFIDENCE_DOSSIER`, y la fecha de la medición con `local_datetime` leyendo la clave real de `flow_research/subniche_evidence.py` (leerla), más la nota «El ingreso es una estimación por canal típico. Los competidores vienen de listados de terceros, sin confirmar en YouTube.»; para backlog, «Idioma del mercado» con `evidence["language_mix"]` si existe (`Inglés 80% · Español 15% · Sin dato 5%`).
  - `time`: régimen = suma de `production_flow[*].human_minutes_per_video` (siempre); si `schema_version == "dossier-v3"` y hay `calibration`: `videos`, minutos por video de calibración = suma de `minutes_by_step`, total de los videos (h), `setup_hours`, horas de calibración = `calibration_total_hours(...)` del dominio (**no recalcular**), criterio de salida (`exit_criterion.statement`), y la evidencia del régimen (`steady_state_evidence.basis`: `measured` → «Medido en {reference_channel}: {reference_sample_videos} videos», `mapped_flow_equivalent` → «Equivalente a un flujo ya mapeado», `estimate` → «Estimación»). Para v1/v2: aviso «Dossier anterior: no separa calibración de régimen.» y solo la suma de régimen.
  - `gates` (lista de `(texto, "pasa"|"no pasa"|"sin evaluar")`): «Minutos por video, ya en marcha: X de {max_human_minutes} permitidos» y, si v3, «Horas de calibración: Y de {max_calibration_hours} permitidas», «Derechos del material: {RIGHTS[...]}» (`pasa` si `cleared`, `conditional`→`pasa` con la nota «con condiciones», `blocked`→`no pasa`; sin `rights` → «Derechos del material: sin evaluar» con `sin evaluar`). Los máximos salen de `evidence["gate"]` (`max_human_minutes`, `max_calibration_hours`).
  - `budget`: `totals.low/likely/high` con `usd(...)` («Bajo», «Probable», «Peor caso (tope)»), `horizon` (`short|medium`) y el aviso «Cifras del informe; no incluyen tu tiempo.».
  - `avisos`: `main_risks`, `unknowns`, `conditions` (si v3), `policy_risk.summary` y `rights.conditions`, cada uno como lista de textos con su encabezado; contador «N avisos».
  - `tools`: cada herramienta (`name`, `phase`, `purpose`, `pricing`, `cheaper_alternative`), contador «N herramientas».
  - `competitors` (`name`, `subscribers` con `compact`, `channel_url` con `safe_url`) y `sources` (`title`, `url` con `safe_url`, `accessed_on`), contador «N canales · M enlaces».
  - `actions`: `launch_href = f"/pilotos/autorizar?informe={id}"`, `postpone_href = "/subnichos" si es subnicho, si no "/nichos"`, `can_discard = not es_subnicho`, con `niche_label` y `format` para el formulario de descarte.
- `status_view(detail)`: para `pendiente` («En cola»), `en_curso` («Investigando», con la nota «Claude Code la atiende en su sesión; el encargo se reclama 60 minutos») y `rechazado` («Rechazada» con `rejection.problems` como lista `path: message`; sin `rejection` → texto genérico) y para `listo` sin dossier («El dossier no está disponible»).
- `AVISOS_INFORME = {"creada": ("Investigación creada. Claude Code la atenderá en la próxima sesión.", "green"), "existente": ("Ya había una investigación activa con esa clave.", "amber"), "piloto": ("Piloto autorizado.", "green")}`; el identificador del piloto solo se muestra si coincide con `^pil_\d{8}_[a-z0-9_-]+$`.

Crear `src/nicheradar/web/routes_reports.py` (ruta `GET /informes/{id}`: validar con `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` **antes** de llamar a la API; 404 con `error.html` si no coincide; `ApiError` → 404 o 503 con `with_radar=False`; plantilla `informes/informe.html` si `listo` con dossier, `informes/estado.html` en otro caso; encabezado `Cache-Control` ya lo pone el middleware). Registrar el router en `app.py`. Crear las plantillas con los textos de M3/M11: bloques «Qué tan firme es», «Cuánto tarda cada video» (calibración y régimen), «Cuándo pasas a régimen» (`exit_criterion.statement`) con las filas de compuertas como `chip` (`pasa` en `green`, `no pasa` en `rose`, `sin evaluar` en `neutral`), «Lo que gastarías», «Detalle (toca para abrir)» con tres `<details class="acc">` («Dónde corre cada herramienta», «Lo que debes saber antes de decidir», «Competidores y fuentes»), enlaces solo con `safe_url` y `rel="noopener noreferrer nofollow" target="_blank"`, y las acciones: botón primario «Lanzar piloto» (enlace), «Posponer» (enlace secundario) y, si `can_discard`, un formulario `POST /nichos/decidir` con `csrf`, `etiqueta`, `formato`, `decision=descartado`, `volver=/nichos` y botón «Descartar». Reutilizar `chip` y las clases existentes (`.card .rows .row .acc .note`); si hace falta una barra de proporción por etapa (Figma M11 «Guion · Voz · Visuales…»), omitirla en este corte y anotarlo.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_report.py tests/test_web_niches.py tests/test_web_research.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_report.py
git commit -m "feat: pantallas M3 y M11, informe del dossier con calibración, régimen y compuertas"
```

---

### Task 4: Autorizar piloto (M4 y M12)

**Files:**
- Create: `src/nicheradar/web/pilots_form.py`, `src/nicheradar/web/routes_pilots.py`, `src/nicheradar/web/templates/pilotos/autorizar.html`
- Modify: `src/nicheradar/web/app.py` (router), `src/nicheradar/web/report.py` (reutilizar el resumen de tiempo y compuertas), `tests/web_helpers.py` (`pilot_item`)
- Create: `tests/test_web_pilot_authorize.py`

**Interfaces:**
- Consumes: `report.report_view` (secciones `time`, `gates`, `budget`, `firm`, `title`) y `subject_label`, `render`, `current_session`, `ApiClient`.
- Produces: en `pilots_form.py`: `CHANNEL_RE = re.compile(r"^canal-[a-z0-9-]{1,40}$")`, `PILOT_ID_RE`, `Defaults(max_videos=10, valid_days=14, close_after=2)`, `busy_channels(pilots: list[dict]) -> set[str]` (canales de pilotos cuyo estado no es `cerrado` ni `cancelado`), `parse_form(data: Mapping[str, str]) -> tuple[dict | None, dict[str, str]]` (valores válidos o errores por campo: `max_videos` 1–50, `valid_days` 1–60, `close_after` 1–5, `canal` vacío o `CHANNEL_RE`), `budget_body(dossier: dict, max_videos: int, informe_id: str) -> dict` (`low/likely/high` redondeados a 2 decimales con `Decimal` y orden `low ≤ likely ≤ high`; `basis` = f«Presupuesto del informe {id}: probable {usd(likely)}.»), `GATE_MESSAGES: dict[str, str]` (por `detail.code`); rutas `GET /pilotos/autorizar?informe=<id>` y `POST /pilotos/autorizar`; en pruebas `pilot_item(...)`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/web_helpers.py`:

```python
def pilot_item(pilot_id: str = "pil_20261102_historia", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "pilot_id": pilot_id, "status": "autorizado", "niche_label": "historia militar explicada",
        "format": "long", "target_channel": "canal-historias", "authorized_at": "2026-11-02T03:00:00Z",
        "last_report_at": None, "channel_last_contact_at": None,
        "totals": {"videos": 0, "published": 0, "measured": 0, "by_stage": {}, "spent_usd": 0,
                   "equivalent_usd": 0, "machine_minutes": 0, "machine_minutes_complete": True},
        "proposal": {"action": "sin_datos_suficientes", "reason": "x"}, "needs_decision": False,
    }
    return base | over
```

Crear `tests/test_web_pilot_authorize.py` con estas pruebas (usar `ID`, `GET`, `STATUS`, `api_with` como en `test_web_report.py`, más `PILOTS = ("GET", "/api/v1/pilots")` y `AUTH = ("POST", "/api/v1/pilots")`; todas las pruebas autenticadas parten de `make_client`):

```python
# tests/test_web_pilot_authorize.py
import json

import httpx
import pytest

from nicheradar.web.pilots_form import busy_channels, budget_body, parse_form
from tests.web_helpers import (
    HOSTILE, Api, csrf_of, dossier_v3, make_client, pilot_item, report_detail,
)

ID = "f0c90924-295a-4136-a0fb-d3fb2c3eacc6"
GET = ("GET", f"/api/v1/flow-research/{ID}")
PILOTS = ("GET", "/api/v1/pilots")
AUTH = ("POST", "/api/v1/pilots")
STATUS = ("GET", "/api/v1/status")
URL = f"/pilotos/autorizar?informe={ID}"


def api_with(detail: dict[str, object] | None = None, pilots: list[dict[str, object]] | None = None,
             **extra: object) -> Api:
    routes: dict[tuple[str, str], object] = {
        GET: (200, detail or report_detail(dossier=dossier_v3())),
        PILOTS: (200, {"items": pilots or []}),
        STATUS: (200, {"radar_paused": True}),
    }
    routes.update(extra)  # type: ignore[arg-type]
    return Api(routes)  # type: ignore[arg-type]


def test_busy_channels_ignore_closed_and_cancelled_pilots() -> None:
    items = [pilot_item(target_channel="canal-a", status="en_ejecucion"),
             pilot_item(target_channel="canal-b", status="cerrado"),
             pilot_item(target_channel="canal-c", status="cancelado"),
             pilot_item(target_channel=None, status="autorizado")]
    assert busy_channels(items) == {"canal-a"}


def test_parse_form_enforces_the_api_ranges_and_reports_field_errors() -> None:
    ok, errors = parse_form({"max_videos": "10", "valid_days": "14", "close_after": "2", "canal": ""})
    assert errors == {} and ok == {"max_videos": 10, "valid_days": 14, "close_after": 2, "canal": None}
    for field, bad in (("max_videos", "0"), ("max_videos", "51"), ("valid_days", "61"), ("close_after", "6"),
                       ("max_videos", "x"), ("canal", "Canal Uno"), ("canal", "canal-" + "a" * 41)):
        data = {"max_videos": "10", "valid_days": "14", "close_after": "2", "canal": ""} | {field: bad}
        assert field in parse_form(data)[1], (field, bad)


def test_budget_body_rounds_money_to_two_decimals_and_keeps_order() -> None:
    dossier = dossier_v3()
    dossier["budget"]["totals"] = {"low": 2.994, "likely": 9.294, "high": 40.999}  # type: ignore[index]
    body = budget_body(dossier, 10, ID)
    assert body["currency"] == "USD" and body["max_videos"] == 10
    assert (body["low"], body["likely"], body["high"]) == ("2.99", "9.29", "41.00") or (
        float(body["low"]), float(body["likely"]), float(body["high"])) == (2.99, 9.29, 41.0)
    assert ID in body["basis"]


def test_the_form_shows_what_is_fixed_the_budget_and_the_time_summary() -> None:
    text = make_client(api_with()).get(URL).text
    assert "Antes de lanzar, fija las reglas" in text and "Lo que fijes aquí no cambia después." in text
    assert 'name="max_videos"' in text and 'name="valid_days"' in text and 'name="close_after"' in text
    assert "Idioma (fijado en la investigación)" in text and "Presupuesto" in text
    assert "Cadencia" not in text and "Preparación (días)" not in text
    assert "Reglas de parada" in text and 'action="/pilotos/autorizar"' in text and 'name="csrf"' in text
    assert "Autorizar piloto" in text


def test_a_busy_channel_is_listed_as_taken_and_cannot_be_chosen() -> None:
    api = api_with(pilots=[pilot_item(target_channel="canal-historias", status="en_ejecucion")])
    text = make_client(api).get(URL).text
    assert "Ocupado: ya tiene un piloto activo" in text and "canal-historias" in text
    assert 'value="canal-historias" disabled' in text or 'value="canal-historias"  disabled' in text


def test_a_subniche_report_shows_the_m12_evidence_block() -> None:
    detail = report_detail(dossier=dossier_v3(niche_label="subniche:prehistoric_creatures"),
                           niche_label="subniche:prehistoric_creatures")
    detail["evidence"]["source"] = "subniche"  # type: ignore[index]
    text = make_client(api_with(detail)).get(URL).text
    assert "Prehistoric Creatures" in text and "Evidencia de un subnicho" in text
    assert "esa compuerta no aplica" in text.replace("\n", " ")


def test_only_finished_reports_can_be_authorized_and_ids_are_validated() -> None:
    api = api_with(report_detail("en_curso"))
    web = make_client(api)
    assert web.get(URL).status_code == 409 and "todavía no está listo" in web.get(URL).text
    assert web.get("/pilotos/autorizar").status_code == 404
    assert web.get("/pilotos/autorizar?informe=../x").status_code == 404


def test_the_no_go_and_failed_gate_checkboxes_appear_only_when_needed() -> None:
    clean = make_client(api_with()).get(URL).text
    assert 'name="accept_no_go"' not in clean and 'name="accept_gate_failure"' not in clean
    dossier = dossier_v3()
    dossier["verdict"]["recommendation"] = "no_go"  # type: ignore[index]
    nogo = make_client(api_with(report_detail(dossier=dossier))).get(URL).text
    assert 'name="accept_no_go"' in nogo
    failing = report_detail(dossier=dossier_v3())
    failing["evidence"]["gate"]["passed"] = False  # type: ignore[index]
    assert 'name="accept_gate_failure"' in make_client(api_with(failing)).get(URL).text


def post(web, token: str, **over: str):  # type: ignore[no-untyped-def]
    data = {"csrf": token, "informe": ID, "max_videos": "10", "valid_days": "14", "close_after": "2", "canal": ""}
    return web.post("/pilotos/autorizar", data=data | over)


def test_authorizing_posts_server_derived_fields_and_redirects_to_the_report() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"pilot_id": "pil_20261102_historia", "status": "autorizado", "package": {}})

    web = make_client(api_with(**{AUTH: accept}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token, niche_label="OTRA", format="shorts", authorized_by="otro", canal="canal-nuevo")
    assert response.status_code == 303
    assert response.headers["location"] == f"/informes/{ID}?aviso=piloto&piloto=pil_20261102_historia"
    body = json.loads(bodies[0])
    assert body["niche_label"] == "historia militar explicada" and body["format"] == "long"
    assert body["dossier_request_id"] == ID and body["authorized_by"] == "propietario (web)"
    assert body["max_videos"] if "max_videos" in body else body["budget"]["max_videos"] == 10
    assert body["budget"]["max_videos"] == 10 and body["valid_days"] == 14
    assert body["close_after_failed_milestones"] == 2 and body["target_channel"] == "canal-nuevo"
    assert body["accept_no_go"] is False and body["accept_gate_failure"] is False


def test_an_empty_channel_means_a_new_channel_and_omits_target_channel() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"pilot_id": "pil_20261102_x", "status": "autorizado", "package": {}})

    web = make_client(api_with(**{AUTH: accept}))
    token = csrf_of(web.get(URL).text)
    post(web, token)
    assert "target_channel" not in json.loads(bodies[0])


def test_a_bad_csrf_or_out_of_range_value_never_reaches_the_api() -> None:
    api = api_with(**{AUTH: (201, {"pilot_id": "pil_20261102_x", "status": "autorizado", "package": {}})})
    web = make_client(api)
    token = csrf_of(web.get(URL).text)
    assert post(web, "wrong").status_code == 403 and web.post("/pilotos/autorizar").status_code == 403
    for field, bad in (("max_videos", "99"), ("valid_days", "0"), ("close_after", "9"), ("canal", "NO válido")):
        response = post(web, token, **{field: bad})
        assert response.status_code == 422, (field, bad)
    assert api.count(*AUTH) == 0


def test_the_form_keeps_what_was_typed_when_validation_fails() -> None:
    web = make_client(api_with())
    token = csrf_of(web.get(URL).text)
    text = post(web, token, max_videos="99", valid_days="21").text
    assert 'value="99"' in text and 'value="21"' in text and "1 a 50" in text


@pytest.mark.parametrize(
    ("code", "needle"),
    [("channel_busy", "ya tiene un piloto activo"), ("no_go_requires_acceptance", "no-go"),
     ("dossier_not_ready", "todavía no está listo"), ("language_unknown", "idioma"),
     ("niche_mismatch", "no corresponde")],
)
def test_api_conflicts_map_to_clear_messages_and_keep_the_form(code: str, needle: str) -> None:
    web = make_client(api_with(**{AUTH: (409, {"detail": {"code": code, "message": "x"}})}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and needle in response.text and 'name="max_videos"' in response.text


def test_failed_gate_reasons_from_the_api_are_listed_escaped() -> None:
    detail = {"code": "gate_failed", "message": "x", "reasons": [{"gate": "rights", "message": HOSTILE}]}
    web = make_client(api_with(**{AUTH: (409, {"detail": detail})}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 409 and "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_package_problems_from_a_422_are_listed_escaped() -> None:
    body = {"accepted": False, "problems": [{"path": "budget", "message": HOSTILE}]}
    web = make_client(api_with(**{AUTH: (422, body)}))
    token = csrf_of(web.get(URL).text)
    response = post(web, token)
    assert response.status_code == 422 and "&lt;script&gt;" in response.text


def test_the_accept_flags_are_sent_only_when_the_checkbox_is_checked() -> None:
    bodies: list[bytes] = []

    def accept(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"pilot_id": "pil_20261102_x", "status": "autorizado", "package": {}})

    dossier = dossier_v3()
    dossier["verdict"]["recommendation"] = "no_go"  # type: ignore[index]
    web = make_client(api_with(report_detail(dossier=dossier), **{AUTH: accept}))
    token = csrf_of(web.get(URL).text)
    post(web, token, accept_no_go="1")
    assert json.loads(bodies[0])["accept_no_go"] is True


def test_api_outage_on_the_page_and_on_the_post() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    down = make_client(Api({GET: boom, PILOTS: (200, {"items": []}), STATUS: (200, {"radar_paused": True})}))
    assert down.get(URL).status_code == 503 and "API no disponible" in down.get(URL).text
    web = make_client(api_with(**{AUTH: boom}))
    token = csrf_of(web.get(URL).text)
    assert post(web, token).status_code == 503


def test_when_only_the_pilot_list_fails_the_form_still_opens_with_a_warning() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = Api({GET: (200, report_detail(dossier=dossier_v3())), PILOTS: boom, STATUS: (200, {"radar_paused": True})})
    page = make_client(api).get(URL)
    assert page.status_code == 200 and "No se pudo comprobar qué canales están ocupados" in page.text
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_pilot_authorize.py -q 2>&1 | tail -6`
Expected: FAIL (`ModuleNotFoundError: nicheradar.web.pilots_form`).

- [ ] **Step 3: Implementar**

Crear `src/nicheradar/web/pilots_form.py` con `CHANNEL_RE`, `PILOT_ID_RE = re.compile(r"^pil_\d{8}_[a-z0-9_-]+$")`, `busy_channels`, `parse_form` (rangos de la API; devuelve errores con textos «1 a 50», «1 a 60», «1 a 5», «Usa el formato canal-nombre»), `budget_body` (usar `Decimal(str(valor)).quantize(Decimal("0.01"), ROUND_HALF_UP)`; si tras redondear `low > likely` o `likely > high`, ajustar `likely`/`high` al valor mayor para respetar el orden; serializar como cadena o número con 2 decimales, según lo que acepte el modelo `Money` de la API —leer `pilots/contracts.py`—) y `GATE_MESSAGES` (`channel_busy`: «Ese canal ya tiene un piloto activo.», `no_go_requires_acceptance`: «El informe recomienda no-go: marca la casilla para aceptarlo bajo tu responsabilidad.», `dossier_not_ready`: «El informe todavía no está listo.», `language_unknown`: «El informe no tiene un idioma conocido: inicia una investigación nueva con idioma.», `niche_mismatch`: «El informe no corresponde a ese nicho.», `gate_failed`: «El informe no pasa una compuerta: revisa los motivos.», `bad_transition`: «El piloto que reemplazas ya no se puede reemplazar.»).

Crear `src/nicheradar/web/routes_pilots.py`:

- `GET /pilotos/autorizar?informe=<id>`: validar el id con la misma expresión regular de la Task 3 (si no, 404); `GET /flow-research/{id}` (error → 404/503, `with_radar=False`); si el estado no es `listo` o no hay dossier → 409 con «El informe todavía no está listo»; `GET /pilots?limit=100` (si falla, seguir con aviso «No se pudo comprobar qué canales están ocupados.» y sin canales ocupados); construir la vista con `report.report_view` (secciones de tiempo, compuertas, presupuesto y el bloque M12 «Evidencia de un subnicho» si `evidence.source == "subniche"`: «Viene de la medición de YouTube del {fecha} (hace N días), con confianza {…}. No hay puntajes de Opportunity ni de automatización, así que esa compuerta no aplica. Las de tiempo y derechos sí.») y los booleanos `needs_no_go = recommendation == "no_go"` y `needs_gate = not evidence.gate.passed or las compuertas calculadas fallan`.
- `POST /pilotos/autorizar`: sesión + CSRF (403 sin llamar a la API); validar `informe` (404); `parse_form` (errores → re-renderizar el formulario con 422 conservando los valores); volver a pedir el informe a la API y **derivar en el servidor** `niche_label`, `format`, `dossier_request_id`, presupuesto; ignorar cualquier `niche_label`, `format` o `authorized_by` del formulario; cuerpo = `{niche_label, format, dossier_request_id, budget: budget_body(...), authorized_by: "propietario (web)", close_after_failed_milestones, valid_days, accept_no_go: casilla marcada, accept_gate_failure: casilla marcada}` más `target_channel` solo si el campo no está vacío (el valor `canal-nuevo` del campo de texto es un canal real; «Canal nuevo» sin texto = omitir); `ApiError`: `conflict` → 409 con `GATE_MESSAGES[detail.code]` y, si `detail.reasons`, la lista escapada; `invalid` (422) → 422 con la lista de `problems` (`path: message`) escapada; otros → 503 con `err.message`; **siempre re-renderizar el formulario con lo escrito**. Éxito → `RedirectResponse(f"/informes/{id}?aviso=piloto&piloto={pilot_id}")` solo si `pilot_id` cumple `PILOT_ID_RE`; si no, aviso `piloto` sin identificador.

Crear `src/nicheradar/web/templates/pilotos/autorizar.html` con los textos de M4/M12: «AUTORIZAR PILOTO», «Antes de lanzar, fija las reglas», «Lo que fijes aquí no cambia después.», bloque «Nicho» (`{{ title_label }} · {{ formato }}` y «Se toma del informe listo.»), el bloque de evidencia de subnicho (M12), «Idioma (fijado en la investigación)», «Canal destino» con un radio «Canal nuevo (sin nombre todavía)» y un campo de texto `canal` con la lista de canales ocupados como radios deshabilitados `value="canal-…" disabled` con «Ocupado: ya tiene un piloto activo», «Tope de videos» (`max_videos`, «1 a 50»), «Vigencia (días)» (`valid_days`, «Editable ahora»), «Hitos fallidos para cerrar» (`close_after`, «1 a 5. Solo se elige ahora.»), resumen de tiempo y compuertas (parcial compartido con el informe), «Presupuesto de {max_videos} videos» con bajo/probable/peor caso, «Reglas de parada» (texto: «Se usan las reglas por defecto del formato: retención, exploración e ingresos. Las que se pueden medir se comparan solas.»), las casillas condicionales `accept_no_go` y `accept_gate_failure` (solo si hacen falta, con texto explícito «Acepto lanzarlo aunque…»), botón «Autorizar piloto» y enlace «Cancelar» al informe. Los valores escritos se conservan; los errores de campo salen junto a cada campo; no se muestran `Cadencia`, `Preparación (días)` ni «Receta del método». Reutilizar `chip` y las clases existentes. Registrar el router en `app.py`.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_pilot_authorize.py tests/test_web_report.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests/web_helpers.py tests/test_web_pilot_authorize.py
git commit -m "feat: pantallas M4 y M12, autorizar un piloto desde un informe"
```

---

### Task 5: Hoy (M1 y M14)

**Files:**
- Create: `src/nicheradar/web/today.py`, `src/nicheradar/web/routes_today.py`, `src/nicheradar/web/templates/hoy.html`
- Modify: `src/nicheradar/web/routes_auth.py` (quitar la ruta `GET /` provisional que redirige a `/subnichos`), `src/nicheradar/web/app.py` (router), `src/nicheradar/web/format.py` (`spanish_date`), `tests/test_web_session.py` (la prueba que espera la redirección a `/subnichos` pasa a esperar la página «Hoy»)
- Create: `tests/test_web_today.py`; Modify: `tests/test_web_format.py`

**Interfaces:**
- Consumes: `niches.card`/`research_index`, `subniches.card`, `format.usd`, `render`, `current_session`, `ApiClient`.
- Produces: `format.spanish_date(moment: datetime, timezone: str) -> str` (`"Domingo 25 de octubre"`, días y meses en español); `today.py`: `PILOT_ATTENTION` (`needs_decision` → «Decide si sigue o cierra»; `autorizado` → «Falta entregar el paquete al canal»), `attention_cards(pilots: list[dict]) -> list[dict]`, `ready_reports(flows: list[dict], pilots: list[dict]) -> list[dict]` (informes `listo` sin piloto abierto con la misma `niche_label` y `format`; como mucho 3), `top_niches(items, research_items) -> list[dict]` (los 3 primeros con puntaje, usando `niches.card`), `top_subniches(items) -> list[dict]` (finalistas con medición primero; 3), `today_view(sources: dict) -> dict` donde cada fuente puede ser `None` (fallida); ruta `GET /`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/test_web_format.py`:

```python
from datetime import datetime, timezone

from nicheradar.web.format import spanish_date


def test_spanish_date_names_the_weekday_and_month_in_the_local_timezone() -> None:
    moment = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)  # Sunday evening in Lima
    assert spanish_date(moment, "America/Lima") == "Domingo 1 de noviembre"
    assert spanish_date(moment, "UTC") == "Lunes 2 de noviembre"
```

Crear `tests/test_web_today.py`:

```python
# tests/test_web_today.py
import httpx

from nicheradar.web.today import ready_reports, top_niches
from tests.web_helpers import (
    HOSTILE, Api, flow_item, make_client, niche_item, pilot_item, subniche_item,
)

NICHES = ("GET", "/api/v1/market/niches")
FLOW = ("GET", "/api/v1/flow-research")
PILOTS = ("GET", "/api/v1/pilots")
SUBS = ("GET", "/api/v1/subniches")
STATUS = ("GET", "/api/v1/status")


def full_api(**over: object) -> Api:
    routes: dict[tuple[str, str], object] = {
        STATUS: (200, {"radar_paused": True, "timezone": "America/Lima"}),
        NICHES: (200, {"items": [niche_item(f"n{i}", opportunity={"version": "v1", "value": 90.0 - i, "state": "scored",
                                                                  "components": {}, "components_used": []})
                                 for i in range(5)], "total": 5, "limit": 3, "offset": 0}),
        FLOW: (200, {"items": []}),
        PILOTS: (200, {"items": []}),
        SUBS: (200, {"items": [subniche_item("uno"), subniche_item("dos", finalist=False)]}),
    }
    routes.update(over)  # type: ignore[arg-type]
    return Api(routes)  # type: ignore[arg-type]


def boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def test_ready_reports_exclude_those_with_an_open_pilot_and_cap_at_three() -> None:
    flows = [flow_item("listo", id=f"{i}" * 8 + "-1111-1111-1111-111111111111", niche_label=f"n{i}") for i in range(5)]
    pilots = [pilot_item(niche_label="n0", status="en_ejecucion"), pilot_item("pil_20261102_b", niche_label="n1", status="cerrado")]
    labels = [r["label"] for r in ready_reports(flows, pilots)]
    assert labels == ["n1", "n2", "n3"]  # n0 has an open pilot; a closed pilot does not block


def test_top_niches_skip_unscored_and_take_three() -> None:
    items = [niche_item("a"), niche_item("b", opportunity={"version": "v1", "value": None, "state": "insufficient_evidence",
                                                           "components": {}, "components_used": []}),
             niche_item("c"), niche_item("d"), niche_item("e")]
    assert [c["label"] for c in top_niches(items, [])] == ["a", "c", "d"]


def test_the_home_needs_a_session_and_is_the_landing_page() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    response = TestClient(create_app(settings()), follow_redirects=False).get("/")
    assert response.status_code == 303 and response.headers["location"].startswith("/login")
    page = make_client(full_api()).get("/")
    assert page.status_code == 200 and ">Hoy<" in page.text


def test_the_home_shows_the_date_and_the_four_cards() -> None:
    text = make_client(full_api()).get("/").text
    assert "3 nichos que merecen tu atención" in text
    assert "Subnichos medidos" in text and "Informes listos" in text
    assert text.count('class="card"') >= 3
    assert 'href="/nichos"' in text and 'href="/subnichos"' in text


def test_pilots_needing_something_are_listed_as_text_with_a_disabled_pilots_link() -> None:
    pilots = [pilot_item("pil_20261102_a", needs_decision=True, status="decision_pendiente"),
              pilot_item("pil_20261102_b", status="autorizado", target_channel="canal-b")]
    text = make_client(full_api(**{PILOTS: (200, {"items": pilots})})).get("/").text
    assert "2 pilotos necesitan algo de ti" in text
    assert "Decide si sigue o cierra" in text and "Falta entregar el paquete al canal" in text
    assert "Ver pilotos" in text and "Próximamente" in text


def test_with_no_pilots_needing_attention_the_card_says_so() -> None:
    assert "Ningún piloto necesita algo de ti" in make_client(full_api()).get("/").text


def test_a_ready_report_without_a_pilot_gets_a_link_to_its_report() -> None:
    flows = [flow_item("listo", id="f0c90924-295a-4136-a0fb-d3fb2c3eacc6", niche_label="n0")]
    text = make_client(full_api(**{FLOW: (200, {"items": flows})})).get("/").text
    assert 'href="/informes/f0c90924-295a-4136-a0fb-d3fb2c3eacc6"' in text


def test_each_source_failing_degrades_only_its_own_card() -> None:
    for key, needle in ((PILOTS, "Pilotos"), (NICHES, "nichos"), (FLOW, "Informes"), (SUBS, "Subnichos")):
        page = make_client(full_api(**{key: boom})).get("/")
        assert page.status_code == 200, key
        assert "no disponible" in page.text, key
    everything = Api({STATUS: (200, {"radar_paused": True}), NICHES: boom, FLOW: boom, PILOTS: boom, SUBS: boom})
    page = make_client(everything).get("/")
    assert page.status_code == 200 and page.text.count("no disponible") >= 4


def test_hostile_text_in_any_source_is_escaped() -> None:
    api = full_api(**{
        NICHES: (200, {"items": [niche_item(HOSTILE)], "total": 1, "limit": 3, "offset": 0}),
        SUBS: (200, {"items": [subniche_item("x", label=HOSTILE)]}),
        PILOTS: (200, {"items": [pilot_item(niche_label=HOSTILE, needs_decision=True, status="decision_pendiente")]}),
    })
    text = make_client(api).get("/").text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;alert(1)&lt;/script&gt;" in text
```

En `tests/test_web_session.py`, la prueba `test_after_login_the_home_redirects_to_the_subniche_list` se reemplaza por una que compruebe que, con sesión, `GET /` responde 200 (usar `make_client` con un `Api` mínimo que contesta 404 a todo: «Hoy» degrada, no se rompe).

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_web_today.py tests/test_web_format.py -q 2>&1 | tail -6`
Expected: FAIL (`nicheradar.web.today` no existe; `/` redirige a `/subnichos`).

- [ ] **Step 3: Implementar**

En `format.py` añadir `spanish_date` con tablas `DAYS = ("Lunes", …, "Domingo")` y `MONTHS = ("enero", …)`:

```python
def spanish_date(moment: datetime, timezone: str) -> str:
    local = moment.astimezone(ZoneInfo(timezone))
    return f"{DAYS[local.weekday()]} {local.day} de {MONTHS[local.month - 1]}"
```

Crear `today.py` con las funciones de la sección Interfaces. Reglas: `attention_cards` genera una tarjeta por piloto con `needs_decision` («Decide si sigue o cierra») o `status == "autorizado"` («Falta entregar el paquete al canal») con `niche_label`, `target_channel` o «Canal nuevo», sin enlace; `ready_reports` cruza informes `listo` con pilotos cuyo estado no sea `cerrado` ni `cancelado` por `(niche_label, format)`; `top_niches` usa `niches.card` sobre los items con puntaje; `top_subniches` ordena finalistas con medición primero y usa `subniches.card`; `today_view` recibe `{"status", "niches", "flows", "pilots", "subniches"}` (cada valor, `None` si falló) y devuelve por tarjeta `{"ok": bool, ...}`.

Crear `routes_today.py` con `GET /`: llamar a `/status` (para la fecha y la zona; si falla, usar `config.timezone`), `/market/niches?limit=3&order=opportunity` (pedir 10 para poder saltar los sin puntaje y tomar 3), `/flow-research?status=listo&limit=100`, `/pilots?limit=100` y `/subniches`, **cada una en su `try/except ApiError`** (nunca `raise`), construir `today_view` y renderizar `hoy.html` con `active_tab="hoy"`. Quitar la ruta `GET /` de `routes_auth.py` (y su importación sin uso). Si **todas** las fuentes fallan, la página sigue siendo 200 con cada tarjeta en «no disponible». Registrar el router en `app.py`.

Crear `templates/hoy.html` con M1/M14: título «Hoy», fecha (`spanish_date`), tarjeta «N pilotos necesitan algo de ti» (o «Ningún piloto necesita algo de ti») con las filas y el enlace desactivado «Ver pilotos» («Próximamente»), tarjeta «Informes listos» con enlaces `/informes/{id}`, tarjeta «3 nichos que merecen tu atención» (cada nicho con su botón, usando `niches.card`; los formularios de «Marcar tentativo» llevan `volver="/nichos"`) con enlace «Ver todos los nichos» a `/nichos`, y tarjeta «Subnichos medidos» con enlace «Ver subnichos» a `/subnichos`. Cada tarjeta fallida muestra «{Nombre}: no disponible ahora» en una `note note--amber`. Los chips «Victorias rápidas / Más automatizables / Confianza alta / Con ingresos» del Figma no se incluyen (son filtros que aquí viven en `/nichos`).

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `uv run pytest tests/test_web_today.py tests/test_web_session.py tests/test_web_format.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/web tests/test_web_today.py tests/test_web_format.py tests/test_web_session.py
git commit -m "feat: pantalla Hoy (M1 y M14) con tarjetas independientes por fuente"
```

---

### Task 6: Integración, capturas contra el Figma y documentación

**Files:**
- Modify: `scripts/web_preview.py`, `scripts/web_preview_data.py` (añadir Hoy, Nichos, Investigar, Informe v3, Autorizar con datos de ejemplo de la forma real de la API)
- Modify: `docs/web-movil.md`, `docs/comandos.md` (una línea si hace falta), `AGENTS.md` (solo si cambia la lista de archivos)
- Create: `tests/test_web_smoke_screens.py`; Modify: `tests/test_web_preview.py`

**Interfaces:**
- Consumes: todas las rutas de las Tasks 1 a 5.
- Produces: prueba de humo que recorre las pantallas con texto hostil y API caída; `scripts/web_preview.py` genera `hoy.png`, `nichos.png`, `investigar.png`, `informe.png`, `autorizar.png` además de `lista.png` y `ficha.png`.

- [ ] **Step 1: Prueba de humo que falla**

Crear `tests/test_web_smoke_screens.py`: parametrizar sobre las rutas autenticadas (`/`, `/nichos`, `/nichos/investigar?etiqueta=x&formato=long`, `/subnichos`, `/subnichos/uno`, `/informes/<id>`, `/pilotos/autorizar?informe=<id>`) y comprobar para cada una (a) con una API cuyos datos están llenos de `HOSTILE` en todas las cadenas, ninguna respuesta contiene `<script>alert(1)</script>` ni `javascript:` en un `href`, y el código es < 500; (b) con una API que lanza `ConnectError` en todo, el código es 200 o 503 (nunca 500) y el cuerpo contiene el mensaje en español; (c) ninguna respuesta incluye `http://` ni `https://` fuera de enlaces `<a href>` de fuentes del informe (no hay recursos externos: ningún `src=`, `<link>` ni `url(` hacia terceros); (d) el CSP de la respuesta es idéntico en todas. Para construir los datos hostiles, escribir un ayudante `hostile(value)` que recorra recursivamente un diccionario de fixture y reemplace cada cadena por `HOSTILE` salvo claves de estado, formato, idioma y URLs (`status`, `format`, `language`, `decision`, `recommendation`, `schema_version`, `id`).

- [ ] **Step 2: Ejecutar y verificar el resultado**

Run: `uv run pytest tests/test_web_smoke_screens.py -q 2>&1 | tail -8`
Expected: FAIL o PASS; cada fallo es un defecto real de escape o de manejo de errores en las tasks anteriores: corregirlo en el módulo responsable con su prueba específica (RED primero) y repetir hasta PASS.

- [ ] **Step 3: Capturas y documentación**

Extender `scripts/web_preview_data.py` con ejemplos de la forma exacta de la API (reutilizar los fixtures de `tests/web_helpers.py` **copiando solo los datos**, sin importar nada de `tests/`) y `scripts/web_preview.py` con las cinco pantallas nuevas (misma técnica de iframe a 390 px). Actualizar `docs/web-movil.md`: pantallas del corte 1 completas (rutas y APIs que usa cada una), qué no incluye todavía (Pilotos, Más, corte 2 y 3), las decisiones de datos que no se inventan (Fit, Demanda, Volumen, idioma en la lista, Cadencia, Preparación) y los rulings de este plan.

- [ ] **Step 4: Validación completa**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q 2>&1 | tail -4` (en primer plano; `tests/test_smoke.py` necesita `.venv/bin` en el `PATH`).
Expected: todo en verde. Después `uv run python scripts/web_preview.py --out /tmp/web-preview` y confirmar que se crean las siete imágenes. **Las comparaciones con el Figma las hace el controlador**; el implementador entrega las rutas y anota cualquier defecto visible.

- [ ] **Step 5: Commit**

```bash
git add scripts/web_preview.py scripts/web_preview_data.py tests/test_web_smoke_screens.py tests/test_web_preview.py docs/web-movil.md
git commit -m "docs: capturas y prueba de humo de las pantallas del corte 1"
```

---

## Fuera de este plan

Corte 2 (M5 lista de pilotos, M6 panel, M7 preparación, M13 y M14 completo, y el contrato `channel-report-v3` con minutos humanos automáticos, que tiene su propio spec y plan); corte 3 (paridad con Streamlit y retiro de Streamlit); la release y el cambio de `NR_DASHBOARD_UI` en Easypanel (requiere aprobación del propietario); la barra de proporción por etapa del Figma M11 y el filtro por idioma en la lista de nichos (la API no entrega el dato).

## Self-Review

- **Cobertura del spec (sección 5):** `/` Hoy (Task 5), `/nichos` con decisiones (Task 1), `/nichos/{label}/investigar` (Task 2, con la ruling de ruta por query), `/informes/{id}` con v1/v2/v3 y aviso de subnicho (Task 3), `/pilotos/autorizar` (Task 4). Las reglas de datos del spec (degradar por tarjeta, omitir cifras que la API no entrega, v1/v2 con aviso, subnicho con aviso de confianza y fecha) están en las Tasks 3, 4 y 5. M14 se cubre en «Hoy»; sus pilotos en calibración quedan para el corte 2 (M13).
- **Rulings:** (1) etiqueta por query en vez de ruta; (2) Descartar solo para backlog; (3) autorizar sin cadencia ni preparación ni receta; (4) `authorized_by` fijo; (5) «Ver pilotos» desactivado. Cada uno anota su costo si es incorrecto.
- **Consistencia de tipos:** `niches.card`/`research_index`/`investigate_href` (Task 1) los usan las Tasks 2 y 5; `report.report_view`/`safe_url`/`subject_label` (Task 3) los usa la Task 4; los fixtures `niche_item`, `flow_item`, `niche_detail`, `dossier_v3`, `report_detail`, `pilot_item` se añaden a `tests/web_helpers.py` en las Tasks 1 a 4 sin tocar los existentes; la expresión regular del id de informe se define en la Task 3 y la reutiliza la Task 4.
- **Riesgos conocidos del plan:** el fixture de dossier-v3 depende de uno existente en `tests/` (la Task 3 manda reutilizarlo y comprobar que valida con `DossierV3`); la clave de fecha de medición de un subnicho en `evidence` hay que leerla de `flow_research/subniche_evidence.py` (no está en este resumen); el redondeo de dinero debe coincidir con lo que acepta `Money` de la API (la Task 4 manda leerlo); `/flow-research` y `/pilots` solo admiten `limit ≤ 100` sin `offset`, así que con más de 100 registros la web ve los 100 más recientes.
- **Sin placeholders:** las pruebas y los modelos de las Tasks 1 y 2 traen el código; las Tasks 3 a 5 traen las pruebas completas y las reglas exactas del modelo de vista y de las rutas con los textos del Figma, porque dependen de fixtures y del dominio que el implementador debe leer en el repositorio (nombres reales indicados).
