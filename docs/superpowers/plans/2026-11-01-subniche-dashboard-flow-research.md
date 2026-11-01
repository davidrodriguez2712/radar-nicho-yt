# Subnichos en el dashboard, investigación de flujo y piloto desde una hipótesis: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ver las hipótesis de subnichos en el dashboard, ordenar una investigación de flujo y autorizar un piloto desde una hipótesis medida, sin tocar el descubrimiento ni la base de datos.

**Architecture:** Un encargo de subnicho usa `niche_label = "subniche:<slug>"` (sin migración; el índice único actual sirve). Un modelo de lectura nuevo (`subniche_discovery/catalog.py`) une cada hipótesis con su última medición y su última investigación; `create_request` arma, para ese prefijo, una evidencia congelada propia (`evidence.source = "subniche"`, `evidence.niche = None`); la API gana `GET /api/v1/subniches`; la autorización del piloto mapea esa evidencia a la forma ya permitida de `pilot-package-v1`; el panel gana la página **Subnichos**.

**Tech Stack:** Python 3.13, SQLAlchemy Core, FastAPI, pydantic v2, Streamlit (`AppTest`), pytest con Postgres, uv.

**Spec:** `docs/superpowers/specs/2026-11-01-subniche-dashboard-flow-research-design.md`

## Global Constraints

- Prefijo reservado del encargo: `subniche:` (constante `PREFIX` en `subniche_discovery/catalog.py`); `format` e `language` del encargo deben coincidir con los de la hipótesis (`niche_hypotheses.format` y `.language`).
- Elegibilidad: hipótesis con `status = "active"` y al menos una fila en `hypothesis_snapshots`; si no, error `subniche_not_ready`.
- Un encargo de subnicho no evalúa compuertas de nicho (no hay score de backlog): `evidence.niche` es `None`; siguen aplicando minutos de régimen, horas de calibración y derechos al entregar el dossier, con el tope vigente al enviar y la misma excepción registrada (`gate_override`, solo si se pasó al crear el encargo).
- Confianza de la evidencia de subnicho: `"baja"` con menos de 10 canales incluidos, `"media"` desde 10; nunca `"alta"`.
- Autorización del piloto (`pilot-package-v1`, sin versión nueva): `scores` todo `null`, `listings_with_income = 0`, `language_mix = [{"language": <de la hipótesis>, "share_pct": 100}]`, `figures` con `origin = "estimate"`.
- Los datos de la API de YouTube se conservan 30 días: canales vencidos (`retain_until <= now`) no se devuelven y la evidencia declara `channels_available: false`.
- La lista del panel muestra por defecto hipótesis `active` y `proposed`; una casilla incluye `paused` y `archived`.
- Texto de canales, títulos y consultas se muestra siempre con `st.text` (nunca Markdown).
- Sin cambios de esquema de base de datos ni migración Alembic.
- Mensajes y textos visibles en español; nombres de código en inglés, como el resto del paquete.

## Review Focus

1. Crear un encargo con `subniche:<slug>` de una hipótesis `proposed`, `paused`, `archived` o sin medición debe dar `subniche_not_ready`; con slug inexistente, `not_found`.
2. Un encargo activo para el mismo `subniche:<slug>`, formato e idioma no se duplica (devuelve el activo con `created = False`).
3. Un `niche_label` del backlog nunca puede empezar con `subniche:`: ese prefijo se enruta siempre al flujo de subnichos.
4. Un dossier de subnicho con `confidence = "baja"` en la evidencia y `verdict.unknowns` vacío se rechaza.
5. Texto hostil en consultas, títulos o enlaces de canales (`**x**`, HTML, `[x](https://evil.test)`) se muestra como texto plano.
6. Un dossier v2 o un encargo del backlog ya guardado no cambia de comportamiento en ninguna de las rutas modificadas (crear, entregar, autorizar).

---

### Task 1: Modelo de lectura de subnichos

**Files:**
- Create: `src/nicheradar/subniche_discovery/catalog.py`
- Create: `tests/test_subniche_catalog.py`

**Interfaces:**
- Consumes: tablas `niche_hypotheses`, `hypothesis_snapshots`, `hypothesis_channel_hits`, `discovery_channel_snapshots`, `flow_research_requests` (`nicheradar.repositories.schema`); helpers de prueba `tests/subniche_samples.py` (`NOW`, `make_run`, `draft`, `channel`, `video`) y `tests.test_subniche_aggregate.hit`.
- Produces: `PREFIX: str`, `research_label(slug: str) -> str`, `slug_of(label: str) -> str | None`, `list_subniches(connection, *, include_inactive: bool = False) -> list[dict[str, Any]]`, `subniche_detail(connection, slug: str, now: datetime) -> dict[str, Any] | None`. Forma de una fila de `list_subniches`: `{"slug","label","family","parent_niche_slug","status","finalist","language","format","queries","measurement": dict | None,"research": dict | None}`. `measurement`: `{"measured_at","included","stable_channels","volatile_channels","traction_channels","large_channels","excluded","income_low","income_high","rpm_source","signal"}` (importes como texto con 2 decimales o `None`). `research`: `{"id","status","language","created_at"}` de la última solicitud con `niche_label = PREFIX + slug`. Forma de `subniche_detail`: `{"hypothesis": <fila sin measurement ni research>, "measurement": ..., "channels": list[dict], "channels_available": bool, "research": ...}`; cada canal: `{"channel_id","title","subscribers","monthly_long_views","income_low","income_high","traction","flags"}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_subniche_catalog.py`:

