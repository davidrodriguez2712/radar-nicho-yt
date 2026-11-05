import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from nicheradar.web import app as web_app
from tests.lead_samples import GIF, PNG
from tests.web_helpers import Api, make_client

STATIC = Path(web_app.__file__).parent / "static"
HARNESS = Path(__file__).parent / "js" / "sw_harness.mjs"
READ_ID = "0b6f3a52-1c1e-4c39-9b0e-2f6a7c1d0002"


def run_sw(scenario: str) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node no está instalado: la prueba del service worker necesita Node >= 20")
    done = subprocess.run(
        [node, str(HARNESS), str(STATIC / "sw.js"), scenario],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    result: dict[str, Any] = json.loads(done.stdout)
    return result


def test_manifest_has_a_single_post_share_target_with_image_files() -> None:
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    target = manifest["share_target"]
    assert target["method"] == "POST" and target["enctype"] == "multipart/form-data"
    assert target["action"] == "/compartir"
    assert target["params"]["files"] == [
        {"name": "imagen", "accept": ["image/png", "image/jpeg", "image/webp"]}
    ]


def test_service_worker_caches_a_valid_shared_image_and_serves_it() -> None:
    out = run_sw("image")
    assert out["post"] == {
        "handled": True,
        "status": 303,
        "location": "https://app.test/compartir/imagen",
        "type": None,
    }
    assert out["cached"] == ["nicheradar-share-v1 /compartir/imagen/archivo"]
    assert out["get"]["status"] == 200 and out["get"]["type"] == "image/png"


@pytest.mark.parametrize("scenario", ["too_big", "gif"])
def test_service_worker_refuses_other_files(scenario: str) -> None:
    out = run_sw(scenario)
    assert out["post"]["location"] == "https://app.test/compartir/imagen?aviso=imagen_no_valida"
    assert out["cached"] == []


def test_service_worker_turns_a_shared_link_into_the_get_screen() -> None:
    out = run_sw("link")
    assert out["post"]["status"] == 303
    assert out["post"]["location"] == (
        "https://app.test/compartir?title=Mira&text=https%3A%2F%2Fx.com%2Fautor_x%2Fstatus%2F123"
    )


def test_service_worker_ignores_other_posts_and_misses_without_a_file() -> None:
    out = run_sw("other")
    assert out["post"] == {"handled": False}
    assert out["missing"]["status"] == 404


def test_service_worker_still_caches_only_static_and_the_shared_file() -> None:
    source = (STATIC / "sw.js").read_text()
    assert (
        source.count("cache.put(") == 2
    )  # /static (stale-while-revalidate) y la imagen compartida
    assert '"/compartir/imagen/archivo"' in source and '"nicheradar-share-v1"' in source
    assert "/api/" not in source


def test_share_script_has_no_eval_or_inner_html_or_external_resources() -> None:
    source = (STATIC / "js" / "compartir.js").read_text()
    for banned in ("eval(", "innerHTML", "document.write", "new Function", "http://", "https://"):
        assert banned not in source
    assert "textContent" in source


def api() -> Api:
    return Api(
        {
            ("POST", "/api/v1/leads/images"): (
                202,
                {"id": READ_ID, "status": "queued", "created": True},
            )
        }
    )


def page_tokens(web: Any) -> tuple[str, str]:
    page = web.get("/compartir/imagen")
    assert page.status_code == 200 and "Imagen recibida" in page.text
    assert 'src="/compartir/imagen/archivo"' in page.text and "Leer imagen" in page.text
    assert '<script src="/static/js/compartir.js"' in page.text
    csrf = page.text.split('data-csrf="')[1].split('"')[0]
    nonce = page.text.split('data-nonce="')[1].split('"')[0]
    return csrf, nonce


def test_image_screen_shows_the_fixed_notices() -> None:
    web = make_client(api())
    bad = web.get("/compartir/imagen?aviso=imagen_no_valida")
    assert "Solo se aceptan imágenes PNG, JPEG o WEBP de hasta 5 MB." in bad.text
    again = web.get("/compartir/imagen?aviso=reinstala")
    assert "abre NicheRadar una vez desde el icono instalado" in again.text
    assert "<script>alert" not in web.get("/compartir/imagen?aviso=<script>alert(1)</script>").text


def test_read_image_forwards_bytes_once_and_returns_the_next_page() -> None:
    fake = api()
    web = make_client(fake)
    csrf, nonce = page_tokens(web)
    head = {"X-CSRF-Token": csrf, "X-Nonce": nonce, "Content-Type": "image/png"}
    first = web.post("/compartir/imagen/leer", content=PNG, headers=head)
    second = web.post("/compartir/imagen/leer", content=PNG, headers=head)
    assert first.json() == second.json() == {"next": f"/lecturas/{READ_ID}"}
    sent = [json.loads(c.content) for c in fake.calls]
    assert sent[0]["media_type"] == "image/png" and len(sent) == 2
    keys = {c.headers["idempotency-key"] for c in fake.calls}
    assert len(keys) == 1


@pytest.mark.parametrize(
    ("body", "head", "status"),
    [
        (PNG, {"X-CSRF-Token": "malo"}, 403),
        (PNG, {"X-Nonce": "no-es-un-nonce"}, 403),
        (GIF, {}, 422),
        (b"<svg/>", {}, 422),
        (PNG + b"\x00" * 5_242_880, {}, 413),
    ],
)
def test_read_image_refuses_without_calling_the_api(
    body: bytes, head: dict[str, str], status: int
) -> None:
    fake = api()
    web = make_client(fake)
    csrf, nonce = page_tokens(web)
    headers = {"X-CSRF-Token": csrf, "X-Nonce": nonce, "Content-Type": "image/png"} | head
    response = web.post("/compartir/imagen/leer", content=body, headers=headers)
    assert response.status_code == status and "error" in response.json()
    assert fake.calls == []


def test_read_image_without_a_session_is_refused() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    fake = api()
    anonymous = TestClient(
        create_app(settings(), transport=httpx.MockTransport(fake)), follow_redirects=False
    )
    response = anonymous.post("/compartir/imagen/leer", content=PNG)
    assert response.status_code in (303, 401, 403) and fake.calls == []


def test_api_rejection_is_a_fixed_text() -> None:
    fake = Api(
        {("POST", "/api/v1/leads/images"): (429, {"code": "daily_limit", "message": "de la API"})}
    )
    web = make_client(fake)
    csrf, nonce = page_tokens(web)
    response = web.post(
        "/compartir/imagen/leer",
        content=PNG,
        headers={"X-CSRF-Token": csrf, "X-Nonce": nonce, "Content-Type": "image/png"},
    )
    assert response.status_code == 429
    assert response.json() == {"error": "Se llegó al tope diario de lecturas de tweets."}


def test_server_never_stores_the_shared_file() -> None:
    web = make_client(api())
    assert web.get("/compartir/imagen/archivo").status_code == 404
    with_file = web.post("/compartir", files={"imagen": ("a.png", PNG, "image/png")})
    assert with_file.status_code == 303
    assert with_file.headers["location"] == "/compartir/imagen?aviso=reinstala"
    link = web.post("/compartir", data={"title": "t", "text": "https://youtu.be/dQw4w9WgXcQ"})
    assert link.status_code == 303 and link.headers["location"].startswith("/compartir?")
    assert "text=https%3A%2F%2Fyoutu.be" in link.headers["location"]


def test_image_screen_requires_a_session() -> None:
    from fastapi.testclient import TestClient

    from nicheradar.web.app import create_app
    from tests.web_helpers import settings

    anonymous = TestClient(
        create_app(settings(), transport=httpx.MockTransport(api())), follow_redirects=False
    )
    response = anonymous.get("/compartir/imagen")
    assert response.status_code == 303 and response.headers["location"].startswith("/login?next=")
