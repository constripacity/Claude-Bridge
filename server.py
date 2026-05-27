"""
Claude Bridge — General-purpose MCP relay server for real-time multi-agent
Claude Code communication across machines and projects.

Any number of Claude Code instances on any machine can connect to this server
and exchange messages via named channels. Channels are project-scoped by
convention: "<project>:<role>", e.g. "pawprint:orchestrator", "bookforge:mac".

Messages are persisted to SQLite (default: ./claude-bridge.db, override with
the CLAUDE_BRIDGE_DB environment variable) so they survive server restarts.

Run on MacBook Air:  python server.py
Mac connects:        localhost:8765
Shadow connects:     <mac-tailscale-ip>:8765
Any other machine:   <mac-tailscale-ip>:8765
"""

import os
import uuid
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
import uvicorn


# ── Persistence ──────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("CLAUDE_BRIDGE_DB", "claude-bridge.db")

_conn: sqlite3.Connection | None = None
_write_lock = asyncio.Lock()


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                seq       INTEGER PRIMARY KEY AUTOINCREMENT,
                id        TEXT    NOT NULL UNIQUE,
                channel   TEXT    NOT NULL,
                sender    TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            )
        """)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel)")
    return _conn


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── MCP Server ────────────────────────────────────────────────────────────────

server = Server("claude-bridge")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="bridge_send",
            description=(
                "Send a message to a named channel on the Claude Bridge. "
                "The other agent can read it with bridge_receive. "
                "Use descriptive channel names like 'pawprint:orchestrator' or 'pawprint:mac'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name, e.g. 'pawprint:orchestrator'"
                    },
                    "sender": {
                        "type": "string",
                        "description": "Your identity, e.g. 'shadow' or 'mac'"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content — can be plain text or JSON"
                    },
                },
                "required": ["channel", "sender", "content"]
            }
        ),
        Tool(
            name="bridge_receive",
            description=(
                "Read messages from a named channel. "
                "Pass since_id to only get messages newer than a known message. "
                "Poll this every few seconds to simulate real-time communication."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel to read from"
                    },
                    "since_id": {
                        "type": "string",
                        "description": "Only return messages after this message ID (exclusive). Get from a previous receive."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default: 20)",
                        "default": 20
                    }
                },
                "required": ["channel"]
            }
        ),
        Tool(
            name="bridge_channels",
            description="List all active channels and their message counts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="bridge_ping",
            description="Check if the bridge server is alive and get a status summary.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="bridge_clear",
            description="Clear all messages from a specific channel. Useful for resetting state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel to clear"
                    }
                },
                "required": ["channel"]
            }
        ),
        Tool(
            name="bridge_status",
            description=(
                "Get the last N messages from ALL channels at once. "
                "Useful for getting a full picture of what's happening across agents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "per_channel": {
                        "type": "integer",
                        "description": "How many recent messages to show per channel (default: 5)",
                        "default": 5
                    }
                }
            }
        ),
    ]


async def dispatch_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Plain dispatcher — also exposed for tests so they don't depend on the
    MCP @server.call_tool() decorator."""

    # ── bridge_send ──────────────────────────────────────────────────────────
    if name == "bridge_send":
        msg_id = str(uuid.uuid4())
        ts = utc_now_iso()
        async with _write_lock:
            cur = db().execute(
                "INSERT INTO messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (msg_id, arguments["channel"], arguments["sender"], arguments["content"], ts),
            )
            seq = cur.lastrowid
        result = (
            f"✓ Sent to [{arguments['channel']}]\n"
            f"  id: {msg_id}\n"
            f"  seq: {seq}\n"
            f"  time: {ts}"
        )
        return [TextContent(type="text", text=result)]

    # ── bridge_receive ───────────────────────────────────────────────────────
    elif name == "bridge_receive":
        channel = arguments["channel"]
        since_id = arguments.get("since_id")
        limit = int(arguments.get("limit", 20))
        conn = db()

        if since_id:
            row = conn.execute("SELECT seq FROM messages WHERE id = ?", (since_id,)).fetchone()
            since_seq = row["seq"] if row else 0
            rows = conn.execute(
                "SELECT seq, id, sender, content, timestamp FROM messages "
                "WHERE channel = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (channel, since_seq, limit),
            ).fetchall()
        else:
            rows = list(reversed(conn.execute(
                "SELECT seq, id, sender, content, timestamp FROM messages "
                "WHERE channel = ? ORDER BY seq DESC LIMIT ?",
                (channel, limit),
            ).fetchall()))

        if not rows:
            suffix = f" after {since_id[:8]}" if since_id else ""
            return [TextContent(type="text", text=f"[{channel}] — no messages{suffix}")]

        lines = []
        for m in rows:
            ts = m["timestamp"][:19].replace("T", " ")
            lines.append(f"━━ [{m['seq']}] {m['sender']} @ {ts} (id: {m['id']})")
            lines.append(m["content"])
            lines.append("")

        header = f"[{channel}] — {len(rows)} message(s)\n"
        return [TextContent(type="text", text=header + "\n".join(lines).rstrip())]

    # ── bridge_channels ──────────────────────────────────────────────────────
    elif name == "bridge_channels":
        rows = db().execute(
            "SELECT channel, COUNT(*) AS n, MAX(timestamp) AS last_ts "
            "FROM messages GROUP BY channel ORDER BY channel"
        ).fetchall()
        if not rows:
            return [TextContent(type="text", text="No active channels yet.")]
        total = sum(r["n"] for r in rows)
        lines = [f"Active channels ({len(rows)}, {total} total messages):"]
        for r in rows:
            last_ts = r["last_ts"][:19].replace("T", " ") if r["last_ts"] else "—"
            lines.append(f"  • {r['channel']}  ({r['n']} msgs, last: {last_ts})")
        return [TextContent(type="text", text="\n".join(lines))]

    # ── bridge_ping ──────────────────────────────────────────────────────────
    elif name == "bridge_ping":
        row = db().execute(
            "SELECT COUNT(DISTINCT channel) AS chans, COUNT(*) AS total FROM messages"
        ).fetchone()
        return [TextContent(type="text", text=(
            f"✓ Claude Bridge online\n"
            f"  Channels: {row['chans']}\n"
            f"  Messages: {row['total']}\n"
            f"  Server time: {utc_now_iso()}"
        ))]

    # ── bridge_clear ─────────────────────────────────────────────────────────
    elif name == "bridge_clear":
        channel = arguments["channel"]
        async with _write_lock:
            cur = db().execute("DELETE FROM messages WHERE channel = ?", (channel,))
            count = cur.rowcount
        return [TextContent(type="text", text=f"Cleared {count} message(s) from [{channel}]")]

    # ── bridge_status ────────────────────────────────────────────────────────
    elif name == "bridge_status":
        per_channel = int(arguments.get("per_channel", 5))
        conn = db()
        channel_rows = conn.execute(
            "SELECT channel, COUNT(*) AS n FROM messages GROUP BY channel ORDER BY channel"
        ).fetchall()
        if not channel_rows:
            return [TextContent(type="text", text="No active channels.")]

        sections = []
        for cr in channel_rows:
            ch = cr["channel"]
            recent = list(reversed(conn.execute(
                "SELECT seq, sender, content, timestamp FROM messages "
                "WHERE channel = ? ORDER BY seq DESC LIMIT ?",
                (ch, per_channel),
            ).fetchall()))
            section = [f"┌─ [{ch}] — {cr['n']} total"]
            for m in recent:
                ts = m["timestamp"][:19].replace("T", " ")
                preview = m["content"][:120].replace("\n", " ")
                if len(m["content"]) > 120:
                    preview += "…"
                section.append(f"│  [{m['seq']}] {m['sender']} @ {ts}")
                section.append(f"│  {preview}")
            section.append("└" + "─" * 40)
            sections.append("\n".join(section))

        return [TextContent(type="text", text="\n\n".join(sections))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    return await dispatch_tool(name, arguments)


# ── HTTP status endpoint (not MCP, just for humans) ──────────────────────────

async def http_status(request: Request) -> JSONResponse:
    rows = db().execute(
        "SELECT channel, COUNT(*) AS n FROM messages GROUP BY channel"
    ).fetchall()
    return JSONResponse({
        "service": "claude-bridge",
        "status": "online",
        "db_path": DB_PATH,
        "channels": {r["channel"]: r["n"] for r in rows},
        "total_messages": sum(r["n"] for r in rows),
        "server_time": utc_now_iso(),
    })


# ── SSE Transport ─────────────────────────────────────────────────────────────

sse_transport = SseServerTransport("/messages")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


async def handle_messages(request: Request):
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )


# ── App ───────────────────────────────────────────────────────────────────────

app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/status", endpoint=http_status),
        Mount("/messages", app=handle_messages),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]
)


if __name__ == "__main__":
    db()  # initialize DB before serving
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Claude Bridge — General MCP Relay Server")
    print(f"  DB: {os.path.abspath(DB_PATH)}")
    print("  http://localhost:8765/sse        ← Mac MCP config")
    print("  http://<tailscale-ip>:8765/sse   ← Remote machines")
    print("  http://localhost:8765/status     ← Health check")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    uvicorn.run(app, host="0.0.0.0", port=8765)
