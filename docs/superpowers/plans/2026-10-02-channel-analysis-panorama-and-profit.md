# Channel Analysis: Niche Panorama, Real Profit, Better Comparables — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between the approved channel-analysis spec and what the first implementation actually delivered: compute a real niche panorama (demand/concentration/breakout) over comparables, wire real profit estimation (recipe + a new project-wide advertising benchmark) into the pipeline, discover comparables from the target channel's own content instead of its bare title, and correct the real YouTube search-quota numbers.

**Architecture:** Every task reuses existing, already-tested machinery (`features/metrics.py::calculate()`, `services/production.py::default_recipe()`, `services/scenarios.py::simulate()`) rather than inventing new scoring logic — the only new state is one optional field on the existing project-wide `CreatorProfile` (no new table, no migration). All changes land in `src/nicheradar/discovery/channel_analysis.py`, `src/nicheradar/workers/pipeline.py`'s `_process_channel_analysis_stage`, `src/nicheradar/domain/profile.py`, `src/nicheradar/dashboard.py`, `src/nicheradar/integrations/youtube.py`/`synthetic.py`, and `src/nicheradar/config.py`.

**Tech Stack:** Python, FastAPI, Streamlit, SQLAlchemy/PostgreSQL, Pydantic — same stack as the rest of NicheRadar. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-channel-competitive-analysis-design.md` (original, already approved — this plan completes goal 1's "panorama del nicho" and step 9's profit estimation, which the first implementation left incomplete; confirmed via live research with the project owner, recorded in the conversation this plan was written from).

## Global Constraints

- Never invent RPM, costs, or metrics — every profit/panorama field must resolve to a real declared value or an explicit `incomplete`/`unknown`/`insufficient_evidence` state (project-wide anti-fabrication rule, unchanged from the original plan).
- All work continues on the existing branch/worktree: `worktree-channel-competitive-analysis` at `/Users/davidrodriguez/Programming/radar-nicho-yt/.claude/worktrees/channel-competitive-analysis`. Do not create a new worktree. Current HEAD before this plan starts: `6c9ec01`.
- `search.list`'s real cost is a flat 100 units regardless of `maxResults` (confirmed by the project owner's own Google Cloud Console) — never add a second `search.list` call (e.g. pagination) without an explicit, separate budget decision.
- The `Limits`/`calendar_windows()` budget system (`services/budget.py`) has no day-level granularity and is explicitly OUT OF SCOPE to extend in this plan — quota corrections here are config-value changes only, never changes to that shared module.
- `featuredChannelsUrls` and any HTML-scraping-based "similar channels" source are explicitly rejected (validated live against real channels; proven to be noise or redundant) — no task in this plan touches either.
- Run `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin` before every `uv run pytest` invocation that touches `@pytest.mark.postgres` tests.

## Review Focus

- A target channel whose `description` has no hashtags and no `keywords` (bare/empty profile) must still get a usable (if weaker) comparable-discovery query — never crash, never silently search for an empty string (Task 2).
- A channel-analysis run where the owner has NOT configured the new advertising benchmark must still complete and persist with `profit.status == "incomplete"` and the real missing-reason, never a crash or a fabricated number (Task 7).
- The panorama computation must tolerate zero comparable videos (e.g., every comparable's video fetch returned nothing) without crashing `calculate()` — mixed video formats across comparables must not raise `calculate()`'s own `ValueError("mixed formats cannot be evaluated as one cohort")` uncaught (Task 4).
- A malformed/missing YouTube `brandingSettings.channel.keywords` string (not every real channel sets this) must parse to an empty tuple, not raise (Task 1).
- The new advertising-benchmark Configuración form must let the owner leave it unset (clearing a previously-set benchmark back to `None`) without validation errors blocking the rest of the form (Task 6).

---

### Task 1: `Channel.keywords` — real YouTube branding keywords

**Files:**
- Modify: `src/nicheradar/integrations/contracts.py` (`Channel` class, ~line 63-74)
- Modify: `src/nicheradar/integrations/youtube.py` (`fetch()`'s `part` assembly ~line 96-101, `_normalize` CHANNELS branch ~line 164-179)
- Modify: `src/nicheradar/integrations/synthetic.py` (CHANNELS/CHANNEL_SEARCH/SEARCH fixture branch)
- Test: `tests/test_channel_analysis_youtube.py` (extend), `tests/test_adapters.py` (extend if it already covers CHANNELS normalization — check first)

**Interfaces:**
- Produces: `Channel.keywords: tuple[str, ...] = ()` — new field, always present, empty tuple when the channel never declared any.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_youtube.py
import httpx

from nicheradar.integrations.contracts import Operation
from nicheradar.integrations.youtube import YouTubeProvider


def test_channels_list_requests_branding_settings_and_parses_keywords() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC1",
                        "snippet": {"title": "Revenge Showdown", "description": "desc"},
                        "statistics": {"subscriberCount": "100"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                        "brandingSettings": {
                            "channel": {"keywords": ('"Cheating wife" "Reddit stories" singleword')}
                        },
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    import asyncio
    from datetime import UTC, datetime

    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UC1"}, datetime.now(UTC)))
    assert "brandingSettings" in captured["request"].url.params["part"]
    channel = batch.channels[0]
    assert channel.keywords == ("Cheating wife", "Reddit stories", "singleword")


def test_channels_list_keywords_default_to_empty_tuple_when_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC2",
                        "snippet": {"title": "No Keywords Channel"},
                        "statistics": {"subscriberCount": "5"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU2"}},
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    import asyncio
    from datetime import UTC, datetime

    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UC2"}, datetime.now(UTC)))
    assert batch.channels[0].keywords == ()
```

