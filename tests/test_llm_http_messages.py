"""Los códigos `llm_http_*` del adaptador tienen texto fijo propio en cada mapa, sin texto ajeno."""

import pytest

from nicheradar.lead_api import LEAD_MESSAGES, lead_error
from nicheradar.llm_codes import normalize_llm_code
from nicheradar.subniche_api import MESSAGES, error_message
from nicheradar.web.client import CODE_MESSAGES, ApiError
from nicheradar.web.leads import error_text

CATEGORIES = ("llm_rejected", "llm_auth", "llm_permission", "llm_rate_limited")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("llm_http_400_invalid_request_error", "llm_rejected"),
        ("llm_http_400", "llm_rejected"),
        ("llm_http_404_not_found_error", "llm_rejected"),
        ("llm_http_413_request_too_large", "llm_rejected"),
        ("llm_http_422", "llm_rejected"),
        ("llm_http_401_authentication_error", "llm_auth"),
        ("llm_http_401", "llm_auth"),
        ("llm_http_403_permission_error", "llm_permission"),
        ("llm_http_402_billing_error", "llm_permission"),
        ("llm_http_429_rate_limit_error", "llm_rate_limited"),
        ("llm_http_500_api_error", "llm_failed"),
        ("llm_http_529_overloaded_error", "llm_failed"),
        ("llm_http_418", "llm_failed"),
    ],
)
def test_http_codes_are_grouped_into_fixed_categories(code: str, expected: str) -> None:
    assert normalize_llm_code(code) == expected


@pytest.mark.parametrize(
    "code",
    ["llm_failed", "invalid_response", "llm_http_", "llm_http_abc", "llm_http_400_<script>", "x"],
)
def test_other_codes_are_left_untouched(code: str) -> None:
    assert normalize_llm_code(code) == code


def test_every_map_has_a_clear_text_per_category_and_they_mirror() -> None:
    for code in CATEGORIES:
        assert MESSAGES[code] == CODE_MESSAGES[code]
        assert LEAD_MESSAGES[code] == error_text(code)
        assert error_text(code) != error_text(None)
        assert MESSAGES[code] != MESSAGES["llm_failed"]
        assert LEAD_MESSAGES[code] != LEAD_MESSAGES["llm_failed"]
    assert MESSAGES["llm_rejected"] == (
        "El modelo de lenguaje rechazó la solicitud. "
        "Revisa la configuración del modelo y el saldo de la cuenta de Anthropic."
    )


def test_the_api_helpers_turn_a_raw_http_code_into_the_category_text() -> None:
    raw = "llm_http_400_invalid_request_error"
    assert error_message(raw) == {"code": "llm_rejected", "message": MESSAGES["llm_rejected"]}
    assert lead_error(raw) == {"code": "llm_rejected", "message": LEAD_MESSAGES["llm_rejected"]}
    unavailable = error_message("llm_http_529_overloaded_error")
    assert unavailable == {"code": "llm_failed", "message": MESSAGES["llm_failed"]}
    assert lead_error("llm_http_500") == {
        "code": "llm_failed",
        "message": LEAD_MESSAGES["llm_failed"],
    }


def test_unknown_llm_http_codes_get_the_generic_text() -> None:
    assert error_message("llm_http_<b>") == {
        "code": "unknown",
        "message": "No se pudo preparar la propuesta.",
    }
    unknown = lead_error("llm_http_<b>")
    assert unknown is not None and unknown["code"] == "unknown"


def test_the_web_client_shows_its_own_text_for_a_category() -> None:
    error = ApiError("conflict", 409, {"code": "llm_rejected", "message": "texto ajeno"})
    assert error.message == CODE_MESSAGES["llm_rejected"]
