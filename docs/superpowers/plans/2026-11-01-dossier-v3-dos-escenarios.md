# dossier-v3 (tiempo humano en dos escenarios) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el contrato de investigación de flujo separe los minutos humanos de calibración y de régimen, y que la compuerta compare el régimen (con evidencia) y las horas de calibración.

**Architecture:** `dossier-v3` es una versión nueva del contrato (mismo patrón que v1 → v2): `DossierV2` y los dossiers guardados siguen legibles, los encargos nuevos exigen v3. `human_minutes_per_video` pasa a significar solo régimen (lo que ya suma la compuerta); la calibración vive en un objeto `calibration` con minutos por paso, horas de preparación y criterio de salida; la evidencia del régimen en `steady_state_evidence`. No hay cambios de base de datos.

**Tech Stack:** Python 3.13, pydantic v2, pytest, Streamlit (panel), uv.

**Spec:** `docs/superpowers/specs/2026-11-01-dossier-v3-dos-escenarios-design.md`

## Global Constraints

- Los encargos nuevos exigen `schema_version = "dossier-v3"`; `dossier-v1` y `dossier-v2` se rechazan en encargos nuevos con el mensaje `"<versión> ya no se acepta en encargos nuevos: usa dossier-v3"`, pero siguen legibles en lo guardado (`authorization_reasons`, panel, pilotos).
- `human_minutes_per_video` (por paso y por etapa de `automation_plan`) = **régimen**; el total sigue derivándose como la suma de `production_flow[].human_minutes_per_video`, nunca declarado.
- `NR_GATE_MAX_HUMAN_MINUTES` = 60 (sin cambios) compara solo el régimen. Nueva `NR_GATE_MAX_CALIBRATION_HOURS` = 40 (supuesto inicial, no medido).
- `calibration.total_hours` se deriva: `setup_hours + videos × Σ(minutes_by_step) / 60`, redondeado a 2 decimales; si el payload lo declara, es un campo no permitido.
- La calibración de un paso nunca puede ser menor que su régimen.
- Con `steady_state_evidence.basis = "estimate"` el dossier no puede recomendar `go`; con `go_with_conditions` el `exit_criterion.statement` debe estar literalmente entre `verdict.conditions`.
- Misma excepción registrada (`gate_override`) para todas las compuertas; `no_go` siempre se acepta; derechos `blocked` siguen sin excepción.
- Los mensajes de error no devuelven los valores enviados (patrón existente en `contracts.py`).
- El 90 % de automatización del backlog (`niche_reasons`) no cambia.
- Sin cambios de esquema de base de datos ni migración Alembic.
- Comentarios y mensajes visibles en español; nombres de código en inglés, como el resto del paquete.

## Review Focus

1. Un dossier con régimen `estimate` y recomendación `go` (o `go_with_conditions` sin el criterio de salida entre las condiciones) debe rechazarse; con `measured` o `mapped_flow_equivalent` y `go` debe aceptarse.
2. Un dossier `dossier-v2` ya guardado debe seguir pasando por `authorization_reasons` y por el panel sin error y sin cambio de resultado.
3. `calibration.minutes_by_step` que omite un paso, repite uno, o trae un valor menor que el régimen debe rechazarse con la ruta del campo.
4. Payload que declara `calibration.total_hours` a mano debe rechazarse como campo no permitido sin repetir su valor.
5. Un encargo ordenado con un tope de calibración distinto del vigente al enviar el dossier se evalúa con el tope vigente (como ya pasa con los minutos).

---

### Task 1: Contrato `dossier-v3`

**Files:**
- Modify: `src/nicheradar/flow_research/contracts.py`
- Modify: `tests/flow_research_samples.py`
- Modify: `tests/test_dossier_v2.py` (mensaje de versión nueva)
- Create: `tests/test_dossier_v3.py`

**Interfaces:**
- Consumes: modelos existentes (`Contract`, `DossierBody`, `Verdict`, `Label`, `Text`, `ProductionStep`, `AutomationPlan`, `Rights`).
- Produces: `SCHEMA_VERSION = "dossier-v3"`, `LEGACY_SCHEMA_VERSIONS = ("dossier-v1", "dossier-v2")`, `DossierV3`, `RightsDossier` (base común de `DossierV2` y `DossierV3`), `calibration_total_hours(setup_hours: float, videos: int, minutes_per_video: int) -> float`, `validate_dossier(...) -> tuple[DossierV3 | None, list[Problem]]`; en las pruebas, `valid_dossier` devuelve un dossier v3 y `valid_dossier_v2` uno v2.

- [ ] **Step 1: Actualizar la muestra y escribir las pruebas que fallan**

En `tests/flow_research_samples.py`, cambiar la cabecera de `valid_dossier` y su construcción para producir v3, y añadir `valid_dossier_v2`. Dentro del `return {` de `valid_dossier`, cambiar `"schema_version": "dossier-v2",` por `"schema_version": "dossier-v3",`; en `"verdict"` añadir la clave `"conditions"`; y añadir tras `"sources": [...]` las claves nuevas. Resultado concreto (los demás campos quedan como están):

```python
        "verdict": {
            "recommendation": "go_with_conditions",
            "confidence": "medium",
            "thesis": "Nicho con demanda estable y producción parcialmente automatizable.",
            "main_risks": ["Dependencia de voz sintética aceptada por la plataforma"],
            "unknowns": ["RPM real del nicho en el país objetivo"],
            "conditions": [EXIT_STATEMENT],
        },
```

Al inicio del archivo (tras los imports) añadir:

```python
EXIT_STATEMENT = "Pasar a régimen tras 3 videos seguidos bajo 60 minutos humanos"
```

Y al final del diccionario devuelto, tras `"sources": [...]`, antes del `}` de cierre:

