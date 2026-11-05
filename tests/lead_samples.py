"""Muestras compartidas para la lectura de tweets e imágenes."""

from typing import Any

from nicheradar.integrations.tweets import ImageData, Tweet, TweetReadError, TweetRef

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
GIF = b"GIF89a" + b"\x00" * 32
TWEET_ID = "1850000000000000000"


def fx_payload(
    text: str = "Mira https://www.youtube.com/@historia_uno",
    photos: tuple[str, ...] = (),
    author: str = "autor_x",
    tweet_id: str = TWEET_ID,
) -> dict[str, Any]:
    return {
        "code": 200,
        "message": "OK",
        "tweet": {
            "id": tweet_id,
            "text": text,
            "author": {"screen_name": author, "name": "Autor"},
            "media": {"photos": [{"type": "photo", "url": url} for url in photos]},
        },
    }


class FakeTweetReader:
    """`TweetReader` guionizado: un tweet o un código de error, y fotos por URL."""

    def __init__(
        self,
        tweet: Tweet | None = None,
        error: str | None = None,
        photos: dict[str, ImageData] | None = None,
    ) -> None:
        self.tweet, self.error, self.photos = tweet, error, photos or {}
        self.reads: list[TweetRef] = []
        self.photo_calls: list[str] = []

    async def read(self, ref: TweetRef) -> Tweet:
        self.reads.append(ref)
        if self.error is not None or self.tweet is None:
            raise TweetReadError(self.error or "tweet_unavailable")
        return self.tweet

    async def photo(self, url: str) -> ImageData:
        self.photo_calls.append(url)
        if url not in self.photos:
            raise TweetReadError("photo_failed")
        return self.photos[url]
