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


def test_the_preview_renders_the_corte_1_screens_with_local_assets(tmp_path: Path) -> None:
    assert web_preview.main(["--out", str(tmp_path), "--no-screenshots"]) == 0
    expected = {
        "hoy": "nichos que merecen tu atención",
        "nichos": "historia militar explicada",
        "investigar": "Iniciar investigación en inglés",
        "informe": "Qué tan firme es",
        "autorizar": "Autorizar piloto",
    }
    for name, text in expected.items():
        html = (tmp_path / f"{name}.html").read_text()
        assert text in html, name
        assert "file://" in html and 'href="/static/' not in html, name


def test_the_preview_renders_the_corte_2a_pilot_screens_with_local_assets(tmp_path: Path) -> None:
    assert web_preview.main(["--out", str(tmp_path), "--no-screenshots"]) == 0
    expected = {
        "pilotos": "ciencia en español",
        "piloto": "Estado actual",
        "preparacion": "Carpeta del canal en la Mac",
        "confirmar": "Confirmar: cancelar piloto",
    }
    for name, text in expected.items():
        html = (tmp_path / f"{name}.html").read_text()
        assert text in html, name
        assert "file://" in html and 'href="/static/' not in html, name


def test_the_preview_renders_the_corte_3a_operation_screens_with_local_assets(
    tmp_path: Path,
) -> None:
    assert web_preview.main(["--out", str(tmp_path), "--no-screenshots"]) == 0
    expected = {
        "operacion": "Scraper de mercado",
        "ejecuciones": "Ejecuciones del scraper",
        "mas": "Scraper de mercado y subnichos",
        "confirmar-scraper": "Confirmar y reanudar",
    }
    for name, text in expected.items():
        html = (tmp_path / f"{name}.html").read_text()
        assert text in html, name
        assert "file://" in html and 'href="/static/' not in html, name
    operacion = (tmp_path / "operacion.html").read_text()
    assert "Pausado" in operacion and "parcial" in operacion and "falló" in operacion