```python
        "calibration": {
            "videos": 6,
            "setup_hours": 8.0,
            "exit_criterion": {
                "max_minutes_per_video": 60,
                "consecutive_videos": 3,
                "statement": EXIT_STATEMENT,
            },
            "minutes_by_step": [
                {"step": "Guion", "minutes_per_video": 40},
                {"step": "Voz", "minutes_per_video": 10},
                {"step": "Edición", "minutes_per_video": 45},
            ],
        },
        "steady_state_evidence": {
            "basis": "measured",
            "reference_channel": "canal-historias",
            "reference_minutes_per_video": 20,
            "reference_sample_videos": 10,
            "format_match": "Mismo formato (narración larga sin rostro) e idioma (inglés)",
        },
```

Actualizar el docstring a `"""A complete, internally consistent dossier-v3 (JSON-shaped, as the skill sends it)."""` y añadir al final del archivo:

```python
def valid_dossier_v2(request_id: UUID, now: datetime) -> dict[str, Any]:
    """The same dossier as ``valid_dossier`` in the dossier-v2 shape (stored before dossier-v3)."""
    payload = copy.deepcopy(valid_dossier(request_id, now))
    payload["schema_version"] = "dossier-v2"
    del payload["calibration"], payload["steady_state_evidence"]
    del payload["verdict"]["conditions"]
    return payload
```

con `import copy` junto a los imports del archivo.

Crear `tests/test_dossier_v3.py`:

```python
# tests/test_dossier_v3.py
"""dossier-v3: calibración y régimen, con evidencia del régimen."""

import copy
from typing import Any
from uuid import UUID

from nicheradar.flow_research.contracts import (
    DossierV2,
    DossierV3,
    calibration_total_hours,
    validate_dossier,
)
from tests.flow_research_samples import EXIT_STATEMENT, valid_dossier, valid_dossier_v2
from tests.test_persistence import NOW

ID = UUID(int=9)


def sample() -> dict[str, Any]:
    return copy.deepcopy(valid_dossier(ID, NOW))


def paths(payload: dict[str, Any]) -> set[str]:
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    return {problem["path"] for problem in problems}


def test_the_sample_is_a_valid_v3_dossier_with_derived_hours_and_regime_minutes() -> None:
    dossier, problems = validate_dossier(sample(), NOW)
    assert problems == [] and isinstance(dossier, DossierV3)
    assert dossier.human_minutes_per_video == 55  # régimen: suma del flujo
    assert dossier.calibration_hours == 17.5  # 8 + 6 × 95 / 60


def test_calibration_total_hours_adds_setup_and_per_video_minutes() -> None:
    assert calibration_total_hours(8.0, 6, 95) == 17.5
    assert calibration_total_hours(0.0, 1, 90) == 1.5


def test_v1_and_v2_are_refused_in_new_requests_with_the_v3_message() -> None:
    for version in ("dossier-v1", "dossier-v2"):
        dossier, problems = validate_dossier(sample() | {"schema_version": version}, NOW)
        assert dossier is None
        assert problems == [
            {
                "path": "schema_version",
                "message": f"{version} ya no se acepta en encargos nuevos: usa dossier-v3",
            }
        ]


def test_a_stored_v2_dossier_still_parses_as_the_legacy_model() -> None:
    legacy = DossierV2.model_validate(valid_dossier_v2(ID, NOW))
    assert legacy.human_minutes_per_video == 55


def test_calibration_and_steady_state_evidence_are_mandatory() -> None:
    for key in ("calibration", "steady_state_evidence"):
        payload = sample()
        del payload[key]
        assert key in paths(payload)


def test_a_declared_total_of_hours_is_not_allowed_and_its_value_is_not_echoed() -> None:
    payload = sample()
    payload["calibration"]["total_hours"] = 999.123456
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    assert {"path": "calibration.(campo no permitido)", "message": problems[0]["message"]} in problems
    assert "999.123456" not in str(problems)


def test_minutes_by_step_must_cover_every_step_once() -> None:
    payload = sample()
    del payload["calibration"]["minutes_by_step"][2]
    assert "calibration.minutes_by_step" in paths(payload)
    payload = sample()
    payload["calibration"]["minutes_by_step"][2]["step"] = "Guion"
    assert "calibration.minutes_by_step" in paths(payload)


def test_calibration_cannot_cost_fewer_minutes_than_the_regime() -> None:
    payload = sample()
    payload["calibration"]["minutes_by_step"][0]["minutes_per_video"] = 19  # régimen: 20
    assert "calibration.minutes_by_step.0.minutes_per_video" in paths(payload)


def test_a_measured_regime_declares_its_channel_minutes_and_sample() -> None:
    payload = sample()
    payload["steady_state_evidence"]["reference_minutes_per_video"] = None
    assert "steady_state_evidence.reference_minutes_per_video" in paths(payload)
    payload = sample()
    payload["steady_state_evidence"]["reference_channel"] = None
    assert "steady_state_evidence.reference_channel" in paths(payload)


def test_a_mapped_flow_equivalent_only_needs_the_reference_channel() -> None:
    payload = sample()
    evidence = payload["steady_state_evidence"]
    evidence["basis"] = "mapped_flow_equivalent"
    evidence["reference_minutes_per_video"] = None
    evidence["reference_sample_videos"] = None
    dossier, problems = validate_dossier(payload, NOW)
    assert problems == [] and dossier is not None


def estimate_payload(recommendation: str, conditions: list[str]) -> dict[str, Any]:
    payload = sample()
    payload["steady_state_evidence"] = {
        "basis": "estimate",
        "format_match": "Formato nuevo: ningún canal propio lo ha producido",
    }
    payload["verdict"]["recommendation"] = recommendation
    payload["verdict"]["conditions"] = conditions
    return payload


def test_an_estimated_regime_cannot_recommend_go() -> None:
    assert "verdict.recommendation" in paths(estimate_payload("go", []))


def test_an_estimated_regime_with_conditions_must_state_the_exit_criterion_verbatim() -> None:
    assert "verdict.conditions" in paths(estimate_payload("go_with_conditions", ["Otra cosa"]))
    ok, problems = validate_dossier(estimate_payload("go_with_conditions", [EXIT_STATEMENT]), NOW)
    assert problems == [] and ok is not None


def test_an_estimated_regime_is_fine_for_no_go() -> None:
    ok, problems = validate_dossier(estimate_payload("no_go", []), NOW)
    assert problems == [] and ok is not None


def test_a_measured_regime_can_recommend_go_without_conditions() -> None:
    payload = sample()
    payload["verdict"]["recommendation"] = "go"
    payload["verdict"]["conditions"] = []
    ok, problems = validate_dossier(payload, NOW)
    assert problems == [] and ok is not None


def test_go_with_conditions_must_list_conditions_whatever_the_basis() -> None:
    payload = sample()
    payload["verdict"]["conditions"] = []
    assert "verdict.conditions" in paths(payload)
```

