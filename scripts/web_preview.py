# scripts/web_preview.py
"""Render the mobile web screens with sample data to HTML and PNG, to compare them with Figma."""

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.web import app as web_app
from nicheradar.web.app import create_app

if __package__ in (None, ""):  # run as `python scripts/web_preview.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.web_preview_data import (  # noqa: E402
    APPROVAL,
    CALIBRATING_ID,
    CALIBRATION_DETAIL,
    CALIBRATION_VIDEOS,
    CARD,
    FLOWS,
    ITEMS,
    LEAD_FAILED,
    LEAD_IMAGE,
    LEAD_QUEUED,
    LEAD_READY,
    NICHE_DETAIL,
    NICHES,
    PILOT_DETAIL,
    PILOT_ID,
    PILOT_VIDEOS,
    PILOTS,
    PROPOSAL_ID,
    PROPOSAL_QUEUED,
    PROPOSAL_READY,
    PROPOSED_SLUG,
    READ_FAILED_ID,
    READ_IMAGE_ID,
    READ_QUEUED_ID,
    READ_READY_ID,
    REPORT,
    RUNS,
    SCHEDULE,
)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PASSWORD = "p" * 32
STATIC = Path(web_app.__file__).parent / "static"
WIDTH = 390
MIN_WINDOW = 500
MAX_HEIGHT = 8000
QUEUED_ID = "1c2d3e4f-5061-4b7c-8d9e-0f1a2b3c4d5e"
PROPOSED_CARD = CARD | {
    "hypothesis": CARD["hypothesis"]
    | {"slug": PROPOSED_SLUG, "label": "Ancient Rome", "status": "proposed"}
}
LEADS = {
    READ_READY_ID: LEAD_READY,
    READ_QUEUED_ID: LEAD_QUEUED,
    READ_FAILED_ID: LEAD_FAILED,
    READ_IMAGE_ID: LEAD_IMAGE,
}
# A 1x1 PNG: the shared image only lives in the phone's cache, so the preview inlines a sample.
SAMPLE_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PREVIEW_NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # the sample data is dated around it


