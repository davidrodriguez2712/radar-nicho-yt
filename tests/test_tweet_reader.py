import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from nicheradar.integrations.tweets import (
    MAX_IMAGE_BYTES,
    FxTwitterReader,
    TweetReadError,
    TweetRef,
    parse_tweet_url,
    sniff_image_type,
)
from tests.lead_samples import GIF, JPEG, PNG, TWEET_ID, WEBP, fx_payload

PHOTO = "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg?name=orig"


@pytest.mark.parametrize(
    ("raw", "author", "tweet_id"),
    [
        ("https://x.com/autor_x/status/123?s=20", "autor_x", "123"),
        ("https://twitter.com/autor_x/status/123", "autor_x", "123"),
        ("https://mobile.twitter.com/autor_x/status/123/photo/1", "autor_x", "123"),
        ("https://www.x.com/autor_x/status/123", "autor_x", "123"),
        ("https://x.com/i/status/123", None, "123"),
        ("https://x.com/i/web/status/123", None, "123"),
        ("  mira esto https://x.com/autor_x/status/123 ", "autor_x", "123"),
    ],
)
def test_parse_tweet_url_accepts_x_forms(raw: str, author: str | None, tweet_id: str) -> None:
    assert parse_tweet_url(raw) == TweetRef(author, tweet_id)


@pytest.mark.parametrize(
    "raw",
    [
        "https://notx.com/a/status/1",
        "https://x.com.evil.test/a/status/1",
        "https://fxtwitter.com/a/status/1",
        "https://x.com/a/status/12a",
        "https://x.com/a/status/" + "1" * 21,
        "https://x.com/nombre_demasiado_largo_x/status/1",
        "javascript:alert(1)//x.com/a/status/1",
        "http://x.com/a/status/1",
        "https://x.com/a/status/",
        "x" * 600,
        "",
    ],
)
def test_parse_tweet_url_refuses_everything_else(raw: str) -> None:
    assert parse_tweet_url(raw) is None


def test_ref_builds_fixed_paths() -> None:
    assert TweetRef("autor_x", "123").api_path == "/autor_x/status/123"
    assert TweetRef(None, "123").api_path == "/i/status/123"
    assert TweetRef(None, "123").canonical_url == "https://x.com/i/status/123"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (WEBP, "image/webp"),
        (GIF, None),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", None),
        (b"", None),
        (b"\x89PN", None),
    ],
)
def test_sniff_image_type_uses_magic_bytes(data: bytes, expected: str | None) -> None:
    assert sniff_image_type(data) == expected


def reader(handler) -> FxTwitterReader:  # type: ignore[no-untyped-def]
    return FxTwitterReader(transport=httpx.MockTransport(handler))


def json_response(body: object, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )


def test_read_calls_only_the_fixed_host_and_path() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return json_response(fx_payload(photos=(PHOTO,)))

    tweet = asyncio.run(reader(handler).read(TweetRef("autor_x", TWEET_ID)))
    assert [str(url) for url in seen] == [f"https://api.fxtwitter.com/autor_x/status/{TWEET_ID}"]
    assert tweet.author == "autor_x" and tweet.tweet_id == TWEET_ID
    assert tweet.text.startswith("Mira")
    assert tweet.photo_urls == ("https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg?name=large",)


def test_read_keeps_at_most_four_x_photos_and_drops_other_domains() -> None:
    photos = (
        "https://evil.test/media/a.jpg",
        "https://pbs.twimg.com/profile_images/1/a.jpg",
        *(f"https://pbs.twimg.com/media/foto{n}.png" for n in range(6)),
    )
    tweet = asyncio.run(
        reader(lambda r: json_response(fx_payload(photos=photos))).read(
            TweetRef("autor_x", TWEET_ID)
        )
    )
    assert len(tweet.photo_urls) == 4
    assert all(url.startswith("https://pbs.twimg.com/media/foto") for url in tweet.photo_urls)