En `tests/test_dossier_v2.py`, reemplazar el cuerpo de `test_a_new_dossier_must_be_v2_and_the_message_says_so` por:

```python
def test_a_new_dossier_must_be_v3_and_the_message_says_so() -> None:
    payload = sample() | {"schema_version": "dossier-v1"}
    assert problems_of(payload) == [
        {
            "path": "schema_version",
            "message": "dossier-v1 ya no se acepta en encargos nuevos: usa dossier-v3",
        }
    ]
```

y cambiar `assert problems == [] and isinstance(dossier, DossierV2)` en `test_the_sample_is_a_valid_v2_dossier_and_minutes_are_derived_from_the_flow` por `isinstance(dossier, DossierV3)` (importar `DossierV3` en lugar de `DossierV2` en ese archivo) y renombrar esa prueba a `test_the_sample_is_a_valid_dossier_and_minutes_are_derived_from_the_flow`.

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `uv run pytest tests/test_dossier_v3.py tests/test_dossier_v2.py -q 2>&1 | tail -15`
Expected: FAIL por `ImportError: cannot import name 'DossierV3'`.

- [ ] **Step 3: Implementar el contrato v3**

En `src/nicheradar/flow_research/contracts.py`:

3a. Cambiar las constantes de versión (junto a `SCHEMA_VERSION = "dossier-v2"` y `LEGACY_SCHEMA_VERSION`):

```python
SCHEMA_VERSION = "dossier-v3"
LEGACY_SCHEMA_VERSIONS = ("dossier-v1", "dossier-v2")
```

(la constante `LEGACY_SCHEMA_VERSION` desaparece; su único uso está en `validate_dossier`, que se reescribe en 3e. Buscar con `grep -rn LEGACY_SCHEMA_VERSION src tests` y corregir cualquier otro uso.)

3b. Reemplazar la clase `DossierV2` por la base común y las dos versiones (la clase `DossierV2` conserva exactamente sus campos):

```python
class RightsDossier(DossierBody):
    """Fields of dossier-v2 and dossier-v3: rights and the per-stage automation plan."""

    rights: Rights
    automation_plan: AutomationPlan

    @property
    def human_minutes_per_video(self) -> int:
        return human_minutes_per_video(self)


class DossierV2(RightsDossier):
    """dossier-v2: kept only to read dossiers stored before dossier-v3."""

    schema_version: Literal["dossier-v2"]


class VerdictV3(Verdict):
    conditions: list[Text] = Field(max_length=10)


class CalibrationStep(Contract):
    step: Label
    minutes_per_video: int = Field(ge=0, le=10_000)


class ExitCriterion(Contract):
    max_minutes_per_video: int = Field(ge=1, le=10_000)
    consecutive_videos: int = Field(ge=1, le=12)
    statement: Text


class Calibration(Contract):
    """The first videos of a channel, while the flow is built and tuned (not a per-video cost)."""

    videos: int = Field(ge=1, le=12)
    setup_hours: float = Field(ge=0, le=1000)
    exit_criterion: ExitCriterion
    minutes_by_step: list[CalibrationStep] = Field(min_length=3, max_length=15)


SteadyBasis = Literal["measured", "mapped_flow_equivalent", "estimate"]


class SteadyStateEvidence(Contract):
    """What backs the regime minutes: a timed channel, an equivalent mapped flow, or a guess."""

    basis: SteadyBasis
    reference_channel: Label | None = None
    reference_minutes_per_video: int | None = Field(default=None, ge=0, le=10_000)
    reference_sample_videos: int | None = Field(default=None, ge=1, le=10_000)
    format_match: Text


class DossierV3(RightsDossier):
    schema_version: Literal["dossier-v3"]
    verdict: VerdictV3
    calibration: Calibration
    steady_state_evidence: SteadyStateEvidence

    @property
    def calibration_hours(self) -> float:
        return calibration_total_hours(
            self.calibration.setup_hours,
            self.calibration.videos,
            sum(item.minutes_per_video for item in self.calibration.minutes_by_step),
        )


def calibration_total_hours(setup_hours: float, videos: int, minutes_per_video: int) -> float:
    """Derived, never declared: preparation plus the human minutes of every calibration video."""
    return round(setup_hours + videos * minutes_per_video / 60, 2)
```

3c. Cambiar la anotación de `v2_problems` de `dossier: DossierV2` a `dossier: RightsDossier`.

3d. Añadir `v3_problems` tras `v2_problems`:

