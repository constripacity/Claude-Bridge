"""Tests for the JSON HTTP API used by the web dashboard."""

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


@pytest.fixture
def client(fresh_db):
    """TestClient against the live ASGI app, with the per-test SQLite fixture."""
    return TestClient(bridge.app)


# ── /status (existing, but version field is new) ─────────────────────────────

def test_status(client):
    r = client.get("/status")
    assert r.status_code == 200
    d = r.json()
    assert d["service"] == "claude-bridge"
    assert d["status"] == "online"
    assert d["version"] == bridge.VERSION
    assert d["total_messages"] == 0
    assert d["channels"] == {}


# ── /api/state ──────────────────────────────────────────────────────────────

def test_api_state_empty(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    d = r.json()
    assert d["service"] == "claude-bridge"
    assert d["version"] == bridge.VERSION
    assert d["total_messages"] == 0
    assert d["channels"] == []
    assert d["uptime_seconds"] >= 0
    assert ":" in d["uptime_human"]


def test_api_state_with_data(client):
    client.post("/api/send", json={"channel": "demo:orchestrator", "sender": "mac",     "content": "one"})
    client.post("/api/send", json={"channel": "demo:orchestrator", "sender": "windows", "content": "two"})
    client.post("/api/send", json={"channel": "demo:worker",       "sender": "windows", "content": "three"})

    d = client.get("/api/state").json()
    assert d["total_messages"] == 3
    assert len(d["channels"]) == 2
    orch = next(c for c in d["channels"] if c["id"] == "demo:orchestrator")
    assert orch == {
        **orch,
        "group": "demo",
        "name": "orchestrator",
        "count": 2,
        "senders": ["mac", "windows"],
    }
    assert orch["last_ts"]  # short HH:MM:SS form populated


def test_api_state_channel_without_group(client):
    """Channels without ':' should still appear, with group='' and name=full id."""
    client.post("/api/send", json={"channel": "ungrouped", "sender": "mac", "content": "x"})
    d = client.get("/api/state").json()
    assert d["channels"][0] == {**d["channels"][0], "group": "", "name": "ungrouped"}


# ── /api/messages ───────────────────────────────────────────────────────────

def test_api_messages_requires_channel(client):
    r = client.get("/api/messages")
    assert r.status_code == 400
    assert "channel" in r.json()["error"]


def test_api_messages_empty(client):
    r = client.get("/api/messages?channel=nope")
    assert r.status_code == 200
    assert r.json() == {"channel": "nope", "messages": []}


def test_api_messages_detects_json(client):
    client.post("/api/send", json={"channel": "c", "sender": "mac", "content": '{"k":1}'})
    client.post("/api/send", json={"channel": "c", "sender": "mac", "content": "plain text"})
    msgs = client.get("/api/messages?channel=c").json()["messages"]
    assert msgs[0]["is_json"] is True
    assert msgs[1]["is_json"] is False


def test_api_messages_since_id(client):
    r1 = client.post("/api/send", json={"channel": "c", "sender": "a", "content": "one"})
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": "two"})
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": "three"})
    since = r1.json()["id"]
    msgs = client.get(f"/api/messages?channel=c&since_id={since}").json()["messages"]
    assert [m["preview"] for m in msgs] == ["two", "three"]


def test_api_messages_truncates_preview(client):
    long = "x" * 500
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": long})
    msgs = client.get("/api/messages?channel=c").json()["messages"]
    assert msgs[0]["preview"].endswith("…")
    assert len(msgs[0]["preview"]) == 201  # 200 chars + ellipsis


def test_api_messages_limit_clamped(client):
    for i in range(5):
        client.post("/api/send", json={"channel": "c", "sender": "a", "content": f"m{i}"})
    # limit=1 honored
    assert len(client.get("/api/messages?channel=c&limit=1").json()["messages"]) == 1
    # limit=0 clamped up to 1
    assert len(client.get("/api/messages?channel=c&limit=0").json()["messages"]) == 1


# ── /api/messages/{id} ──────────────────────────────────────────────────────

def test_api_message_detail_404(client):
    r = client.get("/api/messages/does-not-exist")
    assert r.status_code == 404


def test_api_message_detail_parses_json(client):
    sent = client.post("/api/send", json={
        "channel": "c", "sender": "mac",
        "content": '{"task":"test","n":42}',
    }).json()
    d = client.get(f"/api/messages/{sent['id']}").json()
    assert d["channel"] == "c"
    assert d["sender"] == "mac"
    assert d["is_json"] is True
    assert d["content_parsed"] == {"task": "test", "n": 42}
    assert d["bytes"] == len('{"task":"test","n":42}'.encode())


def test_api_message_detail_plain_text(client):
    sent = client.post("/api/send", json={"channel": "c", "sender": "mac", "content": "hi"}).json()
    d = client.get(f"/api/messages/{sent['id']}").json()
    assert d["is_json"] is False
    assert d["content_parsed"] is None
    assert d["content"] == "hi"


# ── /api/send ───────────────────────────────────────────────────────────────

def test_api_send_round_trip(client):
    r = client.post("/api/send", json={
        "channel": "demo:worker", "sender": "windows", "content": "hello",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["channel"] == "demo:worker"
    assert d["seq"] >= 1
    assert d["id"]
    # Confirm it lands in /api/messages
    msgs = client.get("/api/messages?channel=demo:worker").json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["id"] == d["id"]


def test_api_send_matches_mcp_send(client):
    """Dashboard sends should be indistinguishable from MCP bridge_send calls."""
    import asyncio
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": "via http"})
    asyncio.run(bridge.dispatch_tool("bridge_send", {"channel": "c", "sender": "a", "content": "via mcp"}))
    msgs = client.get("/api/messages?channel=c").json()["messages"]
    assert [m["preview"] for m in msgs] == ["via http", "via mcp"]
    # Both should look identical to a downstream consumer (same shape, same sender)
    assert all(set(m.keys()) == {"seq", "id", "ts", "ts_full", "sender", "is_json", "preview"} for m in msgs)


def test_api_send_validation(client):
    cases = [
        ({},                                                          "channel"),
        ({"channel": "x"},                                            "sender"),
        ({"channel": "x", "sender": "y"},                             "content"),
        ({"channel": "",  "sender": "y", "content": "z"},             "channel"),
        ({"channel": "x", "sender": "",  "content": "z"},             "sender"),
        ({"channel": "x", "sender": "y", "content": ""},              "content"),
    ]
    for body, expected_field in cases:
        r = client.post("/api/send", json=body)
        assert r.status_code == 400, body
        assert expected_field in r.json()["error"]


def test_api_send_rejects_non_json(client):
    r = client.post("/api/send", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


# ── /api/clear ──────────────────────────────────────────────────────────────

def test_api_clear(client):
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": "x"})
    client.post("/api/send", json={"channel": "c", "sender": "a", "content": "y"})
    r = client.post("/api/clear", json={"channel": "c"})
    assert r.status_code == 200
    assert r.json() == {"channel": "c", "cleared": 2}
    assert client.get("/api/messages?channel=c").json()["messages"] == []


def test_api_clear_validation(client):
    assert client.post("/api/clear", json={}).status_code == 400
    assert client.post("/api/clear", json={"channel": ""}).status_code == 400


# ── Static dashboard serving ────────────────────────────────────────────────

def test_dashboard_html_served_when_web_dir_exists(client):
    """If web/index.html exists, GET / should return the dashboard HTML."""
    import os
    if not os.path.isdir(bridge.WEB_DIR):
        pytest.skip("web/ directory not present in this build")
    r = client.get("/")
    assert r.status_code == 200
    assert "Claude Bridge" in r.text
    assert "<div id=\"root\"></div>" in r.text


def test_dashboard_jsx_served_as_static(client):
    import os
    if not os.path.isfile(os.path.join(bridge.WEB_DIR, "shared.jsx")):
        pytest.skip("shared.jsx not present")
    r = client.get("/shared.jsx")
    assert r.status_code == 200
    assert "SENDER_COLORS" in r.text
