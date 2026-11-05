# src/nicheradar/web/routes_share.py
"""M29/M30: a link shared from Android. Read-only: it classifies and offers «Proponer»."""

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.proposals import new_nonce
from nicheradar.web.security import Session
from nicheradar.web.share import Classified, classify, extract_link

router = APIRouter()
KIND_LABELS = {
    "channel": "Canal de YouTube",
    "video": "Video de YouTube",
    "tweet": "Tweet de X",
    "unknown": "Enlace no reconocido",
    "none": "Sin enlace",
}


def share_context(
    found: Classified, *, nonce: str | None = None, error: str | None = None
) -> dict[str, Any]:
    """The context of `compartir.html`; `nonce` is reused after a transient failure only."""
    kind = found["kind"]
    shown = found["propose"] or found["link"]
    propose = (
        f"/subnichos/proponer?q={quote(found['propose'], safe='')}" if found["propose"] else None
    )
    return {
        "active_tab": "nichos",
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "link": shown,
        "propose_href": propose,
        "nonce": nonce or new_nonce(),
        "error": error,
    }


@router.get("/compartir")
@shape_guard
def shared(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    title: str = "",
    text: str = "",
    url: str = "",
) -> Response:
    found = classify(extract_link(title, text, url))
    return render(request, "compartir.html", share_context(found), session=session)