```python
def v3_problems(dossier: DossierV3) -> list[Problem]:
    """Calibration against the flow, and what the regime minutes are allowed to promise."""
    problems: list[Problem] = []

    def add(path: str, message: str) -> None:
        problems.append({"path": path, "message": message})

    regime = {step.name: step.human_minutes_per_video for step in dossier.production_flow}
    steps = [item.step for item in dossier.calibration.minutes_by_step]
    if len(set(steps)) != len(steps) or set(steps) != set(regime):
        add("calibration.minutes_by_step", "debe haber un valor por cada paso de production_flow")
    for index, item in enumerate(dossier.calibration.minutes_by_step):
        steady = regime.get(item.step)
        if steady is not None and item.minutes_per_video < steady:
            add(
                f"calibration.minutes_by_step.{index}.minutes_per_video",
                "la calibración no puede costar menos minutos que el régimen",
            )

    evidence = dossier.steady_state_evidence
    if evidence.basis != "estimate" and evidence.reference_channel is None:
        add("steady_state_evidence.reference_channel", "cita el canal de referencia")
    if evidence.basis == "measured" and (
        evidence.reference_minutes_per_video is None or evidence.reference_sample_videos is None
    ):
        add(
            "steady_state_evidence.reference_minutes_per_video",
            "un régimen medido declara los minutos y cuántos videos se midieron",
        )

    recommendation = dossier.verdict.recommendation
    conditions = dossier.verdict.conditions
    if recommendation == "go_with_conditions" and not conditions:
        add("verdict.conditions", "go_with_conditions debe listar sus condiciones")
    if evidence.basis == "estimate":
        if recommendation == "go":
            add(
                "verdict.recommendation",
                "el régimen es una estimación: usa go_with_conditions o no_go",
            )
        elif (
            recommendation == "go_with_conditions"
            and dossier.calibration.exit_criterion.statement not in conditions
        ):
            add("verdict.conditions", "incluye el criterio de salida de la calibración tal cual")
    return problems
```

3e. Reescribir `validate_dossier`:

```python
def validate_dossier(payload: object, now: datetime) -> tuple[DossierV3 | None, list[Problem]]:
    """Return the dossier, or ``None`` with every problem found; never raises on bad input.

    Only ``dossier-v3`` is accepted: v1 and v2 exist solely for stored dossiers.
    """
    if isinstance(payload, dict) and payload.get("schema_version") in LEGACY_SCHEMA_VERSIONS:
        return None, [
            {
                "path": "schema_version",
                "message": (
                    f"{payload['schema_version']} ya no se acepta en encargos nuevos: "
                    "usa dossier-v3"
                ),
            }
        ]
    try:
        dossier = DossierV3.model_validate(payload)
    except ValidationError as error:
        return None, [
            _problem(item)
            for item in error.errors(include_url=False, include_context=False, include_input=False)[
                :MAX_PROBLEMS
            ]
        ]
    problems = (
        consistency_problems(dossier, now) + v2_problems(dossier) + v3_problems(dossier)
    )[:MAX_PROBLEMS]
    return (None if problems else dossier), problems
```

Actualizar el docstring del módulo: `"""dossier-v3: the structured result a researcher hands back (v1 and v2 are legacy, read-only).`

- [ ] **Step 4: Ejecutar las pruebas del contrato**

Run: `uv run pytest tests/test_dossier_v3.py tests/test_dossier_v2.py tests/test_flow_research_contracts.py -q 2>&1 | tail -15`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/flow_research/contracts.py tests/flow_research_samples.py tests/test_dossier_v3.py tests/test_dossier_v2.py
git commit -m "feat: dossier-v3 con calibración y régimen del tiempo humano"
```

---

### Task 2: Compuerta de calibración, configuración y servicio

**Files:**
- Modify: `src/nicheradar/config.py` (cerca de la línea 107)
- Modify: `src/nicheradar/flow_research/gates.py`
- Modify: `src/nicheradar/flow_research/service.py`
- Create: `tests/test_flow_research_calibration_gate.py`
- Modify: `tests/test_niche_gates.py` (solo si algún test deja de pasar por el cambio de la muestra)

**Interfaces:**
- Consumes: `calibration_total_hours`, `DossierV3.calibration_hours`, `valid_dossier`, `valid_dossier_v2` (Task 1); `Gates`, `minutes_reasons`, `authorization_reasons`.
- Produces: `Settings.gate_max_calibration_hours: float`, `Gates.max_calibration_hours: float` (último campo, defecto 40), `calibration_reasons(hours: float, gates: Gates) -> list[GateReason]`, gate id `"calibration_hours"`, clave `max_calibration_hours` en `annotation(...)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_flow_research_calibration_gate.py`:

```python
# tests/test_flow_research_calibration_gate.py
"""Compuerta de horas de calibración: al enviar el dossier y al autorizar el piloto."""

import copy
from uuid import UUID

from nicheradar.config import Settings
from nicheradar.flow_research.gates import (
    Gates,
    annotation,
    authorization_reasons,
    calibration_reasons,
)
from tests.flow_research_samples import valid_dossier, valid_dossier_v2
from tests.test_persistence import NOW

ID = UUID(int=11)
NICHE = {"automation": {"value": 95, "policy_risk": {"level": "bajo"}}, "decision": {}}


def test_calibration_hours_over_the_limit_give_one_reason_naming_both_numbers() -> None:
    reasons = calibration_reasons(50.5, Gates(max_calibration_hours=40))
    assert [reason["gate"] for reason in reasons] == ["calibration_hours"]
    assert "50.5" in reasons[0]["message"] and "40" in reasons[0]["message"]


def test_calibration_hours_at_or_under_the_limit_pass() -> None:
    assert calibration_reasons(40, Gates(max_calibration_hours=40)) == []
    assert calibration_reasons(0, Gates()) == []


def test_the_default_limit_is_forty_hours_and_comes_from_the_settings() -> None:
    assert Gates().max_calibration_hours == 40
    config = Settings(gate_max_calibration_hours=12.5)  # type: ignore[call-arg]
    assert Gates.from_settings(config).max_calibration_hours == 12.5


def test_the_frozen_annotation_records_the_calibration_limit() -> None:
    assert annotation(NICHE, Gates(max_calibration_hours=25))["max_calibration_hours"] == 25


def test_authorization_checks_the_calibration_hours_of_a_stored_v3_dossier() -> None:
    stored = copy.deepcopy(valid_dossier(ID, NOW))  # 17,5 horas de calibración
    assert authorization_reasons(stored, NICHE, Gates(max_calibration_hours=40)) == []
    reasons = authorization_reasons(stored, NICHE, Gates(max_calibration_hours=10))
    assert [reason["gate"] for reason in reasons] == ["calibration_hours"]


