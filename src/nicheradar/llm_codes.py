"""Agrupa los códigos `llm_http_<estado>[_<tipo>]` del adaptador en categorías de texto fijo."""

import re

_HTTP = re.compile(r"llm_http_([0-9]{3})(?:_([a-z_]{1,40}))?", re.ASCII)
_BY_TYPE = {
    "invalid_request_error": "llm_rejected",
    "not_found_error": "llm_rejected",
    "request_too_large": "llm_rejected",
    "authentication_error": "llm_auth",
    "permission_error": "llm_permission",
    "billing_error": "llm_permission",
    "rate_limit_error": "llm_rate_limited",
}
_BY_STATUS = {
    400: "llm_rejected",
    404: "llm_rejected",
    413: "llm_rejected",
    422: "llm_rejected",
    401: "llm_auth",
    402: "llm_permission",
    403: "llm_permission",
    429: "llm_rate_limited",
}


def normalize_llm_code(code: str) -> str:
    """Categoría de un `llm_http_*` bien formado; cualquier otro código vuelve igual."""
    match = _HTTP.fullmatch(code)
    if match is None:
        return code
    kind = match.group(2)
    if kind in _BY_TYPE:
        return _BY_TYPE[kind]
    return _BY_STATUS.get(int(match.group(1)), "llm_failed")
