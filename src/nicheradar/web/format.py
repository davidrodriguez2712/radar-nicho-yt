# src/nicheradar/web/format.py
"""Spanish number, money and date formatting for the mobile web."""

from datetime import datetime
from zoneinfo import ZoneInfo


def es_int(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def usd_range(low: str | None, high: str | None) -> str | None:
    if low is None or high is None:
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
