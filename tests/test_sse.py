"""Tests for the per-channel live event stream (`GET /events/channel/<name>`).

Uses httpx.AsyncClient + ASGITransport (same pattern as test_tui_client.py)
so we exercise the real Starlette app — middleware, routing, the broker — but
without standing up a real socket.

SSE wire format we parse here:

    event: <name>\n
    id: <msg-id>\n          (optional)
    data: <json>\n
    \n                       (event boundary)
"""

import asyncio
import json

import httpx
import pytest

import claude_bridge.server as bridge


# ── Helpers ─────────────────────────────────────────────────────────────────


def asgi_streaming_client(base_url: str = "http://testserver") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=bridge.app)
    return httpx.AsyncClient(transport=transport, base_url=base_url, timeout=5.0)


async def collect_events(response, count: int, timeout: float = 3.0) -> list[dict]:
    """Read at least `count` events off an SSE stream or raise TimeoutError."""
    events: list[dict] = []
    current: dict = {}

    async def reader():
        nonlocal current
        async for line in response.aiter_lines():
            if line == "":
                if current:
                    events.append(current)
                    current = {}
                    if len(events) >= count:
                        return
            elif line.startswith(":"):
                continue
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = line[6:]
            elif line.startswith("id: "):
                current["id"] = line[4:]

    try:
        await asyncio.wait_for(reader(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return events


def reset_broker(monkeypatch):
    """Empty the module-level subscriber registry so tests don't bleed."""
    monkeypatch.setattr(bridge, "_subscribers", {})
    monkeypatch.setattr(bridge, "_dropped_events_total", 0)


# ── 1. Subscribe + receive end-to-end ──────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_receives_new_message(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    async with asgi_streaming_client() as client:
        async with client.stream("GET", "/events/channel/demo:c") as r:
            assert r.status_code == 200
            # Give the subscriber a chance to register before the writer fires.
            await asyncio.sleep(0.05)
            # Send via the broker chokepoint — same path bridge_send + api_send take.
            await bridge.insert_message("demo:c", "windows", "hello")
            events = await collect_events(r, count=1, timeout=2.0)

    assert len(events) >= 1
    msg = next(e for e in events if e.get("event") == "message")
    payload = json.loads(msg["data"])
    assert payload["sender"] == "windows"
    assert payload["content"] == "hello"
    assert msg["id"] == payload["id"]


# ── 2. Clear emits a clear event ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_emits_clear_event(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")
    async with asgi_streaming_client() as client:
        async with client.stream("GET", "/events/channel/demo:c") as r:
            await asyncio.sleep(0.05)
            cleared = await bridge.clear_channel("demo:c")
            events = await collect_events(r, count=1, timeout=2.0)

    assert cleared == 2
    clear_evt = next(e for e in events if e.get("event") == "clear")
    payload = json.loads(clear_evt["data"])
    assert payload == {"channel": "demo:c", "cleared": 2}


# ── 3. Reconnect with Last-Event-ID replays backlog ────────────────────────


@pytest.mark.asyncio
async def test_reconnect_with_last_event_id_replays_backlog(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    first_id, _, _ = await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")
    await bridge.insert_message("demo:c", "a", "three")

    async with asgi_streaming_client() as client:
        async with client.stream(
            "GET", "/events/channel/demo:c",
            headers={"Last-Event-ID": first_id},
        ) as r:
            events = await collect_events(r, count=2, timeout=2.0)

    messages = [e for e in events if e.get("event") == "message"]
    contents = [json.loads(m["data"])["content"] for m in messages]
    # Backlog contains messages newer than first_id (exclusive), so "two" and "three".
    assert contents == ["two", "three"]
    assert "one" not in contents


# ── 4. Cursor-stale on unknown Last-Event-ID ───────────────────────────────


@pytest.mark.asyncio
async def test_cursor_stale_on_unknown_last_event_id(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    await bridge.insert_message("demo:c", "a", "one")
    await bridge.insert_message("demo:c", "a", "two")

    bogus = "00000000-0000-0000-0000-000000000000"
    async with asgi_streaming_client() as client:
        async with client.stream(
            "GET", "/events/channel/demo:c",
            headers={"Last-Event-ID": bogus},
        ) as r:
            events = await collect_events(r, count=1, timeout=2.0)

    stale = next(e for e in events if e.get("event") == "cursor_stale")
    assert json.loads(stale["data"])["since_id"] == bogus
    # Pre-existing messages must NOT have leaked into the response — the
    # symmetry contract with bridge_receive / api_messages from v0.7.4.
    assert all("one" not in (e.get("data") or "") for e in events)
    assert all("two" not in (e.get("data") or "") for e in events)


# ── 5. Replay truncated at SSE_REPLAY_LIMIT ────────────────────────────────


@pytest.mark.asyncio
async def test_replay_truncated_when_backlog_too_long(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "SSE_REPLAY_LIMIT", 3)
    first_id, _, _ = await bridge.insert_message("demo:c", "a", "0")
    for i in range(1, 6):  # 5 more → 5 newer than first_id, limit is 3
        await bridge.insert_message("demo:c", "a", str(i))

    async with asgi_streaming_client() as client:
        async with client.stream(
            "GET", "/events/channel/demo:c",
            headers={"Last-Event-ID": first_id},
        ) as r:
            events = await collect_events(r, count=4, timeout=2.0)

    messages = [e for e in events if e.get("event") == "message"]
    truncated = [e for e in events if e.get("event") == "replay_truncated"]
    assert len(messages) == 3
    assert len(truncated) == 1
    assert json.loads(truncated[0]["data"])["limit"] == 3


# ── 6. Auth required via Bearer header ─────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_header_required_when_token_set(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret-abc")
    async with asgi_streaming_client() as client:
        r = await client.get("/events/channel/demo:c")
        assert r.status_code == 401

        # Wrong token also rejected.
        r = await client.get(
            "/events/channel/demo:c",
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401

        # Correct token connects (we don't bother streaming, just confirm 200).
        async with client.stream(
            "GET", "/events/channel/demo:c",
            headers={"Authorization": "Bearer s3cret-abc"},
        ) as r:
            assert r.status_code == 200


# ── 7. Auth via ?token= query param ────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_via_query_param_for_events(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret-abc")
    async with asgi_streaming_client() as client:
        r = await client.get("/events/channel/demo:c?token=wrong")
        assert r.status_code == 401

        async with client.stream("GET", "/events/channel/demo:c?token=s3cret-abc") as r:
            assert r.status_code == 200

    # Query-param token must NOT work on non-/events/ paths — the bypass is
    # deliberately scoped narrow to limit the access-log leak surface.
    async with asgi_streaming_client() as client:
        r = await client.get("/api/state?token=s3cret-abc")
        assert r.status_code == 401


# ── 8. Multiple subscribers on the same channel ────────────────────────────


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    async with asgi_streaming_client() as c1, asgi_streaming_client() as c2:
        async with c1.stream("GET", "/events/channel/demo:c") as r1, \
                   c2.stream("GET", "/events/channel/demo:c") as r2:
            await asyncio.sleep(0.05)
            await bridge.insert_message("demo:c", "a", "broadcast")
            e1, e2 = await asyncio.gather(
                collect_events(r1, count=1, timeout=2.0),
                collect_events(r2, count=1, timeout=2.0),
            )

    for events in (e1, e2):
        msg = next(e for e in events if e.get("event") == "message")
        assert json.loads(msg["data"])["content"] == "broadcast"


# ── 9. Channel isolation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_channel_isolation(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    async with asgi_streaming_client() as ca, asgi_streaming_client() as cb:
        async with ca.stream("GET", "/events/channel/demo:a") as ra, \
                   cb.stream("GET", "/events/channel/demo:b") as rb:
            await asyncio.sleep(0.05)
            await bridge.insert_message("demo:a", "x", "for-a")
            # Reader on channel B must not see anything.
            events_a = await collect_events(ra, count=1, timeout=1.5)
            events_b = await collect_events(rb, count=1, timeout=0.5)

    assert any(e.get("event") == "message" for e in events_a)
    assert all(e.get("event") != "message" for e in events_b)


# ── 10. Disconnect cleanup ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect_removes_subscriber(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    async with asgi_streaming_client() as client:
        async with client.stream("GET", "/events/channel/demo:c") as _:
            await asyncio.sleep(0.05)
            assert len(bridge._subscribers.get("demo:c", set())) == 1
        # After context exit, the EventSourceResponse generator's `finally`
        # should run and discard the subscriber. Give it a tick.
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    assert len(bridge._subscribers.get("demo:c", set())) == 0


# ── 11. Per-channel cap returns 503 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_channel_cap_returns_503(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 1)
    async with asgi_streaming_client() as c1, asgi_streaming_client() as c2:
        async with c1.stream("GET", "/events/channel/demo:c") as r1:
            assert r1.status_code == 200
            await asyncio.sleep(0.05)
            # The second subscriber to the same channel should be rejected.
            r2 = await c2.get("/events/channel/demo:c")
            assert r2.status_code == 503
            assert "channel" in r2.json()["error"]


# ── 12. Global cap returns 503 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_global_cap_returns_503(fresh_db, monkeypatch):
    reset_broker(monkeypatch)
    monkeypatch.setattr(bridge, "MAX_SSE_SUBSCRIBERS", 1)
    monkeypatch.setattr(bridge, "MAX_SSE_PER_CHANNEL", 10)  # don't hit per-channel
    async with asgi_streaming_client() as c1, asgi_streaming_client() as c2:
        async with c1.stream("GET", "/events/channel/demo:a") as r1:
            assert r1.status_code == 200
            await asyncio.sleep(0.05)
            # Different channel, but global cap is 1.
            r2 = await c2.get("/events/channel/demo:b")
            assert r2.status_code == 503
            assert "server" in r2.json()["error"]
