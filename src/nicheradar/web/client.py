# src/nicheradar/web/client.py
"""Server-side client of the private API. The browser never sees the service token."""

import json
from typing import Any

import httpx

from nicheradar.config import Settings

TIMEOUT_SECONDS = 15
MAX_TEXT_BYTES = 256 * 1024  # the API itself caps what it accepts from the channel at 256 KiB
MESSAGES = {
    "not_configured": "Falta configurar la credencial de servicio.",
    "unavailable": "API no disponible. Los datos anteriores no se han actualizado.",
    "unauthorized": "La API rechazó la credencial de servicio. Revisa la configuración.",
    "not_found": "No se encontró lo que buscabas.",
    "conflict": "No se aplicó el cambio: el radar está pausado, la versión cambió o falta algo.",
    "invalid": "Revisa los valores: la solicitud no cumple el formato esperado.",
    "error": "No se pudo completar la solicitud. Revisa la API y la base de datos.",
}
LLM_UNAVAILABLE = "El modelo de lenguaje no está disponible: usa la propuesta manual."
# Closed list of domain codes the web knows. The text shown is the web's own, never the API's:
# an unknown code (or any `message` the server sends) is not displayed. `not_found` is left out
# because its meaning depends on the endpoint; the `kind` already has a message for it.
CODE_MESSAGES: dict[str, str] = {
    "invalid_input": (
        "No se reconoce esa entrada. Usa una consulta, un video, o un canal con @handle o enlace."
    ),
    "tweet_not_supported_yet": "Los enlaces de X todavía no se leen.",
    "manual_needs_a_query": "La propuesta manual solo admite una consulta.",
    "daily_limit": "Se llegó al tope diario de propuestas.",
    "duplicate": "Ya existe una hipótesis con esa consulta o con ese canal semilla.",
    "unknown_parent_niche": "Ese nicho padre no existe en el catálogo.",
    "invalid_proposal": "La propuesta no es válida.",
    "youtube_not_configured": "YouTube no está configurado en el servidor.",
    "youtube_quota_exhausted": (
        "La cuota de búsqueda de YouTube de hoy está agotada; "
        "inténtalo mañana o usa una consulta manual."
    ),
    "youtube_unreachable": "No se pudo consultar YouTube; vuelve a intentarlo.",
    "abandoned": "La preparación se interrumpió; vuelve a intentarlo.",
    "invalid_transition": "Esa hipótesis no puede pasar a ese estado.",
    **dict.fromkeys(
        (
            "llm_disabled",
            "synthetic_mode",
            "configuration_missing",
            "llm_tariff_not_current",
            "policy_not_enabled",
            "llm_failed",
            "invalid_response",
            "incomplete_response",
        ),
        LLM_UNAVAILABLE,
    ),
}
CODE_MAX = 80


class RootDetail(dict[str, Any]):
    """A `{code, message}` found at the root of the body, not under `detail`: its `message`
    is never shown."""


def code_of(detail: object) -> str | None:
    """The domain `code` of an error detail, or None when absent, not text or absurdly long."""
    code = detail.get("code") if isinstance(detail, dict) else None
    if isinstance(code, str) and 0 < len(code) <= CODE_MAX:
        return code
    return None


class ApiError(Exception):
    def __init__(self, kind: str, status: int | None = None, detail: object = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.status = status
        self.detail = detail

    @property
    def code(self) -> str | None:
        return code_of(self.detail)

    @property
    def message(self) -> str:
        code = self.code
        if code is not None:
            known = CODE_MESSAGES.get("duplicate" if code.startswith("duplicate") else code)
            if known is not None:
                return known
        if (
            self.kind == "conflict"
            and isinstance(self.detail, dict)
            and not isinstance(self.detail, RootDetail)
        ):
            text = self.detail.get("message")
            if isinstance(text, str) and text:
                return text
        return MESSAGES.get(self.kind, MESSAGES["error"])


def _error_detail(raw: bytes) -> object:
    """The `detail` of a JSON error body, or None when the body is not JSON or has none."""
    try:
        body_json = json.loads(raw)
    except ValueError:
        return None
    detail = body_json.get("detail") if isinstance(body_json, dict) else None
    if detail is None and isinstance(body_json, dict) and "problems" in body_json:
        detail = body_json  # the API's `{accepted: false, problems: [...]}` 422
    if detail is None and isinstance(body_json, dict) and "code" in body_json:
        detail = RootDetail(body_json)  # a domain rejection: `{code, message}` at the root
    return detail


def _kind(status: int) -> str:
    if status in (401, 403):
        return "unauthorized"
    return {404: "not_found", 409: "conflict", 422: "invalid"}.get(status, "error")


class ApiClient:
    def __init__(self, config: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: object = None,
        headers: dict[str, str] | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        token = self._config.service_token
        if token is None:
            raise ApiError("not_configured")
        try:
            with httpx.Client(
                base_url=self._config.api_url,
                timeout=timeout,
                transport=self._transport,
                headers={
                    **{
                        k: v
                        for k, v in (headers or {}).items()
                        if k.strip().lower() != "authorization"
                    },
                    "Authorization": f"Bearer {token.get_secret_value()}",
                },
            ) as client:
                response = client.request(method, "/api/v1" + path, params=params, json=body)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise ApiError("unavailable") from error
        if response.status_code >= 400:
            raise ApiError(
                _kind(response.status_code), response.status_code, _error_detail(response.content)
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            result = response.json()
        except ValueError as error:
            raise ApiError("error", response.status_code) from error
        if not isinstance(result, dict):
            raise ApiError("error", response.status_code)
        return result

    def request_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> str:
        """A plain-text endpoint. Same errors as `request`; bodies over 256 KiB are refused."""
        token = self._config.service_token
        if token is None:
            raise ApiError("not_configured")
        try:
            with (
                httpx.Client(
                    base_url=self._config.api_url,
                    timeout=timeout,
                    transport=self._transport,
                    headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                ) as client,
                client.stream(method, "/api/v1" + path, params=params) as response,
            ):
                declared = response.headers.get("content-length", "")
                if declared.isascii() and declared.isdigit() and int(declared) > MAX_TEXT_BYTES:
                    raise ApiError("error", response.status_code)
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw += chunk
                    if len(raw) > MAX_TEXT_BYTES:
                        raise ApiError("error", response.status_code)
                status = response.status_code
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise ApiError("unavailable") from error
        if status >= 400:
            raise ApiError(_kind(status), status, _error_detail(bytes(raw)))
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("error", status) from error
