# src/nicheradar/web/routes_pilots.py
"""M4 and M12: authorize a pilot from a finished dossier report.

The POST creates a pilot with real consequences, so everything that matters (niche, format,
dossier, budget) is derived here from the stored report; the form only supplies the rules.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from starlette.responses import RedirectResponse, Response

from nicheradar.web.client import ApiError
from nicheradar.web.deps import SHAPE_ERRORS, SHAPE_MESSAGE, current_session, render, shape_guard
from nicheradar.web.format import local_datetime, parse_utc
from nicheradar.web.niches import CONFIDENCE, FORMATS
from nicheradar.web.pilots_form import (
    GATE_MESSAGES,
    PILOT_ID_RE,
    Defaults,
    budget_body,
    busy_channels,
    parse_form,
)
from nicheradar.web.report import report_view, subject_label
from nicheradar.web.research import LANGUAGE_NAMES, UUID_RE
from nicheradar.web.security import Session

router = APIRouter()
_log = logging.getLogger(__name__)
GONE = "El nicho ya no está en el radar. Inicia el flujo de nuevo."
NOT_FOUND = "No se encontró lo que buscabas."
NOT_READY = "El informe todavía no está listo."
NO_BUDGET = "El informe no trae un presupuesto utilizable: no se puede autorizar el piloto."
LIST_LIMIT = 100
BUSY_FAILED = "No se pudo comprobar qué canales están ocupados."
BUSY_TRUNCATED = (
    f"Se leyeron los últimos {LIST_LIMIT} pilotos. Puede haber pilotos más antiguos que no se "
    "muestran: si un canal ya está en uso, la API lo rechazará al autorizar."
)
AUTHOR = "propietario (web)"


def _error_page(request: Request, session: Session, message: str, status: int) -> Response:
    return render(
        request,
        "error.html",
        {"message": message, "active_tab": "nichos"},
        status_code=status,
        session=session,
    )


def _fetch(request: Request, session: Session, report_id: str) -> dict[str, Any] | Response:
    """The stored report, or the error page that answers when it cannot be used."""
    try:
        detail = request.app.state.api.request("GET", f"/flow-research/{quote(report_id, safe='')}")
    except ApiError as err:
        missing = err.kind in ("not_found", "invalid")
        return _error_page(
            request, session, NOT_FOUND if missing else err.message, 404 if missing else 503
        )
    view = report_view(detail, request.app.state.config.timezone)
    if detail.get("status") != "listo" or view["missing"]:
        return _error_page(request, session, NOT_READY, 409)
    if not isinstance(detail.get("niche_label"), str) or detail.get("format") not in FORMATS:
        return _error_page(request, session, NOT_FOUND, 404)
    if budget_body(detail["dossier"], 1, report_id) is None:
        return _error_page(request, session, NO_BUDGET, 422)
    result: dict[str, Any] = {**detail, "id": report_id}  # the validated id, not the payload's
    return result


def _busy(request: Request) -> tuple[set[str], str | None]:
    """Busy channels and a warning when that list is missing or may be cut off."""
    try:
        items = request.app.state.api.request("GET", "/pilots", params={"limit": str(LIST_LIMIT)})
    except ApiError:
        return set(), BUSY_FAILED
    pilots = [p for p in items.get("items") or [] if isinstance(p, dict)]
    return busy_channels(pilots), BUSY_TRUNCATED if len(pilots) >= LIST_LIMIT else None


def _subniche_block(request: Request, detail: dict[str, Any]) -> dict[str, Any] | None:
    evidence = detail.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("source") != "subniche":
        return None
    measurement = evidence.get("measurement")
    measured = measurement.get("measured_at") if isinstance(measurement, dict) else None
    when: str | None = None
    ago: int | None = None
    if isinstance(measured, str):
        try:
            when = local_datetime(measured, request.app.state.config.timezone)[:10]
            moment = parse_utc(measured)
            now = datetime.fromtimestamp(request.app.state.clock(), UTC)
            ago = max((now - moment).days, 0)
        except (ValueError, TypeError, OverflowError, OSError):
            when = ago = None
    return {"date": when, "ago": ago, "confidence": CONFIDENCE.get(str(evidence.get("confidence")))}


def _needs(detail: dict[str, Any], view: dict[str, Any]) -> tuple[bool, bool]:
    evidence = detail.get("evidence")
    gate = evidence.get("gate") if isinstance(evidence, dict) else None
    frozen_failed = isinstance(gate, dict) and gate.get("passed") is False
    row_failed = any(state == "no pasa" for _, state, _ in view["gates"])
    verdict = detail["dossier"].get("verdict")
    no_go = isinstance(verdict, dict) and verdict.get("recommendation") == "no_go"
    return no_go, frozen_failed or row_failed


def _page(
    request: Request,
    session: Session,
    detail: dict[str, Any],
    *,
    form: dict[str, str] | None = None,
    errors: dict[str, str] | None = None,
    status: int = 200,
    error: str | None = None,
    reasons: list[str] | None = None,
    show_no_go: bool = False,
    show_gate: bool = False,
    accepted: tuple[bool, bool] = (False, False),
    busy: tuple[set[str], str | None] | None = None,
) -> Response:
    busy_set, warning = busy if busy is not None else _busy(request)
    view = report_view(detail, request.app.state.config.timezone)
    needs_no_go, needs_gate = _needs(detail, view)
    defaults = Defaults()
    values = {
        "max_videos": str(defaults.max_videos),
        "valid_days": str(defaults.valid_days),
        "close_after": str(defaults.close_after),
        "canal": "",
        "canal_modo": "",
    } | (form or {})
    language = detail.get("language")
    return render(
        request,
        "pilotos/autorizar.html",
        {
            "active_tab": "nichos",
            "v": view,
            "report_id": detail.get("id"),
            "title_label": subject_label(str(detail["niche_label"]))[0],
            "format_text": FORMATS[detail["format"]],
            "language": LANGUAGE_NAMES.get(str(language), str(language) if language else "—"),
            "subniche": _subniche_block(request, detail),
            "values": values,
            "errors": errors or {},
            "error": error,
            "reasons": reasons or [],
            "busy": sorted(busy_set),
            "busy_warning": warning,
            "needs_no_go": needs_no_go or show_no_go,
            "needs_gate": needs_gate or show_gate,
            "accepted": accepted,
        },
        status_code=status,
        session=session,
        # After a failed call the API already answered: skip the radar badge's extra call.
    )


@router.get("/pilotos/autorizar")
@shape_guard
def form(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    informe: str = "",
) -> Response:
    if not UUID_RE.fullmatch(informe):
        return _error_page(request, session, NOT_FOUND, 404)
    detail = _fetch(request, session, informe)
    if isinstance(detail, Response):
        return detail
    return _page(request, session, detail)


def _problems(detail: object) -> list[str]:
    items = detail.get("problems") if isinstance(detail, dict) else None
    out: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("message"), str):
            path = item.get("path")
            out.append(
                f"{path}: {item['message']}" if isinstance(path, str) and path else item["message"]
            )
    return out


@router.post("/pilotos/autorizar")
def authorize(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    csrf: Annotated[str, Form()] = "",
    informe: Annotated[str, Form()] = "",
    max_videos: Annotated[str, Form()] = "",
    valid_days: Annotated[str, Form()] = "",
    close_after: Annotated[str, Form()] = "",
    canal: Annotated[str, Form()] = "",
    accept_no_go: Annotated[str, Form()] = "",
    accept_gate_failure: Annotated[str, Form()] = "",
    canal_modo: Annotated[str, Form()] = "",
) -> Response:
    # niche_label, format and authorized_by are deliberately not read from the form.
    if not request.app.state.signer.csrf_valid(session, csrf):
        return _error_page(request, session, "La solicitud no es válida.", 403)
    if not UUID_RE.fullmatch(informe):
        return _error_page(request, session, NOT_FOUND, 404)
    typed = {
        "max_videos": max_videos,
        "valid_days": valid_days,
        "close_after": close_after,
        "canal": canal,
        "canal_modo": canal_modo,
    }
    accepted = (accept_no_go == "1", accept_gate_failure == "1")
    try:
        return _authorize(request, session, informe, typed, accepted)
    except SHAPE_ERRORS:
        _log.exception("unexpected API payload shape on authorize")
        try:  # redraw the form with what was typed if the report can still be read
            detail = _fetch(request, session, informe)
            if isinstance(detail, Response):
                return detail
            return _page(request, session, detail, form=typed, status=503, error=SHAPE_MESSAGE)
        except SHAPE_ERRORS:
            return _error_page(request, session, SHAPE_MESSAGE, 503)


def _authorize(
    request: Request,
    session: Session,
    informe: str,
    typed: dict[str, str],
    accepted: tuple[bool, bool],
) -> Response:
    detail = _fetch(request, session, informe)
    if isinstance(detail, Response):
        return detail
    # "Canal nuevo" means no target channel: whatever is typed in the text box is ignored.
    parsed = typed | {"canal": ""} if typed["canal_modo"] == "nuevo" else typed
    values, errors = parse_form(parsed)
    busy = _busy(request)
    context: dict[str, Any] = {"form": typed, "accepted": accepted, "busy": busy}
    if values is None:
        return _page(request, session, detail, errors=errors, status=422, **context)
    if values["canal"] in busy[0]:
        return _page(
            request, session, detail, status=409, error=GATE_MESSAGES["channel_busy"], **context
        )
    budget = budget_body(detail["dossier"], values["max_videos"], informe)
    body: dict[str, Any] = {
        "niche_label": detail["niche_label"],
        "format": detail["format"],
        "dossier_request_id": informe,
        "budget": budget,
        "authorized_by": AUTHOR,
        "close_after_failed_milestones": values["close_after"],
        "valid_days": values["valid_days"],
        "accept_no_go": accepted[0],
        "accept_gate_failure": accepted[1],
    }
    if values["canal"]:
        body["target_channel"] = values["canal"]
    try:
        result = request.app.state.api.request("POST", "/pilots", body=body)
    except ApiError as err:
        info = err.detail if isinstance(err.detail, dict) else {}
        code = str(info.get("code"))
        show_no_go = code == "no_go_requires_acceptance"
        show_gate = code == "gate_failed"
        if err.kind == "conflict":
            reasons = [
                str(r.get("message", "")) for r in info.get("reasons") or [] if isinstance(r, dict)
            ]
            return _page(
                request,
                session,
                detail,
                status=409,
                error=GATE_MESSAGES.get(code, err.message),
                reasons=reasons,
                show_no_go=show_no_go,
                show_gate=show_gate,
                **context,
            )
        if err.kind == "invalid":
            return _page(
                request,
                session,
                detail,
                status=422,
                error=err.message,
                reasons=_problems(err.detail),
                **context,
            )
        if err.kind == "not_found":
            return _page(request, session, detail, status=404, error=GONE, **context)
        return _page(request, session, detail, status=503, error=err.message, **context)
    pilot = result.get("pilot_id")
    if isinstance(pilot, str) and PILOT_ID_RE.fullmatch(pilot):
        return RedirectResponse(f"/pilotos/{pilot}?aviso=autorizado", status_code=303)
    return RedirectResponse(f"/informes/{informe}?aviso=piloto", status_code=303)
