"""The participants section of /api/state: presence, live task and usage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge
from claude_bridge.participants import presence
from claude_bridge.timestamps import utc_timestamp

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def seen(delta: timedelta) -> str:
    return (NOW - delta).isoformat(timespec="microseconds").replace("+00:00", "Z")


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(0), "online"),
        (timedelta(minutes=10), "online"),
        (timedelta(minutes=10, seconds=1), "idle"),
        (timedelta(hours=24), "idle"),
        (timedelta(hours=24, seconds=1), "offline"),
        (timedelta(days=30), "offline"),
    ],
)
def test_presence_thresholds(age, expected):
    assert presence(seen(age), NOW) == expected


@pytest.fixture
def client(fresh_db):
    return TestClient(bridge.app, base_url="http://localhost")


def state_participants(client):
    return {p["name"]: p for p in client.get("/api/state").json()["participants"]}


def call(name, args):
    _content, data = asyncio.run(bridge.dispatch_tool(name, args, structured=True))
    return data


def test_state_lists_no_participants_on_an_empty_bridge(client):
    assert client.get("/api/state").json()["participants"] == []


def test_state_shows_the_live_task_with_title_and_claim_time(client):
    call("bridge_enqueue", {"channel": "jobs", "content": "Build it\nmore", "title": "Build"})
    task = call("bridge_claim", {"channel": "jobs", "consumer": "w1"})["task"]

    w1 = state_participants(client)["w1"]
    assert w1["presence"] == "online"
    assert w1["current_channel"] == "jobs"
    assert w1["current_task"] == {
        "id": task["task_id"],
        "title": "Build",
        "claimed_since": task["updated_at"],
    }
    assert w1["usage"] is None


def test_finished_task_is_no_current_task(client):
    call("bridge_enqueue", {"channel": "jobs", "content": "work"})
    task = call("bridge_claim", {"channel": "jobs", "consumer": "w1"})["task"]
    call(
        "bridge_complete",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    assert state_participants(client)["w1"]["current_task"] is None


def test_expired_lease_is_no_current_task(client):
    call("bridge_enqueue", {"channel": "jobs", "content": "work"})
    task = call("bridge_claim", {"channel": "jobs", "consumer": "w1"})["task"]
    bridge.db().execute(
        "UPDATE tasks SET lease_expires_at = '2000-01-01T00:00:00.000000Z' WHERE id = ?",
        (task["task_id"],),
    )
    bridge.db().commit()
    assert state_participants(client)["w1"]["current_task"] is None


def test_state_shows_the_latest_usage_report(client):
    resets_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    client.post(
        "/api/participants/w2/usage",
        json={"session": {"used_pct": 42, "resets_at": int(resets_at.timestamp())}},
    )
    usage = state_participants(client)["w2"]["usage"]
    assert usage["session"] == {"used_pct": 42.0, "resets_at": utc_timestamp(resets_at)}
    assert usage["weekly"] is None
    assert usage["reported_at"].endswith("Z")


def test_state_participants_use_one_query(client):
    for name in ("a", "b", "c"):
        call("bridge_send", {"channel": "chat", "sender": name, "content": "hi"})
    store = bridge.participant_store()
    statements = []
    store.conn.set_trace_callback(statements.append)
    try:
        assert len(bridge._participants_state(datetime.now(timezone.utc))) == 3
    finally:
        store.conn.set_trace_callback(None)
    assert len(statements) == 1


def test_claimed_since_stays_while_the_worker_reads_notes(client):
    queued = call("bridge_enqueue", {"channel": "jobs", "content": "work"})
    task = call("bridge_claim", {"channel": "jobs", "consumer": "w1"})["task"]
    call(
        "bridge_task_note",
        {"channel": "jobs", "task_id": queued["task_id"], "sender": "lead", "content": "n"},
    )
    call(
        "bridge_task_notes",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    claimed_since = state_participants(client)["w1"]["current_task"]["claimed_since"]
    assert claimed_since == task["updated_at"]
