# tests/test_web_pilots_view.py
from datetime import UTC, datetime

import pytest

from nicheradar.web.pilots_view import (
    PILOT_RE,
    blockers,
    dates,
    list_view,
    next_action,
    parse_filter,
    progress_text,
)
from tests.web_helpers import pilot_detail, pilot_item

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _channel(*checks: object) -> dict[str, object]:
    return {
        "reported_at": "2026-11-03T11:00:00Z",
        "channel_status": "active",
        "note": None,
        "checks": list(checks),
    }


def _check(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "youtube_oauth",
        "label": "YouTube",
        "ok": True,
        "detail": None,
        "expires_at": None,
    }
    return base | over


def _totals(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "videos": 0,
        "published": 0,
        "measured": 0,
        "by_stage": {},
        "spent_usd": 0,
        "equivalent_usd": 0,
        "machine_minutes": 0,
        "machine_minutes_complete": True,
    }
    return base | over


def test_a_failed_check_becomes_a_blocker_with_its_detail() -> None:
    item = pilot_item(
        channel={
            "reported_at": "2026-11-03T11:00:00Z",
            "channel_status": "active",
            "note": None,
            "checks": [
                {
                    "id": "visual_assets",
                    "label": "Visuales del nicho",
                    "ok": False,
                    "detail": "Faltan loops",
                    "expires_at": None,
                }
            ],
        }
    )
    texts = [b["text"] for b in blockers(item, NOW)]
    assert "Falta: Visuales del nicho. Faltan loops" in texts


def test_a_failed_check_without_detail_has_no_trailing_dot() -> None:
    item = pilot_item(channel=_channel(_check(label="Visuales", ok=False)))
    assert blockers(item, NOW) == [{"text": "Falta: Visuales", "kind": "falta"}]


def test_a_check_expiring_within_seven_days_is_a_blocker_and_a_later_one_is_not() -> None:
    soon = pilot_item(channel=_channel(_check(expires_at="2026-11-08T00:00:00Z")))
    later = pilot_item(channel=_channel(_check(expires_at="2026-12-08T00:00:00Z")))
    assert any("vence el 8 nov" in b["text"] for b in blockers(soon, NOW))
    assert not any("vence" in b["text"] for b in blockers(later, NOW))
    expired = pilot_item(channel=_channel(_check(expires_at="2026-11-01T00:00:00Z")))
    assert any("venció" in b["text"] for b in blockers(expired, NOW))


def test_expiry_dates_use_the_given_timezone() -> None:
    soon = pilot_item(channel=_channel(_check(expires_at="2026-11-08T00:00:00Z")))
    assert blockers(soon, NOW, "America/Lima") == [
        {"text": "YouTube vence el 7 nov", "kind": "vence"}
    ]


def test_an_expiry_exactly_at_the_seven_day_edge_counts_and_a_naive_date_is_utc() -> None:
    edge = pilot_item(channel=_channel(_check(expires_at="2026-11-10T12:00:00")))
    assert [b["text"] for b in blockers(edge, NOW)] == ["YouTube vence el 10 nov"]
    after = pilot_item(channel=_channel(_check(expires_at="2026-11-10T12:00:01")))
    assert blockers(after, NOW) == []


def test_stale_contact_unknown_videos_and_pending_decision_are_blockers() -> None:
    item = pilot_item(
        status="en_ejecucion",
        channel_last_contact_at="2026-11-01T00:00:00Z",
        needs_decision=True,
        totals={
            "videos": 3,
            "published": 3,
            "measured": 1,
            "by_stage": {"unknown": 1},
            "spent_usd": 1,
            "equivalent_usd": 2,
            "machine_minutes": 10,
            "machine_minutes_complete": True,
        },
    )
    texts = " | ".join(b["text"] for b in blockers(item, NOW))
    assert "sin contacto" in texts and "1 video con estado desconocido" in texts
    assert "decisión pendiente" in texts


