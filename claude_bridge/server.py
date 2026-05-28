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
from anyio.streams.memory import MemoryObjectSendStream
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.requests import Request

from .auth import BearerAuthMiddleware, RequestSizeLimitMiddleware


VERSION = "0.8.0"
SERVER_STARTED_AT = datetime.now(timezone.utc)
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
AUTH_TOKEN = os.environ.get("CLAUDE_BRIDGE_AUTH_TOKEN") or None

# CORS: by default only same-origin and localhost (any port) are allowed. To
# add origins (e.g. when running the dashboard from a separate domain), pass
# `--cors-origin <origin>` on the CLI or set CLAUDE_BRIDGE_CORS_ORIGIN to a
# comma-separated list. The wildcard `allow_origins=["*"]` from earlier
# versions is gone — it let drive-by sites read and write the bridge in any
# default deployment.
_CORS_ORIGIN_ENV = os.environ.get("CLAUDE_BRIDGE_CORS_ORIGIN", "").strip()
CORS_EXTRA_ORIGINS = (
    [o.strip() for o in _CORS_ORIGIN_ENV.split(",") if o.strip()]
    if _CORS_ORIGIN_ENV
    else []
)
CORS_LOCALHOST_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

# Maximum HTTP request body (POST /api/send, /api/clear). Rejecting at the
# Content-Length header avoids reading the body into memory. Anything larger
# than this is almost certainly abuse — channel messages are short by design.
MAX_REQUEST_BYTES = 256 * 1024
# Maximum length of a single message `content` field, enforced after JSON
# decode for defense-in-depth (the Content-Length cap above already rejects
# most abuse; this catches the boundary).
MAX_MESSAGE_BYTES = 128 * 1024

# Live event-stream caps. Global cap protects against a runaway client opening
# thousands of EventSources; per-channel cap stops one busy channel from
# starving the global pool. Subscribers past the cap get 503. Backlog cap is
# how many historical messages a reconnecting subscriber can replay before we
# tell them to re-sync via /api/messages (avoids unbounded replay after days
# of disconnect). All three are env-tunable so operators can grow without a
# code change.
MAX_SSE_SUBSCRIBERS = int(os.environ.get("CLAUDE_BRIDGE_MAX_SSE", "100"))
MAX_SSE_PER_CHANNEL = int(os.environ.get("CLAUDE_BRIDGE_MAX_SSE_PER_CHANNEL", "25"))
SSE_REPLAY_LIMIT = int(os.environ.get("CLAUDE_BRIDGE_SSE_REPLAY_LIMIT", "500"))


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


# ── Live event broker ────────────────────────────────────────────────────────
#
# Subscribers to `GET /events/channel/<name>` register a memory object stream
# here; insert_message / clear_channel push events into matching streams. Slow
# subscribers get events dropped rather than blocking the writer — we count
# the drops so /api/state can surface whether the caps need raising.

_subscribers: dict[str, set[MemoryObjectSendStream]] = {}
_dropped_events_total: int = 0


def _subscriber_count_total() -> int:
    return sum(len(s) for s in _subscribers.values())


async def _broadcast(channel: str, envelope: dict[str, Any]) -> None:
    """Fan an event envelope out to every subscriber of `channel`.

    Envelope shape: {"event": "message"|"clear"|..., "data": {...}, "id": "..."}.
    Send is non-blocking — if a subscriber's buffer is full, we drop the event
    for that subscriber rather than stall the writer (writers must stay snappy
    so `bridge_send` latency isn't held hostage by a slow dashboard tab).
    """
    global _dropped_events_total
    streams = list(_subscribers.get(channel, ()))
    for stream in streams:
        try:
            stream.send_nowait(envelope)
        except anyio.WouldBlock:
            _dropped_events_total += 1
        except anyio.BrokenResourceError:
            # Subscriber's receive side is gone (their task already exited);
            # drop them from the set so we stop trying.
            _subscribers.get(channel, set()).discard(stream)


