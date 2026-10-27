"""Onboarding de `canal-speedrun-ledger`: su tabla de estados copia la de `canal-historias`."""

from nicheradar.pilots.translation import PUBLISHED_STATE, TABLES, translate

# Estados reales de `canal-historias/pipeline/estados.py` (la máquina que copia el canal 2).
CHANNEL_STATE_MACHINE = (
    "IDEA_CRUDA",
    "IDEA_VALIDADA",
    "GUION_BORRADOR",
    "GUION_APROBADO",
    "VEREDICTOS_PENDIENTES",
    "GUION_FINAL",
    "ASSETS_LISTOS",
    "RENDER_COMPLETO",
    "QA_APROBADO",
    "EMPAQUETADO",
    "PROGRAMADO",
    "PUBLICADO",
    "EN_MEDICION",
    "KILL",
    "BLOQUEADO_POLITICA",
    "FALLO_QA",
)
CHANNEL = "canal-speedrun-ledger"


def test_every_state_of_the_copied_state_machine_has_a_stage() -> None:
    for state in CHANNEL_STATE_MACHINE:
        for visibility in ("public", "private"):
            assert translate(CHANNEL, state, visibility) != "unknown", state
            assert translate(CHANNEL, state, visibility) == translate(
                "canal-historias", state, visibility
            )


def test_the_published_state_depends_on_visibility_and_is_never_guessed() -> None:
    assert translate(CHANNEL, "PUBLICADO", "public") == "published"
    assert translate(CHANNEL, "PUBLICADO", "private") == "uploaded"
    assert translate(CHANNEL, "PUBLICADO", "unknown") == "unknown"
    assert translate(CHANNEL, "ESTADO_NUEVO", "public") == "unknown"


def test_the_channel_table_and_its_published_state_are_registered_together() -> None:
    assert CHANNEL in TABLES and PUBLISHED_STATE[CHANNEL] == "PUBLICADO"
    assert set(TABLES[CHANNEL]) | {PUBLISHED_STATE[CHANNEL]} == set(CHANNEL_STATE_MACHINE)