def test_blockers_come_in_the_documented_order_with_exact_texts() -> None:
    item = pilot_item(
        status="en_ejecucion",
        channel=_channel(
            _check(label="A", ok=False, detail="d"),
            _check(label="B", expires_at="2026-11-05T00:00:00Z"),
        ),
        channel_last_contact_at="2026-11-01T11:00:00Z",
        needs_decision=True,
        totals=_totals(by_stage={"unknown": 2}),
    )
    assert blockers(item, NOW) == [
        {"text": "Falta: A. d", "kind": "falta"},
        {"text": "B vence el 5 nov", "kind": "vence"},
        {"text": "Tu Mac está sin contacto hace 49 h", "kind": "contacto"},
        {"text": "2 videos con estado desconocido", "kind": "desconocido"},
        {"text": "Hay una decisión pendiente", "kind": "decision"},
    ]


def test_contact_staleness_only_applies_to_delivered_or_running_pilots_after_48_hours() -> None:
    fresh = pilot_item(status="en_ejecucion", channel_last_contact_at="2026-11-01T12:00:00Z")
    assert blockers(fresh, NOW) == []  # exactly 48 h is not "more than"
    never = pilot_item(status="en_ejecucion", channel_last_contact_at=None)
    assert blockers(never, NOW) == []
    authorized = pilot_item(status="autorizado", channel_last_contact_at="2026-10-01T00:00:00Z")
    assert not any("contacto" in b["text"] for b in blockers(authorized, NOW))
    future = pilot_item(status="entregado", channel_last_contact_at="2026-12-01T00:00:00Z")
    assert blockers(future, NOW) == []


def test_a_closed_pilot_has_no_blockers_and_a_clean_one_has_none() -> None:
    assert blockers(pilot_item(status="cerrado", needs_decision=True), NOW) == []
    assert blockers(pilot_item(status="cancelado", needs_decision=True), NOW) == []
    assert blockers(pilot_item(), NOW) == []


def test_the_authorization_validity_is_a_blocker_only_for_undelivered_pilots() -> None:
    near = pilot_item(status="autorizado", delivered_at=None, valid_until="2026-11-05T00:00:00Z")
    assert any("vigencia" in b["text"] for b in blockers(near, NOW))
    delivered = pilot_item(status="entregado", valid_until="2026-11-05T00:00:00Z")
    assert not any("vigencia" in b["text"] for b in blockers(delivered, NOW))
    far = pilot_item(status="autorizado", delivered_at=None, valid_until="2026-11-16T00:00:00Z")
    assert blockers(far, NOW) == []
    assert blockers(near, NOW) == [
        {
            "text": "La vigencia vence el 5 nov si tu Mac no baja el paquete",
            "kind": "vigencia",
        }
    ]


@pytest.mark.parametrize(
    "item",
    [
        {},
        {"status": None, "channel": "x", "totals": "x", "needs_decision": "yes"},
        {"status": ["autorizado"], "channel": [], "totals": []},
        {"status": "en_ejecucion", "channel": {"checks": "nope"}, "totals": {"by_stage": []}},
        {"status": "en_ejecucion", "channel": {"checks": [1, None, "x", ["a"]]}},
        {
            "status": "autorizado",
            "valid_until": 5,
            "delivered_at": {},
            "channel_last_contact_at": [],
        },
        {"status": "entregado", "channel_last_contact_at": "garbage"},
        {"status": "autorizado", "channel": _channel(_check(expires_at="garbage", ok="no"))},
        {"status": "autorizado", "channel": _channel(_check(label=None, ok=False, detail=5))},
        {"status": "entregado", "totals": {"by_stage": {"unknown": float("nan")}}},
        {"status": "entregado", "totals": {"by_stage": {"unknown": float("inf")}}},
        {"status": "entregado", "totals": {"by_stage": {"unknown": "3"}}},
        {"status": "entregado", "totals": {"by_stage": {"unknown": True}}},
        {"status": "autorizado", "valid_until": "0001-01-01T00:00:00Z"},
        {"status": "autorizado", "valid_until": "9999-12-31T23:59:59Z"},
    ],
)
def test_the_derivations_never_raise_on_malformed_items(item: object) -> None:
    assert isinstance(item, dict)
    for result in blockers(item, NOW):
        assert isinstance(result["text"], str) and isinstance(result["kind"], str)
    action = next_action(item)
    assert action is None or isinstance(action, str)
    assert isinstance(progress_text(item), str)


