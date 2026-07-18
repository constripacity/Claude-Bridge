"""Tests for the per-channel live event stream (`GET /events/channel/<name>`).

## Why these tests don't stream over an ASGI transport

`sse_channel` returns an `EventSourceResponse` whose body never ends (it stays
open until the client disconnects, with a 15s keepalive). Driving that through
`httpx.ASGITransport` deadlocks: sse-starlette runs the body generator and a
disconnect-listener in an internal `anyio` task group, and the in-process ASGI
transport can't interleave that infinite response with the test reading from
it — `client.stream(...)` hangs on context exit waiting for the app task that
never completes. (This is what burned the v0.8.0 CI run for its full 6h ceiling.)

`test_auth.py` already established the repo precedent for this: it asserts the
`/sse` *rejection* path over HTTP and covers the un-tearable happy path another
way. We do the same here — every assertion below runs against a **finite** path:

- live delivery / clear / fan-out / isolation → exercise the broker directly by
  registering a subscriber stream exactly as `sse_channel` does, then asserting
  what lands on the receive end. This is the real `insert_message` /
  `clear_channel` / `_broadcast` code, just without the HTTP wrapper.
- backlog replay / cursor_stale / truncation → drive `_replay_backlog`, which is
  finite by construction.
- caps (503) and auth (401) → finite responses, exercised end-to-end via the
  sync `TestClient`. The "auth accepted" case is proven by forcing the handler
  to a finite 503 *after* the middleware lets the request through.
"""

import asyncio
import json

import anyio
import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


# ── Helpers ─────────────────────────────────────────────────────────────────


def reset_broker(monkeypatch):
    """Empty the module-level subscriber registry so tests don't bleed."""
    monkeypatch.setattr(bridge, "_subscribers", {})
    monkeypatch.setattr(bridge, "_dropped_events_total", 0)


def subscribe(channel: str, buffer: int = 100):
    """Register a subscriber on `channel` the same way `sse_channel` does, and
    return its (send, receive) pair. The send side lands in `_subscribers` so
    `_broadcast` will fan events out to the receive side."""
    send, recv = anyio.create_memory_object_stream(max_buffer_size=buffer)
    bridge._subscribers.setdefault(channel, set()).add(send)
    return send, recv


async def next_event(recv, timeout: float = 2.0) -> dict:
    """Await one envelope off a subscriber's receive stream, or fail."""
    return await asyncio.wait_for(recv.receive(), timeout=timeout)


async def drain(agen) -> list[dict]:
    """Collect a finite async generator (e.g. `_replay_backlog`) into a list."""
    return [evt async for evt in agen]


@pytest.fixture
def client(fresh_db):
    return TestClient(bridge.app, base_url="http://localhost")


# ── 1. Subscribe + receive end-to-end (broker) ─────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_receives_new_message(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    _send, recv = subscribe("demo:c")
    # Insert via the broker chokepoint — same path bridge_send + api_send take.
    msg_id, seq, _ts = await bridge.insert_message("demo:c", "windows", "hello")

    env = await next_event(recv)
    assert env["event"] == "message"
    assert env["id"] == msg_id
    assert env["data"]["sender"] == "windows"
    assert env["data"]["content"] == "hello"
    assert env["data"]["seq"] == seq


# ── 2. Clear emits a clear event (broker) ──────────────────────────────────


