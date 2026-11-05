# src/nicheradar/web/report.py
"""View models of the dossier report (M3) and of an order that has no report yet (M11).

Stored dossiers can be dossier-v1, -v2 or -v3 and any optional field can be null or absent:
every read here tolerates that, so a stored dossier can never turn into a server error.
"""

import math
import re
from typing import Any

from nicheradar.flow_research.contracts import calibration_total_hours
from nicheradar.flow_research.gates import (
    DEFAULT_GATES,
    Gates,
    calibration_reasons,
    minutes_reasons,
)
from nicheradar.web.format import compact, local_datetime, money_amount, parse_utc, zone
from nicheradar.web.niches import CONFIDENCE, FORMATS
from nicheradar.web.research import LANGUAGE_NAMES

RECOMMENDATION = {
    "go": ("sí", "green"),
    "go_with_conditions": ("sí, con condiciones", "amber"),
    "no_go": ("no", "rose"),
}
CONFIDENCE_DOSSIER = {"low": "Baja", "medium": "Media", "high": "Alta"}
RIGHTS = {"cleared": "resueltos", "conditional": "con condiciones", "blocked": "bloqueados"}
HORIZON = {"short": "corto plazo", "medium": "mediano plazo"}
BASIS = {
    "measured": "Medido",
    "mapped_flow_equivalent": "Equivalente a un flujo ya mapeado",
    "estimate": "Estimación",
}
AVISOS_INFORME = {
    "creada": ("Investigación creada. Claude Code la atenderá en la próxima sesión.", "green"),
    "existente": ("Ya había una investigación activa con esa clave.", "amber"),
    "piloto": ("Piloto autorizado.", "green"),
}
PILOT_RE = re.compile(r"pil_[0-9]{8}_[a-z0-9-]{1,40}")
STATUS_PAGES = {
    "pendiente": ("En cola", "amber", "La investigación espera a que Claude Code la reclame."),
    "en_curso": (
        "Investigando",
        "blue",
        "Claude Code la atiende en su sesión; el encargo se reclama 60 minutos.",
    ),
    "rechazado": (
        "Rechazada",
        "rose",
        "El dossier entregado no pasó la validación. Puedes iniciar una investigación nueva.",
    ),
}
OLD_NOTICE = "Dossier anterior: no separa calibración de régimen."
INCOMPLETE_NOTICE = (
    "Este informe no trae la calibración completa: solo se muestran los minutos de cuando "
    "ya está en marcha."
)
NO_DATA = "sin dato"
BAR_COLOURS = 5  # classes bar__seg--c0..c4, in the order of the legend
BAR_UNITS = 20  # a bar is cut in steps of 5 % (classes bar--p0..bar--p100)
SCALE_NOTE = "mismos colores en las dos barras, a la misma escala"


def safe_url(url: object) -> str | None:
    """Only https links without whitespace or control characters can become an href."""
    if (
        isinstance(url, str)
        and url.startswith("https://")
        and not any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url)
    ):
        return url
    return None


def subject_label(niche_label: str) -> tuple[str, bool]:
    prefix = "subniche:"
    if niche_label.startswith(prefix):
        return niche_label[len(prefix) :].replace("_", " ").title(), True
    return niche_label, False


