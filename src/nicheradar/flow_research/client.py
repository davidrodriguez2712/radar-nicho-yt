# src/nicheradar/flow_research/client.py
"""HTTP client the Claude Code skill uses to claim requests and hand dossiers back."""

from typing import Any, Self

import httpx

from nicheradar.config import Settings

PREFIX = "/api/v1/flow-research"


class ApiError(Exception):
    def __init__(self, status: int, detail: object) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def _fail(response: httpx.Response) -> ApiError:
    try:
        detail: object = response.json().get("detail", response.text[:200])
    except (ValueError, AttributeError):
        detail = response.text[:200]
    return ApiError(response.status_code, detail)


class FlowResearchClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @classmethod
    def from_settings(cls, config: Settings) -> Self:
        if config.service_token is None:
            raise ValueError("Configura NR_SERVICE_TOKEN")
        token = config.service_token.get_secret_value()
        http = httpx.Client(
            base_url=config.api_url, timeout=30, headers={"Authorization": f"Bearer {token}"}
        )
        return cls(http)

    def _json(self, response: httpx.Response, *, accept: tuple[int, ...] = (200,)) -> Any:
        if response.status_code not in accept:
            raise _fail(response)
        return response.json()

    def create(
        self,
        niche_label: str,
        format: str,
        language: str,
        gate_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"niche_label": niche_label, "format": format, "language": language}
        if gate_override is not None:
            body["gate_override"] = gate_override
        created: dict[str, Any] = self._json(self.http.post(PREFIX, json=body), accept=(200, 201))
        return created

    def pending(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = self._json(self.http.get(PREFIX + "/pending"))["items"]
        return items

    def claim(self, request_id: str, owner: str) -> dict[str, Any]:
        response = self.http.post(f"{PREFIX}/{request_id}/claim", json={"owner": owner})
        claimed: dict[str, Any] = self._json(response)
        return claimed

    def submit(self, request_id: str, owner: str, dossier: dict[str, Any]) -> dict[str, Any]:
        response = self.http.post(
            f"{PREFIX}/{request_id}/dossier", json={"owner": owner, "dossier": dossier}
        )
        if response.status_code == 422 and "accepted" in response.json():
            rejected: dict[str, Any] = response.json()  # a contract rejection, not a usage error
            return rejected
        result: dict[str, Any] = self._json(response)
        return result
