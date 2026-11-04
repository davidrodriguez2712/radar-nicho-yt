# tests/test_web_calibration.py
import copy
import math
from datetime import UTC, datetime
from typing import Any

import pytest

from nicheradar.web.calibration import Calibration, parse_calibration, streak, view
from tests.web_helpers import dossier_v1, dossier_v2, dossier_v3, pilot_video

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
STATEMENT = dossier_v3()["calibration"]["exit_criterion"]["statement"]


def calib(**over: Any) -> Calibration:
    base: dict[str, Any] = {
        "videos_planned": 6,
        "setup_hours": 8.0,
        "max_minutes": 60,
        "consecutive": 3,
        "statement": "tres videos seguidos bajo 60 minutos",
        "steps": [("Guion", 40), ("Voz", 10), ("Edición", 45)],
        "regime_minutes": 20,
    }
    return Calibration(**(base | over))


def vids(*minutes: object, method: str | None = None) -> list[dict[str, object]]:
    return [
        pilot_video(
            f"v{i}", human_minutes=m, human_minutes_method=method if m is not None else None
        )
        for i, m in enumerate(minutes, 1)
    ]


# ---- parse_calibration ----------------------------------------------------------------------


def test_parse_reads_the_calibration_block_of_a_v3_dossier() -> None:
    result = parse_calibration(dossier_v3())
    assert result == Calibration(
        videos_planned=6,
        setup_hours=8.0,
        max_minutes=60,
        consecutive=3,
        statement=STATEMENT,
        steps=[("Guion", 40), ("Voz", 10), ("Edición", 45)],
        regime_minutes=55,
    )


@pytest.mark.parametrize("maker", [dossier_v1, dossier_v2])
def test_parse_is_none_for_dossiers_without_calibration(maker: Any) -> None:
    assert parse_calibration(maker()) is None


def test_parse_is_none_for_a_v3_that_lost_its_calibration() -> None:
    dossier = dossier_v3()
    del dossier["calibration"]
    assert parse_calibration(dossier) is None


@pytest.mark.parametrize("junk", [None, 3, "x", [], [dossier_v3()], {}])
def test_parse_never_raises_on_something_that_is_not_a_dossier(junk: object) -> None:
    assert parse_calibration(junk) is None


