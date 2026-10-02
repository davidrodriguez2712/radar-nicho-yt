# Análisis competitivo de canal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner paste a YouTube channel URL/handle/ID and get a saved, evidence-based report answering (a) is there room to compete in this niche, and (b) how does this specific channel compare to its real comparables — using YouTube Data API v3 and vidIQ together, degrading gracefully (never crashing, never inventing data) when either runs out of budget.

**Architecture:** Reuses the existing job-queue worker (`analysis_runs`/`jobs`) with a new `trigger="channel_analysis"` and its own parallel stage sequence (separate from the catalog/refresh sequence, since the existing `confirm_stage()` is hardcoded to the catalog's `STAGES` tuple). Reuses `features/metrics.py::calculate()` for cohort-style metrics and `scoring/profit.py::estimate_profit()` for the profit range, unchanged. Two new, narrow extensions to shared code are required (flagged below) because of two hardcoded assumptions discovered while planning: `budget.py::reserve()`'s vidIQ-credit clamp, and `workers/queue.py::confirm_stage()`'s stage tuple.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Pydantic v2, Streamlit, PostgreSQL/Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-channel-competitive-analysis-design.md`

## Global Constraints

- Never invent a number: every metric/estimate that lacks real data must surface as `None`/`"incomplete"` with the exact missing reason, never a guess or a zero standing in for "unknown" (spec, project-wide rule already enforced everywhere else in this codebase).
- vidIQ cap for this feature: **50 credits per analysis** (owner's explicit decision). At vidIQ's real flat cost of 5 credits/call, that is **10 calls total** per analysis.
- YouTube `search.list` costs **100 units/call** against its own separate daily bucket (owner confirmed via Google Cloud Console: `Search Queries per day` quota = 100, independent of the general 10,000/day pool). Design must call it **at most once per analysis**.
- YouTube `channels.list`/`playlistItems.list`/`videos.list`/`commentThreads.list`/`videoCategories.list` cost **1 unit/call** against the general 10,000/day pool — generous, not a binding constraint for personal use.
- Social Blade, the YouTube RSS feed, and Google Trends are explicitly **not used** (spec: no free tier, compliance gray zone, and no public API respectively). Do not add them in this plan.
- If vidIQ fails for budget/quota reasons mid-analysis, the analysis continues with YouTube-only data, marked `vidiq_omitted: "budget_exhausted"` in the snapshot — it must never fail the whole analysis for this reason.
- Every provider call in this feature must go through the existing `Gateway`/`reserve()` budget machinery — no direct `httpx`/transport calls that bypass budget tracking.
- Each channel analysis is immutable once created; re-analyzing the same channel creates a new row, never edits an existing one.

## Review Focus

- **Channel input the user pastes is a full URL in an unsupported shape** (e.g. `youtube.com/c/CustomName` or `youtube.com/user/LegacyName`) — the spec only commits to handle (`@name`) and raw channel ID (`UC...`) resolution; an unsupported shape must return a clear, explicit "unsupported input" error before spending any budget, never silently misparse into a wrong channel ID.
- **The target channel itself gets returned as one of its own "comparables"** by the YouTube/vidIQ search — must be filtered out before computing the best/worst range, or the direct comparison becomes meaningless (compares the channel to itself).
- **vidIQ's balance/credits are already exhausted before the analysis even starts** (not mid-analysis) — the very first vidIQ call must fail cleanly with the same graceful degradation, not treat "zero calls succeeded" differently from "some calls succeeded then ran out."
- **Two analyses for the same channel run back-to-back on the same day**, and YouTube's 100/day `search.list` bucket is already spent by the first one — the second analysis must fail that specific stage with a clear, real error (`youtube_search_quota_exhausted`), not fall back to an unapproved source (RSS, cached guesses) and not crash the job.
- **A channel with zero real comparables found** (obscure niche, or both searches return nothing usable) — the niche panorama section must show `status: "insufficient_real_evidence"`, matching the project's established pattern (e.g. `compute_references.py`), never fabricate placeholder comparables to fill the report.

---

## File Structure

| File | Responsibility |
|---|---|
| `migrations/versions/0010_channel_analyses.py` | New table, additive |
| `src/nicheradar/repositories/schema.py` | `channel_analyses` table definition (modify) |
| `src/nicheradar/integrations/contracts.py` | New `Operation` values + `Batch.comments`/`Batch.category_labels` fields (modify) |
| `src/nicheradar/integrations/synthetic.py` | Deterministic fixtures for the new operations (modify) |
| `src/nicheradar/integrations/youtube.py` | Real `search.list`/`commentThreads.list`/`videoCategories.list` support (modify) |
| `src/nicheradar/config.py` | New `youtube_search_quota_*`/`youtube_detail_quota_*` Settings fields (modify) |
| `src/nicheradar/domain/profile.py` | New `channel_analysis_credits_per_run` field (modify) |
| `src/nicheradar/services/budget.py` | Trigger-aware vidIQ run-cap clamp (modify, narrow) |
| `src/nicheradar/services/channel_analysis_providers.py` | New: tariffs/limits for the new operations (YouTube + vidIQ, including `KEYWORDS`) |
| `src/nicheradar/workers/channel_analysis_queue.py` | New: `CHANNEL_ANALYSIS_STAGES` + `confirm_channel_analysis_stage()`, parallel to `workers/queue.py::confirm_stage()` |
| `src/nicheradar/discovery/channel_analysis.py` | New: `parse_channel_input`, `resolve_channel`, `fetch_channel_videos`, `discover_comparables`, `compute_comparison` |
| `src/nicheradar/workers/pipeline.py` | Dispatch the new stage sequence when `run["trigger"] == "channel_analysis"` (modify) |
| `src/nicheradar/services/channel_analysis.py` | New: `save_channel_analysis`, `list_channel_analyses`, `channel_analysis_detail` (persistence, mirrors `services/console.py`) |
| `src/nicheradar/api.py` | `POST/GET /channel-analyses`, `GET /channel-analyses/{id}` (modify) |
| `src/nicheradar/dashboard.py` | New "Análisis de canal" tab (modify) |
| `tests/test_channel_analysis_*.py` | New, one per layer |

---

### Task 1: `channel_analyses` table (migration + schema)

**Files:**
- Create: `migrations/versions/0010_channel_analyses.py`
- Modify: `src/nicheradar/repositories/schema.py`
- Test: `tests/test_ranking.py` (existing `test_ranking_migration_matches_metadata` already asserts `compare_metadata(context, metadata) == []` across the whole schema — no new test file needed, this one must keep passing)

**Interfaces:**
- Produces: table `channel_analyses` with columns `id, profile_id, run_id, channel_input, channel_external_id, status, configuration, snapshot, consumption, created_at, retain_until, expired_at`.

- [ ] **Step 1: Write the migration**

```python
"""Channel competitive analysis: saved, immutable per-run snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("channel_input", sa.Text, nullable=False),
        sa.Column("channel_external_id", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("snapshot", JSONB),
        sa.Column("consumption", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'failed')", name="channel_analysis_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("channel_analyses")
```

- [ ] **Step 2: Add the matching table to `schema.py`**

Open `src/nicheradar/repositories/schema.py`. Find the `production_recipe_defaults` table
block (added in a previous release) and insert this immediately after it, same style:

```python
channel_analyses = sa.Table(
    "channel_analyses",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column(
        "run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True
    ),
    sa.Column("channel_input", sa.Text, nullable=False),
    sa.Column("channel_external_id", sa.String(80)),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("configuration", JSONB, nullable=False),
    sa.Column("snapshot", JSONB),
    sa.Column("consumption", JSONB, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expired_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint("status IN ('completed', 'partial', 'failed')", name="channel_analysis_status"),
)
```

- [ ] **Step 3: Run the schema-consistency test**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_ranking.py::test_ranking_migration_matches_metadata -v`
Expected: PASS (if it fails, the migration and `schema.py` definitions have drifted — compare them column by column).

- [ ] **Step 4: Run the full test suite once to confirm nothing else broke**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q`
Expected: all currently-passing tests still pass.

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0010_channel_analyses.py src/nicheradar/repositories/schema.py
git commit -m "feat: add channel_analyses table"
```

---

### Task 2: New `Operation` values and `Batch` fields

**Files:**
- Modify: `src/nicheradar/integrations/contracts.py`
- Test: `tests/test_channel_analysis_contracts.py` (new)

**Interfaces:**
- Produces: `Operation.SEARCH`, `Operation.COMMENT_THREADS`, `Operation.VIDEO_CATEGORIES`; `Batch.comments: tuple[dict[str, Any], ...] = ()`; `Batch.category_labels: dict[str, str] = Field(default_factory=dict)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_analysis_contracts.py
from nicheradar.integrations.contracts import Batch, Coverage, Operation, Provenance
from datetime import datetime, UTC


def test_new_operations_exist_and_batch_carries_comments_and_categories() -> None:
    assert Operation.SEARCH == "search"
    assert Operation.COMMENT_THREADS == "comment_threads"
    assert Operation.VIDEO_CATEGORIES == "video_categories"
    batch = Batch(
        provenance=Provenance(
            provider="test", operation=Operation.SEARCH, auth_scope="x", fetched_at=datetime.now(UTC)
        ),
        coverage=Coverage(returned=0, selection_method="test"),
        costs=(),
        comments=({"text": "hi", "like_count": 1},),
        category_labels={"24": "Entertainment"},
    )
    assert batch.comments[0]["text"] == "hi"
    assert batch.category_labels["24"] == "Entertainment"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_contracts.py -v`
Expected: FAIL (`Operation` has no attribute `SEARCH`, or `Batch` rejects unknown fields — `Contract` uses `extra="forbid"`).

- [ ] **Step 3: Add the enum values and Batch fields**

In `src/nicheradar/integrations/contracts.py`, extend the `Operation` enum:

```python
class Operation(StrEnum):
    EXPLANATION = "explanation"
    CHANNEL_SEARCH = "channel_search"
    CHANNEL_VIDEOS = "channel_videos"
    OUTLIERS = "outliers"
    KEYWORDS = "keyword_research"
    BALANCE = "balance"
    CHANNELS = "channels"
    UPLOADS = "uploads"
    VIDEOS = "videos"
    SEARCH = "search"
    COMMENT_THREADS = "comment_threads"
    VIDEO_CATEGORIES = "video_categories"
```

Extend `Batch`:

```python
class Batch(Contract):
    provenance: Provenance
    coverage: Coverage
    costs: tuple[Cost, ...]
    channels: tuple[Channel, ...] = ()
    videos: tuple[Video, ...] = ()
    keywords: tuple[dict[str, Any], ...] = ()
    balance: Balance | None = None
    comments: tuple[dict[str, Any], ...] = ()
    category_labels: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_analysis_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite (enum/Batch changes are widely imported)**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q`
Expected: all pass (additive changes only — no existing code matches on an exhaustive `Operation` switch without a default branch; verify this assumption holds by checking the run is clean).

- [ ] **Step 6: Lint, format, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/integrations/contracts.py tests/test_channel_analysis_contracts.py
git commit -m "feat: add search/comment-threads/video-categories operations"
```

---

### Task 3: Synthetic provider fixtures for the new operations

**Files:**
- Modify: `src/nicheradar/integrations/synthetic.py`
- Test: `tests/test_channel_analysis_contracts.py` (extend)

**Interfaces:**
- Consumes: `Operation.SEARCH`/`COMMENT_THREADS`/`VIDEO_CATEGORIES` (Task 2).
- Produces: `SyntheticProvider.fetch()` returns deterministic, realistic `Batch` data for all three new operations (every later task's tests depend on this).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_contracts.py
import asyncio
from nicheradar.integrations.synthetic import SyntheticProvider


def test_synthetic_provider_supports_new_operations() -> None:
    provider = SyntheticProvider()
    now = datetime.now(UTC)
    search = asyncio.run(
        provider.fetch(Operation.SEARCH, {"type": "channel", "q": "science", "family": "science"}, now)
    )
    assert len(search.channels) > 0
    comments = asyncio.run(
        provider.fetch(Operation.COMMENT_THREADS, {"videoId": "x", "family": "science"}, now)
    )
    assert len(comments.comments) > 0
    categories = asyncio.run(provider.fetch(Operation.VIDEO_CATEGORIES, {"family": "science"}, now))
    assert categories.category_labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_contracts.py::test_synthetic_provider_supports_new_operations -v`
Expected: FAIL (new operations fall through to the generic video-fixture branch today, so `search.channels` is empty and `comments.comments`/`categories.category_labels` don't exist yet as populated values).

- [ ] **Step 3: Add branches to `SyntheticProvider.fetch()`**

In `src/nicheradar/integrations/synthetic.py`, insert these branches **before** the existing
`if operation in {Operation.CHANNEL_SEARCH, Operation.CHANNELS}:` line (so `SEARCH` with
`type=channel` reuses that exact channel fixture block — change that line's condition to
also include `Operation.SEARCH` when `parameters.get("type") != "video"`):

```python
    if operation == Operation.COMMENT_THREADS:
        return Batch(
            **common,
            comments=tuple(
                {"text": f"Synthetic comment {index} about {family}", "like_count": index * 2}
                for index in range(3)
            ),
            coverage=Coverage(returned=3, complete=True, selection_method="synthetic"),
        )
    if operation == Operation.VIDEO_CATEGORIES:
        return Batch(
            **common,
            category_labels={"24": "Entertainment", "27": "Education"},
            coverage=Coverage(returned=2, complete=True, selection_method="synthetic"),
        )
    if operation == Operation.SEARCH and parameters.get("type") == "video":
        operation = Operation.CHANNEL_VIDEOS  # falls through to the generic video fixture below
    if operation in {Operation.CHANNEL_SEARCH, Operation.CHANNELS, Operation.SEARCH}:
```

(That last line replaces the existing `if operation in {Operation.CHANNEL_SEARCH, Operation.CHANNELS}:` — just add `Operation.SEARCH` to the set.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_analysis_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite, lint, format, type-check**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/integrations/synthetic.py tests/test_channel_analysis_contracts.py
git commit -m "feat: synthetic fixtures for search/comment-threads/video-categories"
```

---

### Task 4: Real YouTube support for the new operations

**Files:**
- Modify: `src/nicheradar/integrations/youtube.py`
- Test: `tests/test_channel_analysis_youtube.py` (new)

**Interfaces:**
- Consumes: `Operation.SEARCH`/`COMMENT_THREADS`/`VIDEO_CATEGORIES` (Task 2).
- Produces: `YouTubeProvider` resolves these three operations against the real YouTube Data API v3 shapes (verified against `search.list`/`commentThreads.list`/`videoCategories.list` response schemas).

**Note for the implementer:** `YouTubeProvider.fetch()` currently builds a `resource` dict
keyed by `Operation` and a flat parameter allowlist. Read the full current file first —
it is short (~180 lines) — before editing, since the allowlist and `normalize()` dispatch
both need new branches, and `search.list` results have the `id.videoId`/`id.channelId`
nested shape, not the flat `id` shape the other endpoints use.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channel_analysis_youtube.py
# NOTE: this project has no pytest-asyncio plugin installed (checked pyproject.toml/
# uv.lock — confirm this is still true before using it). Every async call elsewhere in
# this codebase is tested via the sync `def test_...(): asyncio.run(coro)` pattern (see
# tests/test_evaluation.py) — follow that convention here, not `@pytest.mark.asyncio`.
import asyncio
from datetime import datetime, UTC

import httpx
from pydantic import SecretStr

from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.youtube import YouTubeProvider


def _provider(transport: httpx.MockTransport) -> YouTubeProvider:
    return YouTubeProvider(SecretStr("key"), "scope", enabled=True, transport=transport)


def test_search_channels_maps_nested_id_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["type"] == "channel"
        assert request.url.params["q"] == "science"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": {"channelId": "UC123"}, "snippet": {"title": "Science Channel"}},
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(
        Operation.SEARCH, {"type": "channel", "q": "science", "maxResults": "10"}, datetime.now(UTC)
    ))
    assert batch.channels[0].id == "UC123"
    assert batch.channels[0].title == "Science Channel"
    assert batch.costs[0].maximum == 100


def test_comment_threads_maps_top_level_comments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["videoId"] == "vid1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "snippet": {
                            "topLevelComment": {
                                "snippet": {"textDisplay": "Nice video", "likeCount": 4}
                            }
                        }
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(
        Operation.COMMENT_THREADS, {"videoId": "vid1", "maxResults": "20"}, datetime.now(UTC)
    ))
    assert batch.comments[0]["text"] == "Nice video"
    assert batch.comments[0]["like_count"] == 4
    assert batch.costs[0].maximum == 1


