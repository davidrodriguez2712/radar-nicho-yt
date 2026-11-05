from pathlib import Path

from nicheradar.web.deps import make_templates
from nicheradar.web.journey import Step, niche_journey, subniche_journey


def states(steps: list[Step]) -> list[str]:
    return [s.state for s in steps]


def names(steps: list[Step]) -> list[str]:
    return [s.name for s in steps]


NAMES = [
    "Candidato",
    "Decisión",
    "Listo para investigar",
    "Investigación de flujo",
    "Informe",
    "Piloto",
]


def niche(decision: str = "tentativo", opp: float | None = 72, auto: float | None = 64) -> dict:
    return {
        "decision": {"decision": decision},
        "opportunity": {"value": opp},
        "automation": {"value": auto},
    }


def test_a_new_niche_stops_at_the_decision() -> None:
    steps = niche_journey(niche("nuevo"), None, None)
    assert names(steps) == NAMES
    assert states(steps) == ["done", "now", "done", "pending", "pending", "pending"]
    assert "Tentativo" in steps[1].detail


def test_a_tentative_niche_with_scores_waits_for_the_research() -> None:
    steps = niche_journey(niche(), None, None)
    assert states(steps) == ["done", "done", "done", "now", "pending", "pending"]


def test_the_research_in_progress_and_rejected_texts() -> None:
    assert (
        "En curso"
        in niche_journey(niche(), {"status": "en_curso", "language": "en"}, None)[3].detail
    )
    assert (
        "Pendiente"
        in niche_journey(niche(), {"status": "pendiente", "language": "en"}, None)[3].detail
    )
    assert (
        "Rechazada"
        in niche_journey(niche(), {"status": "rechazado", "language": "en"}, None)[3].detail
    )


def test_a_ready_dossier_without_pilot_points_at_the_pilot() -> None:
    steps = niche_journey(niche(), {"status": "listo", "language": "en"}, None)
    assert states(steps) == ["done", "done", "done", "done", "done", "now"]
    assert steps[3].detail == "Hecha por Claude Code en inglés"
    assert steps[5].detail == "Decide si lo lanzas"


def test_an_open_pilot_is_the_current_step() -> None:
    steps = niche_journey(
        niche(), {"status": "listo", "language": "en"}, {"status": "en_ejecucion"}
    )
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


def sub(
    status: str = "active",
    measured: str | None = "2026-10-31T12:00:00+00:00",
    research: dict | None = None,
) -> dict:
    return {
        "status": status,
        "measurement": {"measured_at": measured} if measured else None,
        "research": research,
    }


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


MACRO = "{% from 'components.html' import journey %}{{ journey(steps) }}"


def render(steps: list[Step]) -> str:
    return make_templates().env.from_string(MACRO).render(steps=steps)


def test_the_macro_paints_the_card_with_a_row_and_mark_per_step() -> None:
    html = render(niche_journey(niche(), {"status": "listo", "language": "en"}, None))
    assert "Recorrido hasta el piloto" in html
    assert html.count("journey__row") == 6
    assert html.count("✓") == 5 and html.count("●") == 1 and "○" not in html
    assert "journey__mark--done" in html and "journey__mark--now" in html


def test_the_macro_marks_pending_steps_and_escapes_hostile_detail() -> None:
    hostile = [Step("pending", "Paso", "<script>alert(1)</script>")]
    html = render(hostile)
    assert "○" in html and "<script>" not in html and "&lt;script&gt;" in html


def test_the_macro_never_uses_safe() -> None:
    text = Path("src/nicheradar/web/templates/components.html").read_text()
    assert "|safe" not in text.replace(" ", "")
