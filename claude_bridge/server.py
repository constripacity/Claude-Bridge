"""
Claude Bridge — General-purpose MCP relay server for real-time multi-agent
Claude Code communication across machines and projects.

Any number of Claude Code instances on any machine can connect to this server
and exchange messages via named channels. Channels are project-scoped by
convention: "<project>:<role>", e.g. "demo:orchestrator", "myproject:worker".

Messages are persisted to SQLite (default: ./claude-bridge.db, override with
the CLAUDE_BRIDGE_DB environment variable) so they survive server restarts.

Run on the host machine: `claude-bridge` (or `python -m claude_bridge`)
Host machine connects:    localhost:8765
Remote machines connect:  <host-address>:8765 (LAN IP, Tailscale IP, etc.)
"""

import os
import json
import uuid
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Any

import anyio
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.requests import Request


VERSION = "0.6.1"
SERVER_STARTED_AT = datetime.now(timezone.utc)
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


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


def uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - SERVER_STARTED_AT).total_seconds())


def format_uptime(s: int) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _is_json_str(s: str) -> bool:
    s = s.strip()
    if not s or s[0] not in "{[":
        return False
    try:
        json.loads(s)
        return True
    except (ValueError, TypeError):
        return False


async def insert_message(channel: str, sender: str, content: str) -> tuple[str, int, str]:
    """Append a message to a channel. Returns (id, seq, timestamp)."""
    msg_id = str(uuid.uuid4())
    ts = utc_now_iso()
    async with _write_lock:
        cur = db().execute(
            "INSERT INTO messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (msg_id, channel, sender, content, ts),
        )
        seq = cur.lastrowid
    return msg_id, seq, ts


async def clear_channel(channel: str) -> int:
    async with _write_lock:
        cur = db().execute("DELETE FROM messages WHERE channel = ?", (channel,))
        return cur.rowcount


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
                "Use descriptive channel names like 'demo:orchestrator' or 'demo:worker'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name, e.g. 'demo:orchestrator'"
                    },
                    "sender": {
                        "type": "string",
                        "description": "Your identity, e.g. 'windows' or 'mac'"
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
        msg_id, seq, ts = await insert_message(
            arguments["channel"], arguments["sender"], arguments["content"]
        )
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
        count = await clear_channel(channel)
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


# ── HTTP / JSON API ──────────────────────────────────────────────────────────

async def http_status(request: Request) -> JSONResponse:
    rows = db().execute(
        "SELECT channel, COUNT(*) AS n FROM messages GROUP BY channel"
    ).fetchall()
    return JSONResponse({
        "service": "claude-bridge",
        "status": "online",
        "version": VERSION,
        "db_path": DB_PATH,
        "channels": {r["channel"]: r["n"] for r in rows},
        "total_messages": sum(r["n"] for r in rows),
        "server_time": utc_now_iso(),
    })


async def api_state(request: Request) -> JSONResponse:
    conn = db()
    chan_rows = conn.execute(
        "SELECT channel, COUNT(*) AS n, MAX(timestamp) AS last_ts "
        "FROM messages GROUP BY channel ORDER BY channel"
    ).fetchall()
    channels = []
    for r in chan_rows:
        ch = r["channel"]
        group, _, name = ch.partition(":")
        if not name:
            group, name = "", ch
        senders = [
            s["sender"] for s in conn.execute(
                "SELECT DISTINCT sender FROM messages WHERE channel = ? ORDER BY sender",
                (ch,),
            ).fetchall()
        ]
        channels.append({
            "id": ch,
            "group": group,
            "name": name,
            "count": r["n"],
            "last_ts": r["last_ts"][11:19] if r["last_ts"] else "",
            "last_ts_full": r["last_ts"],
            "senders": senders,
        })
    up = uptime_seconds()
    return JSONResponse({
        "service": "claude-bridge",
        "status": "online",
        "version": VERSION,
        "uptime_seconds": up,
        "uptime_human": format_uptime(up),
        "total_messages": sum(c["count"] for c in channels),
        "channels": channels,
        "server_time": utc_now_iso(),
    })


async def api_messages(request: Request) -> JSONResponse:
    channel = request.query_params.get("channel")
    if not channel:
        return JSONResponse({"error": "channel parameter required"}, status_code=400)
    since_id = request.query_params.get("since_id")
    try:
        limit = int(request.query_params.get("limit", 50))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 500))

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

    messages = []
    for r in rows:
        content = r["content"]
        preview = content if len(content) <= 200 else content[:200] + "…"
        messages.append({
            "seq": r["seq"],
            "id": r["id"],
            "ts": r["timestamp"][11:19] if r["timestamp"] else "",
            "ts_full": r["timestamp"],
            "sender": r["sender"],
            "is_json": _is_json_str(content),
            "preview": preview,
        })
    return JSONResponse({"channel": channel, "messages": messages})


