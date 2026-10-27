"""Tabla de traducción de `source_state` (estado interno del canal) a `stage` (etapa gruesa).

La mantiene NicheRadar, una tabla por canal (decisión 7 de `docs/ecosistema-youtube.md`): el canal
manda su estado tal cual y no conoce este vocabulario. Un estado ausente de la tabla, o un
canal sin tabla, se traduce a `unknown`: el reporte se acepta y el piloto queda para revisión.
"""

from __future__ import annotations

# `PUBLICADO` no figura aquí: su etapa depende de la visibilidad (ver `translate`).
_CANAL_HISTORIAS: dict[str, str] = {
    **dict.fromkeys(
        (
            "IDEA_CRUDA",
            "IDEA_VALIDADA",
            "GUION_BORRADOR",
            "GUION_APROBADO",
            "GUION_FINAL",
            "ASSETS_LISTOS",
            "RENDER_COMPLETO",
            "QA_APROBADO",
            "EMPAQUETADO",
        ),
        "in_production",
    ),
    "VEREDICTOS_PENDIENTES": "awaiting_human",
    "PROGRAMADO": "uploaded",
    "EN_MEDICION": "measuring",
    "KILL": "killed",
    "BLOQUEADO_POLITICA": "blocked",
    "FALLO_QA": "blocked",
}

# `canal-speedrun-ledger` copia la máquina de estados de `canal-historias` (receta del foundry),
# así que su tabla es la misma. Si el canal cambia su vocabulario, se separa aquí con una prueba.
TABLES: dict[str, dict[str, str]] = {
    "canal-historias": _CANAL_HISTORIAS,
    "canal-speedrun-ledger": _CANAL_HISTORIAS,
}
PUBLISHED_STATE = {"canal-historias": "PUBLICADO", "canal-speedrun-ledger": "PUBLICADO"}


def translate(channel_id: str, source_state: str, visibility: str) -> str:
    table = TABLES.get(channel_id)
    if table is None:
        return "unknown"
    if source_state == PUBLISHED_STATE.get(channel_id):
        # Con visibilidad desconocida no se adivina: queda `unknown` y se revisa a mano.
        return {"public": "published", "private": "uploaded"}.get(visibility, "unknown")
    return table.get(source_state, "unknown")
