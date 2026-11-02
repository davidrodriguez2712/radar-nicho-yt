# tests/test_web_preview.py
from pathlib import Path

import pytest

from scripts import web_preview


def test_the_preview_renders_the_list_and_the_card_with_local_assets(tmp_path: Path) -> None:
    assert web_preview.main(["--out", str(tmp_path), "--no-screenshots"]) == 0
    lista = (tmp_path / "lista.html").read_text()
    ficha = (tmp_path / "ficha.html").read_text()
    assert "Subnichos" in lista and "Prehistoric Creatures" in lista
    assert "Ingreso típico por canal al mes" in ficha
    assert 'href="/static/' not in lista and "file://" in lista
    assert "http://" not in lista.replace("file://", "") and "https://" not in lista


def test_the_preview_refuses_a_missing_output_directory_argument() -> None:
    with pytest.raises(SystemExit):
        web_preview.main([])