def test_video_categories_maps_id_to_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"id": "24", "snippet": {"title": "Entertainment"}}]},
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(
        Operation.VIDEO_CATEGORIES, {"regionCode": "US"}, datetime.now(UTC)
    ))
    assert batch.category_labels == {"24": "Entertainment"}
    assert batch.costs[0].maximum == 1


def test_unsupported_parameter_is_dropped_not_forwarded() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    provider = _provider(httpx.MockTransport(handler))
    asyncio.run(provider.fetch(
        Operation.SEARCH,
        {"type": "channel", "q": "science", "not_a_real_param": "x"},
        datetime.now(UTC),
    ))
    assert "not_a_real_param" not in captured["params"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_channel_analysis_youtube.py -v`
Expected: FAIL (`Operation.SEARCH` etc. not in `YouTubeProvider.operations`, raises
`ProviderError("unsupported_operation")`).

- [ ] **Step 3: Read the current file, then extend it**

Read `src/nicheradar/integrations/youtube.py` fully first. Then:

1. Add to `operations`:
```python
    operations = frozenset(
        {Operation.CHANNELS, Operation.UPLOADS, Operation.VIDEOS, Operation.SEARCH,
         Operation.COMMENT_THREADS, Operation.VIDEO_CATEGORIES}
    )
```
2. Add to the `resource` dict inside `fetch()`:
```python
        resource = {
            Operation.CHANNELS: "channels",
            Operation.UPLOADS: "playlistItems",
            Operation.VIDEOS: "videos",
            Operation.SEARCH: "search",
            Operation.COMMENT_THREADS: "commentThreads",
            Operation.VIDEO_CATEGORIES: "videoCategories",
        }[operation]
```
3. Extend whatever parameter allowlist filtering exists in `fetch()` so `q`/`type`/`order`
   (for `SEARCH`) and `videoId`/`order` (for `COMMENT_THREADS`) and `regionCode` (for
   `VIDEO_CATEGORIES`) pass through, and any key not on the allowlist is dropped (this is
   what `test_unsupported_parameter_is_dropped_not_forwarded` pins).
4. Add a `Cost` per operation where costs are assigned (find where `Operation.VIDEOS` or
   similar gets its `Cost(unit="youtube_quota", maximum=Decimal(1), ...)` — mirror that,
   using `maximum=Decimal(100)` only for `Operation.SEARCH`, `Decimal(1)` for the other two).
5. Add response-normalization branches:

```python
        if operation == Operation.SEARCH:
            channels = tuple(
                Channel(id=item["id"]["channelId"], title=item["snippet"]["title"])
                for item in data.get("items", [])
                if "channelId" in item.get("id", {})
            )
            videos = tuple(
                Video(
                    id=item["id"]["videoId"],
                    channel_id=item["snippet"].get("channelId", ""),
                    title=item["snippet"]["title"],
                    published_at=None,
                )
                for item in data.get("items", [])
                if "videoId" in item.get("id", {})
            )
            return Batch(
                provenance=provenance, costs=costs, channels=channels, videos=videos,
                coverage=Coverage(returned=len(data.get("items", [])), selection_method="search"),
            )
        if operation == Operation.COMMENT_THREADS:
            comments = tuple(
                {
                    "text": item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                    "like_count": item["snippet"]["topLevelComment"]["snippet"]["likeCount"],
                }
                for item in data.get("items", [])
            )
            return Batch(
                provenance=provenance, costs=costs, comments=comments,
                coverage=Coverage(returned=len(comments), selection_method="comment_threads"),
            )
        if operation == Operation.VIDEO_CATEGORIES:
            labels = {item["id"]: item["snippet"]["title"] for item in data.get("items", [])}
            return Batch(
                provenance=provenance, costs=costs, category_labels=labels,
                coverage=Coverage(returned=len(labels), selection_method="video_categories"),
            )
```

Adapt variable names (`provenance`, `costs`, `data`) to whatever the existing function
already uses at that point — read the surrounding code first, this sketch shows the shape,
not a drop-in replacement for the whole method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_youtube.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/integrations/youtube.py tests/test_channel_analysis_youtube.py
git commit -m "feat: real YouTube search/comment-threads/video-categories support"
```

---

### Task 5: Budget config — new Settings and CreatorProfile fields

**Files:**
- Modify: `src/nicheradar/config.py`
- Modify: `src/nicheradar/domain/profile.py`
- Test: `tests/test_channel_analysis_budget.py` (new)

**Interfaces:**
- Produces: `Settings.youtube_search_quota_per_run/week/month`, `Settings.youtube_detail_quota_per_run/week/month`, `CreatorProfile.channel_analysis_credits_per_run`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_analysis_budget.py
from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile


def test_new_budget_fields_have_conservative_defaults() -> None:
    settings = Settings()
    assert settings.youtube_search_quota_per_run == 100
    assert settings.youtube_search_quota_per_week == 100
    assert settings.youtube_search_quota_per_month == 300
    assert settings.youtube_detail_quota_per_run == 100
    assert settings.youtube_detail_quota_per_week == 500
    assert settings.youtube_detail_quota_per_month == 2000
    profile = CreatorProfile()
    assert profile.channel_analysis_credits_per_run == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: FAIL (`AttributeError` on the new fields).

- [ ] **Step 3: Add the fields**

In `src/nicheradar/config.py`, immediately after `youtube_maximum_videos` (line 38):

```python
    youtube_search_quota_per_run: int = Field(default=100, ge=0, le=10_000)
    youtube_search_quota_per_week: int = Field(default=100, ge=0, le=100_000)
    youtube_search_quota_per_month: int = Field(default=300, ge=0, le=1_000_000)
    youtube_detail_quota_per_run: int = Field(default=100, ge=0, le=10_000)
    youtube_detail_quota_per_week: int = Field(default=500, ge=0, le=100_000)
    youtube_detail_quota_per_month: int = Field(default=2000, ge=0, le=1_000_000)
```

In `src/nicheradar/domain/profile.py`, immediately after `credits_per_cycle` (line 35):

```python
    channel_analysis_credits_per_run: int = Field(default=50, ge=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite (CreatorProfile is serialized/stored — check no snapshot/contract test pins an exhaustive field list), lint, format, type-check**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/nicheradar/config.py src/nicheradar/domain/profile.py tests/test_channel_analysis_budget.py
git commit -m "feat: budget config fields for channel analysis"
```

---

### Task 6: Trigger-aware vidIQ run-cap in `budget.py::reserve()`

**Why this task exists:** `reserve()` unconditionally clamps any `vidiq_credit` cost's
`run` cap to `profile.credits_per_run` (currently far below 50), regardless of what
`Limits` the caller passed in. Without this change, a channel-analysis job could never
spend more than the ordinary per-run vidIQ cap, no matter what limits Task 7 configures.

**Files:**
- Modify: `src/nicheradar/services/budget.py`
- Test: `tests/test_channel_analysis_budget.py` (extend)

**Interfaces:**
- Consumes: `CreatorProfile.channel_analysis_credits_per_run` (Task 5), `analysis_runs.trigger`.
- Produces: `reserve()` uses `profile.channel_analysis_credits_per_run` for the `run` cap
  specifically when `request["run_id"]`'s `analysis_runs.trigger == "channel_analysis"`;
  `week`/`period` stay on the existing shared `credits_per_week`/`credits_per_cycle`
  fields unchanged (those represent one real, shared vidIQ account balance).

- [ ] **Step 1: Write the failing test**

This test needs a real Postgres connection (the function queries `analysis_runs`). Mirror
the fixture style already used in `tests/test_persistence.py`/`tests/test_discovery.py`
for creating a profile + run + a `provider_requests` row directly, then call `reserve()`.

```python
# append to tests/test_channel_analysis_budget.py
import pytest
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Connection, insert, select

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Cost
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.budget import Limits, reserve
from tests.test_persistence import NOW


def _prepared_request(db: Connection, profile_id, trigger: str) -> "uuid4":
    run_id = insert_record(
        db, "analysis_runs",
        {"profile_id": profile_id, "mode": "live", "trigger": trigger, "status": "running",
         "configuration": {}},
    )
    request_id = insert_record(
        db, "provider_requests",
        {"run_id": run_id, "provider": "vidiq", "operation": "channel_search",
         "auth_scope": "test", "cache_key": "a" * 64, "idempotency_key": str(uuid4()),
         "state": "prepared"},
    )
    return request_id


@pytest.mark.postgres
def test_channel_analysis_trigger_uses_its_own_run_cap(db: Connection) -> None:
    profile = CreatorProfile(credits_per_run=5, channel_analysis_credits_per_run=50,
                              credits_per_week=200, credits_per_cycle=400)
    profile_id = seed_profile(db, profile, __import__(
        "nicheradar.domain.profile", fromlist=["initial_catalog"]
    ).initial_catalog())
    db.execute(
        insert(s.credit_balances).values(
            provider="vidiq", auth_scope="test", unit="vidiq_credit",
            renewable_remaining=Decimal(1000), additional_remaining=Decimal(0),
            cycle_started_at=NOW, renews_at=NOW + timedelta(days=30),
            refresh_required=False, confirmed_usage=Decimal(0),
        )
    )
    limits = {"vidiq_credit": Limits(operation=Decimal(5), run=Decimal(50),
                                      week=Decimal(200), period=Decimal(400))}
    costs = (Cost(unit="vidiq_credit", maximum=Decimal(30), source="test"),)

    manual_request = _prepared_request(db, profile_id, "manual")
    with pytest.raises(Exception):  # ProviderError("run_budget_exhausted") — 30 > 5
        reserve(db, manual_request, profile_id, costs, limits, NOW)

    analysis_request = _prepared_request(db, profile_id, "channel_analysis")
    reserve(db, analysis_request, profile_id, costs, limits, NOW)  # 30 <= 50: must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: FAIL on the `channel_analysis` call (still clamped to `credits_per_run=5`, raises `run_budget_exhausted`).

- [ ] **Step 3: Make the clamp trigger-aware**

In `src/nicheradar/services/budget.py`, inside `reserve()`, the `request` row is already
fetched with `.with_for_update()` a few lines above the `for cost in sorted(...)` loop.
Add a lookup of the run's trigger right after that `request` fetch:

```python
    trigger = connection.execute(
        select(s.analysis_runs.c.trigger).where(s.analysis_runs.c.id == request["run_id"])
    ).scalar_one()
```

Then change the existing `elif cost.unit == "vidiq_credit":` branch to:

```python
        elif cost.unit == "vidiq_credit":
            run_cap = (
                profile.channel_analysis_credits_per_run
                if trigger == "channel_analysis"
                else profile.credits_per_run
            )
            cap = Limits(
                operation=cap.operation,
                run=min(cap.run, Decimal(run_cap)),
                week=min(cap.week, Decimal(profile.credits_per_week)),
                period=min(cap.period, Decimal(profile.credits_per_cycle)),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: PASS (both assertions — manual still clamps to 5, channel_analysis allows 30).

- [ ] **Step 5: Run the FULL suite — this touches a core shared function**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q`
Expected: every existing budget/pilot/discovery test involving vidIQ credits still
passes unchanged (they all use `trigger` values other than `"channel_analysis"`, so they
fall into the unchanged `profile.credits_per_run` branch).

- [ ] **Step 6: Lint, format, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/services/budget.py tests/test_channel_analysis_budget.py
git commit -m "fix: make vidIQ run-cap clamp trigger-aware for channel analysis"
```

---

### Task 7: Tariffs/limits module for channel-analysis operations

**Files:**
- Create: `src/nicheradar/services/channel_analysis_providers.py`
- Test: `tests/test_channel_analysis_budget.py` (extend)

**Interfaces:**
- Consumes: `Settings` (Task 5), `Limits` (`services/budget.py`).
- Produces: `channel_analysis_youtube_tariffs() -> dict[Operation, tuple[Cost, ...]]`,
  `channel_analysis_youtube_limits(config: Settings) -> dict[str, Limits]`,
  `channel_analysis_vidiq_tariffs() -> dict[Operation, tuple[Cost, ...]]`,
  `channel_analysis_vidiq_limits(profile: CreatorProfile) -> dict[str, Limits]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_budget.py
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Operation
from nicheradar.services.channel_analysis_providers import (
    channel_analysis_vidiq_limits, channel_analysis_vidiq_tariffs,
    channel_analysis_youtube_limits, channel_analysis_youtube_tariffs,
)


def test_channel_analysis_tariffs_cover_every_operation_used() -> None:
    youtube = channel_analysis_youtube_tariffs()
    for op in (Operation.CHANNELS, Operation.UPLOADS, Operation.VIDEOS,
               Operation.SEARCH, Operation.COMMENT_THREADS, Operation.VIDEO_CATEGORIES):
        assert op in youtube
    assert youtube[Operation.SEARCH][0].maximum == 100
    assert youtube[Operation.VIDEOS][0].maximum == 1

    vidiq = channel_analysis_vidiq_tariffs()
    for op in (Operation.CHANNEL_SEARCH, Operation.CHANNEL_VIDEOS, Operation.OUTLIERS,
               Operation.KEYWORDS):
        assert op in vidiq
    assert vidiq[Operation.CHANNEL_SEARCH][0].maximum == 5


def test_channel_analysis_limits_use_configured_values() -> None:
    settings = Settings()
    yt_limits = channel_analysis_youtube_limits(settings)
    assert yt_limits["youtube_search_quota"].run == 100
    assert yt_limits["youtube_detail_quota"].run == 100
    profile = CreatorProfile()
    vidiq_limits = channel_analysis_vidiq_limits(profile)
    assert vidiq_limits["vidiq_credit"].run == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the module**

```python
# src/nicheradar/services/channel_analysis_providers.py
"""Tariffs and limits for the channel-analysis flow only; separate from the
scheduled-cycle YouTube enrichment budget (src/nicheradar/services/youtube_enrichment.py)
and the pilot vidIQ budget (src/nicheradar/services/pilot.py) — this feature needs its
own higher per-run vidIQ cap (Task 6) and its own YouTube search-vs-detail split
(search.list has its own 100/day bucket; detail calls share the general 10,000/day pool).
"""

from decimal import Decimal

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Cost, Operation
from nicheradar.services.budget import Limits

YOUTUBE_TARIFF_SOURCE = "YouTube Data API v3 docs, search.list/commentThreads.list/videoCategories.list verified 2026-10-01"
VIDIQ_TARIFF_SOURCE = "MCP tools/list reviewed 2026-09-21; flat 5 credits per call"


def channel_analysis_youtube_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    detail_cost = Cost(unit="youtube_detail_quota", maximum=Decimal(1), source=YOUTUBE_TARIFF_SOURCE)
    return {
        Operation.CHANNELS: (detail_cost,),
        Operation.UPLOADS: (detail_cost,),
        Operation.VIDEOS: (detail_cost,),
        Operation.COMMENT_THREADS: (detail_cost,),
        Operation.VIDEO_CATEGORIES: (detail_cost,),
        Operation.SEARCH: (
            Cost(unit="youtube_search_quota", maximum=Decimal(100), source=YOUTUBE_TARIFF_SOURCE),
        ),
    }


def channel_analysis_youtube_limits(config: Settings) -> dict[str, Limits]:
    return {
        "youtube_search_quota": Limits(
            operation=Decimal(100),
            run=Decimal(config.youtube_search_quota_per_run),
            week=Decimal(config.youtube_search_quota_per_week),
            period=Decimal(config.youtube_search_quota_per_month),
        ),
        "youtube_detail_quota": Limits(
            operation=Decimal(1),
            run=Decimal(config.youtube_detail_quota_per_run),
            week=Decimal(config.youtube_detail_quota_per_week),
            period=Decimal(config.youtube_detail_quota_per_month),
        ),
    }


def channel_analysis_vidiq_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    cost = Cost(unit="vidiq_credit", maximum=Decimal(5), source=VIDIQ_TARIFF_SOURCE)
    return {
        Operation.CHANNEL_SEARCH: (cost,),
        Operation.CHANNEL_VIDEOS: (cost,),
        Operation.OUTLIERS: (cost,),
        Operation.KEYWORDS: (cost,),
    }


def channel_analysis_vidiq_limits(profile: CreatorProfile) -> dict[str, Limits]:
    return {
        "vidiq_credit": Limits(
            operation=Decimal(5),
            run=Decimal(profile.channel_analysis_credits_per_run),
            week=Decimal(profile.credits_per_week),
            period=Decimal(profile.credits_per_cycle),
        )
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/services/channel_analysis_providers.py tests/test_channel_analysis_budget.py
git commit -m "feat: tariffs and limits for channel-analysis provider calls"
```

---

### Task 8: Parallel stage queue (`CHANNEL_ANALYSIS_STAGES`)

**Why this task exists:** `workers/queue.py::confirm_stage()` computes "next stage" via
`STAGES[STAGES.index(stage) + 1]` against the single hardcoded catalog `STAGES` tuple —
a `channel_analysis` stage name isn't in it, so reusing `confirm_stage()` directly would
raise `ValueError` or silently misadvance. This task adds a parallel, independent
implementation — it does not touch `workers/queue.py` at all.

**Files:**
- Create: `src/nicheradar/workers/channel_analysis_queue.py`
- Test: `tests/test_channel_analysis_queue.py` (new)

**Interfaces:**
- Consumes: `owned_job`, `heartbeat` (reused unchanged from `workers/queue.py` — these are generic).
- Produces: `CHANNEL_ANALYSIS_STAGES: tuple[str, ...]`, `confirm_channel_analysis_stage(connection, job_id, owner, now, stage, checkpoint, *, partial=False) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_analysis_queue.py
import pytest
from sqlalchemy import Connection, select

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.workers.channel_analysis_queue import (
    CHANNEL_ANALYSIS_STAGES, confirm_channel_analysis_stage,
)
from nicheradar.workers.queue import claim
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_stage_sequence_advances_and_completes(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = insert_record(
        db, "analysis_runs",
        {"profile_id": profile_id, "mode": "live", "trigger": "channel_analysis",
         "status": "running", "configuration": {}},
    )
    insert_record(
        db, "jobs",
        {"run_id": run_id, "occurrence_key": "test-channel-analysis-1", "status": "queued",
         "stage": CHANNEL_ANALYSIS_STAGES[0], "checkpoints": {}, "available_at": NOW},
    )
    job = claim(db, "owner-a", NOW)
    assert job is not None
    assert job["stage"] == CHANNEL_ANALYSIS_STAGES[0]
    confirm_channel_analysis_stage(db, job["id"], "owner-a", NOW, job["stage"], {"ok": True})
    db.commit()
    row = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert row["stage"] == CHANNEL_ANALYSIS_STAGES[1]
    assert row["status"] == "queued"

    # Confirming the final stage marks the job completed.
    for stage in CHANNEL_ANALYSIS_STAGES[1:]:
        current = claim(db, "owner-a", NOW)
        assert current is not None
        confirm_channel_analysis_stage(db, current["id"], "owner-a", NOW, stage, {"ok": True})
        db.commit()
    final = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert final["status"] == "succeeded"


@pytest.mark.postgres
def test_partial_confirmation_marks_job_partial_not_queued(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = insert_record(
        db, "analysis_runs",
        {"profile_id": profile_id, "mode": "live", "trigger": "channel_analysis",
         "status": "running", "configuration": {}},
    )
    insert_record(
        db, "jobs",
        {"run_id": run_id, "occurrence_key": "test-channel-analysis-2", "status": "queued",
         "stage": CHANNEL_ANALYSIS_STAGES[-1], "checkpoints": {}, "available_at": NOW},
    )
    job = claim(db, "owner-b", NOW)
    assert job is not None
    confirm_channel_analysis_stage(
        db, job["id"], "owner-b", NOW, job["stage"], {"reason": "budget_exhausted"}, partial=True
    )
    db.commit()
    row = db.execute(select(s.jobs).where(s.jobs.c.id == job["id"])).mappings().one()
    assert row["status"] == "partial"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_queue.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Read `workers/queue.py::confirm_stage()` in full, then write the parallel module**

Read the existing `confirm_stage()` (around line 246) to copy its exact checkpoint-merge
and status-transition logic. Then:

```python
# src/nicheradar/workers/channel_analysis_queue.py
"""Stage sequence for the channel-analysis flow; parallel to workers/queue.py's
STAGES/confirm_stage(), which are hardcoded to the catalog discovery sequence and cannot
be reused for a different stage sequence without risking index/completion-detection bugs.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, update

from nicheradar.repositories import schema_v1 as s
from nicheradar.workers.queue import owned_job

CHANNEL_ANALYSIS_STAGES = (
    "resolve",
    "target_videos",
    "discover_comparables",
    "comparable_videos",
    "metrics",
    "profit",
    "persist",
)


def confirm_channel_analysis_stage(
    connection: Connection,
    job_id: UUID,
    owner: str,
    now: datetime,
    stage: str,
    checkpoint: dict[str, Any],
    *,
    partial: bool = False,
) -> None:
    job = owned_job(connection, job_id, owner, now)
    index = CHANNEL_ANALYSIS_STAGES.index(stage)
    checkpoints = job["checkpoints"] | {stage: checkpoint}
    is_final = index == len(CHANNEL_ANALYSIS_STAGES) - 1
    values: dict[str, Any] = {"checkpoints": checkpoints}
    if partial:
        values["status"] = "partial"
    elif is_final:
        values["status"] = "succeeded"
    else:
        values["stage"] = CHANNEL_ANALYSIS_STAGES[index + 1]
        values["status"] = "queued"
        values["available_at"] = now
    connection.execute(update(s.jobs).where(s.jobs.c.id == job_id).values(**values))
```

(If `workers/queue.py::confirm_stage()`'s real status-transition logic differs from this
sketch in a detail — e.g. it also resets `attempts` or `lease_owner` — match that exact
behavior; read the real function before finalizing this file, since the two must behave
identically except for which tuple drives "next"/"final".)

- [ ] **Step 4: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_queue.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/workers/channel_analysis_queue.py tests/test_channel_analysis_queue.py
git commit -m "feat: parallel job-stage sequence for channel analysis"
```

---

### Task 9: `parse_channel_input` and `resolve_channel`

**Files:**
- Create: `src/nicheradar/discovery/channel_analysis.py`
- Test: `tests/test_channel_analysis_discovery.py` (new)

**Interfaces:**
- Produces: `parse_channel_input(raw: str) -> dict[str, str]` (returns `{"forHandle": ...}` or `{"id": ...}`, raises `ValueError("unsupported_channel_input")` otherwise); `async def resolve_channel(gateway: Gateway, raw_input: str, now: datetime) -> Channel` (raises `ProviderError("channel_not_found")` if YouTube returns zero channels).

**Scope cut, stated explicitly (matches the plan's Review Focus item 1):** only `@handle`
(anywhere in a pasted URL or bare) and raw channel IDs (`UC` + 22 chars) are supported in
this version. Legacy `/user/Name` and custom `/c/Name` URLs are out of scope — note this
in the dashboard's input help text (Task 15) so the owner knows which channels to paste
by their handle instead.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channel_analysis_discovery.py
import asyncio
from datetime import datetime, UTC

import pytest

from nicheradar.discovery.channel_analysis import parse_channel_input, resolve_channel
from nicheradar.integrations.contracts import ProviderError
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.services.gateway import Gateway


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@scienceexplained", {"forHandle": "scienceexplained"}),
        ("https://www.youtube.com/@scienceexplained", {"forHandle": "scienceexplained"}),
        ("https://www.youtube.com/@scienceexplained/videos", {"forHandle": "scienceexplained"}),
        ("UC" + "a" * 22, {"id": "UC" + "a" * 22}),
        ("https://www.youtube.com/channel/" + "UC" + "a" * 22, {"id": "UC" + "a" * 22}),
    ],
)
def test_parse_channel_input_handles_and_ids(raw: str, expected: dict[str, str]) -> None:
    assert parse_channel_input(raw) == expected


def test_parse_channel_input_rejects_unsupported_shapes() -> None:
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("https://www.youtube.com/c/SomeCustomName")
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("https://www.youtube.com/user/LegacyName")
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("not a channel at all")


@pytest.mark.postgres
def test_resolve_channel_not_found_raises_without_spending_other_budget(db) -> None:
    # Synthetic provider's generic channel fixture always returns at least one channel for
    # CHANNELS/CHANNEL_SEARCH, so to exercise "not found" we must call with a handle the
    # fixture won't match; adapt once Task 3's synthetic CHANNELS branch is confirmed to
    # key its result set off the `family` parameter, not the handle itself — if the
    # synthetic fixture can't produce an empty result deterministically, add a minimal
    # branch to synthetic.py in this task (`family="__none__"` returns zero channels) and
    # pin it with its own synthetic-provider test alongside Task 3's.
    pass
```

(The last test above is intentionally left as a stub you must finish, per the scope note:
decide and implement the actual "zero channels" synthetic trigger before marking this
task done — do not leave the `pass` body in the committed test.)

- [ ] **Step 2: Run tests to verify the parsing ones fail**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `parse_channel_input`**

```python
# src/nicheradar/discovery/channel_analysis.py
"""Bounded, on-demand channel competitive analysis: resolve a channel, pull its real
videos, discover real comparables, and compute the same metrics/profit machinery already
used for catalog opportunities — scoped to a single owner-requested channel, not the
seed-family catalog.
"""

import re
from datetime import datetime

from nicheradar.integrations.contracts import Channel, Operation, ProviderError
from nicheradar.services.gateway import Gateway

_HANDLE = re.compile(r"@([A-Za-z0-9_.-]+)")
_CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")


def parse_channel_input(raw: str) -> dict[str, str]:
    raw = raw.strip()
    channel_id_match = _CHANNEL_ID.search(raw)
    if channel_id_match and "/@" not in raw:
        return {"id": channel_id_match.group(1)}
    handle_match = _HANDLE.search(raw)
    if handle_match:
        return {"forHandle": handle_match.group(1)}
    raise ValueError("unsupported_channel_input")


async def resolve_channel(gateway: Gateway, raw_input: str, now: datetime) -> Channel:
    params = parse_channel_input(raw_input)
    batch, _, _ = await gateway.fetch(Operation.CHANNELS, params, now)
    if not batch.channels:
        raise ProviderError("channel_not_found", not_sent=True)
    return batch.channels[0]
```

(Check `Gateway.fetch()`'s exact return shape before finalizing — the research task
reported `async def fetch(self, operation, parameters, now) -> ...` returning a tuple
including the `Batch`; confirm the unpacking above matches the real signature, adjusting
if `fetch()` returns just a `Batch` or a different tuple shape.)

- [ ] **Step 4: Run the parsing tests, finish and run the resolve test**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS once the stub is completed (do not leave `pass` in the final commit — the
"Review Focus" item about channel-not-found errors depends on this test being real).

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py tests/test_channel_analysis_discovery.py
git commit -m "feat: parse channel input and resolve via YouTube channels.list"
```

---

### Task 10: `fetch_channel_videos` and per-channel view-rate

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py`
- Test: `tests/test_channel_analysis_discovery.py` (extend)

**Interfaces:**
- Consumes: `features/metrics.py` (read-only reuse of its median-rate approach — do not
  import private helpers; replicate the one-line `views / days` calculation here, since
  `calculate()` operates on `Membership` tuples from the catalog's sampling machinery,
  which this flow does not use).
- Produces: `async def fetch_channel_videos(gateway: Gateway, channel: Channel, now: datetime) -> tuple[Video, ...]`; `def channel_view_rate(videos: tuple[Video, ...], now: datetime) -> float | None` (median views/day, `None` if no video has both `views` and `published_at`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_discovery.py
from datetime import timedelta

from nicheradar.discovery.channel_analysis import channel_view_rate
from nicheradar.integrations.contracts import Video
from nicheradar.domain.profile import VideoFormat
from tests.test_persistence import NOW


def test_channel_view_rate_is_median_views_per_day() -> None:
    videos = (
        Video(id="a", channel_id="c", title="t", published_at=NOW - timedelta(days=10),
              views=100, format=VideoFormat.LONG),
        Video(id="b", channel_id="c", title="t", published_at=NOW - timedelta(days=10),
              views=300, format=VideoFormat.LONG),
        Video(id="c", channel_id="c", title="t", published_at=None, views=500,
              format=VideoFormat.LONG),  # no published_at: excluded
    )
    assert channel_view_rate(videos, NOW) == 20.0  # median(100/10, 300/10) = 20


def test_channel_view_rate_none_when_no_usable_video() -> None:
    videos = (Video(id="a", channel_id="c", title="t", published_at=None, views=None,
                     format=VideoFormat.LONG),)
    assert channel_view_rate(videos, NOW) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

```python
# append to src/nicheradar/discovery/channel_analysis.py
from statistics import median

from nicheradar.integrations.contracts import Video


def channel_view_rate(videos: tuple[Video, ...], now: datetime) -> float | None:
    rates = []
    for video in videos:
        if video.views is None or video.published_at is None:
            continue
        days = (now - video.published_at).total_seconds() / 86400
        if days > 0:
            rates.append(video.views / days)
    return median(rates) if rates else None


async def fetch_channel_videos(gateway: Gateway, channel: Channel, now: datetime) -> tuple[Video, ...]:
    if channel.uploads_playlist:
        uploads, _, _ = await gateway.fetch(
            Operation.UPLOADS, {"playlistId": channel.uploads_playlist, "maxResults": "25"}, now
        )
        video_ids = [video.id for video in uploads.videos][:25]
        if video_ids:
            batch, _, _ = await gateway.fetch(
                Operation.VIDEOS, {"id": ",".join(video_ids)}, now
            )
            return batch.videos
    return ()
```

(`channel.uploads_playlist` comes from `channels.list`'s `contentDetails.relatedPlaylists.uploads`
— confirm `YouTubeProvider`'s existing `Operation.CHANNELS` normalization already
populates this field on `Channel`; if it doesn't yet, add that one field mapping as part
of this task, with its own test alongside Task 4's.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py tests/test_channel_analysis_discovery.py
git commit -m "feat: fetch a channel's videos and compute its view-rate"
```

---

### Task 11: `discover_comparables`

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py`
- Test: `tests/test_channel_analysis_discovery.py` (extend)

**Interfaces:**
- Consumes: `Channel` (Task 9).
- Produces: `async def discover_comparables(youtube_gateway: Gateway, vidiq_gateway: Gateway | None, target: Channel, now: datetime, *, max_comparables: int = 8) -> tuple[Channel, ...]` — deduplicated by `id`, target excluded, capped at `max_comparables`. If `vidiq_gateway` is `None` or raises `ProviderError` with a budget-related code, continues with YouTube-only results (never raises past this function for that reason).

**Module constants (add alongside the function):** `MAX_COMPARABLES = 8`,
`VIDIQ_BUDGET_ERROR_CODES = {"run_budget_exhausted", "period_budget_exhausted", "balance_exhausted", "balance_refresh_required"}`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_channel_analysis_discovery.py
import asyncio
from datetime import datetime, UTC

from nicheradar.discovery.channel_analysis import discover_comparables
from nicheradar.integrations.contracts import Channel, Operation, ProviderError


class _FakeGateway:
    def __init__(self, channels: tuple[Channel, ...], *, raises: ProviderError | None = None):
        self._channels = channels
        self._raises = raises

    async def fetch(self, operation, parameters, now):
        if self._raises:
            raise self._raises
        from nicheradar.integrations.contracts import Batch, Coverage, Provenance

        return (
            Batch(
                provenance=Provenance(provider="fake", operation=operation, auth_scope="x",
                                       fetched_at=now),
                coverage=Coverage(returned=len(self._channels), selection_method="fake"),
                costs=(),
                channels=self._channels,
            ),
            "fake-request-id",
            now,
        )


def test_discover_comparables_dedupes_and_excludes_target() -> None:
    target = Channel(id="UC_target", title="Target")
    youtube_results = (target, Channel(id="UC_a", title="A"), Channel(id="UC_b", title="B"))
    vidiq_results = (Channel(id="UC_b", title="B"), Channel(id="UC_c", title="C"))
    comparables = asyncio.run(
        discover_comparables(
            _FakeGateway(youtube_results), _FakeGateway(vidiq_results), target, datetime.now(UTC)
        )
    )
    ids = {channel.id for channel in comparables}
    assert ids == {"UC_a", "UC_b", "UC_c"}  # target excluded, UC_b not duplicated


def test_discover_comparables_degrades_when_vidiq_budget_exhausted() -> None:
    target = Channel(id="UC_target", title="Target")
    youtube_results = (Channel(id="UC_a", title="A"),)
    comparables = asyncio.run(
        discover_comparables(
            _FakeGateway(youtube_results),
            _FakeGateway((), raises=ProviderError("run_budget_exhausted")),
            target,
            datetime.now(UTC),
        )
    )
    assert {channel.id for channel in comparables} == {"UC_a"}  # did not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

```python
# append to src/nicheradar/discovery/channel_analysis.py
MAX_COMPARABLES = 8
VIDIQ_BUDGET_ERROR_CODES = {
    "run_budget_exhausted", "period_budget_exhausted", "balance_exhausted",
    "balance_refresh_required",
}


async def discover_comparables(
    youtube_gateway: Gateway,
    vidiq_gateway: Gateway | None,
    target: Channel,
    now: datetime,
    *,
    max_comparables: int = MAX_COMPARABLES,
) -> tuple[Channel, ...]:
    query = target.category or (target.subtopics[0] if target.subtopics else target.title)
    found: dict[str, Channel] = {}

    youtube_batch, _, _ = await youtube_gateway.fetch(
        Operation.SEARCH, {"type": "channel", "q": query, "maxResults": "25"}, now
    )
    for channel in youtube_batch.channels:
        found[channel.id] = channel

    if vidiq_gateway is not None:
        try:
            vidiq_batch, _, _ = await vidiq_gateway.fetch(
                Operation.CHANNEL_SEARCH, {"query": query}, now
            )
            for channel in vidiq_batch.channels:
                found[channel.id] = channel
        except ProviderError as error:
            if error.code not in VIDIQ_BUDGET_ERROR_CODES:
                raise

    found.pop(target.id, None)
    return tuple(found.values())[:max_comparables]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py tests/test_channel_analysis_discovery.py
git commit -m "feat: discover real comparable channels via YouTube and vidIQ"
```

---

### Task 12: `compute_comparison` — metrics + profit, target excluded from range

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py`
- Test: `tests/test_channel_analysis_discovery.py` (extend)

**Interfaces:**
- Consumes: `channel_view_rate` (Task 10), `scoring.profit.estimate_profit` (existing,
  unchanged — signature: `estimate_profit(*, best_channel_views_per_day, worst_channel_views_per_day, videos_per_month, advertising, monthly_cost_usd) -> ProfitEstimate`).
- Produces: `def compute_comparison(target_videos, target: Channel, comparable_videos: dict[str, tuple[Video, ...]], now, *, videos_per_month=None, advertising=None, monthly_cost_usd=None) -> dict[str, Any]` returning
  `{"target_view_rate": float|None, "comparable_best": float|None, "comparable_worst": float|None, "target_position": "above"|"below"|"within"|"unknown", "profit": <ProfitEstimate as dict>}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_discovery.py
from nicheradar.discovery.channel_analysis import compute_comparison


def test_compute_comparison_positions_target_against_real_comparables() -> None:
    target_videos = (
        Video(id="t1", channel_id="target", title="t", published_at=NOW - timedelta(days=10),
              views=500, format=VideoFormat.LONG),
    )
    comparable_videos = {
        "UC_a": (
            Video(id="a1", channel_id="UC_a", title="t", published_at=NOW - timedelta(days=10),
                  views=100, format=VideoFormat.LONG),
        ),
        "UC_b": (
            Video(id="b1", channel_id="UC_b", title="t", published_at=NOW - timedelta(days=10),
                  views=2000, format=VideoFormat.LONG),
        ),
    }
    result = compute_comparison(
        target_videos, Channel(id="target", title="Target"), comparable_videos, NOW
    )
    assert result["target_view_rate"] == 50.0
    assert result["comparable_worst"] == 10.0
    assert result["comparable_best"] == 200.0
    assert result["target_position"] == "within"
    assert result["profit"]["status"] == "incomplete"  # no videos_per_month/advertising/cost given


def test_compute_comparison_handles_zero_comparables_without_crashing() -> None:
    target_videos = (
        Video(id="t1", channel_id="target", title="t", published_at=NOW - timedelta(days=10),
              views=500, format=VideoFormat.LONG),
    )
    result = compute_comparison(target_videos, Channel(id="target", title="Target"), {}, NOW)
    assert result["comparable_best"] is None
    assert result["comparable_worst"] is None
    assert result["target_position"] == "unknown"
    assert result["profit"]["status"] == "incomplete"
    assert "channel_view_rate" in result["profit"]["missing"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

```python
# append to src/nicheradar/discovery/channel_analysis.py
from typing import Any

from nicheradar.scoring.advertising import AdvertisingBenchmark
from nicheradar.domain.production import EstimateRange
from nicheradar.scoring.profit import estimate_profit


def compute_comparison(
    target_videos: tuple[Video, ...],
    target: Channel,
    comparable_videos: dict[str, tuple[Video, ...]],
    now: datetime,
    *,
    videos_per_month: int | None = None,
    advertising: AdvertisingBenchmark | None = None,
    monthly_cost_usd: EstimateRange | None = None,
) -> dict[str, Any]:
    target_rate = channel_view_rate(target_videos, now)
    rates = [
        rate
        for videos in comparable_videos.values()
        if (rate := channel_view_rate(videos, now)) is not None
    ]
    best = max(rates) if rates else None
    worst = min(rates) if rates else None
    position = "unknown"
    if target_rate is not None and best is not None and worst is not None:
        position = "above" if target_rate > best else "below" if target_rate < worst else "within"
    profit = estimate_profit(
        best_channel_views_per_day=best,
        worst_channel_views_per_day=worst,
        videos_per_month=videos_per_month,
        advertising=advertising,
        monthly_cost_usd=monthly_cost_usd,
    )
    return {
        "target_view_rate": target_rate,
        "comparable_best": best,
        "comparable_worst": worst,
        "target_position": position,
        "profit": profit.model_dump(mode="json"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py tests/test_channel_analysis_discovery.py
git commit -m "feat: compute target-vs-comparables position and profit estimate"
```

---

### Task 13: Wire the stage sequence into `workers/pipeline.py`

**Files:**
- Modify: `src/nicheradar/workers/pipeline.py`
- Test: `tests/test_channel_analysis_pipeline.py` (new)

**Interfaces:**
- Consumes: Tasks 8–12, `channel_analysis_youtube_tariffs/limits`, `channel_analysis_vidiq_tariffs/limits` (Task 7).
- Produces: `Pipeline.process()` recognizes `run["trigger"] == "channel_analysis"` and
  dispatches `CHANNEL_ANALYSIS_STAGES` via `confirm_channel_analysis_stage` instead of the
  catalog stage sequence.

**Note:** read `Pipeline.process()`'s full current body first (it's the file's central
dispatch loop, already read in full earlier this session — see the `if stage == "planning":` /
`elif stage == "query":` chain). This task adds a parallel branch gated at the very top of
the loop body, before the existing `if stage == "planning":` check, so the two sequences
never interleave.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_analysis_pipeline.py
import asyncio

import pytest
from sqlalchemy import Engine, select

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.workers.channel_analysis_queue import CHANNEL_ANALYSIS_STAGES
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_channel_analysis_run_completes_through_every_stage(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run_id = insert_record(
            connection, "analysis_runs",
            {"profile_id": profile_id, "mode": "synthetic", "trigger": "channel_analysis",
             "status": "running", "configuration": {"channel_input": "@scienceexplained"}},
        )
        job_id = insert_record(
            connection, "jobs",
            {"run_id": run_id, "occurrence_key": "test-ca-pipeline-1", "status": "queued",
             "stage": CHANNEL_ANALYSIS_STAGES[0], "checkpoints": {}, "available_at": NOW},
        )
    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(job_id, "test-worker"))
    with isolated_engine.connect() as connection:
        job = connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one()
    assert job["status"] in {"succeeded", "partial"}
    assert set(job["checkpoints"]) >= set(CHANNEL_ANALYSIS_STAGES[:1])
```

(Adjust the `Pipeline(...)` constructor call to match its real signature from
`tests/test_discovery.py::run_pipeline` if it differs — e.g. it may need
`maximum_calls=...` or a `settings=` argument; that helper is the authoritative template.)

```python
@pytest.mark.postgres
def test_second_analysis_same_week_hits_search_quota_cleanly(isolated_engine: Engine) -> None:
    """Default youtube_search_quota_per_run == _per_week == 100: one search.list call (100
    units) already exhausts the week. A second analysis's discover_comparables stage must
    fail as a clean partial job, never hang, crash, or silently skip to a disallowed source.
    """
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())

        def make_job(key: str) -> tuple:
            run_id = insert_record(
                connection, "analysis_runs",
                {"profile_id": profile_id, "mode": "synthetic", "trigger": "channel_analysis",
                 "status": "running", "configuration": {"channel_input": "@scienceexplained"}},
            )
            job_id = insert_record(
                connection, "jobs",
                {"run_id": run_id, "occurrence_key": key, "status": "queued",
                 "stage": "discover_comparables",
                 "checkpoints": {"resolve": {"channel": {"id": "UC1", "title": "Science"}}},
                 "available_at": NOW},
            )
            return run_id, job_id

        _, first_job_id = make_job("test-ca-quota-1")
        _, second_job_id = make_job("test-ca-quota-2")

    pipeline = Pipeline(isolated_engine, clock=lambda: NOW, provider=SyntheticProvider())
    asyncio.run(pipeline.process(first_job_id, "test-worker"))
    asyncio.run(pipeline.process(second_job_id, "test-worker"))

    with isolated_engine.connect() as connection:
        second_job = connection.execute(
            select(s.jobs).where(s.jobs.c.id == second_job_id)
        ).mappings().one()
    assert second_job["status"] == "partial"
    # Partial reasons live in the checkpoint JSON (same convention as the catalog flow's
    # `coverage["pending_reason"]`), not the `error_code` column — that column is only
    # written by fail_job() for hard failures, which this path deliberately avoids.
    assert second_job["checkpoints"]["discover_comparables"]["reason"] in {
        "run_budget_exhausted", "period_budget_exhausted",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_pipeline.py -v`
Expected: FAIL (job never advances — `process()` doesn't recognize the trigger yet, loops
forever on an unmatched stage or raises).

- [ ] **Step 3: Add the dispatch branch**

Inside `Pipeline.process()`, immediately after `run = (...)` is fetched and before the
existing `stage = job["stage"]` / `if stage == "planning":` chain, add:

```python
                    if run["trigger"] == "channel_analysis":
                        await self._process_channel_analysis_stage(job, run, owner, now)
                        continue
```

Then add the new method to the `Pipeline` class:

```python
    async def _process_channel_analysis_stage(
        self, job: dict[str, Any], run: dict[str, Any], owner: str, now: datetime
    ) -> None:
        from nicheradar.discovery.channel_analysis import (
            compute_comparison, discover_comparables, fetch_channel_videos, resolve_channel,
        )
        from nicheradar.services.channel_analysis_providers import (
            channel_analysis_vidiq_limits, channel_analysis_vidiq_tariffs,
            channel_analysis_youtube_limits, channel_analysis_youtube_tariffs,
        )
        from nicheradar.workers.channel_analysis_queue import confirm_channel_analysis_stage

        stage = job["stage"]
        checkpoints = job["checkpoints"]
        profile = CreatorProfile.model_validate(
            self.engine  # placeholder — reuse the same profile-loading lines already
            # present a few lines above in process() for the existing branch, do not
            # refetch differently; pass `profile` into this method instead of reloading it
            # if that reads more naturally once you see the surrounding code.
        )
        # Codes that mean "budget/quota ran out" — these must leave the job `partial`
        # with the reason visible, never propagate to the generic fail_job() path (which
        # would retry or mark the job "failed"/"deferred" instead of "partial", and would
        # not match the spec's "falla esa etapa específica con un error claro" contract).
        budget_error_codes = {
            "run_budget_exhausted", "period_budget_exhausted", "balance_exhausted",
            "balance_refresh_required", "shared_budget_exhausted",
        }
        with self.engine.begin() as connection:
            youtube_gateway = Gateway(
                self.engine, self.youtube, run["profile_id"], run["id"], self.settings.youtube_auth_scope,
                profile, channel_analysis_youtube_limits(self.settings),
                channel_analysis_youtube_tariffs(), maximum_calls=self.maximum_calls,
            )
            vidiq_gateway = Gateway(
                self.engine, self.provider, run["profile_id"], run["id"], "vidiq-scope",
                profile, channel_analysis_vidiq_limits(profile),
                channel_analysis_vidiq_tariffs(), maximum_calls=self.maximum_calls,
            ) if self.provider.name == "vidiq" else None
            try:
                if stage == "resolve":
                    channel = await resolve_channel(
                        youtube_gateway, run["configuration"]["channel_input"], now
                    )
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage,
                        {"channel": channel.model_dump(mode="json")},
                    )
                elif stage == "target_videos":
                    channel = Channel.model_validate(checkpoints["resolve"]["channel"])
                    videos = await fetch_channel_videos(youtube_gateway, channel, now)
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage,
                        {"videos": [video.model_dump(mode="json") for video in videos]},
                    )
                elif stage == "discover_comparables":
                    channel = Channel.model_validate(checkpoints["resolve"]["channel"])
                    comparables = await discover_comparables(
                        youtube_gateway, vidiq_gateway, channel, now
                    )
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage,
                        {"comparables": [c.model_dump(mode="json") for c in comparables]},
                    )
                elif stage == "comparable_videos":
                    comparables = [
                        Channel.model_validate(c)
                        for c in checkpoints["discover_comparables"]["comparables"]
                    ]
                    videos_by_channel = {}
                    for comparable in comparables:
                        videos_by_channel[comparable.id] = [
                            v.model_dump(mode="json")
                            for v in await fetch_channel_videos(youtube_gateway, comparable, now)
                        ]
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage,
                        {"videos_by_channel": videos_by_channel},
                    )
                elif stage == "metrics":
                    # Pure computation, no provider calls — see Task 12's compute_comparison.
                    target_videos = tuple(
                        Video.model_validate(v) for v in checkpoints["target_videos"]["videos"]
                    )
                    channel = Channel.model_validate(checkpoints["resolve"]["channel"])
                    comparable_videos = {
                        channel_id: tuple(Video.model_validate(v) for v in videos)
                        for channel_id, videos
                        in checkpoints["comparable_videos"]["videos_by_channel"].items()
                    }
                    comparison = compute_comparison(target_videos, channel, comparable_videos, now)
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage, comparison
                    )
                elif stage == "profit":
                    # Profit is already computed inside compute_comparison (Task 12); this
                    # stage exists so the sequence matches the spec 1:1 and leaves room for a
                    # future task (e.g. attaching a specific recipe/advertising lookup)
                    # without renumbering stages. For now it just carries the prior
                    # checkpoint forward.
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage, checkpoints["metrics"]
                    )
                elif stage == "persist":
                    from nicheradar.services.channel_analysis import save_channel_analysis

                    save_channel_analysis(connection, run["id"], run["profile_id"], checkpoints, now)
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage, {"saved": True}
                    )
            except ProviderError as error:
                if error.code not in budget_error_codes:
                    raise
                confirm_channel_analysis_stage(
                    connection, job["id"], owner, now, stage,
                    {"reason": error.code}, partial=True,
                )