def _api(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    body: object
    if (lead := LEADS.get(path.removeprefix("/api/v1/leads/"))) is not None:
        body = lead
    elif path == "/api/v1/subniches":
        body = {"items": ITEMS}
    elif path == f"/api/v1/subniches/proposals/{PROPOSAL_ID}":
        body = PROPOSAL_READY
    elif path == f"/api/v1/subniches/proposals/{QUEUED_ID}":
        body = PROPOSAL_QUEUED
    elif path == f"/api/v1/subniches/{PROPOSED_SLUG}/approval":
        body = APPROVAL
    elif path == f"/api/v1/subniches/{PROPOSED_SLUG}":
        body = PROPOSED_CARD
    elif path.startswith("/api/v1/subniches/"):
        body = CARD
    elif path == "/api/v1/status":
        body = {"radar_paused": True, "timezone": "America/Lima"}
    elif path == "/api/v1/market/schedule":
        body = SCHEDULE
    elif path == "/api/v1/market/runs":
        body = {"items": RUNS}
    elif path == "/api/v1/market/niches":
        body = {"items": NICHES, "total": len(NICHES), "limit": 200, "offset": 0}
    elif path.startswith("/api/v1/market/niches/"):
        body = NICHE_DETAIL
    elif path == "/api/v1/flow-research":
        body = {"items": FLOWS}
    elif path.startswith("/api/v1/flow-research/"):
        body = REPORT
    elif path == "/api/v1/pilots":
        body = {"items": PILOTS}
    elif path == f"/api/v1/pilots/{CALIBRATING_ID}":
        body = CALIBRATION_DETAIL
    elif path == f"/api/v1/pilots/{CALIBRATING_ID}/videos":
        body = {"items": CALIBRATION_VIDEOS}
    elif path == "/api/v1/pilots/pil_20261030_ciencia":
        body = CALIBRATION_DETAIL | {
            "pilot_id": "pil_20261030_ciencia",
            "status": "decision_pendiente",
            "niche_label": "ciencia en español",
        }
    elif path == "/api/v1/pilots/pil_20261030_ciencia/videos":
        body = {"items": CALIBRATION_VIDEOS[:3]}
    elif path == f"/api/v1/pilots/{PILOT_ID}":
        body = PILOT_DETAIL
    elif path == f"/api/v1/pilots/{PILOT_ID}/videos":
        body = {"items": PILOT_VIDEOS}
    else:
        return httpx.Response(404, json={"detail": "not found"})
    return httpx.Response(200, json=body)


def _local(html: str) -> str:
    """Point the static assets at the package folder: only the preview uses file://."""
    return html.replace('"/static/', f'"file://{STATIC}/').replace(
        'src="/compartir/imagen/archivo"', f'src="{SAMPLE_IMAGE}"'
    )


def render_pages(out: Path) -> dict[str, Path]:
    config = Settings(
        service_token=SecretStr("t" * 32),
        dashboard_password=SecretStr(PASSWORD),
        api_url="http://api.test",
        dashboard_ui="web",
    )
    app = create_app(
        config, transport=httpx.MockTransport(_api), clock=lambda: PREVIEW_NOW.timestamp()
    )
    web = TestClient(app, follow_redirects=False)
    assert web.post("/login", data={"password": PASSWORD}).status_code == 303
    slug = CARD["hypothesis"]["slug"]
    label = quote(NICHES[0]["niche_label"], safe="")
    pages = {
        "lista": "/subnichos",
        "ficha": f"/subnichos/{slug}",
        "proponer": "/subnichos/proponer",
        "propuesta_cola": f"/subnichos/propuestas/{QUEUED_ID}",
        "propuesta_lista": f"/subnichos/propuestas/{PROPOSAL_ID}",
        "aprobar": f"/subnichos/{PROPOSED_SLUG}/aprobar",
        "archivar": f"/subnichos/{slug}/archivar",
        "compartir": "/compartir?url=" + quote("https://youtu.be/dQw4w9WgXcQ?si=x", safe=""),
        "compartir_tweet": "/compartir?url=" + quote("https://x.com/u/status/1", safe=""),
        "lectura_lista": f"/lecturas/{READ_READY_ID}",
        "lectura_en_curso": f"/lecturas/{READ_QUEUED_ID}",
        "lectura_fallida": f"/lecturas/{READ_FAILED_ID}",
        "lectura_imagen": f"/lecturas/{READ_IMAGE_ID}",
        "lectura_propuestas": f"/lecturas/{READ_READY_ID}/propuestas?creadas=1&omitidas=0",
        "compartir_imagen": "/compartir/imagen",
        "hoy": "/",
        "nichos": "/nichos",
        "nicho_detalle": f"/nichos/ver?etiqueta={label}&formato=long",
        "investigar": f"/nichos/investigar?etiqueta={label}&formato=long",
        "informe": f"/informes/{REPORT['id']}",
        "autorizar": f"/pilotos/autorizar?informe={REPORT['id']}",
        "pilotos": "/pilotos",
        "piloto": f"/pilotos/{PILOT_ID}",
        "preparacion": f"/pilotos/{PILOT_ID}?pestana=preparacion",
        "calibracion": f"/pilotos/{CALIBRATING_ID}?pestana=calibracion",
        "confirmar": f"/pilotos/{PILOT_ID}/cancelar",
        "operacion": "/operacion",
        "ejecuciones": "/operacion/ejecuciones",
        "mas": "/mas",
        "confirmar-scraper": "/operacion/scraper/reanudar",
    }
    written: dict[str, Path] = {}
    for name, path in pages.items():
        target = out / f"{name}.html"
        target.write_text(_local(web.get(path).text))
        written[name] = target
    return written


def _chrome(chrome: str, page: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            *args,
            f"file://{page}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _frame(page: Path, height: int | None) -> Path:
    """Chrome headless never makes a window narrower than 500 px, so the 390 px phone viewport
    is an iframe inside a wider page, centred and cropped out afterwards."""
    frame = page.with_name(f"{page.stem}.frame.html")
    probe = (
        "<script>addEventListener('load',()=>{const d=document.querySelector('iframe')"
        ".contentDocument.documentElement;document.body.dataset.h=d.scrollHeight})</script>"
    )
    frame.write_text(
        "<!doctype html><meta charset=utf-8><style>html,body{margin:0;background:#fff}"
        f"iframe{{display:block;border:0;margin-left:{(MIN_WINDOW - WIDTH) // 2}px;"
        f"width:{WIDTH}px;height:{height or 900}px}}</style>"
        f'<iframe src="file://{page}"></iframe>{probe}'
    )
    return frame


def content_height(page: Path, chrome: str) -> int:
    """Document height at the phone width, read from the rendered DOM."""
    frame = _frame(page, None)
    try:
        dom = _chrome(chrome, frame, f"--window-size={MIN_WINDOW},900", "--dump-dom").stdout
    finally:
        frame.unlink()
    marker = 'data-h="'
    start = dom.find(marker)
    if start < 0:
        return 1800
    return min(int(dom[start + len(marker) :].split('"', 1)[0]), MAX_HEIGHT)


def screenshot(page: Path, chrome: str) -> Path:
    png = page.with_suffix(".png")
    height = content_height(page, chrome)
    frame = _frame(page, height)
    try:
        _chrome(
            chrome,
            frame,
            "--force-device-scale-factor=2",
            f"--window-size={MIN_WINDOW},{height}",
            f"--screenshot={png}",
        )
    finally:
        frame.unlink()
    # `sips` (macOS) crops from the centre, where the frame sits.
    subprocess.run(
        [
            "sips",
            "--cropToHeightWidth",
            str(height * 2),
            str(WIDTH * 2),
            str(png),
        ],
        check=True,
        capture_output=True,
    )
    return png


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chrome", default=CHROME)
    parser.add_argument("--no-screenshots", action="store_true")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    pages = render_pages(args.out)
    for path in pages.values():
        print(path)
        if not args.no_screenshots and Path(args.chrome).exists():
            print(screenshot(path, args.chrome))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
