"""vidIQ MCP adapter, mapped against tool contracts reviewed 2026-09-21.

Runtime auth must be supplied by this application's own API key or OAuth connection. Neither
construction nor normalization sends requests. No automatic paid retries.
"""

import asyncio
import hashlib
import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import (
    Balance,
    Batch,
    Channel,
    Cost,
    Coverage,
    Metric,
    Operation,
    Provenance,
    ProviderError,
    Video,
)


class ToolTransport(Protocol):
    async def call(self, name: str, parameters: dict[str, Any]) -> dict[str, Any]: ...


class VidIQAPIKeyAuth(httpx.Auth):
    """Own MCP key, restricted to vidIQ's HTTPS origin; never refreshes/retries."""

    def __init__(self, token: SecretStr):
        value = token.get_secret_value()
        if not value or not value.isascii() or any(char.isspace() for char in value):
            raise ProviderError("invalid_credential", not_sent=True)
        if any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise ProviderError("invalid_credential", not_sent=True)
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        if (
            request.url.scheme != "https"
            or request.url.host != "mcp.vidiq.com"
            or request.url.port not in {None, 443}
            or request.url.userinfo
        ):
            raise ProviderError("authentication_origin_rejected", not_sent=True)
        request.headers["Authorization"] = f"Bearer {self._token.get_secret_value()}"
        yield request


class MCPTransport:
    endpoint = "https://mcp.vidiq.com/mcp"

    def __init__(
        self,
        auth: httpx.Auth | None = None,
        *,
        enabled: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.auth = auth
        self.enabled = enabled
        self.transport = transport

    async def call(self, name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return await self._request(name, parameters)

    async def inspect_tools(self) -> dict[str, Any]:
        """Handshake and bounded tools/list only; never calls any provider tool.

        Return only known operation names and schema fingerprints. Descriptions,
        server instructions and arbitrary tool metadata never enter the report.
        This does not validate tariffs, account identity or research permissions.
        """
        return await self._request(None, {})

    async def _request(self, name: str | None, parameters: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise ProviderError("integration_disabled", not_sent=True)
        if self.auth is None:
            raise ProviderError("authentication_required", not_sent=True)
        sent = False
        try:
            async with (
                asyncio.timeout(45),
                httpx.AsyncClient(
                    auth=self.auth, timeout=20, transport=self.transport, trust_env=False
                ) as http,
            ):
                async with streamable_http_client(self.endpoint, http_client=http) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=20)
                    ) as session:
                        await session.initialize()
                        if name is None:
                            return await _inspect_tools(session)
                        sent = True
                        result = await session.call_tool(name, parameters)
                        if result.isError:
                            # Do not expose provider error text (may contain query text/secrets).
                            raise ProviderError("provider_tool_error", may_have_charged=True)
                        if result.structuredContent is not None:
                            return result.structuredContent
                        for block in result.content:
                            if block.type == "text":
                                value = json.loads(block.text)
                                if isinstance(value, dict):
                                    return value
                        raise ProviderError("invalid_response", may_have_charged=True)
        except ProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            code = (
                "authentication_required"
                if exc.response.status_code in {401, 403}
                else "quota"
                if exc.response.status_code == 429
                else "provider_http_error"
            )
            raise ProviderError(code, may_have_charged=sent, not_sent=not sent) from None
        except Exception as exc:
            leaves = list(_exception_leaves(exc))
            for leaf in leaves:
                if isinstance(leaf, ProviderError):
                    raise leaf from None
                if isinstance(leaf, httpx.HTTPStatusError):
                    if leaf.response.status_code in {401, 403, 429}:
                        raise ProviderError(
                            "quota"
                            if leaf.response.status_code == 429
                            else "authentication_required",
                            may_have_charged=sent,
                            not_sent=not sent,
                        ) from None
            raise ProviderError(
                "transport_failure", may_have_charged=sent, retry_safe=not sent, not_sent=not sent
            ) from None


async def _inspect_tools(session: ClientSession) -> dict[str, Any]:
    matches: dict[str, list[dict[str, str]]] = {op.value: [] for op in VidIQProvider.operations}
    aliases = {
        alias: op.value
        for op in VidIQProvider.operations
        for alias in (op.value, f"vidiq_{op.value}")
    }
    cursor = None
    seen: set[str] = set()
    total = 0
    for _ in range(5):
        page = await session.list_tools(cursor=cursor)
        total += len(page.tools)
        if total > 250:
            raise ProviderError("tool_catalog_limit", not_sent=True)
        for tool in page.tools:
            if tool.name in aliases:
                matches[aliases[tool.name]].append(
                    {
                        "tool_name": tool.name,
                        "input_schema_sha256": hashlib.sha256(
                            json.dumps(tool.inputSchema, sort_keys=True).encode()
                        ).hexdigest(),
                    }
                )
        cursor = page.nextCursor
        if not cursor:
            break
        if cursor in seen:
            raise ProviderError("tool_catalog_pagination", not_sent=True)
        seen.add(cursor)
    else:
        raise ProviderError("tool_catalog_limit", not_sent=True)
    return {
        "status": "connected",
        "authentication": "accepted",
        "tool_calls": 0,
        "catalog_tools": total,
        "operations": {
            operation: {
                "status": "available"
                if len(found) == 1
                else "missing"
                if not found
                else "ambiguous",
                "matches": found,
            }
            for operation, found in sorted(matches.items())
        },
        "pilot_ready": False,
    }


def _exception_leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for nested in exc.exceptions for leaf in _exception_leaves(nested)]
    return [exc]