(`_provider(transport)` is an existing helper already defined at the top of `tests/test_channel_analysis_youtube.py` — confirmed: `def _provider(transport: httpx.MockTransport) -> YouTubeProvider: return YouTubeProvider(SecretStr("key"), "scope", enabled=True, transport=transport)`. Reuse it exactly as shown above; do not construct `YouTubeProvider(...)` directly or invent a `_secret` helper.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_youtube.py -v`
Expected: FAIL (`AttributeError: 'Channel' object has no attribute 'keywords'`, and the `part` assertion fails since `brandingSettings` isn't requested yet).

- [ ] **Step 3: Add the field and real parsing**

In `src/nicheradar/integrations/contracts.py`, add to `Channel` (after `subtopics`):

```python
    keywords: tuple[str, ...] = ()
```

In `src/nicheradar/integrations/youtube.py`, find the `part` assembly inside `fetch()` (the `else: params["part"] = "snippet,contentDetails,statistics"` branch used for CHANNELS/UPLOADS/VIDEOS) and change the CHANNELS case specifically to also request `brandingSettings`:

```python
        if operation == Operation.UPLOADS:
            params["part"] = "snippet,contentDetails"
        elif operation in {Operation.SEARCH, Operation.COMMENT_THREADS, Operation.VIDEO_CATEGORIES}:
            params["part"] = "snippet"
        elif operation == Operation.CHANNELS:
            params["part"] = "snippet,contentDetails,statistics,brandingSettings"
        else:
            params["part"] = "snippet,contentDetails,statistics"
```

Add a module-level keyword parser near the top of `youtube.py` (YouTube's `brandingSettings.channel.keywords` is one shell-quoted string, e.g. `'"Cheating wife" "Reddit stories" singleword'` — `shlex.split` parses this exactly):

```python
import shlex


def _parse_keywords(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        return tuple(shlex.split(raw))
    except ValueError:
        # Unbalanced quotes in a creator-supplied field — fail soft, not loud.
        return tuple(raw.split())
```

In the CHANNELS normalization branch (where `Channel(...)` is constructed), add:

```python
keywords = (_parse_keywords(row.get("brandingSettings", {}).get("channel", {}).get("keywords")),)
```

- [ ] **Step 4: Update the synthetic fixture**

Open `src/nicheradar/integrations/synthetic.py` and find the generic CHANNELS/CHANNEL_SEARCH/SEARCH fixture branch that constructs `Channel(...)` objects (the one keyed by `family`). Add a `keywords=(family, f"{family} explained")` (or similarly derived from whatever variable that branch already uses to name/title the fixture channels — match its existing style, do not hardcode unrelated literal strings) so every synthetic channel has non-empty keywords. Add one assertion to whichever existing synthetic-provider test already checks the CHANNELS/SEARCH fixture shape (grep `tests/test_synthetic*.py` or wherever Task 3's original synthetic tests live) confirming `channel.keywords` is non-empty.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_youtube.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/integrations/contracts.py src/nicheradar/integrations/youtube.py src/nicheradar/integrations/synthetic.py tests/test_channel_analysis_youtube.py
git commit -m "feat: parse real YouTube branding keywords onto Channel"
```

---

### Task 2: Derive comparable-discovery query from keywords/description, raise maxResults to 50

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py` (`discover_comparables`, ~line 83-114)
- Test: `tests/test_channel_analysis_discovery.py` (extend)

**Interfaces:**
- Consumes: `Channel.keywords` (Task 1), `Channel.description` (already existed).
- Produces: `discover_comparables`'s query-derivation behavior changes; its signature and `ComparableDiscovery` return type are UNCHANGED.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_discovery.py
def test_discover_comparables_queries_by_keyword_not_title() -> None:
    target = Channel(
        id="UC_target",
        title="Revenge Showdown",
        description="#revengestories #familydrama",
        keywords=("reddit revenge stories", "family drama"),
    )
    captured: dict[str, Any] = {}

    class CapturingGateway:
        async def fetch(self, operation, parameters, now):
            captured["parameters"] = parameters
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(returned=0, selection_method="fake"),
                    costs=(),
                    channels=(),
                ),
                "fake-request-id",
                now,
            )

    asyncio.run(discover_comparables(CapturingGateway(), None, target, datetime.now(UTC)))
    assert captured["parameters"]["q"] == "reddit revenge stories"
    assert captured["parameters"]["maxResults"] == "50"


def test_discover_comparables_falls_back_to_description_hashtag_then_title() -> None:
    no_keywords = Channel(
        id="UC_target", title="Revenge Showdown", description="Welcome! #revengestories here"
    )
    bare = Channel(id="UC_bare", title="Bare Title Channel")
    captured: list[str] = []

    class CapturingGateway:
        async def fetch(self, operation, parameters, now):
            captured.append(parameters["q"])
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(returned=0, selection_method="fake"),
                    costs=(),
                    channels=(),
                ),
                "fake-request-id",
                now,
            )

    asyncio.run(discover_comparables(CapturingGateway(), None, no_keywords, datetime.now(UTC)))
    asyncio.run(discover_comparables(CapturingGateway(), None, bare, datetime.now(UTC)))
    assert captured[0] == "revengestories"
    assert captured[1] == "Bare Title Channel"
```

(Add `import asyncio`, `from datetime import UTC, datetime`, `from typing import Any`, and `from nicheradar.integrations.contracts import Batch, Coverage, Provenance` to the test file's imports if not already present — check first, this file already has several of these from earlier tasks.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (query still derived from `category`/`subtopics`/`title`, and `maxResults` is still `"25"`).

- [ ] **Step 3: Implement**

In `src/nicheradar/discovery/channel_analysis.py`, add a query-derivation helper and use it:

```python
import re as _re  # already imported as `re` at module top — reuse that import, do not re-import

_HASHTAG = re.compile(r"#(\w+)")


def _discovery_query(target: Channel) -> str:
    if target.keywords:
        return target.keywords[0]
    if target.description:
        hashtag = _HASHTAG.search(target.description)
        if hashtag:
            return hashtag.group(1)
    return target.title
```

Replace the existing line:

```python
    query = target.category or (target.subtopics[0] if target.subtopics else target.title)
```

with:

```python
    query = _discovery_query(target)
```

And change the YouTube search call's `maxResults` from `"25"` to `"50"`:

```python
    youtube_batch, _, _ = await youtube_gateway.fetch(
        Operation.SEARCH, {"type": "channel", "q": query, "maxResults": "50"}, now
    )
```

(Do not add a second import line for `re` — it is already imported at the top of this file for `_HANDLE`/`_CHANNEL_ID`; just add `_HASHTAG = re.compile(...)` alongside them.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py tests/test_channel_analysis_discovery.py
git commit -m "feat: discover comparables by real keywords/content, not channel title"
```

---

### Task 3: Correct YouTube search-quota defaults

**Files:**
- Modify: `src/nicheradar/config.py`
- Modify: `docs/channel-analysis.md`
- Test: `tests/test_channel_analysis_budget.py` (extend if it asserts the literal default values; otherwise confirm no test hardcodes the old numbers — grep first)

**Interfaces:** none (config-value change only).

- [ ] **Step 1: Write the failing test**

Grep first: `grep -rn "youtube_search_quota_per_week\|youtube_search_quota_per_month" tests/`. If any existing test asserts the literal default `100` for `_per_week` or `300` for `_per_month`, that assertion is the one to update (this IS the "failing test" for this task — update its expected value and watch it fail against the still-unchanged default). If no test asserts these literal defaults, add one:

```python
# append to tests/test_channel_analysis_budget.py
from nicheradar.config import Settings


def test_youtube_search_quota_defaults_match_real_console_values() -> None:
    settings = Settings()
    assert settings.youtube_search_quota_per_run == 100
    assert settings.youtube_search_quota_per_week == 700
    assert settings.youtube_search_quota_per_month == 3000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: FAIL (current defaults are `week=100`, `month=300`).

- [ ] **Step 3: Correct the defaults**

In `src/nicheradar/config.py`, change:

```python
    youtube_search_quota_per_week: int = Field(default=100, ge=0, le=100_000)
    youtube_search_quota_per_month: int = Field(default=300, ge=0, le=1_000_000)
```

to:

```python
    youtube_search_quota_per_week: int = Field(default=700, ge=0, le=100_000)
    youtube_search_quota_per_month: int = Field(default=3000, ge=0, le=1_000_000)
```

(`youtube_search_quota_per_run` stays `100` — unchanged, already correct.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_budget.py -v`
Expected: PASS

- [ ] **Step 5: Update docs**

In `docs/channel-analysis.md`, find the budget/quota table and update the `search.list` week/month figures to `700`/`3000`, and add a short note directly below the table:

```markdown
> **Nota:** Google anunció una migración a un sistema de cuotas más granular para
> `search.list` a partir de junio de 2026, que podría ya estar vigente en tu cuenta.
> Antes de depender de estos números en producción, vuelve a verificar en
> [Google Cloud Console → YouTube Data API v3 → Cuotas](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas).
```

- [ ] **Step 6: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/config.py docs/channel-analysis.md tests/test_channel_analysis_budget.py
git commit -m "fix: correct real YouTube search-quota defaults (100/day confirmed, not week)"
```

---

### Task 4: Real niche panorama via `features/metrics.py::calculate()`

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py` (new function alongside `compute_comparison`)
- Modify: `src/nicheradar/workers/pipeline.py` (`_process_channel_analysis_stage`'s `metrics` branch)
- Test: `tests/test_channel_analysis_discovery.py` (extend), `tests/test_channel_analysis_pipeline.py` (extend)

**Interfaces:**
- Consumes: `features/metrics.py::calculate(members: tuple[Membership, ...], now, *, baseline_minimum=5, breakout_threshold=5) -> CohortMetrics`; `discovery/sampling.py::Membership` (fields: `video`, `included`, `reason`, `size_stratum`, `age_band`, `selection_method` — no topic/cohort coupling); `discovery/sampling.py::age_band(days: float) -> str`.
- Produces: `def compute_panorama(comparable_videos: dict[str, tuple[Video, ...]], now: datetime) -> dict[str, Any]` in `channel_analysis.py`, returning `CohortMetrics.model_dump(mode="json")` or an explicit incomplete marker when there's nothing to compute. The `metrics` stage's checkpoint gains a `"panorama"` key alongside the existing `compute_comparison` fields (`target_view_rate`, `comparable_best`, etc. — unchanged).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_discovery.py
from nicheradar.discovery.channel_analysis import compute_panorama


def test_compute_panorama_computes_real_metrics_across_comparables() -> None:
    comparable_videos = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, NOW)
    assert panorama["status"] == "computed"
    assert panorama["metrics"]["videos"] == 2
    assert panorama["metrics"]["channels"] == 2


def test_compute_panorama_incomplete_when_no_comparable_videos() -> None:
    panorama = compute_panorama({}, NOW)
    assert panorama == {"status": "incomplete", "reason": "no_comparable_videos"}


def test_compute_panorama_skips_mixed_formats_without_crashing() -> None:
    comparable_videos = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.SHORTS,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, NOW)
    assert panorama["status"] == "incomplete"
    assert panorama["reason"] == "mixed_formats_not_evaluable"
```

(`NOW`, `timedelta`, `VideoFormat`, `Video` are already imported in this test file from earlier tasks — confirm, don't re-import if present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`ImportError: cannot import name 'compute_panorama'`).

- [ ] **Step 3: Implement**

Append to `src/nicheradar/discovery/channel_analysis.py`:

```python
from nicheradar.discovery.sampling import Membership, age_band
from nicheradar.features.metrics import calculate


def compute_panorama(
    comparable_videos: dict[str, tuple[Video, ...]], now: datetime
) -> dict[str, Any]:
    all_videos = [video for videos in comparable_videos.values() for video in videos]
    if not all_videos:
        return {"status": "incomplete", "reason": "no_comparable_videos"}
    formats = {video.format for video in all_videos}
    if len(formats) > 1:
        return {"status": "incomplete", "reason": "mixed_formats_not_evaluable"}
    members = tuple(
        Membership(
            video=video,
            included=True,
            reason="channel_analysis_comparable",
            size_stratum="unknown",
            age_band=age_band((now - video.published_at).total_seconds() / 86400)
            if video.published_at
            else "unknown",
            selection_method="channel_analysis",
        )
        for video in all_videos
    )
    metrics = calculate(members, now)
    return {"status": "computed", "metrics": metrics.model_dump(mode="json")}
```

(`age_band` and `Membership` are the exact names/signatures from `discovery/sampling.py` — do not redefine age-banding logic here.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Wire into the pipeline's `metrics` stage**

In `src/nicheradar/workers/pipeline.py`, inside `_process_channel_analysis_stage`'s `elif stage == "metrics":` branch, import `compute_panorama` alongside the existing `compute_comparison` import at the top of the method, then change:

```python
comparison = compute_comparison(target_videos, channel, comparable_videos, now)
confirm_channel_analysis_stage(connection, job["id"], owner, now, stage, comparison)
```

to:

```python
                    comparison = compute_comparison(target_videos, channel, comparable_videos, now)
                    panorama = compute_panorama(comparable_videos, now)
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage, comparison | {"panorama": panorama}
                    )
```

Add `compute_panorama` to the existing `from nicheradar.discovery.channel_analysis import (...)` import block in `_process_channel_analysis_stage`.

- [ ] **Step 6: Write the failing pipeline test**

```python
# append to tests/test_channel_analysis_pipeline.py
def test_channel_analysis_persists_a_real_panorama_alongside_comparison() -> None:
    with isolated_engine.begin() as connection:
        # Reuse the exact same setup as test_channel_analysis_run_completes_through_every_stage
        # (seed_profile, job insert, claim) from this same file — do not duplicate the whole
        # bootstrap, extend that existing test's own assertions instead:
        pass
```

(This step is intentionally a pointer, not a new test function — the real work is: open `test_channel_analysis_run_completes_through_every_stage` in this file and add, after its existing assertions, a fetch of the saved `channel_analyses` row's `snapshot["metrics"]["panorama"]` and assert `["status"] in {"computed", "incomplete"}` — whichever it resolves to for that test's synthetic fixture data — and if `"computed"`, assert `["metrics"]["videos"] > 0`. Extend the existing test function; do not create a parallel one that re-bootstraps the whole job/claim/process sequence.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_pipeline.py -v`
Expected: PASS

- [ ] **Step 8: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py src/nicheradar/workers/pipeline.py tests/test_channel_analysis_discovery.py tests/test_channel_analysis_pipeline.py
git commit -m "feat: compute a real niche panorama (demand/concentration/breakout) for comparables"
```

---

### Task 5: Project-wide advertising benchmark setting on `CreatorProfile`

**Files:**
- Modify: `src/nicheradar/domain/profile.py` (`CreatorProfile`)
- Test: `tests/test_execution.py` or wherever `CreatorProfile` round-trip serialization is already tested (grep `CreatorProfile(` in `tests/` for the simplest existing round-trip test to extend) — if none fits cleanly, add a new focused test file `tests/test_channel_analysis_advertising_benchmark.py`

**Interfaces:**
- Produces: `CreatorProfile.channel_analysis_advertising: dict[str, Any] | None = None` — a new field, storing the RAW serialized benchmark, not the typed `AdvertisingBenchmark` object. **Why raw, not typed:** confirmed by reading both files — `domain/profile.py` currently has zero `nicheradar.*` imports (a clean, dependency-free foundational layer), while `scoring/advertising.py` already imports `from nicheradar.domain.profile import VideoFormat`. Typing this field as `AdvertisingBenchmark` directly would create a real circular import (`domain.profile` → `scoring.advertising` → `domain.profile`) and would also break this project's existing layering (`domain` has no dependents, `scoring` depends on `domain`). Keeping it raw here and validating it into a real `AdvertisingBenchmark` at the point of use (Task 7, in `pipeline.py`, which already imports both modules) is the correct, minimal fix — no new table, no migration: `CreatorProfile` already persists entirely as the `creator_profiles.configuration` JSONB column (confirmed via `seed_profile`/`update_profile` in `src/nicheradar/repositories/core.py`), so this field round-trips through the EXISTING `GET /profile` / `PUT /profile` endpoints automatically once added, exactly like any other dict/JSON field already on this model.

- [ ] **Step 1: Write the failing test**

```python
# new file: tests/test_channel_analysis_advertising_benchmark.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.scoring.advertising import AdvertisingBenchmark


def test_creator_profile_round_trips_an_optional_advertising_benchmark() -> None:
    now = datetime.now(UTC)
    benchmark = AdvertisingBenchmark(
        version="2026-10-02",
        source="owner_declared_estimate",
        origin="manual_assumption",
        format=VideoFormat.LONG,
        language="es",
        audience_key="general",
        unit="usd_ads_per_1000_views",
        rate=EstimateRange(low=Decimal("1.0"), high=Decimal("3.0")),
        revenue_scope="youtube_ads_only_after_revenue_share",
        assumptions="Estimación propia basada en benchmarks públicos del nicho.",
        observed_at=now,
        valid_until=now + timedelta(days=180),
    )
    profile = CreatorProfile(channel_analysis_advertising=benchmark.model_dump(mode="json"))
    restored = CreatorProfile.model_validate(profile.model_dump(mode="json"))
    assert restored.channel_analysis_advertising is not None
    # Stored raw — round-trip it back through AdvertisingBenchmark to prove it's valid.
    revalidated = AdvertisingBenchmark.model_validate(restored.channel_analysis_advertising)
    assert revalidated.rate.low == Decimal("1.0")


def test_creator_profile_defaults_advertising_benchmark_to_none() -> None:
    assert CreatorProfile().channel_analysis_advertising is None


def test_creator_profile_rejects_a_malformed_advertising_benchmark_dict() -> None:
    import pytest

    with pytest.raises(Exception):
        AdvertisingBenchmark.model_validate({"not": "a real benchmark"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_advertising_benchmark.py -v`
Expected: FAIL (`CreatorProfile` has `extra="forbid"` — `channel_analysis_advertising` is rejected as an unknown field).

- [ ] **Step 3: Add the field**

In `src/nicheradar/domain/profile.py`, add (no new nicheradar import needed — `dict`/`Any` come from `typing`, already a standard import; add `Any` to the existing `from typing import Self` line if not already imported):

```python
    channel_analysis_advertising: dict[str, Any] | None = None
```

(Add it near `channel_analysis_credits_per_run`, which already exists on this model from the original plan — keep channel-analysis-specific fields grouped together. This field intentionally stores a raw dict, not a typed `AdvertisingBenchmark` — see the Interfaces note above for why. Task 6's dashboard form writes a plain dict to it via the existing `PUT /profile` endpoint; Task 7's pipeline code is the only place that validates it into a real `AdvertisingBenchmark`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_advertising_benchmark.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/domain/profile.py tests/test_channel_analysis_advertising_benchmark.py
git commit -m "feat: add an optional project-wide advertising benchmark to CreatorProfile"
```

---

### Task 6: Configuración UI to edit the advertising benchmark

**Files:**
- Modify: `src/nicheradar/dashboard.py` (`render_configuration`)
- Test: `tests/test_dashboard_navigation.py` (extend)

**Interfaces:**
- Consumes: `CreatorProfile.channel_analysis_advertising` (Task 5), existing `GET /profile` / `PUT /profile` endpoints (unchanged — the new field round-trips automatically).

- [ ] **Step 1: Write the failing test**

Append to the existing `test_dashboard_navigation_and_operation` test in `tests/test_dashboard_navigation.py`, inside the `app.radio[0].set_value("Configuración").run()` block (after its existing assertions):

```python
assert any("Benchmark publicitario" in item.value for item in app.subheader)
```

(Confirmed directly against this file's own existing pattern at line 68: `assert any(item.value == "Explicación de la evaluación" for item in app.subheader)` — `app.subheader` elements expose `.value`, not `.label` (`.label` is for input widgets like `app.text_input`). Match this exact accessor, do not use `.label` on a subheader.)

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_dashboard_navigation.py -v`
Expected: FAIL (no such section exists yet).

- [ ] **Step 3: Add the form section**

In `src/nicheradar/dashboard.py`'s `render_configuration`, after the existing `resource-profile` form's closing (find where that form's `st.form_submit_button` block ends and `PUT /profile` is called), add a new, separate form:

```python
st.subheader("Benchmark publicitario para análisis de canal")
st.caption(
    "Opcional. Si lo dejas vacío, la ganancia estimada de los análisis de canal "
    "queda 'incompleta' con la razón exacta — nunca se inventa un RPM."
)
existing_benchmark = profile.get("channel_analysis_advertising")
with st.form("channel-analysis-advertising"):
    enabled = st.checkbox(
        "Declarar un benchmark publicitario", value=existing_benchmark is not None
    )
    version = st.text_input(
        "Versión/fecha de la estimación",
        value=(existing_benchmark or {}).get("version", ""),
    )
    source = st.text_input(
        "Fuente de la estimación",
        value=(existing_benchmark or {}).get("source", ""),
    )
    rate_low = st.number_input(
        "RPM mínimo (USD por 1000 vistas)",
        min_value=0.0,
        value=float((existing_benchmark or {}).get("rate", {}).get("low", 0.0)),
    )
    rate_high = st.number_input(
        "RPM máximo (USD por 1000 vistas)",
        min_value=0.0,
        value=float((existing_benchmark or {}).get("rate", {}).get("high", 0.0)),
    )
    audience_key = st.text_input(
        "Audiencia (clave libre)",
        value=(existing_benchmark or {}).get("audience_key", "general"),
    )
    assumptions = st.text_area(
        "Supuestos declarados",
        value=(existing_benchmark or {}).get("assumptions", ""),
    )
    if st.form_submit_button("Guardar benchmark"):
        benchmark_payload = None
        if enabled:
            now_iso = datetime.now(UTC).isoformat()
            benchmark_payload = {
                "version": version or "sin-version",
                "source": source or "owner_declared",
                "origin": "manual_assumption",
                "format": "long",
                "language": "es",
                "audience_key": audience_key or "general",
                "unit": "usd_ads_per_1000_views",
                "rate": {"low": rate_low, "high": rate_high},
                "revenue_scope": "youtube_ads_only_after_revenue_share",
                "assumptions": assumptions or "Sin supuestos declarados explícitamente.",
                "observed_at": now_iso,
                "valid_until": (datetime.now(UTC) + timedelta(days=180)).isoformat(),
            }
        api_request(
            config,
            "PUT",
            "/profile",
            body={
                "profile": profile | {"channel_analysis_advertising": benchmark_payload},
                "expected_version": version,
            },
        )
        st.success("Benchmark actualizado.")
```

(This form reuses `profile`/`version` — the exact variables `render_configuration` already has in scope at the top of the function: `profile = api_request(config, "GET", "/profile")` then `version = profile.pop("version_number")` (confirmed directly in the real file, `src/nicheradar/dashboard.py:800-801`). Do not re-fetch the profile a second time, and do not rename the variable.)

(`Settings` has no `.language` field — confirmed by reading `src/nicheradar/config.py` directly. Hardcode `"es"` for the `language` key in `benchmark_payload`, matching this project's existing Spanish-only dashboard copy; drop the `hasattr` guard shown above, it was an unresolved placeholder.)

Add `from datetime import timedelta` to this file's imports if not already present (check first — `UTC`/`datetime` are almost certainly already imported given the rest of this file's existing code).

- [ ] **Step 4: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_dashboard_navigation.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/dashboard.py tests/test_dashboard_navigation.py
git commit -m "feat: edit the channel-analysis advertising benchmark from Configuración"
```

---

### Task 7: Wire real recipe + advertising benchmark into profit estimation

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py` (`compute_comparison`'s caller in pipeline, not `compute_comparison` itself)
- Modify: `src/nicheradar/workers/pipeline.py` (`_process_channel_analysis_stage`'s `metrics` branch)
- Test: `tests/test_channel_analysis_pipeline.py` (extend)

**Interfaces:**
- Consumes: `services/production.py::default_recipe(video_format, language) -> Recipe`, `default_template(video_format, language) -> DefaultRecipeTemplate` (for its `.tools`), `services/scenarios.py::simulate(Scenario(...), profile) -> ScenarioResult` (`.monthly_usd: EstimateRange | None`), `CreatorProfile.channel_analysis_advertising: dict[str, Any] | None` (Task 5, raw — this task is where it gets validated into a real `AdvertisingBenchmark`), `services/production.py::DEFAULT_VIDEOS_PER_MONTH`.
- Produces: no new function signatures — `compute_comparison`'s existing `videos_per_month`/`advertising`/`monthly_cost_usd` parameters (already present, currently always called with their defaults of `None`) are now populated with real values from the pipeline.

- [ ] **Step 1: Write the failing test**

Extend the existing `test_channel_analysis_run_completes_through_every_stage` in `tests/test_channel_analysis_pipeline.py`: seed the profile with a real `channel_analysis_advertising` benchmark instead of a bare `CreatorProfile()`:

```python
# modify the existing seed_profile(...) call in this test to pass:
from datetime import timedelta
from decimal import Decimal

from nicheradar.domain.production import EstimateRange
from nicheradar.scoring.advertising import AdvertisingBenchmark

benchmark = AdvertisingBenchmark(
    version="2026-10-02",
    source="owner_declared_estimate",
    origin="manual_assumption",
    format=VideoFormat.LONG,
    language="es",
    audience_key="general",
    unit="usd_ads_per_1000_views",
    rate=EstimateRange(low=Decimal("1.0"), high=Decimal("3.0")),
    revenue_scope="youtube_ads_only_after_revenue_share",
    assumptions="Prueba.",
    observed_at=NOW - timedelta(days=1),
    valid_until=NOW + timedelta(days=180),
)
profile_id = seed_profile(
    connection,
    CreatorProfile(paid_limits_confirmed=True, channel_analysis_advertising=benchmark),
    initial_catalog(),
)
```

Then add, after the test's existing assertions:

```python
with isolated_engine.connect() as connection:
    analysis = (
        connection.execute(select(channel_analyses).where(channel_analyses.c.run_id == run_id))
        .mappings()
        .one()
    )
profit = analysis["snapshot"]["metrics"]["profit"]
assert profit["status"] in {"estimated", "incomplete"}
```

(Keep the assertion loose — `{"estimated", "incomplete"}` — since whether it fully resolves to `"estimated"` also depends on real comparable view-rate data existing in this specific synthetic run, which this task isn't changing; the point of this test is confirming the WIRING runs without crashing and that `videos_per_month`/`advertising` are no longer unconditionally `None`. Add a second, more specific assertion: `assert profit["status"] != "incomplete" or "advertising_rate" not in profit["missing"]` — i.e., if it IS incomplete, it must NOT be incomplete specifically because of a missing advertising rate, since this test DID declare one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_pipeline.py -v`
Expected: FAIL (`profit["missing"]` still contains `"advertising_rate"` and `"videos_per_month"` since neither is wired in yet).

- [ ] **Step 3: Implement**

In `src/nicheradar/workers/pipeline.py`, import inside `_process_channel_analysis_stage` (alongside the other function-local imports already there):

```python
from collections import Counter

from pydantic import ValidationError

from nicheradar.scoring.advertising import AdvertisingBenchmark
from nicheradar.services.production import (
    DEFAULT_VIDEOS_PER_MONTH,
    default_recipe,
    default_template,
)
from nicheradar.services.scenarios import Proposal, Scenario, simulate
```

Replace the `metrics` branch's body:

```python
                elif stage == "metrics":
                    target_videos = tuple(
                        Video.model_validate(v) for v in checkpoints["target_videos"]["videos"]
                    )
                    channel = Channel.model_validate(checkpoints["resolve"]["channel"])
                    comparable_videos = {
                        channel_id: tuple(Video.model_validate(v) for v in videos)
                        for channel_id, videos in checkpoints["comparable_videos"][
                            "videos_by_channel"
                        ].items()
                    }
                    video_format = (
                        Counter(video.format for video in target_videos).most_common(1)[0][0]
                        if target_videos
                        else VideoFormat.LONG
                    )
                    advertising = None
                    if profile.channel_analysis_advertising is not None:
                        try:
                            advertising = AdvertisingBenchmark.model_validate(
                                profile.channel_analysis_advertising
                            )
                        except ValidationError:
                            # A malformed stored benchmark must degrade profit to
                            # "incomplete", never crash the whole analysis.
                            advertising = None
                    monthly_cost_usd = None
                    scenario_result = simulate(
                        Scenario(
                            name="channel-analysis-cost-estimate",
                            proposals=(
                                Proposal(
                                    channel_key="channel-analysis",
                                    opportunity_keys=(),
                                    recipe=default_recipe(video_format, profile.language),
                                    videos_per_month=DEFAULT_VIDEOS_PER_MONTH,
                                ),
                            ),
                            tools=default_template(video_format, profile.language).tools,
                            radar_monthly_usd=None,
                            reserve_usd=profile.monthly_reserve_usd,
                        ),
                        profile,
                    )
                    monthly_cost_usd = scenario_result.monthly_usd
                    comparison = compute_comparison(
                        target_videos,
                        channel,
                        comparable_videos,
                        now,
                        videos_per_month=DEFAULT_VIDEOS_PER_MONTH,
                        advertising=advertising,
                        monthly_cost_usd=monthly_cost_usd,
                    )
                    panorama = compute_panorama(comparable_videos, now)
                    confirm_channel_analysis_stage(
                        connection, job["id"], owner, now, stage, comparison | {"panorama": panorama}
                    )
```

(`VideoFormat` must already be imported at the top of `pipeline.py` — check first; it's used elsewhere in this file already per the original 17-task plan's work. `Channel`/`Video` are already imported per the earlier channel-analysis tasks.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_channel_analysis_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/workers/pipeline.py tests/test_channel_analysis_pipeline.py
git commit -m "feat: wire the default recipe and declared advertising benchmark into real profit estimation"
```

---

### Task 8: Show the panorama in the dashboard detail view

**Files:**
- Modify: `src/nicheradar/dashboard.py` (`render_channel_analysis`)
- Test: `tests/test_dashboard_navigation.py` (extend)

**Interfaces:**
- Consumes: the `snapshot["metrics"]["panorama"]` shape produced by Task 4 (`{"status": "computed", "metrics": {...CohortMetrics fields...}}` or `{"status": "incomplete", "reason": ...}`).

- [ ] **Step 1: Write the failing test**

This is a rendering-only change exercised by the SAME empty-state path Task 16 of the original plan already tests (zero saved analyses) — no new saved-analysis fixture is needed for a basic render-without-exception check. Confirm the existing test in `tests/test_dashboard_navigation.py` that visits `"Análisis de canal"` still passes after this change (it will, since the empty-state branch returns before reaching the new code) — no new test is required for this task beyond re-running the existing one. Skip to Step 3.

- [ ] **Step 2: (skipped — no new failing test for this rendering-only addition on the empty-state path)**

- [ ] **Step 3: Add the panorama section**

In `src/nicheradar/dashboard.py`'s `render_channel_analysis`, after the existing `render_structured(detail.get("snapshot") or {})` line, add, BEFORE that line (so the panorama gets its own clearly-labeled section rather than being buried inside the generic structured dump):

```python
        snapshot = detail.get("snapshot") or {}
        panorama = snapshot.get("metrics", {}).get("panorama")
        if panorama:
            st.subheader("Panorama del nicho")
            if panorama["status"] == "computed":
                metrics = panorama["metrics"]
                cols = st.columns(3)
                cols[0].metric("Videos analizados", metrics["videos"])
                cols[1].metric("Canales comparables", metrics["channels"])
                cols[2].metric(
                    "Tasa de breakout",
                    f"{metrics['breakout_rate']:.1%}" if metrics["breakout_rate"] is not None else "—",
                )
                st.caption(
                    f"Concentración (HHI): {metrics['hhi']:.3f}"
                    if metrics["hhi"] is not None
                    else "Concentración: sin datos suficientes."
                )
            else:
                st.info(f"Panorama incompleto: {panorama['reason']}")
        render_structured(snapshot)
```

(Remove the now-redundant earlier `detail.get("snapshot") or {}` line if the original code computed it inline at the `render_structured(...)` call site — check the real current code first to avoid computing it twice.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest tests/test_dashboard_navigation.py -v`
Expected: PASS (unchanged — confirms no regression)

- [ ] **Step 5: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/dashboard.py
git commit -m "feat: show the real niche panorama in the channel-analysis detail view"
```

---

### Task 9: Docs update

**Files:**
- Modify: `docs/channel-analysis.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the doc**

Read the current `docs/channel-analysis.md` in full first. Add/update sections covering, accurately against the real code built in Tasks 1-8 (not aspirational):
- The niche panorama is now real (demand/concentration/breakout via `features/metrics.py::calculate()`), computed over comparable videos excluding the target, and its `incomplete` reasons (`no_comparable_videos`, `mixed_formats_not_evaluable`).
- Profit estimation now resolves to `"estimated"` when the owner has declared a `channel_analysis_advertising` benchmark in Configuración, reusing the same default production recipe already documented; still `"incomplete"` with the exact missing-reason otherwise — never fabricated.
- Comparable discovery now queries by the target channel's own declared `keywords` (from `brandingSettings`) or a hashtag from its `description`, falling back to its title only when neither exists — not by category/subtopics (which were confirmed never populated).
- `featuredChannelsUrls` was evaluated and explicitly rejected as a comparable-discovery signal (tested live: returns the creator's own side-channels and personal friends, not competitors) — note this so a future task doesn't re-propose it without new evidence.
- The real, corrected YouTube search-quota numbers (100/day confirmed via the owner's own console; `_per_week=700`/`_per_month=3000` as the practical correction, given this project's budget system has no day-level window) and the June-2026 granular-quota-system caveat.

- [ ] **Step 2: Commit**

```bash
git add docs/channel-analysis.md
git commit -m "docs: niche panorama, real profit wiring, and corrected quota numbers"
```

---

### Task 10 (added after Task 9 found it during docs review): fix `breakout_rate` always resolving to `None`

**Why this task exists:** Task 9's implementer, while writing accurate documentation,
found and reported a real bug in Task 4's already-approved code (not a docs issue):
`compute_panorama()` hardcodes `size_stratum="unknown"` on every `Membership` it builds.
`features/metrics.py::calculate()` only computes `breakout_rate`/`breakout_classified`/
`breakout_channels`/`breakout_coverage` from members where `size_stratum == "small"` —
confirmed by reading `calculate()` directly: `small = [member for member in valid if
member.size_stratum == "small"]`, and `breakout_rate=breakout / classified if classified
else None` where `classified` is only ever incremented from iterating `small`. Since no
`Membership` ever has `size_stratum == "small"`, `breakout_rate` is **structurally always
`None`** — one of the three headline panorama numbers shown in the dashboard (Task 8) is
permanently blank, regardless of real data quality. This is a wiring bug, not a
data-availability limitation: the real signal needed (each comparable channel's
subscriber count) is already fetched and available — `discover_comparables`'s checkpoint
already stores full `Channel` objects (including `.subscribers`) under
`checkpoints["discover_comparables"]["comparables"]`, just never read by the `metrics`
stage. Fixing this completes Task 4's own originally-stated goal ("real
demand/concentration/breakout-rate metrics"), not new scope.

**Files:**
- Modify: `src/nicheradar/discovery/channel_analysis.py` (`compute_panorama`'s signature)
- Modify: `src/nicheradar/workers/pipeline.py` (`_process_channel_analysis_stage`'s
  `metrics` branch — the call site)
- Test: `tests/test_channel_analysis_discovery.py` (extend), `tests/test_channel_analysis_pipeline.py` (extend)

**Interfaces:**
- Consumes: `Channel.subscribers: int | None` (already exists), `CreatorProfile.small_channel_subscribers: int` (already exists, default `50_000` — the same real threshold `discovery/sampling.py::sample()` already uses for the catalog flow's own identical classification).
- Produces: `compute_panorama`'s signature changes from `compute_panorama(comparable_videos, now)` to `compute_panorama(comparable_videos, comparable_channels, small_channel_subscribers, now)` — all three new/changed parameters required, no silent defaulting that could mask the same bug again.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_channel_analysis_discovery.py
def test_compute_panorama_classifies_breakout_by_real_subscriber_counts() -> None:
    small_channel = Channel(id="UC_a", title="Small", subscribers=1000)
    large_channel = Channel(id="UC_b", title="Large", subscribers=5_000_000)
    comparable_videos = {
        "UC_a": tuple(
            Video(
                id=f"a{i}",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=100,
                format=VideoFormat.LONG,
            )
            for i in range(5)
        )
        + (
            Video(
                id="a-outlier",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=10_000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, (small_channel, large_channel), 50_000, NOW)
    assert panorama["status"] == "computed"
    assert panorama["metrics"]["breakout_rate"] is not None


def test_compute_panorama_unknown_stratum_when_subscribers_not_resolved() -> None:
    unresolved = Channel(id="UC_a", title="Unresolved")  # subscribers defaults to None
    comparable_videos = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, (unresolved,), 50_000, NOW)
    assert panorama["status"] == "computed"
    assert (
        panorama["metrics"]["breakout_rate"] is None
    )  # no "small" members at all — honest, not fabricated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: FAIL (`TypeError: compute_panorama() missing 2 required positional arguments`).

- [ ] **Step 3: Implement**

Replace `compute_panorama`'s current body in `src/nicheradar/discovery/channel_analysis.py`:

```python
def compute_panorama(
    comparable_videos: dict[str, tuple[Video, ...]],
    comparable_channels: tuple[Channel, ...],
    small_channel_subscribers: int,
    now: datetime,
) -> dict[str, Any]:
    subscribers_by_channel = {channel.id: channel.subscribers for channel in comparable_channels}
    all_videos = [video for videos in comparable_videos.values() for video in videos]
    if not all_videos:
        return {"status": "incomplete", "reason": "no_comparable_videos"}
    formats = {video.format for video in all_videos}
    if len(formats) > 1:
        return {"status": "incomplete", "reason": "mixed_formats_not_evaluable"}

    def stratum(channel_id: str) -> str:
        subscribers = subscribers_by_channel.get(channel_id)
        if subscribers is None:
            return "unknown"
        return "small" if subscribers <= small_channel_subscribers else "large"

    members = tuple(
        Membership(
            video=video,
            included=True,
            reason="channel_analysis_comparable",
            size_stratum=stratum(video.channel_id),
            age_band=age_band((now - video.published_at).total_seconds() / 86400)
            if video.published_at
            else "unknown",
            selection_method="channel_analysis",
        )
        for video in all_videos
    )
    metrics = calculate(members, now)
    return {"status": "computed", "metrics": metrics.model_dump(mode="json")}
```

(Note: `stratum()` keys off `video.channel_id`, not the `comparable_videos` dict's own key — confirm these are identical in practice, since `comparable_videos` is built keyed by each comparable's `channel.id` and every `Video.channel_id` within that channel's tuple should match it; if you find a real mismatch while testing, use `comparable_videos`'s own dict key to drive the lookup instead of `video.channel_id`, and note why in your report.)

- [ ] **Step 4: Update the call site**

In `src/nicheradar/workers/pipeline.py`'s `_process_channel_analysis_stage`, in the `elif stage == "metrics":` branch, add a line parsing the real comparable `Channel` objects from the checkpoint (mirroring how `comparable_videos` itself is already parsed there) and pass them into the updated call:

```python
comparable_channels = tuple(
    Channel.model_validate(c) for c in checkpoints["discover_comparables"]["comparables"]
)
```

Change:

```python
                    panorama = compute_panorama(comparable_videos, now)
```

to:

```python
                    panorama = compute_panorama(
                        comparable_videos, comparable_channels, profile.small_channel_subscribers, now
                    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_channel_analysis_discovery.py -v`
Expected: PASS

- [ ] **Step 6: Extend the pipeline test**

In `tests/test_channel_analysis_pipeline.py`'s existing `test_channel_analysis_run_completes_through_every_stage`, after the existing panorama assertion (`assert panorama["status"] in {"computed", "incomplete"}` or similar from Task 4), add a check that the test doesn't regress: if `panorama["status"] == "computed"`, assert `"breakout_rate" in panorama["metrics"]` (presence, not a specific value — the synthetic fixture's exact subscriber counts aren't controlled by this test, so don't assert it's non-`None`, just that the wiring didn't crash and the key exists).

- [ ] **Step 7: Run full suite, lint, format, type-check, commit**

```bash
NR_TEST_POSTGRES_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin uv run pytest -q
uv run ruff check . && uv run ruff format . && uv run mypy
git add src/nicheradar/discovery/channel_analysis.py src/nicheradar/workers/pipeline.py tests/test_channel_analysis_discovery.py tests/test_channel_analysis_pipeline.py
git commit -m "fix: classify panorama breakout by each comparable's real subscriber count"
```

- [ ] **Step 8: Update docs**

In `docs/channel-analysis.md`, remove or correct the "Limitación conocida" note Task 9 added about `breakout_rate` always being `None` (it's now fixed) — replace it with a short note that breakout classification uses each comparable channel's real subscriber count against `small_channel_subscribers` (default 50,000), the same threshold the catalog flow already uses.

```bash
git add docs/channel-analysis.md
git commit -m "docs: breakout rate now classified by real subscriber counts"
```

---

## Self-Review

**Spec coverage:** Goal 1 "panorama del nicho" (Task 4), step 9 "ganancia mensual estimada si hay receta y RPM declarados" (Tasks 5-7), comparable discovery quality (Tasks 1-2), real quota numbers (Task 3). The spec's explicit exclusions (Social Blade/RSS/Google Trends/`featuredChannelsUrls`/scraping) remain excluded — no task in this plan touches any of them; Task 9 documents the `featuredChannelsUrls` rejection explicitly so it isn't re-litigated later without new evidence.

**Placeholder scan:** No bare TODO/TBD. Task 4 Step 6 and Task 8 Step 1 are deliberately pointer-style ("extend this existing test, here's exactly what to add") rather than full fresh test functions, because the target is an EXISTING large test function from the original plan that should not be duplicated — each still specifies the exact assertion code to add, not a vague "write tests for this."

**Type consistency:** `ComparableDiscovery`, `compute_comparison`'s signature, and `Channel`'s field set are used identically across all tasks that touch them. `compute_panorama`'s return shape (`{"status": "computed"/"incomplete", ...}`) is used identically in Task 4 (where it's produced) and Task 8 (where it's rendered).

**Review Focus coverage:** all five items above have an owning task and test (empty/malformed keywords → Task 1 Step 1's second test and Task 2's fallback test; unset advertising benchmark → Task 7's loose status assertion plus the project's pre-existing `estimate_profit` incomplete-state tests; mixed video formats in the panorama → Task 4's dedicated test; the Configuración form's clear-to-None path → implicitly covered by the checkbox-gated `benchmark_payload = None` branch in Task 6, though Task 6 does not add a dedicated automated test for this specific clearing path since `AppTest`'s checkbox/form interaction for this exact case would meaningfully duplicate the existing form-submission test pattern already in the file — flagging this as a deliberately accepted minor gap rather than silently skipping it).

---

**Execution:** continuing on the existing `worktree-channel-competitive-analysis` branch. Given the explicit per-task review discipline already used successfully for the original 17-task plan on this same branch (caught multiple real defects before they compounded), and that several tasks here (5, 6, 7) touch shared/cross-cutting code (`CreatorProfile`, the pipeline's `metrics` stage) where a fresh reviewer's gate per task has already proven valuable on this branch, I recommend **Subagent-driven** execution again, consistent with how the rest of this feature was built.