async def api_message_detail(request: Request) -> JSONResponse:
    msg_id = request.path_params["msg_id"]
    row = db().execute(
        "SELECT seq, id, channel, sender, content, timestamp FROM messages WHERE id = ?",
        (msg_id,),
    ).fetchone()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    content = row["content"]
    is_json = _is_json_str(content)
    parsed = None
    if is_json:
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            parsed = None
    return JSONResponse({
        "seq": row["seq"],
        "id": row["id"],
        "channel": row["channel"],
        "sender": row["sender"],
        "ts": row["timestamp"],
        "is_json": is_json,
        "content": content,
        "content_parsed": parsed,
        "bytes": len(content.encode("utf-8")),
    })


async def api_send(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    for key in ("channel", "sender", "content"):
        if not isinstance(body.get(key), str) or not body[key]:
            return JSONResponse({"error": f"missing or empty: {key}"}, status_code=400)
    msg_id, seq, ts = await insert_message(body["channel"], body["sender"], body["content"])
    return JSONResponse({"id": msg_id, "seq": seq, "channel": body["channel"], "ts": ts})


async def api_clear(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    channel = body.get("channel")
    if not isinstance(channel, str) or not channel:
        return JSONResponse({"error": "missing or empty: channel"}, status_code=400)
    count = await clear_channel(channel)
    return JSONResponse({"channel": channel, "cleared": count})


# ── SSE Transport ─────────────────────────────────────────────────────────────

sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )
    # SSE bytes were already streamed via request._send inside connect_sse;
    # this empty Response just satisfies Starlette's response-object contract.
    return Response()


# Wrap the SDK's POST handler so a closed-session push — client disconnected
# between our 202 ACK and the SDK trying to forward the JSON-RPC response back
# over SSE — doesn't surface as a noisy ASGI traceback. The client already has
# the 202; their MCP SDK reconnects on its own.
async def handle_post_message(scope, receive, send):
    try:
        await sse_transport.handle_post_message(scope, receive, send)
    except (anyio.ClosedResourceError, anyio.BrokenResourceError):
        pass


# ── stdio Transport ───────────────────────────────────────────────────────────

async def run_stdio() -> None:
    """Run the MCP server over stdin/stdout (no HTTP, no dashboard).

    For single-process / local-only deployments where the MCP client spawns
    the bridge as a subprocess. Uses the same SQLite store as HTTP mode, so
    a `claude-bridge --stdio` server and a `claude-bridge` HTTP server pointed
    at the same `--db` path share state.
    """
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


# ── App ───────────────────────────────────────────────────────────────────────

_routes = [
    Route("/status", endpoint=http_status),
    Route("/api/state", endpoint=api_state),
    Route("/api/messages", endpoint=api_messages),
    Route("/api/messages/{msg_id}", endpoint=api_message_detail),
    Route("/api/send", endpoint=api_send, methods=["POST"]),
    Route("/api/clear", endpoint=api_clear, methods=["POST"]),
    Route("/sse", endpoint=handle_sse),
    Mount("/messages/", app=handle_post_message),
]
if os.path.isdir(WEB_DIR) and not os.environ.get("CLAUDE_BRIDGE_NO_DASHBOARD"):
    # Catch-all static mount goes LAST so it doesn't shadow API routes.
    # html=True makes "/" serve index.html.
    _routes.append(Mount("/", app=StaticFiles(directory=WEB_DIR, html=True)))

app = Starlette(
    routes=_routes,
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)


# Direct execution (`python -m claude_bridge` or the `claude-bridge` console
# script) goes through `claude_bridge.cli:main`. This module just defines the
# Starlette `app` and stays importable on its own.