def _message_envelope(seq: int, msg_id: str, sender: str, content: str, timestamp: str) -> dict[str, Any]:
    return {
        "event": "message",
        "id": msg_id,
        "data": {
            "seq": seq,
            "id": msg_id,
            "sender": sender,
            "content": content,
            "timestamp": timestamp,
        },
    }


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
    await _broadcast(channel, _message_envelope(seq, msg_id, sender, content, ts))
    return msg_id, seq, ts


async def clear_channel(channel: str) -> int:
    async with _write_lock:
        cur = db().execute("DELETE FROM messages WHERE channel = ?", (channel,))
        count = cur.rowcount
    await _broadcast(channel, {
        "event": "clear",
        "data": {"channel": channel, "cleared": count},
    })
    return count


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
            if row is None:
                # Cursor stale — message was cleared, never existed, or was
                # never on this server. Earlier versions silently fell back to
                # "from the beginning" here, which floods the caller with the
                # full channel on every poll once the cursor goes bad. Return
                # an empty result and tell the caller their cursor is stale so
                # they can decide whether to drop it and re-sync.
                return [TextContent(type="text", text=(
                    f"[{channel}] — since_id {since_id[:8]} not found "
                    f"(cursor stale, channel may have been cleared); "
                    f"call again without since_id to read from the start"
                ))]
            since_seq = row["seq"]
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
        per_channel = max(1, min(int(arguments.get("per_channel", 5)), 50))
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
    # Public endpoint — keep payload to the bare healthcheck signal.
    # Prior versions returned the absolute db_path and the full channel map
    # here; both were useful recon for an unauthenticated probe.
    return JSONResponse({
        "service": "claude-bridge",
        "status": "online",
        "version": VERSION,
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
        "sse_subscribers": _subscriber_count_total(),
        "sse_dropped_events": _dropped_events_total,
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
        if row is None:
            # See bridge_receive — return empty + warning instead of silently
            # dumping the channel from the beginning when the cursor is stale.
            return JSONResponse({
                "channel": channel,
                "messages": [],
                "warning": "since_id_not_found",
            })
        since_seq = row["seq"]
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
    if len(body["content"].encode("utf-8")) > MAX_MESSAGE_BYTES:
        return JSONResponse(
            {"error": f"content exceeds {MAX_MESSAGE_BYTES} bytes"},
            status_code=413,
        )
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


# ── Live event stream per channel ────────────────────────────────────────────


async def sse_channel(request: Request):
    """Server-sent events for a single channel.

    Emits `message` events as inserts land, `clear` events when the channel is
    cleared, plus `cursor_stale` / `replay_truncated` signals on connect when
    a `Last-Event-ID` header (or `?since_id=` query param) points at a message
    we don't have or asks for more backlog than we'll replay.

    Auth: same Bearer-token gate as the rest of `/events/`, with an
    `?token=...` query-param fallback because the EventSource API can't send
    custom headers. See `auth.py` for the bypass logic.
    """
    channel = request.path_params["channel"]

    # Cap enforcement before allocating a stream. Per-channel cap first so a
    # busy channel can't drain the global pool by itself.
    if len(_subscribers.get(channel, ())) >= MAX_SSE_PER_CHANNEL:
        return JSONResponse(
            {"error": f"channel '{channel}' has reached its subscriber cap"},
            status_code=503,
        )
    if _subscriber_count_total() >= MAX_SSE_SUBSCRIBERS:
        return JSONResponse(
            {"error": "server subscriber cap reached"},
            status_code=503,
        )

    # Resolve the resume cursor: `Last-Event-ID` is the standard SSE reconnect
    # header (browsers send it automatically). `?since_id=` is the explicit
    # opt-in for first-time connects (TUI uses this).
    last_id = request.headers.get("Last-Event-ID") or request.query_params.get("since_id")

    send_stream, recv_stream = anyio.create_memory_object_stream(max_buffer_size=100)
    _subscribers.setdefault(channel, set()).add(send_stream)

    async def event_gen():
        try:
            # 1. Backlog replay if the caller has a resume cursor.
            if last_id:
                row = db().execute(
                    "SELECT seq FROM messages WHERE id = ?", (last_id,)
                ).fetchone()
                if row is None:
                    # Cursor stale — symmetry with bridge_receive / api_messages
                    # since v0.7.4 (M3). Tell the client their cursor is gone
                    # and they should re-sync via /api/messages without it.
                    yield {
                        "event": "cursor_stale",
                        "data": json.dumps({"since_id": last_id}),
                    }
                else:
                    # Fetch one extra row so we can detect truncation cheaply.
                    rows = db().execute(
                        "SELECT seq, id, sender, content, timestamp FROM messages "
                        "WHERE channel = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                        (channel, row["seq"], SSE_REPLAY_LIMIT + 1),
                    ).fetchall()
                    truncated = len(rows) > SSE_REPLAY_LIMIT
                    for m in rows[:SSE_REPLAY_LIMIT]:
                        yield {
                            "event": "message",
                            "id": m["id"],
                            "data": json.dumps({
                                "seq": m["seq"],
                                "id": m["id"],
                                "sender": m["sender"],
                                "content": m["content"],
                                "timestamp": m["timestamp"],
                            }),
                        }
                    if truncated:
                        yield {
                            "event": "replay_truncated",
                            "data": json.dumps({"limit": SSE_REPLAY_LIMIT}),
                        }

            # 2. Live stream until the client disconnects.
            async with recv_stream:
                async for envelope in recv_stream:
                    out = {
                        "event": envelope["event"],
                        "data": json.dumps(envelope["data"]),
                    }
                    if "id" in envelope:
                        out["id"] = envelope["id"]
                    yield out
        finally:
            _subscribers.get(channel, set()).discard(send_stream)
            send_stream.close()

    # ping=15 emits a comment-line keepalive every 15s so the stream survives
    # the 30–60s idle cutoff most reverse proxies enforce (nginx, Cloudflare,
    # Tailscale Funnel).
    return EventSourceResponse(event_gen(), ping=15)


# ── SSE Transport (MCP) ───────────────────────────────────────────────────────

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
    Route("/events/channel/{channel:path}", endpoint=sse_channel),
    Route("/sse", endpoint=handle_sse),
    Mount("/messages/", app=handle_post_message),
]
if os.path.isdir(WEB_DIR) and not os.environ.get("CLAUDE_BRIDGE_NO_DASHBOARD"):
    # Catch-all static mount goes LAST so it doesn't shadow API routes.
    # html=True makes "/" serve index.html.
    _routes.append(Mount("/", app=StaticFiles(directory=WEB_DIR, html=True)))

_cors_kwargs: dict[str, object] = {
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type"],
}
if CORS_EXTRA_ORIGINS:
    _cors_kwargs["allow_origins"] = CORS_EXTRA_ORIGINS
else:
    # Default: localhost/127.0.0.1/::1 on any port. Browsers will not send
    # cross-origin requests from any other origin without the user having
    # explicitly configured one via CLAUDE_BRIDGE_CORS_ORIGIN.
    _cors_kwargs["allow_origin_regex"] = CORS_LOCALHOST_REGEX

app = Starlette(
    routes=_routes,
    middleware=[
        # CORS first (outermost) so OPTIONS preflight doesn't get blocked by
        # the auth check before browsers can complete the handshake.
        Middleware(CORSMiddleware, **_cors_kwargs),
        # Reject obviously oversized POSTs at the Content-Length header before
        # reading any body.
        Middleware(RequestSizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES),
        # Bearer-token auth — no-op when AUTH_TOKEN is None (opt-in).
        # token_getter reads at request time so monkeypatch and runtime
        # rotation both work without rebuilding the app.
        Middleware(BearerAuthMiddleware, token_getter=lambda: AUTH_TOKEN),
    ],
)


# Direct execution (`python -m claude_bridge` or the `claude-bridge` console
# script) goes through `claude_bridge.cli:main`. This module just defines the
# Starlette `app` and stays importable on its own.
