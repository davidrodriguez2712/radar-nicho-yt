# tests/test_pilot_contracts.py
import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import timedelta
from typing import Any

import pytest

from nicheradar.pilots.contracts import (
    Problem,
    canonical_json,
    package_sha256,
    stage_of,
    validate_package,
    validate_report,
    with_sha256,
)
from nicheradar.pilots.translation import translate
from tests.pilot_samples import NOW, iso, package, package_body, report, video


def paths(problems: Sequence[Problem]) -> set[str]:
    return {item["path"] for item in problems}


def test_a_valid_package_is_accepted_and_keeps_its_hash() -> None:
    parsed, problems = validate_package(package(), NOW)
    assert problems == [] and parsed is not None
    assert parsed.package_sha256 == package_sha256(package())


def test_the_hash_ignores_key_order_and_whitespace_and_detects_any_change() -> None:
    body = package()
    reordered = json.loads(json.dumps(dict(reversed(list(body.items()))), indent=3))
    assert package_sha256(reordered) == body["package_sha256"]
    assert canonical_json({"b": 1, "a": [1, 2]}) == b'{"a":[1,2],"b":1}'
    tampered = deepcopy(body)
    tampered["budget"]["high"] = 42
    assert package_sha256(tampered) != body["package_sha256"]
    _, problems = validate_package(tampered, NOW)
    assert "package_sha256" in paths(problems)


def test_unknown_keys_are_rejected_without_echoing_them() -> None:
    _, problems = validate_package(package(secret_key_xyz=1), NOW)
    assert any(item["path"] == "(campo no permitido)" for item in problems)
    assert "secret_key_xyz" not in json.dumps(problems)


@pytest.mark.parametrize(
    ("override", "path"),
    [
        ({"pilot_id": "pil_2026_x"}, "pilot_id"),
        ({"target_channel": "historias"}, "target_channel"),
        ({"close_after_failed_milestones": 0}, "close_after_failed_milestones"),
        ({"valid_until": "2026-10-01T00:00:00Z"}, "valid_until"),
        (
            {"authorized_at": "2026-12-01T00:00:00Z", "valid_until": "2026-12-20T00:00:00Z"},
            "authorized_at",
        ),
        ({"niche": {"label": "x", "format": "long", "language": "ingles"}}, "niche.language"),
    ],
)
def test_rejects_invalid_fields(override: dict[str, Any], path: str) -> None:
    _, problems = validate_package(package(**override), NOW)
    assert path in paths(problems)


def test_the_language_has_no_default() -> None:
    body = package_body()
    del body["niche"]["language"]
    from nicheradar.pilots.contracts import with_sha256

    _, problems = validate_package(with_sha256(body), NOW)
    assert "niche.language" in paths(problems)


def test_budget_must_be_ordered_and_stop_rules_unique() -> None:
    body = package_body()
    body["budget"]["low"], body["budget"]["high"] = 50, 3
    from nicheradar.pilots.contracts import with_sha256

    _, problems = validate_package(with_sha256(body), NOW)
    assert "budget" in paths(problems)
    dup = package_body()
    dup["stop_rules"][1]["id"] = dup["stop_rules"][0]["id"]
    _, problems = validate_package(with_sha256(dup), NOW)
    assert "stop_rules" in paths(problems)


def test_a_threshold_is_required_for_measurable_rules_and_null_for_manual_ones() -> None:
    from nicheradar.pilots.contracts import with_sha256

    body = package_body()
    body["stop_rules"][0]["threshold"] = None
    _, problems = validate_package(with_sha256(body), NOW)
    assert "stop_rules.0.threshold" in paths(problems)
    manual = package_body()
    manual["stop_rules"] = [
        {
            "id": "ok",
            "text": "Revision humana",
            "metric": "manual",
            "comparator": ">=",
            "threshold": None,
            "min_cases": None,
            "milestone": {"kind": "week", "value": 6},
        }
    ]
    parsed, problems = validate_package(with_sha256(manual), NOW)
    assert problems == [] and parsed is not None


def test_low_confidence_requires_declared_unknowns() -> None:
    from nicheradar.pilots.contracts import with_sha256

    body = package_body()
    body["evidence"]["confidence"] = "low"
    body["dossier"]["unknowns"] = []
    _, problems = validate_package(with_sha256(body), NOW)
    assert "dossier.unknowns" in paths(problems)


def test_a_valid_report_is_accepted() -> None:
    parsed, problems = validate_report(report(), NOW)
    assert problems == [] and parsed is not None and parsed.videos[0].video_id == "v_20261103_a1b2"


