# src/nicheradar/web/routes_niches.py
"""Niche list (M2) and the 'mark tentative' decision."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import SHAPE_ERRORS, current_session, is_fragment, render, shape_guard
from nicheradar.web.niche_decision import (
    detail_url,
    note_problem,
    safe_target,
    target_url,
    valid_label,
    validate_note,
)
from nicheradar.web.niche_detail import (
    UNREADABLE,
    detail_view,
    latest_research,
    open_pilot,
)
from nicheradar.web.niches import AVISOS_NICHOS, list_view, parse_filters
from nicheradar.web.security import Session
from nicheradar.web.segment import UNKNOWN, counts, subniche_total

router = APIRouter()
VARY = "HX-Request, HX-History-Restore-Request"
FORMATS = ("long", "shorts")
MISSING = "No se encontró lo que buscabas."
DECISIONS = ("nuevo", "tentativo", "descartado")
DECISION_FAILED = "No se pudo guardar la decisión."
DETAIL_NOTICES = {
    "decidido": ("Decisión guardada.", "green"),
    "error": (DECISION_FAILED, "rose"),
    "invalida": ("Revisa la decisión y la nota.", "amber"),
}
RESEARCH_PAGE = 100
RESEARCH_OLDER = (
    "Puede haber investigaciones más antiguas que no se ven; "
    "el botón Investigar podría repetir una."
)
PILOTS_OLDER = (
    "Puede haber pilotos más antiguos que no se ven: el recorrido podría estar incompleto."
)
RESEARCH_DOWN = "La lista de investigaciones no está disponible: no se muestra su estado."


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
                "seg_counts": counts(UNKNOWN, subniche_total(api)),
                "fragment": htmx,
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
                "seg_counts": counts(view["api_total"], subniche_total(api)),
                "fragment": htmx,
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
    return _detail_page(
        request,
        session,
        etiqueta,
        formato,
        notice=DETAIL_NOTICES.get(request.query_params.get("aviso", "")),
    )


def _detail_page(
    request: Request,
    session: Session,
    etiqueta: str,
    formato: str,
    *,
    notice: tuple[str, str] | None = None,
    form: dict[str, str] | None = None,
    status: int = 200,
) -> Response:
    """The detail; `form` (decision, note, error) re-shows what was typed after a refused save."""
    if not valid_label(etiqueta) or formato not in FORMATS:
        return _missing(request, session, MISSING, 404)
    api = request.app.state.api
    try:
        detail = api.request(
            "GET", f"/market/niches/{quote(etiqueta, safe='')}", params={"format": formato}
        )
    except ApiError as error:
        missing = error.kind in ("not_found", "invalid")
        if form is not None:
            return _bare_decision(request, session, etiqueta, formato, form, status)
        return _missing(
            request, session, MISSING if missing else error.message, 404 if missing else 503
        )
    research: object
    pilot: object
    research_capped = pilots_capped = False
    try:
        orders = api.request("GET", "/flow-research", params={"limit": str(RESEARCH_PAGE)})["items"]
        research_capped = len(orders) >= RESEARCH_PAGE
        research = latest_research(orders, etiqueta, formato)
    except (ApiError, KeyError, TypeError):
        research = UNREADABLE
    try:
        pilots = api.request("GET", "/pilots", params={"limit": str(RESEARCH_PAGE)})["items"]
        pilots_capped = len(pilots) >= RESEARCH_PAGE
        pilot = open_pilot(pilots, etiqueta, formato)
    except (ApiError, KeyError, TypeError):
        pilot = UNREADABLE
    try:
        view = detail_view(
            detail,
            research,
            pilot,
            request.app.state.config.timezone,
            research_capped=research_capped,
        )
        if research_capped:
            view["warnings"].append(RESEARCH_OLDER)
        if pilots_capped:
            view["warnings"].append(PILOTS_OLDER)
    except SHAPE_ERRORS:
        if form is None:
            raise
        return _bare_decision(request, session, etiqueta, formato, form, status)
    view["form"] = {**view["form"], **(form or {})}
    response = render(
        request,
        "nichos/detalle.html",
        {
            "active_tab": "nichos",
            "v": view,
            "notice": notice,
            "etiqueta": etiqueta,
            "formato": formato,
            "volver": detail_url(etiqueta, formato),
        },
        status_code=status,
        session=session,
    )
    response.headers["Vary"] = VARY
    return response


def _bare_decision(
    request: Request,
    session: Session,
    etiqueta: str,
    formato: str,
    form: dict[str, str],
    status: int,
) -> Response:
    """The detail could not be read: only the decision card, so nothing typed is lost."""
    return render(
        request,
        "nichos/decision_error.html",
        {
            "active_tab": "nichos",
            "title": etiqueta,
            "v": {"form": form},
            "etiqueta": etiqueta,
            "formato": formato,
            "volver": detail_url(etiqueta, formato),
        },
        status_code=status,
        session=session,
    )


def _missing(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


def _fail(
    request: Request,
    session: Session,
    form: dict[str, str],
    etiqueta: str,
    formato: str,
    message: str,
    status: int,
) -> Response:
    return _detail_page(
        request, session, etiqueta, formato, form={**form, "error": message}, status=status
    )


@router.post("/nichos/decidir")
def decide(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    etiqueta: Annotated[str, Form()] = "",
    formato: Annotated[str, Form()] = "",
    decision: Annotated[str, Form()] = "",
    nota: Annotated[str, Form()] = "",
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
    target = safe_target(volver) or ("list", [])
    kind, pairs = target
    detail = kind == "detail" and valid_label(etiqueta) and formato in FORMATS
    if kind == "detail" and dict(pairs) != {"etiqueta": etiqueta, "formato": formato}:
        return RedirectResponse(target_url(kind, pairs, "invalida"), status_code=303)
    form = {"decision": decision if decision in DECISIONS else "nuevo", "note": nota}
    if decision not in DECISIONS or formato not in FORMATS or not valid_label(etiqueta):
        if detail:
            return _fail(
                request, session, form, etiqueta, formato, "La decisión no es válida.", 422
            )
        return RedirectResponse(target_url(kind, pairs, "invalida"), status_code=303)
    note = validate_note(nota)
    if note is None:
        if detail:
            return _fail(request, session, form, etiqueta, formato, note_problem(nota) or "", 422)
        return RedirectResponse(target_url(kind, pairs, "invalida"), status_code=303)
    body: dict[str, str] = {"format": formato, "decision": decision}
    if note:
        body["note"] = note
    try:
        request.app.state.api.request(
            "POST", f"/market/niches/{quote(etiqueta, safe='')}/decisions", body=body
        )
    except ApiError as error:
        if detail:
            if error.kind == "not_found":
                return _fail(request, session, form, etiqueta, formato, MISSING, 404)
            keep = error.kind in ("unavailable", "not_configured", "unauthorized")
            return _fail(
                request,
                session,
                form,
                etiqueta,
                formato,
                error.message if keep else DECISION_FAILED,
                503,
            )
        return RedirectResponse(target_url(kind, pairs, "error"), status_code=303)
    if kind == "detail":
        return RedirectResponse(target_url(kind, pairs, "decidido"), status_code=303)
    notice = "marcado" if decision == "tentativo" else "guardada"
    return RedirectResponse(target_url(kind, pairs, notice), status_code=303)
