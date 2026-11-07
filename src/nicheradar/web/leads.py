# src/nicheradar/web/leads.py
"""Vista de una lectura de tweet o imagen. Todo texto de la API se muestra como dato.

Funciones puras: sin E/S ni proveedores. Los textos de error son los de la web, elegidos por
`code`; el `message` que envía la API nunca se muestra.
"""

import re
import unicodedata
from typing import Any

from nicheradar.web.deps import UNSAFE_CATEGORIES
from nicheradar.web.format import compact
from nicheradar.web.proposals import PROPOSAL_ID as UUID_RE
from nicheradar.web.proposals import valid_proposal_id

GENERIC = "No se pudo leer."
VISION = "El modelo con visión no está disponible: solo se leyeron los enlaces del texto."
TEXTS: dict[str, str] = {
    "reading_disabled": "La lectura de tweets e imágenes no está activa en el servidor.",
    "invalid_tweet_url": "Ese enlace no es un tweet de X.",
    "daily_limit": "Se llegó al tope diario de lecturas de tweets.",
    "invalid_image": "La imagen no es un PNG, JPEG o WEBP válido.",
    "image_too_large": "La imagen pasa de 5 MB.",
    "read_closed": "La lectura ya está cerrada.",
    "not_ready": "La lectura todavía no terminó.",
    "invalid_candidates": "Esos canales no pertenecen a esta lectura o no se pueden usar así.",
    "tweet_unavailable": (
        "No se pudo leer el tweet: puede estar borrado, ser privado o de una cuenta protegida. "
        "Comparte la imagen."
    ),
    "vision_not_configured": "No se pudo leer la imagen: el modelo de visión no está configurado.",
    "reader_failed": "El servicio de lectura de tweets no respondió. Comparte la imagen.",
    "reader_not_configured": "La lectura con la API de X no está configurada en el servidor.",
    "reader_unauthorized": (
        "La API de X rechazó la credencial del servidor: el token no es válido o no tiene permiso."
    ),
    "reader_rate_limited": (
        "La API de X pidió esperar por demasiadas lecturas; vuelve a intentarlo más tarde."
    ),
    "reader_credits_depleted": "Se agotaron los créditos de la API de X en el servidor.",
    "reader_blocked": "El servicio de lectura rechazó la solicitud desde el servidor.",
    "expired": "La lectura caducó sin atenderse; vuelve a intentarla.",
    "cancelled": "La lectura se canceló; vuelve a intentarlo.",
    "abandoned": "La lectura se interrumpió; vuelve a intentarlo.",
    "llm_input_too_large": (
        "El texto o las imágenes son demasiado grandes para el modelo; "
        "se usaron solo los enlaces del texto."
    ),
    "youtube_not_configured": "YouTube no está configurado en el servidor.",
    "youtube_quota_exhausted": (
        "La cuota de búsqueda de YouTube de hoy está agotada; "
        "inténtalo mañana o usa una consulta manual."
    ),
    "youtube_unreachable": "No se pudo consultar YouTube; vuelve a intentarlo.",
    "llm_rejected": (
        "El modelo de lenguaje rechazó la solicitud. "
        "Revisa la configuración del modelo y el saldo de la cuenta de Anthropic."
    ),
    "llm_auth": (
        "El modelo de lenguaje rechazó la credencial del servidor. Revisa la clave de Anthropic."
    ),
    "llm_permission": (
        "La cuenta del modelo de lenguaje no tiene permiso o saldo para esta solicitud. "
        "Revisa la cuenta de Anthropic."
    ),
    "llm_rate_limited": (
        "El modelo de lenguaje alcanzó su límite de uso; vuelve a intentarlo más tarde."
    ),
    **dict.fromkeys(
        (
            "llm_disabled",
            "synthetic_mode",
            "configuration_missing",
            "llm_tariff_not_current",
            "policy_not_enabled",
            "llm_failed",
            "invalid_response",
            "incomplete_response",
        ),
        VISION,
    ),
}
STATES = {"queued": "en_cola", "running": "leyendo", "ready": "lista", "failed": "fallida"}
STAGES = ("text", "images", "mentions")
STEP_LABELS = ("Texto del tweet", "Imagen del tweet", "Canales mencionados")
FOUND = {"text": "en el texto", "image": "en la imagen", "both": "en el texto y la imagen"}
RESOLUTION = {
    "resolved": "resuelto en YouTube",
    "name_only": "buscar por nombre (100 u.)",
    "name_queued": "buscando por nombre",
    "searching": "buscando por nombre",
    "ambiguous": "ambiguo: revisa el canal",
    "not_found": "no encontrado",
}
SEARCHING = ("name_queued", "searching")
PROPOSAL = {
    "queued": "En cola",
    "running": "En preparación",
    "succeeded": "Lista",
    "ready": "Lista",
    "failed": "Fallida",
}
MAX_CANDIDATES = 10
LABEL_MAX = 120
TEXT_MAX = 1000
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}", re.ASCII)
AUTHOR = re.compile(r"[A-Za-z0-9_]{1,15}", re.ASCII)
TWEET_URL = re.compile(r"https://x\.com/(?:[A-Za-z0-9_]{1,15}|i)/status/[0-9]{1,20}", re.ASCII)


def error_text(code: str | None) -> str:
    return TEXTS.get(code, GENERIC) if isinstance(code, str) else GENERIC


