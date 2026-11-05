# src/nicheradar/web/niche_detail.py
"""View model of the niche detail (M19): read-only, built from `GET /market/niches/{label}`."""

import math
from dataclasses import replace
from typing import Any

from nicheradar.web.format import compact, es_int, money_amount
from nicheradar.web.journey import niche_journey
from nicheradar.web.niches import DECISION_CHIP, RESEARCH_CHIP, investigate_href
from nicheradar.web.pilots_view import CLOSED
from nicheradar.web.research import language_options, valid_id

UNREADABLE = "unreadable"  # sentinel: the source could not be read (not "there is none")
MAX_LISTINGS = 100
PAGE = 10
NOTICE = (
    "Las cifras salen de fichas de canales en venta y las declaran los vendedores: "
    "no son ingresos verificados."
)
RESEARCH_DOWN = "No se pudo leer el estado de la investigación"
PILOTS_DOWN = "No se pudo leer el estado de los pilotos: el recorrido puede estar incompleto."
HOW = (
    "Opportunity: Rentabilidad 30 · Eficiencia 30 · Validación 25 · Dinámica 15.",
    "Automatización: Sin rostro 30 · Guionable 25 · Visuales automatizables 20 · "
    "Voz sintética aceptable 15 · Baja dependencia de derechos 10, más riesgo de política.",
)
HOW_NOTE = "Un puntaje necesita al menos 3 fichas con ingreso; sin eso se muestra «sin evidencia»."
VERIFICATION = {
    "verified": ("verificado", "green"),
    "mismatch": ("no coincide", "amber"),
    "not_found": ("canal no encontrado", "neutral"),
    "unverifiable": ("no verificable", "neutral"),
}
UNVERIFIED = ("sin verificar", "neutral")
CONFIDENCE = ("alta", "media", "baja")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _count(value: object) -> str:
    number = _number(value)
    return "—" if number is None else es_int(number)


def _score(block: object) -> str:
    number = _number(_dict(block).get("value"))
    return "sin evidencia" if number is None else es_int(number)


def trend_text(value: object) -> str:
    number = _number(value)
    if number is None:
        return "sin dato"
    return "sube" if number > 0 else "baja" if number < 0 else "estable"


def _subs(value: float) -> str:
    return compact(value).replace(",0 ", " ")  # "120,0 mil" reads "120 mil"


def _ratio(value: object) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.1f}".replace(".", ",") + "×"


def _per_month(value: object) -> str:
    text = money_amount(value)
    return text if text == "—" else text + " al mes"


def _language_text(mix: object) -> str:
    view = language_options(mix)  # type: ignore[arg-type]
    parts = [f"{o['name']} {o['share']} %" for o in view["options"]]
    if view["unknown_share"] is not None:
        parts.append(f"Sin dato {view['unknown_share']} %")
    return " · ".join(parts) or "sin dato"


def latest_research(items: object, label: str, fmt: str) -> dict[str, Any] | None:
    """The API lists newest first: the first order of this niche and format wins."""
    if not isinstance(items, list):
        return None
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("niche_label") == label
            and item.get("format") == fmt
        ):
            return item
    return None


def open_pilot(items: object, label: str, fmt: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("niche_label") == label
            and item.get("format") == fmt
            and item.get("status") not in CLOSED
        ):
            return item
    return None


def _listing(raw: object) -> dict[str, Any]:
    item = _dict(raw)
    title = item.get("title")
    status = "Activa" if item.get("status") == "active" else "Desapareció"
    verification = item.get("verification")
    chip_text, chip_kind = (
        VERIFICATION.get(verification, UNVERIFIED) if isinstance(verification, str) else UNVERIFIED
    )
    declared = _number(item.get("subscribers"))
    real = _number(item.get("real_subscribers"))
    first = [status, money_amount(item.get("price_usd"))]
    if declared is not None:
        first.append(f"{_subs(declared)} suscriptores declarados")
    if real is not None:
        first.append(f"{_subs(real)} en YouTube")
    second = []
    if money_amount(item.get("income_monthly_usd")) != "—":
        second.append("Ingreso declarado " + _per_month(item.get("income_monthly_usd")))
    if money_amount(item.get("expense_monthly_usd")) != "—":
        second.append("gasto declarado " + _per_month(item.get("expense_monthly_usd")))
    url = item.get("url")
    return {
        "title": title if isinstance(title, str) and title else "Ficha sin título",
        "line1": " · ".join(p for p in first if p != "—"),
        "line2": " · ".join(second),
        "chip_text": chip_text,
        "chip_kind": chip_kind,
        "url": url if isinstance(url, str) and url.startswith("https://") else None,
    }