def test_authorization_of_a_stored_v2_dossier_is_unchanged_and_ignores_calibration() -> None:
    stored = copy.deepcopy(valid_dossier_v2(ID, NOW))
    assert authorization_reasons(stored, NICHE, Gates(max_calibration_hours=0)) == []
    reasons = authorization_reasons(stored, NICHE, Gates(max_human_minutes=40))
    assert [reason["gate"] for reason in reasons] == ["human_minutes"]
```

Y las pruebas del servicio (mismo archivo, al final), con las fixtures del módulo `tests/test_niche_gates.py` (`db`, `claimed`, `dossier_for`, `STRICT`). Para reutilizarlas sin duplicar, importar desde allí:

```python
from sqlalchemy import Connection

from nicheradar.flow_research.service import submit_dossier
from tests.test_niche_gates import STRICT, claimed, db, dossier_for  # noqa: F401  (db es fixture)


def test_a_go_dossier_over_the_calibration_limit_is_rejected_but_no_go_is_not(
    db: Connection,
) -> None:
    request_id, owner = claimed(db, STRICT)
    tight = Gates(70, 60, True, max_calibration_hours=10)  # la muestra necesita 17,5 horas
    result = submit_dossier(db, request_id, owner, dossier_for(request_id), NOW, tight)
    assert result["accepted"] is False
    problem = result["problems"][0]
    assert problem["path"] == "verdict.recommendation"
    assert "17.5" in problem["message"] and "10" in problem["message"]
    no_go = dossier_for(request_id, recommendation="no_go")
    assert submit_dossier(db, request_id, owner, no_go, NOW, tight)["accepted"] is True


