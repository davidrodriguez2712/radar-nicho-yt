# src/nicheradar/web/pilots_form.py
"""M4: validation of the authorize form and the budget the server derives from the report."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from nicheradar.web.format import money_amount

CHANNEL_RE = re.compile(r"^canal-[a-z0-9-]{1,40}$")
PILOT_ID_RE = re.compile(r"^pil_[0-9]{8}_[a-z0-9-]{1,40}$")  # pilots/contracts.py PILOT_ID
CLOSED = ("cerrado", "cancelado")
MAX_MONEY = Decimal("1000000")
CENT = Decimal("0.01")
RANGES = {
    "max_videos": (1, 50, "1 a 50"),
    "valid_days": (1, 60, "1 a 60"),
    "close_after": (1, 5, "1 a 5"),
}
CHANNEL_ERROR = "Usa el formato canal-nombre"
GATE_MESSAGES = {
    "channel_busy": "Ese canal ya tiene un piloto activo.",
    "no_go_requires_acceptance": (
        "El informe recomienda no-go: marca la casilla para aceptarlo bajo tu responsabilidad."
    ),
    "dossier_not_ready": "El informe todavía no está listo.",
    "language_unknown": (
        "El informe no tiene un idioma conocido: inicia una investigación nueva con idioma."
    ),
    "niche_mismatch": "El informe no corresponde a ese nicho.",
    "gate_failed": "El informe no pasa una compuerta: revisa los motivos.",
    "bad_transition": "El piloto que reemplazas ya no se puede reemplazar.",
}


@dataclass(frozen=True)
class Defaults:
    max_videos: int = 10
    valid_days: int = 14
    close_after: int = 2


def busy_channels(pilots: list[dict[str, Any]]) -> set[str]:
    return {
        channel
        for pilot in pilots
        if isinstance(channel := pilot.get("target_channel"), str)
        and pilot.get("status") not in CLOSED
    }


def parse_form(data: Mapping[str, str]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field, (low, high, hint) in RANGES.items():
        raw = data.get(field, "").strip()
        # isascii: str.isdigit also accepts digits int() could misread (e.g. superscripts).
        # len cap: int() raises on thousands of digits, and no valid value has more than 2.
        if len(raw) <= 3 and raw.isascii() and raw.isdigit() and low <= int(raw) <= high:
            values[field] = int(raw)
        else:
            errors[field] = hint
    channel = data.get("canal", "").strip()
    if not channel:
        values["canal"] = None
    elif CHANNEL_RE.fullmatch(channel):
        values["canal"] = channel
    else:
        errors["canal"] = CHANNEL_ERROR
    return (None, errors) if errors else (values, errors)


def _money(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    try:
        number = number.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # astronomical values do not fit the cent precision
        return None
    return number if 0 <= number <= MAX_MONEY else None


def budget_body(dossier: dict[str, Any], max_videos: int, informe_id: str) -> dict[str, Any] | None:
    """The `budget` of the authorize body, or None if the dossier has no usable totals."""
    budget = dossier.get("budget")
    totals = budget.get("totals") if isinstance(budget, dict) else None
    if not isinstance(totals, dict):
        return None
    low, likely, high = (_money(totals.get(key)) for key in ("low", "likely", "high"))
    if low is None or likely is None or high is None:
        return None
    likely = max(low, likely)  # rounding can invert a near tie: keep low <= likely <= high
    high = max(likely, high)
    return {
        "currency": "USD",
        "low": float(low),
        "likely": float(likely),
        "high": float(high),
        "max_videos": max_videos,
        "basis": f"Presupuesto del informe {informe_id}: probable {money_amount(float(likely))}.",
    }
