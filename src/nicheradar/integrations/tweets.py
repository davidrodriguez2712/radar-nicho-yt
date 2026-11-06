"""Lectura acotada de un tweet público vía FxTwitter (gratuito) y de sus fotos de X.

La lectura con la API oficial de X vive en `x_api.py` y comparte `BoundedReader`.

Anti-SSRF: solo dos hosts fijos, rutas construidas por código, sin seguir redirecciones, sin
variables de entorno de proxy y con cuerpos acotados. Todo lo que devuelve es de terceros.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

FX_HOST = "api.fxtwitter.com"
MEDIA_HOST = "pbs.twimg.com"
MAX_JSON_BYTES = 262_144
MAX_IMAGE_BYTES = 5_242_880
MAX_PHOTOS = 4
MAX_TEXT = 1000
TIMEOUT_SECONDS = 10
TOTAL_JSON_TIMEOUT_SECONDS = 20
TOTAL_PHOTO_TIMEOUT_SECONDS = 30
MIN_JPEG_BYTES = 100
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")
X_HOSTS = frozenset(
    {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
)
_AUTHOR = re.compile(r"[A-Za-z0-9_]{1,15}")
_ID = re.compile(r"[1-9][0-9]{0,19}")
_PATH = re.compile(
    r"/(?:i(?:/web)?|(?P<author>[A-Za-z0-9_]{1,15}))/status/(?P<id>[1-9][0-9]{0,19})(?:/[A-Za-z0-9_-]{1,30}){0,3}/?"
)
_URL_IN_TEXT = re.compile(r"https://[^\s<>\"']{1,490}")
_MEDIA = re.compile(
    r"https://pbs\.twimg\.com/media/([A-Za-z0-9_-]{5,40})\.(jpg|jpeg|png|webp)(?:\?[A-Za-z0-9=&_.-]{0,60})?"
)
_CANONICAL_MEDIA = re.compile(
    r"https://pbs\.twimg\.com/media/[A-Za-z0-9_-]{5,40}\.(?:jpg|jpeg|png|webp)\?name=large"
)


class TweetReadError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TweetRef:
    author: str | None
    tweet_id: str

    @property
    def api_path(self) -> str:
        return f"/{self.author or 'i'}/status/{self.tweet_id}"

    @property
    def canonical_url(self) -> str:
        return f"https://x.com{self.api_path}"


@dataclass(frozen=True)
class Tweet:
    author: str
    tweet_id: str
    text: str
    photo_urls: tuple[str, ...]


@dataclass(frozen=True)
class ImageData:
    media_type: str
    data: bytes


class TweetReader(Protocol):
    async def read(self, ref: TweetRef) -> Tweet: ...

    async def photo(self, url: str) -> ImageData: ...


def parse_tweet_url(raw: str) -> TweetRef | None:
    """El primer enlace https del texto, solo si es un tweet de x.com/twitter.com."""
    if len(raw) > 500:
        return None
    found = _URL_IN_TEXT.search(raw.strip())
    if found is None:
        return None
    try:
        parts = urlsplit(found.group(0))
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or (parts.hostname or "") not in X_HOSTS or port is not None:
        return None
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return None
    match = _PATH.fullmatch(parts.path)
    if match is None:
        return None
    return TweetRef(match.group("author"), match.group("id"))


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # JPEG: marcador SOI+0xFF, un byte de marcador real (>= 0xC0) y al menos MIN_JPEG_BYTES;
    # descarta políglotas como `\xff\xd8\xff<script>`. Es una regla mínima, no un decodificador.
    if data.startswith(b"\xff\xd8\xff") and len(data) >= MIN_JPEG_BYTES and data[3] >= 0xC0:
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _photo_urls(media: object) -> tuple[str, ...]:
    photos = media.get("photos") if isinstance(media, dict) else None
    urls: dict[str, None] = {}
    for item in photos if isinstance(photos, list) else []:
        url = item.get("url") if isinstance(item, dict) else None
        match = _MEDIA.fullmatch(url) if isinstance(url, str) else None
        if match is not None:
            urls[f"https://{MEDIA_HOST}/media/{match.group(1)}.{match.group(2)}?name=large"] = None
    return tuple(urls)[:MAX_PHOTOS]


def _clean_text(text: str) -> str:
    """Sin NUL (Postgres lo rechaza) ni surrogates sueltos (psycopg no los codifica)."""
    return text.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")


class BoundedReader:
    """Descarga acotada y fotos de X: lo común de los lectores (FxTwitter y API oficial)."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        )

    async def _bounded(
        self,
        url: httpx.URL,
        limit: int,
        error: str,
        too_large: str,
        total: float,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, str, bytes]:
        headers = {**(extra_headers or {}), "Accept-Encoding": "identity"}
        try:
            async with asyncio.timeout(total):
                async with (
                    self._client() as client,
                    client.stream("GET", url, headers=headers) as response,
                ):
                    encoding = response.headers.get("content-encoding", "identity")
                    if encoding.strip().lower() not in ("", "identity"):
                        raise TweetReadError(error)
                    declared = response.headers.get("content-length", "")
                    if declared.isascii() and declared.isdigit() and int(declared) > limit:
                        raise TweetReadError(too_large)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > limit:
                            raise TweetReadError(too_large)
                    content_type = response.headers.get("content-type", "")
                    return response.status_code, content_type, bytes(raw)
        except (httpx.HTTPError, TimeoutError):
            raise TweetReadError(error) from None

    async def photo(self, url: str) -> ImageData:
        if not _CANONICAL_MEDIA.fullmatch(url):
            raise TweetReadError("photo_failed")
        status, _, raw = await self._bounded(
            httpx.URL(url),
            MAX_IMAGE_BYTES,
            "photo_failed",
            "photo_too_large",
            TOTAL_PHOTO_TIMEOUT_SECONDS,
        )
        if status != 200:
            raise TweetReadError("photo_failed")
        media_type = sniff_image_type(raw)
        if media_type is None:
            raise TweetReadError("photo_invalid")
        return ImageData(media_type, raw)


class FxTwitterReader(BoundedReader):
    async def read(self, ref: TweetRef) -> Tweet:
        if not _ID.fullmatch(ref.tweet_id) or (
            ref.author is not None and not _AUTHOR.fullmatch(ref.author)
        ):
            raise TweetReadError("reader_failed")
        url = httpx.URL(scheme="https", host=FX_HOST, path=ref.api_path)
        status, content_type, raw = await self._bounded(
            url, MAX_JSON_BYTES, "reader_failed", "reader_failed", TOTAL_JSON_TIMEOUT_SECONDS
        )
        if status == 403:  # Cloudflare rechaza la IP del servidor: no es culpa del tweet
            raise TweetReadError("reader_blocked")
        if status in (401, 404):
            raise TweetReadError("tweet_unavailable")
        if status != 200 or content_type.split(";")[0].strip().lower() != "application/json":
            raise TweetReadError("reader_failed")
        try:
            payload: Any = json.loads(raw)
            tweet = payload["tweet"]
            author = tweet["author"]["screen_name"]
            text = tweet["text"]
            if (
                payload.get("code") != 200
                or str(tweet["id"]) != ref.tweet_id
                or not isinstance(text, str)
                or not isinstance(author, str)
                or not _AUTHOR.fullmatch(author)
            ):
                raise ValueError("unexpected tweet")
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise TweetReadError("reader_failed") from None
        return Tweet(
            author, ref.tweet_id, _clean_text(text)[:MAX_TEXT], _photo_urls(tweet.get("media"))
        )
