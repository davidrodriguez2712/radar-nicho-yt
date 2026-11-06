# src/nicheradar/api_limits.py
"""Límite de tamaño de cuerpo de `/api/v1`, aplicado ANTES de autenticar.

FastAPI lee y parsea el cuerpo JSON de los endpoints con modelo Pydantic antes de resolver la
dependencia `authenticate` (medido: 50 MB sin token tardaban 39 ms en devolver 401, con todo el
cuerpo ya cargado). Este middleware ASGI puro (no `BaseHTTPMiddleware`: no bufferiza nada) rechaza
con 413 en cuanto el `Content-Length` declarado o los bytes realmente recibidos pasan del tope, sin
leer el resto. El 413 sale también sin token: es intencional y el mensaje es fijo, no repite nada
de la petición.

Las exenciones de la tabla son por igualdad exacta de ruta (una subruta de `leads/images` es
otra ruta con cuerpo JSON); los topes cubren la ruta y sus subrutas.

Solo toca peticiones HTTP con método con cuerpo (POST, PUT, PATCH) a rutas bajo `/api/v1`;
`lifespan`, websocket, GET/HEAD/DELETE y el resto de rutas pasan tal cual.

Auditoría de los cuerpos legítimos más grandes (que fija los topes):

* `POST /api/v1/leads/images`: imagen en base64 (7,1 MB). Exenta: autentica antes y lee en
  streaming con su propio tope (`lead_api.MAX_IMAGE_BODY`).
* `POST /api/v1/flow-research/{id}/dossier`: el cuerpo es `dict[str, Any]` y lo valida
  `DossierV3`. Peor caso teórico (todas las listas y textos al máximo de sus contratos, a 1 byte
  por carácter) de unos 2,3 MB; un dossier real pesa decenas de KB. Es el mayor cuerpo legítimo.
* `POST /api/v1/pilots/{id}/reports` (informes `channel-report-v3`, hasta 100 videos): la propia
  ruta ya rechaza por encima de 256 KiB (`pilots.contracts.MAX_REPORT_BYTES`).
* Import de subnichos con YAML: solo por CLI (`importer.MAX_CHARS` = 200 000 caracteres), no hay
  endpoint en la API.
* Mercado, pilotos, canales, decisiones, escenarios, `runs`: cuerpos de pocos KB (textos de hasta
  4000 caracteres).
* `leads/{tweets,names,proposals}` y `subniches/proposals`: una URL (500), hasta 10 UUID o una
  etiqueta (500); menos de 4 KB reales.

Por eso el tope por defecto es 4 MiB (el dossier teórico de 2,3 MB redondeado hacia arriba con
margen) y el de leads/propuestas es 64 KiB.
"""

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, NamedTuple

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

API_PREFIX = "/api/v1"
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
LEAD_BODY_LIMIT = 64 * 1024
DEFAULT_BODY_LIMIT = 4 * 1024 * 1024


class Rule(NamedTuple):
    path: str
    limit: int | None  # None = exenta
    exact: bool  # True: solo esa ruta; False: la ruta y todas sus subrutas (por segmentos)


# Gana la primera coincidencia. Criterio: una EXENCIÓN es siempre exacta (`exact=True`): una
# subruta como `/api/v1/leads/images/names` cae en otra ruta (`/{read_id}/names`) con cuerpo JSON y
# no debe heredar la exención. Un TOPE (no exento) cubre también las subrutas: solo las acota más.
BODY_LIMITS: tuple[Rule, ...] = (
    Rule("/api/v1/leads/images", None, exact=True),
    Rule("/api/v1/leads", LEAD_BODY_LIMIT, exact=False),
    Rule("/api/v1/subniches/proposals", LEAD_BODY_LIMIT, exact=False),
)
PAYLOAD_TOO_LARGE = {
    "code": "payload_too_large",
    "message": "El cuerpo de la solicitud es demasiado grande.",
}
_RESPONSE_BODY = json.dumps(PAYLOAD_TOO_LARGE).encode()
_RESPONSE_HEADERS = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_RESPONSE_BODY)).encode()),
    (b"connection", b"close"),
]


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def limit_for(path: str) -> int | None:
    """Tope en bytes para `path`, o None si el middleware no debe tocarla."""
    if not _under(path, API_PREFIX):
        return None
    for rule in BODY_LIMITS:
        if path == rule.path or (not rule.exact and _under(path, rule.path)):
            return rule.limit
    return DEFAULT_BODY_LIMIT


class _BodyTooLarge(BaseException):
    """BaseException a propósito: FastAPI vuelve 400 cualquier `Exception` al leer el cuerpo."""


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or ():
        if name == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isascii() and text.isdigit() else None
    return None


class ApiBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = (
            limit_for(scope["path"])
            if scope["type"] == "http" and scope["method"] in BODY_METHODS
            else None
        )
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await self._reject(send)
            return
        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except* _BodyTooLarge:
            # `except*` atrapa también el corte envuelto en un BaseExceptionGroup (task group).
            # Si la respuesta ya empezó no se envía un segundo inicio: se relanza el corte y el
            # servidor cierra la conexión.
            if started:
                raise
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send({"type": "http.response.start", "status": 413, "headers": _RESPONSE_HEADERS})
        await send({"type": "http.response.body", "body": _RESPONSE_BODY})
