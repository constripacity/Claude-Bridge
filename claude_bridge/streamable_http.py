"""Modern MCP Streamable HTTP transport for Claude Bridge.

The MCP Python SDK's :class:`StreamableHTTPSessionManager` has an important
lifecycle requirement: its ``run()`` context must be active before requests
are handled, and a manager instance can only be run once.  Keeping that detail
in this small adapter makes it hard for the main Starlette application to
accidentally mount a handler without starting its session manager.

Typical integration with an existing Starlette app::

    transport = StreamableHTTPApp(server)

    @asynccontextmanager
    async def lifespan(app):
        async with transport.run():
            yield

    routes = [Route("/mcp", endpoint=transport), ...]

``Route`` (rather than ``Mount``) intentionally exposes one canonical MCP
endpoint at exactly ``/mcp``.  The adapter is an ASGI object, so Starlette lets
the SDK handle POST, GET, and DELETE as required by the protocol.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send


LOCAL_ALLOWED_HOSTS = (
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "[::1]",
    "[::1]:*",
)

LOCAL_ALLOWED_ORIGINS = (
    "http://127.0.0.1",
    "http://127.0.0.1:*",
    "http://localhost",
    "http://localhost:*",
    "http://[::1]",
    "http://[::1]:*",
    "https://127.0.0.1",
    "https://127.0.0.1:*",
    "https://localhost",
    "https://localhost:*",
    "https://[::1]",
    "https://[::1]:*",
)


@dataclass(frozen=True, slots=True)
class StreamableHTTPConfig:
    """Runtime policy for the modern MCP endpoint.

    ``json_response`` is enabled because Claude Bridge tools return one bounded
    response and do not currently emit unsolicited MCP notifications.  JSON
    responses avoid holding a POST stream open through reverse proxies while
    still implementing the Streamable HTTP transport.  The SDK continues to
    support a standalone GET event stream for future server notifications.

    DNS-rebinding protection defaults to localhost-only.  Cross-machine
    deployments must explicitly add every public, LAN, or Tailscale host name
    clients put in the HTTP ``Host`` header.  Setting
    ``dns_rebinding_protection=False`` is available for trusted reverse-proxy
    setups, but is not the safe default.
    """

    json_response: bool = True
    stateless: bool = False
    session_idle_timeout: float | None = 30 * 60
    dns_rebinding_protection: bool = True
    allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS
    allowed_origins: tuple[str, ...] = LOCAL_ALLOWED_ORIGINS

    def security_settings(self) -> TransportSecuritySettings:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=self.dns_rebinding_protection,
            allowed_hosts=list(self.allowed_hosts),
            allowed_origins=list(self.allowed_origins),
        )


class StreamableHTTPApp:
    """ASGI endpoint plus lifecycle owner for MCP Streamable HTTP.

    Create exactly one instance for an application.  Call :meth:`run` from the
    parent application's lifespan, then register this object as a Starlette
    ``Route`` endpoint.  A stopped instance cannot be restarted; construct a
    fresh app for a fresh server lifecycle (which Starlette naturally does in
    production).
    """

    def __init__(
        self,
        server: Server[Any, Any],
        config: StreamableHTTPConfig | None = None,
    ) -> None:
        self.config = config or StreamableHTTPConfig()
        self.session_manager = StreamableHTTPSessionManager(
            app=server,
            json_response=self.config.json_response,
            stateless=self.config.stateless,
            security_settings=self.config.security_settings(),
            session_idle_timeout=(
                None if self.config.stateless else self.config.session_idle_timeout
            ),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.session_manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Run the SDK session manager for the parent app's lifetime."""

        async with self.session_manager.run():
            yield

    def standalone_app(
        self,
        path: str = "/mcp",
        *,
        extra_routes: Sequence[Any] = (),
    ) -> Starlette:
        """Build a small standalone Starlette app, useful for tests/embedding.

        The returned app and this transport are single-use together because the
        underlying SDK manager is deliberately single-use.
        """

        if not path.startswith("/"):
            raise ValueError("Streamable HTTP path must start with '/'")

        @asynccontextmanager
        async def lifespan(_app: Starlette) -> AsyncIterator[None]:
            async with self.run():
                yield

        return Starlette(
            routes=[Route(path, endpoint=self), *extra_routes],
            lifespan=lifespan,
        )


class RestartableStreamableHTTPApp:
    """Lifecycle wrapper that creates a fresh SDK manager per app startup.

    ASGI servers normally start once, but test harnesses and embedded runtimes
    may start/stop the same Starlette app repeatedly. The MCP SDK correctly
    makes each session manager single-use, so this wrapper owns a fresh
    :class:`StreamableHTTPApp` for every sequential lifespan.
    """

    def __init__(
        self,
        server: Server[Any, Any],
        config: StreamableHTTPConfig | None = None,
    ) -> None:
        self.server = server
        self.config = config or StreamableHTTPConfig()
        self._active: StreamableHTTPApp | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        active = self._active
        if active is None:
            response = JSONResponse(
                {"error": "MCP transport is not running"}, status_code=503
            )
            await response(scope, receive, send)
            return
        await active(scope, receive, send)

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        if self._active is not None:
            raise RuntimeError("MCP transport lifespan is already active")
        active = StreamableHTTPApp(self.server, self.config)
        self._active = active
        try:
            async with active.run():
                yield
        finally:
            self._active = None


def create_streamable_http_app(
    server: Server[Any, Any],
    *,
    path: str = "/mcp",
    config: StreamableHTTPConfig | None = None,
) -> Starlette:
    """Convenience factory for a standalone modern MCP application."""

    return StreamableHTTPApp(server, config).standalone_app(path)