```python
# tests/test_subniche_catalog.py
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.repositories import schema
from nicheradar.subniche_discovery.aggregate import HitMetrics, build_profile
from nicheradar.subniche_discovery.catalog import (
    PREFIX,
    list_subniches,
    research_label,
    slug_of,
    subniche_detail,
)
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed, set_status
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres


def measured(
    db: Connection, run_id: UUID, slug: str, hits: list[HitMetrics], *, finalist: bool = False
) -> UUID:
    hypothesis_id = create_proposed(db, draft(slug=slug, queries=(f"{slug} words",)), NOW)
    approve(db, slug, NOW)
    if finalist:
        db.execute(
            sa.update(schema.niche_hypotheses)
            .where(schema.niche_hypotheses.c.id == hypothesis_id)
            .values(finalist=True)
        )
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=NOW,
        channels=[(channel("a"), [video(1)])],
        hits=hits,
        profile=build_profile(hits, rpm_source="inherited:x"),
    )
    return hypothesis_id


def request_row(db: Connection, label: str, status: str, at: object) -> UUID:
    request_id = uuid4()
    db.execute(
        sa.insert(schema.flow_research_requests).values(
            id=request_id,
            niche_label=label,
            format="long",
            language="en",
            status=status,
            evidence={},
            attempts=0,
            created_at=at,
            updated_at=at,
            retain_until=NOW + timedelta(days=90),
        )
    )
    return request_id


def test_label_helpers_round_trip_and_reject_other_labels() -> None:
    assert PREFIX == "subniche:" and research_label("a_b") == "subniche:a_b"
    assert slug_of("subniche:a_b") == "a_b" and slug_of("personal_finance") is None


def test_listing_hides_paused_and_archived_unless_asked(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a", traction=True, low="10", high="20")])
    measured(db, run_id, "paused_one", [hit("a")])
    set_status(db, "paused_one", "paused")
    create_proposed(db, draft(slug="fresh_one", queries=("fresh words",)), NOW)
    assert [r["slug"] for r in list_subniches(db)] == ["alive_one", "fresh_one"]
    everything = {r["slug"] for r in list_subniches(db, include_inactive=True)}
    assert everything == {"alive_one", "paused_one", "fresh_one"}


def test_listing_exposes_the_latest_measurement_and_orders_finalists_first(
    db: Connection,
) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "plain_one", [hit("a", traction=True, low="10", high="20")])
    measured(db, run_id, "star_one", [hit("a", low="5", high="9")], finalist=True)
    rows = list_subniches(db)
    assert [r["slug"] for r in rows] == ["star_one", "plain_one"]
    plain = rows[1]["measurement"]
    assert plain["traction_channels"] == 1 and plain["rpm_source"] == "inherited:x"
    assert plain["income_low"] == "10.00" and plain["income_high"] == "20.00"
    assert plain["included"] == 1 and rows[1]["language"] == "en" and rows[1]["format"] == "long"


def test_an_unmeasured_hypothesis_has_no_measurement_and_no_research(db: Connection) -> None:
    create_proposed(db, draft(slug="fresh_one", queries=("fresh words",)), NOW)
    row = list_subniches(db)[0]
    assert row["measurement"] is None and row["research"] is None


def test_the_latest_research_of_each_hypothesis_is_reported(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a")])
    request_row(db, research_label("alive_one"), "rechazado", NOW)
    newest = request_row(db, research_label("alive_one"), "pendiente", NOW + timedelta(hours=1))
    request_row(db, "personal_finance", "listo", NOW)  # del backlog: no cuenta
    research = list_subniches(db)[0]["research"]
    assert research["id"] == newest and research["status"] == "pendiente"


def test_detail_lists_current_channels_with_titles_and_declares_expired_ones(
    db: Connection,
) -> None:
    run_id, _, _ = make_run(db)
    measured(db, run_id, "alive_one", [hit("a", traction=True, low="100", high="900")])
    detail = subniche_detail(db, "alive_one", NOW)
    assert detail is not None and detail["channels_available"] is True
    first = detail["channels"][0]
    assert first["channel_id"] == "a" and first["income_high"] == "900.00" and first["traction"]
    assert detail["hypothesis"]["slug"] == "alive_one"
    later = subniche_detail(db, "alive_one", NOW + timedelta(days=31))
    assert later is not None and later["channels"] == []
    assert later["channels_available"] is False and later["measurement"] is not None


def test_detail_of_an_unknown_slug_is_none(db: Connection) -> None:
    assert subniche_detail(db, "nope_nope", NOW) is None
```

