"""`workers/main.py` llama a `tick_leads` solo con el subnicho activo y antes de las propuestas."""

from typing import Any

import pytest

from nicheradar.config import Settings
from nicheradar.workers import main as worker_main


def run_once(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> list[str]:
    called: list[str] = []
    monkeypatch.setattr(worker_main, "Settings", lambda: Settings(subniche_enabled=enabled))
    monkeypatch.setattr(worker_main, "tick", lambda config: {"status": "idle"})
    monkeypatch.setattr(worker_main, "record", lambda *args: None)
    monkeypatch.setattr(worker_main, "run_market_tick", lambda *args: {"status": "idle"})

    def background(name: str, fn: Any, *args: Any) -> dict[str, Any]:
        called.append(name)
        assert (
            fn.__name__
            == {
                "leads": "tick_leads",
                "subniche_proposals": "tick_proposals",
                "subniche": "tick_subniche",
            }[name]
        )
        return {"status": "idle"}

    monkeypatch.setattr(worker_main, "run_background_tick", background)
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    worker_main.main()
    return called


def test_leads_run_before_proposals(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_once(monkeypatch, True) == ["leads", "subniche_proposals", "subniche"]


def test_leads_do_not_run_without_the_subniche_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_once(monkeypatch, False) == []
