# src/nicheradar/web/proposals.py
"""View models and form rules for «Proponer subnicho». Pure: no I/O, no provider imports.

Every error text comes from a fixed dictionary of the web, chosen by `code`; whatever message
the API, YouTube or the model sends is data and is never shown.
"""

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from nicheradar.web.client import CODE_MESSAGES
from nicheradar.web.format import ago
from nicheradar.web.security import Session, SessionSigner

DASH = "—"
GENERIC_ERROR = "No se pudo preparar la propuesta."
ERROR_TEXTS: dict[str, str] = {**CODE_MESSAGES, "not_found": "No se encontró ese video o canal."}
INPUT_MIN, INPUT_MAX = 3, 500
LABEL_MIN, LABEL_MAX = 3, 120
PARENT_MAX = 60
LIST_MAX = 20
TEXT_MAX = 500
FAMILY = re.compile(r"[a-z][a-z0-9_]{1,39}")
STATE = {"queued": "en_cola", "running": "preparando", "succeeded": "lista", "failed": "fallida"}
KIND_LABEL = {"query": "Consulta", "video": "Video", "channel": "Canal"}


NONCE = re.compile(r"[0-9a-f]{32}")
PROPOSAL_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,59}", re.ASCII)
RESERVED_SLUGS = ("proponer",)  # `/subnichos/proponer` is a screen, not a sub-niche card
HYPOTHESIS_STATUS = {"active": "Activa", "paused": "Pausada", "archived": "Archivada"}
MAX_POLLS = 120  # 120 polls of 5 s: about 10 minutes
COUNT_DIGITS = 6


def poll_count(raw: object) -> int:
    """The `n` of a polling URL: ASCII digits only; anything else is 0, a huge one is spent."""
    if not isinstance(raw, str) or not raw:
        return 0
    if not (raw.isascii() and raw.isdigit()):
        return 0
    return int(raw) if len(raw) <= COUNT_DIGITS else MAX_POLLS


def reserved_label(label: str) -> bool:
    """Same normalization as the API's `slugify`: the label becomes the slug of the card."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60] in RESERVED_SLUGS


FORM_ERRORS = {
    "input_invalid": "Escribe entre 3 y 500 caracteres.",
    "manual_invalid": (
        "Revisa la etiqueta (3 a 120 caracteres), la familia (minúsculas, números y guion bajo, "
        "2 a 40) y el nicho padre (hasta 60)."
    ),
    "nonce_invalid": "La solicitud no es válida. Vuelve a pulsar «Proponer».",
}


def new_nonce() -> str:
    return secrets.token_hex(16)


def valid_proposal_id(value: object) -> bool:
    """A UUID as the API prints it: lowercase hex, ASCII only (`\\d` would accept other digits)."""
    return isinstance(value, str) and PROPOSAL_ID.fullmatch(value) is not None


def valid_nonce(nonce: object) -> bool:
    return isinstance(nonce, str) and NONCE.fullmatch(nonce) is not None


def idempotency_key(
    signer: SessionSigner, session: Session, nonce: str, body: dict[str, Any]
) -> str:
    """Same session, nonce and content, same key: a double tap, a reload or a retry after a
    transient failure never queues twice; corrected content is another request."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return "nr-" + signer.derive("idem", f"{signer.csrf(session)}:{nonce}:{digest}")[:40]


def _clean(value: str) -> bool:
    """The API (and the database) refuse NUL and lone surrogates."""
    return not any(char == "\x00" or "\ud800" <= char <= "\udfff" for char in value)


def parse_form(
    raw_input: str, modo_manual: bool, label: str, family: str, parent: str
) -> tuple[dict[str, Any], str | None]:
    """`(body, error_key)`. On error the body is empty; the key is one of the fixed ones."""
    text = raw_input.strip()
    if not INPUT_MIN <= len(text) <= INPUT_MAX or not _clean(text):
        return {}, "input_invalid"
    body: dict[str, Any] = {"input": text}
    if not modo_manual:
        return body, None
    label, family, parent = label.strip(), family.strip(), parent.strip()
    if (
        not LABEL_MIN <= len(label) <= LABEL_MAX
        or FAMILY.fullmatch(family) is None
        or len(parent) > PARENT_MAX
        or reserved_label(label)
        or not _clean(label)
        or not _clean(parent)
    ):
        return {}, "manual_invalid"
    body["manual"] = {"label": label, "family": family, "parent": parent or None}
    return body, None


def error_text(code: str | None) -> str:
    if not isinstance(code, str):
        return GENERIC_ERROR
    return ERROR_TEXTS.get("duplicate" if code.startswith("duplicate") else code, GENERIC_ERROR)


def _text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value[:TEXT_MAX]
    return DASH


def _all_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry[:TEXT_MAX] for entry in value if isinstance(entry, str) and entry]


def _texts(value: object) -> list[str]:
    return _all_texts(value)[:LIST_MAX]


def _hypothesis(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    parent = value.get("parent_niche")
    raw_slug = value.get("slug")
    slug_ok = isinstance(raw_slug, str) and SLUG.fullmatch(raw_slug) is not None
    status = value.get("status")
    return {
        "proposed": status == "proposed",
        "status_label": HYPOTHESIS_STATUS.get(status, DASH) if isinstance(status, str) else DASH,
        "slug": _text(raw_slug),
        "approve_href": f"/subnichos/{raw_slug}/aprobar"
        if slug_ok and status == "proposed"
        else None,
        "label": _text(value.get("label")),
        "family": _text(value.get("family")),
        "parent_niche": _text(parent) if isinstance(parent, str) and parent else None,
        "queries": _texts(value.get("queries")),
        "seed_channels": _texts(value.get("seed_channels")),
        "clipped": len(_all_texts(value.get("queries"))) > LIST_MAX
        or len(_all_texts(value.get("seed_channels"))) > LIST_MAX,
    }


def proposal_view(item: object, now: datetime | None = None) -> dict[str, Any]:
    """One queue entry for the screen; a malformed item degrades to `fallida` and «—»."""
    data = item if isinstance(item, dict) else {}
    status = data.get("status")
    kind = data.get("kind")
    error = data.get("error")
    state = STATE.get(status, "fallida") if isinstance(status, str) else "fallida"
    return {
        "state": state,
        "kind_label": KIND_LABEL.get(kind, DASH) if isinstance(kind, str) else DASH,
        "input": _text(data.get("input")),
        "error": error_text(error.get("code") if isinstance(error, dict) else "unknown")
        if error is not None
        else None,
        "hypothesis": _hypothesis(data.get("hypothesis")),
        "finished_ago": ago(data.get("finished_at"), now or datetime.now(UTC)),
    }
