"""Cierra la reserva de una llamada al modelo que falló y dice por qué, sin texto del proveedor."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine

from nicheradar.integrations.contracts import ProviderError
from nicheradar.services.budget import settle
from nicheradar.services.requests import record_not_sent


def settle_failed_call(
    engine: Engine, request_id: UUID, profile_id: UUID, error: BaseException, now: datetime
) -> str:
    """Liquida la reserva y devuelve el motivo estable.

    Un rechazo que el adaptador certifica como no procesado (`not_sent`: HTTP 400, 401, 403,
    404, 413 o 422) libera la reserva con el mecanismo existente `record_not_sent`. Todo lo
    demás (timeouts, cancelación, 429, 5xx, respuestas ambiguas) sigue como `unknown_charge`.
    El motivo es el código cerrado `llm_http_*` del adaptador o `llm_failed`.
    """
    with engine.begin() as connection:
        if isinstance(error, ProviderError) and error.not_sent:
            record_not_sent(connection, request_id, profile_id, now)
        else:
            settle(connection, request_id, profile_id, None, now)
    if isinstance(error, ProviderError) and error.code.startswith("llm_http_"):
        return error.code
    return "llm_failed"
