"""Async HTTP client for the Claude Bridge JSON API.

Used by tui.py. Wraps the five endpoints exposed by server.py:
    GET  /api/state
    GET  /api/messages?channel=X[&since_id=Y][&limit=N]
    GET  /api/messages/{id}
    POST /api/send
    POST /api/clear

Kept separate from the UI so it's unit-testable without spinning up Textual.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


# Sender colours — keep in sync with the design palette in
# docs/design/terminal/tui-core.jsx (TC.shadow / TC.mac / TC.watcher).
# Anything not in this map gets a deterministic hash-based assignment.
SENDER_PALETTE: list[str] = [
    "#58a6ff",  # blue
    "#3fb950",  # green
    "#d97706",  # amber
    "#bc8cff",  # magenta
    "#f85149",  # red
    "#7dd3fc",  # cyan
]
SENDER_OVERRIDES: dict[str, str] = {
    "mac":     "#58a6ff",
    "windows": "#d97706",
    "linux":   "#3fb950",
    "watcher": "#bc8cff",
}

# Message type colours — match TYPE_COLORS in tui-core.jsx.
TYPE_COLORS: dict[str, str] = {
    "TASK":   "#a371f7",
    "RESULT": "#3fb950",
    "ACK":    "#7dd3fc",
    "ERR":    "#f85149",
    "ERROR":  "#f85149",
    "HB":     "#8b949e",
    "HEARTBEAT": "#8b949e",
    "TXT":    "#e6edf3",
}


def sender_color(name: str) -> str:
    if name in SENDER_OVERRIDES:
        return SENDER_OVERRIDES[name]
    return SENDER_PALETTE[hash(name) % len(SENDER_PALETTE)]


def classify_message(content: str) -> str:
    """Best-effort type tag for a message. Mirrors the design's TASK/RESULT/ACK/HB/ERR/TXT."""
    s = content.strip()
    if not s:
        return "TXT"
    if s[0] not in "{[":
        return "TXT"
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return "TXT"
    if not isinstance(obj, dict):
        return "TXT"
    t = obj.get("type")
    if isinstance(t, str):
        return t.upper()
    return "TXT"


def group_channels(channels: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group channels by the part before ':'. Channels without ':' go under ''."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for ch in channels:
        groups.setdefault(ch.get("group", ""), []).append(ch)
    return groups


@dataclass
class BridgeError(Exception):
    status: int
    body: str

    def __str__(self) -> str:
        return f"HTTP {self.status}: {self.body[:200]}"


class BridgeClient:
    """Thin async wrapper around the bridge's JSON API."""

    def __init__(self, base_url: str = "http://localhost:8765", timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BridgeClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        r = await self._client.get(path, params=clean)
        if r.status_code >= 400:
            raise BridgeError(r.status_code, r.text)
        return r.json()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post(path, json=body)
        if r.status_code >= 400:
            raise BridgeError(r.status_code, r.text)
        return r.json()

    async def state(self) -> dict[str, Any]:
        return await self._get("/api/state")

    async def messages(
        self,
        channel: str,
        since_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await self._get(
            "/api/messages",
            channel=channel,
            since_id=since_id,
            limit=limit,
        )

    async def message_detail(self, msg_id: str) -> dict[str, Any]:
        return await self._get(f"/api/messages/{msg_id}")

    async def send(self, channel: str, sender: str, content: str) -> dict[str, Any]:
        return await self._post(
            "/api/send",
            {"channel": channel, "sender": sender, "content": content},
        )

    async def clear(self, channel: str) -> dict[str, Any]:
        return await self._post("/api/clear", {"channel": channel})
