# src/nicheradar/web/security.py
"""Signed session cookie, CSRF token and login rate limit for the mobile web."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from nicheradar.config import Settings

SESSION_COOKIE = "nr_session"
SESSION_SECONDS = 12 * 3600
LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class Session:
    expires: int
    nonce: str


class SessionSigner:
    def __init__(self, key: bytes, clock: Callable[[], float] = time.time) -> None:
        self._key = key
        self._clock = clock

    @classmethod
    def from_settings(
        cls, config: Settings, clock: Callable[[], float] = time.time
    ) -> "SessionSigner | None":
        if config.service_token is None:
            return None
        key = hmac.new(
            config.service_token.get_secret_value().encode(),
            b"nicheradar-web-session",
            hashlib.sha256,
        ).digest()
        return cls(key, clock)

    def _mac(self, message: str) -> str:
        return hmac.new(self._key, message.encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        payload = f"{int(self._clock()) + SESSION_SECONDS}.{secrets.token_urlsafe(16)}"
        return f"{payload}.{self._mac(payload)}"

    def read(self, token: str | None) -> Session | None:
        if not token:
            return None
        payload, _, mac = token.rpartition(".")
        if not payload or not hmac.compare_digest(mac.encode(), self._mac(payload).encode()):
            return None
        expires, _, nonce = payload.partition(".")
        if not expires.isdigit() or not nonce or int(expires) <= self._clock():
            return None
        return Session(int(expires), nonce)

    def csrf(self, session: Session) -> str:
        return self._mac(f"csrf:{session.nonce}")

    def csrf_valid(self, session: Session, value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(
            (value or "").encode(), self.csrf(session).encode()
        )


class LoginLimiter:
    """Counts failed logins in a sliding window. One key is enough: this is a one-owner app."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        attempts: int = LOGIN_ATTEMPTS,
        window: int = LOGIN_WINDOW_SECONDS,
    ) -> None:
        self._clock = clock
        self._attempts = attempts
        self._window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] <= self._clock() - self._window:
            failures.popleft()
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self._attempts

    def fail(self, key: str) -> None:
        self._prune(key).append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
