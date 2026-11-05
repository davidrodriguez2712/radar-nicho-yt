# src/nicheradar/web/routes_share.py
"""M29/M30: a link shared from Android. Read-only: it classifies and offers «Proponer»."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.security import Session
from nicheradar.web.share import classify, extract_link

router = APIRouter()
KIND_LABELS = {
    "channel": "Canal de YouTube",
    "video": "Video de YouTube",
    "tweet": "Tweet de X",
    "unknown": "Enlace no reconocido",
    "none": "Sin enlace",
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
    kind = found["kind"]
    propose = (
        f"/subnichos/proponer?q={quote(found['link'], safe='')}"
        if kind in ("channel", "video")
        else None
    )
    return render(
        request,
        "compartir.html",
        {
            "active_tab": "nichos",
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "link": found["link"],
            "propose_href": propose,
        },
        session=session,
    )