def _date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Contract's outlier publication timestamp is in epoch seconds.
        return datetime.fromtimestamp(value, UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _format(value: Any) -> VideoFormat:
    return {
        "long": VideoFormat.LONG,
        "short": VideoFormat.SHORTS,
        "shorts": VideoFormat.SHORTS,
    }.get(str(value), VideoFormat.UNKNOWN)


class VidIQProvider:
    name = "vidiq"
    operations = frozenset(
        {
            Operation.CHANNEL_SEARCH,
            Operation.CHANNEL_VIDEOS,
            Operation.OUTLIERS,
            Operation.KEYWORDS,
            Operation.BALANCE,
        }
    )

    def __init__(self, transport: ToolTransport, auth_scope: str):
        self.transport = transport
        self.auth_scope = auth_scope
        self.calls = 0

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if operation not in self.operations:
            raise ProviderError("unsupported_operation")
        args = {key: value for key, value in parameters.items() if key != "family"}
        if operation == Operation.OUTLIERS:
            # Discovery uses provider-neutral names; MCP silently ignoring these
            # would broaden the topic and mix formats in a paid response.
            for internal, external in (("query", "keyword"), ("videoFormat", "contentType")):
                if internal in args:
                    value = args.pop(internal)
                    if external in args and args[external] != value:
                        raise ProviderError("conflicting_parameters", not_sent=True)
                    args[external] = value
        if operation == Operation.CHANNEL_VIDEOS:
            args.setdefault("popular", False)
        self.calls += 1
        payload = await self.transport.call(f"vidiq_{operation.value}", args)
        try:
            return self.normalize(operation, args, payload, now)
        except (ValueError, KeyError, TypeError):
            raise ProviderError("contract_mismatch", may_have_charged=True) from None

    def normalize(
        self, operation: Operation, args: dict[str, Any], payload: dict[str, Any], now: datetime
    ) -> Batch:
        common: dict[str, Any] = {
            "provenance": Provenance(
                provider=self.name, operation=operation, auth_scope=self.auth_scope, fetched_at=now
            ),
            "costs": (
                Cost(
                    unit="vidiq_credit",
                    maximum=Decimal(0 if operation == Operation.BALANCE else 5),
                    actual=Decimal(0 if operation == Operation.BALANCE else 5),
                    source="MCP tools/list reviewed 2026-09-21; not a per-request charge receipt",
                ),
            ),
        }
        limitation = ("Provider response is a sample, not an exhaustive niche census.",)
        if operation == Operation.BALANCE:
            renewable = payload["renewableCredits"]
            additional = payload["addOnCredits"]
            if payload["type"] == "limited" and renewable + additional != payload["totalCredits"]:
                raise ValueError("inconsistent balance")
            return Batch(
                **common,
                balance=Balance(
                    renewable=renewable,
                    additional=additional,
                    recurring_allocation=payload["maxRenewableCredits"],
                    renews_at=_date(payload["renewableResetsAt"]),
                    unlimited=payload["type"] == "unlimited",
                ),
                coverage=Coverage(returned=1, complete=True, selection_method="account_balance"),
            )
        if operation == Operation.CHANNEL_SEARCH:
            channels = tuple(
                Channel(
                    id=row["channelId"],
                    title=row["channelTitle"],
                    description=row.get("description"),
                    subscribers=row.get("subscriberCount"),
                    country=row.get("country"),
                    content_languages=tuple(
                        x.strip() for x in (row.get("languages") or "").split(",") if x.strip()
                    ),
                    faceless=row.get("isFaceless"),
                    category=row.get("mainCategory"),
                    subtopics=tuple(row.get("subNiches") or []),
                    metrics={
                        key: Metric(
                            value=row.get(key),
                            unit="provider_unspecified_growth",
                            definition="Growth semantics require provider confirmation",
                        )
                        for key in ("subsGrowth30d", "viewsGrowth30d")
                    },
                )
                for row in payload["channels"]
            )
            return Batch(
                **common,
                channels=channels,
                coverage=Coverage(
                    returned=len(channels),
                    reported_total=payload.get("total"),
                    selection_method="search",
                    limitations=limitation,
                ),
            )
        if operation == Operation.KEYWORDS:
            rows = list(payload.get("relatedKeywords") or [])
            if payload.get("keyword"):
                rows.insert(
                    0, {key: value for key, value in payload.items() if key != "relatedKeywords"}
                )
            for key in ("questions", "matchingTerms", "risingKeywords"):
                rows.extend(payload.get(key) or [])
            return Batch(
                **common,
                keywords=tuple(rows),
                coverage=Coverage(
                    returned=len(rows), selection_method="keyword_metrics", limitations=limitation
                ),
            )
        videos = []
        for row in payload["videos"]:
            is_outlier = operation == Operation.OUTLIERS
            fmt = _format(row.get("videoType") if is_outlier else payload.get("videoFormat"))
            videos.append(
                Video(
                    id=row["videoId"],
                    channel_id=row["channelId"] if is_outlier else payload["channelId"],
                    title=row["videoTitle"] if is_outlier else row["title"],
                    published_at=_date(
                        row.get("videoPublishedAt") if is_outlier else row.get("publishedAt")
                    ),
                    views=row.get("viewCount"),
                    format=fmt,
                    format_evidence="provider response format"
                    if fmt != VideoFormat.UNKNOWN
                    else None,
                    # Search filters/title language are not verified audio language.
                    language=None,
                    subscriber_count=row.get("subscriberCount"),
                    category=row.get("mainCategory"),
                    duration_seconds=row.get("videoDuration") if is_outlier else None,
                    metrics={
                        "provider_breakout": Metric(
                            value=row.get("breakoutScore"),
                            unit="provider_score",
                            definition="vidIQ baseline; not NicheRadar baseline",
                        ),
                        "provider_vph": Metric(
                            value=row.get("vph"),
                            unit="views/hour",
                            definition="provider-reported current views per hour",
                        ),
                    },
                )
            )
        return Batch(
            **common,
            videos=tuple(videos),
            coverage=Coverage(
                returned=len(videos),
                selection_method="outliers"
                if operation == Operation.OUTLIERS
                else "popular"
                if args.get("popular")
                else "recent",
                limitations=(*limitation, "No pagination or full-window coverage guaranteed."),
            ),
        )