def test_a_report_rejects_duplicates_future_dates_and_unknown_keys() -> None:
    _, problems = validate_report(report(video(), video()), NOW)
    assert "videos" in paths(problems)
    _, problems = validate_report(report(reported_at=iso(NOW + timedelta(hours=1))), NOW)
    assert "reported_at" in paths(problems)
    _, problems = validate_report(report(extra_secret="x"), NOW)
    assert any(item["path"] == "(campo no permitido)" for item in problems)


def test_report_coherence_rules() -> None:
    no_pub = video(published_at=None)  # medido sin fecha de publicacion
    _, problems = validate_report(report(no_pub), NOW)
    assert any(p.startswith("videos.0") for p in paths(problems))
    killed = video(
        source_state="KILL",
        measurement=None,
        published_at=None,
        visibility="private",
        failure_code=None,
    )
    _, problems = validate_report(report(killed), NOW)
    assert "videos.0.failure_code" in paths(problems)
    bad_time = video()
    bad_time["measurement"]["measured_at"] = iso(NOW - timedelta(days=30))
    _, problems = validate_report(report(bad_time), NOW)
    assert "videos.0.measurement.measured_at" in paths(problems)


def test_a_measuring_video_must_be_public_after_translation() -> None:
    _, problems = validate_report(report(video(visibility="unknown")), NOW)
    assert "videos.0.visibility" in paths(problems)


def test_published_state_with_unknown_visibility_is_not_guessed() -> None:
    sent = video(source_state="PUBLICADO", visibility="unknown", measurement=None)
    parsed, problems = validate_report(report(sent), NOW)
    assert problems == [] and parsed is not None
    assert stage_of("canal-historias", parsed.videos[0]) == "unknown"


def test_state_translation_table_and_unknown_fallback() -> None:
    assert translate("canal-historias", "EN_MEDICION", "public") == "measuring"
    assert translate("canal-historias", "FALLO_QA", "private") == "blocked"
    assert translate("canal-historias", "PUBLICADO", "private") == "uploaded"
    assert translate("canal-historias", "PUBLICADO", "public") == "published"
    assert translate("canal-historias", "ESTADO_NUEVO", "public") == "unknown"
    assert translate("canal-otro", "EN_MEDICION", "public") == "unknown"


def test_checks_are_optional_unique_and_bounded() -> None:
    check = {"id": "voice_ref", "label": "Voz", "ok": True, "detail": None, "expires_at": None}
    parsed, problems = validate_report(report(video(), checks=[check]), NOW)
    assert problems == [] and parsed is not None and parsed.checks[0].id == "voice_ref"
    _, problems = validate_report(report(video(), checks=[check, check]), NOW)
    assert "checks" in paths(problems)


def test_ctr_and_impressions_do_not_exist_in_v1() -> None:
    v = video()
    v["measurement"]["ctr_pct"] = 4.0
    _, problems = validate_report(report(v), NOW)
    assert any(item["path"].endswith("(campo no permitido)") for item in problems)


def test_errors_never_echo_submitted_values() -> None:
    v = video(video_id="valor-secreto con espacios")
    _, problems = validate_report(report(v), NOW)
    assert problems and "valor-secreto" not in json.dumps(problems)


def test_at_most_100_videos_and_50_problems() -> None:
    many = [video(f"v_{i}") for i in range(101)]
    _, problems = validate_report(report(*many), NOW)
    assert "videos" in paths(problems)
    broken = [video(f"v_{i}", cost_usd=-1) for i in range(80)]
    _, problems = validate_report(report(*broken), NOW)
    assert len(problems) <= 50


def test_the_evidence_carries_the_language_mix_and_it_must_add_up() -> None:
    body = package_body()
    body["evidence"]["language_mix"] = [
        {"language": "en", "share_pct": 80},
        {"language": "es", "share_pct": 15},
        {"language": "unknown", "share_pct": 5},
    ]
    parsed, problems = validate_package(with_sha256(body), NOW)
    assert problems == [] and parsed is not None
    body["evidence"]["language_mix"][0]["share_pct"] = 50
    _, problems = validate_package(with_sha256(body), NOW)
    assert "evidence.language_mix" in paths(problems)
    body["evidence"]["language_mix"] = [{"language": "ingles", "share_pct": 100}]
    _, problems = validate_package(with_sha256(body), NOW)
    assert "evidence.language_mix.0.language" in paths(problems)
    del body["evidence"]["language_mix"]
    _, problems = validate_package(with_sha256(body), NOW)
    assert "evidence.language_mix" in paths(problems)