def test_read_truncates_the_text_and_takes_the_author_from_the_reply() -> None:
    body = fx_payload(text="a" * 5000, author="otro_autor")
    tweet = asyncio.run(reader(lambda r: json_response(body)).read(TweetRef(None, TWEET_ID)))
    assert len(tweet.text) == 1000 and tweet.author == "otro_autor"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            json_response({"code": 404, "message": "NOT_FOUND", "tweet": None}, 404),
            "tweet_unavailable",
        ),
        (
            json_response({"code": 401, "message": "PRIVATE_TWEET", "tweet": None}, 401),
            "tweet_unavailable",
        ),
        (
            httpx.Response(
                200, content=b"<!DOCTYPE html><html></html>", headers={"content-type": "text/html"}
            ),
            "reader_failed",
        ),
        (httpx.Response(302, headers={"location": "https://evil.test/"}), "reader_failed"),
        (httpx.Response(500), "reader_failed"),
        (json_response(["no es un objeto"]), "reader_failed"),
        (json_response(fx_payload(tweet_id="999")), "reader_failed"),
        (json_response(fx_payload(author="autor con espacios")), "reader_failed"),
        (
            httpx.Response(
                200,
                content=b"{" + b" " * 300_000 + b"}",
                headers={"content-type": "application/json"},
            ),
            "reader_failed",
        ),
    ],
)
def test_read_failures_are_fixed_codes(response: httpx.Response, code: str) -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: response).read(TweetRef("autor_x", TWEET_ID)))
    assert caught.value.code == code


def test_network_failure_is_reader_failed() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("lento", request=request)

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(boom).read(TweetRef("autor_x", TWEET_ID)))
    assert caught.value.code == "reader_failed"


def test_read_refuses_a_ref_that_was_not_validated() -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: pytest.fail("no request")).read(TweetRef("a/../b", "1")))
    assert caught.value.code == "reader_failed"


def test_photo_downloads_bounded_and_sniffs_the_type() -> None:
    url = "https://pbs.twimg.com/media/foto1.png?name=large"
    image = asyncio.run(reader(lambda r: httpx.Response(200, content=PNG)).photo(url))
    assert (image.media_type, image.data) == ("image/png", PNG)


@pytest.mark.parametrize(
    ("url", "response", "code"),
    [
        ("https://evil.test/media/a.png", httpx.Response(200, content=PNG), "photo_failed"),
        (
            "https://pbs.twimg.com/media/a1234.png?name=large",
            httpx.Response(200, content=b"x" * (MAX_IMAGE_BYTES + 1)),
            "photo_too_large",
        ),
        (
            "https://pbs.twimg.com/media/a1234.png?name=large",
            httpx.Response(200, content=PNG, headers={"content-length": str(MAX_IMAGE_BYTES + 1)}),
            "photo_too_large",
        ),
        (
            "https://pbs.twimg.com/media/a1234.png?name=large",
            httpx.Response(200, content=GIF),
            "photo_invalid",
        ),
        (
            "https://pbs.twimg.com/media/a1234.png?name=large",
            httpx.Response(301, headers={"location": "https://evil.test/a.png"}),
            "photo_failed",
        ),
    ],
)
def test_photo_failures_are_fixed_codes(url: str, response: httpx.Response, code: str) -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: response).photo(url))
    assert caught.value.code == code


# --- Casos hostiles añadidos ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "https://user@x.com/a/status/1",
        "https://user:pw@x.com/a/status/1",
        "https://x.com@evil.test/a/status/1",
        "https://x.com:8443/a/status/1",
        "https://x.com:443/a/status/1",
        "https://x.com:abc/a/status/1",
        "https://xn--x-9ma.com/a/status/1",
        "https://х.com/a/status/1",
        "https://x.com/a/status/000",
        "https://x.com/a/status/0123",
        "https://x.com/a/status/１２３",
        "https://x.com/ñandú/status/1",
        "https://x.com/a/status/1/../../x",
        "https://t.co/abcdef",
        "https://x.com//a/status/1",
        "https://x.com/i/web/status/",
    ],
)
def test_parse_tweet_url_refuses_hostile_hosts_and_ids(raw: str) -> None:
    assert parse_tweet_url(raw) is None


def test_parse_tweet_url_accepts_the_largest_id() -> None:
    assert parse_tweet_url("https://x.com/a/status/" + "9" * 20) == TweetRef("a", "9" * 20)


def test_read_normalises_web_status_to_the_fixed_i_path() -> None:
    ref = parse_tweet_url("https://x.com/i/web/status/" + TWEET_ID)
    assert ref is not None and ref.api_path == f"/i/status/{TWEET_ID}"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return json_response(fx_payload())

    asyncio.run(reader(handler).read(ref))
    assert seen == [f"https://api.fxtwitter.com/i/status/{TWEET_ID}"]


@pytest.mark.parametrize(
    "ref",
    [
        TweetRef("a", "0" * 21),
        TweetRef("a", "12a"),
        TweetRef("a", "１２３"),
        TweetRef("a", "1\n"),
        TweetRef("a", ""),
        TweetRef("ñandú", "1"),
        TweetRef("a" * 16, "1"),
        TweetRef("a?x=1", "1"),
        TweetRef("a#b", "1"),
        TweetRef("a@evil.test", "1"),
        TweetRef("", "1"),
    ],
)
def test_read_refuses_malformed_refs_without_any_request(ref: TweetRef) -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: pytest.fail("no request")).read(ref))
    assert caught.value.code == "reader_failed"


