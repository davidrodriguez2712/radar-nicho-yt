# src/nicheradar/web/routes_reports.py
"""M3 and M11: the dossier report of a flow-research order, or the state of one without report."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.report import notice, report_view, status_view
from nicheradar.web.research import UUID_RE
from nicheradar.web.security import Session

router = APIRouter()
NOT_FOUND = "No se encontró lo que buscabas."


def _error(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
        with_radar=False,
    )


@router.get("/informes/{report_id}")
@shape_guard
def report(
    request: Request,
    report_id: str,
    session: Annotated[Session, Depends(current_session)],
    aviso: str = "",
    piloto: str = "",
) -> Response:
    # UUID_RE has no anchors: always fullmatch, so a trailing newline is rejected.
    if not UUID_RE.fullmatch(report_id):
        return _error(request, session, NOT_FOUND, 404)
    try:
        detail = request.app.state.api.request("GET", f"/flow-research/{quote(report_id, safe='')}")
    except ApiError as err:
        missing = err.kind in ("not_found", "invalid")
        return _error(
            request, session, NOT_FOUND if missing else err.message, 404 if missing else 503
        )
    detail = {**detail, "id": report_id}  # links use the id that was validated, not the payload's
    context = {"active_tab": "nichos", "notice": notice(aviso, piloto)}
    if detail.get("status") == "listo":
        view = report_view(detail, request.app.state.config.timezone)
        if not view["missing"]:
            return render(request, "informes/informe.html", context | {"v": view}, session=session)
    return render(
        request,
        "informes/estado.html",
        context | {"v": status_view(detail)},
        session=session,
    )
