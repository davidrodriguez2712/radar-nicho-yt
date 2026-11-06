"""Lectura de un tweet con la API oficial de X (de pago por uso, ≈ US$0,005 por post leído).

El Bearer token es una credencial de pago: viaja solo en la cabecera `Authorization`, se saca de un
`SecretStr` en el momento de la llamada y nunca entra en URL, excepciones, `repr` ni mensajes.
Los errores son códigos fijos; nada del texto del proveedor sale de aquí. Sin reintentos.
"""

import json
from typing import Any

import httpx
from pydantic import SecretStr

from nicheradar.integrations import tweets
from nicheradar.integrations.tweets import (
    _AUTHOR,
    _ID,
    _MEDIA,
    MAX_JSON_BYTES,
    MAX_PHOTOS,
    MAX_TEXT,
    MEDIA_HOST,
    BoundedReader,
    Tweet,
    TweetReadError,
    TweetRef,
    _clean_text,
)

X_API_HOST = "api.x.com"
_UNAVAILABLE_PROBLEMS = (
    "resource-not-found",
    "not-authorized-for-resource",
    "resource-unavailable",
)
_STATUS_CODES = {
    401: "reader_unauthorized",
    403: "reader_unauthorized",
    404: "tweet_unavailable",
    402: "reader_credits_depleted",
    429: "reader_rate_limited",
}


def _photo_urls(media: object, attached: object) -> tuple[str, ...]:
    raw_keys = attached.get("media_keys") if isinstance(attached, dict) else None
    keys: list[Any] = raw_keys if isinstance(raw_keys, list) else []
    urls: dict[str, None] = {}
    for item in media if isinstance(media, list) else []:
        if not isinstance(item, dict) or item.get("type") != "photo":
            continue
        if item.get("media_key") not in keys:
            continue
        url = item.get("url")
        match = _MEDIA.fullmatch(url) if isinstance(url, str) else None
        if match is not None:
            urls[f"https://{MEDIA_HOST}/media/{match.group(1)}.{match.group(2)}?name=large"] = None
    return tuple(urls)[:MAX_PHOTOS]


def _problems_unavailable(errors: object) -> bool:
    """Solo clasifica; ningún texto del proveedor se conserva."""
    for item in errors if isinstance(errors, list) else []:
        kind = item.get("type") if isinstance(item, dict) else None
        if isinstance(kind, str) and any(name in kind for name in _UNAVAILABLE_PROBLEMS):
            return True
    return False


class XApiReader(BoundedReader):
    def __init__(
        self, token: SecretStr | None, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(transport=transport)
        self._token = token

    def __repr__(self) -> str:
        return f"XApiReader(token_configured={self._token is not None})"

    __str__ = __repr__

    async def read(self, ref: TweetRef) -> Tweet:
        secret = self._token.get_secret_value() if self._token is not None else ""
        if not secret:
            raise TweetReadError("reader_not_configured")  # sin llamar a nadie ni gastar
        if not _ID.fullmatch(ref.tweet_id) or (
            ref.author is not None and not _AUTHOR.fullmatch(ref.author)
        ):
            raise TweetReadError("reader_failed")
        # X cobra por recurso devuelto: expandir el autor suma un recurso User (US$0,010). Solo se
        # pide cuando la URL no trae el autor (`/i/status/<id>`).
        params = {
            "tweet.fields": "text,note_tweet,entities,attachments",
            "expansions": "attachments.media_keys",
            "media.fields": "type,url,width,height",
        }
        if ref.author is None:
            params["tweet.fields"] += ",author_id"
            params["expansions"] += ",author_id"
            params["user.fields"] = "username"
        url = httpx.URL(
            scheme="https", host=X_API_HOST, path=f"/2/tweets/{ref.tweet_id}", params=params
        )
        status, content_type, raw = await self._bounded(
            url,
            MAX_JSON_BYTES,
            "reader_failed",
            "reader_failed",
            tweets.TOTAL_JSON_TIMEOUT_SECONDS,
            {"Authorization": f"Bearer {secret}"},
        )
        if status == 403 and content_type.split(";")[0].strip().lower() == "text/html":
            raise TweetReadError("reader_blocked")  # Cloudflare, no la API de X
        if status in _STATUS_CODES:
            raise TweetReadError(_STATUS_CODES[status])
        if status != 200 or content_type.split(";")[0].strip().lower() != "application/json":
            raise TweetReadError("reader_failed")
        try:
            payload: Any = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("unexpected body")
            data: Any = payload.get("data")
            if data is None and _problems_unavailable(payload.get("errors")):
                raise TweetReadError("tweet_unavailable")
            includes = payload.get("includes")
            includes = includes if isinstance(includes, dict) else {}
            text = data["text"]
            note = data.get("note_tweet")
            long_text = note.get("text") if isinstance(note, dict) else None
            if isinstance(long_text, str) and long_text:
                text = long_text
            author = (
                ref.author
                if ref.author is not None
                else next(
                    user["username"]
                    for user in includes["users"]
                    if isinstance(user, dict) and user.get("id") == data.get("author_id")
                )
            )
            if (
                str(data["id"]) != ref.tweet_id
                or not isinstance(text, str)
                or not isinstance(author, str)
                or not _AUTHOR.fullmatch(author)
            ):
                raise ValueError("unexpected tweet")
        except TweetReadError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, StopIteration):
            raise TweetReadError("reader_failed") from None
        return Tweet(
            author,
            ref.tweet_id,
            _clean_text(text)[:MAX_TEXT],
            _photo_urls(includes.get("media"), data.get("attachments")),
        )
