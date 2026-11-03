# src/nicheradar/web/format.py
"""Spanish number, money and date formatting for the mobile web."""

import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
MONTHS_SHORT = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def zone(name: str) -> ZoneInfo:
    """The IANA zone, or UTC when the name is unknown or malformed: a date never breaks a page."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def es_int(value: float) -> str:
    """Whole number with '.' thousands; NaN and infinity (a malformed API) read as missing."""
    if not math.isfinite(value):
        return "—"
    return f"{round(value):,}".replace(",", ".")


def usd_range(low: str | None, high: str | None) -> str | None:
    if low is None or high is None:
        return None
    if not (math.isfinite(float(low)) and math.isfinite(float(high))):
        return None
    return f"US$ {es_int(float(low))} – {es_int(float(high))}"


def compact(value: float | int | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    number = float(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}".replace(".", ",") + " M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}".replace(".", ",") + " mil"
    return es_int(number)


def parse_utc(value: str) -> datetime:
    """An ISO moment as an aware datetime; one without a zone is taken as UTC."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def local_datetime(value: str, timezone: str) -> str:
    return parse_utc(value).astimezone(zone(timezone)).strftime("%d/%m/%Y %H:%M")


def usd(value: float | str | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    return f"US$ {es_int(float(value))}"


MAX_MONEY = 1e9


def money_amount(value: object) -> str:
    """One money format for a single amount: US$ with a Spanish decimal comma.

    A whole amount has no decimals ("US$ 41"); under 100 it keeps two ("US$ 0,96"); from 100 up it
    rounds to a whole number. Negative, non-finite, non-numeric or absurdly large read as "—".
    A numeric string (the API sends some amounts as strings) counts as its number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return "—"
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return "—"
    if not math.isfinite(number) or number < 0 or number > MAX_MONEY:
        return "—"
    if number >= 100 or number == int(number):
        return f"US$ {es_int(number)}"
    return "US$ " + f"{number:.2f}".replace(".", ",")


def pct(value: float | None) -> str:
    return "—" if value is None or not math.isfinite(value) else f"{round(value)}%"


def spanish_date(moment: datetime, timezone: str) -> str:
    """'Domingo 1 de noviembre' in the given timezone; a naive moment is taken as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone("UTC"))
    local = moment.astimezone(zone(timezone))
    return f"{DAYS[local.weekday()]} {local.day} de {MONTHS[local.month - 1]}"


def short_date(moment: datetime, timezone: str) -> str:
    """'8 nov' in the given timezone; a naive moment is taken as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone(zone(timezone))
    return f"{local.day} {MONTHS_SHORT[local.month - 1]}"
