"""Task queue (v1.3): work distribution, leases, retries, dead-lettering.

Tool-surface behaviour is driven through ``bridge.dispatch_tool`` (the same path
MCP clients use); time-dependent lease/requeue behaviour is tested at the store
level with an injected ``now`` so it stays deterministic and fast.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import claude_bridge.server as bridge
from claude_bridge.taskqueue import TaskStatus
from claude_bridge.validation import BridgeValidationError

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


async def call(name, args):
    _content, data = await bridge.dispatch_tool(name, args, structured=True)
    return data


# ── Tool surface (via dispatch_tool) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_claim_complete_round_trip(fresh_db):
    enq = await call("bridge_enqueue", {"channel": "jobs", "payload": {"n": 1}})
    assert enq["created"] is True and enq["status"] == "pending"
    task_id = enq["task_id"]

    claim = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w1", "lease_seconds": 300}
    )
    assert claim["task"]["task_id"] == task_id
    assert claim["task"]["payload"] == '{"n":1}'  # canonical JSON
    token = claim["task"]["lease_token"]
    assert token

    done = await call(
        "bridge_complete",
        {"channel": "jobs", "task_id": task_id, "lease_token": token,
         "result": {"ok": True}},
    )
    assert done["status"] == "completed" and done["result"] == '{"ok":true}'


@pytest.mark.asyncio
async def test_enqueue_accepts_string_content(fresh_db):
    enq = await call("bridge_enqueue", {"channel": "jobs", "content": "do-the-thing"})
    claim = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w", "lease_seconds": 60}
    )
    assert claim["task"]["payload"] == "do-the-thing"
    assert enq["task_id"] == claim["task"]["task_id"]


@pytest.mark.asyncio
async def test_claim_is_exclusive(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "a"})
    await call("bridge_enqueue", {"channel": "jobs", "content": "b"})
    c1 = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w1", "lease_seconds": 60}
    )
    c2 = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w2", "lease_seconds": 60}
    )
    assert c1["task"]["task_id"] != c2["task"]["task_id"]
    # queue now drained
    c3 = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w3", "lease_seconds": 60}
    )
    assert c3["task"] is None


@pytest.mark.asyncio
async def test_priority_is_claimed_first(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "low"})
    await call(
        "bridge_enqueue", {"channel": "jobs", "content": "high", "priority": 10}
    )
    c = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w", "lease_seconds": 60}
    )
    assert c["task"]["payload"] == "high"


@pytest.mark.asyncio
async def test_lease_fencing_rejects_stale_completer(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "a"})
    claim = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w1", "lease_seconds": 60}
    )
    task_id = claim["task"]["task_id"]
    with pytest.raises(BridgeValidationError) as excinfo:
        await call(
            "bridge_complete",
            {"channel": "jobs", "task_id": task_id, "lease_token": "not-the-token"},
        )
    assert excinfo.value.field == "lease_token"


@pytest.mark.asyncio
async def test_complete_unknown_task_reports_not_found(fresh_db):
    with pytest.raises(BridgeValidationError) as excinfo:
        await call(
            "bridge_complete",
            {"channel": "jobs", "task_id": "tsk_missing", "lease_token": "x"},
        )
    assert excinfo.value.field == "task_id" and excinfo.value.code == "not_found"


@pytest.mark.asyncio
async def test_idempotent_enqueue_dedupes(fresh_db):
    a = await call(
        "bridge_enqueue", {"channel": "jobs", "content": "x", "idempotency_key": "k1"}
    )
    b = await call(
        "bridge_enqueue", {"channel": "jobs", "content": "y", "idempotency_key": "k1"}
    )
    assert a["created"] is True and b["created"] is False
    assert a["task_id"] == b["task_id"]
    counts = (await call("bridge_tasks", {"channel": "jobs"}))["counts"]
    assert counts["pending"] == 1


@pytest.mark.asyncio
async def test_fail_requeues_then_dead_letters(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "f", "max_attempts": 2})
    c1 = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w", "lease_seconds": 60}
    )
    r1 = await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": c1["task"]["task_id"],
         "lease_token": c1["task"]["lease_token"], "error": "boom"},
    )
    assert r1["status"] == "pending"  # requeued (attempt 1 of 2)
    c2 = await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w", "lease_seconds": 60}
    )
    assert c2["task"]["attempts"] == 2
    r2 = await call(
        "bridge_fail",
        {"channel": "jobs", "task_id": c2["task"]["task_id"],
         "lease_token": c2["task"]["lease_token"]},
    )
    assert r2["status"] == "dead"  # attempts exhausted


@pytest.mark.asyncio
async def test_bridge_tasks_reports_counts(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "1"})
    await call("bridge_enqueue", {"channel": "jobs", "content": "2"})
    await call(
        "bridge_claim", {"channel": "jobs", "consumer": "w", "lease_seconds": 60}
    )
    data = await call("bridge_tasks", {"channel": "jobs"})
    assert data["counts"]["pending"] == 1 and data["counts"]["claimed"] == 1
    assert len(data["tasks"]) == 2
    # payload is not leaked in the inspection view
    assert "payload" not in data["tasks"][0]


@pytest.mark.asyncio
async def test_clear_channel_drops_tasks(fresh_db):
    await call("bridge_enqueue", {"channel": "jobs", "content": "a"})
    await call("bridge_clear", {"channel": "jobs"})
    data = await call("bridge_tasks", {"channel": "jobs"})
    assert all(v == 0 for v in data["counts"].values())


@pytest.mark.asyncio
async def test_invalid_channel_is_rejected(fresh_db):
    with pytest.raises(BridgeValidationError):
        await call("bridge_enqueue", {"channel": "", "content": "a"})


@pytest.mark.asyncio
async def test_claim_long_poll_wakes_on_enqueue(fresh_db):
    async def producer():
        await asyncio.sleep(0.1)
        await call("bridge_enqueue", {"channel": "jobs", "content": "late"})

    task = asyncio.create_task(producer())
    claim = await call(
        "bridge_claim",
        {"channel": "jobs", "consumer": "w", "lease_seconds": 60, "wait_seconds": 5},
    )
    await task
    assert claim["task"] is not None and claim["task"]["payload"] == "late"


# ── Time-dependent behaviour (store level, injected ``now``) ───────────────────


def test_lease_expiry_requeues_with_attempt_increment(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", now=at(0))
    c1 = store.claim(channel="q", consumer="w1", lease_seconds=10, now=at(0))
    assert c1.attempts == 1
    # Before the lease expires the task is not reclaimable.
    assert store.claim(channel="q", consumer="w2", lease_seconds=10, now=at(5)) is None
    # After it expires the next claim reclaims it and increments attempts.
    c2 = store.claim(channel="q", consumer="w2", lease_seconds=10, now=at(20))
    assert c2.id == c1.id and c2.attempts == 2


def test_lease_expiry_dead_letters_after_max_attempts(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", max_attempts=1, now=at(0))
    store.claim(channel="q", consumer="w1", lease_seconds=5, now=at(0))
    # The lease expires with attempts == max; the next claim dead-letters it.
    assert store.claim(channel="q", consumer="w2", lease_seconds=5, now=at(100)) is None
    assert store.counts(channel="q")["dead"] == 1


def test_delay_seconds_gates_claim(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", delay_seconds=30, now=at(0))
    assert store.claim(channel="q", consumer="w", lease_seconds=5, now=at(10)) is None
    claimed = store.claim(channel="q", consumer="w", lease_seconds=5, now=at(31))
    assert claimed is not None and claimed.payload == "A"


def test_fail_retry_delay_backs_off(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", max_attempts=3, now=at(0))
    c = store.claim(channel="q", consumer="w", lease_seconds=60, now=at(0))
    store.fail(
        channel="q", task_id=c.id, lease_token=c.lease_token,
        requeue=True, retry_delay_seconds=30, now=at(1),
    )
    # Requeued but not yet available.
    assert store.claim(channel="q", consumer="w", lease_seconds=60, now=at(10)) is None
    assert store.claim(channel="q", consumer="w", lease_seconds=60, now=at(31)) is not None


def test_requeue_expired_sweep(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", now=at(0))
    store.claim(channel="q", consumer="w", lease_seconds=10, now=at(0))
    swept = store.requeue_expired(now=at(100))
    assert swept.requeued == 1 and swept.dead_lettered == 0
    assert store.counts(channel="q")["pending"] == 1


def test_prune_terminal_removes_finished_tasks(fresh_db):
    store = bridge.task_store()
    enq = store.enqueue(channel="q", payload="A", now=at(0))
    c = store.claim(channel="q", consumer="w", lease_seconds=60, now=at(0))
    store.complete(channel="q", task_id=c.id, lease_token=c.lease_token, now=at(1))
    # Not old enough yet.
    assert store.prune_terminal(older_than_iso=at(0).isoformat().replace("+00:00", "Z")) == 0
    removed = store.prune_terminal(
        older_than_iso=at(100).isoformat().replace("+00:00", "Z")
    )
    assert removed == 1
    assert store.counts(channel="q")["completed"] == 0
    assert enq.task.id  # sanity: the enqueue returned a task


def test_delete_channel_removes_all_tasks(fresh_db):
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", now=at(0))
    store.enqueue(channel="q", payload="B", now=at(1))
    assert store.delete_channel(channel="q") == 2
    assert store.counts(channel="q")["pending"] == 0


def test_status_invariant_holds_across_lifecycle(fresh_db):
    """The claimed<->lease-fields CHECK never rejects a legal transition."""
    store = bridge.task_store()
    store.enqueue(channel="q", payload="A", max_attempts=2, now=at(0))
    c = store.claim(channel="q", consumer="w", lease_seconds=5, now=at(0))
    t = store.fail(channel="q", task_id=c.id, lease_token=c.lease_token, now=at(1))
    assert t.status is TaskStatus.PENDING and t.lease_owner is None
    c2 = store.claim(channel="q", consumer="w", lease_seconds=5, now=at(2))
    t2 = store.complete(channel="q", task_id=c2.id, lease_token=c2.lease_token, now=at(3))
    assert t2.status is TaskStatus.COMPLETED and t2.lease_token is None