def test_read_does_not_follow_redirects_to_another_host() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(307, headers={"location": "https://evil.test/x"})

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).read(TweetRef("autor_x", TWEET_ID)))
    assert caught.value.code == "reader_failed" and hosts == ["api.fxtwitter.com"]


def test_json_limit_is_exact_and_declared_length_is_checked() -> None:
    from nicheradar.integrations.tweets import MAX_JSON_BYTES

    body = json.dumps(fx_payload()).encode()
    exact = body[:-1] + b" " * (MAX_JSON_BYTES - len(body)) + b"}"
    assert len(exact) == MAX_JSON_BYTES
    headers = {"content-type": "application/json"}
    ok = asyncio.run(
        reader(lambda r: httpx.Response(200, content=exact, headers=headers)).read(
            TweetRef("autor_x", TWEET_ID)
        )
    )
    assert ok.tweet_id == TWEET_ID
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(
            reader(lambda r: httpx.Response(200, content=exact + b" ", headers=headers)).read(
                TweetRef("autor_x", TWEET_ID)
            )
        )
    assert caught.value.code == "reader_failed"
    lying = {**headers, "content-length": str(MAX_JSON_BYTES + 1)}
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(
            reader(lambda r: httpx.Response(200, content=b"{}", headers=lying)).read(
                TweetRef("autor_x", TWEET_ID)
            )
        )
    assert caught.value.code == "reader_failed"


def test_a_huge_chunked_body_is_cut_off_without_reading_everything() -> None:
    pulled = 0

    async def endless() -> AsyncIterator[bytes]:
        nonlocal pulled
        while True:
            pulled += 1
            yield b"x" * 65_536

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=endless(), headers={"content-type": "application/json"})

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).read(TweetRef("autor_x", TWEET_ID)))
    assert caught.value.code == "reader_failed" and pulled <= 6


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"",
        b"null",
        b"\xff\xfe\x00",
        b"[" * 200_000,
        b'{"code":200,"tweet":null}',
        b'{"code":200,"tweet":{"id":"%s","text":1,"author":{"screen_name":"a"}}}'
        % TWEET_ID.encode(),
        b'{"code":200,"tweet":{"id":"%s","text":"x","author":{"screen_name":5}}}'
        % TWEET_ID.encode(),
        b'{"code":200,"tweet":{"id":"%s","text":"x","author":null}}' % TWEET_ID.encode(),
        b'{"code":"200","tweet":{"id":"%s","text":"x","author":{"screen_name":"a"}}}'
        % TWEET_ID.encode(),
        b'{"code":200,"tweet":{"id":%s,"text":"x","author":{"screen_name":"a\\n"}}}'
        % TWEET_ID.encode(),
    ],
)
def test_malformed_json_is_reader_failed(body: bytes) -> None:
    headers = {"content-type": "application/json"}
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(
            reader(lambda r: httpx.Response(200, content=body, headers=headers)).read(
                TweetRef("autor_x", TWEET_ID)
            )
        )
    assert caught.value.code == "reader_failed"


def test_json_with_charset_and_numeric_id_is_accepted() -> None:
    body = fx_payload()
    body["tweet"]["id"] = int(TWEET_ID)
    response = httpx.Response(
        200,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json; charset=utf-8"},
    )
    assert (
        asyncio.run(reader(lambda r: response).read(TweetRef("autor_x", TWEET_ID))).tweet_id
        == TWEET_ID
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://pbs.twimg.com.evil.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://evilpbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://user@pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com@evil.test/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com:8443/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com:443/media/BhxWutnCEAAtEQ6.jpg",
        "http://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "//pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.gif",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.svg",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg.html",
        "https://pbs.twimg.com/media/../x/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg#frag",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg?name=orig",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg?name=large&x=1",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg?name=large\n",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg ?name=large",
        "https://pbs.twimg.com/profile_images/BhxWutnCEAAtEQ6.jpg?name=large",
        "https://pbs.twimg.com/media/ñandúñandú.jpg?name=large",
        "https://pbs.twimg.com/media/%2e%2e.jpg?name=large",
        "https://xn--pbs-twimg-xxx.com/media/BhxWutnCEAAtEQ6.jpg?name=large",
        "https://t.co/abcdef",
        "",
    ],
)
def test_photo_refuses_look_alike_urls_before_any_request(url: str) -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: pytest.fail("no request")).photo(url))
    assert caught.value.code == "photo_failed"


