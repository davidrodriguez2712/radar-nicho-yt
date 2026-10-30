"""El recálculo no llama al modelo, es idempotente, no escribe en simulación y limpia lo erróneo."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, select

from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.market_intel.evidence.wire import EvidenceResult
from nicheradar.market_intel.evidence_stage import save_evidence
from nicheradar.repositories.schema import listing_evidence as le
from scripts.rederive_evidence import rederive
from tests.test_market_intel_evidence import base
from tests.test_market_intel_evidence_stage import NOW, seed


def store(engine: Engine, external_id: str, doc: dict[str, Any]) -> None:
    evidence = ModelEvidence.model_validate(doc)  # what an old run saved, whatever the parser said
    derived = build_derived(evidence, fx={}, extracted_at=NOW, declared_income=Decimal(500))
    derived["call"] = {"output_tokens": 123}
    result = EvidenceResult(evidence=evidence, actual_usd=Decimal("0.003"), reason="ok")
    with engine.begin() as connection:
        listing = seed(connection, external_id)
        save_evidence(
            connection,
            listing,
            state="complete",
            now=NOW,
            total=1,
            hashes=["h"],
            result=result,
            derived=derived,
        )


def rows(engine: Engine) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(select(le)).mappings())


def misread() -> dict[str, Any]:
    doc = deepcopy(base())
    doc["earnings"][0]["raw_text"] = "US$0.001"  # the old parser read this as 1
    doc["earnings"][0]["amount"]["value"] = "1.00"
    return doc


@pytest.mark.postgres
def test_a_dry_run_reports_the_change_and_writes_nothing(isolated_engine: Engine) -> None:
    store(isolated_engine, "a", misread())
    before = rows(isolated_engine)[0]["derived"]
    counts = rederive(isolated_engine, apply=False)
    assert counts["changed"] == 1 and counts["entries_dropped"] == 1
    assert rows(isolated_engine)[0]["derived"] == before


@pytest.mark.postgres
def test_applying_drops_the_misread_value_and_rederives(isolated_engine: Engine) -> None:
    store(isolated_engine, "a", misread())
    assert rows(isolated_engine)[0]["derived"]["primary"] is not None
    rederive(isolated_engine, apply=True)
    [row] = rows(isolated_engine)
    assert row["derived"]["primary"] is None and row["rpm_usd"] is None
    assert row["model_evidence"]["earnings"] == []
    assert row["derived"]["call"] == {"output_tokens": 123}  # the call record survives
    assert any(u["reason"] == "unreadable" for u in row["model_evidence"]["unresolved"])


@pytest.mark.postgres
def test_it_is_idempotent_and_leaves_clean_rows_alone(isolated_engine: Engine) -> None:
    store(isolated_engine, "a", misread())
    store(isolated_engine, "b", base())
    rederive(isolated_engine, apply=True)
    again = rederive(isolated_engine, apply=True)
    assert again["changed"] == 0 and again["rows"] == 2