def test_a_check_with_an_unparsable_expiry_is_ignored_and_a_non_true_ok_is_not_a_failure() -> None:
    item = pilot_item(channel=_channel(_check(expires_at="garbage"), _check(ok=None, label="X")))
    assert blockers(item, NOW) == []


def test_non_finite_or_non_numeric_unknown_counts_are_ignored() -> None:
    for value in (float("nan"), float("inf"), "2", True, 0, -1):
        item = pilot_item(totals=_totals(by_stage={"unknown": value}))
        assert blockers(item, NOW) == []


def test_a_malformed_channel_is_ignored_but_other_blockers_still_show() -> None:
    item = pilot_item(channel="boom", needs_decision=True)
    assert [b["kind"] for b in blockers(item, NOW)] == ["decision"]


def test_hostile_label_and_detail_stay_plain_text_in_the_blocker() -> None:
    hostile = "<script>alert(1)</script>"
    item = pilot_item(channel=_channel(_check(label=hostile, ok=False, detail=hostile)))
    assert blockers(item, NOW)[0]["text"] == f"Falta: {hostile}. {hostile}"


def test_next_action_only_states_what_can_be_asserted() -> None:
    assert next_action(pilot_item(needs_decision=True)) == "Decide si sigue o cierra"
    waiting = pilot_item(totals=_totals(videos=2, by_stage={"awaiting_human": 2}))
    assert next_action(waiting) == "2 videos esperan tu veredicto en el canal"
    assert next_action(pilot_item(status="autorizado", delivered_at=None)) == (
        "Falta que tu Mac baje el paquete"
    )
    assert next_action(pilot_item(status="cerrado")) is None


def test_next_action_uses_the_singular_and_gives_way_to_a_pending_decision() -> None:
    one = pilot_item(totals=_totals(videos=1, by_stage={"awaiting_human": 1}))
    assert next_action(one) == "1 video espera tu veredicto en el canal"
    both = pilot_item(needs_decision=True, totals=_totals(by_stage={"awaiting_human": 1}))
    assert next_action(both) == "Decide si sigue o cierra"
    assert next_action(pilot_item(status="cancelado", needs_decision=True)) is None
    assert next_action(pilot_item(status="en_ejecucion")) is None


def test_the_singular_for_one_unknown_video_and_the_plural_for_several() -> None:
    one = pilot_item(totals=_totals(by_stage={"unknown": 1}))
    many = pilot_item(totals=_totals(by_stage={"unknown": 4}))
    assert blockers(one, NOW)[0]["text"] == "1 video con estado desconocido"
    assert blockers(many, NOW)[0]["text"] == "4 videos con estado desconocido"


def test_progress_text_uses_the_package_cap_when_present() -> None:
    item = pilot_item(totals=_totals(videos=3, published=3, measured=1))
    assert progress_text(item, max_videos=10) == "3 de 10 videos"
    assert progress_text(item, max_videos=None) == "3 videos"
    assert progress_text(item) == "3 videos"


def test_progress_text_singular_zero_and_garbage() -> None:
    assert progress_text(pilot_item(totals=_totals(published=1))) == "1 video"
    assert progress_text(pilot_item(totals=_totals(published=0))) == "0 videos"
    assert progress_text(pilot_item(totals=_totals(published=1)), max_videos=10) == "1 de 10 videos"
    assert progress_text(pilot_item(totals=_totals(published=float("nan")))) == "0 videos"
    assert progress_text({"totals": None}) == "0 videos"
    assert progress_text(pilot_item(totals=_totals(published=2)), max_videos=True) == "2 videos"


