"""V12: the literal text the model read must reproduce the number it reported."""

import re
from decimal import Decimal, InvalidOperation

from nicheradar.market_intel.evidence.contracts import (
    Earning,
    ModelEvidence,
    Unresolved,
    ViewMetric,
)

_SUFFIX = {"K": Decimal(1_000), "M": Decimal(1_000_000), "B": Decimal(1_000_000_000)}
_NUMBER = re.compile(r"(\d[\d.,\s]*)\s*([KMB])?\b", re.IGNORECASE)


def parse_raw_number(raw: str) -> tuple[Decimal, Decimal] | None:
    """Return (value, tolerance) read from a literal like "$1,276.14", "69.7K" or "1.2M"."""
    found = _NUMBER.search(raw.replace("\u00a0", " "))
    if found is None:
        return None
    digits = found.group(1).strip().replace(" ", "")
    suffix = found.group(2).upper() if found.group(2) else None
    last_dot, last_comma = digits.rfind("."), digits.rfind(",")
    decimals = 0
    decimal_mark: str | None
    if last_dot >= 0 and last_comma >= 0:
        decimal_mark = "." if last_dot > last_comma else ","
    elif last_dot >= 0 or last_comma >= 0:
        mark = "." if last_dot >= 0 else ","
        mark_tail = digits[digits.rfind(mark) + 1 :]
        # "1,276" is thousands; "1,27" or "69.7" is a decimal mark.
        decimal_mark = mark if (len(mark_tail) != 3 or suffix) and digits.count(mark) == 1 else None
    else:
        decimal_mark = None
    if decimal_mark:
        whole, _, tail = digits.rpartition(decimal_mark)
        decimals = len(tail)
        cleaned = re.sub(r"[.,]", "", whole) + "." + tail
    else:
        cleaned = re.sub(r"[.,]", "", digits)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    multiplier = _SUFFIX[suffix] if suffix else Decimal(1)
    tolerance = Decimal(5) / (Decimal(10) ** (decimals + 1)) * multiplier
    negative = any(mark in raw[: found.start()] for mark in "-\u2212\u2013")
    return (-value if negative else value) * multiplier, tolerance


def raw_text_matches(raw: str, value: Decimal | float) -> bool:
    parsed = parse_raw_number(raw)
    if parsed is None:
        return False
    number, tolerance = parsed
    return abs(number - Decimal(str(value))) <= tolerance


def drop_unverifiable_entries(evidence: ModelEvidence) -> ModelEvidence:
    """Keep only earnings and view metrics whose `raw_text` reproduces their value.

    Dropped entries move to `unresolved` (`unreadable`); the document itself is not rejected.
    """
    kept_earnings: list[Earning] = []
    kept_views: list[ViewMetric] = []
    dropped: list[Unresolved] = []
    for earning in evidence.earnings:
        if raw_text_matches(earning.raw_text, earning.amount.value):
            kept_earnings.append(earning)
        else:
            dropped.append(
                Unresolved(topic="revenue", reason="unreadable", image_index=earning.image_index)
            )
    for metric in evidence.views:
        if raw_text_matches(metric.raw_text, metric.value):
            kept_views.append(metric)
        else:
            dropped.append(
                Unresolved(topic="views", reason="unreadable", image_index=metric.image_index)
            )
    if not dropped:
        return evidence
    return evidence.model_copy(
        update={
            "earnings": tuple(kept_earnings),
            "views": tuple(kept_views),
            "unresolved": (*evidence.unresolved, *dropped),
        }
    )