(Si `tests.subniche_samples.channel` o `video` no aceptan estos argumentos, copiar la forma exacta con la que los usa `tests/test_subniche_report.py`. Si `set_status` o `approve` tienen otra firma, seguir `tests/test_subniche_store.py`.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_catalog.py -q 2>&1 | tail -6`
Expected: FAIL por `ModuleNotFoundError: nicheradar.subniche_discovery.catalog`.

- [ ] **Step 3: Implementar el modelo de lectura**

Crear `src/nicheradar/subniche_discovery/catalog.py`:

```python
# src/nicheradar/subniche_discovery/catalog.py
"""Read model: hypotheses with their latest measurement and research request.

Used by the dashboard, the private API and the research orders. Read-only.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select

from nicheradar.repositories.schema import discovery_channel_snapshots as channel_snapshots
from nicheradar.repositories.schema import flow_research_requests as requests
from nicheradar.repositories.schema import hypothesis_channel_hits as hits
from nicheradar.repositories.schema import hypothesis_snapshots as snapshots
from nicheradar.repositories.schema import niche_hypotheses as nh

PREFIX = "subniche:"
ACTIVE_STATUSES = ("active", "proposed")
MAX_CHANNELS = 10


def research_label(slug: str) -> str:
    return PREFIX + slug


def slug_of(label: str) -> str | None:
    return label.removeprefix(PREFIX) if label.startswith(PREFIX) else None


def _money(value: Any) -> str | None:
    return None if value is None else f"{value:.2f}"


def _latest_snapshots() -> Any:
    return (
        select(snapshots)
        .distinct(snapshots.c.hypothesis_id)
        .order_by(snapshots.c.hypothesis_id, snapshots.c.measured_at.desc())
        .subquery()
    )


def _measurement(row: Any) -> dict[str, Any] | None:
    if row["measured_at"] is None:
        return None
    profile = row["profile"]
    return {
        "measured_at": row["measured_at"],
        "included": profile.get("channels_included", 0),
        "stable_channels": row["stable_channels"],
        "volatile_channels": profile.get("volatile_channels", 0),
        "traction_channels": row["traction_channels"],
        "large_channels": profile.get("large_channels", 0),
        "excluded": profile.get("excluded", {}),
        "income_low": _money(row["median_income_low"]),
        "income_high": _money(row["median_income_high"]),
        "rpm_source": profile.get("rpm_source"),
        "signal": profile.get("signal"),
    }


def _hypothesis(row: Any) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "label": row["label"],
        "family": row["family"],
        "parent_niche_slug": row["parent_niche_slug"],
        "status": row["status"],
        "finalist": row["finalist"],
        "language": row["language"],
        "format": row["format"],
        "queries": list(row["queries"]),
    }


def _latest_research(connection: Connection) -> dict[str, dict[str, Any]]:
    query = (
        select(
            requests.c.niche_label,
            requests.c.id,
            requests.c.status,
            requests.c.language,
            requests.c.created_at,
        )
        .where(requests.c.niche_label.like(PREFIX + "%"))
        .order_by(requests.c.created_at.desc())
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in connection.execute(query).mappings():
        latest.setdefault(
            row["niche_label"],
            {
                "id": row["id"],
                "status": row["status"],
                "language": row["language"],
                "created_at": row["created_at"],
            },
        )
    return latest


def _columns(latest: Any) -> list[Any]:
    return [
        nh.c.slug,
        nh.c.label,
        nh.c.family,
        nh.c.parent_niche_slug,
        nh.c.status,
        nh.c.finalist,
        nh.c.language,
        nh.c.format,
        nh.c.queries,
        latest.c.run_id,
        latest.c.measured_at,
        latest.c.stable_channels,
        latest.c.traction_channels,
        latest.c.median_income_low,
        latest.c.median_income_high,
        latest.c.profile,
    ]


def list_subniches(
    connection: Connection, *, include_inactive: bool = False
) -> list[dict[str, Any]]:
    latest = _latest_snapshots()
    query = select(*_columns(latest)).select_from(
        nh.outerjoin(latest, latest.c.hypothesis_id == nh.c.id)
    )
    if not include_inactive:
        query = query.where(nh.c.status.in_(ACTIVE_STATUSES))
    query = query.order_by(
        nh.c.finalist.desc(), latest.c.traction_channels.desc().nulls_last(), nh.c.slug
    )
    research = _latest_research(connection)
    return [
        _hypothesis(row)
        | {
            "measurement": _measurement(row),
            "research": research.get(research_label(row["slug"])),
        }
        for row in connection.execute(query).mappings()
    ]


def subniche_detail(connection: Connection, slug: str, now: datetime) -> dict[str, Any] | None:
    latest = _latest_snapshots()
    row = (
        connection.execute(
            select(*_columns(latest))
            .select_from(nh.outerjoin(latest, latest.c.hypothesis_id == nh.c.id))
            .where(nh.c.slug == slug)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    channels: list[dict[str, Any]] = []
    if row["run_id"] is not None:
        hypothesis_id = connection.execute(
            select(nh.c.id).where(nh.c.slug == slug)
        ).scalar_one()
        query = (
            select(
                hits.c.channel_id,
                channel_snapshots.c.title,
                hits.c.subscribers,
                hits.c.monthly_long_views,
                hits.c.income_low,
                hits.c.income_high,
                hits.c.traction,
                hits.c.flags,
            )
            .select_from(
                hits.outerjoin(
                    channel_snapshots,
                    (channel_snapshots.c.run_id == hits.c.run_id)
                    & (channel_snapshots.c.channel_id == hits.c.channel_id)
                    & (channel_snapshots.c.retain_until > now),
                )
            )
            .where(
                hits.c.hypothesis_id == hypothesis_id,
                hits.c.run_id == row["run_id"],
                hits.c.excluded_reason.is_(None),
                hits.c.retain_until > now,
            )
            .order_by(hits.c.income_high.desc().nulls_last(), hits.c.monthly_long_views.desc())
            .limit(MAX_CHANNELS)
        )
        channels = [
            {
                "channel_id": item["channel_id"],
                "title": item["title"],
                "subscribers": item["subscribers"],
                "monthly_long_views": item["monthly_long_views"],
                "income_low": _money(item["income_low"]),
                "income_high": _money(item["income_high"]),
                "traction": item["traction"],
                "flags": list(item["flags"]),
            }
            for item in connection.execute(query).mappings()
        ]
    return {
        "hypothesis": _hypothesis(row),
        "measurement": _measurement(row),
        "channels": channels,
        "channels_available": bool(channels),
        "research": _latest_research(connection).get(research_label(slug)),
    }
```

(Si `ACTIVE_STATUSES` y `MAX_CHANNELS` no se usan fuera, dejarlos igualmente; son parte de la interfaz de la tarea 3 y 5.)

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_catalog.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS; ruff y mypy sin errores.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/subniche_discovery/catalog.py tests/test_subniche_catalog.py
git commit -m "feat: modelo de lectura de subnichos (última medición e investigación)"
```

---

### Task 2: Encargo de investigación desde una hipótesis

**Files:**
- Create: `src/nicheradar/flow_research/subniche_evidence.py`
- Modify: `src/nicheradar/flow_research/service.py` (create_request, `MESSAGES`, `_gate_problems`, `_request_problems`)
- Create: `tests/test_flow_research_subniche.py`

**Interfaces:**
- Consumes: `catalog.PREFIX`, `catalog.slug_of`, `catalog.subniche_detail` (Task 1); `Gates`, `valid_dossier`, `claimed`-style helpers de `tests/test_niche_gates.py`.
- Produces: `build_subniche_evidence(detail: dict, gates: Gates, gate_override: dict[str, str] | None) -> dict[str, Any]` con claves `source`, `niche` (`None`), `subniche`, `measurement`, `channels`, `channels_available`, `language`, `language_mix`, `confidence` (`"baja"`/`"media"`), `gate`, y `gate_override` si se pasó; nuevos códigos de `FlowResearchError`: `subniche_not_ready`, `format_mismatch`, `language_mismatch`; `create_request(...)` acepta `niche_label` con prefijo `subniche:`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_flow_research_subniche.py`:

```python
# tests/test_flow_research_subniche.py
"""Encargos de investigación de flujo ordenados desde una hipótesis de subnicho."""

import copy
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Connection

from nicheradar.flow_research.gates import Gates
from nicheradar.flow_research.service import (
    FlowResearchError,
    claim_request,
    create_request,
    submit_dossier,
)
from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed, set_status
from tests.flow_research_samples import valid_dossier
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
LABEL = "subniche:history_revenge"
OPEN = Gates(0, 10_000, False, 10_000)  # sin compuertas de nicho, minutos ni calibración


def measured_hypothesis(db: Connection, *, hits: int = 3, approved: bool = True) -> None:
    run_id, _, _ = make_run(db)
    rows = [hit(f"c{index}", traction=index == 0, low="100", high="900") for index in range(hits)]
    hypothesis_id = create_proposed(
        db, draft(slug="history_revenge", queries=("history revenge",)), NOW
    )
    if approved:
        approve(db, "history_revenge", NOW)
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=NOW,
        channels=[(channel("c0"), [video(1)])],
        hits=rows,
        profile=build_profile(rows, rpm_source="inherited:x"),
    )


def order(db: Connection, **over: Any) -> tuple[dict[str, Any], bool]:
    args: dict[str, Any] = {"label": LABEL, "format": "long", "language": "en"}
    args.update(over)
    return create_request(
        db, args["label"], args["format"], args["language"], NOW, gates=OPEN,
        gate_override=args.get("gate_override"),
    )


def test_an_order_freezes_the_measurement_with_no_backlog_niche(db: Connection) -> None:
    measured_hypothesis(db)
    request, created = order(db)
    evidence = request["evidence"]
    assert created is True and request["niche_label"] == LABEL and request["status"] == "pendiente"
    assert evidence["source"] == "subniche" and evidence["niche"] is None
    assert evidence["subniche"]["slug"] == "history_revenge"
    assert evidence["measurement"]["traction_channels"] == 1
    assert evidence["language_mix"] == [{"language": "en", "share_pct": 100}]
    assert evidence["channels_available"] is True and evidence["gate"]["automation_known"] is False


def test_confidence_is_low_under_ten_channels_and_medium_from_ten(db: Connection) -> None:
    measured_hypothesis(db, hits=3)
    assert order(db)[0]["evidence"]["confidence"] == "baja"


def test_ten_channels_give_medium_confidence(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    assert order(db)[0]["evidence"]["confidence"] == "media"


@pytest.mark.parametrize("status", ["paused", "archived"])
def test_only_active_hypotheses_can_be_researched(db: Connection, status: str) -> None:
    measured_hypothesis(db)
    set_status(db, "history_revenge", status)
    with pytest.raises(FlowResearchError) as error:
        order(db)
    assert error.value.code == "subniche_not_ready"


def test_a_proposed_or_unmeasured_hypothesis_cannot_be_researched(db: Connection) -> None:
    create_proposed(db, draft(slug="history_revenge", queries=("history revenge",)), NOW)
    with pytest.raises(FlowResearchError) as proposed:
        order(db)
    approve(db, "history_revenge", NOW)
    with pytest.raises(FlowResearchError) as unmeasured:
        order(db)
    assert proposed.value.code == unmeasured.value.code == "subniche_not_ready"


def test_unknown_slug_and_prefix_without_hypothesis_are_not_found(db: Connection) -> None:
    for label in ("subniche:nope_nope", "subniche:"):
        with pytest.raises(FlowResearchError) as error:
            order(db, label=label)
        assert error.value.code == "not_found"


def test_format_and_language_must_match_the_hypothesis(db: Connection) -> None:
    measured_hypothesis(db)
    with pytest.raises(FlowResearchError) as fmt:
        order(db, format="shorts")
    with pytest.raises(FlowResearchError) as lang:
        order(db, language="es")
    assert fmt.value.code == "format_mismatch" and lang.value.code == "language_mismatch"


def test_an_active_order_is_not_duplicated(db: Connection) -> None:
    measured_hypothesis(db)
    first, _ = order(db)
    again, created = order(db)
    assert created is False and again["id"] == first["id"]


def test_a_recorded_override_is_frozen_with_the_evidence(db: Connection) -> None:
    measured_hypothesis(db)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = order(db, gate_override=override)
    assert request["evidence"]["gate_override"]["by"] == "david"


def submit(db: Connection, request: dict[str, Any], gates: Gates, **verdict: Any) -> dict[str, Any]:
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    payload = copy.deepcopy(valid_dossier(request["id"], NOW))
    payload["niche_label"] = LABEL
    payload["verdict"].update(verdict)
    return submit_dossier(db, request["id"], owner, payload, NOW, gates)


def test_a_dossier_for_a_subniche_is_accepted_when_it_passes_the_gates(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    assert submit(db, request, Gates(70, 60, True, 40))["accepted"] is True


def test_minutes_and_calibration_gates_apply_to_a_subniche_dossier(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    tight = Gates(70, 40, True, 10)  # la muestra: 55 minutos de régimen y 17,5 horas
    result = submit(db, request, tight)
    assert result["accepted"] is False
    message = result["problems"][0]["message"]
    assert "55" in message and "17.5" in message


def test_low_confidence_evidence_requires_declared_unknowns(db: Connection) -> None:
    measured_hypothesis(db, hits=3)
    request, _ = order(db)
    result = submit(db, request, OPEN, unknowns=[])
    assert result["accepted"] is False
    assert result["problems"][0]["path"] == "verdict.unknowns"


def test_a_dossier_for_another_label_does_not_answer_the_order(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    payload = copy.deepcopy(valid_dossier(UUID(str(request["id"])), NOW))
    payload["niche_label"] = "personal_finance"
    result = submit_dossier(db, request["id"], owner, payload, NOW, OPEN)
    assert result["accepted"] is False
    assert any(p["path"] == "niche_label" for p in result["problems"])
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_flow_research_subniche.py -q 2>&1 | tail -6`
Expected: FAIL (el código `subniche_not_ready` no existe; el encargo se resuelve contra el backlog y da `not_found` o `KeyError`).

- [ ] **Step 3: Implementar la evidencia y el flujo de creación**

Crear `src/nicheradar/flow_research/subniche_evidence.py`:

```python
# src/nicheradar/flow_research/subniche_evidence.py
"""The frozen evidence package of a research order that comes from a sub-niche hypothesis."""

from typing import Any

from pydantic_core import to_jsonable_python

from nicheradar.flow_research.gates import Gates

MEDIUM_CONFIDENCE_FROM = 10  # channels included in the measurement; assumption, not measured


def build_subniche_evidence(
    detail: dict[str, Any], gates: Gates, gate_override: dict[str, str] | None = None
) -> dict[str, Any]:
    """Freeze the hypothesis, its latest measurement and the channels still retained.

    There is no backlog score, so ``niche`` is ``None`` and the niche gates do not apply; the
    minutes, calibration and rights gates still run when the dossier arrives.
    """
    hypothesis = detail["hypothesis"]
    measurement = detail["measurement"]
    included = measurement["included"]
    package: dict[str, Any] = {
        "source": "subniche",
        "niche": None,
        "subniche": {
            key: hypothesis[key]
            for key in (
                "slug",
                "label",
                "family",
                "parent_niche_slug",
                "language",
                "format",
                "finalist",
                "queries",
            )
        },
        "measurement": measurement,
        "channels": detail["channels"],
        "channels_available": detail["channels_available"],
        "language": hypothesis["language"],
        "language_mix": [{"language": hypothesis["language"], "share_pct": 100}],
        "confidence": "media" if included >= MEDIUM_CONFIDENCE_FROM else "baja",
        "gate": {
            "min_automation": gates.min_automation,
            "max_human_minutes": gates.max_human_minutes,
            "max_calibration_hours": gates.max_calibration_hours,
            "block_high_policy_risk": gates.block_high_policy_risk,
            "automation_known": False,
            "policy_risk_level": None,
            "passed": True,
            "reasons": [],
        },
    }
    if gate_override is not None:
        package["gate_override"] = gate_override
    frozen: dict[str, Any] = to_jsonable_python(package)
    return frozen
```

En `src/nicheradar/flow_research/service.py`:

1. Importar: `from nicheradar.flow_research.subniche_evidence import build_subniche_evidence` y `from nicheradar.subniche_discovery.catalog import PREFIX, subniche_detail`.
2. Ampliar `MESSAGES`:

```python
    "subniche_not_ready": "La hipótesis debe estar activa y tener al menos una medición.",
    "format_mismatch": "El formato no coincide con el de la hipótesis.",
    "language_mismatch": "El idioma no coincide con el de la hipótesis.",
```

3. Extraer la inserción de `create_request` a una función compartida y añadir la rama de subnicho. Reemplazar el cuerpo desde `detail = niche_detail(...)` hasta el `return _stored(connection, request_id), True` final por:

```python
    if niche_label.startswith(PREFIX):
        return _create_subniche(
            connection, niche_label, format, language, now, gates, gate_override
        )
    detail = niche_detail(connection, niche_label, format, now, timezone)
    if detail is None:
        raise FlowResearchError("not_found")
    reason = ineligible_reason(detail["niche"])
    if reason is not None:
        raise FlowResearchError(reason)
    gates = gates or gate_rules.DEFAULT_GATES
    failing = niche_reasons(detail["niche"], gates)
    if failing and gate_override is None:
        raise FlowResearchError("gate_failed", failing)
    override = None
    if failing and gate_override is not None:
        override = {**gate_override, "at": now.isoformat()}
    evidence = build_evidence(detail, language, gates, override)
    return _insert_request(connection, niche_label, format, language, evidence, now)


def _create_subniche(
    connection: Connection,
    niche_label: str,
    format: str,
    language: str,
    now: datetime,
    gates: Gates | None,
    gate_override: dict[str, str] | None,
) -> tuple[dict[str, Any], bool]:
    detail = subniche_detail(connection, niche_label.removeprefix(PREFIX), now)
    if detail is None:
        raise FlowResearchError("not_found")
    hypothesis = detail["hypothesis"]
    if hypothesis["status"] != "active" or detail["measurement"] is None:
        raise FlowResearchError("subniche_not_ready")
    if format != hypothesis["format"]:
        raise FlowResearchError("format_mismatch")
    if language != hypothesis["language"]:
        raise FlowResearchError("language_mismatch")
    override = None if gate_override is None else {**gate_override, "at": now.isoformat()}
    evidence = build_subniche_evidence(detail, gates or gate_rules.DEFAULT_GATES, override)
    return _insert_request(connection, niche_label, format, language, evidence, now)


def _insert_request(
    connection: Connection,
    niche_label: str,
    format: str,
    language: str,
    evidence: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    request_id = uuid4()
    try:
        with connection.begin_nested():
            connection.execute(
                requests.insert().values(
                    id=request_id,
                    niche_label=niche_label,
                    format=format,
                    language=language,
                    status="pendiente",
                    evidence=evidence,
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                    retain_until=now + RETENTION,
                )
            )
    except IntegrityError:
        # A concurrent creation won the unique index for this niche; return that one.
        winner = _active(connection, niche_label, format, language)
        if winner is None:
            raise
        return _stored(connection, winner), False
    return _stored(connection, request_id), True
```

(El orden de `create_request` se mantiene: `LANGUAGE.fullmatch`, `release_expired`, `_active` y, solo después, la rama por prefijo; el docstring de `create_request` gana una línea que menciona el prefijo `subniche:`.)

4. Tolerar evidencia sin nicho. En `_gate_problems`, dentro de `if "gate_override" not in evidence:` reemplazar `reasons += niche_reasons(evidence["niche"], gates)` por:

```python
        niche = evidence.get("niche")
        if niche is not None:
            reasons += niche_reasons(niche, gates)
```

y en `_request_problems` reemplazar la condición `row["evidence"]["niche"].get("confidence") == "baja"` por:

```python
    niche = row["evidence"].get("niche")
    confidence = niche.get("confidence") if niche is not None else row["evidence"].get("confidence")
    if confidence == "baja" and not dossier.verdict.unknowns:
```

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_flow_research_subniche.py tests/test_flow_research_service.py tests/test_niche_gates.py tests/test_flow_research_calibration_gate.py tests/test_flow_research_api.py tests/test_flow_research_language.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS (las pruebas de backlog existentes siguen verdes: Review Focus 6).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/flow_research/subniche_evidence.py src/nicheradar/flow_research/service.py tests/test_flow_research_subniche.py
git commit -m "feat: encargo de investigación de flujo desde una hipótesis de subnicho"
```

---

### Task 3: API de lectura de subnichos

**Files:**
- Create: `src/nicheradar/subniche_api.py`
- Modify: `src/nicheradar/api.py` (import e `include_router`, cerca de la línea 893)
- Create: `tests/test_subniche_api.py`

**Interfaces:**
- Consumes: `list_subniches`, `subniche_detail` (Task 1); `authenticate`, `db`, `clock` como los demás routers (`flow_research_router(authenticate=..., db=..., config=..., clock=...)`).
- Produces: `subniche_router(*, authenticate: Callable[..., None], db: Callable[..., Iterator[Connection]], clock: Callable[[], datetime]) -> APIRouter` con `GET /api/v1/subniches?include_inactive=false` → `{"items": [...]}` y `GET /api/v1/subniches/{slug}` → ficha (404 con `{"code": "not_found", ...}` si no existe).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_subniche_api.py`:

```python
# tests/test_subniche_api.py
import pytest
from sqlalchemy import Engine

from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed
from tests.subniche_samples import NOW as MEASURED
from tests.subniche_samples import channel, draft, make_run, video
from tests.test_market_api import AUTH, client
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
BASE = "/api/v1/subniches"


def seed(engine: Engine) -> None:
    with engine.begin() as connection:
        run_id, _, _ = make_run(connection)
        rows = [hit("a", traction=True, low="100", high="900")]
        hypothesis_id = create_proposed(
            connection, draft(slug="history_revenge", queries=("history revenge",)), MEASURED
        )
        approve(connection, "history_revenge", MEASURED)
        save_measurement(
            connection,
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            now=MEASURED,
            channels=[(channel("a"), [video(1)])],
            hits=rows,
            profile=build_profile(rows, rpm_source="inherited:x"),
        )
        create_proposed(connection, draft(slug="fresh_one", queries=("fresh words",)), MEASURED)


def test_every_endpoint_requires_the_service_token(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    assert api.get(BASE).status_code == 401
    assert api.get(BASE + "/history_revenge").status_code == 401
    assert api.get(BASE, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_the_listing_returns_measurements_and_hides_inactive_by_default(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    items = api.get(BASE, headers=AUTH).json()["items"]
    assert [item["slug"] for item in items] == ["history_revenge", "fresh_one"]
    assert items[0]["measurement"]["traction_channels"] == 1
    assert items[1]["measurement"] is None


def test_the_listing_can_include_inactive_hypotheses(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    assert api.get(BASE + "?include_inactive=true", headers=AUTH).status_code == 200


def test_the_detail_returns_the_card_and_unknown_slugs_are_404(isolated_engine: Engine) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    card = api.get(BASE + "/history_revenge", headers=AUTH).json()
    assert card["hypothesis"]["slug"] == "history_revenge" and card["research"] is None
    assert card["measurement"]["income_high"] == "900.00"
    missing = api.get(BASE + "/nope_nope", headers=AUTH)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"
```

(El reloj del cliente de pruebas es `tests.test_persistence.NOW`; si es anterior a la medición, el detalle sigue mostrando canales porque `retain_until` está en el futuro. Si no, ajustar el reloj con la misma convención de `tests/test_market_api.py`.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_api.py -q 2>&1 | tail -5`
Expected: FAIL (`404` en todas las rutas: el router no existe).

- [ ] **Step 3: Implementar el router y registrarlo**

Crear `src/nicheradar/subniche_api.py`:

```python
# src/nicheradar/subniche_api.py
"""Private read-only API for sub-niche hypotheses; same Bearer as the rest of /api/v1."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import Connection

from nicheradar.subniche_discovery.catalog import list_subniches, subniche_detail


def subniche_router(
    *,
    authenticate: Callable[..., None],
    db: Callable[..., Iterator[Connection]],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subniches", dependencies=[Depends(authenticate)])

    @router.get("")
    def listing(
        connection: Annotated[Connection, Depends(db)],
        include_inactive: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        return {"items": list_subniches(connection, include_inactive=include_inactive)}

    @router.get("/{slug}")
    def detail(
        slug: Annotated[str, Path(min_length=1, max_length=60)],
        connection: Annotated[Connection, Depends(db)],
    ) -> dict[str, Any]:
        card = subniche_detail(connection, slug, clock())
        if card is None:
            raise HTTPException(
                404, {"code": "not_found", "message": "Hipótesis no encontrada."}
            )
        return card

    return router
```

En `src/nicheradar/api.py`: añadir `from nicheradar.subniche_api import subniche_router` junto a los demás imports de routers (orden alfabético) y, tras `flow_research_router(...)`, `app.include_router(subniche_router(authenticate=authenticate, db=db, clock=clock))`.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_api.py tests/test_market_api.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/subniche_api.py src/nicheradar/api.py tests/test_subniche_api.py
git commit -m "feat: API de lectura de subnichos (listado y ficha)"
```

---

### Task 4: Autorizar un piloto desde un subnicho

**Files:**
- Modify: `src/nicheradar/flow_research/gates.py` (`authorization_reasons`)
- Modify: `src/nicheradar/pilots/service.py` (`authorize`, nuevo `_subniche_evidence`)
- Create: `tests/test_pilots_subniche.py`

**Interfaces:**
- Consumes: encargo de subnicho con dossier listo (Task 2); `CONFIDENCE`, `_plain`, `_number`, `_new_pilot_id` de `pilots/service.py`.
- Produces: `authorization_reasons(dossier, niche: dict[str, Any] | None, gates)` (con `niche is None` omite la compuerta de nicho); `authorize(...)` acepta `niche_label = "subniche:<slug>"`; `_subniche_evidence(evidence: dict[str, Any], now: datetime) -> dict[str, Any]` en la forma `pilot-package-v1` (`scores` nulos, `listings_with_income = 0`, `figures` con `origin = "estimate"`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_pilots_subniche.py`:

```python
# tests/test_pilots_subniche.py
"""Piloto autorizado desde un dossier de subnicho."""

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed
from tests.flow_research_samples import valid_dossier
from tests.subniche_samples import NOW as MEASURED
from tests.subniche_samples import channel, draft, make_run, video
from tests.test_flow_research_api import BASE as FLOW
from tests.test_market_api import AUTH, client
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE as PILOTS
from tests.test_pilots_api import authorize_body
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
LABEL = "subniche:history_revenge"


def seed(engine: Engine, hits: int = 10) -> None:
    with engine.begin() as connection:
        run_id, _, _ = make_run(connection)
        rows = [hit(f"c{i}", traction=i == 0, low="100", high="900") for i in range(hits)]
        hypothesis_id = create_proposed(
            connection, draft(slug="history_revenge", queries=("history revenge",)), MEASURED
        )
        approve(connection, "history_revenge", MEASURED)
        save_measurement(
            connection,
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            now=MEASURED,
            channels=[(channel("c0"), [video(1)])],
            hits=rows,
            profile=build_profile(rows, rpm_source="inherited:x"),
        )


def ready_subniche(api: TestClient) -> str:
    body = {"niche_label": LABEL, "format": "long", "language": "en"}
    created = api.post(FLOW, json=body, headers=AUTH)
    assert created.status_code == 201, created.text
    request_id = str(created.json()["id"])
    owner = api.post(f"{FLOW}/{request_id}/claim", json={"owner": "w"}, headers=AUTH).json()[
        "lease_owner"
    ]
    dossier: dict[str, Any] = valid_dossier(UUID(request_id), NOW)
    dossier["niche_label"] = LABEL
    done = api.post(
        f"{FLOW}/{request_id}/dossier", json={"owner": owner, "dossier": dossier}, headers=AUTH
    )
    assert done.status_code == 200, done.text
    return request_id


def test_a_pilot_is_authorized_from_a_subniche_with_the_v1_package_shape(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    created = api.post(
        PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH
    )
    assert created.status_code == 201, created.text
    package = created.json()["package"]
    assert created.json()["pilot_id"].startswith("pil_")
    assert created.json()["pilot_id"].endswith("-history-revenge")
    assert package["niche"]["label"] == LABEL
    evidence = package["evidence"]
    assert evidence["scores"] == {
        "opportunity": None,
        "automation": None,
        "creator_fit": None,
        "market": None,
    }
    assert evidence["listings_with_income"] == 0 and evidence["confidence"] == "medium"
    assert evidence["language_mix"] == [{"language": "en", "share_pct": 100}]
    figures = {item["name"]: item for item in evidence["figures"]}
    assert figures["income_estimate_high"]["value"] == 900
    assert figures["income_estimate_high"]["origin"] == "estimate"
    assert figures["traction_channels"]["value"] == 1


def test_low_confidence_subniche_evidence_maps_to_low(isolated_engine: Engine) -> None:
    seed(isolated_engine, hits=3)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    created = api.post(
        PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH
    )
    assert created.status_code == 201, created.text
    assert created.json()["package"]["evidence"]["confidence"] == "low"


def test_authorization_repeats_the_minutes_gate_for_a_subniche_dossier(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    request_id = ready_subniche(client(isolated_engine))
    strict = client(isolated_engine, gate_max_human_minutes=40)
    refused = strict.post(
        PILOTS, json=authorize_body(request_id, niche_label=LABEL), headers=AUTH
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_failed"
    assert [reason["gate"] for reason in detail["reasons"]] == ["human_minutes"]
    accepted = strict.post(
        PILOTS,
        json=authorize_body(
            request_id, niche_label=LABEL, accept_gate_failure=True, target_channel=None
        ),
        headers=AUTH,
    )
    assert accepted.status_code == 201, accepted.text


def test_a_niche_label_that_does_not_match_the_order_is_refused(
    isolated_engine: Engine,
) -> None:
    seed(isolated_engine)
    api = client(isolated_engine)
    request_id = ready_subniche(api)
    wrong = api.post(
        PILOTS, json=authorize_body(request_id, niche_label="personal_finance"), headers=AUTH
    )
    assert wrong.status_code in (404, 409, 422)
```

(`test_a_pilot_is_authorized...` incluye una comprobación sobre el `pilot_id`: debe ser `pil_<aaaammdd>_history-revenge` — sin el prefijo `subniche-`. Si la forma de `authorize_body` o de los códigos HTTP del rechazo difiere, seguir `tests/test_pilots_api.py` y `tests/test_niche_gates.py::test_authorizing_repeats_the_gates...`; si `client(...)` no acepta `gate_max_human_minutes`, usar `Settings(...)` igual que ese test.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_pilots_subniche.py -q 2>&1 | tail -6`
Expected: FAIL (`404 not_found` en la autorización: `niche_detail` no conoce `subniche:history_revenge`).

- [ ] **Step 3: Implementar**

En `src/nicheradar/flow_research/gates.py`, cambiar la firma y el inicio de `authorization_reasons`:

```python
def authorization_reasons(
    dossier: dict[str, Any], niche: dict[str, Any] | None, gates: Gates
) -> list[GateReason]:
    """Every gate again, on a stored dossier (any version) just before a pilot is authorized.

    A sub-niche order has no backlog niche (``niche`` is ``None``): the niche gates are skipped.
    """
    reasons = [] if niche is None else niche_reasons(niche, gates)
```

(el resto de la función queda igual: minutos de régimen, horas de calibración y derechos).

En `src/nicheradar/pilots/service.py`:

1. Constante y función nuevas junto a `_evidence`:

```python
SUBNICHE_PREFIX = "subniche:"


def _subniche_evidence(evidence: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Map a frozen sub-niche measurement to the existing pilot-package-v1 evidence shape."""
    measurement = evidence["measurement"]
    figures: list[dict[str, Any]] = []
    for name, key in (("income_estimate_low", "income_low"), ("income_estimate_high", "income_high")):
        if measurement[key] is not None:
            figures.append(
                {
                    "name": name,
                    "value": _plain(_number(measurement[key])),
                    "unit": "usd_per_month",
                    "origin": "estimate",
                }
            )
    for name, key in (
        ("traction_channels", "traction_channels"),
        ("stable_channels", "stable_channels"),
        ("large_channels", "large_channels"),
        ("volatile_channels", "volatile_channels"),
    ):
        figures.append(
            {
                "name": name,
                "value": _plain(Decimal(measurement[key])),
                "unit": "channels",
                "origin": "estimate",
            }
        )
    return {
        "captured_at": now.isoformat(),
        "scores": {"opportunity": None, "automation": None, "creator_fit": None, "market": None},
        "confidence": CONFIDENCE[evidence["confidence"]],
        "listings_with_income": 0,
        "language_mix": evidence["language_mix"],
        "figures": figures,
    }
```

2. En `authorize`, reemplazar el bloque `detail = niche_detail(...) ... failures = authorization_reasons(...)` por:

```python
    frozen = request["evidence"]
    from_subniche = frozen.get("source") == "subniche"
    detail = None
    if not from_subniche:
        detail = niche_detail(connection, niche_label, format, now, timezone)
        if detail is None:
            raise PilotError("not_found")
    failures = authorization_reasons(dossier, frozen.get("niche"), gates or gate_rules.DEFAULT_GATES)
```

3. En el armado del `body`, reemplazar `"evidence": _evidence(detail, now),` por:

```python
        "evidence": _subniche_evidence(frozen, now) if from_subniche else _evidence(detail, now),
```

(con `assert detail is not None` antes si mypy lo exige) y `_new_pilot_id(connection, niche_label, now)` por `_new_pilot_id(connection, niche_label.removeprefix(SUBNICHE_PREFIX), now)`. Importar `Decimal` si falta.

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_pilots_subniche.py tests/test_pilots_api.py tests/test_niche_gates.py tests/test_flow_research_calibration_gate.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS (Review Focus 6: las autorizaciones del backlog no cambian).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/flow_research/gates.py src/nicheradar/pilots/service.py tests/test_pilots_subniche.py
git commit -m "feat: autorizar un piloto desde un dossier de subnicho"
```

---

### Task 5: Página «Subnichos» del dashboard

**Files:**
- Create: `src/nicheradar/subniche_dashboard.py`
- Modify: `src/nicheradar/dashboard.py` (import, entrada «Subnichos» del selector lateral y su rama)
- Create: `tests/test_subniche_dashboard.py`

**Interfaces:**
- Consumes: `GET /subniches` y `GET /subniches/{slug}` (Task 3), `POST /flow-research` con `niche_label = "subniche:<slug>"` (Task 2) y `render_dossier` de `flow_research_dashboard`; `ApiRequest = Callable[..., dict[str, Any]]` (`api(config, "GET", "/ruta", body=...)`).
- Produces: `subniche_rows(items: list[dict]) -> list[dict]`, `channel_rows(channels: list[dict]) -> list[dict]`, `render_subniches(config: Settings, api: ApiRequest) -> None`; entrada «Subnichos» en el selector lateral.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_subniche_dashboard.py`:

```python
# tests/test_subniche_dashboard.py
from typing import Any

from streamlit.testing.v1 import AppTest

from nicheradar.subniche_dashboard import channel_rows, subniche_rows

HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def item(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "slug": "history_revenge",
        "label": "History Revenge Stories",
        "family": "history",
        "parent_niche_slug": "historical_stories",
        "status": "active",
        "finalist": True,
        "language": "en",
        "format": "long",
        "queries": ["history revenge"],
        "measurement": {
            "measured_at": "2026-10-31T12:00:00+00:00",
            "included": 22,
            "stable_channels": 9,
            "volatile_channels": 13,
            "traction_channels": 5,
            "large_channels": 11,
            "excluded": {"language": 8},
            "income_low": "884.67",
            "income_high": "2022.10",
            "rpm_source": "inherited:historical_stories",
            "signal": "estimable",
        },
        "research": {"id": "r1", "status": "listo", "language": "en", "created_at": "x"},
    }
    return base | over


def test_rows_show_income_range_counts_and_research_status() -> None:
    row = subniche_rows([item()])[0]
    assert row["Subnicho"] == "History Revenge Stories" and row["Finalista"] == "sí"
    assert row["Ingreso por canal (US$)"] == "884.67 – 2022.10"
    assert row["Tracción"] == 5 and row["Estables"] == 9 and row["Grandes"] == 11
    assert row["Investigación"] == "listo"


def test_rows_of_an_unmeasured_hypothesis_have_blanks_and_no_research() -> None:
    row = subniche_rows([item(measurement=None, research=None, finalist=False)])[0]
    assert row["Ingreso por canal (US$)"] == "" and row["Tracción"] is None
    assert row["Finalista"] == "no" and row["Investigación"] == "sin investigar"


def test_channel_rows_keep_hostile_text_as_plain_values() -> None:
    rows = channel_rows(
        [
            {
                "channel_id": "UC1",
                "title": HOSTILE,
                "subscribers": 1200,
                "monthly_long_views": 5000,
                "income_low": "10.00",
                "income_high": "20.00",
                "traction": True,
                "flags": ["young"],
            }
        ]
    )
    assert rows[0]["Canal"] == HOSTILE and rows[0]["Tracción"] == "sí"


def _render(listing: dict[str, Any], card: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    from nicheradar.config import Settings
    from nicheradar.subniche_dashboard import render_subniches

    calls: list[tuple[str, str]] = []

    def api(config: Settings, method: str, path: str, body: Any = None) -> dict[str, Any]:
        calls.append((method, path))
        return listing if path.startswith("/subniches?") else card

    render_subniches(Settings(), api)


def test_the_page_renders_the_list_and_the_card_without_exceptions() -> None:
    card = {
        "hypothesis": item() | {"measurement": None, "research": None},
        "measurement": item()["measurement"],
        "channels": [
            {
                "channel_id": "UC1",
                "title": HOSTILE,
                "subscribers": 1200,
                "monthly_long_views": 5000,
                "income_low": "10.00",
                "income_high": "20.00",
                "traction": True,
                "flags": [],
            }
        ],
        "channels_available": True,
        "research": None,
    }
    app = AppTest.from_function(_render, kwargs={"listing": {"items": [item()]}, "card": card})
    app.run()
    assert not app.exception
    assert any(button.label == "Iniciar investigación de flujo" for button in app.button)
    assert not any("<script>" in block.value for block in app.markdown)
```

(La última aserción exige que el texto hostil nunca llegue a `st.markdown`: los datos se muestran con `st.text` o `st.dataframe`.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_dashboard.py -q 2>&1 | tail -5`
Expected: FAIL por `ModuleNotFoundError: nicheradar.subniche_dashboard`.

- [ ] **Step 3: Implementar la página**

Crear `src/nicheradar/subniche_dashboard.py`:

```python
# src/nicheradar/subniche_dashboard.py
"""Streamlit page for sub-niche hypotheses: measurements, research order and dossier.

Everything that came from YouTube or from a hypothesis is shown with ``st.text`` or a dataframe,
never as Markdown. Income figures are estimates (inherited RPM), not verified earnings.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import streamlit as st

from nicheradar.config import Settings
from nicheradar.flow_research_dashboard import STATUS_LABELS, language_name, render_dossier

ApiRequest = Callable[..., dict[str, Any]]
ALL = "Todas"


def _yes(value: bool) -> str:
    return "sí" if value else "no"


def _income(measurement: dict[str, Any] | None) -> str:
    if measurement is None or measurement["income_low"] is None:
        return ""
    return f"{measurement['income_low']} – {measurement['income_high']}"


def subniche_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in items:
        measurement = entry["measurement"]
        research = entry["research"]
        rows.append(
            {
                "Subnicho": entry["label"],
                "Familia": entry["family"],
                "Estado": entry["status"],
                "Finalista": _yes(entry["finalist"]),
                "Ingreso por canal (US$)": _income(measurement),
                "Tracción": None if measurement is None else measurement["traction_channels"],
                "Estables": None if measurement is None else measurement["stable_channels"],
                "Grandes": None if measurement is None else measurement["large_channels"],
                "Investigación": research["status"] if research else "sin investigar",
            }
        )
    return rows


def channel_rows(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Canal": item["title"] or item["channel_id"],
            "Enlace": f"https://www.youtube.com/channel/{item['channel_id']}",
            "Suscriptores": item["subscribers"],
            "Vistas largas al mes": item["monthly_long_views"],
            "Ingreso (US$)": f"{item['income_low']} – {item['income_high']}"
            if item["income_low"] is not None
            else "",
            "Tracción": _yes(item["traction"]),
            "Señales": ", ".join(item["flags"]),
        }
        for item in channels
    ]


def _render_research(
    config: Settings, api: ApiRequest, hypothesis: dict[str, Any], research: dict[str, Any] | None
) -> None:
    st.markdown("**Investigación de flujo**")
    language = hypothesis["language"]
    st.caption(
        f"Idioma de la hipótesis: {language_name(language)}. La investigación usa el mismo idioma y formato."
    )
    active = research is not None and research["status"] in ("pendiente", "en_curso")
    if research is not None:
        st.caption("Última investigación: " + STATUS_LABELS[research["status"]])
    if st.button("Iniciar investigación de flujo", disabled=active):
        api(
            config,
            "POST",
            "/flow-research",
            body={
                "niche_label": "subniche:" + hypothesis["slug"],
                "format": hypothesis["format"],
                "language": language,
            },
        )
        st.rerun()
    if research is not None and research["status"] == "listo":
        detail = api(config, "GET", f"/flow-research/{research['id']}")
        render_dossier(detail["dossier"])
    elif research is not None and research["status"] == "rechazado":
        detail = api(config, "GET", f"/flow-research/{research['id']}")
        for problem in (detail.get("rejection") or {}).get("problems", []):
            st.text(f"{problem['path']}: {problem['message']}")


def render_subniches(config: Settings, api: ApiRequest) -> None:
    st.subheader("Subnichos: hipótesis medidas")
    st.caption(
        "El ingreso es la mediana mensual estimada por canal estable, con el RPM heredado del nicho "
        "padre: es una estimación, no ingresos verificados. «Tracción» cuenta canales pequeños con "
        "un video largo muy por encima de su tamaño."
    )
    include_inactive = st.checkbox("Mostrar pausadas y archivadas")
    data = api(
        config, "GET", "/subniches?include_inactive=" + ("true" if include_inactive else "false")
    )
    items = data["items"]
    if not items:
        st.info("Todavía no hay hipótesis. Cárgalas con scripts/subniche.py import.")
        return
    filters = st.columns(2)
    families = [ALL, *sorted({entry["family"] for entry in items})]
    family = filters[0].selectbox("Familia", families)
    only_finalists = filters[1].checkbox("Solo finalistas")
    shown = [
        entry
        for entry in items
        if (family == ALL or entry["family"] == family)
        and (not only_finalists or entry["finalist"])
    ]
    st.dataframe(subniche_rows(shown), hide_index=True, width="stretch")
    if not shown:
        return
    by_slug = {entry["slug"]: entry for entry in shown}
    selected = st.selectbox(
        "Abrir subnicho", list(by_slug), format_func=lambda slug: by_slug[slug]["label"]
    )
    card = api(config, "GET", f"/subniches/{quote(selected, safe='')}")
    hypothesis = card["hypothesis"]
    st.markdown("**Hipótesis**")
    st.text(f"{hypothesis['label']} · estado {hypothesis['status']} · {hypothesis['family']}")
    for query in hypothesis["queries"]:
        st.text("Consulta: " + query)
    measurement = card["measurement"]
    if measurement is None:
        st.info("Esta hipótesis todavía no tiene una medición.")
    else:
        st.text(
            f"Medida el {measurement['measured_at']}: {measurement['included']} canales incluidos, "
            f"{measurement['stable_channels']} estables, {measurement['volatile_channels']} "
            f"volátiles, tracción {measurement['traction_channels']}, grandes "
            f"{measurement['large_channels']}. RPM: {measurement['rpm_source']}"
        )
    st.markdown("**Canales relevantes**")
    if card["channels_available"]:
        st.dataframe(channel_rows(card["channels"]), hide_index=True, width="stretch")
    else:
        st.caption("Los datos de canales vencieron (30 días) o no hay medición vigente.")
    if measurement is not None:
        _render_research(config, api, hypothesis, card["research"])
```

En `src/nicheradar/dashboard.py`: importar `from nicheradar.subniche_dashboard import render_subniches`, añadir `"Subnichos"` a la lista del `st.sidebar.radio("Observatorio", [...])` justo después de `"Mercado"`, y la rama `elif page == "Subnichos": render_subniches(config, api_request)` tras la de «Mercado».

- [ ] **Step 4: Ejecutar pruebas, ruff y mypy**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_subniche_dashboard.py tests/test_flow_research_dashboard.py tests/test_market_dashboard.py -q 2>&1 | tail -4; uv run ruff format src tests -q; uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/subniche_dashboard.py src/nicheradar/dashboard.py tests/test_subniche_dashboard.py
git commit -m "feat: página Subnichos del dashboard con investigación de flujo"
```

---

### Task 6: Skill y documentación

**Files:**
- Modify: `.claude/skills/flow-research/SKILL.md`
- Modify: `docs/subniche-discovery.md`, `docs/flow-research.md`, `docs/comandos.md`
- Modify: `tests/test_flow_research_create.py` (aguja de la skill)

**Interfaces:**
- Consumes: el comportamiento de las Tasks 1-5.
- Produces: la skill sabe leer una evidencia de subnicho; documentación del flujo y de los comandos.

- [ ] **Step 1: Escribir la prueba que falla**

En `tests/test_flow_research_create.py`, en el test de las agujas de la skill (`test_the_skill_asks_for_v3_calibration_and_the_plan_and_forbids_overrides`), añadir a la tupla: `"subniche:"`, `"evidence.source"`, `"measurement"`.

Run: `uv run pytest tests/test_flow_research_create.py -q 2>&1 | tail -3`
Expected: FAIL (la skill no menciona encargos de subnicho).

- [ ] **Step 2: Implementar los cambios de la skill y los documentos**

En `.claude/skills/flow-research/SKILL.md`, antes de `## Pasos`, añadir:

```markdown
## Encargos de subnicho (`niche_label` = `subniche:<slug>`)

Si el `niche_label` empieza con `subniche:`, el encargo viene de una hipótesis medida por el descubrimiento de
subnichos, no del backlog de Mercado: `evidence.source` es `subniche` y `evidence.niche` es `null`. La evidencia
congelada trae `evidence.subniche` (hipótesis, consultas, familia, idioma y formato), `evidence.measurement` (canales
incluidos, estables, volátiles, de tracción, grandes, exclusiones por idioma y rango de ingreso mensual
**por canal estable**, con RPM heredado del nicho padre: es una estimación) y `evidence.channels` (los canales más
relevantes, o vacío si los datos de 30 días vencieron: `channels_available`). No hay score de automatización: no
inventes uno; esa compuerta no aplica, pero sí las de minutos de régimen, horas de calibración y derechos. Con
`evidence.confidence` `baja`, declara en `verdict.unknowns` qué no pudiste verificar. Investiga la competencia en el
idioma del encargo partiendo de `evidence.channels` y de las consultas, y no copies el `niche_label` con otro texto:
el dossier lo repite igual (`subniche:<slug>`).
```

En `docs/subniche-discovery.md`, añadir una sección `## Dashboard e investigación de flujo` con: la página **Subnichos** del dashboard (lista con casilla de pausadas y archivadas, ficha con canales y botón «Iniciar investigación de flujo»); el encargo `subniche:<slug>` (formato e idioma de la hipótesis; elegibilidad: `active` y con medición); la autorización del piloto con `scripts/pilots.py lanzar` usando `niche_label = subniche:<slug>`; y la forma de la evidencia en el paquete (`scores` nulos, cifras con origen `estimate`, `confidence` `low` con menos de 10 canales). En `docs/flow-research.md`, una línea en «Cómo se opera» que remita a esa sección. En `docs/comandos.md`, en la sección de subnichos, la fila `GET /api/v1/subniches` y la nota de que `pilots.py lanzar` acepta `subniche:<slug>`.

- [ ] **Step 3: Validación completa**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_flow_research_create.py -q 2>&1 | tail -3; uv run ruff check . && uv run ruff format --check . && uv run mypy; NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q 2>&1 | tail -4`
Expected: todo en verde; la suite completa pasa con Postgres.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/flow-research/SKILL.md docs tests/test_flow_research_create.py
git commit -m "docs: skill y documentación de subnichos en el dashboard e investigación desde una hipótesis"
```

---

## Fuera de este plan (necesita aprobación del propietario)

Release (imágenes, digests y despliegue) y la lectura real de los 60 subnichos en producción. El código no cambia la base de datos.

## Self-Review

- **Cobertura del spec:** identidad `subniche:<slug>` sin migración (Task 2); evidencia congelada, elegibilidad y compuertas (Task 2); API de lectura (Task 3); autorización del piloto con forma `pilot-package-v1` (Task 4); página Subnichos con lista, casilla de inactivas, ficha y botón (Task 5); skill y documentación (Task 6); catálogo de herramientas fuera de alcance, como dice el spec.
- **Ruling 1:** el spec dice que un `niche_label` del backlog que empiece con `subniche:` «se rechaza»; el plan lo enruta siempre al flujo de subnichos y, sin hipótesis, devuelve `not_found`: el efecto es el mismo (no se puede abrir un nicho del backlog con ese prefijo) sin una comprobación adicional.
- **Ruling 2:** el panel muestra el ingreso como «mediana mensual estimada por canal estable». Es lo que guarda `hypothesis_snapshots.median_income_low/high` (mediana de los canales estables), no un agregado del subnicho; las investigaciones y el informe anteriores lo llamaban «agregado» y deben corregirse.
- **Consistencia de tipos:** `research_label`/`slug_of`/`PREFIX` (Task 1) los usan Tasks 2, 3, 4 y 5; `build_subniche_evidence(detail, gates, gate_override)` produce las claves que lee `_subniche_evidence` (`measurement`, `confidence`, `language_mix`); `authorization_reasons(dossier, niche | None, gates)` recibe `frozen.get("niche")`.
- **Sin placeholders:** cada paso de código trae el código; las notas entre paréntesis indican dónde seguir la forma de una prueba vecina si una firma de ayudante difiere.