def test_dates_are_tentative_and_only_present_with_a_basis() -> None:
    detail = pilot_detail()
    rows = dates(detail, NOW)
    assert all("tentativa" in r["label"] or r["label"] in ("Autorizado", "Entregado") for r in rows)
    assert any(r["label"].startswith("Vigencia") for r in rows)
    bare = pilot_detail(delivered_at=None, valid_until=None)
    assert dates(bare, NOW) == [r for r in dates(bare, NOW) if r["label"] == "Autorizado"]


def test_dates_rows_have_exact_values_in_the_given_timezone() -> None:
    rows = dates(pilot_detail(), NOW, "America/Lima")
    by_label = {r["label"]: r for r in rows}
    assert by_label["Autorizado"]["value"] == "1 nov"  # 2026-11-02T03:00Z is the 1st in Lima
    assert by_label["Entregado"]["value"] == "3 nov"
    assert by_label["Vigencia (tentativa)"]["value"] == "15 nov"


def test_the_preparation_deadline_exists_only_when_the_package_carries_the_days() -> None:
    assert not any("Plazo" in r["label"] for r in dates(pilot_detail(), NOW))
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    within = dates(pilot_detail(package=package | {"preparation_days": 10}), NOW)
    row = next(r for r in within if r["label"] == "Plazo de preparación (tentativa)")
    assert row["value"] == "13 nov" and row["note"] == "dentro del plazo"
    old = pilot_detail(
        package=package | {"preparation_days": 5}, delivered_at="2026-10-20T10:00:00Z"
    )
    row = next(r for r in dates(old, NOW) if r["label"] == "Plazo de preparación (tentativa)")
    assert row["value"] == "25 oct" and row["note"] == "vencido"
    for junk in (0, -3, "10", None, True, float("nan"), 10**9):
        rows = dates(pilot_detail(package=package | {"preparation_days": junk}), NOW)
        assert not any("Plazo" in r["label"] for r in rows)


def test_review_milestones_come_from_the_stop_rules_and_video_ones_have_no_date() -> None:
    rules = [
        {"id": "a", "milestone": {"kind": "week", "value": 2}},
        {"id": "b", "milestone": {"kind": "month", "value": 1}},
        {"id": "c", "milestone": {"kind": "video", "value": 5}},
        {"id": "d", "milestone": {"kind": "week", "value": 2}},
    ]
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    rows = dates(pilot_detail(package=package | {"stop_rules": rules}), NOW)
    reviews = [r for r in rows if r["label"] == "Revisión (tentativa)"]
    assert [(r["value"], r["note"]) for r in reviews] == [
        ("16 nov", "semana 2"),
        ("2 dic", "mes 1"),
        (None, "al llegar al video 5"),
    ]


def test_dates_never_raise_on_malformed_details() -> None:
    package = dict(pilot_detail()["package"])  # type: ignore[call-overload]
    bad_rules: list[object] = [
        None,
        "x",
        {},
        {"milestone": None},
        {"milestone": "week:2"},
        {"milestone": {"kind": "week", "value": "2"}},
        {"milestone": {"kind": "week", "value": -1}},
        {"milestone": {"kind": "week", "value": 10**12}},
        {"milestone": {"kind": "month", "value": float("nan")}},
        {"milestone": {"kind": "decade", "value": 1}},
    ]
    for detail in (
        {},
        {"authorized_at": 5, "delivered_at": [], "valid_until": {}, "package": "x"},
        {"authorized_at": "garbage", "package": None},
        pilot_detail(package=package | {"stop_rules": bad_rules}),
        pilot_detail(package=package | {"stop_rules": "nope"}),
        pilot_detail(authorized_at="0001-01-01T00:00:00Z"),
        pilot_detail(authorized_at="9999-12-31T00:00:00Z"),
    ):
        for row in dates(detail, NOW):
            assert isinstance(row["label"], str)


def test_a_naive_authorization_date_is_read_as_utc() -> None:
    rows = dates({"authorized_at": "2026-11-05T00:00:00"}, NOW)
    assert rows == [{"label": "Autorizado", "value": "5 nov", "note": None}]


