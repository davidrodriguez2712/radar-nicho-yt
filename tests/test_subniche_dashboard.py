# tests/test_subniche_dashboard.py
from typing import Any

from streamlit.testing.v1 import AppTest

from nicheradar.subniche_dashboard import channel_rows, subniche_rows

HOSTILE = "**negrita** <script>alert(1)</script> [x](https://evil.test)"


def item(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "slug": "history_revenge",
        "label": "History Revenge Stories",
        "family": "history",
        "parent_niche_slug": "historical_stories",
        "status": "active",
        "finalist": True,
        "language": "en",
        "format": "long",
        "queries": ["history revenge"],
        "measurement": {
            "measured_at": "2026-10-31T12:00:00+00:00",
            "included": 22,
            "stable_channels": 9,
            "volatile_channels": 13,
            "traction_channels": 5,
            "large_channels": 11,
            "excluded": {"language": 8},
            "income_low": "884.67",
            "income_high": "2022.10",
            "rpm_source": "inherited:historical_stories",
            "signal": "estimable",
        },
        "research": {"id": "r1", "status": "listo", "language": "en", "created_at": "x"},
    }
    return base | over


def test_rows_show_income_range_counts_and_research_status() -> None:
    row = subniche_rows([item()])[0]
    assert row["Subnicho"] == "History Revenge Stories" and row["Finalista"] == "sí"
    assert row["Ingreso por canal (US$)"] == "884.67 – 2022.10"
    assert row["Tracción"] == 5 and row["Estables"] == 9 and row["Grandes"] == 11
    assert row["Investigación"] == "listo"


def test_rows_of_an_unmeasured_hypothesis_have_blanks_and_no_research() -> None:
    row = subniche_rows([item(measurement=None, research=None, finalist=False)])[0]
    assert row["Ingreso por canal (US$)"] == "" and row["Tracción"] is None
    assert row["Finalista"] == "no" and row["Investigación"] == "sin investigar"


def test_channel_rows_keep_hostile_text_as_plain_values() -> None:
    rows = channel_rows(
        [
            {
                "channel_id": "UC1",
                "title": HOSTILE,
                "subscribers": 1200,
                "monthly_long_views": 5000,
                "income_low": "10.00",
                "income_high": "20.00",
                "traction": True,
                "flags": ["young"],
            }
        ]
    )
    assert rows[0]["Canal"] == HOSTILE and rows[0]["Tracción"] == "sí"


def _render(listing, card):  # type: ignore[no-untyped-def]  # AppTest runs it as a standalone script
    from typing import Any

    import streamlit as st

    from nicheradar.config import Settings
    from nicheradar.subniche_dashboard import render_subniches

    def api(config: Settings, method: str, path: str, body: Any = None) -> dict[str, Any]:
        if method == "POST":
            st.session_state["posted"] = (path, body)
        result: dict[str, Any] = listing if path.startswith("/subniches?") else card
        return result

    render_subniches(Settings(), api)


def test_the_page_renders_the_list_and_the_card_without_exceptions() -> None:
    card = {
        "hypothesis": item() | {"measurement": None, "research": None},
        "measurement": item()["measurement"],
        "channels": [
            {
                "channel_id": "UC1",
                "title": HOSTILE,
                "subscribers": 1200,
                "monthly_long_views": 5000,
                "income_low": "10.00",
                "income_high": "20.00",
                "traction": True,
                "flags": [],
            }
        ],
        "channels_available": True,
        "research": None,
    }
    app = AppTest.from_function(_render, kwargs={"listing": {"items": [item()]}, "card": card})
    app.run()
    assert not app.exception
    assert any(button.label == "Iniciar investigación de flujo" for button in app.button)
    assert not any("<script>" in block.value for block in app.markdown)


def test_starting_the_research_posts_the_subniche_label_with_its_format_and_language() -> None:
    card = {
        "hypothesis": item() | {"measurement": None, "research": None},
        "measurement": item()["measurement"],
        "channels": [],
        "channels_available": False,
        "research": None,
    }
    app = AppTest.from_function(_render, kwargs={"listing": {"items": [item()]}, "card": card})
    app.run()
    next(b for b in app.button if b.label == "Iniciar investigación de flujo").click().run()
    assert app.session_state["posted"] == (
        "/flow-research",
        {"niche_label": "subniche:history_revenge", "format": "long", "language": "en"},
    )
