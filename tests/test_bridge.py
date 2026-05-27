"""Tests for the six bridge_* MCP tools and SQLite persistence."""

import re
import sqlite3

import pytest

import claude_bridge.server as bridge


def text(result):
    """Pull the plain text out of a list[TextContent] tool response."""
    assert len(result) == 1
    return result[0].text


def extract_id(send_result_text: str) -> str:
    m = re.search(r"id: ([0-9a-f-]{36})", send_result_text)
    assert m, f"no id in: {send_result_text!r}"
    return m.group(1)


# ── bridge_ping ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_on_empty_db(fresh_db):
    out = text(await bridge.dispatch_tool("bridge_ping", {}))
    assert "Claude Bridge online" in out
    assert "Channels: 0" in out
    assert "Messages: 0" in out


# ── bridge_send / bridge_receive ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_then_receive(fresh_db):
    await bridge.dispatch_tool("bridge_send", {
        "channel": "proj:orchestrator",
        "sender": "windows",
        "content": '{"type":"task","phase":1}',
    })
    out = text(await bridge.dispatch_tool("bridge_receive", {"channel": "proj:orchestrator"}))
    assert "proj:orchestrator" in out
    assert "1 message(s)" in out
    assert "windows" in out
    assert '"type":"task"' in out


@pytest.mark.asyncio
async def test_receive_empty_channel(fresh_db):
    out = text(await bridge.dispatch_tool("bridge_receive", {"channel": "nope"}))
    assert "no messages" in out


@pytest.mark.asyncio
async def test_receive_since_id_returns_only_newer(fresh_db):
    send1 = text(await bridge.dispatch_tool("bridge_send", {
        "channel": "c", "sender": "a", "content": "one",
    }))
    first_id = extract_id(send1)
    await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "a", "content": "two"})
    await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "a", "content": "three"})

    out = text(await bridge.dispatch_tool("bridge_receive", {
        "channel": "c", "since_id": first_id,
    }))
    assert "2 message(s)" in out
    assert "two" in out
    assert "three" in out
    assert "\none\n" not in out  # the first message is excluded


@pytest.mark.asyncio
async def test_receive_limit_applies(fresh_db):
    for i in range(10):
        await bridge.dispatch_tool("bridge_send", {
            "channel": "c", "sender": "a", "content": f"msg-{i}",
        })
    out = text(await bridge.dispatch_tool("bridge_receive", {"channel": "c", "limit": 3}))
    assert "3 message(s)" in out
    # When no since_id, we return the most recent N
    assert "msg-9" in out
    assert "msg-7" in out
    assert "msg-0" not in out


# ── bridge_channels ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channels_lists_active(fresh_db):
    await bridge.dispatch_tool("bridge_send", {"channel": "a:x", "sender": "s", "content": "1"})
    await bridge.dispatch_tool("bridge_send", {"channel": "a:x", "sender": "s", "content": "2"})
    await bridge.dispatch_tool("bridge_send", {"channel": "b:y", "sender": "s", "content": "1"})

    out = text(await bridge.dispatch_tool("bridge_channels", {}))
    assert "Active channels (2, 3 total messages)" in out
    assert "a:x" in out
    assert "b:y" in out
    assert "(2 msgs" in out
    assert "(1 msgs" in out


@pytest.mark.asyncio
async def test_channels_empty(fresh_db):
    out = text(await bridge.dispatch_tool("bridge_channels", {}))
    assert "No active channels" in out


# ── bridge_clear ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_removes_messages(fresh_db):
    for _ in range(4):
        await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "s", "content": "x"})
    out = text(await bridge.dispatch_tool("bridge_clear", {"channel": "c"}))
    assert "Cleared 4 message(s)" in out

    after = text(await bridge.dispatch_tool("bridge_receive", {"channel": "c"}))
    assert "no messages" in after


@pytest.mark.asyncio
async def test_clear_only_affects_target_channel(fresh_db):
    await bridge.dispatch_tool("bridge_send", {"channel": "keep", "sender": "s", "content": "x"})
    await bridge.dispatch_tool("bridge_send", {"channel": "drop", "sender": "s", "content": "x"})
    await bridge.dispatch_tool("bridge_clear", {"channel": "drop"})

    out = text(await bridge.dispatch_tool("bridge_receive", {"channel": "keep"}))
    assert "1 message(s)" in out


# ── bridge_status ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_shows_recent_per_channel(fresh_db):
    for i in range(7):
        await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "s", "content": f"m{i}"})
    out = text(await bridge.dispatch_tool("bridge_status", {"per_channel": 3}))
    assert "[c] — 7 total" in out
    assert "m6" in out
    assert "m4" in out
    assert "m0" not in out


@pytest.mark.asyncio
async def test_status_long_content_truncated(fresh_db):
    long = "x" * 200
    await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "s", "content": long})
    out = text(await bridge.dispatch_tool("bridge_status", {}))
    assert "…" in out  # truncation marker
    assert "xxxxxxxx" in out


# ── Persistence ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_messages_persist_across_connection_reset(fresh_db, monkeypatch):
    """Simulate a server restart: close the connection, null it out, reopen."""
    await bridge.dispatch_tool("bridge_send", {
        "channel": "persist:test", "sender": "windows", "content": "survives restart",
    })

    bridge._conn.close()
    monkeypatch.setattr(bridge, "_conn", None)

    out = text(await bridge.dispatch_tool("bridge_receive", {"channel": "persist:test"}))
    assert "survives restart" in out
    assert "windows" in out


@pytest.mark.asyncio
async def test_seq_is_monotonic(fresh_db):
    """seq is the SQLite rowid — must strictly increase per insert."""
    for _ in range(5):
        await bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "s", "content": "x"})
    seqs = [row[0] for row in bridge.db().execute("SELECT seq FROM messages ORDER BY seq").fetchall()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


@pytest.mark.asyncio
async def test_id_uniqueness_enforced(fresh_db):
    """The id column has a UNIQUE constraint — duplicate inserts should fail."""
    conn = bridge.db()
    conn.execute(
        "INSERT INTO messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("fixed-id", "c", "s", "x", "2026-01-01T00:00:00Z"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            ("fixed-id", "c", "s", "y", "2026-01-01T00:00:01Z"),
        )


# ── datetime regression ─────────────────────────────────────────────────────

def test_utc_now_iso_format():
    """Format should be RFC3339-ish with 'Z' suffix and no deprecation warning."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        ts = bridge.utc_now_iso()
    assert ts.endswith("Z")
    assert "T" in ts
    # 2026-05-27T01:23:45.678901Z
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)
