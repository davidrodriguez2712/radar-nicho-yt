# src/nicheradar/web/routes_niches.py
"""Niche list (M2) and the 'mark tentative' decision."""

from typing import Annotated
from urllib.parse import parse_qsl, quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import current_session, is_fragment, render, shape_guard
from nicheradar.web.niche_detail import (
    UNREADABLE,
    detail_view,
    latest_research,
    open_pilot,
)
from nicheradar.web.niches import AVISOS_NICHOS, list_view, parse_filters
from nicheradar.web.security import Session

router = APIRouter()
VARY = "HX-Request, HX-History-Restore-Request"
FORMATS = ("long", "shorts")
MISSING = "No se encontró lo que buscabas."
DECISIONS = ("nuevo", "tentativo", "descartado")
RESEARCH_PAGE = 100
RESEARCH_OLDER = (
    "Puede haber investigaciones más antiguas que no se ven; "
    "el botón Investigar podría repetir una."
)
RESEARCH_DOWN = "La lista de investigaciones no está disponible: no se muestra su estado."


def _back(volver: str, aviso: str) -> str:
    # Only the niche list itself: an open redirect through `volver` must be impossible.
    base = volver if volver == "/nichos" or volver.startswith("/nichos?") else "/nichos"
    path, _, query = base.partition("?")
    pairs = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "aviso"]
    return path + "?" + urlencode([*pairs, ("aviso", aviso)])


@router.get("/nichos")
@shape_guard
def niche_list(request: Request, session: Annotated[Session, Depends(current_session)]) -> Response:
    filters = parse_filters(request.query_params)
    htmx = is_fragment(request)
    template = "nichos/_lista.html" if htmx else "nichos/lista.html"
    notice = AVISOS_NICHOS.get(request.query_params.get("aviso", ""))
    api = request.app.state.api
    try:
        niches = api.request(
            "GET", "/market/niches", params={"order": filters.orden, "limit": "200"}
        )
    except ApiError as error:
        response = render(
            request,
            template,
            {
                "active_tab": "nichos",
                "error": error.message,
                "view": None,
                "filtros": filters,
                "notice": None,
                "warnings": [],
            },
            status_code=200 if htmx else 503,
            session=session,
        )
    else:
        warnings: list[str] = []
        try:
            research = api.request("GET", "/flow-research", params={"limit": str(RESEARCH_PAGE)})[
                "items"
            ]
        except ApiError:
            research = []
            warnings.append(RESEARCH_DOWN)
        else:
            if len(research) >= RESEARCH_PAGE:
                warnings.append(RESEARCH_OLDER)
        view = list_view(niches["items"], research, filters, niches.get("total"))
        if view["truncated"]:
            warnings.insert(
                0,
                f"Se muestran {view['total']} de {view['api_total']} nichos: "
                "el resto no se carga en esta pantalla.",
            )
        response = render(
            request,
            template,
            {
                "active_tab": "nichos",
                "error": None,
                "view": view,
                "filtros": filters,
                "notice": notice,
                "warnings": warnings,
            },
            session=session,
        )
    response.headers["Vary"] = VARY
    return response


@router.get("/nichos/ver")
@shape_guard
def niche_detail(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    etiqueta: str = "",
    formato: str = "",
) -> Response:
    if not (1 <= len(etiqueta) <= 140) or etiqueta in (".", "..") or formato not in FORMATS:
        return _missing(request, session, MISSING, 404)
    api = request.app.state.api
    try:
        detail = api.request(
            "GET", f"/market/niches/{quote(etiqueta, safe='')}", params={"format": formato}
        )
    except ApiError as error:
        missing = error.kind in ("not_found", "invalid")
        return _missing(
            request, session, MISSING if missing else error.message, 404 if missing else 503
        )
    research: object
    pilot: object
    try:
        research = latest_research(
            api.request("GET", "/flow-research", params={"limit": str(RESEARCH_PAGE)})["items"],
            etiqueta,
            formato,
        )
    except (ApiError, KeyError, TypeError):
        research = UNREADABLE
    try:
        pilot = open_pilot(
            api.request("GET", "/pilots", params={"limit": str(RESEARCH_PAGE)})["items"],
            etiqueta,
            formato,
        )
    except (ApiError, KeyError, TypeError):
        pilot = UNREADABLE
    view = detail_view(detail, research, pilot, request.app.state.config.timezone)
    response = render(
        request,
        "nichos/detalle.html",
        {"active_tab": "nichos", "v": view},
        session=session,
    )
    response.headers["Vary"] = VARY
    return response


def _missing(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


@router.post("/nichos/decidir")
def decide(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    etiqueta: Annotated[str, Form()] = "",
    formato: Annotated[str, Form()] = "",
    decision: Annotated[str, Form()] = "",
    volver: Annotated[str, Form()] = "/nichos",
) -> Response:
    if not request.app.state.signer.csrf_valid(session, csrf):
        return render(
            request,
            "error.html",
            {"message": "La solicitud no es válida."},
            status_code=403,
            session=session,
        )
    if (
        decision not in DECISIONS
        or formato not in ("long", "shorts")
        or not (1 <= len(etiqueta) <= 140)
        or etiqueta in (".", "..")
    ):
        return RedirectResponse(_back(volver, "invalida"), status_code=303)
    try:
        request.app.state.api.request(
            "POST",
            f"/market/niches/{quote(etiqueta, safe='')}/decisions",
            body={"format": formato, "decision": decision},
        )
    except ApiError:
        return RedirectResponse(_back(volver, "error"), status_code=303)
    notice = "marcado" if decision == "tentativo" else "guardada"
    return RedirectResponse(_back(volver, notice), status_code=303)
