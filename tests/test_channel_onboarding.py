"""Onboarding de los canales que copian el pipeline de `canal-historias` y su tabla de estados."""

import pytest

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
# Canales cuyo pipeline es copia de `canal-historias` (receta faceless-storytelling).
COPIED_CHANNELS = ("canal-speedrun-ledger", "canal-testedoftime", "canal-prehistoric-creatures")


@pytest.mark.parametrize("channel", COPIED_CHANNELS)
def test_every_state_of_the_copied_state_machine_has_a_stage(channel: str) -> None:
    for state in CHANNEL_STATE_MACHINE:
        for visibility in ("public", "private"):
            assert translate(channel, state, visibility) != "unknown", state
            assert translate(channel, state, visibility) == translate(
                "canal-historias", state, visibility
            )


@pytest.mark.parametrize("channel", COPIED_CHANNELS)
def test_the_published_state_depends_on_visibility_and_is_never_guessed(channel: str) -> None:
    assert translate(channel, "PUBLICADO", "public") == "published"
    assert translate(channel, "PUBLICADO", "private") == "uploaded"
    assert translate(channel, "PUBLICADO", "unknown") == "unknown"
    assert translate(channel, "ESTADO_NUEVO", "public") == "unknown"


@pytest.mark.parametrize("channel", COPIED_CHANNELS)
def test_the_channel_table_and_its_published_state_are_registered_together(channel: str) -> None:
    assert channel in TABLES and PUBLISHED_STATE[channel] == "PUBLICADO"
    assert set(TABLES[channel]) | {PUBLISHED_STATE[channel]} == set(CHANNEL_STATE_MACHINE)
