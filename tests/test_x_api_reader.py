import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.integrations.tweets import Tweet, TweetReadError, TweetRef
from nicheradar.integrations.x_api import XApiReader
from tests.lead_samples import PNG, TWEET_ID

TOKEN = "SENTINEL-bearer-9f3c1d7a-do-not-leak"
REF = TweetRef("autor_x", TWEET_ID)
NO_AUTHOR = TweetRef(None, TWEET_ID)
MEDIA = "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg"


def payload(
    text: str = "Mira https://www.youtube.com/@historia_uno",
    photos: tuple[str, ...] = (),
    username: str | None = "autor_x",
    note: str | None = None,
    tweet_id: str = TWEET_ID,
) -> dict[str, Any]:
    data: dict[str, Any] = {"id": tweet_id, "text": text, "author_id": "77"}
    media = [
        {"media_key": f"3_{n}", "type": "photo", "url": url, "width": 1, "height": 1}
        for n, url in enumerate(photos)
    ]
    if media:
        data["attachments"] = {"media_keys": [m["media_key"] for m in media]}
    if note is not None:
        data["note_tweet"] = {"text": note}
    includes: dict[str, Any] = {"media": media}
    if username is not None:
        includes["users"] = [{"id": "77", "username": username, "name": "Autor"}]
    return {"data": data, "includes": includes}


def jr(body: object, status: int = 200, ctype: str = "application/json") -> httpx.Response:
    return httpx.Response(
        status, content=json.dumps(body).encode(), headers={"content-type": ctype}
    )


def reader(handler: Any, token: str | None = TOKEN) -> XApiReader:
    secret = SecretStr(token) if token is not None else None
    return XApiReader(secret, transport=httpx.MockTransport(handler))


def read(handler: Any) -> Tweet:
    return asyncio.run(reader(handler).read(REF))


def code_of(handler: Any, ref: TweetRef = REF) -> str:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).read(ref))
    return caught.value.code


def test_request_with_author_in_url_does_not_expand_the_author() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return jr(payload(photos=(MEDIA,), username=None))

    tweet = read(handler)
    (request,) = seen
    assert request.url.scheme == "https" and request.url.host == "api.x.com"
    assert request.url.path == f"/2/tweets/{TWEET_ID}"
    params = dict(request.url.params)
    assert params["expansions"] == "attachments.media_keys"
    assert "author_id" not in str(request.url) and "user.fields" not in params
    assert "note_tweet" in params["tweet.fields"]
    assert params["media.fields"] == "type,url,width,height"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["accept-encoding"] == "identity"
    assert TOKEN not in str(request.url)
    assert tweet == Tweet("autor_x", TWEET_ID, tweet.text, (MEDIA + "?name=large",))


def test_request_without_author_expands_the_author_and_reads_it() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return jr(payload(username="otro_autor"))

    tweet = asyncio.run(reader(handler).read(NO_AUTHOR))
    params = dict(seen[0].url.params)
    assert params["expansions"] == "attachments.media_keys,author_id"
    assert params["user.fields"] == "username" and "author_id" in params["tweet.fields"]
    assert tweet.author == "otro_autor"


def test_author_from_the_url_is_used_even_if_the_reply_names_another() -> None:
    assert read(lambda r: jr(payload(username="otro_autor"))).author == "autor_x"


def test_long_text_prefers_note_tweet_and_is_truncated_and_cleaned() -> None:
    tweet = read(lambda r: jr(payload(text="corto…", note="largo\x00" + "a" * 5000)))
    assert tweet.text.startswith("largo") and len(tweet.text) == 1000 and "\x00" not in tweet.text


def test_no_photos_and_several_photos_deduplicated_and_capped() -> None:
    assert read(lambda r: jr(payload())).photo_urls == ()
    urls = tuple(f"https://pbs.twimg.com/media/foto{n}.png" for n in range(6))
    tweet = read(lambda r: jr(payload(photos=(urls[0], *urls))))
    assert tweet.photo_urls == tuple(f"{u}?name=large" for u in urls[:4])


def test_other_hosts_and_non_photos_are_dropped() -> None:
    body = payload(photos=("https://evil.test/media/a.jpg", MEDIA))
    body["includes"]["media"].append(
        {"media_key": "7_1", "type": "video", "url": "https://pbs.twimg.com/media/video1.jpg"}
    )
    body["includes"]["media"].append({"media_key": "9", "type": "photo", "url": 5})
    assert read(lambda r: jr(body)).photo_urls == (MEDIA + "?name=large",)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "reader_unauthorized"),
        (403, "reader_unauthorized"),
        (404, "tweet_unavailable"),
        (429, "reader_rate_limited"),
        (402, "reader_credits_depleted"),
        (500, "reader_failed"),
        (503, "reader_failed"),
        (204, "reader_failed"),
        (302, "reader_failed"),
    ],
)
def test_status_codes_map_to_fixed_codes(status: int, code: str) -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return jr({"title": "secreto-del-proveedor", "detail": TOKEN}, status)

    assert code_of(handler) == code
    assert len(seen) == 1  # sin reintentos


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            {"errors": [{"type": "https://api.twitter.com/2/problems/resource-not-found"}]},
            "tweet_unavailable",
        ),
        (
            {
                "errors": [
                    {"type": "https://api.twitter.com/2/problems/not-authorized-for-resource"}
                ]
            },
            "tweet_unavailable",
        ),
        ({"errors": [{"title": "Authorization Error", "type": "about:blank"}]}, "reader_failed"),
        ({"errors": "raro"}, "reader_failed"),
        ({}, "reader_failed"),
        ({"data": None}, "reader_failed"),
        ({"data": []}, "reader_failed"),
        ({"data": {"id": TWEET_ID}}, "reader_failed"),
        ({"data": {"id": TWEET_ID, "text": 5}}, "reader_failed"),
        (
            {"data": {"id": "999", "text": "x"}, "includes": {"users": [{"username": "a"}]}},
            "reader_failed",
        ),
        (payload(username=None), "reader_failed"),
        (payload(username="autor con espacios"), "reader_failed"),
        (payload(tweet_id="999"), "reader_failed"),
        (
            {"data": {"id": TWEET_ID, "text": "x", "author_id": "77"}, "includes": {"users": "no"}},
            "reader_failed",
        ),
        (["no es objeto"], "reader_failed"),
    ],
)
def test_hostile_or_error_bodies(body: object, code: str) -> None:
    assert code_of(lambda r: jr(body), NO_AUTHOR) == code


