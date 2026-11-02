# tests/test_web_format.py
from datetime import UTC, datetime, timedelta

import pytest

from nicheradar.web.format import (
    compact,
    es_int,
    local_datetime,
    pct,
    spanish_date,
    usd,
    usd_range,
)


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


def test_usd_and_pct_format_for_spanish_readers() -> None:
    assert usd(1234.4) == "US$ 1.234"
    assert usd("19.0") == "US$ 19"
    assert usd(None) == "—"
    assert pct(80.0) == "80%"
    assert pct(66.6) == "67%"
    assert pct(None) == "—"


def test_spanish_date_names_the_weekday_and_month_in_the_local_timezone() -> None:
    moment = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)  # Sunday evening in Lima
    assert spanish_date(moment, "America/Lima") == "Domingo 1 de noviembre"
    assert spanish_date(moment, "UTC") == "Lunes 2 de noviembre"


def test_spanish_date_covers_the_seven_weekdays() -> None:
    start = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)  # a Monday
    days = [spanish_date(start + timedelta(days=i), "UTC") for i in range(7)]
    assert days == [
        "Lunes 2 de noviembre",
        "Martes 3 de noviembre",
        "Miércoles 4 de noviembre",
        "Jueves 5 de noviembre",
        "Viernes 6 de noviembre",
        "Sábado 7 de noviembre",
        "Domingo 8 de noviembre",
    ]


def test_spanish_date_handles_the_year_boundaries_and_every_month_name() -> None:
    assert (
        spanish_date(datetime(2026, 12, 31, 12, 0, tzinfo=UTC), "UTC") == "Jueves 31 de diciembre"
    )
    assert spanish_date(datetime(2027, 1, 1, 12, 0, tzinfo=UTC), "UTC") == "Viernes 1 de enero"
    # 03:00 UTC on New Year's Day is still New Year's Eve in Lima.
    assert (
        spanish_date(datetime(2027, 1, 1, 3, 0, tzinfo=UTC), "America/Lima")
        == "Jueves 31 de diciembre"
    )
    names = [
        spanish_date(datetime(2026, m, 15, 12, 0, tzinfo=UTC), "UTC").split(" de ")[1]
        for m in range(1, 13)
    ]
    assert names == [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]  # fmt: skip