```

(This sketch is long and touches real gateway construction — before finalizing, check the
real `Gateway.__init__` signature from the research already gathered this session, and
adapt the `profile`-loading line marked above to reuse whatever `process()` already does
two dozen lines earlier in the same method, rather than the placeholder comment shown.
Remove the placeholder comment before committing — it violates the plan's own
no-placeholder rule and exists here only because this sketch must adapt to code the
implementer will have open, not code quoted fully in this plan.)

- [ ] **Step 4: Run test to verify it passes**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/workers/pipeline.py tests/test_channel_analysis_pipeline.py
git commit -m "feat: dispatch channel-analysis stage sequence in the worker"
```

---

### Task 14: Persistence (`services/channel_analysis.py`)

**Files:**
- Create: `src/nicheradar/services/channel_analysis.py`
- Test: `tests/test_channel_analysis_service.py` (new)

**Interfaces:**
- Produces: `save_channel_analysis(connection, run_id, profile_id, checkpoints: dict, now) -> UUID`; `list_channel_analyses(connection, *, limit=20, offset=0) -> dict[str, Any]` (mirrors `backlog()`'s `{"items", "total", "limit", "offset"}` shape); `channel_analysis_detail(connection, analysis_id) -> dict[str, Any] | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_analysis_service.py
import pytest
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.channel_analysis import (
    channel_analysis_detail, list_channel_analyses, save_channel_analysis,
)
from tests.test_persistence import NOW


@pytest.mark.postgres
def test_save_then_list_then_detail(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    run_id = insert_record(
        db, "analysis_runs",
        {"profile_id": profile_id, "mode": "synthetic", "trigger": "channel_analysis",
         "status": "succeeded", "configuration": {"channel_input": "@scienceexplained"}},
    )
    checkpoints = {
        "resolve": {"channel": {"id": "UC1", "title": "Science"}},
        "metrics": {"target_view_rate": 50.0, "comparable_best": 200.0,
                    "comparable_worst": 10.0, "target_position": "within",
                    "profit": {"status": "incomplete", "missing": ["videos_per_month"]}},
    }
    analysis_id = save_channel_analysis(db, run_id, profile_id, checkpoints, NOW)
    db.commit()

    listed = list_channel_analyses(db, limit=20, offset=0)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == analysis_id
    assert listed["items"][0]["channel_external_id"] == "UC1"

    detail = channel_analysis_detail(db, analysis_id)
    assert detail is not None
    assert detail["snapshot"]["metrics"]["target_position"] == "within"

    assert channel_analysis_detail(db, "00000000-0000-0000-0000-000000000000") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_service.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# src/nicheradar/services/channel_analysis.py
"""Persistence for saved channel-analysis reports; mirrors services/console.py's
pagination shape. Each row is immutable — re-analyzing creates a new row."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import channel_analyses


def save_channel_analysis(
    connection: Connection, run_id: UUID, profile_id: UUID, checkpoints: dict[str, Any], now: datetime
) -> UUID:
    # This is only ever called from the pipeline's final "persist" stage (Task 13), which
    # only runs once every earlier stage has already confirmed cleanly — so the row is
    # "completed" by construction. A stage that hit a budget wall exits via the pipeline's
    # own partial-confirm path (Task 13's except block) and never reaches persist at all;
    # a channel-not-found or similar hard failure never reaches it either (Task 9's
    # ProviderError propagates to the generic fail_job() path instead).
    channel = checkpoints.get("resolve", {}).get("channel", {})
    return insert_record(
        connection,
        "channel_analyses",
        {
            "profile_id": profile_id,
            "run_id": run_id,
            "channel_input": channel.get("title", ""),
            "channel_external_id": channel.get("id"),
            "status": "completed",
            "configuration": {},
            "snapshot": checkpoints,
            "consumption": {},
            "created_at": now,
            "retain_until": now + timedelta(days=180),
        },
    )


def list_channel_analyses(
    connection: Connection, *, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    total = connection.execute(
        select(func.count()).select_from(channel_analyses)
    ).scalar_one()
    rows = (
        connection.execute(
            select(channel_analyses)
            .order_by(channel_analyses.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def channel_analysis_detail(connection: Connection, analysis_id: UUID) -> dict[str, Any] | None:
    row = (
        connection.execute(select(channel_analyses).where(channel_analyses.c.id == analysis_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_service.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/services/channel_analysis.py tests/test_channel_analysis_service.py
git commit -m "feat: persist and list saved channel analyses"
```

---

### Task 15: API endpoints

**Files:**
- Modify: `src/nicheradar/api.py`
- Test: `tests/test_channel_analysis_api.py` (new)

**Interfaces:**
- Produces: `POST /api/v1/channel-analyses` (body `{"channel_input": str}`, header `Idempotency-Key`, mirrors `manual_run`), `GET /api/v1/channel-analyses`, `GET /api/v1/channel-analyses/{id}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channel_analysis_api.py
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.api import create_app
from nicheradar.config import Settings
from tests.test_foundation import TOKEN


@pytest.mark.postgres
def test_post_requires_auth_and_enqueues(isolated_engine: Engine) -> None:
    client = TestClient(create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine))
    path = "/api/v1/channel-analyses"
    assert client.post(path, json={"channel_input": "@x"}).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        path, json={"channel_input": "@x"}, headers={"Idempotency-Key": "a" * 10}
    )
    assert response.status_code == 202
    assert "job_id" in response.json()

    listing = client.get(path)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 0

    detail = client.get(f"{path}/00000000-0000-0000-0000-000000000000")
    assert detail.status_code == 404


@pytest.mark.postgres
def test_post_rejects_unsupported_channel_input(isolated_engine: Engine) -> None:
    client = TestClient(create_app(Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine))
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    response = client.post(
        "/api/v1/channel-analyses",
        json={"channel_input": "not a real channel"},
        headers={"Idempotency-Key": "b" * 10},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_api.py -v`
Expected: FAIL (404 — routes don't exist).

- [ ] **Step 3: Add the endpoints**

In `src/nicheradar/api.py`, mirror `manual_run` (`POST /runs`) closely. Add near it:

```python
class ChannelAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_input: str = Field(min_length=1, max_length=500)


@router.post("/channel-analyses", status_code=202)
def request_channel_analysis(
    body: ChannelAnalysisRequest,
    connection: Annotated[Connection, Depends(db)],
    idempotency_key: Annotated[str, Header(min_length=8, max_length=100)],
) -> dict[str, str]:
    from nicheradar.discovery.channel_analysis import parse_channel_input
    from nicheradar.workers.channel_analysis_queue import CHANNEL_ANALYSIS_STAGES

    try:
        parse_channel_input(body.channel_input)
    except ValueError:
        raise HTTPException(422, "No se reconoce ese canal; usa su @handle o su ID (UC...).") from None
    connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
    profile_id, _, _ = get_profile(connection)
    if config.mode == "live":
        require_live_ready(connection, scheduled=False)
    key = f"channel-analysis:{profile_id}:{config.mode}:{idempotency_key}"
    existing = connection.execute(
        select(s.jobs.c.id).where(s.jobs.c.occurrence_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return {"job_id": str(existing), "status": "accepted", "status_url": f"/api/v1/jobs/{existing}"}
    run_id = insert_record(
        connection, "analysis_runs",
        {"profile_id": profile_id, "mode": config.mode, "trigger": "channel_analysis",
         "status": "running", "configuration": {"channel_input": body.channel_input}},
    )
    job_id = insert_record(
        connection, "jobs",
        {"run_id": run_id, "occurrence_key": key, "status": "queued",
         "stage": CHANNEL_ANALYSIS_STAGES[0], "checkpoints": {}, "available_at": clock()},
    )
    return {"job_id": str(job_id), "status": "accepted", "status_url": f"/api/v1/jobs/{job_id}"}


@router.get("/channel-analyses")
def channel_analyses_list(
    connection: Annotated[Connection, Depends(db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    from nicheradar.services.channel_analysis import list_channel_analyses

    return list_channel_analyses(connection, limit=limit, offset=offset)


@router.get("/channel-analyses/{analysis_id}")
def channel_analysis_detail_endpoint(
    analysis_id: UUID, connection: Annotated[Connection, Depends(db)]
) -> dict[str, Any]:
    from nicheradar.services.channel_analysis import channel_analysis_detail

    result = channel_analysis_detail(connection, analysis_id)
    if result is None:
        raise HTTPException(404, "Análisis no encontrado")
    return result
```

(Check real import availability for `insert_record`/`select`/`func`/`QUEUE_LOCK`/
`get_profile`/`require_live_ready` at the top of `api.py` — all are already imported for
`manual_run`; reuse the same names, do not re-import under different aliases.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_api.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/api.py tests/test_channel_analysis_api.py
git commit -m "feat: channel-analysis API endpoints"
```

---

### Task 16: Dashboard tab

**Files:**
- Modify: `src/nicheradar/dashboard.py`
- Test: `tests/test_dashboard_navigation.py` (extend)

**Interfaces:**
- Produces: `render_channel_analysis(config: Settings) -> None`, wired into the sidebar
  `st.radio` options list, as its own page (per the spec: separate from Home).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_dashboard_navigation.py, inside the existing navigation test or as
# a new focused test following the same AppTest + LocalClient pattern already in this file
def test_channel_analysis_tab_renders_without_exception(...):
    ...
    app.radio[0].set_value("Análisis de canal").run()
    assert not app.exception
    assert "URL, handle o ID" in str(app.text_input[-1].label)
```

(Fit this into the existing test function's flow, after the other `app.radio[0].set_value(...)`
calls, using the same `backend`/`LocalClient` fixtures already set up earlier in that test —
do not duplicate the whole AppTest bootstrap in a new test function unless the existing
one has grown unwieldy enough to warrant splitting, matching this codebase's established
"follow existing patterns" convention.)

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_dashboard_navigation.py -v`
Expected: FAIL ("Análisis de canal" not a valid radio option yet).

- [ ] **Step 3: Add the page**

Add `"Análisis de canal"` to the `st.sidebar.radio(...)` options tuple in `render()`, and
dispatch it alongside the existing `elif page == "Operación":` branches. Then add:

```python
def render_channel_analysis(config: Settings) -> None:
    st.subheader("Análisis de canal")
    st.caption(
        "Investiga si hay oportunidad de competir en el nicho de un canal real. Usa su "
        "@handle o su ID de canal (UC...); URLs con /c/ o /user/ todavía no se reconocen."
    )
    with st.form("channel-analysis-request"):
        channel_input = st.text_input("URL, handle o ID del canal")
        st.caption(
            "Costo máximo real por análisis: hasta 50 créditos vidIQ y 1 búsqueda "
            "(100 unidades) de cuota de YouTube."
        )
        if st.form_submit_button("Analizar") and channel_input:
            api_request(
                config, "POST", "/channel-analyses",
                body={"channel_input": channel_input},
                headers={"Idempotency-Key": str(uuid4())},
            )
            st.success("Análisis encolado. Aparecerá abajo cuando el radar lo procese.")
    result = api_request(config, "GET", "/channel-analyses?limit=20")
    if not result["items"]:
        st.info("Todavía no hay análisis de canal guardados.")
        return
    st.dataframe(
        [
            {
                "Canal": item.get("channel_input"),
                "Estado": item.get("status"),
                "Creado": local_time(str(item.get("created_at")), config.timezone),
            }
            for item in result["items"]
        ],
        hide_index=True, width="stretch",
    )
    selected_id = st.selectbox(
        "Ver detalle", [item["id"] for item in result["items"]],
        format_func=lambda analysis_id: next(
            item["channel_input"] for item in result["items"] if item["id"] == analysis_id
        ),
    )
    if selected_id:
        detail = api_request(config, "GET", f"/channel-analyses/{selected_id}")
        render_structured(detail.get("snapshot") or {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_dashboard_navigation.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/dashboard.py tests/test_dashboard_navigation.py
git commit -m "feat: Análisis de canal dashboard tab"
```

---

### Task 17: Docs update

**Files:**
- Create: `docs/channel-analysis.md`
- Modify: `README.md` (add to the doc list)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Write `docs/channel-analysis.md`**

Summarize, in this project's established documentation style (see
`docs/creator-fit-rubric.md`/`docs/advertising-scoring.md` for tone and structure): the
flow end to end, the real budget numbers from the Global Constraints section above, the
explicit exclusions (Social Blade/RSS/Google Trends and why), the scope cut on
`/c/`/`/user/` URLs, and the test files that cover it.

- [ ] **Step 2: Add a line to `README.md`'s doc list**

```markdown
- [Análisis competitivo de canal](docs/channel-analysis.md).
```

- [ ] **Step 3: Commit**

```bash
git add docs/channel-analysis.md README.md
git commit -m "docs: channel competitive analysis"
```

---

## Self-Review

**Spec coverage:** Fuentes de datos (Tasks 2–4, 7), flujo paso a paso (Tasks 9–12),
ejecución vía cola de trabajos (Tasks 8, 13), modelo de datos (Task 1), presupuesto
(Tasks 5–7), API (Task 15), UI (Task 16), manejo de errores/degradación (Task 11's
`VIDIQ_BUDGET_ERROR_CODES` path for vidIQ, Task 13's `budget_error_codes` try/except for
YouTube, Task 9's `channel_not_found`, Task 15's 422 on unsupported input). Found and
fixed during review: Task 13's first draft let a YouTube budget/quota `ProviderError`
propagate to the generic `fail_job()` path, which would have produced `status="failed"`
(with retry/defer semantics) instead of the spec's "falla esa etapa específica con un
error claro" — added an explicit `try/except ProviderError` around the per-stage dispatch
that converts only budget-related codes into a `partial` confirm via
`confirm_channel_analysis_stage(..., partial=True)`, mirroring exactly how the existing
catalog flow's `query()`/`collect()` already do this. Non-budget errors (e.g.
`channel_not_found`, `contract_mismatch`) still propagate to the existing outer handler
unchanged.

**Placeholder scan:** Task 13 contains two explicit, flagged adaptation notes (the
`profile`-loading line and "read the real function first") rather than unresolved TBDs —
they tell the implementer which exact lines to go read before writing, not what to leave
unfinished. No bare `TODO`/`TBD`/"handle appropriately" language remains anywhere else in
the plan.

**Type consistency:** `Channel`/`Video`/`ProfitEstimate`/`EstimateRange` used identically
across Tasks 9–13 (same import paths, same `.model_dump(mode="json")` round-trip
convention already established elsewhere in this codebase for JSONB storage).

**Review Focus coverage, all five now have an owning test:** unsupported input (Task 9 +
Task 15), target-as-own-comparable (Task 11's dedup+exclude test), vidIQ already
exhausted before call #1 (Task 11's degrade test), same-day double search-quota
exhaustion (Task 13's `test_second_analysis_same_week_hits_search_quota_cleanly`, added
during this review — exercises the real `reserve()` week-cap check across two separate
`analysis_runs`, asserts `status == "partial"` with the reason in the checkpoint, not a
crash), zero comparables found (Task 12's
`test_compute_comparison_handles_zero_comparables_without_crashing`, added during this
review — asserts `"unknown"` position and `"incomplete"` profit with
`"channel_view_rate"` in the missing list, never a fabricated comparable).
