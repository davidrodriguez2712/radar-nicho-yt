import pytest
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.integrations.tweets import FxTwitterReader
from nicheradar.integrations.x_api import XApiReader
from nicheradar.subniche_discovery.lead_worker import make_tweet_reader

TOKEN = "SENTINEL-bearer-9f3c1d7a-do-not-leak"


def test_defaults_are_fxtwitter_and_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NR_TWEET_READER", raising=False)
    monkeypatch.delenv("NR_X_API_BEARER_TOKEN", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.tweet_reader == "fxtwitter" and settings.x_api_bearer_token is None
    assert isinstance(make_tweet_reader(settings), FxTwitterReader)


def test_xapi_with_token_selects_xapi() -> None:
    reader = make_tweet_reader(Settings(tweet_reader="xapi", x_api_bearer_token=SecretStr(TOKEN)))
    assert isinstance(reader, XApiReader)


def test_xapi_without_token_is_typed_error_and_never_calls() -> None:
    import asyncio

    from nicheradar.integrations.tweets import TweetReadError, TweetRef

    reader = make_tweet_reader(Settings(tweet_reader="xapi"))
    with pytest.raises(TweetReadError) as caught:
        asyncio.run(reader.read(TweetRef("a", "1")))
    assert caught.value.code == "reader_not_configured"


def test_token_never_appears_in_settings_repr_or_public_status() -> None:
    settings = Settings(tweet_reader="xapi", x_api_bearer_token=SecretStr(TOKEN))
    for shown in (
        repr(settings),
        str(settings),
        str(settings.public_status()),
        settings.model_dump_json(),
    ):
        assert TOKEN not in shown


def test_invalid_reader_value_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(tweet_reader="otro")  # type: ignore[arg-type]
