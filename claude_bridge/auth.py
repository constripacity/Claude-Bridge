"""Security middleware for Claude Bridge.

Three pieces:

- `BearerAuthMiddleware`: when `CLAUDE_BRIDGE_AUTH_TOKEN` is set (or
  `--auth-token <value>` passed on the CLI), every HTTP endpoint except
  `/status` and the static dashboard requires either `Authorization: Bearer
  <token>` or a valid opaque dashboard-session cookie. Off when no token is
  configured.
- `RequestSizeLimitMiddleware`: rejects oversized mutation bodies whether or
  not the client supplies an honest ``Content-Length`` header.
- `RequestPolicyMiddleware`: an opt-in browser/network boundary for trusted
  hosts, mutation origins, and JSON-only application routes.

The stdio transport is not affected by either middleware (no network surface).
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
from collections.abc import Collection, Sequence
from typing import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("claude_bridge")


# Audit hook shape: called as `await hook(path, client_ip)` when a request is
# rejected. Optional — `None` means "don't audit" (the default). Kept as a
# plain callable so this module stays decoupled from the server/audit store.
AuditHook = Callable[[str, "str | None"], Awaitable[None]]


async def _run_hook(hook: AuditHook | None, request: Request) -> None:
    """Fire an audit hook best-effort. The audit log is a side-channel — a
    failure in it (e.g. SQLite busy, disk full) must never turn a clean 401/413
    rejection into a 500, so swallow and log rather than propagate."""
    if hook is None:
        return
    try:
        ip = request.client.host if request.client else None
        await hook(request.url.path, ip)
    except Exception:
        logger.warning("audit hook failed", exc_info=True)


# Routes that require the Bearer token when auth is enabled. Everything else
# (including /status and the static dashboard mount) is public. The dashboard
# exchanges a bearer token once for an opaque, HttpOnly session cookie.
PROTECTED_PREFIXES = ("/api/", "/messages/", "/events/")
PROTECTED_PATHS = frozenset({"/sse", "/mcp"})

SESSION_COOKIE_NAME = "claude_bridge_session"


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

    def __init__(
        self,
        app,
        token_getter: Callable[[], str | None],
        on_auth_failure: AuditHook | None = None,
        session_validator: Callable[[str], bool] | None = None,
        allow_unauthenticated_network_getter: Callable[[], bool] | None = None,
    ):
        super().__init__(app)
        self._get_token = token_getter
        self._on_auth_failure = on_auth_failure
        self._session_validator = session_validator
        self._allow_unauthenticated_network = (
            allow_unauthenticated_network_getter or (lambda: False)
        )

    async def _deny(self, request: Request) -> JSONResponse:
        await _run_hook(self._on_auth_failure, request)
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _is_protected(path):
            return await call_next(request)
        token = self._get_token()
        if not token:
            client_host = request.client.host if request.client else ""
            try:
                is_remote_ip = not ipaddress.ip_address(client_host).is_loopback
            except ValueError:
                # ASGI test harnesses and some in-process adapters use a
                # symbolic client name. Network servers such as uvicorn supply
                # a concrete address here.
                is_remote_ip = False
            if is_remote_ip and not self._allow_unauthenticated_network():
                await _run_hook(self._on_auth_failure, request)
                return JSONResponse(
                    {"error": "unauthenticated network access is disabled"},
                    status_code=403,
                )
            request.state.bridge_auth = "none"
            return await call_next(request)
        if path == "/api/session" and request.method == "DELETE":
            request.state.bridge_auth = "session"
            return await call_next(request)
        # RFC 7235: auth-scheme is case-insensitive. Parse "<scheme> <credential>"
        # and compare only the credential half with constant-time compare to
        # avoid leaking the expected token's length via the prefix-equality check.
        header = request.headers.get("Authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() == "bearer" and credential:
            if hmac.compare_digest(credential.encode(), token.encode()):
                request.state.bridge_auth = "bearer"
                return await call_next(request)
            return await self._deny(request)
        # Session creation is a one-way exchange from the master credential.
        # An existing (or stolen) cookie must never mint descendant sessions.
        if path == "/api/session" and request.method == "POST":
            return await self._deny(request)
        cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "")
        if (
            cookie_token
            and self._session_validator is not None
            and self._session_validator(cookie_token)
        ):
            request.state.bridge_auth = "session"
            return await call_next(request)
        return await self._deny(request)


class RequestSizeLimitMiddleware:
    """Reject oversized request bodies before application code sees them.

    ``Content-Length`` is checked first for a cheap early rejection, then the
    ASGI request stream is counted up to ``max_bytes``.  The second check is
    essential: chunked requests have no length header and a malicious client
    can simply lie about the value it sends.

    Bodies at or below the cap are replayed to the downstream application.
    At most ``max_bytes`` plus one ASGI chunk is held while validating, and an
    over-limit request never invokes the route handler.  The cap is applied to
    HTTP methods that normally carry mutation bodies; callers may override
    ``body_methods`` when their application accepts bodies elsewhere.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        on_reject: AuditHook | None = None,
        body_methods: Collection[str] = ("POST", "PUT", "PATCH", "DELETE"),
    ):
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        self.app = app
        self._max = max_bytes
        self._on_reject = on_reject
        self._body_methods = frozenset(method.upper() for method in body_methods)

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        error: str,
        status: int,
    ) -> None:
        request = Request(scope)
        await _run_hook(self._on_reject, request)
        response = JSONResponse({"error": error}, status_code=status)
        await response(scope, receive, send)

    @staticmethod
    def _content_lengths(scope: Scope) -> list[str]:
        """Return every Content-Length value, preserving duplicates.

        ``Headers.get`` hides duplicate framing headers.  Rejecting duplicates
        removes an avoidable request-smuggling ambiguity between proxies and
        the application server.
        """
        return [
            value.decode("latin-1").strip()
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]

    @staticmethod
    def _header_values(scope: Scope, header_name: bytes) -> list[str]:
        return [
            value.decode("latin-1").strip()
            for name, value in scope.get("headers", [])
            if name.lower() == header_name
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method", "").upper() not in self._body_methods
        ):
            await self.app(scope, receive, send)
            return

        lengths = self._content_lengths(scope)
        transfer_encodings = self._header_values(scope, b"transfer-encoding")
        if len(lengths) > 1:
            await self._reject(scope, receive, send, "invalid content-length", 400)
            return
        if len(transfer_encodings) > 1 or (lengths and transfer_encodings):
            await self._reject(scope, receive, send, "ambiguous request framing", 400)
            return
        if transfer_encodings and transfer_encodings[0].lower() != "chunked":
            await self._reject(scope, receive, send, "invalid transfer-encoding", 400)
            return
        declared_length: int | None = None
        if lengths:
            raw_length = lengths[0]
            try:
                # ``+1`` and whitespace are intentionally rejected. HTTP
                # framing uses a non-negative decimal integer, not Python's
                # more permissive integer syntax.
                if not raw_length.isascii() or not raw_length.isdecimal():
                    raise ValueError
                length = int(raw_length)
            except ValueError:
                await self._reject(scope, receive, send, "invalid content-length", 400)
                return
            if length > self._max:
                await self._reject(scope, receive, send, "request body too large", 413)
                return
            declared_length = length

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":  # pragma: no cover - ASGI extension
                continue
            total += len(message.get("body", b""))
            if total > self._max:
                await self._reject(scope, receive, send, "request body too large", 413)
                return
            if not message.get("more_body", False):
                break

        if declared_length is not None and total != declared_length:
            await self._reject(scope, receive, send, "content-length mismatch", 400)
            return

        position = 0

        async def replay_receive() -> Message:
            nonlocal position
            if position < len(buffered):
                message = buffered[position]
                position += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)


