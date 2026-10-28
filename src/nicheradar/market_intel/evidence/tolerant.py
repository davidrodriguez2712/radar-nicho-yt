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


def _gap(topic: str, reason: str, entry: Any) -> Unresolved:
    index = entry.get("image_index") if isinstance(entry, dict) else None
    return Unresolved(
        topic=topic,  # type: ignore[arg-type]
        reason=reason,  # type: ignore[arg-type]
        image_index=index if isinstance(index, int) and index >= 0 else None,
    )


def tolerant_evidence(data: dict[str, Any]) -> ModelEvidence:
    doc = dict(data)
    gaps: list[Unresolved] = []
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
                    gaps.append(_gap(topic, reason, entry))
        doc[name] = kept
    audience = doc.get("audience")
    if isinstance(audience, dict):
        doc["audience"], more = _audience(audience)
        gaps.extend(more)
    evidence = ModelEvidence.model_validate(doc)
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
