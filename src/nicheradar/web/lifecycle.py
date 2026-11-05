# src/nicheradar/web/lifecycle.py
"""Rules and view models of M28 and the lifecycle buttons of the card. Pure: no I/O.

Every text shown comes from fixed dictionaries of the web; what the API says in `message` is
data and is never displayed.
"""

import re
from typing import Any

SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,59}", re.ASCII)
# POST action (Spanish path) -> (API endpoint, notice key)
ACTIONS = {
    "aprobar": ("approve", "aprobado"),
    "pausar": ("pause", "pausado"),
    "reanudar": ("resume", "reanudado"),
    "archivar": ("archive", "archivado"),
}
NOT_PROPOSED = "Esta hipótesis ya no está propuesta, así que no se puede aprobar."
ALREADY_ARCHIVED = "Esta hipótesis ya está archivada."
CONFIRM_NEEDED = "Marca la casilla para confirmar."
AVISOS: dict[str, tuple[str, str]] = {
    "aprobado": (
        "Hipótesis aprobada. Aprobar no mide al instante: la primera medición llega en la "
        "próxima ronda del radar.",
        "green",
    ),
    "pausado": ("Hipótesis pausada: deja de medirse.", "green"),
    "reanudado": ("Hipótesis reanudada: vuelve a medirse.", "green"),
    "archivado": ("Hipótesis archivada.", "green"),
    "transicion_invalida": ("Esa hipótesis no puede pasar a ese estado.", "amber"),
    "transicion_fallida": (
        "No se pudo cambiar el estado. Revisa la API e inténtalo de nuevo.",
        "rose",
    ),
}


def valid_slug(value: object) -> bool:
    return isinstance(value, str) and SLUG.fullmatch(value) is not None


def _count(data: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TypeError(f"{key} is not a valid count")
    return int(value)


def approval_view(data: object, label: str | None, slug: str) -> dict[str, Any]:
    """The M28 numbers. A payload that does not fit raises (the route turns it into a 503)."""
    if not isinstance(data, dict) or not isinstance(data["status"], str):
        raise TypeError("approval payload")
    if not isinstance(data["fits"], bool):
        raise TypeError("fits is not a boolean")
    needed = _count(data, "search_units_needed")
    cap = _count(data, "daily_cap")
    cadence = _count(data, "cadence_days", minimum=1)
    # The figures rule over the flag: whoever reads them must not see a contradiction.
    fits = needed <= cap
    return {
        "label": label or slug,
        "proposed": data["status"] == "proposed",
        "queries": _count(data, "queries"),
        "pages": _count(data, "pages", minimum=1),
        "needed": needed,
        "cap": cap,
        "fits": fits,
        "cadence_days": cadence,
        "post_href": f"/subnichos/{slug}/aprobar",
        "back_href": f"/subnichos/{slug}",
    }


def lifecycle_actions(status: object, slug: object) -> dict[str, Any] | None:
    """The valid buttons of the card for this state, or None when there is none."""
    if not valid_slug(slug) or not isinstance(status, str):
        return None
    base = f"/subnichos/{slug}"
    return {
        "approve_href": f"{base}/aprobar" if status == "proposed" else None,
        "pause_href": f"{base}/pausar" if status == "active" else None,
        "resume_href": f"{base}/reanudar" if status == "paused" else None,
        "archive_href": f"{base}/archivar" if status in ("proposed", "active", "paused") else None,
    }