_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _hostname(value: str) -> str:
    """Extract a lowercase hostname from a Host-header authority."""
    try:
        parsed = urlsplit(f"//{value}")
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def _host_matches(hostname: str, patterns: Sequence[str]) -> bool:
    for raw_pattern in patterns:
        pattern = raw_pattern.strip().lower()
        # Configuration may include a port for convenience; host trust is
        # deliberately based on the DNS/IP identity rather than listen port.
        if pattern.count(":") >= 2 and not pattern.startswith("["):
            # Bare IPv6 literal in configuration (Host headers themselves are
            # bracketed, but asking operators to include brackets is needless).
            pattern_host = pattern
        else:
            pattern_host = _hostname(pattern) if ":" in pattern else pattern
        if pattern_host.startswith("*."):
            suffix = pattern_host[1:]
            if hostname.endswith(suffix) and hostname != suffix[1:]:
                return True
        elif hostname == pattern_host:
            return True
    return False


def _origin_is_same_origin(origin: str, scope: Scope, host_header: str) -> bool:
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = urlsplit(f"//{host_header}")
        host_port = host.port or (443 if scope.get("scheme") == "https" else 80)
        return (
            parsed.scheme == scope.get("scheme", "http")
            and parsed.hostname.lower() == (host.hostname or "").lower()
            and origin_port == host_port
        )
    except ValueError:
        return False