def notice(aviso: str, pilot: str) -> tuple[str, str] | None:
    """Only a fixed key picks the text; the pilot id shows only if it has the pilot's shape."""
    found = AVISOS_INFORME.get(aviso)
    if found is None:
        return None
    if aviso == "piloto" and PILOT_RE.fullmatch(pilot):
        return (f"{found[0]} Identificador: {pilot}", found[1])
    return found


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _texts(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def _hours(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _money(value: object) -> str:
    return money_amount(value)


def _step_minutes(value: object) -> float | None:
    """Minutes of one step; null, non-numeric, non-finite or negative values are no data."""
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _minutes(items: list[dict[str, Any]], key: str) -> int:
    return round(sum(n for item in items if (n := _step_minutes(item.get(key))) is not None))


def _by_step(items: list[dict[str, Any]], name_key: str, key: str) -> dict[str, float | None]:
    """Minutes per step name; a repeated name adds up and a step without data stays None."""
    result: dict[str, float | None] = {}
    for index, item in enumerate(items):
        name = item.get(name_key)
        name = name.strip() if isinstance(name, str) and name.strip() else f"Paso {index + 1}"
        minutes = _step_minutes(item.get(key))
        previous = result.get(name)
        result[name] = minutes if previous is None else previous + (minutes or 0)
    return result


def _total(minutes: dict[str, float | None]) -> float | None:
    known = [m for m in minutes.values() if m is not None]
    return sum(known) if known else None


def _units(minutes: dict[str, float | None], scale: float) -> dict[str, int]:
    """Width of each step in 5 % units, on a scale shared by both bars (largest remainder).

    A step with minutes always shows at least one unit; a bar without data stays empty.
    """
    total = _total(minutes)
    if not total or scale <= 0:
        return {name: 0 for name in minutes}
    exact = {name: (m or 0) / scale * BAR_UNITS for name, m in minutes.items()}
    units = {name: int(value) for name, value in exact.items()}
    target = round(sum(exact.values()))
    for name in sorted(exact, key=lambda n: exact[n] - units[n], reverse=True):
        if sum(units.values()) >= target:
            break
        units[name] += 1
    positive = [name for name, m in minutes.items() if m]
    for name in positive:
        if units[name] == 0:
            units[name] = 1
    while sum(units.values()) > BAR_UNITS:
        widest = max(units, key=lambda n: units[n])
        if units[widest] <= 1:
            break
        units[widest] -= 1
    return units


def _bar(names: list[str], minutes: dict[str, float | None], scale: float) -> list[dict[str, Any]]:
    units = _units(minutes, scale)
    return [
        {
            "name": name,
            "colour": f"c{index % BAR_COLOURS}",
            "width": units.get(name, 0) * 5,
            "minutes": minutes.get(name),
        }
        for index, name in enumerate(names)
    ]


def _bar_text(segments: list[dict[str, Any]]) -> str:
    parts = [
        f"{seg['name']} {round(seg['minutes'])} min"
        for seg in segments
        if seg["minutes"] is not None
    ]
    return ", ".join(parts) if parts else NO_DATA


def _local_date(value: object, timezone: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_utc(value).astimezone(zone(timezone)).strftime("%d/%m/%Y")
    except (ValueError, OverflowError):
        return None


def _hypothesis_name(evidence: dict[str, Any]) -> str | None:
    name = _dict(evidence.get("subniche")).get("label")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _gates(evidence: dict[str, Any]) -> Gates:
    """The thresholds frozen with the order; the defaults only if the evidence lacks them."""
    frozen = _dict(evidence.get("gate"))
    minutes = _number(frozen.get("max_human_minutes"))
    hours = _number(frozen.get("max_calibration_hours"))
    return Gates(
        max_human_minutes=DEFAULT_GATES.max_human_minutes if minutes is None else round(minutes),
        max_calibration_hours=DEFAULT_GATES.max_calibration_hours if hours is None else hours,
    )


def _calibration(dossier: dict[str, Any]) -> dict[str, Any] | None:
    """Calibration numbers of a dossier-v3, or None for older (or incomplete) dossiers."""
    block = _dict(dossier.get("calibration"))
    videos, setup = _number(block.get("videos")), _number(block.get("setup_hours"))
    steps = _items(block.get("minutes_by_step"))
    if (
        dossier.get("schema_version") != "dossier-v3"
        or videos is None
        or setup is None
        or not steps
    ):
        return None
    by_step = _by_step(steps, "step", "minutes_per_video")
    per_video = _total(by_step)
    count = round(videos)
    return {
        "videos": count,
        "by_step": by_step,
        "per_video": None if per_video is None else round(per_video),
        "setup": setup,
        "total": None
        if per_video is None
        else calibration_total_hours(setup, count, round(per_video)),
        "statement": _dict(block.get("exit_criterion")).get("statement"),
    }


def _time_card(calibration: dict[str, Any], flow: list[dict[str, Any]]) -> dict[str, Any]:
    """Both bars of the time card: same steps, same colours, one scale."""
    regime = _by_step(flow, "name", "human_minutes_per_video")
    names = list(regime) + [name for name in calibration["by_step"] if name not in regime]
    scale = max(_total(regime) or 0, _total(calibration["by_step"]) or 0)
    per_video, videos = calibration["per_video"], calibration["videos"]
    regime_total = _total(regime)
    cal_bar = _bar(names, calibration["by_step"], scale)
    regime_bar = _bar(names, regime, scale)
    return {
        "legend": [{"name": seg["name"], "colour": seg["colour"]} for seg in cal_bar],
        "scale_note": SCALE_NOTE,
        "calibration": {
            "title": f"Primeros {videos} videos (calibración)",
            "segments": cal_bar,
            "aria": _bar_text(cal_bar),
            "rows": [
                ("Tu tiempo por video", NO_DATA if per_video is None else f"{per_video} min"),
                (
                    f"Total de los {videos} videos",
                    NO_DATA
                    if per_video is None
                    else f"{_hours(round(per_video * videos / 60, 2))} h",
                ),
                ("Preparación del canal (una vez)", f"{_hours(calibration['setup'])} h"),
                (
                    "Horas de calibración",
                    NO_DATA
                    if calibration["total"] is None
                    else f"{_hours(calibration['total'])} h",
                ),
            ],
        },
        "regime": {
            "title": "Cuando ya está en marcha (régimen)",
            "segments": regime_bar,
            "aria": _bar_text(regime_bar),
            "rows": [
                (
                    "Tu tiempo por video",
                    NO_DATA if regime_total is None else f"{round(regime_total)} min",
                )
            ],
        },
    }


def _firm(evidence: dict[str, Any], timezone: str) -> dict[str, Any] | None:
    confidence = CONFIDENCE.get(str(evidence.get("confidence")))
    rows: list[tuple[str, str]] = []
    if confidence:
        rows.append(("Confianza de la medición", confidence))
    subniche = evidence.get("source") == "subniche"
    count_line: str | None = None
    if subniche:
        measurement = _dict(evidence.get("measurement"))
        measured = measurement.get("measured_at")
        included = measurement.get("included")
        day = _local_date(measured, timezone)
        if isinstance(included, int) and not isinstance(included, bool) and included >= 0:
            noun = "canal medido" if included == 1 else "canales medidos"
            count_line = f"{included} {noun}" + (f" el {day}" if day else "")
        elif isinstance(measured, str):
            try:
                rows.append(("Medido el", local_datetime(measured, timezone)))
            except ValueError:
                pass
    else:
        mix = [
            f"{LANGUAGE_NAMES.get(code, code) if code != 'unknown' else 'Sin dato'} {round(share)}%"
            for entry in _items(evidence.get("language_mix"))
            if isinstance(code := entry.get("language"), str)
            and (share := _number(entry.get("share_pct"))) is not None
        ]
        if mix:
            rows.append(("Idioma del mercado", " · ".join(mix)))
    if not rows and count_line is None:
        return None
    return {"rows": rows, "subniche": subniche, "count_line": count_line}


def _warnings(dossier: dict[str, Any]) -> list[tuple[str, list[str]]]:
    verdict, rights = _dict(dossier.get("verdict")), _dict(dossier.get("rights"))
    groups = [
        ("Riesgos principales", _texts(verdict.get("main_risks"))),
        ("Lo que no sabemos", _texts(verdict.get("unknowns"))),
        ("Condiciones", _texts(verdict.get("conditions"))),
        ("Riesgo de política", _texts([_dict(dossier.get("policy_risk")).get("summary")])),
        ("Condiciones de los derechos", _texts(rights.get("conditions"))),
    ]
    return [(heading, texts) for heading, texts in groups if texts]


def report_view(detail: dict[str, Any], timezone: str) -> dict[str, Any]:
    dossier = detail.get("dossier")
    if not isinstance(dossier, dict) or not dossier:
        return {"missing": True}
    evidence = _dict(detail.get("evidence"))
    label = str(detail.get("niche_label") or "")
    subject, is_subniche = subject_label(label)
    subject = (_hypothesis_name(evidence) if is_subniche else None) or subject
    verdict = _dict(dossier.get("verdict"))
    headline, kind = RECOMMENDATION.get(
        str(verdict.get("recommendation")), ("sin veredicto", "neutral")
    )
    flow = _items(dossier.get("production_flow"))
    regime = _minutes(flow, "human_minutes_per_video")
    calibration = _calibration(dossier)
    gates = _gates(evidence)

    time_rows: list[tuple[str, str]] = []
    gate_rows: list[tuple[str, str, str]] = []

    def gate(text: str, ok: bool) -> None:
        gate_rows.append((text, "pasa" if ok else "no pasa", "green" if ok else "rose"))

    time = _time_card(calibration, flow) if calibration else None
    if not calibration:
        time_rows.append(("Cuando ya está en marcha (régimen)", f"{regime} min por video"))
    gate(
        f"Minutos por video, ya en marcha: {regime} de {gates.max_human_minutes:g} permitidos",
        not minutes_reasons(regime, gates),
    )
    if calibration and calibration["total"] is None:
        gate_rows.append(("Horas de calibración: sin dato", NO_DATA, "neutral"))
    elif calibration:
        gate(
            f"Horas de calibración: {_hours(calibration['total'])} de "
            f"{_hours(gates.max_calibration_hours)} permitidas",
            not calibration_reasons(calibration["total"], gates),
        )
    rights_verdict = _dict(dossier.get("rights")).get("verdict")
    if rights_verdict in RIGHTS:
        gate(f"Derechos del material: {RIGHTS[rights_verdict]}", rights_verdict != "blocked")
    else:
        gate_rows.append(("Derechos del material: sin evaluar", "sin evaluar", "neutral"))

    steady = _dict(dossier.get("steady_state_evidence"))
    basis = str(steady.get("basis"))
    reference = steady.get("reference_channel")
    sample = _number(steady.get("reference_sample_videos"))
    basis_text = BASIS.get(basis)
    if basis == "measured" and basis_text and isinstance(reference, str) and sample is not None:
        basis_text = f"Medido en {reference}: {round(sample)} videos"
    format_match = steady.get("format_match")
    totals = _dict(_dict(dossier.get("budget")).get("totals"))
    tools = _items(dossier.get("tools"))
    competitors = _items(dossier.get("competitors"))
    sources = _items(dossier.get("sources"))
    warnings = _warnings(dossier)
    fmt = detail.get("format")
    return {
        "missing": False,
        "title": f"{subject}: {headline}",
        "kind": kind,
        "headline": headline,
        "thesis": verdict.get("thesis") if isinstance(verdict.get("thesis"), str) else "",
        "confidence": CONFIDENCE_DOSSIER.get(str(verdict.get("confidence"))),
        "old_notice": None
        if calibration
        else INCOMPLETE_NOTICE
        if dossier.get("schema_version") == "dossier-v3"
        else OLD_NOTICE,
        "firm": _firm(evidence, timezone),
        "time": time,
        "time_rows": time_rows,
        "exit": None
        if not calibration
        else {
            "statement": calibration["statement"]
            if isinstance(calibration["statement"], str)
            else "",
            "basis": basis_text,
            "format_match": format_match if isinstance(format_match, str) else "",
        },
        "gates": gate_rows,
        "budget": [
            ("Bajo", _money(totals.get("low"))),
            ("Probable", _money(totals.get("likely"))),
            ("Peor caso (tope)", _money(totals.get("high"))),
        ],
        "horizon": HORIZON.get(str(dossier.get("horizon"))),
        "tools": [
            {
                "name": t.get("name"),
                "phase": t.get("phase"),
                "purpose": t.get("purpose"),
                "pricing": t.get("pricing"),
                "cheaper": t.get("cheaper_alternative"),
            }
            for t in tools
        ],
        "warnings": warnings,
        "warning_count": sum(len(texts) for _, texts in warnings),
        "competitors": [
            {
                "name": c.get("name"),
                "subscribers": compact(_number(c.get("subscribers"))),
                "url": safe_url(c.get("channel_url")),
            }
            for c in competitors
        ],
        "sources": [
            {
                "title": s.get("title"),
                "url": safe_url(s.get("url")),
                "accessed_on": s.get("accessed_on"),
            }
            for s in sources
        ],
        "launch_href": f"/pilotos/autorizar?informe={detail.get('id')}",
        "postpone_href": "/subnichos" if is_subniche else "/nichos",
        "can_discard": not is_subniche and fmt in FORMATS and 1 <= len(label) <= 140,
        "niche_label": label,
        "format": fmt,
    }


def status_view(detail: dict[str, Any]) -> dict[str, Any]:
    status = str(detail.get("status"))
    if status == "listo":
        chip, kind, text = (
            "Dossier listo",
            "amber",
            "El dossier no está disponible: la investigación figura como lista, pero no hay "
            "informe guardado.",
        )
    else:
        chip, kind, text = STATUS_PAGES.get(
            status,
            ("Estado desconocido", "neutral", "No se reconoce el estado de esta investigación."),
        )
    problems: list[str] = []
    if status == "rechazado":
        for item in _items(_dict(detail.get("rejection")).get("problems")):
            message = item.get("message")
            path = item.get("path")
            if isinstance(message, str) and message:
                problems.append(f"{path}: {message}" if isinstance(path, str) and path else message)
    label = str(detail.get("niche_label") or "")
    subject, is_subniche = subject_label(label)
    return {
        "chip": chip,
        "kind": kind,
        "text": text,
        "problems": problems,
        "title": (_hypothesis_name(_dict(detail.get("evidence"))) if is_subniche else None)
        or subject,
        "back_href": "/subnichos" if is_subniche else "/nichos",
        "back_text": "← Volver a Subnichos" if is_subniche else "← Volver a Nichos",
        "format_text": FORMATS.get(str(detail.get("format")), ""),
    }
