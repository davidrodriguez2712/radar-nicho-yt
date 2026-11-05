# src/nicheradar/web/routes_share.py
"""M29/M30: a link shared from Android. Read-only: it classifies and offers «Proponer»."""

import base64
import hashlib
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from nicheradar.integrations.tweets import MAX_IMAGE_BYTES, sniff_image_type
from nicheradar.web.client import MESSAGES, ApiError
from nicheradar.web.deps import current_session, render, shape_guard
from nicheradar.web.leads import error_text
from nicheradar.web.proposals import PROPOSAL_ID, idempotency_key, new_nonce, valid_nonce
from nicheradar.web.security import SESSION_COOKIE, Session
from nicheradar.web.share import Classified, classify, extract_link

router = APIRouter()
SHARE_FIELD_MAX = 2000
SMALL_FORM = 16_384
IMAGE_NOTICES = {
    "imagen_no_valida": "Solo se aceptan imágenes PNG, JPEG o WEBP de hasta 5 MB.",
    "reinstala": (
        "Para compartir imágenes, abre NicheRadar una vez desde el icono instalado y vuelve a "
        "compartir. Si «Compartir» sigue sin ofrecer NicheRadar con imagen, desinstala la app y "
        "vuelve a instalarla."
    ),
}
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


@router.post("/compartir")
async def share_without_worker(request: Request) -> Response:
    """Llega aquí solo si el service worker no está activo: no se guarda nada."""
    declared = request.headers.get("content-length", "")
    if not (declared.isascii() and declared.isdigit()) or int(declared) > SMALL_FORM:
        return RedirectResponse("/compartir/imagen?aviso=reinstala", status_code=303)
    try:
        form = await request.form(max_files=0, max_fields=5, max_part_size=SMALL_FORM)
    except Exception:  # noqa: BLE001 - un archivo o un formulario raro: no se lee
        return RedirectResponse("/compartir/imagen?aviso=reinstala", status_code=303)
    params = {
        key: str(form.get(key, ""))[:SHARE_FIELD_MAX]
        for key in ("title", "text", "url")
        if form.get(key)
    }
    return RedirectResponse("/compartir?" + urlencode(params), status_code=303)


@router.get("/compartir/imagen")
@shape_guard
def shared_image(
    request: Request,
    session: Annotated[Session, Depends(current_session)],
    aviso: str = "",
) -> Response:
    context = {"active_tab": "nichos", "nonce": new_nonce(), "aviso": IMAGE_NOTICES.get(aviso)}
    return render(request, "compartir/imagen.html", context, session=session)


@router.get("/compartir/imagen/archivo")
def shared_file_is_never_on_the_server() -> Response:
    """La imagen compartida solo vive en la caché del teléfono (service worker)."""
    return Response(status_code=404)


def _refuse(text: str, status: int) -> JSONResponse:
    return JSONResponse({"error": text}, status_code=status)


@router.post("/compartir/imagen/leer")
async def read_image(request: Request) -> Response:
    """Cuerpo crudo con la imagen; se reenvía en base64 a la API. Nada se guarda aquí."""
    signer = request.app.state.signer
    session = signer.read(request.cookies.get(SESSION_COOKIE)) if signer is not None else None
    if session is None:
        return _refuse("Inicia sesión de nuevo y vuelve a compartir.", 401)
    nonce = request.headers.get("x-nonce", "")
    if not signer.csrf_valid(session, request.headers.get("x-csrf-token")) or not valid_nonce(
        nonce
    ):
        return _refuse("La solicitud no es válida.", 403)
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
        return _refuse(error_text("image_too_large"), 413)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_IMAGE_BYTES:
            return _refuse(error_text("image_too_large"), 413)
    media_type = sniff_image_type(bytes(raw))
    if media_type is None:
        return _refuse(error_text("invalid_image"), 422)
    body = {"media_type": media_type, "data": base64.b64encode(bytes(raw)).decode("ascii")}
    # La clave depende de los bytes, no de su copia en base64: el mismo toque, la misma lectura.
    fingerprint = {"media_type": media_type, "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        data = await run_in_threadpool(
            request.app.state.api.request,
            "POST",
            "/leads/images",
            body=body,
            headers={"Idempotency-Key": idempotency_key(signer, session, nonce, fingerprint)},
            timeout=30,
        )
    except ApiError as error:
        domain = error.code is not None and error.status in (409, 413, 422, 429, 503)
        text = error_text(error.code) if domain else MESSAGES.get(error.kind, MESSAGES["error"])
        return _refuse(text, error.status if domain and error.status else 503)
    read_id = data.get("id")
    if not isinstance(read_id, str) or PROPOSAL_ID.fullmatch(read_id) is None:
        return _refuse("No se pudo leer.", 503)
    return JSONResponse({"next": f"/lecturas/{read_id}"})
