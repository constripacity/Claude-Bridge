"""Idempotency and durable consumer-cursor tests."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from claude_bridge.protocol import compute_payload_hash
from claude_bridge.reliability import (
    CursorMessageNotFoundError,
    IdempotencyReservationError,
    IdempotencyState,
    ReliabilityStore,
    ReservationStatus,
    ensure_reliability_schema,
    resolve_channel_message_seq,
)


NOW = datetime(2026, 7, 18, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    connection = sqlite3.connect(tmp_path / "reliability.db", isolation_level=None)
    connection.execute(
        """
        CREATE TABLE messages (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            channel TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    yield connection
    connection.close()


def insert_message(conn, message_id, channel="project:worker"):
    cur = conn.execute(
        "INSERT INTO messages(id, channel, sender, content, timestamp) "
        "VALUES (?, ?, 'agent', 'payload', '2026-07-18T04:00:00Z')",
        (message_id, channel),
    )
    return cur.lastrowid


def reserve(store, *, key="request-1", content="same", now=NOW, **overrides):
    values = {
        "channel": "project:worker",
        "sender": "orchestrator",
        "key": key,
        "payload_sha256": compute_payload_hash(content),
        "ttl_seconds": 60,
        "now": now,
    }
    values.update(overrides)
    return store.reserve_idempotency(**values)


def test_schema_setup_is_idempotent_and_versioned(conn):
    ensure_reliability_schema(conn)
    ensure_reliability_schema(conn)
    row = conn.execute(
        "SELECT version FROM bridge_schema_components WHERE component='reliability'"
    ).fetchone()
    assert row == (1,)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "bridge_idempotency" in tables
    assert "bridge_consumer_cursors" in tables


def test_first_reservation_then_in_progress(conn):
    store = ReliabilityStore(conn)
    first = reserve(store)
    second = reserve(store)
    assert first.status is ReservationStatus.RESERVED
    assert first.should_insert
    assert first.record.state is IdempotencyState.PENDING
    assert second.status is ReservationStatus.IN_PROGRESS
    assert not second.should_insert


def test_committed_retry_replays_original_message(conn):
    store = ReliabilityStore(conn)
    reservation = reserve(store)
    record = store.commit_idempotency(
        channel=reservation.record.channel,
        sender=reservation.record.sender,
        key=reservation.record.key,
        payload_sha256=reservation.record.payload_sha256,
        message_id="message-1",
        message_seq=7,
        now=NOW,
    )
    assert record.state is IdempotencyState.COMMITTED
    assert record.message_id == "message-1"
    assert record.message_seq == 7

    retry = reserve(store)
    assert retry.status is ReservationStatus.REPLAY
    assert retry.record.message_id == "message-1"

    # Committing the identical result again is itself idempotent.
    assert (
        store.commit_idempotency(
            channel=record.channel,
            sender=record.sender,
            key=record.key,
            payload_sha256=record.payload_sha256,
            message_id="message-1",
            message_seq=7,
            now=NOW,
        )
        == record
    )


def test_same_key_with_different_payload_is_conflict(conn):
    store = ReliabilityStore(conn)
    original = reserve(store, content="first")
    conflict = reserve(store, content="different")
    assert original.status is ReservationStatus.RESERVED
    assert conflict.status is ReservationStatus.CONFLICT
    assert conflict.record.payload_sha256 == original.record.payload_sha256


def test_keys_are_scoped_by_channel_and_sender(conn):
    store = ReliabilityStore(conn)
    assert reserve(store).status is ReservationStatus.RESERVED
    assert (
        reserve(store, channel="another:channel").status
        is ReservationStatus.RESERVED
    )
    assert reserve(store, sender="another-agent").status is ReservationStatus.RESERVED


def test_failed_send_can_release_only_matching_pending_reservation(conn):
    store = ReliabilityStore(conn)
    record = reserve(store).record
    assert not store.release_idempotency(
        channel=record.channel,
        sender=record.sender,
        key=record.key,
        payload_sha256=compute_payload_hash("wrong"),
    )
    assert store.release_idempotency(
        channel=record.channel,
        sender=record.sender,
        key=record.key,
        payload_sha256=record.payload_sha256,
    )
    assert store.get_idempotency(
        channel=record.channel, sender=record.sender, key=record.key
    ) is None
    assert reserve(store).status is ReservationStatus.RESERVED


def test_expired_pending_reservation_can_be_reclaimed(conn):
    store = ReliabilityStore(conn)
    first = reserve(store, content="old")
    later = NOW + timedelta(seconds=61)
    replacement = reserve(store, content="new", now=later)
    assert replacement.status is ReservationStatus.RESERVED
    assert replacement.record.payload_sha256 != first.record.payload_sha256
    assert replacement.record.created_at != first.record.created_at


def test_cleanup_is_bounded_and_commit_rejects_expired_reservation(conn):
    store = ReliabilityStore(conn)
    expired = reserve(store, now=NOW, ttl_seconds=1).record
    reserve(store, key="request-2", now=NOW, ttl_seconds=1)
    with pytest.raises(IdempotencyReservationError):
        store.commit_idempotency(
            channel=expired.channel,
            sender=expired.sender,
            key=expired.key,
            payload_sha256=expired.payload_sha256,
            message_id="late-message",
            message_seq=1,
            now=NOW + timedelta(seconds=2),
        )
    assert store.cleanup_expired_idempotency(
        now=NOW + timedelta(seconds=2), limit=1
    ) == 1
    assert store.cleanup_expired_idempotency(
        now=NOW + timedelta(seconds=2), limit=10
    ) == 1


def test_cursor_advances_monotonically(conn):
    store = ReliabilityStore(conn)
    first = store.advance_cursor(
        consumer_id="reviewer",
        channel="project:worker",
        last_seq=10,
        last_message_id="message-10",
        metadata={"host": "mac"},
        now=NOW,
    )
    assert first.advanced
    assert first.cursor.last_seq == 10
    assert first.cursor.metadata == {"host": "mac"}

    stale = store.advance_cursor(
        consumer_id="reviewer",
        channel="project:worker",
        last_seq=4,
        last_message_id="message-4",
        metadata={"host": "windows"},
        now=NOW + timedelta(seconds=1),
    )
    assert not stale.advanced
    assert stale.cursor.last_seq == 10
    assert stale.cursor.last_message_id == "message-10"
    assert stale.cursor.metadata == {"host": "mac"}

    newer = store.advance_cursor(
        consumer_id="reviewer",
        channel="project:worker",
        last_seq=11,
        last_message_id="message-11",
        now=NOW + timedelta(seconds=2),
    )
    assert newer.advanced
    assert newer.cursor.last_seq == 11
    # Omitted metadata is preserved; passing {} explicitly would clear it.
    assert newer.cursor.metadata == {"host": "mac"}


def test_cursors_are_isolated_by_consumer_and_channel(conn):
    store = ReliabilityStore(conn)
    store.advance_cursor(consumer_id="a", channel="one", last_seq=2)
    store.advance_cursor(consumer_id="a", channel="two", last_seq=3)
    store.advance_cursor(consumer_id="b", channel="one", last_seq=4)
    assert store.get_cursor(consumer_id="a", channel="one").last_seq == 2
    assert store.get_cursor(consumer_id="a", channel="two").last_seq == 3
    assert store.get_cursor(consumer_id="b", channel="one").last_seq == 4


def test_explicit_reset_can_move_cursor_backwards(conn):
    store = ReliabilityStore(conn)
    store.advance_cursor(consumer_id="a", channel="one", last_seq=20)
    reset = store.reset_cursor(consumer_id="a", channel="one")
    assert reset.last_seq == 0
    assert reset.last_message_id is None
    assert store.delete_cursor(consumer_id="a", channel="one")
    assert store.get_cursor(consumer_id="a", channel="one") is None


def test_acknowledge_resolves_cursor_within_channel_only(conn):
    store = ReliabilityStore(conn)
    seq_a = insert_message(conn, "shared-a", channel="a")
    insert_message(conn, "shared-b", channel="b")

    result = store.acknowledge_message(
        consumer_id="worker", channel="a", message_id="shared-a", now=NOW
    )
    assert result.cursor.last_seq == seq_a
    assert resolve_channel_message_seq(conn, "a", "shared-a") == seq_a
    assert resolve_channel_message_seq(conn, "b", "shared-a") is None
    with pytest.raises(CursorMessageNotFoundError):
        store.acknowledge_message(
            consumer_id="worker", channel="b", message_id="shared-a", now=NOW
        )


def test_records_survive_repository_recreation(conn):
    first = ReliabilityStore(conn)
    first.advance_cursor(consumer_id="agent", channel="project", last_seq=9)
    record = reserve(first).record

    second = ReliabilityStore(conn)
    assert second.get_cursor(consumer_id="agent", channel="project").last_seq == 9
    assert (
        second.get_idempotency(
            channel=record.channel, sender=record.sender, key=record.key
        ).payload_sha256
        == record.payload_sha256
    )
