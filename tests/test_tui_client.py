"""Tests for tui_client.py — the async HTTP client + helper functions used by the TUI.

The HTTP client is exercised by mounting it against the real Starlette ASGI app
via httpx.ASGITransport, so we get full end-to-end coverage of the JSON API
contract without standing up a real server.
"""

import asyncio

import httpx
import pytest

import claude_bridge.server as bridge
from claude_bridge.tui_client import (
    TYPE_COLORS,
    BridgeClient,
    BridgeError,
    classify_message,
    group_channels,
    sender_color,
)


# ── Helper functions (pure, no I/O) ──────────────────────────────────────────

def test_sender_color_overrides():
    assert sender_color("mac") == "#58a6ff"
    assert sender_color("windows") == "#d97706"
    assert sender_color("linux") == "#3fb950"


def test_sender_color_unknown_is_stable_and_in_palette():
    from claude_bridge.tui_client import SENDER_PALETTE
    c1 = sender_color("vps-01")
    c2 = sender_color("vps-01")
    assert c1 == c2
    assert c1 in SENDER_PALETTE


def test_classify_message_task():
    assert classify_message('{"type": "task", "phase": 1}') == "TASK"


def test_classify_message_result():
    assert classify_message('{"type": "result", "status": "ok"}') == "RESULT"


def test_classify_message_plain_text():
    assert classify_message("hello world") == "TXT"


def test_classify_message_empty():
    assert classify_message("") == "TXT"
    assert classify_message("   ") == "TXT"


def test_classify_message_invalid_json():
    assert classify_message("{not json") == "TXT"


def test_classify_message_array_not_object():
    # JSON arrays don't carry a type tag
    assert classify_message("[1, 2, 3]") == "TXT"


def test_type_colors_cover_design_set():
    for t in ("TASK", "RESULT", "ACK", "ERR", "HB", "TXT"):
        assert t in TYPE_COLORS


def test_group_channels_by_prefix():
    channels = [
        {"id": "demo:orchestrator", "group": "demo", "name": "orchestrator", "count": 1},
        {"id": "demo:worker", "group": "demo", "name": "worker", "count": 2},
        {"id": "general:sync", "group": "general", "name": "sync", "count": 3},
        {"id": "loose", "group": "", "name": "loose", "count": 4},
    ]
    groups = group_channels(channels)
    assert set(groups.keys()) == {"demo", "general", ""}
    assert len(groups["demo"]) == 2
    assert len(groups["general"]) == 1


# ── BridgeClient — full async lifecycle against the real ASGI app ────────────

@pytest.fixture
def asgi_client(fresh_db):
    """A BridgeClient bound to the in-process ASGI app — no real socket."""
    transport = httpx.ASGITransport(app=bridge.app)
    client = BridgeClient(base_url="http://testserver")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=5.0)
    return client


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.new_event_loop().run_until_complete(coro)


def test_state_round_trip(asgi_client):
    async def go():
        try:
            state = await asgi_client.state()
            assert state["service"] == "claude-bridge"
            assert state["channels"] == []

            # send a message, then state should reflect it
            sent = await asgi_client.send("demo:orchestrator", "windows", '{"type":"task","phase":1}')
            assert "id" in sent and "seq" in sent

            state2 = await asgi_client.state()
            assert state2["total_messages"] == 1
            assert len(state2["channels"]) == 1
            assert state2["channels"][0]["id"] == "demo:orchestrator"
        finally:
            await asgi_client.aclose()
    run(go())


def test_messages_and_detail(asgi_client):
    async def go():
        try:
            sent = await asgi_client.send("demo:worker", "mac", '{"type":"result","status":"ok"}')
            msgs = await asgi_client.messages("demo:worker")
            assert msgs["channel"] == "demo:worker"
            assert len(msgs["messages"]) == 1
            assert msgs["messages"][0]["is_json"] is True

            detail = await asgi_client.message_detail(sent["id"])
            assert detail["channel"] == "demo:worker"
            assert detail["is_json"] is True
            assert detail["content_parsed"]["status"] == "ok"
        finally:
            await asgi_client.aclose()
    run(go())


def test_clear(asgi_client):
    async def go():
        try:
            await asgi_client.send("demo:events", "windows", "first")
            await asgi_client.send("demo:events", "windows", "second")
            cleared = await asgi_client.clear("demo:events")
            assert cleared["cleared"] == 2

            after = await asgi_client.messages("demo:events")
            assert after["messages"] == []
        finally:
            await asgi_client.aclose()
    run(go())


def test_send_bad_request_raises_bridge_error(asgi_client):
    async def go():
        try:
            with pytest.raises(BridgeError) as exc:
                # empty content is rejected
                await asgi_client.send("demo:x", "windows", "")
            assert exc.value.status == 400
        finally:
            await asgi_client.aclose()
    run(go())


def test_messages_since_id(asgi_client):
    async def go():
        try:
            first = await asgi_client.send("demo:c", "windows", "one")
            await asgi_client.send("demo:c", "windows", "two")
            await asgi_client.send("demo:c", "windows", "three")

            tail = await asgi_client.messages("demo:c", since_id=first["id"])
            # since_id is exclusive — only "two" and "three" come back
            previews = [m["preview"] for m in tail["messages"]]
            assert previews == ["two", "three"]
        finally:
            await asgi_client.aclose()
    run(go())


# ── BridgeClient token support ──────────────────────────────────────────────

def _build_asgi_client(token: str | None = None) -> BridgeClient:
    transport = httpx.ASGITransport(app=bridge.app)
    headers = {"Authorization": f"Bearer {token}"} if token else None
    client = BridgeClient(base_url="http://testserver", token=token)
    client._client = httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=5.0, headers=headers
    )
    return client


def test_token_client_succeeds_against_auth_enabled_bridge(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret")
    client = _build_asgi_client(token="s3cret")

    async def go():
        try:
            state = await client.state()
            assert state["service"] == "claude-bridge"
        finally:
            await client.aclose()
    run(go())


def test_tokenless_client_rejected_by_auth_enabled_bridge(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret")
    client = _build_asgi_client(token=None)

    async def go():
        try:
            with pytest.raises(BridgeError) as exc:
                await client.state()
            assert exc.value.status == 401
        finally:
            await client.aclose()
    run(go())


def test_wrong_token_rejected(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret")
    client = _build_asgi_client(token="not-the-token")

    async def go():
        try:
            with pytest.raises(BridgeError) as exc:
                await client.state()
            assert exc.value.status == 401
        finally:
            await client.aclose()
    run(go())