@pytest.mark.asyncio
async def test_clear_emits_clear_event(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")
    _send, recv = subscribe("demo:c")

    cleared = await bridge.clear_channel("demo:c")
    assert cleared == 2

    env = await next_event(recv)
    assert env["event"] == "clear"
    assert env["data"] == {"channel": "demo:c", "cleared": 2}


# ── 3. Reconnect with a cursor replays backlog (_replay_backlog) ────────────


@pytest.mark.asyncio
async def test_reconnect_with_last_event_id_replays_backlog(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    first_id, _, _ = await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")
    await bridge.insert_message("demo:c", "a", "three")

    events = await drain(bridge._replay_backlog("demo:c", first_id))

    messages = [e for e in events if e["event"] == "message"]
    contents = [json.loads(m["data"])["content"] for m in messages]
    # Backlog contains messages newer than first_id (exclusive): "two", "three".
    assert contents == ["two", "three"]
    assert "one" not in contents
    # `id:` lines must accompany each replayed message so a browser reconnect
    # keeps advancing its Last-Event-ID.
    assert all("id" in m for m in messages)


# ── 4. Cursor-stale on unknown cursor (_replay_backlog) ─────────────────────


@pytest.mark.asyncio
async def test_cursor_stale_on_unknown_last_event_id(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")

    bogus = "00000000-0000-0000-0000-000000000000"
    events = await drain(bridge._replay_backlog("demo:c", bogus))

    assert len(events) == 1
    assert events[0]["event"] == "cursor_stale"
    assert json.loads(events[0]["data"])["since_id"] == bogus
    # Pre-existing messages must NOT leak — the symmetry contract with
    # bridge_receive / api_messages from v0.7.4.
    assert all("one" not in e["data"] and "two" not in e["data"] for e in events)


# ── 5. Replay truncated at SSE_REPLAY_LIMIT (_replay_backlog) ───────────────


@pytest.mark.asyncio
async def test_replay_truncated_when_backlog_too_long(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "SSE_REPLAY_LIMIT", 3)
    first_id, _, _ = await bridge.insert_message("demo:c", "a", "0")
    for i in range(1, 6):  # 5 newer than first_id, limit is 3
        await bridge.insert_message("demo:c", "a", str(i))

    events = await drain(bridge._replay_backlog("demo:c", first_id))

    messages = [e for e in events if e["event"] == "message"]
    truncated = [e for e in events if e["event"] == "replay_truncated"]
    assert len(messages) == 3
    assert len(truncated) == 1
    assert json.loads(truncated[0]["data"])["limit"] == 3


# ── 6. Auth required via Bearer header (TestClient, finite) ─────────────────
#
# To keep the accepted-token assertion finite we force the per-channel cap to 0:
# the middleware runs first (401 on a bad token), and a request that gets *past*
# it lands in the handler, which immediately returns 503 on the cap. So 503 (not
# 401) proves auth was accepted, without ever opening the infinite stream.


@pytest.mark.asyncio
async def test_auth_header_required_when_token_set(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret-abc")
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 0)

    assert client.get("/events/channel/demo:c").status_code == 401
    assert client.get(
        "/events/channel/demo:c", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401

    # Correct token gets past auth → handler rejects on the (zeroed) cap → 503.
    r = client.get("/events/channel/demo:c", headers={"Authorization": "Bearer s3cret-abc"})
    assert r.status_code == 503


# ── 7. Auth via ?token= query param (TestClient, finite) ───────────────────


@pytest.mark.asyncio
async def test_query_tokens_are_rejected_for_events(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret-abc")
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 0)

    assert client.get("/events/channel/demo:c?token=wrong").status_code == 401
    # Even the correct master token is rejected in a URL. Dashboard streams
    # authenticate with an opaque HttpOnly session cookie instead.
    assert client.get("/events/channel/demo:c?token=s3cret-abc").status_code == 401

    # Query-param token must NOT work on non-/events/ paths — the bypass is
    # deliberately scoped narrow to limit the access-log leak surface.
    assert client.get("/api/state?token=s3cret-abc").status_code == 401


# ── 8. Multiple subscribers on the same channel (broker) ───────────────────


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    _s1, recv1 = subscribe("demo:c")
    _s2, recv2 = subscribe("demo:c")

    await bridge.insert_message("demo:c", "a", "broadcast")

    for recv in (recv1, recv2):
        env = await next_event(recv)
        assert env["event"] == "message"
        assert env["data"]["content"] == "broadcast"


# ── 9. Channel isolation (broker) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_channel_isolation(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    _sa, recv_a = subscribe("demo:a")
    _sb, recv_b = subscribe("demo:b")

    await bridge.insert_message("demo:a", "x", "for-a")

    env = await next_event(recv_a)
    assert env["event"] == "message"
    assert env["data"]["content"] == "for-a"
    # The subscriber on channel B must see nothing.
    with pytest.raises(anyio.WouldBlock):
        recv_b.receive_nowait()


# ── 10. Disconnect cleanup — _broadcast drops a dead subscriber ────────────


@pytest.mark.asyncio
async def test_broadcast_discards_closed_subscriber(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    send, recv = subscribe("demo:c")
    assert len(bridge._subscribers["demo:c"]) == 1

    # Simulate the subscriber's stream having gone away (its `sse_channel`
    # generator exited and closed the receive side). The next broadcast must
    # notice the BrokenResourceError and prune it from the set.
    await recv.aclose()
    await bridge._broadcast("demo:c", {"event": "message", "data": {"x": 1}})

    assert len(bridge._subscribers.get("demo:c", set())) == 0
    send.close()


# ── 11. Per-channel cap returns 503 (TestClient, finite) ───────────────────


@pytest.mark.asyncio
async def test_per_channel_cap_returns_503(client, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 1)
    # Occupy the single slot with a dummy subscriber so the next connect is over cap.
    subscribe("demo:c")

    r = client.get("/events/channel/demo:c")
    assert r.status_code == 503
    assert "channel" in r.json()["error"]


# ── 12. Global cap returns 503 (TestClient, finite) ────────────────────────


@pytest.mark.asyncio
async def test_global_cap_returns_503(client, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "MAX_SSE_SUBSCRIBERS", 1)
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 10)  # don't hit per-channel
    # Occupy the single global slot via a different channel.
    subscribe("demo:a")

    r = client.get("/events/channel/demo:b")
    assert r.status_code == 503
    assert "server" in r.json()["error"]
