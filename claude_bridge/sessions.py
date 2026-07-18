"""Short-lived, opaque dashboard sessions.

The browser never stores the bridge's master bearer token.  It exchanges the
token once for a random HttpOnly cookie whose SHA-256 digest and expiry live in
memory.  Restarting the bridge intentionally invalidates all browser sessions.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time


class SessionStore:
    def __init__(self, ttl_seconds: int = 8 * 60 * 60) -> None:
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[bytes, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        expires = time.monotonic() + self.ttl_seconds
        with self._lock:
            self._sessions[self._digest(token)] = expires
            self._cleanup_locked(time.monotonic())
        return token

    def validate(self, token: str) -> bool:
        if not token:
            return False
        now = time.monotonic()
        digest = self._digest(token)
        with self._lock:
            expiry = self._sessions.get(digest)
            if expiry is None:
                return False
            if expiry <= now:
                self._sessions.pop(digest, None)
                return False
            return True

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            return self._sessions.pop(self._digest(token), None) is not None

    def _cleanup_locked(self, now: float) -> int:
        expired = [digest for digest, expiry in self._sessions.items() if expiry <= now]
        for digest in expired:
            self._sessions.pop(digest, None)
        return len(expired)

    def cleanup(self) -> int:
        with self._lock:
            return self._cleanup_locked(time.monotonic())