@pytest.mark.parametrize(
    "url",
    [
        "https://pbs.twimg.com.evil.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://evilpbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://user@pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com:8443/media/BhxWutnCEAAtEQ6.jpg",
        "http://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg",
        "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.gif",
        "https://xn--pbs-twimg-xxx.com/media/BhxWutnCEAAtEQ6.jpg",
    ],
)
def test_read_drops_look_alike_photo_urls(url: str) -> None:
    ok = "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.jpg"
    tweet = asyncio.run(
        reader(lambda r: json_response(fx_payload(photos=(url, ok)))).read(
            TweetRef("autor_x", TWEET_ID)
        )
    )
    assert tweet.photo_urls == (f"{ok}?name=large",)


def test_read_deduplicates_photos_and_ignores_bad_media_shapes() -> None:
    url = "https://pbs.twimg.com/media/BhxWutnCEAAtEQ6.png"
    body = fx_payload(photos=(url, url))
    assert (
        len(
            asyncio.run(
                reader(lambda r: json_response(body)).read(TweetRef("autor_x", TWEET_ID))
            ).photo_urls
        )
        == 1
    )
    medias: tuple[Any, ...] = (None, [], "x", {"photos": "x"}, {"photos": [1, None, {"url": 5}]})
    for media in medias:
        shaped = fx_payload()
        shaped["tweet"]["media"] = media
        assert (
            asyncio.run(
                reader(lambda r, b=shaped: json_response(b)).read(TweetRef("autor_x", TWEET_ID))
            ).photo_urls
            == ()
        )


def test_photo_size_limit_is_exact_at_the_edge() -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    exact = PNG + b"\x00" * (MAX_IMAGE_BYTES - len(PNG))
    assert len(exact) == MAX_IMAGE_BYTES
    image = asyncio.run(reader(lambda r: httpx.Response(200, content=exact)).photo(url))
    assert len(image.data) == MAX_IMAGE_BYTES and image.media_type == "image/png"
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: httpx.Response(200, content=exact + b"\x00")).photo(url))
    assert caught.value.code == "photo_too_large"
    declared = httpx.Response(200, content=PNG, headers={"content-length": str(MAX_IMAGE_BYTES)})
    assert asyncio.run(reader(lambda r: declared).photo(url)).media_type == "image/png"


def test_photo_huge_stream_is_cut_off() -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    pulled = 0

    async def endless() -> AsyncIterator[bytes]:
        nonlocal pulled
        while True:
            pulled += 1
            yield PNG + b"\x00" * 1_048_576

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: httpx.Response(200, content=endless())).photo(url))
    assert caught.value.code == "photo_too_large" and pulled <= 7


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a" + b"\x00" * 20,
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"<html>" + PNG,
        b" " + PNG,
        b"\x89PNG\r\n\x1a",
        b"\xff\xd8",
        b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 20,
        b"RIFF\x24\x00\x00\x00WEB",
        b"%PDF-1.7",
        b"",
    ],
)
def test_photo_rejects_fake_magic_bytes(data: bytes) -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: httpx.Response(200, content=data)).photo(url))
    assert caught.value.code == "photo_invalid"


def test_photo_ignores_the_declared_content_type() -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    liar = httpx.Response(200, content=GIF, headers={"content-type": "image/png"})
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: liar).photo(url))
    assert caught.value.code == "photo_invalid"
    truth = httpx.Response(200, content=WEBP, headers={"content-type": "text/plain"})
    assert asyncio.run(reader(lambda r: truth).photo(url)).media_type == "image/webp"


@pytest.mark.parametrize("status", [403, 404, 500, 204])
def test_photo_non_200_is_photo_failed(status: int) -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(lambda r: httpx.Response(status, content=PNG)).photo(url))
    assert caught.value.code == "photo_failed"


def test_photo_network_failure_and_fixed_host_only() -> None:
    url = "https://pbs.twimg.com/media/a1234.png?name=large"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader(handler).photo(url))
    assert caught.value.code == "photo_failed" and seen == [url]


def test_error_messages_never_leak_provider_text() -> None:
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(
            reader(
                lambda r: json_response({"code": 404, "message": "secreto-del-proveedor"}, 404)
            ).read(TweetRef("autor_x", TWEET_ID))
        )
    assert "secreto" not in str(caught.value) and str(caught.value) == "tweet_unavailable"


def test_the_client_never_trusts_the_environment_nor_follows_redirects() -> None:
    client = FxTwitterReader()._client()
    assert client.follow_redirects is False and client.trust_env is False
    assert client.timeout.read == 10
