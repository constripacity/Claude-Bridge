"""Participants: presence, the task each participant holds, and its usage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import claude_bridge.server as bridge
import claude_bridge.taskqueue as taskqueue
from claude_bridge.participants import parse_usage_report
from claude_bridge.timestamps import utc_timestamp
from claude_bridge.validation import BridgeValidationError

REPORT = {
    "session": {"used_pct": 42, "resets_at": "2026-11-23T01:20:00Z"},
    "weekly": {"used_pct": 71, "resets_at": "2026-11-27T08:00:00Z"},
}


async def call(name, args):
    _content, data = await bridge.dispatch_tool(name, args, structured=True)
    return data


async def participants():
    data = await call("bridge_participants", {})
    return {p["name"]: p for p in data["participants"]}


async def participants_text():
    content, _data = await bridge.dispatch_tool("bridge_participants", {}, structured=True)
    return content[0].text


def held_task_id(participant):
    task = participant["current_task"]
    return None if task is None else task["id"]


def report_usage(name, body, *, minutes_ago=0):
    store = bridge.participant_store()
    store.report_usage(name, parse_usage_report(body))
    reported_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    bridge.db().execute(
        "UPDATE participants SET usage_reported_at = ? WHERE name = ?",
        (utc_timestamp(reported_at), name),
    )


async def enqueue_and_claim(consumer, *, channel="jobs", lease_seconds=60):
    await call("bridge_enqueue", {"channel": channel, "content": "work"})
    claim = await call(
        "bridge_claim",
        {"channel": channel, "consumer": consumer, "lease_seconds": lease_seconds},
    )
    return claim["task"]


def advance_clock(monkeypatch, seconds):
    later = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    monkeypatch.setattr(taskqueue, "_utc_now", lambda: later)


@pytest.mark.asyncio
async def test_send_records_last_seen_only(fresh_db):
    await call("bridge_send", {"channel": "chat", "sender": "alice", "content": "hi"})
    alice = (await participants())["alice"]
    assert alice["last_seen"]
    assert alice["current_channel"] is None and held_task_id(alice) is None


@pytest.mark.asyncio
async def test_claim_sets_and_complete_clears_the_current_task(fresh_db):
    task = await enqueue_and_claim("w1")
    w1 = (await participants())["w1"]
    assert w1["current_channel"] == "jobs" and held_task_id(w1) == task["task_id"]

    await call(
        "bridge_complete",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    w1 = (await participants())["w1"]
    assert held_task_id(w1) is None and w1["current_channel"] == "jobs"


@pytest.mark.asyncio
async def test_fail_clears_the_current_task(fresh_db):
    task = await enqueue_and_claim("w1")
    await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    assert held_task_id((await participants())["w1"]) is None


@pytest.mark.asyncio
async def test_empty_claim_keeps_the_held_task(fresh_db):
    task = await enqueue_and_claim("w1")
    empty = await call("bridge_claim", {"channel": "other", "consumer": "w1"})
    assert empty["task"] is None
    w1 = (await participants())["w1"]
    assert held_task_id(w1) == task["task_id"] and w1["current_channel"] == "jobs"


@pytest.mark.asyncio
async def test_lease_expiry_at_claim_moves_the_task_to_the_new_owner(fresh_db, monkeypatch):
    task = await enqueue_and_claim("w1", lease_seconds=1)
    advance_clock(monkeypatch, 120)
    reclaimed = await call("bridge_claim", {"channel": "jobs", "consumer": "w2"})
    assert reclaimed["task"]["task_id"] == task["task_id"]
    seen = await participants()
    assert held_task_id(seen["w1"]) is None
    assert held_task_id(seen["w2"]) == task["task_id"]


@pytest.mark.asyncio
async def test_lease_expiry_in_the_sweep_clears_the_current_task(fresh_db, monkeypatch):
    await enqueue_and_claim("w1", lease_seconds=1)
    advance_clock(monkeypatch, 120)
    await bridge.housekeeping_sweep_once()
    assert held_task_id((await participants())["w1"]) is None


@pytest.mark.asyncio
async def test_channel_clear_clears_the_current_task(fresh_db):
    await enqueue_and_claim("w1")
    await bridge.clear_channel("jobs")
    assert held_task_id((await participants())["w1"]) is None


@pytest.mark.asyncio
async def test_participants_are_listed_most_recent_first(fresh_db):
    await call("bridge_send", {"channel": "chat", "sender": "first", "content": "a"})
    await call("bridge_send", {"channel": "chat", "sender": "second", "content": "b"})
    data = await call("bridge_participants", {})
    assert [p["name"] for p in data["participants"]] == ["second", "first"]


@pytest.mark.asyncio
async def test_send_keeps_the_held_task(fresh_db):
    task = await enqueue_and_claim("w1")
    await call("bridge_send", {"channel": "chat", "sender": "w1", "content": "busy"})
    assert held_task_id((await participants())["w1"]) == task["task_id"]


@pytest.mark.asyncio
async def test_finishing_the_newer_of_two_tasks_points_back_to_the_older(fresh_db):
    first = await enqueue_and_claim("w1", channel="a")
    second = await enqueue_and_claim("w1", channel="b")
    assert held_task_id((await participants())["w1"]) == second["task_id"]
    await call(
        "bridge_complete",
        {"channel": "b", "task_id": second["task_id"], "lease_token": second["lease_token"]},
    )
    w1 = (await participants())["w1"]
    assert held_task_id(w1) == first["task_id"] and w1["current_channel"] == "a"


@pytest.mark.asyncio
async def test_requeued_task_reclaimed_by_another_worker(fresh_db):
    task = await enqueue_and_claim("w1")
    await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    await call("bridge_claim", {"channel": "jobs", "consumer": "w2"})
    seen = await participants()
    assert held_task_id(seen["w1"]) is None
    assert held_task_id(seen["w2"]) == task["task_id"]


@pytest.mark.asyncio
async def test_rejected_complete_leaves_participants_unchanged(fresh_db):
    task = await enqueue_and_claim("w1")
    before = await participants()
    with pytest.raises(BridgeValidationError):
        await call(
            "bridge_complete",
            {"channel": "jobs", "task_id": task["task_id"], "lease_token": "wrong"},
        )
    assert await participants() == before


def cutoff_in_the_future(monkeypatch):
    """Make every retention cutoff lie ahead, so all idle rows count as old."""
    future = datetime.now(timezone.utc) + timedelta(days=1)
    stamp = future.isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(bridge, "_retention_cutoff_iso", lambda days, now=None: stamp)


@pytest.mark.asyncio
async def test_sweep_prunes_idle_participants_without_message_retention(
    fresh_db, monkeypatch
):
    task = await enqueue_and_claim("busy")
    await call("bridge_send", {"channel": "chat", "sender": "idle", "content": "x"})
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 0)
    monkeypatch.setattr(bridge, "PARTICIPANT_IDLE_DAYS", 7)
    cutoff_in_the_future(monkeypatch)
    await bridge.housekeeping_sweep_once()
    seen = await participants()
    assert "idle" not in seen and held_task_id(seen["busy"]) == task["task_id"]


@pytest.mark.asyncio
async def test_sweep_keeps_a_participant_waiting_on_its_enqueued_task(
    fresh_db, monkeypatch
):
    await call("bridge_send", {"channel": "chat", "sender": "lead", "content": "x"})
    await call("bridge_enqueue", {"channel": "jobs", "content": "a", "enqueued_by": "lead"})
    monkeypatch.setattr(bridge, "PARTICIPANT_IDLE_DAYS", 7)
    cutoff_in_the_future(monkeypatch)
    await bridge.housekeeping_sweep_once()
    assert "lead" in await participants()


@pytest.mark.asyncio
async def test_participant_idle_days_zero_keeps_idle_participants(fresh_db, monkeypatch):
    await call("bridge_send", {"channel": "chat", "sender": "idle", "content": "x"})
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 1)
    monkeypatch.setattr(bridge, "PARTICIPANT_IDLE_DAYS", 0)
    cutoff_in_the_future(monkeypatch)
    await bridge.housekeeping_sweep_once()
    assert "idle" in await participants()


@pytest.mark.asyncio
async def test_participants_listing_honours_the_limit(fresh_db):
    for name in ("a", "b", "c"):
        await call("bridge_send", {"channel": "chat", "sender": name, "content": "x"})
    data = await call("bridge_participants", {"limit": 2})
    assert [p["name"] for p in data["participants"]] == ["c", "b"]


def test_participant_idle_days_default_is_seven(monkeypatch):
    monkeypatch.delenv("CLAUDE_BRIDGE_PARTICIPANT_IDLE_DAYS", raising=False)
    assert bridge.Settings.from_env().participant_idle_days == 7


@pytest.mark.asyncio
async def test_text_output_names_the_task_and_its_channel(fresh_db):
    task = await enqueue_and_claim("w1")
    assert f"task work ({task['task_id']}) on [jobs]" in await participants_text()


@pytest.mark.asyncio
async def test_structured_output_has_presence_open_tasks_and_usage(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "a", "enqueued_by": "w1"})
    report_usage("w1", REPORT)
    w1 = (await participants())["w1"]
    assert w1["presence"] == "online" and w1["open_tasks"] == 1
    assert w1["usage"]["session"] == {
        "used_pct": 42.0,
        "resets_at": "2026-11-23T01:20:00.000000Z",
    }
    assert w1["usage"]["weekly"]["used_pct"] == 71.0
    assert w1["usage"]["reported_at"] < w1["usage"]["stale_at"]


@pytest.mark.asyncio
async def test_text_line_shows_presence_usage_windows_and_age(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "a", "enqueued_by": "w1"})
    report_usage("w1", REPORT, minutes_ago=3)
    assert (
        "  w1 · online · 5h 42% (resets 01:20Z) · wk 71% (resets 2026-11-27) · "
        "usage 3 min old · no task · 1 enqueued task(s) open"
    ) in (await participants_text()).splitlines()


@pytest.mark.asyncio
async def test_text_skips_a_missing_window_and_an_unknown_reset(fresh_db):
    report_usage("w1", {"session": {"used_pct": 5, "resets_at": None}})
    assert "  w1 · online · 5h 5% · usage 0 min old · no task" in await participants_text()


@pytest.mark.asyncio
async def test_text_marks_a_report_older_than_the_threshold_as_stale(fresh_db):
    report_usage("w1", REPORT, minutes_ago=16)
    assert "usage 16 min old (stale)" in await participants_text()


@pytest.mark.asyncio
async def test_text_says_not_reported_without_a_usage_report(fresh_db):
    await call("bridge_send", {"channel": "chat", "sender": "w1", "content": "hi"})
    assert "  w1 · online · usage: not reported · no task" in await participants_text()


@pytest.mark.asyncio
async def test_tool_listing_declares_bridge_participants_read_only():
    tools = {tool.name: tool for tool in await bridge.list_tools()}
    assert tools["bridge_participants"].annotations.readOnlyHint is True


def test_participant_store_is_cached_per_connection(fresh_db):
    assert bridge.participant_store() is bridge.participant_store()
