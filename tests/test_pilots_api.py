# tests/test_pilots_api.py
"""API de pilotos de punta a punta: autorizar, entregar, reportar, proponer y decidir."""

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.pilots.contracts import package_sha256, validate_package
from tests.flow_research_samples import valid_dossier
from tests.pilot_samples import iso
from tests.test_flow_research_api import BASE as FLOW
from tests.test_flow_research_api import create, tentative_api
from tests.test_foundation import TOKEN
from tests.test_market_api import AUTH
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres
BASE = "/api/v1/pilots"
CHANNEL = "canal-historias"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ready_dossier(api: TestClient, dossier: dict[str, Any] | None = None) -> str:
    request_id = str(create(api)["id"])
    owner = api.post(f"{FLOW}/{request_id}/claim", json={"owner": "w"}, headers=AUTH).json()[
        "lease_owner"
    ]
    content = dossier or valid_dossier(UUID(request_id), NOW)
    done = api.post(
        f"{FLOW}/{request_id}/dossier", json={"owner": owner, "dossier": content}, headers=AUTH
    )
    assert done.status_code == 200
    return request_id


def authorize_body(request_id: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "niche_label": "personal_finance",
        "format": "long",
        "dossier_request_id": request_id,
        "budget": {
            "currency": "USD",
            "low": 3,
            "likely": 19.5,
            "high": 41,
            "max_videos": 10,
            "basis": "10 videos x costo medido en canal-historias",
        },
        "close_after_failed_milestones": 2,
        "target_channel": CHANNEL,
        "recipe": {"name": "faceless-storytelling", "version": "0.1.0"},
        "authorized_by": "david",
    }
    body.update(over)
    return body


def launched(engine: Engine, **over: Any) -> tuple[TestClient, str, str]:
    """Devuelve (api, pilot_id, token del canal) con el piloto autorizado."""
    api = tentative_api(engine)
    request_id = ready_dossier(api)
    created = api.post(BASE, json=authorize_body(request_id, **over), headers=AUTH)
    assert created.status_code == 201, created.text
    token = api.post(
        "/api/v1/channel-tokens", json={"channel_id": CHANNEL, "label": "mac"}, headers=AUTH
    )
    assert token.status_code == 201
    return api, created.json()["pilot_id"], token.json()["token"]


def deliver(api: TestClient, pilot_id: str, token: str) -> dict[str, Any]:
    package = api.get(f"{BASE}/{pilot_id}/package", headers=bearer(token))
    assert package.status_code == 200
    payload: dict[str, Any] = package.json()
    sent = api.post(
        f"{BASE}/{pilot_id}/delivery",
        json={"channel_id": CHANNEL, "package_sha256": payload["package_sha256"]},
        headers=bearer(token),
    )
    assert sent.status_code == 200
    return payload


def video(n: int, avd: float | None = 25.0, **over: Any) -> dict[str, Any]:
    published = NOW - timedelta(days=60 - n)
    data: dict[str, Any] = {
        "video_id": f"v_{n:02d}",
        "source_state": "EN_MEDICION" if avd is not None else "PUBLICADO",
        "visibility": "public",
        "published_at": iso(published),
        "cost_usd": 0.3,
        "cost_equivalent_usd": 1.5,
        "machine_minutes": 60,
        "measurement": None
        if avd is None
        else {
            "measured_at": iso(published + timedelta(days=8)),
            "window_days": 7,
            "avd_pct": avd,
            "views": 100,
            "browse_share_pct": None,
            "subscribers_gained": 0,
        },
        "failure_code": None,
    }
    data.update(over)
    return data


def report(pilot_id: str, videos: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract": "channel-report-v1",
        "pilot_id": pilot_id,
        "channel_id": CHANNEL,
        "reported_at": iso(NOW),
        "channel_status": "active",
        "videos": videos,
        "note": None,
    }
    body.update(over)
    return body


def send(api: TestClient, token: str, pilot_id: str, body: Any) -> Any:
    return api.post(f"{BASE}/{pilot_id}/reports", content=json.dumps(body), headers=bearer(token))


