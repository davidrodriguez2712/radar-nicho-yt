# scripts/web_preview.py
"""Render the mobile web screens with sample data to HTML and PNG, to compare them with Figma."""

import argparse
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.web import app as web_app
from nicheradar.web.app import create_app

if __package__ in (None, ""):  # run as `python scripts/web_preview.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.web_preview_data import CARD, ITEMS  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PASSWORD = "p" * 32
STATIC = Path(web_app.__file__).parent / "static"
WIDTH = 390
MIN_WINDOW = 500
MAX_HEIGHT = 8000


def _api(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/subniches":
        return httpx.Response(200, json={"items": ITEMS})
    if path.startswith("/api/v1/subniches/"):
        return httpx.Response(200, json=CARD)
    if path == "/api/v1/status":
        return httpx.Response(200, json={"radar_paused": True})
    return httpx.Response(404, json={"detail": "not found"})


def _local(html: str) -> str:
    """Point the static assets at the package folder: only the preview uses file://."""
    return html.replace('"/static/', f'"file://{STATIC}/')


def render_pages(out: Path) -> dict[str, Path]:
    config = Settings(
        service_token=SecretStr("t" * 32),
        dashboard_password=SecretStr(PASSWORD),
        api_url="http://api.test",
        dashboard_ui="web",
    )
    app = create_app(config, transport=httpx.MockTransport(_api))
    web = TestClient(app, follow_redirects=False)
    assert web.post("/login", data={"password": PASSWORD}).status_code == 303
    slug = CARD["hypothesis"]["slug"]
    pages = {"lista": "/subnichos", "ficha": f"/subnichos/{slug}"}
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
