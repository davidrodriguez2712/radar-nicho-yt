# src/nicheradar/web/routes_more.py
"""M18 Más: the menu behind the last bottom-nav tab."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.security import Session

router = APIRouter()


@router.get("/mas")
@shape_guard
def more(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
) -> Response:
    return render(request, "mas.html", {"active_tab": "mas"}, session=session)
