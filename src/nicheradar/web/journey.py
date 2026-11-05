# src/nicheradar/web/journey.py
"""The six-step journey from candidate to pilot, shared by niches and sub-niches.

Pure and defensive: malformed input never raises, it yields the six steps with the
text of what is missing.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nicheradar.web.format import parse_utc, zone
from nicheradar.web.pilots_view import STATUS_CHIP

NAMES = (
    "Candidato",
    "Decisión",
    "Listo para investigar",
    "Investigación de flujo",
    "Informe",
    "Piloto",
)
LANGUAGE_NAME = {
    "en": "inglés",
    "es": "español",
    "pt": "portugués",
    "ru": "ruso",
    "de": "alemán",
    "fr": "francés",
}
OTHER_LANGUAGE = "su idioma"
DONE, NOW, PENDING = "done", "now", "pending"


@dataclass(frozen=True)
class Step:
    state: str  # "done" | "now" | "pending"
    name: str
    detail: str


@dataclass(frozen=True)
class _Draft:
    done: bool
    done_text: str
    now_text: str
    pending_text: str
    passive: bool = False  # never the current step: it is measured or computed, not acted on


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _score(block: object) -> bool:
    value = _dict(block).get("value")
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _language(value: object) -> str:
    return LANGUAGE_NAME.get(value, OTHER_LANGUAGE) if isinstance(value, str) else OTHER_LANGUAGE


def _local_date(value: object, tz: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        moment: datetime = parse_utc(value)
        return moment.astimezone(zone(tz)).strftime("%d/%m/%Y")
    except (ValueError, OverflowError):
        return None


def _tail(research: object, pilot: object, start_text: str) -> list[_Draft]:
    """Steps 4 to 6: research, report and pilot."""
    status = _dict(research).get("status")
    ready = status == "listo"
    if ready:
        now_text = "Hecha por Claude Code en " + _language(_dict(research).get("language"))
    elif status == "en_curso":
        now_text = "En curso: Claude Code la está haciendo"
    elif status == "pendiente":
        now_text = "Pendiente: esperando a Claude Code"
    elif status == "rechazado":
        now_text = "Rechazada: vuelve a iniciarla"
    else:
        now_text = start_text
    flow = _Draft(ready, now_text, now_text, "Se inicia desde el detalle")
    report = _Draft(
        ready,
        "Dossier listo",
        "Dossier con veredicto, tiempo y presupuesto",
        "Dossier con veredicto, tiempo y presupuesto",
    )
    if isinstance(pilot, dict):
        raw = pilot.get("status")
        label = STATUS_CHIP.get(raw, ("",))[0].lower() if isinstance(raw, str) else ""
        launch = "Piloto " + (label or "abierto")
    else:
        launch = "Decide si lo lanzas"
    return [flow, report, _Draft(False, launch, launch, "Autorizas y se produce")]


def _build(drafts: list[_Draft]) -> list[Step]:
    steps: list[Step] = []
    current_found = False
    for name, draft in zip(NAMES, drafts, strict=True):
        if draft.done:
            steps.append(Step(DONE, name, draft.done_text))
        elif draft.passive:
            current_found = True
            steps.append(Step(PENDING, name, draft.pending_text))
        elif not current_found:
            current_found = True
            steps.append(Step(NOW, name, draft.now_text))
        else:
            steps.append(Step(PENDING, name, draft.pending_text))
    if not current_found:  # unreachable while the pilot step is never done; kept for safety
        last = steps[-1]
        steps[-1] = Step(NOW, last.name, last.detail)
    return steps


def niche_journey(niche: object, research: object, pilot: object) -> list[Step]:
    """`niche`: backlog entry or `detail["niche"]`; `research`: latest order; `pilot`: open one."""
    try:
        data = _dict(niche)
        decision = _dict(data.get("decision")).get("decision")
        if decision == "descartado":
            decide = _Draft(False, "", "Descartado: se oculta de la lista", "")
        elif decision == "tentativo":
            decide = _Draft(True, "Marcado «Tentativo»", "", "")
        else:
            decide = _Draft(False, "", "Marca «Tentativo» para poder investigarlo", "")
        scored = _score(data.get("opportunity")) and _score(data.get("automation"))
        ready = _Draft(
            scored,
            "Tiene puntajes de Opportunity y de automatización",
            "Necesita puntajes de Opportunity y de automatización (al menos 3 fichas con ingreso)",
            "Necesita puntajes de Opportunity y de automatización (al menos 3 fichas con ingreso)",
            passive=True,
        )
        candidate = _Draft(True, "Viene del scraper de mercado", "", "")
        return _build(
            [candidate, decide, ready, *_tail(research, pilot, "Se inicia desde el detalle")]
        )
    except Exception:  # noqa: BLE001 - a journey must never break a page
        return _build(
            [
                _Draft(i == 0, "Viene del scraper de mercado", "Faltan datos", "Faltan datos")
                for i in range(6)
            ]
        )


def subniche_journey(item: object, pilot: object, tz: str) -> list[Step]:
    """`item` is one element of `GET /subniches`."""
    try:
        data = _dict(item)
        status = data.get("status") if isinstance(data.get("status"), str) else "proposed"
        if status in ("active", "paused"):
            decide = _Draft(True, "Aprobada: activa" if status == "active" else "Pausada", "", "")
        elif status == "archived":
            decide = _Draft(False, "", "Archivada: se descarta", "")
        else:
            decide = _Draft(False, "", "Falta aprobarla", "")
        measured = _local_date(_dict(data.get("measurement")).get("measured_at"), tz)
        if status == "active" and measured is not None:
            ready = _Draft(True, f"Medido el {measured}", "", "")
        else:
            text = (
                "Reanúdala para medirla"
                if status == "paused"
                else "Se mide sola, a más tardar en 3 días"
            )
            ready = _Draft(False, "", text, text, passive=True)
        candidate = _Draft(True, "Propuesta de la hipótesis", "", "")
        return _build(
            [
                candidate,
                decide,
                ready,
                *_tail(data.get("research"), pilot, "Falta iniciarla (abajo)"),
            ]
        )
    except Exception:  # noqa: BLE001 - a journey must never break a page
        return _build(
            [
                _Draft(i == 0, "Propuesta de la hipótesis", "Faltan datos", "Faltan datos")
                for i in range(6)
            ]
        )
