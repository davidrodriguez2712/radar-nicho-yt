from datetime import UTC, datetime

from nicheradar.integrations.contracts import Batch, Coverage, Operation, Provenance


def test_new_operations_exist_and_batch_carries_comments_and_categories() -> None:
    assert Operation.SEARCH == "search"  # type: ignore[comparison-overlap]
    assert Operation.COMMENT_THREADS == "comment_threads"  # type: ignore[comparison-overlap]
    assert Operation.VIDEO_CATEGORIES == "video_categories"  # type: ignore[comparison-overlap]
    batch = Batch(
        provenance=Provenance(
            provider="test",
            operation=Operation.SEARCH,
            auth_scope="x",
            fetched_at=datetime.now(UTC),
        ),
        coverage=Coverage(returned=0, selection_method="test"),
        costs=(),
        comments=({"text": "hi", "like_count": 1},),
        category_labels={"24": "Entertainment"},
    )
    assert batch.comments[0]["text"] == "hi"
    assert batch.category_labels["24"] == "Entertainment"
