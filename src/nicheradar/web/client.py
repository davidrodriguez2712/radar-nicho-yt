# src/nicheradar/web/client.py
"""Server-side client of the private API. The browser never sees the service token."""

import json
from typing import Any

import httpx

from nicheradar.config import Settings

TIMEOUT_SECONDS = 15
MAX_TEXT_BYTES = 256 * 1024  # the API itself caps what it accepts from the channel at 256 KiB
STATUS_TIMEOUT_SECONDS = 3  # the badge must never double the wait of a hung API
MESSAGES = {
    "not_configured": "Falta configurar la credencial de servicio.",
    "unavailable": "API no disponible. Los datos anteriores no se han actualizado.",
    "unauthorized": "La API rechazó la credencial de servicio. Revisa la configuración.",
    "not_found": "No se encontró lo que buscabas.",
    "conflict": "No se aplicó el cambio: el radar está pausado, la versión cambió o falta algo.",
    "invalid": "Revisa los valores: la solicitud no cumple el formato esperado.",
    "error": "No se pudo completar la solicitud. Revisa la API y la base de datos.",
}


class ApiError(Exception):
    def __init__(self, kind: str, status: int | None = None, detail: object = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.status = status
        self.detail = detail

    @property
    def message(self) -> str:
        if self.kind == "conflict" and isinstance(self.detail, dict):
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
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
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
                if declared.isdigit() and int(declared) > MAX_TEXT_BYTES:
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