def _research_card(niche: dict[str, Any], research: object, fmt: str) -> dict[str, Any]:
    label = niche.get("niche_label")
    if research == UNREADABLE:
        return {"status": RESEARCH_DOWN, "action": None}
    order = _dict(research)
    status = order.get("status")
    status = status if isinstance(status, str) and status in RESEARCH_CHIP else None
    order_id = order.get("id")
    action: dict[str, str] | None = None
    if status in ("listo", "pendiente", "en_curso") and valid_id(order_id):
        action = {
            "label": "Ver dossier" if status == "listo" else "Ver estado",
            "href": f"/informes/{order_id}",
            "style": "secondary",
        }
    elif (
        status in (None, "rechazado")
        and _dict(niche.get("decision")).get("decision") == "tentativo"
        and _score(niche.get("opportunity")) != "sin evidencia"
        and isinstance(label, str)
    ):
        action = {"label": "Investigar", "href": investigate_href(label, fmt), "style": "primary"}
    return {"status": status or "sin investigación", "action": action}


def _decision_form(niche: dict[str, Any]) -> dict[str, str]:
    current = _dict(niche.get("decision"))
    value = current.get("decision")
    note = current.get("note")
    return {
        "decision": value if value in ("nuevo", "tentativo", "descartado") else "nuevo",
        "note": note if isinstance(note, str) else "",
        "error": "",
    }


def detail_view(detail: object, research: object, pilot: object, tz: str) -> dict[str, Any]:
    data = _dict(detail)
    niche = data["niche"]
    if not isinstance(niche, dict):
        raise TypeError("niche")
    raw_listings = data["listings"]
    if not isinstance(raw_listings, list):
        raise TypeError("listings")
    fmt = "shorts" if niche.get("format") == "shorts" else "long"
    metrics = _dict(niche.get("metrics"))
    label = niche.get("niche_label")
    decision = _dict(niche.get("decision")).get("decision")
    d_text, d_kind = DECISION_CHIP.get(
        decision if isinstance(decision, str) else "", DECISION_CHIP["nuevo"]
    )
    chips = [("Shorts" if fmt == "shorts" else "Largo", "neutral"), (d_text, d_kind)]
    order = _dict(research)
    r_status = order.get("status")
    r_chip = RESEARCH_CHIP.get(r_status) if isinstance(r_status, str) else None
    if r_chip:
        chips.append(r_chip)
    journey_research = None if research == UNREADABLE else research
    steps = niche_journey(niche, journey_research, None if pilot == UNREADABLE else pilot)
    if research == UNREADABLE:
        steps[3] = replace(steps[3], detail=RESEARCH_DOWN)
    risk = _dict(_dict(niche.get("automation")).get("policy_risk")).get("level")
    confidence = niche.get("confidence")
    rpm = _number(niche.get("rpm_mid"))
    rpm_text = (
        "sin calibrar"
        if fmt == "shorts" or rpm is None or niche.get("rpm_state") != "calibrated"
        else money_amount(rpm)
    )
    shown = raw_listings[:MAX_LISTINGS]
    listings = [_listing(item) for item in shown]
    warnings = []
    if len(raw_listings) > MAX_LISTINGS:
        warnings.append(
            f"Se muestran {MAX_LISTINGS} de {len(raw_listings)} fichas: el resto no se carga aquí."
        )
    if pilot == UNREADABLE:
        warnings.append(PILOTS_DOWN)
    return {
        "title": label if isinstance(label, str) and label else "Nicho sin nombre",
        "chips": chips,
        "journey": steps,
        "scores": [
            ("Opportunity (0 a 100)", _score(niche.get("opportunity"))),
            ("Automatización (0 a 100)", _score(niche.get("automation"))),
            ("Confianza", confidence if confidence in CONFIDENCE else "—"),
            ("Riesgo de política", risk if isinstance(risk, str) and risk else "sin dato"),
            ("Tendencia", trend_text(niche.get("trend"))),
        ],
        "research": _research_card(niche, research, fmt),
        "market": [
            ("Fichas", _count(metrics.get("n_listings"))),
            ("Con ingreso", _count(metrics.get("n_income"))),
            ("Ingreso mediano", _per_month(metrics.get("income_median"))),
            ("Precio / ingreso anual", _ratio(metrics.get("multiple_median"))),
            ("RPM de referencia", rpm_text),
        ],
        "language": _language_text(data.get("language_mix", [])),
        "how": HOW,
        "how_note": HOW_NOTE,
        "listings": listings,
        "pages": [listings[i : i + PAGE] for i in range(PAGE, len(listings), PAGE)],
        "first_page": listings[:PAGE],
        "listings_total": len(raw_listings),
        "truncated": len(raw_listings) > MAX_LISTINGS,
        "warnings": warnings,
        "notice": NOTICE,
        "form": _decision_form(niche),
        "tz": tz,
    }
