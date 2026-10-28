"""Validate the model's document entry by entry (contract §5, V1-V12).

The strict output schema cannot carry patterns or length limits, so the model sometimes writes a
country name instead of `US` or an undated period. One such entry must not discard the other
entries of the same listing: each malformed entry is dropped and recorded in `unresolved`. The
blocks everything else depends on (`images`, `identity_check`, `monetization`) and unknown keys
still reject the whole document.
"""

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from nicheradar.market_intel.evidence.contracts import (
    Audience,
    Claim,
    Earning,
    ModelEvidence,
    Period,
    Rate,
    TopContent,
    TrafficSource,
    Unresolved,
    ViewMetric,
)

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_UNRESOLVED_CAP = 20
# Block name -> (entry model, `unresolved.topic` for a dropped entry).
_LISTS: dict[str, tuple[type[BaseModel], str | None]] = {
    "claims": (Claim, None),
    "earnings": (Earning, "revenue"),
    "views": (ViewMetric, "views"),
    "rates": (Rate, "rpm"),
    "top_content": (TopContent, "revenue"),
    "traffic_sources": (TrafficSource, "audience"),
}


def _concerns_period(error: ValidationError) -> bool:
    return any("period" in item["loc"] for item in error.errors())


def _gap(topic: str, reason: str, entry: Any, note: str | None = None) -> Unresolved:
    index = entry.get("image_index") if isinstance(entry, dict) else None
    return Unresolved(
        topic=topic,  # type: ignore[arg-type]
        reason=reason,  # type: ignore[arg-type]
        image_index=index if isinstance(index, int) and index >= 0 else None,
        note=note,
    )


def _why(entry: Any, error: ValidationError) -> str:
    """Short, content-free reason: the period kind and missing dates, or the first failing field."""
    period = entry.get("period") if isinstance(entry, dict) else None
    if _concerns_period(error) and isinstance(period, dict):
        dates = [name for name in ("start", "end") if not period.get(name)]
        missing = "no dates" if len(dates) == 2 else f"missing {dates[0]}" if dates else "bad dates"
        return f"period {period.get('kind')}: {missing}"[:200]
    first = error.errors()[0]
    return f"invalid {'.'.join(str(part) for part in first['loc'])}: {first['type']}"[:200]


def _language(images: Any, index: Any) -> str | None:
    for image in images if isinstance(images, list) else []:
        if isinstance(image, dict) and image.get("index") == index:
            language = image.get("ui_language")
            return language.strip().lower() if isinstance(language, str) else None
    return None


def _currency(code: Any, language: str | None) -> tuple[str | None, str]:
    """(currency, status): `ok`, `assumed` (bare `$` on an English interface) or `unresolved`."""
    if code is None:
        return None, "ok"
    text = str(code).strip()
    if _CURRENCY.match(text):
        return text, "ok"
    if text == "US$":
        return "USD", "ok"
    if (
        text == "$"
        and language is not None
        and (language == "english" or language.startswith("en"))
    ):
        return "USD", "assumed"
    return None, "unresolved"


def _resolve_currencies(doc: dict[str, Any], gaps: list[Unresolved]) -> tuple[int, ...]:
    """Decision D9: read a bare `$` as USD only when the capture's interface is in English."""
    images, assumed = doc.get("images"), set()
    kept = []
    for entry in doc.get("earnings") or []:
        money = entry.get("amount") if isinstance(entry, dict) else None
        if not isinstance(money, dict):
            kept.append(entry)
            continue
        language = _language(images, entry.get("image_index"))
        currency, status = _currency(money.get("currency"), language)
        if status == "unresolved" and money.get("currency") is not None:
            note = f"currency {str(money['currency'])[:10]!r} with ui_language {language!r}"
            gaps.append(_gap("revenue", "ambiguous_currency", entry, note))
            continue
        if status == "assumed":
            assumed.add(entry.get("image_index"))
        kept.append({**entry, "amount": {**money, "currency": currency}})
    if isinstance(doc.get("earnings"), list):
        doc["earnings"] = kept
    for name, key in (("rates", None), ("top_content", "revenue")):
        entries = doc.get(name)
        if not isinstance(entries, list):
            continue
        fixed = []
        for entry in entries:
            if not isinstance(entry, dict):
                fixed.append(entry)
                continue
            language = _language(images, entry.get("image_index"))
            target = entry.get(key) if key else entry
            if isinstance(target, dict) and target.get("currency") is not None:
                currency, status = _currency(target.get("currency"), language)
                if status == "assumed":
                    assumed.add(entry.get("image_index"))
                if key is None:
                    entry = {**entry, "currency": currency}
                elif currency is None:
                    entry = {**entry, "revenue": None}
                else:
                    entry = {**entry, "revenue": {**target, "currency": currency}}
            fixed.append(entry)
        doc[name] = fixed
    return tuple(sorted(i for i in assumed if isinstance(i, int)))


def tolerant_evidence(data: dict[str, Any]) -> ModelEvidence:
    doc = dict(data)
    doc.pop("usd_symbol_images", None)  # code-owned: whatever the model sent is ignored
    gaps: list[Unresolved] = []
    usd_symbol_images = _resolve_currencies(doc, gaps)
    images = doc.get("images")
    if isinstance(images, list):
        doc["images"] = [
            {**image, "currency_visible": None}
            if isinstance(image, dict)
            and image.get("currency_visible") is not None
            and not _CURRENCY.match(str(image["currency_visible"]))
            else image
            for image in images
        ]
    for name, (model, topic) in _LISTS.items():
        entries = doc.get(name)
        if not isinstance(entries, list):
            continue
        kept = []
        for entry in entries:
            try:
                kept.append(model.model_validate(entry))
            except ValidationError as error:
                if topic is not None:
                    reason = "ambiguous_period" if _concerns_period(error) else "unreadable"
                    gaps.append(_gap(topic, reason, entry, _why(entry, error)))
        doc[name] = kept
    audience = doc.get("audience")
    if isinstance(audience, dict):
        doc["audience"], more = _audience(audience)
        gaps.extend(more)
    evidence = ModelEvidence.model_validate({**doc, "usd_symbol_images": usd_symbol_images})
    if not gaps:
        return evidence
    room = max(0, _UNRESOLVED_CAP - len(evidence.unresolved))
    return evidence.model_copy(update={"unresolved": (*evidence.unresolved, *gaps[:room])})


def _audience(audience: dict[str, Any]) -> tuple[dict[str, Any], list[Unresolved]]:
    gaps: list[Unresolved] = []
    fixed = dict(audience)
    countries = fixed.get("countries")
    if isinstance(countries, list):
        valid = [c for c in countries if isinstance(c, dict) and _COUNTRY.match(str(c.get("code")))]
        if len(valid) != len(countries):
            gaps.append(_gap("audience", "unreadable", audience))
        fixed["countries"] = valid
    period = fixed.get("period")
    if isinstance(period, dict):
        try:
            Period.model_validate(period)
        except ValidationError:
            fixed["period"] = None
            gaps.append(_gap("audience", "ambiguous_period", audience))
    try:
        Audience.model_validate(fixed)
    except ValidationError:
        gaps.append(_gap("audience", "unreadable", audience))
        return None, gaps  # type: ignore[return-value]
    return fixed, gaps
