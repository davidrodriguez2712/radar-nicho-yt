# tests/test_web_assets.py
import json
import re
from pathlib import Path
from typing import cast

from fastapi import Request
from fastapi.testclient import TestClient

from nicheradar.web import app as web_app
from nicheradar.web.app import create_app
from nicheradar.web.deps import radar_state
from tests.web_helpers import Api, make_client, settings

ROOT = Path(web_app.__file__).parent
STATIC = ROOT / "static"


def anonymous() -> TestClient:
    return TestClient(create_app(settings()), follow_redirects=False)


def request_of(web: TestClient) -> Request:
    """Minimal stand-in carrying the app state, typed as the Request radar_state expects."""

    class Req:
        app = web.app

    return cast(Request, Req())


def test_the_stylesheet_the_font_and_htmx_are_served_from_the_app() -> None:
    web = anonymous()
    for path, kind in (
        ("/static/css/app.css", "text/css"),
        ("/static/js/htmx.min.js", "javascript"),
        ("/static/js/app.js", "javascript"),
        ("/static/fonts/InterVariable.woff2", "font/woff2"),
        ("/static/icons/icon-192.png", "image/png"),
        ("/static/icons/icon-512.png", "image/png"),
        ("/static/icons/apple-touch-icon.png", "image/png"),
    ):
        response = web.get(path)
        assert response.status_code == 200, path
        assert kind in response.headers["content-type"], path
    assert "cache-control" not in {k.lower() for k in web.get("/static/css/app.css").headers} or (
        web.get("/static/css/app.css").headers["cache-control"] != "no-store"
    )


def test_the_manifest_declares_a_standalone_app_with_the_brand_colors() -> None:
    manifest = json.loads(anonymous().get("/static/manifest.webmanifest").text)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    assert manifest["theme_color"] == "#be123c" and manifest["background_color"] == "#fff8f5"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes


def test_the_service_worker_is_served_at_the_root_scope_and_caches_only_static_files() -> None:
    response = anonymous().get("/sw.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    assert response.headers["service-worker-allowed"] == "/"
    body = response.text
    assert "/static/" in body and "/sin-conexión" in body
    assert "/api/" not in body  # never caches API data


def test_the_service_worker_revalidates_static_files_so_a_redeploy_is_not_stale() -> None:
    body = anonymous().get("/sw.js").text
    branch = body.split('startsWith("/static/")', 1)[1].split('request.mode === "navigate"', 1)[0]
    assert "cache.put" in branch and "fetch(request)" in branch
    assert "/api/" not in body
    assert body.count("cache.put") == 1  # the only write outside install is the /static/ branch


def test_the_manifest_icons_are_not_declared_maskable() -> None:
    manifest = json.loads(anonymous().get("/static/manifest.webmanifest").text)
    assert {icon["purpose"] for icon in manifest["icons"]} == {"any"}


def test_the_segmented_control_is_not_declared_as_tabs() -> None:
    text = (ROOT / "templates/components.html").read_text()
    assert "tablist" not in text


def test_the_offline_page_is_public() -> None:
    response = anonymous().get("/sin-conexión")
    assert response.status_code == 200 and "Sin conexión" in response.text


def test_the_offline_page_answers_the_percent_encoded_path_the_browser_sends() -> None:
    web = anonymous()
    response = web.get("/sin-conexi%C3%B3n")
    assert response.status_code == 200 and "Sin conexión" in response.text
    assert "/sin-conexión" in web.get("/sw.js").text  # the worker precaches the same path


def test_no_template_stylesheet_or_script_reaches_a_third_party() -> None:
    offenders: list[str] = []
    files = [
        *ROOT.glob("templates/**/*.html"),
        STATIC / "css/app.css",
        STATIC / "js/app.js",
        STATIC / "sw.js",
        STATIC / "manifest.webmanifest",
    ]
    for path in files:
        for found in re.findall(r"https?://[^\s\"')]+", path.read_text()):
            offenders.append(f"{path.name}: {found}")
    assert offenders == []


def test_the_templates_use_no_inline_styles_or_scripts() -> None:
    for path in ROOT.glob("templates/**/*.html"):
        text = path.read_text()
        assert not re.search(r"\sstyle\s*=", text), path.name
        assert not re.search(r"<script(?![^>]*\ssrc=)", text), path.name
        assert not re.search(r"\son[a-z]+\s*=", text), path.name


def test_an_authenticated_page_uses_the_base_with_the_bar_the_nav_and_the_pwa_links() -> None:
    api = Api({("GET", "/api/v1/status"): (200, {"radar_paused": True})})
    web = make_client(api)
    page = web.get("/sin-conexión")  # public, but the base is shared
    assert 'rel="manifest"' in page.text and 'name="theme-color"' in page.text
    assert "/static/css/app.css" in page.text and "/static/js/htmx.min.js" in page.text
    assert "htmx-config" in page.text and "includeIndicatorStyles" in page.text
    meta = re.search(r'<meta name="htmx-config" content=\'([^\']+)\'', page.text)
    assert meta is not None
    config = json.loads(meta.group(1))
    # Offline promise: htmx must not keep page copies (data, CSRF token) in localStorage.
    assert config["historyCacheSize"] == 0


def test_the_radar_badge_reflects_the_api_state_and_is_cached() -> None:
    api = Api({("GET", "/api/v1/status"): (200, {"radar_paused": True})})
    now = [1_000.0]
    web = make_client(api, clock=lambda: now[0])
    # Pages call the status endpoint through render(); two calls inside 30 s hit it once.
    assert radar_state(request_of(web)) == "paused"
    assert radar_state(request_of(web)) == "paused"
    assert api.count("GET", "/api/v1/status") == 1
    now[0] += 31
    api.routes[("GET", "/api/v1/status")] = (200, {"radar_paused": False})
    assert radar_state(request_of(web)) == "active"


def test_a_status_failure_hides_the_badge_instead_of_breaking_the_page() -> None:
    web = make_client(Api())  # /status answers 404
    assert radar_state(request_of(web)) is None
