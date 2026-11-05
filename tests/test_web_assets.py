# tests/test_web_assets.py
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from nicheradar.web import app as web_app
from nicheradar.web.app import create_app
from tests.web_helpers import Api, make_client, settings

ROOT = Path(web_app.__file__).parent
STATIC = ROOT / "static"


def anonymous() -> TestClient:
    return TestClient(create_app(settings()), follow_redirects=False)


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


def test_radios_use_the_brand_colour_and_row_labels_keep_a_minimum_width() -> None:
    css = (ROOT / "static/css/app.css").read_text()
    assert "input[type=radio]" in css and "accent-color:var(--primary)" in css
    assert ".row__label{" in css and "min-width:5.5em" in css


DYNAMIC_CLASSES = {
    "blocker--": ("falta", "vence", "vigencia", "contacto", "desconocido", "decision"),
    "step--": ("done", "current", "todo"),
    "btn--": ("primary", "secondary", "danger"),
    "chip--": ("neutral", "amber", "green", "rose", "blue", "gray"),
    "note--": ("green", "amber", "rose"),
    "mark--": ("ok", "todo"),
    "journey__mark--": ("done", "now", "pending"),
    "bar__seg--": ("c0", "c1", "c2", "c3", "c4"),
    "legend__dot--": ("c0", "c1", "c2", "c3", "c4"),
    "bar--p": tuple(str(n) for n in range(0, 101, 5)),
}


def test_every_class_the_pilot_templates_use_has_a_rule_in_the_stylesheet() -> None:
    css = (STATIC / "css" / "app.css").read_text()
    missing: set[str] = set()
    for template in [
        *(ROOT / "templates" / "pilotos").glob("*.html"),
        *(ROOT / "templates" / "operacion").glob("*.html"),
        *(ROOT / "templates" / "nichos").glob("*.html"),
        *(ROOT / "templates" / "informes").glob("*.html"),
        ROOT / "templates" / "hoy.html",
        ROOT / "templates" / "mas.html",
        ROOT / "templates" / "components.html",
    ]:
        text = template.read_text()
        for attribute in re.findall(r'class="([^"]*)"', text):
            plain = re.sub(r"\{\{.*", "@", re.sub(r"\{%.*?%\}", " ", attribute))  # may cut at "ok"
            for token in plain.split():
                names = [token]
                if token.endswith("--@") or token.endswith("@"):
                    prefix = token.rstrip("@")
                    names = [prefix + kind for kind in DYNAMIC_CLASSES.get(prefix, ())] or [prefix]
                for name in names:
                    if "@" in name or not name:
                        continue
                    if not re.search(rf"\.{re.escape(name)}(?![\w-])", css):
                        missing.add(f"{template.name}: {name}")
    assert not missing, sorted(missing)


def _rule(css: str, selector: str) -> str:
    found = re.search(rf"(?:^|\}})\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert found, selector
    return found.group(1)


def test_pills_and_the_hoy_card_links_are_44px_touch_targets() -> None:
    css = (STATIC / "css" / "app.css").read_text()
    for selector in (".pill", ".list__name"):
        rule = _rule(css, selector)
        assert "min-height:44px" in rule and "align-items:center" in rule, selector