def test_pilot_re_accepts_real_ids_and_rejects_a_trailing_newline_with_fullmatch() -> None:
    assert PILOT_RE.fullmatch("pil_20261102_historia")
    assert PILOT_RE.fullmatch("pil_20261102_a-b-c")
    assert PILOT_RE.fullmatch("pil_20261102_" + "a" * 40)
    assert PILOT_RE.fullmatch("pil_20261102_historia\n") is None
    for bad in ("", "x&y=1", "pil_2026_a", "pil_20261102_", "PIL_20261102_a", "pil_20261102_a/b"):
        assert PILOT_RE.fullmatch(bad) is None
    # the API contract has no underscore in the slug, no Unicode digits and at most 40 characters
    for bad in ("pil_20261102_a_b", "pil_٢٠٢٦١١٠٢_x", "pil_20261102_" + "a" * 41):
        assert PILOT_RE.fullmatch(bad) is None


def test_parse_filter_accepts_only_the_four_keys() -> None:
    for key in ("todos", "activos", "bloqueo", "cerrados"):
        assert parse_filter({"filtro": key}) == key
    for junk in ("", "TODOS", "x", "activos&x", "todos\n"):
        assert parse_filter({"filtro": junk}) == "todos"
    assert parse_filter({}) == "todos"


def _mixed() -> list[dict[str, object]]:
    return [
        pilot_item("pil_20261102_a", niche_label="a", status="en_ejecucion"),
        pilot_item(
            "pil_20261102_b", niche_label="b", status="decision_pendiente", needs_decision=True
        ),
        pilot_item("pil_20261102_c", niche_label="c", status="cerrado"),
        pilot_item("pil_20261102_d", niche_label="d", status="cancelado", needs_decision=True),
        pilot_item("pil_20261102_e", niche_label="e", status="rarisimo"),
    ]


def test_list_view_filters_and_counts_over_the_full_list() -> None:
    items = _mixed()
    for key, expected in (
        ("todos", ["a", "b", "c", "d", "e"]),
        ("activos", ["a", "b", "e"]),
        ("bloqueo", ["b"]),
        ("cerrados", ["c", "d"]),
    ):
        view = list_view(items, key, NOW, "UTC")
        assert [c["niche_label"] for c in view["cards"]] == expected
        assert view["counts"] == {"todos": 5, "activos": 3, "bloqueo": 1, "cerrados": 2}
        assert view["filter"] == key


def test_list_view_cards_carry_the_derived_fields() -> None:
    view = list_view(
        [
            pilot_item(
                status="entregado",
                needs_decision=True,
                totals=_totals(published=2, by_stage={"awaiting_human": 1}),
            )
        ],
        "todos",
        NOW,
        "UTC",
    )
    card = view["cards"][0]
    assert card["pilot_id"] == "pil_20261102_historia"
    assert card["href"] == "/pilotos/pil_20261102_historia"
    assert (card["status_text"], card["status_kind"]) == ("Preparando", "amber")
    assert card["format_text"] == "Largo"
    assert card["channel_text"] == "canal-historias"
    assert card["next_action"] == "Decide si sigue o cierra"
    assert card["progress"] == "2 videos"
    assert card["budget_cap"] is None
    assert [b["kind"] for b in card["blockers"]] == ["decision"]


@pytest.mark.parametrize(
    ("status", "text", "kind"),
    [
        ("autorizado", "Autorizado", "neutral"),
        ("entregado", "Preparando", "amber"),
        ("en_ejecucion", "En ejecución", "green"),
        ("decision_pendiente", "Decisión pendiente", "rose"),
        ("cerrado", "Cerrado", "neutral"),
        ("cancelado", "Cancelado", "neutral"),
        ("marciano", "marciano", "neutral"),
        (None, "Estado desconocido", "neutral"),
        (["x"], "Estado desconocido", "neutral"),
    ],
)
def test_status_chips_and_unknown_statuses(status: object, text: str, kind: str) -> None:
    card = list_view([pilot_item(status=status)], "todos", NOW, "UTC")["cards"][0]
    assert (card["status_text"], card["status_kind"]) == (text, kind)


