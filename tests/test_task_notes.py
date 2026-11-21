"""Task notes: messages bound to one task, delivered to whoever works on it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import claude_bridge.server as bridge
import claude_bridge.taskqueue as taskqueue
from claude_bridge.validation import BridgeValidationError

from .legacy_schema import create_v130_database

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


async def call(name, args):
    _content, data = await bridge.dispatch_tool(name, args, structured=True)
    return data


async def enqueue(channel="jobs"):
    return (await call("bridge_enqueue", {"channel": channel, "content": "work"}))["task_id"]


async def claim(consumer="w1", channel="jobs"):
    return (await call("bridge_claim", {"channel": channel, "consumer": consumer}))["task"]


async def note(task_id, content, *, sender="lead", channel="jobs"):
    return await call(
        "bridge_task_note",
        {"channel": channel, "task_id": task_id, "sender": sender, "content": content},
    )


async def new_notes(task):
    data = await call(
        "bridge_task_notes",
        {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]},
    )
    return [n["content"] for n in data["notes"]]


def lease(task):
    return {"channel": "jobs", "task_id": task["task_id"], "lease_token": task["lease_token"]}


@pytest.mark.asyncio
async def test_note_on_a_pending_task_arrives_with_the_claim(fresh_db):
    task_id = await enqueue()
    sent = await note(task_id, "use branch b")
    assert sent["seq"] > 0 and sent["sender"] == "lead"

    content, data = await bridge.dispatch_tool(
        "bridge_claim", {"channel": "jobs", "consumer": "w1"}, structured=True
    )
    assert [n["content"] for n in data["task"]["notes"]] == ["use branch b"]
    assert "lead" in content[0].text and "use branch b" in content[0].text


@pytest.mark.asyncio
async def test_notes_during_the_lease_are_read_once(fresh_db):
    task_id = await enqueue()
    await note(task_id, "before claim")
    task = await claim()
    assert await new_notes(task) == []  # The claim already delivered it.

    await note(task_id, "first")
    await note(task_id, "second")
    assert await new_notes(task) == ["first", "second"]
    assert await new_notes(task) == []
    await note(task_id, "third")
    assert await new_notes(task) == ["third"]


@pytest.mark.asyncio
async def test_complete_reports_unread_notes(fresh_db):
    task_id = await enqueue()
    task = await claim()
    await note(task_id, "read me")
    await new_notes(task)
    await note(task_id, "late change")
    done = await call("bridge_complete", lease(task))
    assert [n["content"] for n in done["unread_notes"]] == ["late change"]


@pytest.mark.asyncio
async def test_fail_reports_unread_notes(fresh_db):
    task_id = await enqueue()
    task = await claim()
    await note(task_id, "late change")
    failed = await call("bridge_fail", lease(task))
    assert [n["content"] for n in failed["unread_notes"]] == ["late change"]


@pytest.mark.asyncio
async def test_requeued_task_gives_the_next_worker_every_note(fresh_db):
    task_id = await enqueue()
    await note(task_id, "one")
    first = await claim("w1")
    await note(task_id, "two")
    await new_notes(first)
    await call("bridge_fail", lease(first))
    second = await claim("w2")
    assert [n["content"] for n in second["notes"]] == ["one", "two"]
    assert await new_notes(second) == []


@pytest.mark.asyncio
async def test_note_on_a_finished_task_is_rejected(fresh_db):
    task_id = await enqueue()
    task = await claim()
    await call("bridge_complete", lease(task))
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "too late")
    assert (excinfo.value.field, excinfo.value.code) == ("task_id", "not_active")


@pytest.mark.asyncio
async def test_note_on_an_unknown_task_is_not_found(fresh_db):
    with pytest.raises(BridgeValidationError) as excinfo:
        await note("tsk_missing", "hello")
    assert (excinfo.value.field, excinfo.value.code) == ("task_id", "not_found")


@pytest.mark.asyncio
async def test_reading_notes_needs_the_live_lease_token(fresh_db):
    await enqueue()
    task = await claim()
    with pytest.raises(BridgeValidationError) as excinfo:
        await new_notes({**task, "lease_token": "wrong"})
    assert (excinfo.value.field, excinfo.value.code) == ("lease_token", "lost")


@pytest.mark.asyncio
async def test_note_sender_becomes_a_participant(fresh_db):
    task_id = await enqueue()
    await note(task_id, "hi", sender="lead")
    names = [p["name"] for p in (await call("bridge_participants", {}))["participants"]]
    assert "lead" in names


@pytest.mark.asyncio
async def test_channel_clear_drops_only_its_notes(fresh_db):
    await note(await enqueue(), "gone soon")
    await note(await enqueue("other"), "keep", channel="other")
    await bridge.clear_channel("jobs")
    rows = bridge.db().execute("SELECT channel FROM task_notes").fetchall()
    assert [r[0] for r in rows] == ["other"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "field"),
    [
        ({"content": ""}, "content"),
        ({"content": "   "}, "content"),
        ({"content": "x" * (taskqueue.MAX_NOTE_BYTES + 1)}, "content"),
        ({"sender": ""}, "sender"),
    ],
)
async def test_invalid_note_is_rejected(fresh_db, args, field):
    task_id = await enqueue()
    base = {"channel": "jobs", "task_id": task_id, "sender": "lead", "content": "ok"}
    with pytest.raises(BridgeValidationError) as excinfo:
        await call("bridge_task_note", {**base, **args})
    assert excinfo.value.field == field


@pytest.mark.asyncio
async def test_note_to_a_task_of_another_channel_is_not_found(fresh_db):
    task_id = await enqueue("other")
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "wrong channel")
    assert (excinfo.value.field, excinfo.value.code) == ("task_id", "not_found")


@pytest.mark.asyncio
async def test_note_on_a_dead_task_is_rejected(fresh_db):
    task_id = await enqueue()
    task = await claim()
    await call("bridge_fail", {**lease(task), "requeue": False})
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "too late")
    assert excinfo.value.code == "not_active"


@pytest.mark.asyncio
async def test_a_task_holds_at_most_the_note_limit(fresh_db, monkeypatch):
    monkeypatch.setattr(taskqueue, "MAX_NOTES_PER_TASK", 2)
    task_id = await enqueue()
    await note(task_id, "one")
    await note(task_id, "two")
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "three")
    assert (excinfo.value.field, excinfo.value.code) == ("task_id", "too_many_notes")


@pytest.mark.asyncio
async def test_old_lease_cannot_read_notes_after_a_reclaim(fresh_db):
    task_id = await enqueue()
    first = await claim("w1")
    await call("bridge_fail", lease(first))
    second = await claim("w2")
    await note(task_id, "for w2")
    with pytest.raises(BridgeValidationError) as excinfo:
        await new_notes(first)
    assert excinfo.value.code == "lost"
    assert await new_notes(second) == ["for w2"]


@pytest.mark.asyncio
async def test_completed_task_notes_cannot_be_read(fresh_db):
    await enqueue()
    task = await claim()
    await call("bridge_complete", lease(task))
    with pytest.raises(BridgeValidationError) as excinfo:
        await new_notes(task)
    assert excinfo.value.code == "lost"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["bridge_task_notes", "bridge_complete", "bridge_fail"])
async def test_text_output_shows_the_notes(fresh_db, tool):
    task_id = await enqueue()
    task = await claim()
    await note(task_id, "visible in text")
    content, _data = await bridge.dispatch_tool(tool, lease(task), structured=True)
    assert "visible in text" in content[0].text


def test_pruning_a_finished_task_drops_only_its_notes(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", now=T0)
    kept = store.enqueue(channel="q", payload="B", now=T0).task
    task = store.claim(channel="q", consumer="w", lease_seconds=60, now=T0)
    store.add_note(channel="q", task_id=task.id, sender="lead", content="x", now=T0)
    store.add_note(channel="q", task_id=kept.id, sender="lead", content="keep", now=T0)
    store.complete(channel="q", task_id=task.id, lease_token=task.lease_token, now=T0)
    later = (T0 + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    assert store.prune_terminal(older_than_iso=later) == 1
    assert store.all_notes(task) == []
    assert [n.content for n in store.all_notes(kept)] == ["keep"]


def test_delete_channel_drops_only_the_notes_of_that_channel(fresh_db):
    store = bridge.task_store()
    gone = store.enqueue(channel="q", payload="A", now=T0).task
    kept = store.enqueue(channel="r", payload="B", now=T0).task
    store.add_note(channel="q", task_id=gone.id, sender="lead", content="x", now=T0)
    store.add_note(channel="r", task_id=kept.id, sender="lead", content="keep", now=T0)
    assert store.delete_channel(channel="q") == 1
    assert store.all_notes(gone) == []
    assert [n.content for n in store.all_notes(kept)] == ["keep"]


def test_lease_expiry_requeue_gives_the_next_worker_every_note(fresh_db):
    store = bridge.task_store()
    task = store.enqueue(channel="q", payload="A", now=T0).task
    store.add_note(channel="q", task_id=task.id, sender="lead", content="one", now=T0)
    first = store.claim(channel="q", consumer="w1", lease_seconds=10, now=T0)
    store.add_note(channel="q", task_id=task.id, sender="lead", content="two", now=T0)
    store.take_new_notes(channel="q", task_id=task.id, lease_token=first.lease_token)
    store.requeue_expired(now=T0 + timedelta(seconds=60))
    second = store.claim(
        channel="q", consumer="w2", lease_seconds=10, now=T0 + timedelta(seconds=61)
    )
    assert [n.content for n in store.all_notes(second)] == ["one", "two"]
    assert second.notes_read_seq == store.all_notes(second)[-1].seq


@pytest.mark.asyncio
async def test_v130_database_gains_notes_in_place(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    create_v130_database(str(db_path), pending_task_id="tsk_legacy")
    monkeypatch.setattr(bridge, "DB_PATH", str(db_path))
    monkeypatch.setattr(bridge, "_conn", None)
    try:
        await note("tsk_legacy", "for the old task", channel="old")
        task = await claim(channel="old")
        assert [n["content"] for n in task["notes"]] == ["for the old task"]
    finally:
        bridge._conn.close()
        monkeypatch.setattr(bridge, "_conn", None)


@pytest.mark.asyncio
async def test_legacy_database_upgrade_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    create_v130_database(str(db_path), pending_task_id="tsk_legacy")
    monkeypatch.setattr(bridge, "DB_PATH", str(db_path))
    for _ in range(2):
        monkeypatch.setattr(bridge, "_conn", None)
        bridge.db().close()
    monkeypatch.setattr(bridge, "_conn", None)
    try:
        await note("tsk_legacy", "after two upgrades", channel="old")
        task = await claim(channel="old")
        assert [n["content"] for n in task["notes"]] == ["after two upgrades"]
    finally:
        bridge._conn.close()
        monkeypatch.setattr(bridge, "_conn", None)


@pytest.mark.asyncio
async def test_tool_listing_declares_the_note_tools():
    tools = {tool.name: tool for tool in await bridge.list_tools()}
    assert tools["bridge_task_note"].annotations.readOnlyHint is False
    assert set(tools["bridge_task_note"].inputSchema["required"]) == {
        "channel", "task_id", "sender", "content",
    }
    assert set(tools["bridge_task_notes"].inputSchema["required"]) == {
        "channel", "task_id", "lease_token",
    }


@pytest.mark.asyncio
async def test_a_note_of_the_byte_limit_is_accepted(fresh_db):
    task_id = await enqueue()
    sent = await note(task_id, "x" * taskqueue.MAX_NOTE_BYTES)
    assert len(sent["content"].encode("utf-8")) == taskqueue.MAX_NOTE_BYTES


@pytest.mark.asyncio
async def test_the_note_byte_limit_counts_utf8_bytes(fresh_db):
    task_id = await enqueue()
    two_byte_chars = "é" * (taskqueue.MAX_NOTE_BYTES // 2 + 1)
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, two_byte_chars)
    assert (excinfo.value.field, excinfo.value.code) == ("content", "too_large")


@pytest.mark.asyncio
async def test_the_notes_of_a_task_have_a_total_byte_limit(fresh_db):
    task_id = await enqueue()
    full_note = "é" * (taskqueue.MAX_NOTE_BYTES // 2)
    assert len(full_note.encode("utf-8")) == taskqueue.MAX_NOTE_BYTES
    note_count = taskqueue.MAX_NOTE_BYTES_PER_TASK // taskqueue.MAX_NOTE_BYTES
    for _ in range(note_count):
        await note(task_id, full_note)
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "x")
    assert (excinfo.value.field, excinfo.value.code) == ("content", "task_notes_too_large")
    task = await claim()
    assert len(task["notes"]) == note_count


@pytest.mark.asyncio
async def test_small_notes_that_cross_the_total_byte_limit_are_rejected(fresh_db, monkeypatch):
    monkeypatch.setattr(taskqueue, "MAX_NOTE_BYTES_PER_TASK", 10)
    task_id = await enqueue()
    await note(task_id, "1234")
    await note(task_id, "5678")
    with pytest.raises(BridgeValidationError) as excinfo:
        await note(task_id, "abc")
    assert excinfo.value.code == "task_notes_too_large"
    await note(task_id, "ab")  # Exactly 10 bytes in total.
    assert [n["content"] for n in (await claim())["notes"]] == ["1234", "5678", "ab"]
