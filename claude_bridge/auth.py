"""Security middleware for Claude Bridge.

Two pieces:

- `BearerAuthMiddleware`: when `CLAUDE_BRIDGE_AUTH_TOKEN` is set (or
  `--auth-token <value>` passed on the CLI), every HTTP endpoint except
  `/status` and the static dashboard requires `Authorization: Bearer <token>`.
  Off when no token is configured.
- `RequestSizeLimitMiddleware`: rejects POSTs whose `Content-Length` exceeds
  a cap before reading the body. Defends the SQLite store against the obvious
  fill-the-disk DoS.

The stdio transport is not affected by either middleware (no network surface).
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
PROTECTED_PREFIXES = ("/api/", "/messages/", "/events/")
PROTECTED_PATHS = frozenset({"/sse"})

# Paths that accept the token via `?token=` query param in addition to the
# Authorization header. Needed for the EventSource API, which can't send
# custom headers — the dashboard's only way to authenticate against
# `/events/channel/...`. Keep this set deliberately small.
QUERY_TOKEN_PREFIXES = ("/events/",)


def _is_protected(path: str) -> bool:
    if path in PROTECTED_PATHS:
        return True
    return any(path.startswith(p) for p in PROTECTED_PREFIXES)


def _accepts_query_token(path: str) -> bool:
    return any(path.startswith(p) for p in QUERY_TOKEN_PREFIXES)


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
        path = request.url.path
        if not _is_protected(path):
            return await call_next(request)
        # RFC 7235: auth-scheme is case-insensitive. Parse "<scheme> <credential>"
        # and compare only the credential half with constant-time compare to
        # avoid leaking the expected token's length via the prefix-equality check.
        header = request.headers.get("Authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() == "bearer" and credential:
            if hmac.compare_digest(credential.encode(), token.encode()):
                return await call_next(request)
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        # No (or malformed) Authorization header. The EventSource API can't
        # send headers, so for `/events/...` only we accept `?token=` as a
        # fallback. Documented caveat: tokens leak into access logs — operators
        # serving this behind a reverse proxy should scrub them.
        if _accepts_query_token(path):
            query_token = request.query_params.get("token", "")
            if query_token and hmac.compare_digest(query_token.encode(), token.encode()):
                return await call_next(request)
        return JSONResponse({"error": "unauthorized"}, status_code=401)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject POST/PUT/PATCH whose Content-Length exceeds `max_bytes`.

    Chunked requests without Content-Length pass through this check — defense
    against those happens at the handler level (the JSON-content cap in
    `api_send`). This is the cheap rejection of the common case.
    """

    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self._max = max_bytes

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl:
                try:
                    length = int(cl)
                except ValueError:
                    return JSONResponse(
                        {"error": "invalid content-length"}, status_code=400
                    )
                if length > self._max:
                    return JSONResponse(
                        {"error": "request body too large"}, status_code=413
                    )
        return await call_next(request)
