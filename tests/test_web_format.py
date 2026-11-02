# tests/test_web_format.py
import pytest

from nicheradar.web.format import compact, es_int, local_datetime, usd_range


@pytest.mark.parametrize(
    ("value", "text"), [(0, "0"), (999.4, "999"), (1629.23, "1.629"), (1234567.8, "1.234.568")]
)
def test_es_int_uses_dots_for_thousands(value: float, text: str) -> None:
    assert es_int(value) == text


def test_usd_range_rounds_and_handles_missing_values() -> None:
    assert usd_range("672.80", "1681.99") == "US$ 673 – 1.682"
    assert usd_range(None, "10") is None and usd_range("10", None) is None


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, "—"), (987, "987"), (39600, "39,6 mil"), (5580483, "5,6 M"), (14600000, "14,6 M")],
)
def test_compact_abbreviates_counts_in_spanish(value: float | None, text: str) -> None:
    assert compact(value) == text


def test_local_datetime_converts_to_the_configured_timezone() -> None:
    assert local_datetime("2026-10-31T12:00:00Z", "America/Lima") == "31/10/2026 07:00"
    assert local_datetime("2026-10-31T12:00:00+00:00", "UTC") == "31/10/2026 12:00"
