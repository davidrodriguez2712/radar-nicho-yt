# tests/test_pilot_rules.py
"""Reglas de parada: puras y deterministas. Con pocos casos no se concluye; el humano decide."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from nicheradar.pilots.rules import evaluate, proposal
from tests.pilot_samples import NOW, STOP_RULES


def vid(n: int, avd: str | None = "22", browse: str | None = None, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "video_id": f"v{n:02d}",
        "stage": "measuring" if avd is not None else "published",
        "published_at": NOW - timedelta(days=60 - n),
        "cost_usd": Decimal("0.30"),
        "cost_equivalent_usd": Decimal("1.50"),
        "machine_minutes": 60,
        "avd_pct": Decimal(avd) if avd is not None else None,
        "browse_share_pct": Decimal(browse) if browse is not None else None,
        "views": 100,
        "measured_at": NOW - timedelta(days=1) if avd is not None else None,
    }
    base.update(over)
    return base


def run(
    videos: list[dict[str, Any]],
    now: datetime = NOW,
    rules: Any = None,
    close_after: int = 2,
    authorized_at: datetime | None = None,
) -> Any:
    return evaluate(
        rules or STOP_RULES,
        videos,
        now=now,
        authorized_at=authorized_at or NOW - timedelta(days=90),
        max_videos=10,
        close_after=close_after,
    )


def status(ev: Any, rule_id: str) -> str:
    found: str = next(r["status"] for r in ev["rules"] if r["id"] == rule_id)
    return found


def test_with_no_videos_nothing_is_concluded() -> None:
    ev = run([])
    assert proposal(ev, [])["action"] == "sin_datos_suficientes"
    assert ev["totals"]["videos"] == 0 and ev["totals"]["spent_usd"] == 0


def test_a_rule_waits_for_its_milestone() -> None:
    ev = run(
        [vid(n) for n in range(1, 5)]
    )  # solo 4 videos publicados: el hito del video 10 no llegó
    assert status(ev, "retencion-v10") == "pendiente"
    assert proposal(ev, [])["action"] == "sin_datos_suficientes"


def test_retention_is_met_as_soon_as_enough_cases_pass_at_the_milestone() -> None:
    videos = [vid(n, avd="25" if n <= 3 else "10") for n in range(1, 11)]
    ev = run(videos)
    assert status(ev, "retencion-v10") == "cumple"
    assert proposal(ev, [])["action"] == "seguir"


def test_retention_fails_only_when_it_can_no_longer_be_reached() -> None:
    videos = [vid(n, avd="12" if n <= 9 else "30") for n in range(1, 11)]  # solo 1 de 10 llega a 18
    ev = run(videos)
    assert status(ev, "retencion-v10") == "no_cumple"


def test_unmeasured_videos_keep_the_rule_undecided_instead_of_forcing_a_conclusion() -> None:
    videos = [vid(n, avd="12") for n in range(1, 9)] + [vid(9, avd=None), vid(10, avd=None)]
    ev = run(
        videos
    )  # 8 medidos sin llegar; faltan 2 sin medir: aún podrían dar 2 casos, pero se necesitan 3
    assert status(ev, "retencion-v10") == "no_cumple"
    videos = [vid(n, avd="12") for n in range(1, 7)] + [vid(n, avd=None) for n in range(7, 11)]
    ev = run(videos)  # 4 sin medir pueden alcanzar los 3 casos necesarios
    assert status(ev, "retencion-v10") == "sin_datos_suficientes"
    assert proposal(ev, [])["action"] == "sin_datos_suficientes"


def test_revenue_cannot_be_evaluated_without_data_so_a_human_must_decide() -> None:
    ev = run([vid(1)], now=NOW + timedelta(days=200), authorized_at=NOW - timedelta(days=200))
    assert status(ev, "viabilidad-m6") == "no_evaluable"


def test_two_consecutive_failed_milestones_propose_closing() -> None:
    videos = [vid(n, avd="10", browse="5") for n in range(1, 21)]
    ev = run(videos)
    assert status(ev, "retencion-v10") == "no_cumple" and status(ev, "browse-v20") == "no_cumple"
    out = proposal(ev, [])
    assert out["action"] == "cerrar" and "2" in out["reason"]


def test_one_failed_milestone_is_not_enough_to_close() -> None:
    videos = [vid(n, avd="10") for n in range(1, 11)]
    out = proposal(run(videos), [])
    assert out["action"] != "cerrar"


def test_a_milestone_already_decided_by_the_human_is_not_proposed_again() -> None:
    videos = [vid(n, avd="25") for n in range(1, 11)]
    ev = run(videos)
    assert proposal(ev, [])["action"] == "seguir"
    assert proposal(ev, ["video:10"])["action"] == "sin_datos_suficientes"


def test_browse_share_uses_the_latest_measured_value() -> None:
    videos = [vid(n, avd="25", browse="40") for n in range(1, 21)]
    assert status(run(videos), "browse-v20") == "cumple"
    low = [vid(n, avd="25", browse="40") for n in range(1, 20)] + [vid(20, avd="25", browse="10")]
    assert status(run(low), "browse-v20") == "no_cumple"


def test_pipeline_and_manual_rules() -> None:
    rules = [
        {
            "id": "e2e",
            "text": "x",
            "metric": "pipeline_e2e",
            "comparator": ">=",
            "threshold": None,
            "min_cases": None,
            "milestone": {"kind": "week", "value": 6},
        },
        {
            "id": "humano",
            "text": "y",
            "metric": "manual",
            "comparator": ">=",
            "threshold": None,
            "min_cases": None,
            "milestone": {"kind": "video", "value": 1},
        },
    ]
    ev = run([vid(1)], rules=rules, authorized_at=NOW - timedelta(weeks=7))
    assert status(ev, "e2e") == "cumple" and status(ev, "humano") == "revision_manual"
    ev = run([], rules=rules, authorized_at=NOW - timedelta(weeks=7))
    assert status(ev, "e2e") == "no_cumple"


def test_totals_separate_real_money_from_the_subscription_equivalent() -> None:
    ev = run([vid(1), vid(2, machine_minutes=None, cost_equivalent_usd=None)])
    t = ev["totals"]
    assert t["spent_usd"] == Decimal("0.60") and t["equivalent_usd"] == Decimal("1.50")
    assert t["machine_minutes"] == 60 and t["machine_minutes_complete"] is False
    assert t["published"] == 2 and t["measured"] == 2


def test_exceeding_max_videos_is_a_warning_not_a_conclusion() -> None:
    ev = evaluate(
        STOP_RULES,
        [vid(n) for n in range(1, 13)],
        now=NOW,
        authorized_at=NOW - timedelta(days=90),
        max_videos=10,
        close_after=2,
    )
    assert any("max_videos" in w for w in ev["warnings"])
