"""Small ASGI middleware for browser-facing security headers."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=(), payment=()",
                )
                headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                    "form-action 'self'",
                )
                if scope.get("scheme") == "https":
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)