def count_param(raw: object) -> int | None:
    """A 0..10 count from a query string; anything else is None (nothing is shown)."""
    if isinstance(raw, str) and raw.isascii() and raw.isdigit() and len(raw) <= 2:
        return int(raw) if int(raw) <= MAX_CANDIDATES else None
    return None


def result_text(created: object, skipped: object) -> str | None:
    made, left = count_param(created), count_param(skipped)
    if made is None or left is None:
        return None
    done = "Se creó 1 propuesta" if made == 1 else f"Se crearon {made} propuestas"
    if left == 0:
        return done + "."
    verb = "omitió" if left == 1 else "omitieron"
    return f"{done}; {left} se {verb} (duplicadas, sin cupo o sin resolver)."


def parse_candidate_ids(values: list[str]) -> list[str] | None:
    """1 a 10 UUID distintos; cualquier otra cosa es None y nada viaja a la API."""
    unique = list(dict.fromkeys(values))
    if not 1 <= len(unique) <= MAX_CANDIDATES or not all(UUID_RE.fullmatch(v) for v in unique):
        return None
    return unique


def _plain(value: object, limit: int, *, keep_lines: bool = False) -> str:
    """Texto de un tercero: sin control, formato (RLO), NUL ni separadores raros; recortado."""
    if not isinstance(value, str):
        return ""
    out: list[str] = []
    for char in value[: limit * 2]:
        if char == "\n" and keep_lines:
            out.append(char)
        elif char.isspace():
            out.append(" ")
        elif unicodedata.category(char) not in UNSAFE_CATEGORIES:
            out.append(char)
    return re.sub(r" {2,}", " ", "".join(out)).strip()[:limit]


def _code(block: object) -> str | None:
    code = block.get("code") if isinstance(block, dict) else None
    return code if isinstance(code, str) else None


def _steps(status: str, stage: object) -> list[tuple[str, str]]:
    if status == "ready":
        return [(label, "hecho") for label in STEP_LABELS]
    current = STAGES.index(stage) if stage in STAGES else (2 if stage == "resolving" else -1)
    return [
        (label, "hecho" if i < current else "en_curso" if i == current else "pendiente")
        for i, label in enumerate(STEP_LABELS)
    ]


def _candidate(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not valid_proposal_id(raw.get("id")):
        return None
    resolution = raw.get("resolution")
    if resolution not in RESOLUTION:
        resolution = "not_found"
    raw_channel = raw.get("channel")
    channel: dict[str, Any] | None = raw_channel if isinstance(raw_channel, dict) else None
    detail = (
        "Solo hay un nombre, sin @handle"
        if resolution == "name_only"
        else "Buscando por nombre…"
        if resolution in SEARCHING
        else "No hay un canal con ese nombre"
    )
    channel_url = None
    if channel is not None:
        subs = channel.get("subscribers")
        shown = compact(subs) if isinstance(subs, int) and not isinstance(subs, bool) else "—"
        detail = f"{_plain(channel.get('title'), LABEL_MAX) or '—'} · {shown} suscriptores"
        channel_id = channel.get("id")
        if isinstance(channel_id, str) and CHANNEL_ID.fullmatch(channel_id):
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
    raw_proposal = raw.get("proposal")
    proposal: dict[str, Any] | None = raw_proposal if isinstance(raw_proposal, dict) else None
    proposal_id = proposal.get("id") if proposal else None
    usable = channel is not None and proposal is None
    return {
        "id": raw["id"],
        "label": _plain(raw.get("value"), LABEL_MAX) or "—",
        "detail": detail,
        "chips": [FOUND.get(str(raw.get("found_in")), "en el texto"), RESOLUTION[resolution]],
        "checkable": resolution in ("resolved", "ambiguous") and usable,
        "checked": resolution == "resolved" and usable,
        "can_search": resolution == "name_only" and proposal is None,
        "searching": resolution in SEARCHING,
        "resolution": resolution,
        "channel_url": channel_url,
        "proposal_state": PROPOSAL.get(str(proposal.get("status")), "Fallida")
        if proposal
        else None,
        "proposal_href": f"/subnichos/propuestas/{proposal_id}"
        if valid_proposal_id(proposal_id)
        else None,
    }


def read_view(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status"))
    raw_list = item.get("candidates")
    raw: list[Any] = raw_list if isinstance(raw_list, list) else []
    candidates = [c for c in (_candidate(r) for r in raw[:MAX_CANDIDATES]) if c is not None]
    raw_tweet = item.get("tweet")
    url = raw_tweet.get("url") if isinstance(raw_tweet, dict) else None
    tweet_url = url if isinstance(url, str) and TWEET_URL.fullmatch(url) else None
    text = _plain(item.get("untrusted_text"), TEXT_MAX, keep_lines=False)
    state = STATES.get(status, "fallida")
    return {
        "id": item.get("id"),
        "is_image": item.get("kind") == "image",
        "state": state,
        "closed": item.get("closed") is True,
        "steps": _steps(status, item.get("stage")),
        "text": text or None,
        "tweet_url": tweet_url,
        "warning": error_text(_code(item.get("warning"))) if item.get("warning") else None,
        "error": error_text(_code(item.get("error"))) if state == "fallida" else None,
        "candidates": candidates,
        "selected": sum(1 for c in candidates if c["checked"]),
        "searching": any(c["searching"] for c in candidates),
        "proposals": [
            {"label": c["label"], "state": c["proposal_state"], "href": c["proposal_href"]}
            for c in candidates
            if c["proposal_state"]
        ],
    }
