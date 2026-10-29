"""El informe de RPM aplica la regla de Shorts al leer y no inventa nada sin datos."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.market_intel.evidence_stage import save_evidence
from nicheradar.repositories.schema import listing_channel_snapshots as snapshots
from nicheradar.repositories.schema import listing_classifications as classifications
from scripts.rpm_sample_report import build_report
from tests.test_market_intel_evidence_stage import NOW, seed

LONG = [{"views": 1000, "duration_seconds": 900}]
MIXED = [{"views": 500, "duration_seconds": 900}, {"views": 500, "duration_seconds": 40}]


def add(
    connection: sa.Connection,
    listing: UUID,
    *,
    scope: str,
    rpm: str,
    niche: str | None,
    videos: list[dict[str, int]] | None,
) -> None:
    derived: dict[str, Any] = {
        "rpm_sample_eligible": True,
        "rpm_usd": rpm,
        "evidence_grade": "A",
        "income_level": "L1",
        "observed_monthly_income_usd": "100.00",
        "primary": {"scope": scope},
    }
    save_evidence(
        connection, listing, state="complete", now=NOW, total=1, hashes=["h"], derived=derived
    )
    if niche:
        connection.execute(
            classifications.insert().values(
                listing_id=listing,
                prompt_version="x",
                niche_label=niche,
                format="long",
                traits={},
                source="llm",
                retain_until=NOW + timedelta(days=30),
                created_at=NOW,
            )
        )
    if videos is not None:
        connection.execute(
            snapshots.insert().values(
                listing_id=listing,
                youtube_channel_id="UC1",
                status="ok",
                fetched_at=NOW,
                recent_videos=videos,
                retain_until=NOW + timedelta(days=30),
            )
        )


@pytest.mark.postgres
def test_the_report_keeps_long_form_and_drops_shorts_heavy_and_unknown(
    isolated_engine: Engine,
) -> None:
    history = "history_documentaries"
    with isolated_engine.begin() as connection:
        add(connection, seed(connection, "a"), scope="all", rpm="4.00", niche=history, videos=LONG)
        add(connection, seed(connection, "b"), scope="all", rpm="0.05", niche=history, videos=MIXED)
        add(connection, seed(connection, "c"), scope="long", rpm="6.00", niche=history, videos=None)
        add(connection, seed(connection, "d"), scope="all", rpm="9.00", niche=history, videos=None)
        add(connection, seed(connection, "e"), scope="long", rpm="2.00", niche=None, videos=None)
    lines = build_report(isolated_engine)
    assert lines[0].startswith("elegibles segun la derivacion guardada: 5 ")
    assert "'ok': 3" in lines[0] and "'shorts_heavy': 1" in lines[0]
    assert "'shorts_unknown': 1" in lines[0]
    assert any(line.startswith(f"{history} | 2 | 5.00 | ") for line in lines)
    assert any(line.startswith("(sin clasificar) | 1 | 2.00 | ") for line in lines)
    assert not any("0.05" in line for line in lines[1:])  # the Shorts-heavy RPM never enters


@pytest.mark.postgres
def test_the_report_runs_on_an_empty_database(isolated_engine: Engine) -> None:
    lines = build_report(isolated_engine)
    assert lines[0].startswith("elegibles segun la derivacion guardada: 0")
