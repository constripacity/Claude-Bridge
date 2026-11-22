"""The participants section of /api/state: presence, live task and usage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge
from claude_bridge.participants import USAGE_STALE_AFTER, presence

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def seen(delta: timedelta) -> str:
    return (NOW - delta).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_z(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


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
    client.post(
        "/api/participants/w2/usage",
        json={"session": {"used_pct": 42, "resets_at": 1767225600}},
    )
    usage = state_participants(client)["w2"]["usage"]
    assert usage["session"] == {
        "used_pct": 42.0,
        "resets_at": "2026-01-01T00:00:00.000000Z",
    }
    assert usage["weekly"] is None
    assert usage["reported_at"].endswith("Z")


def test_usage_stale_at_is_the_report_time_plus_the_stale_threshold(client):
    client.post("/api/participants/w2/usage", json={"weekly": {"used_pct": 5}})
    usage = state_participants(client)["w2"]["usage"]
    assert parse_z(usage["stale_at"]) - parse_z(usage["reported_at"]) == USAGE_STALE_AFTER


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


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(hours=3), "online"),
        (timedelta(hours=24), "online"),
        (timedelta(hours=24, seconds=1), "offline"),
    ],
)
def test_open_work_keeps_presence_online_within_a_day(age, expected):
    assert presence(seen(age), NOW, has_open_work=True) == expected


def last_seen_hours_ago(name, hours):
    stamp = datetime.now(timezone.utc) - timedelta(hours=hours)
    bridge.db().execute(
        "UPDATE participants SET last_seen = ? WHERE name = ?",
        (stamp.isoformat().replace("+00:00", "Z"), name),
    )
    bridge.db().commit()


def test_waiting_enqueuer_is_online_with_its_open_task_count(client):
    call("bridge_send", {"channel": "chat", "sender": "lead", "content": "delegating"})
    for content in ("a", "b"):
        call("bridge_enqueue", {"channel": "jobs", "content": content, "enqueued_by": "lead"})
    call("bridge_claim", {"channel": "jobs", "consumer": "w1"})
    last_seen_hours_ago("lead", 2)

    lead = state_participants(client)["lead"]
    assert lead["presence"] == "online"
    assert lead["current_task"] is None
    assert lead["open_tasks"] == 2


def test_enqueuer_is_idle_again_once_its_tasks_are_completed_or_dead(client):
    call("bridge_send", {"channel": "chat", "sender": "lead", "content": "delegating"})
    for verb in ("bridge_complete", "bridge_fail"):
        call(
            "bridge_enqueue",
            {"channel": "jobs", "content": verb, "enqueued_by": "lead", "max_attempts": 1},
        )
        task = call("bridge_claim", {"channel": "jobs", "consumer": "w1"})["task"]
        call(
            verb,
            {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
        )
    last_seen_hours_ago("lead", 2)

    lead = state_participants(client)["lead"]
    assert lead["presence"] == "idle"
    assert lead["open_tasks"] == 0


def test_lease_holder_is_online_while_its_lease_is_live(client):
    call("bridge_enqueue", {"channel": "jobs", "content": "long", "enqueued_by": "lead"})
    call("bridge_claim", {"channel": "jobs", "consumer": "w1", "lease_seconds": 3600})
    last_seen_hours_ago("w1", 2)

    w1 = state_participants(client)["w1"]
    assert w1["presence"] == "online"
    assert w1["open_tasks"] == 0