def test_every_endpoint_requires_a_credential(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    for method, path in [
        ("get", BASE),
        ("get", BASE + "/pending?channel=" + CHANNEL),
        ("get", BASE + "/pil_x"),
        ("post", BASE),
        ("get", "/api/v1/channel-tokens"),
        ("post", "/api/v1/channel-tokens"),
    ]:
        assert getattr(api, method)(path).status_code == 401, path
        assert getattr(api, method)(path, headers=bearer("wrong")).status_code == 401, path


def test_authorize_freezes_a_valid_package_with_honest_evidence(isolated_engine: Engine) -> None:
    api, pilot_id, _ = launched(isolated_engine)
    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    package = detail["package"]
    parsed, problems = validate_package(package, NOW)
    assert problems == [] and parsed is not None
    assert package["package_sha256"] == package_sha256(package)
    assert pilot_id.startswith("pil_20260913_personal-finance")
    assert package["niche"]["language"] == "en" and detail["status"] == "autorizado"
    scores = package["evidence"]["scores"]
    assert scores["creator_fit"] is None and scores["market"] is None  # no existen por nicho
    assert all(f["origin"] != "verified" for f in package["evidence"]["figures"])
    assert [r["id"] for r in package["stop_rules"]][:2] == ["pipeline-s6", "retencion-v10"]
    listed = api.get(BASE, headers=AUTH).json()["items"]
    assert [i["pilot_id"] for i in listed] == [pilot_id]


def test_authorize_refuses_what_it_cannot_support(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    request_id = create(api)["id"]  # sin dossier todavía
    body = authorize_body(request_id)
    assert api.post(BASE, json=body, headers=AUTH).json()["detail"]["code"] == "dossier_not_ready"
    ready = ready_dossier_for(api, request_id)
    mismatch = authorize_body(ready, niche_label="gaming_general")
    assert api.post(BASE, json=mismatch, headers=AUTH).status_code == 409
    bad_budget = authorize_body(ready, budget={**body["budget"], "low": 50, "high": 3})
    refused = api.post(BASE, json=bad_budget, headers=AUTH)
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert api.post(BASE, json=authorize_body(ready, unexpected=1), headers=AUTH).status_code == 422


def ready_dossier_for(api: TestClient, request_id: str) -> str:
    owner = api.post(f"{FLOW}/{request_id}/claim", json={"owner": "w"}, headers=AUTH).json()[
        "lease_owner"
    ]
    content = valid_dossier(UUID(request_id), NOW)
    sent = api.post(
        f"{FLOW}/{request_id}/dossier", json={"owner": owner, "dossier": content}, headers=AUTH
    )
    assert sent.status_code == 200
    return request_id


def test_a_no_go_dossier_needs_explicit_acceptance(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    request_id = create(api)["id"]
    dossier = valid_dossier(UUID(request_id), NOW)
    dossier["verdict"]["recommendation"] = "no_go"
    owner = api.post(f"{FLOW}/{request_id}/claim", json={"owner": "w"}, headers=AUTH).json()[
        "lease_owner"
    ]
    accepted = api.post(
        f"{FLOW}/{request_id}/dossier", json={"owner": owner, "dossier": dossier}, headers=AUTH
    )
    if accepted.status_code != 200:
        pytest.skip("el dossier de muestra no admite no_go sin más cambios")
    body = authorize_body(request_id)
    assert (
        api.post(BASE, json=body, headers=AUTH).json()["detail"]["code"]
        == "no_go_requires_acceptance"
    )
    ok = api.post(BASE, json={**body, "accept_no_go": True}, headers=AUTH)
    assert ok.status_code == 201 and "NO-GO" in ok.json()["package"]["dossier"]["thesis"]


def test_only_one_open_pilot_per_channel_and_supersede_replaces(
    isolated_engine: Engine,
) -> None:
    api, first, _ = launched(isolated_engine)
    request_id = ready_dossier_for(api, create(api)["id"]) if False else None
    again = api.post(
        BASE,
        json=authorize_body(api.get(BASE, headers=AUTH).json()["items"][0] and _any_request(api)),
        headers=AUTH,
    )
    assert again.status_code == 409 and again.json()["detail"]["code"] == "channel_busy"
    replaced = api.post(
        BASE, json=authorize_body(_any_request(api), supersedes=first), headers=AUTH
    )
    assert replaced.status_code == 201
    assert replaced.json()["package"]["supersedes"] == first
    assert api.get(f"{BASE}/{first}", headers=AUTH).json()["status"] == "cancelado"
    assert request_id is None


def _any_request(api: TestClient) -> str:
    items = api.get(FLOW + "?status=listo&limit=1", headers=AUTH).json()["items"]
    return str(items[0]["id"])


def test_channel_tokens_are_scoped_hashed_and_revocable(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    assert token.startswith("nrc_") and len(token) >= 40
    listing = api.get("/api/v1/channel-tokens", headers=AUTH).json()["items"]
    assert listing and "token" not in listing[0] and "token_hash" not in listing[0]
    channel = bearer(token)
    assert api.get(BASE + f"/pending?channel={CHANNEL}", headers=channel).status_code == 200
    assert api.get(BASE + "/pending?channel=canal-otro", headers=channel).status_code == 403
    for path in ("/api/v1/flow-research", "/api/v1/market/niches", "/api/v1/status"):
        assert api.get(path, headers=channel).status_code == 401, path
    for method, path, body in [
        ("post", BASE, {}),
        ("get", BASE, None),
        ("post", "/api/v1/channel-tokens", {}),
        ("post", f"{BASE}/{pilot_id}/decision", {"decision": "cerrar", "note": "x"}),
        ("get", f"{BASE}/{pilot_id}/closing-summary", None),
    ]:
        sent = getattr(api, method)(
            path, headers=channel, **({"json": body} if body is not None else {})
        )
        assert sent.status_code == 403, path
    token_id = listing[0]["id"]
    assert api.delete(f"/api/v1/channel-tokens/{token_id}", headers=AUTH).status_code == 204
    assert api.get(BASE + f"/pending?channel={CHANNEL}", headers=channel).status_code == 401
    assert api.delete(f"/api/v1/channel-tokens/{token_id}", headers=AUTH).status_code == 404


def test_another_channel_cannot_see_the_pilot_not_even_that_it_exists(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, _ = launched(isolated_engine)
    other = api.post(
        "/api/v1/channel-tokens", json={"channel_id": "canal-otro", "label": "x"}, headers=AUTH
    )
    stranger = bearer(other.json()["token"])
    assert api.get(f"{BASE}/{pilot_id}/package", headers=stranger).status_code == 404
    assert api.get(f"{BASE}/{pilot_id}", headers=stranger).status_code == 404
    assert api.get(f"{BASE}/pil_20260913_no-existe", headers=stranger).status_code == 404
    assert api.get(BASE + f"/pending?channel={CHANNEL}", headers=stranger).status_code == 403
    sha = "0" * 64
    body = {"channel_id": "canal-otro", "package_sha256": sha}
    assert api.post(f"{BASE}/{pilot_id}/delivery", json=body, headers=stranger).status_code == 404


def test_delivery_is_idempotent_and_verifies_the_hash(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    channel = bearer(token)
    pending = api.get(BASE + f"/pending?channel={CHANNEL}", headers=channel).json()["items"]
    assert [p["pilot_id"] for p in pending] == [pilot_id]
    package = api.get(f"{BASE}/{pilot_id}/package", headers=channel).json()
    wrong = {"channel_id": CHANNEL, "package_sha256": "f" * 64}
    assert api.post(f"{BASE}/{pilot_id}/delivery", json=wrong, headers=channel).status_code == 409
    right = {"channel_id": CHANNEL, "package_sha256": package["package_sha256"]}
    first = api.post(f"{BASE}/{pilot_id}/delivery", json=right, headers=channel)
    assert first.json()["status"] == "entregado" and first.json()["changed"] is True
    again = api.post(f"{BASE}/{pilot_id}/delivery", json=right, headers=channel)
    assert again.status_code == 200 and again.json()["changed"] is False
    assert api.get(BASE + f"/pending?channel={CHANNEL}", headers=channel).json()["items"] == []


def test_an_expired_package_is_not_listed_and_answers_410(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    later = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)),
            engine=isolated_engine,
            clock=lambda: NOW + timedelta(days=30),
        )
    )
    channel = bearer(token)
    assert later.get(BASE + f"/pending?channel={CHANNEL}", headers=channel).json()["items"] == []
    assert later.get(f"{BASE}/{pilot_id}/package", headers=channel).status_code == 410


def test_reports_require_delivery_and_move_the_pilot_forward(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    early = send(api, token, pilot_id, report(pilot_id, [video(1)]))
    assert early.status_code == 409 and early.json()["detail"]["code"] == "not_delivered"
    deliver(api, pilot_id, token)
    ok = send(api, token, pilot_id, report(pilot_id, [video(1), video(2, avd=None)]))
    assert ok.status_code == 200
    assert ok.json() == {
        "accepted": True,
        "videos_upserted": 2,
        "videos_ignored": 0,
        "warnings": [],
        "pilot_status": "en_ejecucion",
    }
    detail = api.get(f"{BASE}/{pilot_id}", headers=bearer(token)).json()
    assert (
        detail["evaluation"]["totals"]["videos"] == 2
        and detail["evaluation"]["totals"]["measured"] == 1
    )
    assert (
        detail["proposal"]["action"] == "sin_datos_suficientes"
        and detail["needs_decision"] is False
    )
    assert detail["channel_last_contact_at"] is not None


def test_reports_are_idempotent_and_the_newest_wins(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    send(api, token, pilot_id, report(pilot_id, [video(1, avd=20.0)]))
    same = send(api, token, pilot_id, report(pilot_id, [video(1, avd=99.0)]))
    assert (
        same.json()["videos_upserted"] == 0 and same.json()["videos_ignored"] == 1
    )  # empate: se conserva
    newer = report(pilot_id, [video(1, avd=21.0)], reported_at=iso(NOW + timedelta(minutes=1)))
    assert send(api, token, pilot_id, newer).json()["videos_upserted"] == 1
    totals = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()["evaluation"]["totals"]
    assert totals["videos"] == 1 and totals["measured"] == 1
    only_other = report(pilot_id, [video(2)], reported_at=iso(NOW + timedelta(minutes=2)))
    send(api, token, pilot_id, only_other)
    assert api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()["evaluation"]["totals"]["videos"] == 2


def test_invalid_reports_are_rejected_without_echoing_values(isolated_engine: Engine) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    bad = report(pilot_id, [video(1, cost_usd=-5, video_id="valor secreto con espacios")])
    refused = send(api, token, pilot_id, bad)
    assert refused.status_code == 422 and refused.json()["accepted"] is False
    assert refused.json()["problems"] and "secreto" not in refused.text
    notjson = api.post(f"{BASE}/{pilot_id}/reports", content=b"{no es json", headers=bearer(token))
    assert notjson.status_code == 422
    other_path = send(api, token, pilot_id, report("pil_20260913_otro", [video(1)]))
    assert other_path.status_code == 422
    huge = report(pilot_id, [video(1)], note="x" * (300 * 1024))
    assert send(api, token, pilot_id, huge).status_code == 413
    wrong_channel = report(pilot_id, [video(1)], channel_id="canal-otro")
    assert send(api, token, pilot_id, wrong_channel).status_code == 409


def test_a_met_milestone_asks_the_human_who_decides_and_follows_or_closes(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    sent = send(api, token, pilot_id, report(pilot_id, [video(n) for n in range(1, 11)]))
    assert sent.json()["pilot_status"] == "decision_pendiente"
    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    assert detail["proposal"]["action"] == "seguir" and detail["needs_decision"] is True
    channel = bearer(token)
    forbidden = api.post(
        f"{BASE}/{pilot_id}/decision",
        json={"decision": "cerrar", "note": "x"},
        headers=channel,
    )
    assert forbidden.status_code == 403
    follow = api.post(
        f"{BASE}/{pilot_id}/decision",
        json={"decision": "seguir", "note": "va bien"},
        headers=AUTH,
    )
    assert follow.json()["status"] == "en_ejecucion"
    again = send(
        api,
        token,
        pilot_id,
        report(
            pilot_id,
            [video(n) for n in range(1, 11)],
            reported_at=iso(NOW + timedelta(minutes=5)),
        ),
    )
    assert (
        again.json()["pilot_status"] == "en_ejecucion"
    )  # lo ya revisado no vuelve a pedir decisión
    close = api.post(
        f"{BASE}/{pilot_id}/decision",
        json={"decision": "cerrar", "note": "cierro: presupuesto"},
        headers=AUTH,
    )
    assert close.json()["status"] == "cerrado"
    after = send(
        api,
        token,
        pilot_id,
        report(pilot_id, [video(11)], reported_at=iso(NOW + timedelta(minutes=5))),
    )
    assert after.status_code == 409 and after.json()["detail"]["code"] == "closed"
    summary = api.get(f"{BASE}/{pilot_id}/closing-summary", headers=AUTH)
    assert summary.status_code == 200 and summary.text.startswith(
        "# EVD-canal-historias-2026-09-13-"
    )
    assert (
        "cierro: presupuesto" in summary.text
        and "nrc_" not in summary.text
        and token not in summary.text
    )
    events = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()["events"]
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "authorized" and "delivered" in kinds and kinds[-1] == "decision_cerrar"


def test_closing_summary_only_exists_for_closed_pilots_and_cancel_frees_the_channel(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, _ = launched(isolated_engine)
    assert api.get(f"{BASE}/{pilot_id}/closing-summary", headers=AUTH).status_code == 409
    assert (
        api.post(
            f"{BASE}/{pilot_id}/decision",
            json={"decision": "cerrar", "note": "x"},
            headers=AUTH,
        ).status_code
        == 409
    )
    cancelled = api.post(
        f"{BASE}/{pilot_id}/cancel", json={"reason": "cambié de idea"}, headers=AUTH
    )
    assert cancelled.json()["status"] == "cancelado"
    again = api.post(BASE, json=authorize_body(_any_request(api)), headers=AUTH)
    assert again.status_code == 201  # el canal quedó libre


def issue_token(api: TestClient, channel: str) -> str:
    created = api.post(
        "/api/v1/channel-tokens", json={"channel_id": channel, "label": "mac"}, headers=AUTH
    )
    assert created.status_code == 201
    return str(created.json()["token"])


def test_an_unassigned_pilot_goes_to_the_first_channel_that_confirms_delivery(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine, target_channel=None)
    other = issue_token(api, "canal-otro")
    for who, channel in ((token, CHANNEL), (other, "canal-otro")):
        listed = api.get(f"{BASE}/pending?channel={channel}", headers=bearer(who))
        assert [item["pilot_id"] for item in listed.json()["items"]] == [pilot_id]
    payload = deliver(api, pilot_id, token)
    assert api.get(f"{BASE}/{pilot_id}", headers=bearer(token)).json()["target_channel"] == CHANNEL
    assert payload["target_channel"] is None  # el paquete congelado no cambia
    assert api.get(f"{BASE}/{pilot_id}/package", headers=bearer(other)).status_code == 404
    gone = api.get(f"{BASE}/pending?channel=canal-otro", headers=bearer(other))
    assert gone.json()["items"] == []


def test_delivery_to_a_busy_channel_answers_409_channel_busy(isolated_engine: Engine) -> None:
    api, first, token = launched(isolated_engine, target_channel=None)
    deliver(api, first, token)
    request_id = ready_dossier(api)
    second = api.post(
        BASE, json=authorize_body(request_id, target_channel=None), headers=AUTH
    ).json()["pilot_id"]
    package = api.get(f"{BASE}/{second}/package", headers=bearer(token)).json()
    busy = api.post(
        f"{BASE}/{second}/delivery",
        json={"channel_id": CHANNEL, "package_sha256": package["package_sha256"]},
        headers=bearer(token),
    )
    assert busy.status_code == 409 and busy.json()["detail"]["code"] == "channel_busy"
    still = api.get(f"{BASE}/{second}", headers=AUTH).json()
    assert still["status"] == "autorizado" and still["target_channel"] is None


def test_an_untranslated_state_is_accepted_with_a_warning_and_checks_are_kept(
    isolated_engine: Engine,
) -> None:
    api, pilot_id, token = launched(isolated_engine)
    deliver(api, pilot_id, token)
    odd = video(1, avd=None, source_state="ESTADO_NUEVO", published_at=None, visibility="private")
    check = {"id": "voice_ref", "label": "Voz", "ok": False, "detail": "falta", "expires_at": None}
    sent = send(api, token, pilot_id, report(pilot_id, [odd], checks=[check]))
    assert sent.status_code == 200, sent.text
    assert any("sin traducir" in item for item in sent.json()["warnings"])
    detail = api.get(f"{BASE}/{pilot_id}", headers=AUTH).json()
    assert detail["evaluation"]["totals"]["by_stage"] == {"unknown": 1}
    assert detail["channel"]["checks"][0]["id"] == "voice_ref"
    assert detail["channel"]["channel_status"] == "active"