def _is_json_media_type(value: str) -> bool:
    media_type = value.partition(";")[0].strip().lower()
    if media_type == "application/json":
        return True
    if "/" not in media_type:
        return False
    top_level, subtype = media_type.split("/", 1)
    return top_level == "application" and subtype.endswith("+json")


class RequestPolicyMiddleware:
    """Opt-in Host, browser-origin, and JSON media-type policy.

    This middleware is intentionally configuration-driven so it can sit in
    front of both today's REST routes and a future Streamable HTTP MCP route:

    * ``allowed_hosts`` validates the HTTP Host header when supplied. Host
      ports are ignored and ``*.example.com`` wildcards are supported.
    * unsafe browser requests with an ``Origin`` header must be same-origin or
      explicitly listed in ``allowed_origins``. Requests without Origin remain
      available to CLI/MCP clients.
    * ``json_paths`` identifies application routes that require an
      ``application/json`` or ``application/*+json`` content type. A path
      ending in ``/`` is treated as a prefix; all others are exact matches.

    Instantiating this class is the opt-in boundary. Its defaults retain the
    bridge's same-origin dashboard workflow and do not force a Host allowlist
    or JSON policy unless those values are configured.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: Sequence[str] | None = None,
        allowed_origins: Sequence[str] = (),
        allow_localhost_origins: bool = False,
        protect_mutations: bool = True,
        json_paths: Sequence[str] = (),
        on_reject: AuditHook | None = None,
    ) -> None:
        self.app = app
        self._allowed_hosts = (
            tuple(allowed_hosts) if allowed_hosts is not None else None
        )
        self._allowed_origins = frozenset(
            origin.rstrip("/") for origin in allowed_origins
        )
        self._allow_localhost_origins = allow_localhost_origins
        self._protect_mutations = protect_mutations
        self._json_paths = tuple(json_paths)
        self._on_reject = on_reject

    def _requires_json(self, path: str) -> bool:
        return any(
            path.startswith(pattern) if pattern.endswith("/") else path == pattern
            for pattern in self._json_paths
        )

    def _origin_allowed(self, origin: str, scope: Scope, host_header: str) -> bool:
        normalized = origin.rstrip("/")
        if normalized in self._allowed_origins:
            return True
        if _origin_is_same_origin(origin, scope, host_header):
            return True
        if self._allow_localhost_origins:
            try:
                parsed = urlsplit(origin)
                return (
                    parsed.scheme in {"http", "https"}
                    and parsed.hostname in _LOCAL_HOSTS
                )
            except ValueError:
                return False
        return False

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        error: str,
        status: int,
    ) -> None:
        request = Request(scope)
        await _run_hook(self._on_reject, request)
        response = JSONResponse({"error": error}, status_code=status)
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        raw_headers = scope.get("headers", [])
        host_values = [
            value for name, value in raw_headers if name.lower() == b"host"
        ]
        origin_values = [
            value for name, value in raw_headers if name.lower() == b"origin"
        ]
        if len(host_values) > 1:
            await self._reject(scope, receive, send, "duplicate host header", 400)
            return
        if len(origin_values) > 1:
            await self._reject(scope, receive, send, "duplicate origin header", 400)
            return
        host_header = headers.get("host", "")
        hostname = _hostname(host_header)
        if self._allowed_hosts is not None:
            if not hostname or not _host_matches(hostname, self._allowed_hosts):
                await self._reject(scope, receive, send, "invalid host header", 400)
                return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if self._protect_mutations and method in _MUTATION_METHODS:
            origin = headers.get("origin")
            if origin and not self._origin_allowed(origin, scope, host_header):
                await self._reject(scope, receive, send, "origin not allowed", 403)
                return

        # DELETE is used by MCP Streamable HTTP to close a session and has no
        # JSON body. JSON-only policy applies to methods that carry a payload.
        if method in {"POST", "PUT", "PATCH"} and self._requires_json(path):
            if not _is_json_media_type(headers.get("content-type", "")):
                await self._reject(
                    scope,
                    receive,
                    send,
                    "content-type must be application/json",
                    415,
                )
                return

        await self.app(scope, receive, send)
