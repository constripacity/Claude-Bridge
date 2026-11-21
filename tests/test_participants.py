"""Participants: presence and the task each participant currently holds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import claude_bridge.server as bridge
import claude_bridge.taskqueue as taskqueue
from claude_bridge.validation import BridgeValidationError


async def call(name, args):
    _content, data = await bridge.dispatch_tool(name, args, structured=True)
    return data


async def participants():
    data = await call("bridge_participants", {})
    return {p["name"]: p for p in data["participants"]}


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
    assert alice["current_channel"] is None and alice["current_task_id"] is None


@pytest.mark.asyncio
async def test_claim_sets_and_complete_clears_the_current_task(fresh_db):
    task = await enqueue_and_claim("w1")
    w1 = (await participants())["w1"]
    assert w1["current_channel"] == "jobs" and w1["current_task_id"] == task["task_id"]

    await call(
        "bridge_complete",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    w1 = (await participants())["w1"]
    assert w1["current_task_id"] is None and w1["current_channel"] == "jobs"


@pytest.mark.asyncio
async def test_fail_clears_the_current_task(fresh_db):
    task = await enqueue_and_claim("w1")
    await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    assert (await participants())["w1"]["current_task_id"] is None


@pytest.mark.asyncio
async def test_empty_claim_keeps_the_held_task(fresh_db):
    task = await enqueue_and_claim("w1")
    empty = await call("bridge_claim", {"channel": "other", "consumer": "w1"})
    assert empty["task"] is None
    w1 = (await participants())["w1"]
    assert w1["current_task_id"] == task["task_id"] and w1["current_channel"] == "jobs"


@pytest.mark.asyncio
async def test_lease_expiry_at_claim_moves_the_task_to_the_new_owner(fresh_db, monkeypatch):
    task = await enqueue_and_claim("w1", lease_seconds=1)
    advance_clock(monkeypatch, 120)
    reclaimed = await call("bridge_claim", {"channel": "jobs", "consumer": "w2"})
    assert reclaimed["task"]["task_id"] == task["task_id"]
    seen = await participants()
    assert seen["w1"]["current_task_id"] is None
    assert seen["w2"]["current_task_id"] == task["task_id"]


@pytest.mark.asyncio
async def test_lease_expiry_in_the_sweep_clears_the_current_task(fresh_db, monkeypatch):
    await enqueue_and_claim("w1", lease_seconds=1)
    advance_clock(monkeypatch, 120)
    await bridge.housekeeping_sweep_once()
    assert (await participants())["w1"]["current_task_id"] is None


@pytest.mark.asyncio
async def test_channel_clear_clears_the_current_task(fresh_db):
    await enqueue_and_claim("w1")
    await bridge.clear_channel("jobs")
    assert (await participants())["w1"]["current_task_id"] is None


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
    assert (await participants())["w1"]["current_task_id"] == task["task_id"]


@pytest.mark.asyncio
async def test_finishing_the_newer_of_two_tasks_points_back_to_the_older(fresh_db):
    first = await enqueue_and_claim("w1", channel="a")
    second = await enqueue_and_claim("w1", channel="b")
    assert (await participants())["w1"]["current_task_id"] == second["task_id"]
    await call(
        "bridge_complete",
        {"channel": "b", "task_id": second["task_id"], "lease_token": second["lease_token"]},
    )
    w1 = (await participants())["w1"]
    assert w1["current_task_id"] == first["task_id"] and w1["current_channel"] == "a"


@pytest.mark.asyncio
async def test_requeued_task_reclaimed_by_another_worker(fresh_db):
    task = await enqueue_and_claim("w1")
    await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    await call("bridge_claim", {"channel": "jobs", "consumer": "w2"})
    seen = await participants()
    assert seen["w1"]["current_task_id"] is None
    assert seen["w2"]["current_task_id"] == task["task_id"]


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


@pytest.mark.asyncio
async def test_sweep_prunes_idle_participants_past_retention(fresh_db, monkeypatch):
    task = await enqueue_and_claim("busy")
    await call("bridge_send", {"channel": "chat", "sender": "idle", "content": "x"})
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 1)
    real_now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        bridge, "_retention_cutoff_iso",
        lambda days, now=None: (real_now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
    )
    await bridge.housekeeping_sweep_once()
    seen = await participants()
    assert "idle" not in seen and seen["busy"]["current_task_id"] == task["task_id"]


@pytest.mark.asyncio
async def test_text_output_names_the_task_and_its_channel(fresh_db):
    task = await enqueue_and_claim("w1")
    content, _data = await bridge.dispatch_tool("bridge_participants", {}, structured=True)
    assert f"task {task['task_id']} on [jobs]" in content[0].text


@pytest.mark.asyncio
async def test_tool_listing_declares_bridge_participants_read_only():
    tools = {tool.name: tool for tool in await bridge.list_tools()}
    assert tools["bridge_participants"].annotations.readOnlyHint is True