def mutate(path: list[str], value: object) -> dict[str, Any]:
    dossier = copy.deepcopy(dossier_v3())
    node: Any = dossier["calibration"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return dossier


@pytest.mark.parametrize(
    "path,value",
    [
        (["videos"], "6"),
        (["videos"], None),
        (["videos"], True),
        (["setup_hours"], "8"),
        (["setup_hours"], math.nan),
        (["setup_hours"], -1),
        (["exit_criterion"], "x"),
        (["exit_criterion", "max_minutes_per_video"], "60"),
        (["exit_criterion", "max_minutes_per_video"], 0),
        (["exit_criterion", "max_minutes_per_video"], math.inf),
        (["exit_criterion", "consecutive_videos"], 0),
        (["exit_criterion", "consecutive_videos"], 2.5),
        (["exit_criterion", "consecutive_videos"], False),
        (["exit_criterion", "statement"], 5),
        (["exit_criterion", "statement"], ""),
        (["minutes_by_step"], []),
        (["minutes_by_step"], "x"),
        (["minutes_by_step"], [{"step": 1, "minutes_per_video": 3}]),
        (["minutes_by_step"], [{"step": "A", "minutes_per_video": "3"}]),
        (["minutes_by_step"], ["x"]),
    ],
)
def test_parse_is_none_when_a_field_has_the_wrong_type(path: list[str], value: object) -> None:
    assert parse_calibration(mutate(path, value)) is None


def test_parse_is_none_when_the_calibration_is_not_an_object() -> None:
    dossier = dossier_v3()
    dossier["calibration"] = [1, 2]
    assert parse_calibration(dossier) is None


def test_parse_keeps_the_regime_empty_when_the_flow_is_unreadable() -> None:
    dossier = dossier_v3()
    dossier["production_flow"] = "x"
    result = parse_calibration(dossier)
    assert result is not None and result.regime_minutes is None


# ---- streak ---------------------------------------------------------------------------------


def test_streak_counts_only_the_final_run() -> None:
    assert streak([92, 71, 58], 60) == 1
    assert streak([58, 59, 55], 60) == 3
    assert streak([58, 59, 91], 60) == 0
    assert streak([], 60) == 0


def test_streak_a_missing_measure_cuts_the_run() -> None:
    assert streak([58, None, 55], 60) == 1
    assert streak([58, 59, None], 60) == 0
    assert streak([None, 58, 59], 60) == 2


def test_streak_the_threshold_itself_meets_the_criterion_ruling_4() -> None:
    assert streak([60, 60, 60], 60) == 3
    assert streak([61, 60], 60) == 1
    assert streak([60, 61], 60) == 0


def test_streak_ignores_negative_and_non_finite_values_as_not_measured() -> None:
    assert streak([58, 0, 55], 60) == 3  # a measured zero is a valid measure
    assert streak([58, -5, 55], 60) == 1
    assert streak([58, math.nan, 55], 60) == 1
    assert streak([58, math.inf, 55], 60) == 1
    assert streak([58, True, 55], 60) == 1
    assert streak([58, "59", 55], 60) == 1


def test_a_huge_or_out_of_contract_minute_count_is_not_measured_and_never_overflows() -> None:
    assert streak([58, 10**400, 55], 60) == 1  # above the contract range 0..100000: not measured
    assert streak([58, 100_001, 55], 60) == 1
    result = view(calib(), vids(10**400, 100_000), NOW, "UTC")
    assert result["rows"][0]["text"] == "sin medir"
    assert result["rows"][1]["text"] == "100000 min"


# ---- view -----------------------------------------------------------------------------------


def test_view_rows_are_measured_pending_and_unmeasured() -> None:
    result = view(calib(), vids(92, None, 58), NOW, "UTC")
    assert [(r["label"], r["text"]) for r in result["rows"]] == [
        ("Video 1", "92 min"),
        ("Video 2", "sin medir"),
        ("Video 3", "58 min"),
        ("Video 4", "pendiente"),
        ("Video 5", "pendiente"),
        ("Video 6", "pendiente"),
    ]
    assert [r["state"] for r in result["rows"]] == [
        "over",
        "unmeasured",
        "ok",
        "pending",
        "pending",
        "pending",
    ]
    assert result["incomplete"] is True


def test_view_streak_text_and_the_proposal_to_pass() -> None:
    low = view(calib(), vids(92, 71, 58), NOW, "UTC")
    assert low["streak"] == 1
    assert low["streak_text"] == "Racha de hasta 60 minutos: 1 de 3"
    assert low["passes"] is False
    done = view(calib(), vids(58, 59, 55), NOW, "UTC")
    assert done["streak_text"] == "Racha de hasta 60 minutos: 3 de 3"
    assert done["passes"] is True


def test_view_the_threshold_video_counts_and_passes() -> None:
    result = view(calib(), vids(60, 60, 60), NOW, "UTC")
    assert result["passes"] is True


def test_view_fewer_videos_than_the_streak_asks_never_passes() -> None:
    result = view(calib(consecutive=3), vids(50, 50), NOW, "UTC")
    assert result["streak"] == 2 and result["passes"] is False


def test_view_with_no_videos_has_every_row_pending_and_nothing_measured() -> None:
    result = view(calib(), [], NOW, "UTC")
    assert {r["text"] for r in result["rows"]} == {"pendiente"}
    assert result["measured"] is False
    assert result["hours_text"] is None
    assert result["last_video"] is None
    assert result["streak_text"] == "Racha de hasta 60 minutos: 0 de 3"
    assert result["incomplete"] is False


def test_view_more_videos_than_planned_are_all_listed() -> None:
    result = view(calib(videos_planned=2), vids(50, 50, 50, 50), NOW, "UTC")
    assert [r["label"] for r in result["rows"]] == ["Video 1", "Video 2", "Video 3", "Video 4"]
    assert result["streak"] == 4


def test_view_caps_the_rows_at_one_hundred() -> None:
    result = view(calib(videos_planned=12), vids(*([50] * 150)), NOW, "UTC")
    assert len(result["rows"]) == 100
    assert result["capped"] is True


def test_streak_a_measured_zero_counts() -> None:
    assert streak([0, 0, 0], 60) == 3
    assert streak([0, 0, 61], 60) == 0


def test_view_three_measured_zeros_pass_and_render_zero_minutes() -> None:
    result = view(calib(), vids(0, 0, 0), NOW, "UTC")
    assert result["streak"] == 3 and result["passes"] is True
    assert [(r["text"], r["state"]) for r in result["rows"][:3]] == [("0 min", "ok")] * 3
    assert result["measured"] is True and result["incomplete"] is False


def test_view_hours_are_the_setup_plus_the_measured_minutes_against_the_planned() -> None:
    # planned: 8 + 6 * 95 / 60 = 17.5 h; done: 8 + (92 + 71 + 58) / 60 = 11.68 h
    result = view(calib(), vids(92, 71, 58), NOW, "UTC", status="en_ejecucion")
    assert result["hours_text"] == "Horas de calibración hasta hoy: 11,7 h de 17,5 previstas"
    assert result["setup_text"] == "8 h"


def test_view_hours_say_incomplete_when_a_video_has_no_measure() -> None:
    result = view(calib(), vids(60, None), NOW, "UTC", status="en_ejecucion")
    assert result["hours_text"] == "Horas de calibración hasta hoy: 9 h de 17,5 previstas"
    assert result["hours_incomplete"] is True


def test_view_ignores_bad_values_in_the_hours_and_marks_them() -> None:
    result = view(calib(), vids(-5, math.nan, 60), NOW, "UTC", status="cerrado")
    assert [r["text"] for r in result["rows"][:3]] == ["sin medir"] * 2 + ["60 min"]
    assert result["hours_text"] == "Horas de calibración hasta hoy: 9 h de 17,5 previstas"
    assert result["incomplete"] is True


def test_view_regime_text_only_exists_with_the_flow() -> None:
    assert view(calib(regime_minutes=20), [], NOW, "UTC")["regime_text"] == (
        "Régimen que buscamos: 20 min por video"
    )
    assert view(calib(regime_minutes=None), [], NOW, "UTC")["regime_text"] is None


def test_view_setup_hours_are_omitted_when_the_dossier_has_none() -> None:
    assert view(calib(setup_hours=0), [], NOW, "UTC")["setup_text"] is None


def test_view_method_label_one_method_or_mixed() -> None:
    one = view(calib(), vids(50, 50, method="gate_waits"), NOW, "UTC")
    assert one["method_text"] == "estimado (método gate_waits)"
    mixed = vids(50, 50)
    mixed[0]["human_minutes_method"] = "gate_waits"
    mixed[1]["human_minutes_method"] = "session_logs"
    assert view(calib(), mixed, NOW, "UTC")["method_text"] == "métodos mezclados"
    assert view(calib(), vids(None, None), NOW, "UTC")["method_text"] is None


def test_view_method_name_is_text_and_is_capped() -> None:
    result = view(calib(), vids(50, method="x" * 500), NOW, "UTC")
    assert len(result["method_text"]) < 120


def test_view_last_video_has_its_minutes_and_day() -> None:
    result = view(calib(), vids(92, 58), NOW, "UTC")
    assert result["last_video"] == "Video 2 · 58 min · 5 nov"


def test_view_last_video_unmeasured() -> None:
    result = view(calib(), vids(92, None), NOW, "UTC")
    assert result["last_video"] == "Video 2 · sin medir · 5 nov"


def test_view_warning_only_when_a_measured_video_went_over_and_the_streak_is_short() -> None:
    over = view(calib(), vids(92, 71), NOW, "UTC")
    assert over["warning"] == (
        "Algún video pasó de 60 minutos",
        "Es normal en calibración",
    )
    assert view(calib(), vids(50, 50), NOW, "UTC")["warning"] is None
    assert view(calib(), vids(92, 50, 50, 50), NOW, "UTC")["warning"] is None
    assert view(calib(), vids(None), NOW, "UTC")["warning"] is None


def test_view_tolerates_garbage_videos() -> None:
    junk: list[Any] = [
        "x",
        3,
        None,
        {"human_minutes": "5", "published_at": "2026-11-05T12:00:00Z"},
        {"human_minutes": 7},  # no published_at: not a published video
        pilot_video(human_minutes=58),
    ]
    result = view(calib(), junk, NOW, "UTC")
    assert [r["text"] for r in result["rows"][:2]] == ["sin medir", "58 min"]


def test_view_steps_are_exposed_as_text_pairs() -> None:
    result = view(calib(), [], NOW, "UTC")
    assert result["steps"] == [("Guion", 40), ("Voz", 10), ("Edición", 45)]


def test_view_setup_is_done_only_once_the_pilot_runs() -> None:
    for status in ("en_ejecucion", "decision_pendiente", "cerrado"):
        result = view(calib(), vids(60), NOW, "UTC", status=status)
        assert result["setup_label"] == "Preparación del canal (hecha)"
        assert result["hours_text"] == "Horas de calibración hasta hoy: 9 h de 17,5 previstas"


def test_view_setup_is_planned_before_that_and_the_hours_say_so() -> None:
    for status in ("entregado", "autorizado", "otro", None):
        result = view(calib(), vids(60), NOW, "UTC", status=status)
        assert result["setup_label"] == "Preparación del canal (prevista)"
        assert result["hours_text"] == (
            "Horas de calibración hasta hoy: 9 h de 17,5 previstas (incluye preparación prevista)"
        )


def test_view_uses_only_published_videos_a_draft_at_the_end_does_not_cut_the_streak() -> None:
    videos = vids(40, 40, 40, 40)
    videos[3]["published_at"] = None
    result = view(calib(), videos, NOW, "UTC", status="en_ejecucion")
    assert result["streak"] == 3 and result["passes"] is True
    assert [r["text"] for r in result["rows"][:4]] == ["40 min"] * 3 + ["pendiente"]
    assert result["last_video"] == "Video 3 · 40 min · 5 nov"
    assert result["incomplete"] is False
    assert result["hours_text"] == "Horas de calibración hasta hoy: 10 h de 17,5 previstas"


def test_view_drops_videos_whose_published_at_is_missing_or_unparseable() -> None:
    videos = vids(40, 40, 40, 40, 40)
    videos[0]["published_at"] = None
    videos[1]["published_at"] = "ayer"
    videos[2]["published_at"] = 5
    del videos[3]["published_at"]
    result = view(calib(), videos, NOW, "UTC")
    assert result["streak"] == 1
    assert result["rows"][0]["text"] == "40 min"
    assert {r["text"] for r in result["rows"][1:]} == {"pendiente"}


def test_view_method_comes_only_from_measured_videos() -> None:
    videos = vids(None, None)
    videos[0]["human_minutes_method"] = "gate_waits"
    assert view(calib(), videos, NOW, "UTC")["method_text"] is None
    videos[1]["human_minutes"] = 50
    assert view(calib(), videos, NOW, "UTC")["method_text"] is None
    videos[1]["human_minutes_method"] = "claude_sessions"
    assert view(calib(), videos, NOW, "UTC")["method_text"] == "estimado (método claude_sessions)"


# ---- lower bound (method claude_sessions_plus_assumed) ---------------------------------------

LOWER = "claude_sessions_plus_assumed"


def test_a_lower_bound_method_turns_the_streak_into_a_possible_one() -> None:
    result = view(calib(), vids(58, 59, 55, method=LOWER), NOW, "UTC")
    assert result["lower_bound"] is True
    assert result["method_text"] == f"mínimo estimado (método {LOWER})"
    assert result["streak_text"] == (
        "Racha de hasta 60 minutos: 3 de 3 (posible: las cifras son un mínimo)"
    )
    assert [r["text"] for r in result["rows"][:3]] == ["≥ 58 min", "≥ 59 min", "≥ 55 min"]
    assert result["passes"] is True
    assert result["last_video"].startswith("Video 3 · ≥ 55 min")


def test_another_method_or_none_keeps_the_current_texts() -> None:
    other = view(calib(), vids(58, 59, 55, method="gate_waits"), NOW, "UTC")
    assert other["lower_bound"] is False
    assert other["method_text"] == "estimado (método gate_waits)"
    assert other["streak_text"] == "Racha de hasta 60 minutos: 3 de 3"
    assert [r["text"] for r in other["rows"][:3]] == ["58 min", "59 min", "55 min"]
    none = view(calib(), vids(58, 59, 55), NOW, "UTC")
    assert none["lower_bound"] is False and none["method_text"] is None


def test_mixed_methods_including_the_lower_bound_one_are_a_lower_bound() -> None:
    videos = vids(50, 50)
    videos[0]["human_minutes_method"] = "gate_waits"
    videos[1]["human_minutes_method"] = LOWER
    result = view(calib(), videos, NOW, "UTC")
    assert result["lower_bound"] is True
    assert result["method_text"] == "métodos mezclados"
    assert result["rows"][0]["text"] == "≥ 50 min"


def test_lower_bound_never_marks_unmeasured_and_keeps_a_measured_zero() -> None:
    videos = vids(None, 0, method=LOWER)
    videos[0]["human_minutes_method"] = LOWER  # unmeasured rows say nothing
    result = view(calib(), videos, NOW, "UTC")
    assert result["lower_bound"] is True
    assert [r["text"] for r in result["rows"][:3]] == ["sin medir", "≥ 0 min", "pendiente"]
    only_unmeasured = vids(None, None)
    only_unmeasured[0]["human_minutes_method"] = LOWER
    assert view(calib(), only_unmeasured, NOW, "UTC")["lower_bound"] is False


def test_lower_bound_does_not_change_the_numbers() -> None:
    plain = view(calib(), vids(92, 58, 59, method="gate_waits"), NOW, "UTC")
    lower = view(calib(), vids(92, 58, 59, method=LOWER), NOW, "UTC")
    for key in ("streak", "passes", "measured", "incomplete", "hours_text", "warning"):
        assert plain[key] == lower[key]
