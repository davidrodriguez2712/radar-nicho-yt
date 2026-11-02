# src/nicheradar/web/format.py
"""Spanish number, money and date formatting for the mobile web."""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

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
    if value is None:
        return "—"
    number = float(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}".replace(".", ",") + " M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}".replace(".", ",") + " mil"
    return es_int(number)


def local_datetime(value: str, timezone: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(timezone))
    return moment.strftime("%d/%m/%Y %H:%M")


def usd(value: float | str | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    return f"US$ {es_int(float(value))}"


def pct(value: float | None) -> str:
    return "—" if value is None or not math.isfinite(value) else f"{round(value)}%"


def spanish_date(moment: datetime, timezone: str) -> str:
    """'Domingo 1 de noviembre' in the given timezone; a naive moment is taken as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("UTC"))
    local = moment.astimezone(ZoneInfo(timezone))
    return f"{DAYS[local.weekday()]} {local.day} de {MONTHS[local.month - 1]}"
