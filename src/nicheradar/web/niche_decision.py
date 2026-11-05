# src/nicheradar/web/niche_decision.py
"""Niche decision form (M19): the safe return target and the note, validated locally."""

import unicodedata
from urllib.parse import parse_qsl, quote, urlencode

NOTE_MAX = 1000
NOTE_ERROR = f"La nota admite hasta {NOTE_MAX} caracteres."
NOTE_CHARS = "La nota contiene caracteres no válidos."
LABEL_MAX = 140
FORMATS = ("long", "shorts")
LIST_KEYS = {"formato", "alta", "ingresos", "orden", "aviso"}
ORDERS = ("opportunity", "automation")
Target = tuple[str, list[tuple[str, str]]]


def valid_label(label: str) -> bool:
    return (
        1 <= len(label) <= LABEL_MAX
        and bool(label.strip())
        and label not in (".", "..")
        and not any(unicodedata.category(c) == "Cc" for c in label)
    )


def _plain(text: str) -> bool:
    """Printable ASCII with no space and no backslash: nothing a redirect could be bent with."""
    return all(33 <= ord(c) < 127 and c != "\\" for c in text)


def safe_target(volver: str) -> Target | None:
    """('list'|'detail', query pairs without `aviso`) for a whitelisted `volver`, else None."""
    if not _plain(volver):
        return None
    path, _, query = volver.partition("?")
    if path not in ("/nichos", "/nichos/ver"):
        return None
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=bool(query))
    except ValueError:
        return None
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        return None
    values = dict(pairs)
    if path == "/nichos/ver":
        if not set(keys) <= {"etiqueta", "formato", "aviso"}:
            return None
        if not valid_label(values.get("etiqueta", "")) or values.get("formato") not in FORMATS:
            return None
        kind = "detail"
    else:
        if not set(keys) <= LIST_KEYS:
            return None
        if values.get("formato", "long") not in FORMATS:
            return None
        if values.get("alta", "1") != "1" or values.get("ingresos", "1") != "1":
            return None
        if values.get("orden", "opportunity") not in ORDERS:
            return None
        kind = "list"
    return kind, [(k, v) for k, v in pairs if k != "aviso"]


def target_url(kind: str, pairs: list[tuple[str, str]], aviso: str | None = None) -> str:
    path = "/nichos/ver" if kind == "detail" else "/nichos"
    items = [*pairs, *([("aviso", aviso)] if aviso else [])]
    return path + ("?" + urlencode(items, quote_via=quote) if items else "")


def detail_url(label: str, fmt: str) -> str:
    return target_url("detail", [("etiqueta", label), ("formato", fmt)])


def note_problem(value: str) -> str | None:
    """The fixed message saying why the note is refused, or None when it is acceptable."""
    note = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(note) > NOTE_MAX:
        return NOTE_ERROR
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in note):
        return NOTE_CHARS
    return None


def validate_note(value: str) -> str | None:
    """The note as it will be sent ('' when empty), or None when it is not acceptable."""
    if note_problem(value):
        return None
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()