def test_403_with_html_is_blocked_but_json_403_and_401_are_unauthorized() -> None:
    html = httpx.Response(403, content=b"<html>cf</html>", headers={"content-type": "text/html"})
    assert code_of(lambda r: html) == "reader_blocked"
    assert code_of(lambda r: jr({"title": "Forbidden"}, 403)) == "reader_unauthorized"
    assert (
        code_of(
            lambda r: httpx.Response(401, content=b"<html/>", headers={"content-type": "text/html"})
        )
        == "reader_unauthorized"
    )


def test_deep_json_and_huge_body_and_wrong_content_type() -> None:
    deep = httpx.Response(
        200, content=b"[" * 100_000 + b"]" * 100_000, headers={"content-type": "application/json"}
    )
    assert code_of(lambda r: deep) == "reader_failed"
    huge = httpx.Response(
        200, content=b"{" + b" " * 300_000 + b"}", headers={"content-type": "application/json"}
    )
    assert code_of(lambda r: huge) == "reader_failed"
    assert code_of(lambda r: jr(payload(), ctype="text/html")) == "reader_failed"


def test_json_content_type_with_charset_is_accepted() -> None:
    assert (
        read(lambda r: jr(payload(), ctype="application/json; charset=utf-8")).author == "autor_x"
    )


def test_invalid_ids_do_not_call_the_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debe llamar")

    for ref in (TweetRef("autor_x", "0123"), TweetRef("autor_x", "1/../2"), TweetRef("a b", "1")):
        assert code_of(handler, ref) == "reader_failed"


def test_missing_token_calls_nobody() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debe llamar")

    for token in (None, ""):
        with pytest.raises(TweetReadError) as caught:
            asyncio.run(reader(handler, token).read(REF))
        assert caught.value.code == "reader_not_configured"


def test_redirects_are_not_followed() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://evil.test/"})

    assert code_of(handler) == "reader_failed" and seen == ["api.x.com"]


def test_token_never_leaks() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"fallo con {TOKEN}", request=request)

    instance = reader(boom)
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(instance.read(REF))
    error = caught.value
    assert error.code == "reader_failed" and error.__cause__ is None and error.__context__ is None
    for shown in (str(error), repr(error), repr(instance), str(instance), repr(vars(instance))):
        assert TOKEN not in shown
    assert TOKEN not in repr(error.args)


def test_photo_download_does_not_send_the_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=PNG)

    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    image = asyncio.run(reader(handler).photo(url))
    assert image.media_type == "image/png"
    assert "authorization" not in seen[0].headers and TOKEN not in str(seen[0].url)
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).photo("https://api.x.com/2/tweets/1"))
    assert caught.value.code == "photo_failed" and len(seen) == 1


def test_read_has_a_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicheradar.integrations import tweets

    async def drip() -> AsyncIterator[bytes]:
        for _ in range(1000):
            await asyncio.sleep(0.05)
            yield b" "

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=drip(), headers={"content-type": "application/json"})

    monkeypatch.setattr(tweets, "TOTAL_JSON_TIMEOUT_SECONDS", 0.2)
    started = time.monotonic()
    assert code_of(handler) == "reader_failed" and time.monotonic() - started < 3


def _chain(error: BaseException | None) -> list[BaseException]:
    found: list[BaseException] = []
    while error is not None and error not in found:
        found.append(error)
        error = error.__cause__ or error.__context__
    return found


@pytest.mark.parametrize("kind", ["connect", "timeout", "redirect"])
def test_no_exception_chain_reaches_the_token(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "connect":
            raise httpx.ConnectError("x", request=request)
        if kind == "timeout":
            raise httpx.ReadTimeout("x", request=request)
        return httpx.Response(302, headers={"location": "https://evil.test/"})

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).read(REF))
    assert _chain(caught.value) == [caught.value]
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    with pytest.raises(TweetReadError) as photo:
        asyncio.run(reader(handler).photo("https://pbs.twimg.com/media/a1234.png?name=large"))
    assert photo.value.__context__ is None and photo.value.__cause__ is None
