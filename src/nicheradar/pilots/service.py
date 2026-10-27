# src/nicheradar/pilots/service.py
"""Ciclo de vida de un piloto.

autorizado -> entregado -> en_ejecucion -> decision_pendiente -> cerrado.

NicheRadar propone y el humano decide. Todo cambio de estado deja una fila en ``pilot_events``.
El paquete es inmutable: cambiar reglas o presupuesto crea otro (``supersedes``).
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from nicheradar.flow_research import gates as gate_rules
from nicheradar.flow_research.gates import (
    GateReason,
    Gates,
    authorization_reasons,
    describe,
)
from nicheradar.flow_research.service import get_request
from nicheradar.market_intel.niches import niche_detail
from nicheradar.pilots import rules, tokens
from nicheradar.pilots.contracts import (
    AnyReport,
    Measurement,
    Problem,
    ShortsMeasurement,
    ShortsVideo,
    Video,
    package_sha256,
    report_format,
    stage_of,
    validate_package,
    with_sha256,
)
from nicheradar.repositories.schema import pilot_events as events
from nicheradar.repositories.schema import pilot_shorts_measurements as shorts
from nicheradar.repositories.schema import pilot_videos as videos
from nicheradar.repositories.schema import pilots

OPEN_STATES = ("autorizado", "entregado", "en_ejecucion", "decision_pendiente")
CONFIDENCE = {"alta": "high", "media": "medium", "baja": "low"}
DEFAULT_VALID_DAYS = 14
MESSAGES = {
    "not_found": "Piloto, encargo o nicho no encontrado.",
    "forbidden": "El token no corresponde a este canal.",
    "gone": "El paquete venció y ya no se entrega.",
    "dossier_not_ready": "El encargo de investigación no tiene un dossier listo.",
    "niche_mismatch": "El dossier no corresponde al nicho y formato indicados.",
    "language_unknown": "El encargo no tiene idioma: investígalo de nuevo eligiendo uno.",
    "no_go_requires_acceptance": "El dossier recomienda no avanzar: hay que aceptarlo.",
    "gate_failed": "El piloto no pasa las compuertas de selección.",
    "channel_busy": "Ese canal ya tiene un piloto abierto.",
    "bad_transition": "El piloto no está en un estado que permita esa acción.",
    "hash_mismatch": "La huella no coincide con la del paquete entregado.",
    "not_delivered": "El paquete todavía no fue confirmado como entregado.",
    "closed": "El piloto ya está cerrado o cancelado.",
    "channel_mismatch": "El reporte pertenece a otro canal.",
    "report_format_mismatch": "El contrato del reporte no corresponde al formato del piloto.",
    "invalid": "El contenido no cumple el contrato.",
}

# Reglas de referencia: «Criterios de abandono» de canal-historias (overview-proyecto.md §6).
DEFAULT_STOP_RULES: list[dict[str, Any]] = [
    {
        "id": "pipeline-s6",
        "text": "Semana 6: pipeline de punta a punta con 1 video publicado",
        "metric": "pipeline_e2e",
        "comparator": ">=",
        "threshold": None,
        "min_cases": None,
        "milestone": {"kind": "week", "value": 6},
    },
    {
        "id": "retencion-v10",
        "text": "Video 10: AVD (porcentaje promedio visto) de al menos 18% en 3 videos",
        "metric": "avd_pct",
        "comparator": ">=",
        "threshold": 18,
        "min_cases": 3,
        "milestone": {"kind": "video", "value": 10},
    },
    {
        "id": "browse-v20",
        "text": "Video 20: trafico de exploracion de al menos 30%, sin bajar",
        "metric": "browse_share_pct",
        "comparator": ">=",
        "threshold": 30,
        "min_cases": None,
        "milestone": {"kind": "video", "value": 20},
    },
    {
        "id": "viabilidad-m6",
        "text": "Mes 6: ingreso mayor o igual al costo en efectivo del stack",
        "metric": "revenue_vs_cost",
        "comparator": ">=",
        "threshold": 1,
        "min_cases": None,
        "milestone": {"kind": "month", "value": 6},
    },
]


class PilotError(Exception):
    def __init__(
        self,
        code: str,
        problems: list[Problem] | None = None,
        reasons: list[GateReason] | None = None,
    ) -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.problems = problems or []
        self.reasons = reasons or []


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _log(
    connection: Connection, pk: UUID, actor: str, kind: str, now: datetime, **detail: Any
) -> None:
    connection.execute(
        events.insert().values(
            id=uuid4(), pilot_pk=pk, at=now, actor=actor, kind=kind, detail=_plain(detail)
        )
    )


def _slug(label: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return (text or "nicho")[:40].strip("-") or "nicho"


def _score(block: Any) -> int | None:
    value = block.get("value") if isinstance(block, dict) else None
    return None if value is None else max(0, min(100, round(float(value))))


def _number(value: Any) -> Decimal:
    return Decimal(str(round(float(value), 4)))


def _figures(niche: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = niche["metrics"]
    declared = [
        ("income_median", "income_median", "usd_per_month"),
        ("margin_median", "margin_median", "fraction"),
        ("income_per_1k_subs_median", "income_per_1k_subs_median", "usd_per_month_per_1k_subs"),
        ("multiple_median", "multiple_median", "price_over_annual_income"),
    ]
    out: list[dict[str, Any]] = []
    for name, key, unit in declared:
        if (
            metrics.get(key) is not None
        ):  # todo viene de fichas de vendedores: nunca se marca verificado
            out.append(
                {
                    "name": name,
                    "value": _plain(_number(metrics[key])),
                    "unit": unit,
                    "origin": "seller_declared",
                }
            )
    out.append(
        {
            "name": "disappearance_rate",
            "value": _plain(_number(metrics["disappearance_rate"])),
            "unit": "fraction",
            "origin": "estimate",
        }
    )
    if niche.get("rpm_mid") is not None:
        out.append(
            {
                "name": "rpm_mid",
                "value": _plain(_number(niche["rpm_mid"])),
                "unit": "usd_per_1k_views",
                "origin": "estimate",
            }
        )
    return out


def _evidence(detail: dict[str, Any], now: datetime) -> dict[str, Any]:
    niche = detail["niche"]
    return {
        "captured_at": now.isoformat(),
        # creator_fit y market no existen por nicho en el backlog: se declaran null, no se inventan
        "scores": {
            "opportunity": _score(niche["opportunity"]),
            "automation": _score(niche["automation"]),
            "creator_fit": None,
            "market": None,
        },
        "confidence": CONFIDENCE[niche["confidence"]],
        "listings_with_income": int(niche["metrics"]["n_income"]),
        "language_mix": detail["language_mix"],
        "figures": _figures(niche),
    }


def _new_pilot_id(connection: Connection, label: str, now: datetime) -> str:
    base = f"pil_{now:%Y%m%d}_"
    slug = _slug(label)
    for attempt in range(1, 50):
        suffix = "" if attempt == 1 else f"-{attempt}"
        candidate = base + slug[: 40 - len(suffix)].strip("-") + suffix
        taken = connection.execute(
            select(pilots.c.id).where(pilots.c.pilot_id == candidate)
        ).first()
        if taken is None:
            return candidate
    raise PilotError("channel_busy")


def authorize(
    connection: Connection,
    *,
    niche_label: str,
    format: str,
    dossier_request_id: UUID,
    budget: dict[str, Any],
    stop_rules: list[dict[str, Any]] | None,
    close_after: int,
    target_channel: str | None,
    recipe: dict[str, Any] | None,
    valid_days: int,
    authorized_by: str,
    accept_no_go: bool,
    supersedes: str | None,
    now: datetime,
    timezone: str = "UTC",
    gates: Gates | None = None,
    accept_gate_failure: bool = False,
) -> dict[str, Any]:
    """El humano pulsa «Lanzar»: se congela el paquete (evidencia, dossier, presupuesto, reglas).

    Repite las compuertas de selección sobre el dossier guardado: sin ``accept_gate_failure``
    falla con ``gate_failed``; con él, queda registrado y se marca en la tesis del paquete.
    """
    request = get_request(connection, dossier_request_id)
    if request is None:
        raise PilotError("not_found")
    dossier = request["dossier"]
    if request["status"] != "listo" or dossier is None:
        raise PilotError("dossier_not_ready")
    if (request["niche_label"], request["format"]) != (niche_label, format):
        raise PilotError("niche_mismatch")
    language = request["language"]  # se eligió al iniciar la investigación y no se cambia aquí
    if language == "unknown":
        raise PilotError("language_unknown")
    verdict = dossier["verdict"]
    thesis = verdict["thesis"]
    if verdict["recommendation"] == "no_go":
        if not accept_no_go:
            raise PilotError("no_go_requires_acceptance")
        thesis = f"[NO-GO autorizado explicitamente por el humano] {thesis}"[:1500]
    detail = niche_detail(connection, niche_label, format, now, timezone)
    if detail is None:
        raise PilotError("not_found")
    failures = authorization_reasons(
        dossier, request["evidence"]["niche"], gates or gate_rules.DEFAULT_GATES
    )
    if failures:
        if not accept_gate_failure:
            raise PilotError("gate_failed", reasons=failures)
        thesis = f"[COMPUERTAS NO CUMPLIDAS aceptadas por el humano: {describe(failures)}] {thesis}"
        thesis = thesis[:1500]
    previous = None
    if supersedes is not None:
        previous = (
            connection.execute(select(pilots).where(pilots.c.pilot_id == supersedes))
            .mappings()
            .one_or_none()
        )
        if previous is None:
            raise PilotError("not_found")
        if previous["status"] not in ("autorizado", "entregado"):
            raise PilotError("bad_transition")
    pilot_id = _new_pilot_id(connection, niche_label, now)
    body: dict[str, Any] = {
        "contract": "pilot-package-v1",
        "pilot_id": pilot_id,
        "supersedes": supersedes,
        "authorized_by": authorized_by,
        "authorized_at": now.isoformat(),
        "valid_until": (now + timedelta(days=valid_days)).isoformat(),
        "niche": {"label": niche_label, "format": format, "language": language},
        "evidence": _evidence(detail, now),
        "dossier": {
            "request_id": str(dossier_request_id),
            "schema": dossier["schema_version"],
            "recommendation": verdict["recommendation"],
            "confidence": verdict["confidence"],
            "thesis": thesis,
            "unknowns": list(verdict["unknowns"]),
        },
        "budget": {"currency": "USD", **budget},
        "stop_rules": stop_rules if stop_rules is not None else default_stop_rules(format),
        "close_after_failed_milestones": close_after,
        "target_channel": target_channel,
        "recipe": recipe,
    }
    payload = with_sha256(body)
    package, problems = validate_package(payload, now)
    if package is None:
        raise PilotError("invalid", problems)
    pk = uuid4()
    try:
        with connection.begin_nested():
            if previous is not None:
                connection.execute(
                    update(pilots)
                    .where(pilots.c.id == previous["id"])
                    .values(
                        status="cancelado",
                        closed_at=now,
                        close_reason=f"reemplazado por {pilot_id}",
                        updated_at=now,
                    )
                )
                _log(connection, previous["id"], authorized_by, "superseded", now, by=pilot_id)
            connection.execute(
                pilots.insert().values(
                    id=pk,
                    pilot_id=pilot_id,
                    niche_label=niche_label,
                    format=format,
                    language=language,
                    status="autorizado",
                    target_channel=target_channel,
                    package=payload,
                    package_sha256=payload["package_sha256"],
                    authorized_by=authorized_by,
                    authorized_at=now,
                    valid_until=now + timedelta(days=valid_days),
                    acknowledged=[],
                    created_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError as error:
        raise PilotError("channel_busy") from error
    _log(connection, pk, authorized_by, "authorized", now, sha256=payload["package_sha256"])
    if failures:
        _log(connection, pk, authorized_by, "gate_failure_accepted", now, reasons=failures)
    return {"pilot_id": pilot_id, "status": "autorizado", "package": payload}


# Sin umbral de retención inventado: el bench de Shorts no encontró umbrales oficiales y deben
# calibrarse con un canal real. Quien autorice un piloto de Shorts los pasa en `stop_rules`.
SHORTS_DEFAULT_METRICS = {"pipeline_e2e", "revenue_vs_cost"}


def default_stop_rules(format: str) -> list[dict[str, Any]]:
    keep = SHORTS_DEFAULT_METRICS if format == "shorts" else None
    return [
        {**rule, "milestone": dict(rule["milestone"])}
        for rule in DEFAULT_STOP_RULES
        if keep is None or rule["metric"] in keep
    ]


def _row(connection: Connection, pilot_id: str) -> Any:
    row = (
        connection.execute(select(pilots).where(pilots.c.pilot_id == pilot_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PilotError("not_found")
    return row


def _own(row: Any, channel_id: str | None) -> None:
    """Un token de canal solo ve los pilotos de su canal; los ajenos no revelan nada."""
    if channel_id is None or row["target_channel"] == channel_id:
        return
    if row["target_channel"] is None and row["status"] == "autorizado":
        return  # sin asignar: cualquier canal puede reclamarlo al confirmar la entrega
    raise PilotError("not_found")


def pending_for_channel(
    connection: Connection, channel_id: str, now: datetime
) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(
            pilots.c.pilot_id,
            pilots.c.niche_label,
            pilots.c.format,
            pilots.c.authorized_at,
            pilots.c.valid_until,
            pilots.c.package_sha256,
        )
        .where(
            or_(pilots.c.target_channel == channel_id, pilots.c.target_channel.is_(None)),
            pilots.c.status == "autorizado",
            pilots.c.valid_until > now,
        )
        .order_by(pilots.c.authorized_at)
    ).mappings()
    return [
        {
            **row,
            "authorized_at": row["authorized_at"].isoformat(),
            "valid_until": row["valid_until"].isoformat(),
        }
        for row in rows
    ]


def package_for(
    connection: Connection, pilot_id: str, channel_id: str | None, now: datetime
) -> dict[str, Any]:
    row = _row(connection, pilot_id)
    _own(row, channel_id)
    if row["status"] in ("cerrado", "cancelado"):
        raise PilotError("closed")
    if row["status"] == "autorizado" and row["valid_until"] <= now:
        raise PilotError("gone")
    return dict(row["package"])


def confirm_delivery(
    connection: Connection, pilot_id: str, channel_id: str, sha256: str, now: datetime
) -> dict[str, Any]:
    row = _row(connection, pilot_id)
    _own(row, channel_id)
    if row["status"] in ("cerrado", "cancelado"):
        raise PilotError("closed")
    if sha256 != row["package_sha256"]:
        raise PilotError("hash_mismatch")
    if row["status"] == "autorizado":
        if row["valid_until"] <= now:
            raise PilotError("gone")
        values: dict[str, Any] = {"status": "entregado", "delivered_at": now, "updated_at": now}
        assigned = row["target_channel"] is None
        if assigned:
            values["target_channel"] = channel_id  # el índice único detecta un canal ocupado
        try:
            with connection.begin_nested():
                connection.execute(update(pilots).where(pilots.c.id == row["id"]).values(**values))
        except IntegrityError as error:
            raise PilotError("channel_busy") from error
        _log(
            connection,
            row["id"],
            channel_id,
            "delivered",
            now,
            **({"assigned_channel": channel_id} if assigned else {}),
        )
        return {"pilot_id": pilot_id, "status": "entregado", "changed": True}
    return {
        "pilot_id": pilot_id,
        "status": row["status"],
        "changed": False,
    }  # idempotente


def _videos_for_rules(connection: Connection, pk: UUID) -> list[dict[str, Any]]:
    joined = videos.outerjoin(shorts, shorts.c.pilot_video_id == videos.c.id)
    rows = connection.execute(
        select(videos, *(c for c in shorts.c if c.name != "pilot_video_id"))
        .select_from(joined)
        .where(videos.c.pilot_pk == pk)
    ).mappings()
    return [
        {
            "video_id": r["video_id"],
            "stage": r["stage"],
            "published_at": r["published_at"],
            "cost_usd": r["cost_usd"],
            "cost_equivalent_usd": r["cost_equivalent_usd"],
            "machine_minutes": r["machine_minutes"],
            "avd_pct": r["avd_pct"],
            "browse_share_pct": r["browse_share_pct"],
            "views": r["views"],
            "measured_at": r["measured_at"],
            **{name: r[name] for name in SHORTS_FIELDS},
        }
        for r in rows
    ]


def _evaluate(connection: Connection, row: Any, now: datetime) -> dict[str, Any]:
    package = row["package"]
    return rules.evaluate(
        package["stop_rules"],
        _videos_for_rules(connection, row["id"]),
        now=now,
        authorized_at=row["authorized_at"],
        max_videos=int(package["budget"]["max_videos"]),
        close_after=int(package["close_after_failed_milestones"]),
    )


# Columnas de pilot_shorts_measurements que las reglas leen (channel-report-v2).
SHORTS_FIELDS = (
    "engaged_view_ratio_pct",
    "avg_view_pct",
    "shorts_feed_share_pct",
)
_VIDEO_FIELDS = (
    "source_state",
    "stage",
    "visibility",
    "published_at",
    "cost_usd",
    "cost_equivalent_usd",
    "machine_minutes",
    "failure_code",
    "measured_at",
    "window_days",
    "avd_pct",
    "views",
    "browse_share_pct",
    "subscribers_gained",
    "reported_at",
)


def _shorts_values(m: ShortsMeasurement | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {
        "engaged_views": m.engaged_views,
        "engaged_view_ratio_pct": m.engaged_view_ratio_pct,
        "avg_view_pct": m.avg_view_pct,
        "shorts_feed_share_pct": m.shorts_feed_share_pct,
        "shares": m.shares,
        "stayed_to_watch_pct": m.stayed_to_watch_pct,
        "early_retention_pct": m.early_retention_pct,
        "early_retention_second": m.early_retention_second,
    }


def _video_values(
    video: Video | ShortsVideo, channel_id: str, reported_at: datetime
) -> dict[str, Any]:
    m = video.measurement
    long_form = m if isinstance(m, Measurement) else None
    return {
        "source_state": video.source_state,
        "stage": stage_of(channel_id, video),
        "visibility": video.visibility,
        "published_at": video.published_at,
        "cost_usd": video.cost_usd,
        "cost_equivalent_usd": video.cost_equivalent_usd,
        "machine_minutes": video.machine_minutes,
        "failure_code": video.failure_code,
        "measured_at": m.measured_at if m else None,
        "window_days": m.window_days if m else None,
        "avd_pct": long_form.avd_pct if long_form else None,
        "views": m.views if m else None,
        "browse_share_pct": long_form.browse_share_pct if long_form else None,
        "subscribers_gained": m.subscribers_gained if m else None,
        "reported_at": reported_at,
    }


def _store_shorts(connection: Connection, video_pk: UUID, measurement: object) -> None:
    """La medición de Shorts de un video se reemplaza entera (o se borra si ya no viene)."""
    connection.execute(delete(shorts).where(shorts.c.pilot_video_id == video_pk))
    values = _shorts_values(measurement if isinstance(measurement, ShortsMeasurement) else None)
    if values is not None:
        connection.execute(shorts.insert().values(pilot_video_id=video_pk, **values))


def submit_report(
    connection: Connection, channel_id: str, report: AnyReport, now: datetime
) -> dict[str, Any]:
    row = _row(connection, report.pilot_id)
    _own(row, channel_id)
    if report.channel_id != channel_id:
        raise PilotError("channel_mismatch")
    if report_format(report) != row["format"]:
        raise PilotError(
            "report_format_mismatch",
            [{"path": "contract", "message": MESSAGES["report_format_mismatch"]}],
        )
    if row["status"] in ("cerrado", "cancelado"):
        raise PilotError("closed")
    if row["status"] == "autorizado":
        raise PilotError("not_delivered")
    upserted = ignored = 0
    for video in report.videos:
        values = _video_values(video, channel_id, report.reported_at)
        stored = connection.execute(
            select(videos.c.id, videos.c.reported_at).where(
                videos.c.pilot_pk == row["id"], videos.c.video_id == video.video_id
            )
        ).one_or_none()
        if stored is None:
            video_pk = uuid4()
            connection.execute(
                videos.insert().values(
                    id=video_pk, pilot_pk=row["id"], video_id=video.video_id, **values
                )
            )
            _store_shorts(connection, video_pk, video.measurement)
            upserted += 1
        elif (
            report.reported_at > stored.reported_at
        ):  # gana el más reciente; si empata se conserva lo guardado
            connection.execute(update(videos).where(videos.c.id == stored.id).values(**values))
            _store_shorts(connection, stored.id, video.measurement)
            upserted += 1
        else:
            ignored += 1
    warnings: list[str] = []
    status = row["status"]
    changes: dict[str, Any] = {"last_report_at": now, "updated_at": now}
    stored_info = row["channel_info"]
    if stored_info is None or report.reported_at >= datetime.fromisoformat(
        stored_info["reported_at"]
    ):
        changes["channel_info"] = _plain(
            {
                "reported_at": report.reported_at,
                "channel_status": report.channel_status,
                "checks": [check.model_dump(mode="json") for check in report.checks],
                "note": report.note,
            }
        )
    if report.videos and status == "entregado":
        status = "en_ejecucion"
        changes.update(status=status, first_report_at=now)
        _log(connection, row["id"], channel_id, "first_report", now)
    if report.channel_status == "closed":
        warnings.append(
            "el canal reporta channel_status=closed; NicheRadar no cierra el piloto solo"
        )
    refreshed = {**dict(row), **changes}
    evaluation = _evaluate(connection, refreshed, now)
    acknowledged = list(row["acknowledged"])
    proposal = rules.proposal(evaluation, acknowledged)
    warnings += evaluation["warnings"]
    if status == "en_ejecucion" and rules.needs_decision(evaluation, acknowledged):
        status = "decision_pendiente"
        changes["status"] = status
        _log(connection, row["id"], "system", "decision_pending", now, proposal=proposal["action"])
    changes["evaluation"] = _plain({**evaluation, "proposal": proposal, "evaluated_at": now})
    connection.execute(update(pilots).where(pilots.c.id == row["id"]).values(**changes))
    return {
        "accepted": True,
        "videos_upserted": upserted,
        "videos_ignored": ignored,
        "warnings": warnings,
        "pilot_status": status,
    }


def get_pilot(
    connection: Connection, pilot_id: str, channel_id: str | None, now: datetime
) -> dict[str, Any]:
    row = _row(connection, pilot_id)
    _own(row, channel_id)
    return _detail(connection, row, now)


def _detail(connection: Connection, row: Any, now: datetime) -> dict[str, Any]:
    evaluation = _evaluate(connection, row, now)
    acknowledged = list(row["acknowledged"])
    contact = (
        tokens.last_contact(connection, row["target_channel"]) if row["target_channel"] else None
    )
    log = connection.execute(
        select(events).where(events.c.pilot_pk == row["id"]).order_by(events.c.at, events.c.seq)
    ).mappings()
    detail: dict[str, Any] = _plain(
        {
            "pilot_id": row["pilot_id"],
            "status": row["status"],
            "niche_label": row["niche_label"],
            "format": row["format"],
            "language": row["language"],
            "target_channel": row["target_channel"],
            "authorized_by": row["authorized_by"],
            "authorized_at": row["authorized_at"],
            "valid_until": row["valid_until"],
            "delivered_at": row["delivered_at"],
            "first_report_at": row["first_report_at"],
            "last_report_at": row["last_report_at"],
            "closed_at": row["closed_at"],
            "channel": row["channel_info"],
            "close_reason": row["close_reason"],
            "channel_last_contact_at": contact,
            "package": row["package"],
            "evaluation": evaluation,
            "proposal": rules.proposal(evaluation, acknowledged),
            "needs_decision": rules.needs_decision(evaluation, acknowledged),
            "acknowledged": acknowledged,
            "events": [
                {"at": e["at"], "actor": e["actor"], "kind": e["kind"], "detail": e["detail"]}
                for e in log
            ],
        }
    )
    return detail


def list_pilots(
    connection: Connection, status: str | None, limit: int, now: datetime
) -> list[dict[str, Any]]:
    query = select(pilots).order_by(pilots.c.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(pilots.c.status == status)
    out = []
    for row in connection.execute(query).mappings():
        evaluation = _evaluate(connection, row, now)
        acknowledged = list(row["acknowledged"])
        contact = (
            tokens.last_contact(connection, row["target_channel"])
            if row["target_channel"]
            else None
        )
        out.append(
            _plain(
                {
                    "pilot_id": row["pilot_id"],
                    "status": row["status"],
                    "niche_label": row["niche_label"],
                    "format": row["format"],
                    "target_channel": row["target_channel"],
                    "authorized_at": row["authorized_at"],
                    "last_report_at": row["last_report_at"],
                    "channel_last_contact_at": contact,
                    "totals": evaluation["totals"],
                    "proposal": rules.proposal(evaluation, acknowledged),
                    "needs_decision": rules.needs_decision(evaluation, acknowledged),
                }
            )
        )
    return out


def decide(
    connection: Connection, pilot_id: str, decision: str, note: str, actor: str, now: datetime
) -> dict[str, Any]:
    """Decisión humana: ``seguir`` o ``cerrar``. NicheRadar solo propone."""
    row = _row(connection, pilot_id)
    status = row["status"]
    if decision == "seguir":
        if status != "decision_pendiente":
            raise PilotError("bad_transition")
        evaluation = _evaluate(connection, row, now)
        reviewed = sorted(
            {
                *row["acknowledged"],
                *(
                    m["key"]
                    for m in evaluation["milestones"]
                    if m["status"] in rules.CONCLUDED | rules.NEEDS_HUMAN
                ),
            }
        )
        connection.execute(
            update(pilots)
            .where(pilots.c.id == row["id"])
            .values(status="en_ejecucion", acknowledged=reviewed, updated_at=now)
        )
        _log(connection, row["id"], actor, "decision_seguir", now, note=note)
        return {"pilot_id": pilot_id, "status": "en_ejecucion"}
    if decision == "cerrar":
        if status in ("cerrado", "cancelado"):
            raise PilotError("closed")
        if status in ("autorizado", "entregado"):
            raise PilotError("bad_transition")  # antes de ejecutar se cancela, no se cierra
        connection.execute(
            update(pilots)
            .where(pilots.c.id == row["id"])
            .values(status="cerrado", closed_at=now, close_reason=note, updated_at=now)
        )
        _log(connection, row["id"], actor, "decision_cerrar", now, note=note)
        return {"pilot_id": pilot_id, "status": "cerrado"}
    raise PilotError("bad_transition")


def cancel(
    connection: Connection, pilot_id: str, reason: str, actor: str, now: datetime
) -> dict[str, Any]:
    row = _row(connection, pilot_id)
    if row["status"] not in ("autorizado", "entregado"):
        raise PilotError("bad_transition")
    connection.execute(
        update(pilots)
        .where(pilots.c.id == row["id"])
        .values(status="cancelado", closed_at=now, close_reason=reason, updated_at=now)
    )
    _log(connection, row["id"], actor, "cancelled", now, reason=reason)
    return {"pilot_id": pilot_id, "status": "cancelado"}


def verify_package(payload: dict[str, Any]) -> bool:
    return payload.get("package_sha256") == package_sha256(payload)


def closing_summary(connection: Connection, pilot_id: str, now: datetime) -> str:
    """Resumen autocontenido de Project Evidence para el Foundry (sin datos del canal)."""
    row = _row(connection, pilot_id)
    if row["status"] != "cerrado":
        raise PilotError("bad_transition")
    detail = _detail(connection, row, now)
    pkg, ev = detail["package"], detail["evaluation"]
    totals = ev["totals"]
    name = row["target_channel"] or row["pilot_id"]
    slug = _slug(row["niche_label"])
    lines = [
        f"# EVD-{name}-{now:%Y-%m-%d}-{slug}",
        "",
        "Resumen de Project Evidence de un piloto cerrado (workflow `pilot-lifecycle`). "
        "Sin datos ni claves del canal; solo lo reportado.",
        "",
        "## Qué se probó",
        f"- Nicho: `{row['niche_label']}` ({row['format']}), idioma `{row['language']}`.",
        f"- Receta: {pkg['recipe']['name']}@{pkg['recipe']['version']}"
        if pkg.get("recipe")
        else "- Receta: ninguna declarada.",
        f"- Dossier: {pkg['dossier']['recommendation']} "
        f"(confianza {pkg['dossier']['confidence']}); "
        f"evidencia del nicho de confianza {pkg['evidence']['confidence']}.",
        f"- Presupuesto autorizado: bajo {pkg['budget']['low']}, "
        f"probable {pkg['budget']['likely']}, "
        f"alto {pkg['budget']['high']} USD, máximo {pkg['budget']['max_videos']} videos.",
        "",
        "## Qué pasó",
        f"- Videos reportados: {totals['videos']} (publicados {totals['published']}, "
        f"medidos {totals['measured']}).",
        f"- Costo real: {totals['spent_usd']} USD. Equivalente de suscripción "
        f"(no es dinero gastado): {totals['equivalent_usd']} USD.",
        f"- Minutos de máquina: {totals['machine_minutes']}"
        + ("" if totals["machine_minutes_complete"] else " (incompleto: faltan videos sin dato)")
        + ".",
        "",
        "## Reglas de parada frente a lo medido",
        *[f"- `{r['id']}`: {r['status']} — {r['detail']}" for r in ev["rules"]],
        "",
        "## Decisión",
        f"- Cerrado el {row['closed_at'].date()} por el humano: {row['close_reason']}",
        "",
        "## Límites",
        "- Con pocos videos medidos esto es una hipótesis, no un cambio de Standard.",
        "- Las cifras de ingreso del nicho son declaradas por vendedores salvo que se indique.",
        "",
    ]
    return "\n".join(lines)
