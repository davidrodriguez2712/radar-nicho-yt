# tests/test_subniche_store.py
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection

from nicheradar.subniche_discovery.contracts import (
    HypothesisDraft,
    normalize_query,
    slugify,
)
from nicheradar.subniche_discovery.store import (
    DuplicateHypothesis,
    InvalidTransition,
    UnknownHypothesis,
    approve,
    create_proposed,
    due_hypotheses,
    export_yaml,
    get_hypothesis,
    list_hypotheses,
    mark_measured,
    request_remeasure,
    set_finalist,
    set_status,
    unique_slug,
)
from tests.subniche_samples import NOW, draft

SEED = "UC" + "s" * 22


def test_normalize_query_lowercases_and_strips_punctuation() -> None:
    assert normalize_query("  History,  REVENGE!! ") == "history revenge"


def test_slugify_is_snake_case_and_bounded() -> None:
    assert slugify("Deep-Sea Mysteries & Co.") == "deep_sea_mysteries_co"
    assert len(slugify("x" * 200)) == 60


def test_draft_normalizes_and_rejects_bad_queries() -> None:
    assert draft(queries=("History Revenge!",)).queries == ("history revenge",)
    with pytest.raises(ValidationError):
        draft(queries=("see https://evil.example",))
    with pytest.raises(ValidationError):
        draft(queries=("a", "history revenge"))
    with pytest.raises(ValidationError):
        draft(queries=("one query", "two query", "three query", "four query"))
    with pytest.raises(ValidationError):
        draft(queries=("same words", "Same Words"))


def test_draft_validates_slug_and_seed_channel_ids() -> None:
    with pytest.raises(ValidationError):
        draft(slug="Bad Slug")
    with pytest.raises(ValidationError):
        draft(seeds=("not-a-channel",))
    assert isinstance(draft(seeds=(SEED,)), HypothesisDraft)


@pytest.mark.postgres
def test_create_then_approve_moves_proposed_to_active(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    assert get_hypothesis(db, "history_revenge")["status"] == "proposed"
    approve(db, "history_revenge", NOW)
    row = get_hypothesis(db, "history_revenge")
    assert row["status"] == "active" and row["approved_at"] == NOW


@pytest.mark.postgres
def test_duplicate_query_slug_or_seed_channel_is_rejected(db: Connection) -> None:
    create_proposed(db, draft(seeds=(SEED,)), NOW)
    with pytest.raises(DuplicateHypothesis, match="query"):
        create_proposed(db, draft(slug="other_one", queries=("History  Revenge",)), NOW)
    with pytest.raises(DuplicateHypothesis, match="slug"):
        create_proposed(db, draft(queries=("different words",)), NOW)
    with pytest.raises(DuplicateHypothesis, match="seed_channel"):
        create_proposed(db, draft(slug="third", queries=("third words",), seeds=(SEED,)), NOW)


@pytest.mark.postgres
def test_archived_hypotheses_free_their_queries(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    set_status(db, "history_revenge", "archived")
    create_proposed(db, draft(slug="history_revenge_2"), NOW)


@pytest.mark.postgres
def test_approving_twice_or_unknown_slug_fails_cleanly(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    approve(db, "history_revenge", NOW)
    with pytest.raises(InvalidTransition):
        approve(db, "history_revenge", NOW)
    with pytest.raises(UnknownHypothesis):
        approve(db, "nope", NOW)


@pytest.mark.postgres
def test_status_transitions(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    with pytest.raises(InvalidTransition):
        set_status(db, "history_revenge", "paused")  # proposed -> paused is not allowed
    approve(db, "history_revenge", NOW)
    set_status(db, "history_revenge", "paused")
    set_status(db, "history_revenge", "active")
    set_status(db, "history_revenge", "archived")
    with pytest.raises(InvalidTransition):
        set_status(db, "history_revenge", "active")


@pytest.mark.postgres
def test_finalist_only_for_active_hypotheses(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    with pytest.raises(InvalidTransition):
        set_finalist(db, "history_revenge", True)
    approve(db, "history_revenge", NOW)
    set_finalist(db, "history_revenge", True)
    assert get_hypothesis(db, "history_revenge")["finalist"] is True


@pytest.mark.postgres
def test_due_new_then_only_stale_finalists(db: Connection) -> None:
    for slug, words in (("one", "alpha words"), ("two", "beta words"), ("three", "gamma words")):
        create_proposed(db, draft(slug=slug, queries=(words,)), NOW)
        approve(db, slug, NOW)
    assert {h["slug"] for h in due_hypotheses(db, NOW)} == {"one", "two", "three"}
    for slug in ("one", "two", "three"):
        mark_measured(db, get_hypothesis(db, slug)["id"], NOW)
    set_finalist(db, "one", True)
    later = NOW + timedelta(days=8)
    assert [h["slug"] for h in due_hypotheses(db, later)] == ["one"]
    assert due_hypotheses(db, NOW + timedelta(days=3)) == []
    request_remeasure(db, "two")
    assert [h["slug"] for h in due_hypotheses(db, NOW + timedelta(days=3))] == ["two"]


@pytest.mark.postgres
def test_proposed_and_paused_are_never_due(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    assert due_hypotheses(db, NOW) == []
    approve(db, "history_revenge", NOW)
    set_status(db, "history_revenge", "paused")
    assert due_hypotheses(db, NOW) == []


@pytest.mark.postgres
def test_list_filters_by_status_and_unique_slug_avoids_collisions(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    assert [h["slug"] for h in list_hypotheses(db, "proposed")] == ["history_revenge"]
    assert list_hypotheses(db, "active") == []
    assert unique_slug(db, "history_revenge") == "history_revenge_2"
    assert unique_slug(db, "fresh_slug") == "fresh_slug"


@pytest.mark.postgres
def test_export_yaml_is_valid_flow_scalars(db: Connection) -> None:
    create_proposed(db, draft(seeds=(SEED,), parent="historical_stories"), NOW)
    text = export_yaml(db)
    assert '- slug: "history_revenge"' in text
    assert 'parent_niche: "historical_stories"' in text
    assert f'seed_channels: ["{SEED}"]' in text
