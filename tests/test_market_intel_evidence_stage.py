# tests/test_market_intel_evidence_stage.py
"""Etapa `evidence`: petición de visión, respuesta, derivados y flujo con base de datos."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.domain.profile import initial_catalog
from nicheradar.integrations.contracts import Operation
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.integrations.policies import Usage
from nicheradar.market_intel import evidence_stage
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import ListingCard, ListingDetail, SourceError
from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.market_intel.evidence.wire import (
    MAX_OUTPUT_TOKENS,
    evidence_schema,
    parse_response,
    request_body,
)
from nicheradar.market_intel.evidence_stage import (
    POLICY_DATA_TYPE,
    Downloaded,
    download_image,
    pending_evidence,
    stage_evidence,
)
from nicheradar.market_intel.ingest import apply_detail, upsert_cards
from nicheradar.market_intel.sources.dealbaron import parse_detail
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import listing_evidence as le
from tests.test_channel_analysis_advertising_match import llm_configuration, settings_llm_enabled
from tests.test_market_intel_classify import funded_profile, payload, seed_run
from tests.test_market_intel_evidence import base

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
TARIFF = llm_configuration().tariff
FIXTURES = Path(__file__).parent / "fixtures" / "market_intel"


# --- adjuntos de la ficha -----------------------------------------------------------------------


def test_parse_detail_collects_unique_attachments_in_page_order() -> None:
    html = (FIXTURES / "real_detail_snippet.html").read_text()
    first = "https://media.dealbaron.com/listing-attachments/listing-1/aaa.png"
    second = "https://media.dealbaron.com/listing-attachments/listing-1/bbb.jpg"
    html = html.replace(
        "</body>",
        f'<img src="{first}"><img src="{second}"><a href="{first}">again</a>'
        '<img src="https://evil.example/listing-attachments/x.png"></body>',
    )
    detail = parse_detail(html, "569798")
    assert detail.attachment_urls == (first, second)
    assert (
        parse_detail((FIXTURES / "real_detail_snippet.html").read_text(), "1").attachment_urls == ()
    )


# --- esquema, petición y respuesta --------------------------------------------------------------


def walk(node: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        found.append((path, node))
        for key, value in node.items():
            found += walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += walk(value, f"{path}[{index}]")
    return found


def test_the_schema_satisfies_openai_strict_mode_rules() -> None:
    schema = evidence_schema()
    assert schema["type"] == "object"
    banned = {
        "default",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "title",
        "description",
    }
    for path, node in walk(schema):
        if node.get("type") == "object" and "properties" in node:
            assert node["required"] == list(node["properties"]), path
            assert node["additionalProperties"] is False, path
        assert not banned & set(node), path
        branches = node.get("anyOf")
        if isinstance(branches, list):
            types = {b.get("type") for b in branches if isinstance(b, dict)}
            assert not {"number", "string"} <= types, path  # Decimal collapsed to number
    assert set(schema["required"]) == set(ModelEvidence.model_fields)
    assert len(json.dumps(schema)) < 60_000


def test_the_model_cannot_be_asked_for_code_owned_flags() -> None:
    codes = evidence_schema()["$defs"]["ModelRiskFlag"]["properties"]["code"]["enum"]
    assert "stale_capture" not in codes and "copyright_risk" in codes


def test_the_request_carries_images_as_data_urls_and_stores_nothing() -> None:
    body = request_body(TARIFF, {"image_count": 2}, [(PNG, "image/png"), (b"jpg", "image/jpeg")])
    content = body["input"][0]["content"]
    assert content[0]["type"] == "input_text" and json.loads(content[0]["text"]) == {
        "image_count": 2
    }
    assert [part["type"] for part in content[1:]] == ["input_image", "input_image"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert content[2]["image_url"].startswith("data:image/jpeg;base64,")
    assert body["store"] is False and body["tools"] == [] and body["background"] is False
    assert body["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert body["text"]["format"]["strict"] is True
    assert "untrusted" in body["instructions"]


def response(text: str, *, status: str = "completed", output_tokens: int = 900) -> dict[str, Any]:
    done = payload({}, status=status)
    done["usage"]["output_tokens"] = output_tokens
    done["output"][0]["content"][0]["text"] = text
    return done


def test_a_valid_response_becomes_evidence_and_a_cost() -> None:
    result = parse_response(response(json.dumps(base())), TARIFF)
    assert result.reason == "response_received" and result.evidence is not None
    assert result.actual_usd is not None and result.actual_usd > 0
    assert result.evidence.earnings[0].amount.value == Decimal("295.18")


def test_a_number_the_text_does_not_reproduce_is_dropped_not_trusted() -> None:
    doc = base()
    doc["views"][0]["raw_text"] = "97.6K"
    result = parse_response(response(json.dumps(doc)), TARIFF)
    assert result.evidence is not None and result.evidence.views == ()
    assert result.evidence.unresolved[-1].reason == "unreadable"


@pytest.mark.parametrize(
    ("text", "status", "reason"),
    [
        (json.dumps(base()), "incomplete", "incomplete_response"),
        ("not json", "completed", "invalid_response"),
        (json.dumps({**base(), "derived": {}}), "completed", "invalid_response"),
        (json.dumps({**base(), "surprise": 1}), "completed", "invalid_response"),
    ],
)
def test_unusable_responses_carry_a_stable_reason(text: str, status: str, reason: str) -> None:
    result = parse_response(response(text, status=status), TARIFF)
    assert result.evidence is None and result.reason == reason


def test_a_failed_call_carries_codes_and_paths_but_never_content() -> None:
    secret = "SECRETO-DEL-VENDEDOR"
    incomplete = response(json.dumps(base()), status="incomplete")
    incomplete["incomplete_details"] = {"reason": "max_output_tokens"}
    result = parse_response(incomplete, TARIFF)
    assert result.diagnostic is not None
    assert result.diagnostic["incomplete_reason"] == "max_output_tokens"
    invalid = parse_response(response(json.dumps({**base(), "surprise": secret})), TARIFF)
    assert invalid.diagnostic is not None and invalid.diagnostic["error_count"] >= 1
    assert invalid.diagnostic["errors"][0]["loc"] == "surprise"
    assert secret not in json.dumps(invalid.diagnostic)


def test_billing_is_verified_against_the_pinned_model_and_output_allowance() -> None:
    good = response(json.dumps(base()), output_tokens=MAX_OUTPUT_TOKENS)
    assert parse_response(good, TARIFF).actual_usd is not None
    too_long = response(json.dumps(base()), output_tokens=MAX_OUTPUT_TOKENS + 1)
    assert parse_response(too_long, TARIFF).actual_usd is None
    other = response(json.dumps(base()))
    other["model"] = "someone-else"
    assert parse_response(other, TARIFF).actual_usd is None


# --- derivados ----------------------------------------------------------------------------------


def test_the_derived_block_summarizes_the_primary_set() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(base()),
        fx={},
        extracted_at=NOW,
        declared_income=Decimal(375),
    )
    assert derived["evidence_grade"] == "A" and derived["income_level"] == "L1"
    assert derived["rpm_usd"] == "4.2350" and derived["rpm_sample_eligible"] is True
    assert derived["observed_monthly_income_usd"] == "320.88"
    assert derived["primary"]["views"] == "69700" and derived["primary"]["days"] == 28
    assert derived["declared_vs_observed_ratio"] == pytest.approx(0.855, abs=0.01)
    assert derived["scoring_eligible_income"] is True


def test_without_revenue_the_declared_income_is_not_used() -> None:
    doc = base(earnings=[], views=[])
    derived = build_derived(
        ModelEvidence.model_validate(doc), fx={}, extracted_at=NOW, declared_income=Decimal(500)
    )
    assert derived["income_level"] == "L4" and derived["observed_monthly_income_usd"] is None
    assert derived["evidence_grade"] == "E" and derived["scoring_eligible_income"] is False


def test_a_studio_rpm_far_from_the_computed_one_is_flagged() -> None:
    doc = base(
        rates=[
            {
                "image_index": 0,
                "metric": "rpm",
                "scope": "all",
                "period": doc_period(),
                "value": 8.0,
                "raw_text": "$8.00",
                "legibility": "clear",
            }
        ]
    )
    derived = build_derived(
        ModelEvidence.model_validate(doc), fx={}, extracted_at=NOW, declared_income=None
    )
    assert derived["rpm_check"] == pytest.approx(-0.47, abs=0.01)
    assert "edited_or_inconsistent_numbers" in {f["code"] for f in derived["risk_flags"]}


def doc_period() -> dict[str, Any]:
    return base()["earnings"][0]["period"]  # type: ignore[no-any-return]


# --- descarga de adjuntos -----------------------------------------------------------------------

URL = "https://media.dealbaron.com/listing-attachments/listing-1/a.png"


def http_returning(status: int = 200, mime: str = "image/png", body: bytes = PNG) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"content-type": mime})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_only_the_marketplace_media_host_over_https_is_downloaded() -> None:
    client = http_returning()
    found = download_image(client, URL)
    assert found is not None and found.mime == "image/png" and len(found.sha256) == 64
    for url in (
        "http://media.dealbaron.com/listing-attachments/a.png",
        "https://evil.example/listing-attachments/a.png",
        "https://media.dealbaron.com.evil.example/a.png",
    ):
        assert download_image(client, url) is None


def test_unsuitable_responses_are_not_images() -> None:
    assert download_image(http_returning(404), URL) is None
    assert download_image(http_returning(mime="text/html"), URL) is None
    huge = b"x" * (evidence_stage.MAX_IMAGE_BYTES + 1)
    assert download_image(http_returning(body=huge), URL) is None


# --- la etapa -----------------------------------------------------------------------------------


class FakeSource:
    name = "dealbaron"

    def __init__(self, attachments: dict[str, tuple[str, ...] | SourceError | None]) -> None:
        self.attachments = attachments
        self.fetched: list[str] = []

    def fetch_detail(self, external_id: str) -> ListingDetail | None:
        self.fetched.append(external_id)
        value = self.attachments.get(external_id, ())
        if isinstance(value, SourceError):
            raise value
        if value is None:
            return None
        return ListingDetail(external_id=external_id, title="t", attachment_urls=value)

    def crawl(self) -> Any:  # pragma: no cover - unused by this stage
        raise AssertionError


def seed(connection: Connection, external_id: str, *, income: int | None = 500) -> UUID:
    card = ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title=f"Channel {external_id}",
        category="Games",
        subscribers=10_000,
        income_monthly_usd=Decimal(income) if income is not None else None,
    )
    upsert_cards(connection, "dealbaron", [card], NOW, NOW.date())
    apply_detail(
        connection,
        "dealbaron",
        ListingDetail(external_id=external_id, title="t"),
        NOW,
        NOW.date(),
    )
    found: UUID = connection.execute(
        sa.text("SELECT id FROM marketplace_listings WHERE external_id = :e"), {"e": external_id}
    ).scalar_one()
    return found


def seed_evidence_policies(connection: Connection) -> None:
    for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
        insert_record(
            connection,
            "provider_policies",
            {
                "provider": "openai",
                "operation": Operation.LISTING_EVIDENCE.value,
                "data_type": POLICY_DATA_TYPE,
                "usage": usage.value,
                "version": "fixture-v1",
                "status": "enabled",
                "evidence_source": "synthetic test policy; not permission for real requests",
                "effective_at": NOW,
                "retention_seconds": 3600,
            },
        )


def make_run(engine: Engine, *, policies: bool = True) -> dict[str, Any]:
    with engine.begin() as connection:
        profile_id = seed_profile(connection, funded_profile(), initial_catalog())
        run = seed_run(connection, profile_id)
        if policies:
            seed_evidence_policies(connection)
    return run


def context(engine: Engine, run: dict[str, Any], source: FakeSource, **config: Any) -> RunContext:
    current = llm_configuration().model_copy(
        update={
            "tariff": TARIFF.model_copy(
                update={
                    "verified_at": NOW - timedelta(days=1),
                    "valid_until": NOW + timedelta(days=1),
                }
            )
        }
    )
    settings = settings_llm_enabled().model_copy(
        update={"market_intel_evidence_cap_per_run": 10, "llm_configuration": current, **config}
    )
    return RunContext(
        engine=engine,
        config=settings,
        source=source,
        run_id=uuid4(),
        analysis_run=run,
        owner="worker",
        started_at=NOW,
        clock=lambda: NOW,
    )


def selector_answering(text: str | None = None, calls: list[int] | None = None) -> OpenAISelector:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(len(request.content))
        if text is None:
            raise httpx.ConnectError("no route")
        return httpx.Response(200, json=response(text))

    return OpenAISelector(
        SecretStr("secret-for-mocked-http-only"), transport=httpx.MockTransport(handler)
    )


def run_stage(
    ctx: RunContext, selector: OpenAISelector, client: httpx.Client | None = None
) -> dict[str, Any]:
    return stage_evidence(
        ctx, http=client or http_returning(), selector=selector, sleep=lambda _: None
    )


def rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(r)
            for r in connection.execute(sa.select(le).order_by(le.c.extracted_at)).mappings()
        ]


@pytest.mark.postgres
def test_the_stage_is_off_unless_live_with_the_llm_and_a_cap(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    source = FakeSource({})
    synthetic = {**run, "mode": "synthetic"}
    assert stage_evidence(context(isolated_engine, synthetic, source)) == {
        "skipped": "synthetic_mode"
    }
    off = context(isolated_engine, run, source, market_intel_evidence_cap_per_run=0)
    assert stage_evidence(off) == {"skipped": "evidence_not_enabled"}
    no_llm = context(isolated_engine, run, source, llm_enabled=False)
    assert stage_evidence(no_llm) == {"skipped": "evidence_not_enabled"}
    assert source.fetched == []


@pytest.mark.postgres
def test_pending_takes_active_listings_without_evidence_income_first(db: Connection) -> None:
    rich = seed(db, "rich", income=900)
    poor = seed(db, "poor", income=100)
    none = seed(db, "none", income=None)
    done = seed(db, "done", income=500)
    evidence_stage.save_evidence(db, done, state="no_images", now=NOW, total=0, hashes=[])
    assert [i["id"] for i in pending_evidence(db, "dealbaron", 10, NOW)] == [rich, poor, none]
    assert len(pending_evidence(db, "dealbaron", 2, NOW)) == 2


@pytest.mark.postgres
def test_the_full_flow_saves_validated_derived_evidence(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        listing = seed(connection, "one", income=375)
    source = FakeSource({"one": (URL, URL.replace("a.png", "b.png"))})
    sizes: list[int] = []
    ctx = context(isolated_engine, run, source)
    result = run_stage(ctx, selector_answering(json.dumps(base()), sizes))
    assert result["complete"] == 1 and result["pending"] == 1 and "stopped_reason" not in result
    assert len(sizes) == 1 and sizes[0] > 2 * len(PNG)  # both images travelled in one call
    [row] = rows(isolated_engine)
    assert row["listing_id"] == listing and row["extraction_state"] == "complete"
    assert row["evidence_grade"] == "A" and row["income_level"] == "L1"
    assert row["rpm_usd"] == Decimal("4.2350") and row["rpm_sample_eligible"] is True
    assert row["image_count_total"] == 2 and row["image_count_processed"] == 1  # same bytes twice
    assert len(row["image_hashes"][0]) == 64 and row["cost_usd"] > 0
    assert row["model_evidence"]["earnings"][0]["raw_text"] == "$295.18"
    assert "sha256" not in json.dumps(row["model_evidence"])
    # Nothing left to do for this prompt version.
    assert run_stage(ctx, selector_answering(json.dumps(base()))) == {"pending": 0}


@pytest.mark.postgres
def test_a_listing_without_attachments_is_recorded_and_not_asked_again(
    isolated_engine: Engine,
) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "bare")
        seed(connection, "gone", income=100)
    source = FakeSource({"bare": (), "gone": None})
    result = run_stage(
        context(isolated_engine, run, source), selector_answering(json.dumps(base()))
    )
    assert (result["no_images"], result["failed"]) == (1, 1)
    states = {r["extraction_state"]: r["failure_reason"] for r in rows(isolated_engine)}
    assert states == {"no_images": None, "failed": "listing_gone"}


@pytest.mark.postgres
def test_a_failed_download_is_recorded_without_calling_the_model(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    calls: list[int] = []
    result = run_stage(
        context(isolated_engine, run, FakeSource({"one": (URL,)})),
        selector_answering(json.dumps(base()), calls),
        http_returning(404),
    )
    assert result["failed"] == 1 and calls == []
    assert rows(isolated_engine)[0]["failure_reason"] == "download_failed"


@pytest.mark.postgres
def test_an_invalid_answer_is_saved_as_failed_with_its_cost_and_not_retried(
    isolated_engine: Engine,
) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    ctx = context(isolated_engine, run, FakeSource({"one": (URL,)}))
    result = run_stage(ctx, selector_answering("not json"))
    assert result["failed"] == 1
    [row] = rows(isolated_engine)
    assert row["extraction_state"] == "failed" and row["failure_reason"] == "invalid_response"
    assert row["model_evidence"] is None and row["cost_usd"] > 0  # the call was billed
    assert run_stage(ctx, selector_answering("not json")) == {"pending": 0}


@pytest.mark.postgres
def test_three_consecutive_model_failures_stop_the_stage_and_save_nothing(
    isolated_engine: Engine,
) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        for index in range(5):
            seed(connection, f"l{index}", income=500 - index)
    source = FakeSource({f"l{i}": (URL,) for i in range(5)})
    result = run_stage(context(isolated_engine, run, source), selector_answering(None))
    assert result["stopped_reason"] == "llm_failed" and result["partial"] is True
    assert result["skipped"] == 3 and len(source.fetched) == 3
    assert rows(isolated_engine) == []  # retried on the next run


@pytest.mark.postgres
def test_a_missing_policy_stops_the_stage_with_its_reason(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine, policies=False)
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    result = run_stage(
        context(isolated_engine, run, FakeSource({"one": (URL,)})),
        selector_answering(json.dumps(base())),
    )
    assert result["stopped_reason"] == "policy_not_enabled" and rows(isolated_engine) == []


@pytest.mark.postgres
def test_a_blocked_source_stops_the_stage(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    result = run_stage(
        context(isolated_engine, run, FakeSource({"one": SourceError("blocked")})),
        selector_answering(json.dumps(base())),
    )
    assert result["stopped_reason"] == "blocked" and rows(isolated_engine) == []


@pytest.mark.postgres
def test_a_successful_call_stores_its_real_token_usage(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    run_stage(
        context(isolated_engine, run, FakeSource({"one": (URL,)})),
        selector_answering(json.dumps(base())),
    )
    [row] = rows(isolated_engine)
    call = row["derived"]["call"]
    assert call["status"] == "completed" and call["output_tokens"] > 0
    assert call["input_tokens"] > 0


@pytest.mark.postgres
def test_one_unavailable_detail_page_skips_that_listing_and_the_rest_continue(
    isolated_engine: Engine,
) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        seed(connection, "bad", income=900)
        seed(connection, "good", income=100)
    source = FakeSource({"bad": SourceError("source_unavailable"), "good": (URL,)})
    result = run_stage(
        context(isolated_engine, run, source), selector_answering(json.dumps(base()))
    )
    assert result["complete"] == 1 and result["skipped"] == 1
    assert "stopped_reason" not in result


@pytest.mark.postgres
def test_three_unavailable_detail_pages_in_a_row_stop_the_stage(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        for index in range(5):
            seed(connection, f"l{index}", income=500 - index)
    source = FakeSource({f"l{i}": SourceError("source_unavailable") for i in range(5)})
    result = run_stage(context(isolated_engine, run, source), selector_answering(None))
    assert result["stopped_reason"] == "source_unavailable" and result["skipped"] == 3


@pytest.mark.postgres
def test_a_request_blocked_for_one_listing_does_not_freeze_the_rest(
    isolated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = make_run(isolated_engine)
    with isolated_engine.begin() as connection:
        first = seed(connection, "first", income=900)
        second = seed(connection, "second", income=100)
    real = evidence_stage.extract

    async def flaky(
        engine: Engine,
        run_: dict[str, Any],
        config: Settings,
        listing: dict[str, Any],
        images: list[Downloaded],
        now: datetime,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if listing["id"] == first:
            return {"result": None, "reason": "request_in_progress"}
        return await real(engine, run_, config, listing, images, now, **kwargs)

    monkeypatch.setattr(evidence_stage, "extract", flaky)
    source = FakeSource({"first": (URL,), "second": (URL,)})
    result = run_stage(
        context(isolated_engine, run, source), selector_answering(json.dumps(base()))
    )
    assert result["skipped"] == 1 and result["complete"] == 1 and "stopped_reason" not in result
    assert [r["listing_id"] for r in rows(isolated_engine)] == [second]
