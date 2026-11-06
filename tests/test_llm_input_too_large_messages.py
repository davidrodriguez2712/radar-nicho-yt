# tests/test_llm_input_too_large_messages.py
"""`llm_input_too_large` (propuesta y lectura de tweets) tiene un texto fijo propio en cada mapa."""

from nicheradar.lead_api import LEAD_MESSAGES, lead_error
from nicheradar.subniche_api import MESSAGES, error_message
from nicheradar.web.client import CODE_MESSAGES
from nicheradar.web.leads import error_text

CODE = "llm_input_too_large"


def test_every_map_knows_the_code_with_its_own_text() -> None:
    assert MESSAGES[CODE] == CODE_MESSAGES[CODE]
    assert LEAD_MESSAGES[CODE] == error_text(CODE)
    for text in (MESSAGES[CODE], LEAD_MESSAGES[CODE]):
        assert "demasiado grande" in text
    assert MESSAGES[CODE] != MESSAGES["llm_failed"]
    assert LEAD_MESSAGES[CODE] != LEAD_MESSAGES["llm_failed"]


def test_the_error_helpers_return_the_code_not_unknown() -> None:
    assert error_message(CODE) == {"code": CODE, "message": MESSAGES[CODE]}
    assert lead_error(CODE) == {"code": CODE, "message": LEAD_MESSAGES[CODE]}


def test_web_text_is_not_the_generic_one() -> None:
    assert error_text(CODE) != error_text("no_existe")


NEW_READER_CODES = (
    "reader_not_configured",
    "reader_unauthorized",
    "reader_rate_limited",
    "reader_credits_depleted",
    "reader_blocked",
)


def test_reader_codes_have_mirrored_fixed_texts() -> None:
    for code in NEW_READER_CODES:
        assert LEAD_MESSAGES[code] == error_text(code) != error_text(None)
        assert lead_error(code) == {"code": code, "message": LEAD_MESSAGES[code]}
        assert "borrado" not in LEAD_MESSAGES[code]
    assert LEAD_MESSAGES["reader_not_configured"] == (
        "La lectura con la API de X no está configurada en el servidor."
    )
    assert LEAD_MESSAGES["reader_blocked"] == (
        "El servicio de lectura rechazó la solicitud desde el servidor."
    )


def test_help_does_not_blame_only_the_tweet() -> None:
    from pathlib import Path

    html = Path("src/nicheradar/web/templates/lecturas/_lectura.html").read_text()
    assert "el servicio de lectura del servidor no puede leerlo" in html
    assert "ya no existe o el servicio de lectura falla" not in html