def test_a_recorded_override_lifts_the_calibration_gate(db: Connection) -> None:
    from nicheradar.flow_research.service import claim_request, create_request
    from tests.test_niche_gates import niche

    niche(db, "philosophy", automation=1, policy=1)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = create_request(
        db, "philosophy", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    tight = Gates(70, 60, True, max_calibration_hours=10)
    body = dossier_for(request["id"])
    assert submit_dossier(db, request["id"], owner, body, NOW, tight)["accepted"] is True
```

(Si `db` no se exporta como fixture desde `test_niche_gates.py`, copiar su definición exacta de ese archivo en lugar de importarla. Comprobar con `grep -n "def db\|fixture" tests/test_niche_gates.py`.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_flow_research_calibration_gate.py -q 2>&1 | tail -15`
Expected: FAIL por `ImportError: cannot import name 'calibration_reasons'` (las de base de datos se saltan sin Postgres de prueba; ver Nota).

- [ ] **Step 3: Implementar**

En `src/nicheradar/config.py`, tras `gate_max_human_minutes`:

```python
    # Horas de calibración (primeros videos de un canal): supuesto inicial, no medido. El propietario
    # reportó 2 a 3 horas semanales en la primera semana de canal-historias.
    gate_max_calibration_hours: float = Field(default=40, ge=0, le=10_000)
```

En `src/nicheradar/flow_research/gates.py`:

- Importar: `from nicheradar.flow_research.contracts import calibration_total_hours`.
- `GateReason.gate` comentario: `# automation | policy_risk | human_minutes | calibration_hours | rights`.
- Añadir a `Gates` el último campo y a `from_settings`:

```python
@dataclass(frozen=True)
class Gates:
    min_automation: float = 90
    max_human_minutes: int = 60
    block_high_policy_risk: bool = True
    max_calibration_hours: float = 40

    @classmethod
    def from_settings(cls, config: Settings) -> Self:
        return cls(
            config.gate_min_automation,
            config.gate_max_human_minutes,
            config.gate_block_high_policy_risk,
            config.gate_max_calibration_hours,
        )
```

- Tras `minutes_reasons`:

```python
def calibration_reasons(hours: float, gates: Gates) -> list[GateReason]:
    if hours > gates.max_calibration_hours:
        return [
            {
                "gate": "calibration_hours",
                "message": f"La calibración exige {hours:g} horas y el máximo es "
                f"{gates.max_calibration_hours:g}.",
            }
        ]
    return []
```

- En `annotation`, añadir `"max_calibration_hours": gates.max_calibration_hours,` junto a `"max_human_minutes"`.
- En `authorization_reasons`, tras `reasons += minutes_reasons(minutes, gates)`:

```python
    calibration = dossier.get("calibration")
    if calibration is not None:
        hours = calibration_total_hours(
            calibration["setup_hours"],
            calibration["videos"],
            sum(item["minutes_per_video"] for item in calibration["minutes_by_step"]),
        )
        reasons += calibration_reasons(hours, gates)
```

- Actualizar el docstring del módulo: añadir `NR_GATE_MAX_CALIBRATION_HOURS` a la lista.

En `src/nicheradar/flow_research/service.py`:

- Importar `DossierV3` y `calibration_reasons`; reemplazar `DossierV2` por `DossierV3` en las dos firmas (`_gate_problems`, `_request_problems`) y en los imports.
- En `_gate_problems`, dentro de `if "gate_override" not in evidence:` tras `reasons += minutes_reasons(...)`: `reasons += calibration_reasons(dossier.calibration_hours, gates)`.

- [ ] **Step 4: Ejecutar pruebas**

Run: `uv run pytest tests/test_flow_research_calibration_gate.py tests/test_niche_gates.py tests/test_flow_research_service.py -q 2>&1 | tail -15`
Expected: PASS (las que necesitan Postgres de prueba se ejecutan si está disponible; si se saltan, decirlo explícitamente en el informe).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/config.py src/nicheradar/flow_research/gates.py src/nicheradar/flow_research/service.py tests/test_flow_research_calibration_gate.py
git commit -m "feat: compuerta de horas de calibración del dossier-v3"
```

---

### Task 3: Piezas que leen el dossier (pilotos, CLI y panel)

**Files:**
- Modify: `src/nicheradar/pilots/contracts.py:119`
- Modify: `src/nicheradar/flow_research/cli.py` (líneas 14, 49, 62)
- Modify: `src/nicheradar/flow_research_dashboard.py` (`render_dossier`, líneas ~224-265)
- Modify: `tests/test_flow_research_create.py` (líneas 39 y 76), `tests/test_flow_research_client.py` (línea 114), `tests/test_flow_research_dashboard.py`

**Interfaces:**
- Consumes: `DossierV3`, `valid_dossier`, `valid_dossier_v2` (Task 1); `calibration_total_hours` (Task 1).
- Produces: `calibration_rows(content: dict[str, Any]) -> list[dict[str, Any]]` en el panel; `schema` de pilotos acepta `"dossier-v3"`; el comando `schema` imprime `DossierV3`.

- [ ] **Step 1: Escribir/ajustar las pruebas que fallan**

`tests/test_flow_research_create.py`: línea 39 → `assert properties["schema_version"]["const"] == "dossier-v3"` y línea ~76 → cambiar la aguja `"dossier-v2"` por `"dossier-v3"` y añadir `"calibration"`, `"steady_state_evidence"` a la tupla de agujas del skill (ese test se completa con la edición del skill en la Task 4; dejarlo fallando hasta entonces está permitido, pero marcarlo con `uv run pytest ... -k` para esta tarea; ver Step 4).

`tests/test_flow_research_client.py` línea 114: `schema["title"] == "DossierV3"`.

`tests/test_flow_research_dashboard.py`: en `stored_shape` usar `DossierV3` (`from nicheradar.flow_research.contracts import DossierV3`) y añadir:

```python
def test_calibration_rows_show_regime_and_calibration_minutes_per_step() -> None:
    content = stored_shape()
    rows = calibration_rows(content)
    assert [row["Etapa"] for row in rows] == ["Guion", "Voz", "Edición"]
    assert rows[0]["Minutos en régimen"] == 20 and rows[0]["Minutos en calibración"] == 40


def test_a_stored_v2_dossier_renders_without_the_calibration_section() -> None:
    from nicheradar.flow_research.contracts import DossierV2
    from tests.flow_research_samples import valid_dossier_v2

    legacy = DossierV2.model_validate(valid_dossier_v2(UUID(int=1), NOW)).model_dump(mode="json")
    app = AppTest.from_function(_render, kwargs={"content": legacy}).run()
    assert not app.exception
    assert not any("Calibración" in item.value for item in app.markdown)


def test_a_v3_dossier_renders_the_calibration_and_the_regime_evidence() -> None:
    app = AppTest.from_function(_render, kwargs={"content": stored_shape()}).run()
    assert not app.exception
    assert any("Calibración" in item.value for item in app.markdown)
    assert any("canal-historias" in item.value for item in app.text)
```

(añadir `calibration_rows` al import desde `nicheradar.flow_research_dashboard` en ese archivo.)

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_flow_research_dashboard.py tests/test_flow_research_client.py -q 2>&1 | tail -15`
Expected: FAIL (`ImportError: calibration_rows`, `title == "DossierV3"`).

- [ ] **Step 3: Implementar**

`src/nicheradar/pilots/contracts.py` línea 119:

```python
    schema_: Annotated[Literal["dossier-v1", "dossier-v2", "dossier-v3"], Field(alias="schema")]
```

`src/nicheradar/flow_research/cli.py`: importar `DossierV3` en lugar de `DossierV2` (línea 14), `help="print the dossier-v3 JSON schema"` (línea 49) y `_print(DossierV3.model_json_schema())` (línea 62).

`src/nicheradar/flow_research_dashboard.py`: tras `flow_rows` añadir

```python
BASIS = {
    "measured": "medido",
    "mapped_flow_equivalent": "flujo equivalente ya mapeado",
    "estimate": "estimación",
}


def calibration_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    regime = {step["name"]: step["human_minutes_per_video"] for step in content["production_flow"]}
    return [
        {
            "Etapa": item["step"],
            "Minutos en régimen": regime.get(item["step"]),
            "Minutos en calibración": item["minutes_per_video"],
        }
        for item in content["calibration"]["minutes_by_step"]
    ]
```

y en `render_dossier`, justo después de `st.dataframe(flow_rows(content), ...)`:

```python
    if "calibration" in content:
        calibration = content["calibration"]
        evidence = content["steady_state_evidence"]
        hours = calibration_total_hours(
            calibration["setup_hours"],
            calibration["videos"],
            sum(item["minutes_per_video"] for item in calibration["minutes_by_step"]),
        )
        st.markdown("**Calibración y régimen**")
        st.text(
            f"Calibración: {calibration['videos']} videos, {hours:g} horas en total "
            f"({calibration['setup_hours']:g} h de preparación). "
            f"Salida: {calibration['exit_criterion']['statement']}"
        )
        st.dataframe(calibration_rows(content), hide_index=True, width="stretch")
        st.text(
            f"Régimen: {BASIS[evidence['basis']]}"
            + (f" · canal de referencia {evidence['reference_channel']}"
               if evidence.get("reference_channel") else "")
            + (f" · {evidence['reference_minutes_per_video']} min en "
               f"{evidence['reference_sample_videos']} videos"
               if evidence.get("reference_minutes_per_video") is not None else "")
        )
        st.text("Formato: " + evidence["format_match"])
```

con `from nicheradar.flow_research.contracts import calibration_total_hours` en los imports del módulo. Además, en `render_dossier`, el texto `"Minutos humanos por video (suma del flujo): {minutes}"` pasa a `"Minutos humanos por video en régimen (suma del flujo): {minutes}"`; y en `flow_rows` la columna `"Minutos humanos por video"` pasa a `"Minutos humanos por video (régimen)"` (ajustar las aserciones del test que la lean: `grep -n "Minutos humanos por video" tests`).

Texto libre: se muestra con `st.text` (nunca Markdown), como el resto del módulo.

- [ ] **Step 4: Ejecutar pruebas**

Run: `uv run pytest tests/test_flow_research_dashboard.py tests/test_flow_research_client.py tests/test_pilots_api.py -q 2>&1 | tail -15` y `uv run pytest tests/test_flow_research_create.py -q -k "schema"`.
Expected: PASS (el test del skill se cubre en la Task 4).

- [ ] **Step 5: Commit**

```bash
git add src/nicheradar/pilots/contracts.py src/nicheradar/flow_research/cli.py src/nicheradar/flow_research_dashboard.py tests/test_flow_research_create.py tests/test_flow_research_client.py tests/test_flow_research_dashboard.py
git commit -m "feat: pilotos, comando schema y panel leen dossier-v3 (calibración y régimen)"
```

---

### Task 4: Skill, contrato documentado y catálogo

**Files:**
- Modify: `.claude/skills/flow-research/SKILL.md`
- Create: `docs/contracts/dossier-v3.md`
- Modify: `docs/contracts/dossier-v2.md` (nota de legado al inicio)
- Modify: `docs/flow-research.md`
- Modify: `docs/investigacion-herramientas/CATALOGO-CONSOLIDADO.md` (solo si está en la rama; si no, nota en el informe)
- Modify: `tests/test_flow_research_create.py`, `tests/test_flow_research_client.py` (agujas del skill)

**Interfaces:**
- Consumes: el contrato v3 y la compuerta de las Tasks 1-2.
- Produces: instrucciones de la skill para separar calibración y régimen y citar el canal de referencia; documento del contrato.

- [ ] **Step 1: Escribir/ajustar las pruebas del skill que fallan**

En `tests/test_flow_research_create.py`, en el test `test_the_skill_asks_for_v2_rights_and_the_automation_plan_and_forbids_overrides` (renombrar a `..._v3_...`), cambiar la aguja `"dossier-v2"` por `"dossier-v3"` y añadir `"calibration"`, `"steady_state_evidence"`, `"régimen"`. En `tests/test_flow_research_client.py` revisar el test del skill (`test_the_skill_names_every_command_and_forbids_leaking_the_token`) y cambiar cualquier aguja `dossier-v2` por `dossier-v3` (`grep -n "dossier-v2" tests/test_flow_research_*.py`).

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_flow_research_create.py tests/test_flow_research_client.py -q 2>&1 | tail -10`
Expected: FAIL (el skill aún habla de dossier-v2).

- [ ] **Step 3: Escribir la skill y los documentos**

En `.claude/skills/flow-research/SKILL.md` reemplazar cada mención de `dossier-v2` por `dossier-v3` (incluida la descripción y el paso 4) y añadir, tras la sección «Experiencia de los canales propios (Foundry de YouTube)», esta sección:

```markdown
## Tiempo humano: calibración y régimen (`dossier-v3`)

Separa dos escenarios; no los mezcles:

- **Régimen** (`production_flow[].human_minutes_per_video`): minutos humanos por video cuando el flujo ya está
  mapeado y el humano solo da instrucciones y valida. Es lo único que compara la compuerta de minutos.
- **Calibración** (`calibration`): los primeros videos, mientras se construye y ajusta el flujo. Declara
  `videos` (1 a 12), `setup_hours` (horas únicas de preparación), `minutes_by_step` (un valor por cada paso de
  `production_flow`, nunca menor que su régimen) y `exit_criterion` (`max_minutes_per_video`,
  `consecutive_videos` y un `statement` claro). **No declares `total_hours`**: se deriva.

Evidencia del régimen (`steady_state_evidence`):

1. `measured`: cronometrado en un canal propio. Cita `reference_channel`, `reference_minutes_per_video` y
   `reference_sample_videos`. Hoy el único dato es `canal-historias`: unos 20 minutos por video (10 de
   instrucción y postura + 10 de validar y programar) en los últimos 10 videos, declarado por el propietario.
2. `mapped_flow_equivalent`: un canal propio con un flujo mapeado de mismo formato e idioma. Cita
   `reference_channel` y di en `format_match` qué cambia.
3. `estimate`: nadie lo ha hecho. Entonces **no recomiendes `go`**: usa `go_with_conditions` y copia
   literalmente `exit_criterion.statement` entre `verdict.conditions`, o `no_go`.

Reglas: `verdict.conditions` es obligatorio (lista; no vacía con `go_with_conditions`). Un formato distinto al
canal de referencia (otras visuales, otro idioma) no es régimen medido: decláralo en `format_match` y baja a
`estimate`. El tiempo de máquina no cuenta como minutos humanos. No presupuestes régimen sin base.
```

Crear `docs/contracts/dossier-v3.md` con este contenido:

```markdown
# Contrato dossier-v3

Versión vigente del dossier de investigación de flujo. Reemplaza a `dossier-v2` (ver
[`dossier-v2.md`](dossier-v2.md), solo lectura de lo guardado). Los campos de v2 (derechos, plan de automatización,
presupuesto, competidores, herramientas) no cambian; v3 añade el tiempo humano en dos escenarios.

## Qué cambia respecto a v2

| Campo | Cambio |
|---|---|
| `schema_version` | `"dossier-v3"` |
| `production_flow[].human_minutes_per_video` | Significa **régimen** (flujo ya mapeado). El total se deriva (suma) y es lo que compara la compuerta `human_minutes` |
| `verdict.conditions` | Lista de condiciones (obligatoria; no vacía con `go_with_conditions`) |
| `calibration` | Objeto nuevo: `videos` (1 a 12), `setup_hours` (≥ 0), `exit_criterion` {`max_minutes_per_video`, `consecutive_videos`, `statement`}, `minutes_by_step[]` {`step`, `minutes_per_video`} |
| `steady_state_evidence` | Objeto nuevo: `basis` (`measured`, `mapped_flow_equivalent`, `estimate`), `reference_channel`, `reference_minutes_per_video`, `reference_sample_videos`, `format_match` |

## Reglas

1. `minutes_by_step` tiene un valor por cada paso de `production_flow` (sin repetir ni omitir) y ninguno es menor
   que el régimen de ese paso.
2. Horas de calibración (derivadas, no declaradas): `setup_hours + videos × Σ minutes_by_step / 60`, redondeado a
   2 decimales. Declarar `total_hours` es un campo no permitido.
3. `basis` distinto de `estimate` exige `reference_channel`; `measured` exige además `reference_minutes_per_video` y
   `reference_sample_videos`.
4. Con `basis = estimate` no se puede recomendar `go`; con `go_with_conditions`, `calibration.exit_criterion.statement`
   debe estar literalmente en `verdict.conditions`.

## Compuertas

Además de las de v2: `NR_GATE_MAX_CALIBRATION_HOURS` (40 por defecto; **supuesto inicial, no medido**) compara las horas
de calibración derivadas. Un dossier con `go` o `go_with_conditions` se rechaza (`422`, ruta `verdict.recommendation`)
si el régimen supera `NR_GATE_MAX_HUMAN_MINUTES` (60) o la calibración supera el tope, salvo `gate_override` registrado.
`no_go` siempre se acepta. Al autorizar el piloto se repiten las comprobaciones; un dossier v1 o v2 guardado se evalúa
como antes (su total cuenta como régimen y no tiene calibración).

## Evidencia de referencia

`canal-historias`: ~20 min de régimen por video (10 de instrucción y postura + 10 de validación y programación) en los
últimos 10 videos; primera semana: 2 a 3 horas por semana en errores de producción, hoy ninguna. Tiempos declarados por el
propietario, no cronometrados con reloj.
```

En `docs/contracts/dossier-v2.md`, añadir como primeras líneas bajo el título:

```markdown
> **Legado:** `dossier-v2` solo se conserva para leer dossiers guardados. Los encargos nuevos usan
> [`dossier-v3`](dossier-v3.md).
```

En `docs/flow-research.md`, reemplazar la frase que cita `dossier-v2` como vigente por `dossier-v3` (en «Qué valida la app»: `schema_version` debe ser `dossier-v3`) y enlazar el contrato nuevo.

En el catálogo (`docs/investigacion-herramientas/CATALOGO-CONSOLIDADO.md`), reemplazar el título y la tabla de «Minutos humanos por video: la cuenta que importa para la compuerta» por:

```markdown
## Minutos humanos por video: calibración y régimen

La compuerta de NicheRadar compara el **régimen** (flujo ya mapeado) con un máximo de 60 minutos por video; la
**calibración** (primeros videos) se presupuesta aparte en horas. Las cifras por etapa de abajo, tomadas de los
informes, mezclaban ambos escenarios y son supuestos de calibración, no de régimen:

| Etapa | Calibración A (min humanos) | Calibración B (min humanos) |
|---|---|---|
| 01 Guion | 20–30 | 12–20 |
| 02 Voz | 5–10 | 5–10 |
| 03 Visuales | 25–35 | 20–30 |
| 04 Edición | 2–3 | 2–3 |
| 05 Miniaturas | 5–12 | 5–12 |
| 06 Música/subtítulos | 0–3 | 0–3 |
| 07 Publicación | 5–10 | 5–10 |
| **Total (calibración)** | **62–103** | **49–88** |

**Régimen medido:** ~20 minutos por video en `canal-historias` (10 de instrucción y postura + 10 de validación y
programación; últimos 10 videos; declarado por el propietario). Es una evidencia de un canal de narración larga sin rostro
en inglés; otro formato debe tratarse como estimación hasta cronometrarlo.
```

(Esta edición del catálogo solo aplica si el archivo existe en la rama de trabajo. Si no existe, anotarlo en el informe final y no crearlo.)

- [ ] **Step 4: Ejecutar las pruebas**

Run: `uv run pytest tests/test_flow_research_create.py tests/test_flow_research_client.py -q 2>&1 | tail -10`
Expected: PASS.

- [ ] **Step 5: Validación completa y commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q 2>&1 | tail -15`
Expected: ruff y mypy sin errores; la suite completa pasa (las pruebas que necesitan Postgres de prueba se ejecutan si está disponible; si se saltan, listarlas).

```bash
git add .claude/skills/flow-research/SKILL.md docs/contracts docs/flow-research.md docs/investigacion-herramientas tests/test_flow_research_create.py tests/test_flow_research_client.py
git commit -m "docs: skill y contrato dossier-v3 con calibración y régimen"
```

---

## Fuera de este plan (necesita aprobación del propietario)

Release 034 (imágenes, digests, acción de despliegue, despliegue de API y panel). El código de este plan no cambia la base de datos.

## Self-Review

- **Cobertura del spec:** contrato v3 con `calibration`, `steady_state_evidence` y `verdict.conditions` (Task 1); compuerta de horas, configuración y comprobación en autorización (Task 2); pilotos, CLI y panel (Task 3); skill, contrato documentado y catálogo (Task 4); despliegue marcado fuera. Reglas de evidencia (`estimate`/`measured`/`mapped_flow_equivalent`) en `v3_problems`.
- **Ruling 1 (desviación del spec):** el spec pone `calibration_minutes_per_video` en cada paso; el plan lo pone en `calibration.minutes_by_step[]` para no cambiar los tipos de `production_flow`/`automation_plan` (invariancia de `list[...]` en mypy) con la misma validación (uno por paso, ≥ régimen). Costo si está mal: renombrar un campo antes del primer uso.
- **Ruling 2:** el spec dice «entre sus conditions» sin que el dossier tuviera ese campo; el plan añade `verdict.conditions` (obligatorio en v3) y exige ahí el `statement` literal.
- **Consistencia de tipos:** `calibration_total_hours(setup_hours: float, videos: int, minutes_per_video: int) -> float` se usa igual en `DossierV3.calibration_hours`, `gates.authorization_reasons` y el panel; `Gates.max_calibration_hours` es el último campo (las llamadas posicionales `Gates(70, 40, True)` existentes no se rompen); `calibration_reasons(hours, gates)` usa el id `calibration_hours`.
- **Sin placeholders:** cada paso de código incluye el código; la única nota condicional es el catálogo (archivo de otra rama) y `db` de `test_niche_gates.py` (fixture), ambas con instrucción exacta.
