"""Integration coverage for the forward v1 reliability/security features."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys

import anyio
import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


def text(result):
    return result[0].text


def message_id(result) -> str:
    for line in text(result).splitlines():
        if line.strip().startswith("id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("message id missing")


def test_cli_configuration_is_applied_before_server_import(tmp_path):
    script = r"""
import json
import claude_bridge.cli as cli
assert 'claude_bridge.server' not in __import__('sys').modules
def inspect(_args):
    import claude_bridge.server as server
    print(json.dumps({
        'db': server.DB_PATH,
        'auth': server.AUTH_TOKEN,
        'dashboard_off': server.SETTINGS.no_dashboard,
        'retention': server.RETENTION_DAYS,
        'audit': server.AUDIT_ENABLED,
    }))
    return 0
cli._run_http = inspect
raise SystemExit(cli.main([
    '--db', __import__('sys').argv[1], '--auth-token', 'secret-value',
    '--no-dashboard', '--retention-days', '5', '--audit-log'
]))
"""
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("CLAUDE_BRIDGE_"):
            env.pop(name)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "configured.db")],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    configured = json.loads(result.stdout.strip())
    assert configured == {
        "db": str(tmp_path / "configured.db"),
        "auth": "secret-value",
        "dashboard_off": True,
        "retention": 5,
        "audit": True,
    }


def test_cli_reports_invalid_environment_without_traceback(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_BRIDGE_DB"] = str(tmp_path / "invalid-config.db")
    env["CLAUDE_BRIDGE_MAX_SSE"] = "many"
    result = subprocess.run(
        [sys.executable, "-m", "claude_bridge", "--port", "0"],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "CLAUDE_BRIDGE_MAX_SSE must be an integer" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_database_is_owner_only(fresh_db):
    bridge.db()
    assert fresh_db.stat().st_mode & 0o777 == 0o600


def test_wal_setup_retries_a_transient_first_start_lock(monkeypatch):
    class Cursor:
        def fetchone(self):
            return ("wal",)

    class Connection:
        attempts = 0

        def execute(self, sql):
            assert sql == "PRAGMA journal_mode=WAL"
            self.attempts += 1
            if self.attempts < 3:
                raise sqlite3.OperationalError("database is locked")
            return Cursor()

    connection = Connection()
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)
    bridge._enable_wal_mode(connection)
    assert connection.attempts == 3


@pytest.mark.asyncio
async def test_idempotent_send_replays_without_duplicate(fresh_db):
    args = {
        "channel": "project:worker",
        "sender": "codex",
        "content": "build complete",
        "idempotency_key": "task-42-result",
    }
    first = await bridge.dispatch_tool("bridge_send", args)
    second = await bridge.dispatch_tool("bridge_send", args)

    assert message_id(first) == message_id(second)
    assert "deduplicated: true" in text(second)
    assert bridge.db().execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1

    with pytest.raises(Exception, match="different message content"):
        await bridge.dispatch_tool("bridge_send", {**args, "content": "changed"})


@pytest.mark.asyncio
async def test_clear_resets_idempotency_key_without_dangling_record(fresh_db):
    args = {
        "channel": "project:reset",
        "sender": "codex",
        "content": "send again after an explicit reset",
        "idempotency_key": "reset-key",
    }
    first = await bridge.dispatch_tool("bridge_send", args)
    await bridge.clear_channel("project:reset")
    second = await bridge.dispatch_tool("bridge_send", args)

    assert message_id(first) != message_id(second)
    assert "deduplicated: true" not in text(second)
    assert bridge.db().execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
    record = bridge.reliability_store().get_idempotency(
        channel="project:reset", sender="codex", key="reset-key"
    )
    assert record is not None
    assert record.expires_at is None


@pytest.mark.asyncio
async def test_structured_envelope_and_machine_result(fresh_db):
    response = await bridge.dispatch_tool(
        "bridge_send",
        {
            "channel": "project:tasks",
            "sender": "orchestrator",
            "message": {
                "schema_version": 1,
                "type": "task",
                "thread_id": "thread-7",
                "content": {"action": "run_tests"},
            },
        },
        structured=True,
    )
    _content, data = response
    assert data["channel"] == "project:tasks"

    _content, received = await bridge.dispatch_tool(
        "bridge_receive", {"channel": "project:tasks"}, structured=True
    )
    assert received["messages"][0]["message"]["type"] == "task"
    assert received["messages"][0]["message"]["content"]["action"] == "run_tests"


@pytest.mark.asyncio
async def test_acknowledged_consumer_resumes_after_cursor(fresh_db):
    first = await bridge.dispatch_tool(
        "bridge_send", {"channel": "c", "sender": "a", "content": "one"}
    )
    await bridge.dispatch_tool(
        "bridge_send", {"channel": "c", "sender": "a", "content": "two"}
    )
    await bridge.dispatch_tool(
        "bridge_ack",
        {
            "channel": "c",
            "consumer_id": "worker-mac",
            "message_id": message_id(first),
        },
    )
    _content, result = await bridge.dispatch_tool(
        "bridge_receive",
        {"channel": "c", "consumer_id": "worker-mac"},
        structured=True,
    )
    assert [message["content"] for message in result["messages"]] == ["two"]


@pytest.mark.asyncio
async def test_bridge_wait_wakes_for_new_message(fresh_db):
    first = await bridge.dispatch_tool(
        "bridge_send", {"channel": "c", "sender": "a", "content": "one"}
    )

    async def wait():
        return await bridge.dispatch_tool(
            "bridge_wait",
            {
                "channel": "c",
                "since_id": message_id(first),
                "timeout_seconds": 2,
            },
            structured=True,
        )

    task = asyncio.create_task(wait())
    await asyncio.sleep(0)
    await bridge.dispatch_tool(
        "bridge_send", {"channel": "c", "sender": "b", "content": "arrived"}
    )
    _content, result = await task
    assert result["timed_out"] is False
    assert [message["content"] for message in result["messages"]] == ["arrived"]


@pytest.mark.asyncio
async def test_bridge_wait_nonzero_timeout_is_normal(fresh_db):
    _content, result = await bridge.dispatch_tool(
        "bridge_wait",
        {
            "channel": "empty:wait",
            "consumer_id": "idle-consumer",
            "timeout_seconds": 0.01,
        },
        structured=True,
    )
    assert result["messages"] == []
    assert result["timed_out"] is True


def test_dashboard_uses_opaque_revocable_session(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "master-secret")
    with TestClient(bridge.app, base_url="http://localhost") as client:
        login = client.post(
            "/api/session",
            headers={"Authorization": "Bearer master-secret"},
        )
        assert login.status_code == 200
        session_id = client.cookies.get("claude_bridge_session")
        assert session_id and session_id != "master-secret"
        assert client.get("/api/state").status_code == 200
        assert client.get("/api/session").json()["authenticated"] is True

        assert client.delete("/api/session").status_code == 200
        assert client.get("/api/state").status_code == 401


def test_dashboard_cookie_cannot_mint_descendant_sessions(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "master-secret")
    with TestClient(bridge.app, base_url="http://localhost") as client:
        first = client.post(
            "/api/session", headers={"Authorization": "Bearer master-secret"}
        )
        assert first.status_code == 200
        old_session = client.cookies.get("claude_bridge_session")
        assert old_session

        # The valid cookie is present, but only the master Bearer credential
        # may create or rotate a browser session.
        assert client.post("/api/session").status_code == 401

        rotated = client.post(
            "/api/session", headers={"Authorization": "Bearer master-secret"}
        )
        assert rotated.status_code == 200
        new_session = client.cookies.get("claude_bridge_session")
        assert new_session and new_session != old_session
        assert bridge._dashboard_sessions.validate(old_session) is False
        assert bridge._dashboard_sessions.validate(new_session) is True


def test_default_app_rejects_non_loopback_host_header(fresh_db):
    with TestClient(bridge.app, base_url="http://localhost") as client:
        assert client.get("/status").status_code == 200
        assert client.get("/status", headers={"Host": "attacker.example"}).status_code == 400


def test_direct_asgi_export_blocks_unauthenticated_remote_client(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", None)
    with TestClient(
        bridge.app,
        base_url="http://localhost",
        client=("203.0.113.10", 50000),
    ) as client:
        assert client.get("/status").status_code == 200
        denied = client.get("/api/state")
    assert denied.status_code == 403
    assert denied.json()["error"] == "unauthenticated network access is disabled"


@pytest.mark.asyncio
async def test_cross_process_outbox_event_reaches_local_subscriber(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "_subscribers", {})
    send, receive = anyio.create_memory_object_stream(max_buffer_size=2)
    bridge._subscribers.setdefault("remote:c", set()).add(send)
    timestamp = bridge.utc_now_iso()
    cursor = bridge.db().execute(
        "INSERT INTO messages(id, channel, sender, content, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        ("remote-message", "remote:c", "remote-process", "hello", timestamp),
    )
    seq = int(cursor.lastrowid)
    bridge.db().execute(
        "INSERT INTO bridge_events(event_type, channel, message_id, source_instance, "
        "payload, timestamp) VALUES ('message', ?, ?, ?, ?, ?)",
        (
            "remote:c",
            "remote-message",
            "another-process",
            "{}",
            timestamp,
        ),
    )

    assert await bridge._relay_external_events_once() == 1
    event = receive.receive_nowait()
    assert event["id"] == "remote-message"
    assert event["data"]["seq"] == seq
    assert event["data"]["content"] == "hello"
    send.close()
    receive.close()


@pytest.mark.asyncio
async def test_outbox_preserves_external_message_then_local_clear_order(
    fresh_db, monkeypatch
):
    monkeypatch.setattr(bridge, "_subscribers", {})
    send, receive = anyio.create_memory_object_stream(max_buffer_size=4)
    bridge._subscribers.setdefault("ordered:c", set()).add(send)
    timestamp = bridge.utc_now_iso()
    bridge.db().execute(
        "INSERT INTO messages(id, channel, sender, content, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        ("external-before-clear", "ordered:c", "external", "old", timestamp),
    )
    bridge.db().execute(
        "INSERT INTO bridge_events(event_type, channel, message_id, source_instance, "
        "payload, timestamp) VALUES ('message', ?, ?, ?, '{}', ?)",
        ("ordered:c", "external-before-clear", "other-process", timestamp),
    )

    assert await bridge.clear_channel("ordered:c") == 1
    delivered = receive.receive_nowait()
    assert delivered["event"] == "clear"
    with pytest.raises(anyio.WouldBlock):
        receive.receive_nowait()
    assert bridge.db().execute(
        "SELECT COUNT(*) FROM messages WHERE channel = 'ordered:c'"
    ).fetchone()[0] == 0
    send.close()
    receive.close()


@pytest.mark.asyncio
async def test_outbox_preserves_external_clear_then_local_message_order(
    fresh_db, monkeypatch
):
    monkeypatch.setattr(bridge, "_subscribers", {})
    send, receive = anyio.create_memory_object_stream(max_buffer_size=4)
    bridge._subscribers.setdefault("ordered:c", set()).add(send)
    timestamp = bridge.utc_now_iso()
    bridge.db().execute(
        "INSERT INTO bridge_events(event_type, channel, source_instance, payload, timestamp) "
        "VALUES ('clear', ?, ?, ?, ?)",
        ("ordered:c", "other-process", json.dumps({"channel": "ordered:c", "cleared": 1}), timestamp),
    )

    await bridge.insert_message("ordered:c", "local", "new")
    first = receive.receive_nowait()
    second = receive.receive_nowait()
    assert [first["event"], second["event"]] == ["clear", "message"]
    assert second["data"]["content"] == "new"
    send.close()
    receive.close()


@pytest.mark.asyncio
async def test_outbox_does_not_duplicate_message_content(fresh_db):
    secret = "message-content-must-not-live-in-the-outbox"
    await bridge.insert_message("privacy:c", "sender", secret)
    row = bridge.db().execute(
        "SELECT payload FROM bridge_events WHERE event_type = 'message'"
    ).fetchone()
    assert row["payload"] == "{}"
    assert secret not in row["payload"]


@pytest.mark.asyncio
async def test_cursor_from_another_channel_is_rejected(fresh_db):
    foreign = await bridge.dispatch_tool(
        "bridge_send", {"channel": "a", "sender": "x", "content": "foreign"}
    )
    await bridge.dispatch_tool(
        "bridge_send", {"channel": "b", "sender": "y", "content": "must-not-skip"}
    )
    _content, result = await bridge.dispatch_tool(
        "bridge_receive",
        {"channel": "b", "since_id": message_id(foreign)},
        structured=True,
    )
    assert result["messages"] == []
    assert result["warning"] == "since_id_not_found"


def test_deep_legacy_json_cannot_poison_reads(fresh_db):
    deep = "[" * 10_000 + "]" * 10_000
    with TestClient(bridge.app, base_url="http://localhost") as client:
        sent = client.post(
            "/api/send",
            json={"channel": "deep:c", "sender": "sender", "content": deep},
        )
        assert sent.status_code == 200
        listing = client.get("/api/messages?channel=deep:c")
        detail = client.get(f"/api/messages/{sent.json()['id']}")
    assert listing.status_code == 200
    assert listing.json()["messages"][0]["id"] == sent.json()["id"]
    assert detail.status_code == 200
    assert detail.json()["encoding"] == "legacy_text"


def test_deep_request_json_returns_400(fresh_db):
    nested = "[" * 2_000 + "0" + "]" * 2_000
    body = (
        '{"channel":"deep:c","sender":"sender","message":'
        '{"schema_version":1,"type":"task","content":'
        + nested
        + "}}"
    )
    with TestClient(bridge.app, base_url="http://localhost") as client:
        response = client.post(
            "/api/send",
            content=body.encode(),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
    assert "must be nested no more than" in response.json()["error"]


def test_invalid_structured_version_and_ack_metadata_return_400(fresh_db):
    with TestClient(bridge.app, base_url="http://localhost") as client:
        sent = client.post(
            "/api/send",
            json={"channel": "invalid:c", "sender": "sender", "content": "valid"},
        )
        assert sent.status_code == 200
        unsupported = client.post(
            "/api/send",
            json={
                "channel": "invalid:c",
                "sender": "sender",
                "message": {"schema_version": 2, "type": "task", "content": {}},
            },
        )
        bad_metadata = client.post(
            "/api/ack",
            json={
                "channel": "invalid:c",
                "consumer_id": "consumer",
                "message_id": sent.json()["id"],
                "metadata": "not-an-object",
            },
        )
    assert unsupported.status_code == 400
    assert unsupported.json()["code"] == "invalid_protocol"
    assert bad_metadata.status_code == 400
    assert bad_metadata.json()["field"] == "metadata"


def test_busy_send_returns_retryable_503(fresh_db, monkeypatch):
    async def busy(*_args, **_kwargs):
        raise bridge.BridgeBusyError("busy")

    monkeypatch.setattr(bridge, "insert_message_reliable", busy)
    with TestClient(bridge.app, base_url="http://localhost") as client:
        response = client.post(
            "/api/send",
            json={"channel": "busy:c", "sender": "sender", "content": "hello"},
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
