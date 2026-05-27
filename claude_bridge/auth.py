"""Optional Bearer-token authentication for Claude Bridge.

When `CLAUDE_BRIDGE_AUTH_TOKEN` is set (or `--auth-token <value>` passed on the
CLI), every HTTP endpoint except `/status` requires an
`Authorization: Bearer <token>` header. With no token configured, the middleware
is a no-op and the bridge behaves exactly as it did before — this is the
opt-in stance from CONTRIBUTING.md.

The stdio transport is not affected (no network surface).
"""

from __future__ import annotations

import hmac
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# Routes that require the Bearer token when auth is enabled. Everything else
# (including /status and the static dashboard mount) is public — the dashboard
# JS prompts for the token client-side and attaches it to /api/* calls.
PROTECTED_PREFIXES = ("/api/", "/messages/")
PROTECTED_PATHS = frozenset({"/sse"})


def _is_protected(path: str) -> bool:
    if path in PROTECTED_PATHS:
        return True
    return any(path.startswith(p) for p in PROTECTED_PREFIXES)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Enforce `Authorization: Bearer <token>` on protected routes only.

    The token is read from `token_getter()` at request time (not at middleware
    construction), so the bridge can be reconfigured without rebuilding the
    Starlette app — and tests can monkeypatch the source variable freely.
    If `token_getter()` returns a falsy value, the middleware is a no-op.
    """

    def __init__(self, app, token_getter: Callable[[], str | None]):
        super().__init__(app)
        self._get_token = token_getter

    async def dispatch(self, request: Request, call_next):
        token = self._get_token()
        if not token:
            return await call_next(request)
        if not _is_protected(request.url.path):
            return await call_next(request)
        expected = f"Bearer {token}".encode()
        actual = request.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(actual, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
