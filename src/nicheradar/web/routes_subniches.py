# src/nicheradar/web/routes_subniches.py
"""Sub-niche screens: M9 list and M10 card with the start-research action."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, render
from nicheradar.web.security import Session
from nicheradar.web.subniches import AVISOS, detail_view, list_view, parse_filters

router = APIRouter()


VARY = "HX-Request, HX-History-Restore-Request"
INACTIVE_STATES = ("paused", "archived")
MISSING = "No se encontró lo que buscabas."


@router.get("/subnichos")
def subniche_list(
    request: Request, session: Annotated[Session, Depends(current_session)]
) -> Response:
    filters = parse_filters(request.query_params)
    # A history restore asks for the whole page even though htmx sets hx-request.
    htmx = bool(request.headers.get("hx-request")) and not request.headers.get(
        "hx-history-restore-request"
    )
    template = "subnichos/_lista.html" if htmx else "subnichos/lista.html"
    # Choosing paused/archived is explicit intent: the API hides them unless asked.
    inactive = filters.inactivos or filters.estado in INACTIVE_STATES
    try:
        data = request.app.state.api.request(
            "GET", "/subniches", params={"include_inactive": "true" if inactive else "false"}
        )
    except ApiError as error:
        # htmx does not swap 5xx, so a fragment request gets the error as a 200 fragment.
        response = render(
            request,
            template,
            {"active_tab": "nichos", "error": error.message, "view": None, "filtros": filters},
            status_code=200 if htmx else 503,
            session=session,
            with_radar=False,
        )
    else:
        view = list_view(data["items"], filters)
        response = render(
            request,
            template,
            {"active_tab": "nichos", "error": None, "view": view, "filtros": view["filtros"]},
            session=session,
        )
    response.headers["Vary"] = VARY
    return response


@router.get("/subnichos/{slug}")
def subniche_card(
    request: Request,
    slug: str,
    session: Annotated[Session, Depends(current_session)],
    aviso: str = "",
) -> Response:
    try:
        card = request.app.state.api.request("GET", f"/subniches/{quote(slug, safe='')}")
    except ApiError as error:
        # The API answers 422 for a slug it cannot even look up (too long): same as unknown.
        missing = error.kind in ("not_found", "invalid")
        return render(
            request,
            "error.html",
            {"message": MISSING if missing else error.message, "active_tab": "nichos"},
            status_code=404 if missing else 503,
            session=session,
            with_radar=False,
        )
    return render(
        request,
        "subnichos/ficha.html",
        {
            "active_tab": "nichos",
            "v": detail_view(card, request.app.state.config.timezone),
            "notice": AVISOS.get(aviso),
        },
        session=session,
    )


@router.post("/subnichos/{slug}/investigar")
def start_research(
    request: Request,
    slug: str,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request,
            "error.html",
            {"message": "La solicitud no es válida."},
            status_code=403,
            session=session,
        )
    api = request.app.state.api
    target = f"/subnichos/{quote(slug, safe='')}"
    try:
        hypothesis = api.request("GET", f"/subniches/{quote(slug, safe='')}")["hypothesis"]
        # Format and language come from the hypothesis, never from the form.
        result = api.request(
            "POST",
            "/flow-research",
            body={
                "niche_label": f"subniche:{hypothesis['slug']}",
                "format": hypothesis["format"],
                "language": hypothesis["language"],
            },
        )
    except ApiError as error:
        aviso = "no-lista" if error.kind == "conflict" else "error"
        return RedirectResponse(f"{target}?aviso={aviso}", status_code=303)
    aviso = "creada" if result.get("created") else "existente"
    return RedirectResponse(f"{target}?aviso={aviso}", status_code=303)
