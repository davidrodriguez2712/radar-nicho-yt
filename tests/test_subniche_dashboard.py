# tests/test_subniche_dashboard.py
from typing import Any

import pytest
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
    assert row["Exclusiones por idioma"] == 8


def test_research_status_is_shown_with_its_human_label() -> None:
    def label(status: str) -> str:
        research = {"id": "r1", "status": status, "language": "en", "created_at": "x"}
        return str(subniche_rows([item(research=research)])[0]["Investigación"])

    assert [label(s) for s in ("pendiente", "en_curso", "listo", "rechazado")] == [
        "pendiente",
        "en curso",
        "listo",
        "rechazado",
    ]


def test_rows_of_an_unmeasured_hypothesis_have_blanks_and_no_research() -> None:
    row = subniche_rows([item(measurement=None, research=None, finalist=False)])[0]
    assert row["Ingreso por canal (US$)"] == "" and row["Tracción"] is None
    assert row["Finalista"] == "no" and row["Investigación"] == "sin investigar"
    assert row["Exclusiones por idioma"] is None


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


def _render(listing, card, rejected=None):  # type: ignore[no-untyped-def]  # AppTest runs it as a standalone script
    from typing import Any

    import streamlit as st

    from nicheradar.config import Settings
    from nicheradar.subniche_dashboard import render_subniches

    def api(config: Settings, method: str, path: str, body: Any = None) -> dict[str, Any]:
        if path.startswith("/flow-research/"):
            detail: dict[str, Any] = rejected
            return detail
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


def test_hostile_text_reaches_the_page_only_as_plain_text() -> None:
    research = {"id": "r1", "status": "rechazado", "language": "xx", "created_at": "x"}
    hostile = item(label=HOSTILE, family=HOSTILE, queries=[HOSTILE], language=HOSTILE)
    hostile["research"] = research
    card = {
        "hypothesis": hostile,
        "measurement": hostile["measurement"] | {"rpm_source": HOSTILE},
        "channels": [],
        "channels_available": False,
        "research": research,
    }
    rejected = {"rejection": {"problems": [{"path": "rights", "message": HOSTILE}]}}
    app = AppTest.from_function(
        _render, kwargs={"listing": {"items": [hostile]}, "card": card, "rejected": rejected}
    )
    app.run()
    assert not app.exception
    texts = [block.value for block in app.text]
    assert any(HOSTILE in value and value.startswith("Consulta:") for value in texts)
    assert any(HOSTILE in value and value.startswith("Idioma de la hipótesis") for value in texts)
    assert any(HOSTILE in value and value.startswith("rights:") for value in texts)
    assert any(HOSTILE in value and "estado" in value for value in texts)
    assert any(HOSTILE in value and "RPM" in value for value in texts)
    rendering = [*app.markdown, *app.caption, *app.info, *app.warning]
    assert not any("<script>" in block.value for block in rendering)


def _card(hyp: dict[str, Any], research: dict[str, Any] | None, **over: Any) -> dict[str, Any]:
    card: dict[str, Any] = {
        "hypothesis": hyp | {"research": research},
        "measurement": hyp["measurement"],
        "channels": [],
        "channels_available": False,
        "research": research,
    }
    return card | over


def _start_button(hyp: dict[str, Any], research: dict[str, Any] | None) -> Any:
    app = AppTest.from_function(
        _render, kwargs={"listing": {"items": [hyp]}, "card": _card(hyp, research)}
    ).run()
    assert not app.exception
    return next(b for b in app.button if b.label == "Iniciar investigación de flujo"), app


def test_the_start_button_is_enabled_for_an_active_hypothesis_without_pending_research() -> None:
    button, _ = _start_button(item(), None)
    assert button.disabled is False


@pytest.mark.parametrize("status", ["pendiente", "en_curso"])
def test_the_start_button_is_disabled_while_a_research_is_open(status: str) -> None:
    research = {"id": "r1", "status": status, "language": "en", "created_at": "x"}
    button, _ = _start_button(item(), research)
    assert button.disabled is True


@pytest.mark.parametrize("status", ["proposed", "paused", "archived"])
def test_the_start_button_is_disabled_with_an_explanation_when_not_active(status: str) -> None:
    button, app = _start_button(item(status=status), None)
    assert button.disabled is True
    assert any(
        block.value == "La hipótesis debe estar activa y tener al menos una medición."
        for block in app.text
    )


def test_the_card_shows_language_exclusions_and_other_reasons_as_plain_text() -> None:
    hyp = item()
    hyp["measurement"] = hyp["measurement"] | {"excluded": {"language": 13, "no_recent_videos": 2}}
    _, app = _start_button(hyp, None)
    assert any("Excluidos: language 13, no_recent_videos 2" in block.value for block in app.text)
    assert any("Medida el 31/10/2026 07:00 -05" in block.value for block in app.text)


def test_the_list_filters_by_status() -> None:
    items = [item(), item(slug="b", label="B", status="paused", finalist=False)]
    app = AppTest.from_function(
        _render, kwargs={"listing": {"items": items}, "card": _card(items[0], None)}
    ).run()
    status = next(box for box in app.selectbox if box.label == "Estado")
    assert list(status.options) == ["Todos", "active", "paused"]
    status.set_value("paused").run()
    assert not app.exception
    assert [row["Subnicho"] for row in app.dataframe[0].value.to_dict("records")] == ["B"]
