import re
from datetime import UTC, datetime

import pytest

from nicheradar.subniche_api import MESSAGES as API_MESSAGES
from nicheradar.web.proposals import (
    GENERIC_ERROR,
    error_text,
    idempotency_key,
    new_nonce,
    parse_form,
    proposal_view,
)
from nicheradar.web.security import Session, SessionSigner

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def signer_and_session(key: bytes = b"k" * 32) -> tuple[SessionSigner, Session]:
    signer = SessionSigner(key)
    session = signer.read(signer.issue())
    assert session is not None
    return signer, session


def test_new_nonce_is_16_random_bytes_in_hex() -> None:
    first, second = new_nonce(), new_nonce()
    assert re.fullmatch(r"[0-9a-f]{32}", first) and first != second


def test_idempotency_key_is_stable_and_valid_for_the_api() -> None:
    signer, session = signer_and_session()
    key = idempotency_key(signer, session, "abc")
    assert key == idempotency_key(signer, session, "abc")
    assert re.fullmatch(r"nr-[0-9a-f]{40}", key) and 8 <= len(key) <= 100


def test_idempotency_key_changes_with_nonce_and_with_session() -> None:
    signer, session = signer_and_session()
    other_signer = SessionSigner(b"k" * 32)
    other = other_signer.read(other_signer.issue())
    assert other is not None
    assert idempotency_key(signer, session, "a") != idempotency_key(signer, session, "b")
    assert idempotency_key(signer, session, "a") != idempotency_key(other_signer, other, "a")


def test_parse_form_trims_and_builds_the_body() -> None:
    assert parse_form("  dinosaurios  ", False, "", "", "") == ({"input": "dinosaurios"}, None)


@pytest.mark.parametrize("raw", ["ab", "  ab  ", "x" * 501, "", "   ", "hola\x00mundo"])
def test_parse_form_rejects_bad_input(raw: str) -> None:
    body, error = parse_form(raw, False, "", "", "")
    assert error == "input_invalid" and body == {}


def test_parse_form_accepts_the_limits() -> None:
    assert parse_form("abc", False, "", "", "")[1] is None
    assert parse_form("x" * 500, False, "", "", "")[1] is None


def test_parse_form_manual_mode() -> None:
    body, error = parse_form(" criaturas ", True, " Criaturas ", "animales", " ")
    assert error is None
    assert body == {
        "input": "criaturas",
        "manual": {"label": "Criaturas", "family": "animales", "parent": None},
    }
    body, _ = parse_form("criaturas", True, "Criaturas", "animales", "historia")
    assert body["manual"]["parent"] == "historia"


@pytest.mark.parametrize(
    ("label", "family", "parent"),
    [
        ("ab", "animales", ""),
        ("x" * 121, "animales", ""),
        ("Criaturas", "Animales", ""),
        ("Criaturas", "1animales", ""),
        ("Criaturas", "a", ""),
        ("Criaturas", "a" * 41, ""),
        ("Criaturas", "animales", "p" * 61),
        ("Cria\x00turas", "animales", ""),
        ("Criaturas", "animales", "pa\x00dre"),
    ],
)
def test_parse_form_manual_rejects_bad_fields(label: str, family: str, parent: str) -> None:
    body, error = parse_form("criaturas", True, label, family, parent)
    assert error == "manual_invalid" and body == {}


def test_manual_fields_are_ignored_when_not_manual() -> None:
    assert parse_form("criaturas", False, "x", "MAL", "p" * 99) == ({"input": "criaturas"}, None)


def test_error_text_uses_the_fixed_dictionary() -> None:
    for code in (
        "youtube_not_configured",
        "youtube_quota_exhausted",
        "youtube_unreachable",
        "duplicate",
        "daily_limit",
        "invalid_input",
    ):
        assert error_text(code) == API_MESSAGES[code]


def test_error_text_normalizes_duplicates_and_unknowns() -> None:
    assert error_text("duplicate:query:abc") == API_MESSAGES["duplicate"]
    assert error_text("whatever") == GENERIC_ERROR
    assert error_text("unknown") == GENERIC_ERROR
    assert error_text(None) == GENERIC_ERROR
    assert error_text("<script>") == GENERIC_ERROR


def item(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "7",
        "status": "queued",
        "kind": "query",
        "input": "dinosaurios",
        "created_at": "2026-11-05T11:00:00Z",
        "finished_at": None,
        "error": None,
        "hypothesis": None,
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("queued", "en_cola"),
        ("running", "preparando"),
        ("succeeded", "lista"),
        ("failed", "fallida"),
    ],
)
def test_proposal_view_maps_the_status(status: str, state: str) -> None:
    assert proposal_view(item(status=status), "UTC")["state"] == state


@pytest.mark.parametrize(
    ("kind", "label"), [("query", "Consulta"), ("video", "Video"), ("channel", "Canal")]
)
def test_proposal_view_kind_label(kind: str, label: str) -> None:
    assert proposal_view(item(kind=kind), "UTC")["kind_label"] == label


def test_proposal_view_survives_garbage() -> None:
    for garbage in ({}, {"status": "rarísimo"}, {"status": 3, "kind": [], "input": None}):
        view = proposal_view(garbage, "UTC")
        assert view["state"] == "fallida"
        assert view["kind_label"] == "—" and view["input"] == "—"
        assert view["hypothesis"] is None
    assert proposal_view("nope", "UTC")["state"] == "fallida"


def test_proposal_view_error_is_fixed_text_never_the_api_text() -> None:
    failed = item(
        status="failed",
        error={"code": "youtube_unreachable", "message": "<b>Traza interna</b>"},
    )
    assert proposal_view(failed, "UTC")["error"] == API_MESSAGES["youtube_unreachable"]
    odd = item(status="failed", error={"code": "boom", "message": "secreto"})
    assert proposal_view(odd, "UTC")["error"] == GENERIC_ERROR
    assert proposal_view(item(status="failed", error="texto"), "UTC")["error"] == GENERIC_ERROR
    assert proposal_view(item(), "UTC")["error"] is None


def test_proposal_view_hypothesis_caps_and_cleans_lists() -> None:
    hypothesis = {
        "slug": "dinos",
        "label": "Dinosaurios",
        "family": "animales",
        "parent_niche": None,
        "queries": [f"q{n}" for n in range(30)],
        "seed_channels": [f"UC{n}" for n in range(30)] + [None, 5],
        "status": "proposed",
    }
    view = proposal_view(item(status="succeeded", hypothesis=hypothesis), "UTC")["hypothesis"]
    assert view["slug"] == "dinos" and view["label"] == "Dinosaurios"
    assert view["family"] == "animales" and view["parent_niche"] is None
    assert len(view["queries"]) == 20 and len(view["seed_channels"]) == 20


def test_proposal_view_hypothesis_tolerates_missing_fields() -> None:
    view = proposal_view(item(hypothesis={"queries": "no es lista"}), "UTC")["hypothesis"]
    assert view["slug"] == "—" and view["queries"] == [] and view["seed_channels"] == []


def test_proposal_view_hostile_text_stays_plain_data() -> None:
    view = proposal_view(item(input="<script>alert(1)</script>"), "UTC")
    assert view["input"] == "<script>alert(1)</script>"  # the template escapes it


def test_finished_ago_reads_the_finish_moment() -> None:
    done = item(status="succeeded", finished_at="2026-11-05T11:55:00Z")
    assert proposal_view(done, "UTC", NOW)["finished_ago"] == "hace 5 min"
    assert proposal_view(item(), "UTC", NOW)["finished_ago"] == "—"