def test_the_pilot_id_and_href_exist_only_for_valid_ids() -> None:
    for bad in ("pil_20261102_a\n", "", "x&y=1", None, 5):
        card = list_view([pilot_item(bad)], "todos", NOW, "UTC")["cards"][0]  # type: ignore[arg-type]
        assert card["pilot_id"] is None and card["href"] is None


def test_the_channel_falls_back_to_to_be_defined() -> None:
    for target in (None, "", 5, ["x"]):
        card = list_view([pilot_item(target_channel=target)], "todos", NOW, "UTC")["cards"][0]
        assert card["channel_text"] == "canal por definir"


def test_the_contact_line_uses_the_most_recent_contact_of_active_pilots() -> None:
    def contact(*moments: object, status: str = "en_ejecucion") -> str:
        items = [
            pilot_item(f"pil_20261102_p{i}", status=status, channel_last_contact_at=m)
            for i, m in enumerate(moments)
        ]
        return str(list_view(items, "todos", NOW, "UTC")["contact_text"])

    assert contact("2026-11-03T06:00:00Z", "2026-10-01T00:00:00Z") == (
        "Tu Mac: último contacto hace 6 h"
    )
    assert contact("2026-11-03T11:15:00Z") == "Tu Mac: último contacto hace 45 min"
    assert contact("2026-11-03T11:59:30Z") == "Tu Mac: último contacto hace menos de 1 min"
    assert contact("2026-11-03T11:00:00Z") == "Tu Mac: último contacto hace 1 h"
    assert contact("2026-10-30T12:00:00Z") == "Tu Mac: último contacto hace 4 días"
    assert contact("2026-10-31T12:00:00Z") == "Tu Mac: último contacto hace 3 días"
    assert contact("2026-11-02T11:00:00Z") == "Tu Mac: último contacto hace 25 h"
    assert contact("2026-11-02T12:00:00") == "Tu Mac: último contacto hace 24 h"  # naive = UTC
    assert contact("2026-11-03T12:00:00Z", "2026-10-01T00:00:00Z") == (
        "Tu Mac: último contacto hace menos de 1 min"
    )
    assert contact(None) == "Tu Mac: sin contacto todavía"
    assert contact("garbage", 5, []) == "Tu Mac: sin contacto todavía"
    assert contact() == "Tu Mac: sin contacto todavía"
    assert contact("2026-11-03T11:00:00Z", status="cerrado") == "Tu Mac: sin contacto todavía"


def test_a_future_contact_reads_as_just_now_and_never_negative() -> None:
    items = [pilot_item(status="en_ejecucion", channel_last_contact_at="2026-12-25T00:00:00Z")]
    text = str(list_view(items, "todos", NOW, "UTC")["contact_text"])
    assert text == "Tu Mac: último contacto hace menos de 1 min"


def test_list_view_survives_non_list_items_non_dict_elements_and_bare_dicts() -> None:
    assert list_view([], "todos", NOW, "UTC")["cards"] == []
    view = list_view([None, 5, "x", {}, {"status": {}}], "todos", NOW, "UTC")
    assert len(view["cards"]) == 2
    assert view["counts"]["todos"] == 2
    assert view["cards"][0]["niche_label"] == "—"
    assert list_view(None, "todos", NOW, "UTC")["cards"] == []  # type: ignore[arg-type]
    assert list_view([pilot_item()], "junk", NOW, "UTC")["filter"] == "todos"


def test_a_past_validity_of_an_undelivered_pilot_reads_in_the_past_tense() -> None:
    past = pilot_item(status="autorizado", delivered_at=None, valid_until="2026-11-01T00:00:00Z")
    found = blockers(past, NOW)
    assert [b["kind"] for b in found] == ["vigencia"]
    assert found[0]["text"].startswith("La vigencia venció el 1 nov")
    assert "vence" not in found[0]["text"]
    ahead = pilot_item(status="autorizado", delivered_at=None, valid_until="2026-11-05T00:00:00Z")
    assert blockers(ahead, NOW)[0]["text"].startswith("La vigencia vence el 5 nov")
