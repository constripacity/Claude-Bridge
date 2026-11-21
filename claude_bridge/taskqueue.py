"""SQLite-backed task queue for work distribution across agent fleets.

Where ``messages`` is a fan-out log (every consumer cursor sees every row), a
task is **exclusive**: enqueued once, claimed by exactly one worker, and either
completed or retried.  This module adds a ``tasks`` table and a small
:class:`TaskStore` that mirrors :class:`claude_bridge.reliability.ReliabilityStore`
— it binds to the shared connection, guards every write with a savepoint so it
composes inside the caller's ``BEGIN IMMEDIATE``, and expects the same
application write-lock that serializes message inserts.

Guarantees:

* **Atomic claim** — under the caller's single-writer lock, claiming selects the
  oldest eligible pending task and leases it; no two workers get the same task.
* **At-least-once** — a claim increments ``attempts`` and sets a visibility
  timeout (``lease_expires_at``).  An unacked lease is requeued (or dead-lettered
  past ``max_attempts``) lazily at the next claim and by the housekeeping sweep.
* **Lease fencing** — ``complete``/``fail`` require the ``lease_token`` minted at
  claim time, so a worker whose lease was reclaimed cannot clobber the result.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterator

from .migrations import add_missing_columns
from .validation import (
    DEFAULT_LIMITS,
    BridgeValidationError,
    normalize_limit,
    validate_channel,
    validate_consumer,
    validate_non_negative_int,
    validate_reference,
    validate_sender,
    validate_title,
)

TASKQUEUE_SCHEMA_VERSION = 1

# Upper bounds on integer parameters. Counts stay well within SQLite's 64-bit
# INTEGER; seconds-valued fields stay far under the range where
# ``timedelta(seconds=…)`` added to a current datetime overflows. Exceeding
# either now raises a structured BridgeValidationError instead of a raw
# OverflowError from the INSERT or the timedelta arithmetic.
_MAX_COUNT = 2**31 - 1
_MAX_TASK_SECONDS = 10**9  # ~31.7 years; larger than any legitimate delay/lease
# Every claim returns all notes of its task, so count and size are bounded.
MAX_NOTES_PER_TASK = 100
MAX_NOTE_BYTES = 16 * 1024
MAX_NOTE_BYTES_PER_TASK = 64 * 1024


class TaskQueueError(RuntimeError):
    """Base class for task-queue failures safe to handle explicitly."""


class TaskNotFoundError(TaskQueueError):
    def __init__(self, channel: str, task_id: str) -> None:
        self.channel = channel
        self.task_id = task_id
        super().__init__(f"task {task_id!r} was not found in channel {channel!r}")


class TaskLeaseError(TaskQueueError):
    """The lease token did not match a live claim (expired or reclaimed)."""

    def __init__(self, channel: str, task_id: str) -> None:
        self.channel = channel
        self.task_id = task_id
        super().__init__(f"lease on task {task_id!r} is no longer held")


class TaskNotActiveError(TaskQueueError):
    """A note was sent to a task that is already completed, failed or dead."""

    def __init__(self, channel: str, task_id: str) -> None:
        self.channel = channel
        self.task_id = task_id
        super().__init__(f"task {task_id!r} is no longer pending or claimed")


class TaskAction(str, Enum):
    """A task change that a caller can be refused."""

    REPLACE = "replace"

    @property
    def past_participle(self) -> str:
        return {TaskAction.REPLACE: "replaced"}[self]


class TaskPermissionError(TaskQueueError):
    """The caller is not the task's original enqueuer."""

    def __init__(self, channel: str, task_id: str, action: TaskAction) -> None:
        self.channel = channel
        self.task_id = task_id
        self.action = action
        super().__init__(
            f"only the original enqueuer may {action.value} task {task_id!r}"
        )


class TaskStateError(TaskQueueError):
    """The task's current status does not permit the requested change."""

    def __init__(
        self, channel: str, task_id: str, status: TaskStatus, action: TaskAction
    ) -> None:
        self.channel = channel
        self.task_id = task_id
        self.status = status
        self.action = action
        super().__init__(
            f"cannot {action.value} task {task_id!r}: it is {status.value}"
        )


class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_text(value: object, field: str, max_bytes: int) -> str:
    """Bounded free-text field (payload/result/error): string, capped, NUL-free."""
    if not isinstance(value, str):
        raise BridgeValidationError(field, "invalid_type", "must be a string")
    if len(value.encode("utf-8")) > max_bytes:
        raise BridgeValidationError(
            field, "too_large", f"must be at most {max_bytes} UTF-8 bytes"
        )
    if "\x00" in value:
        raise BridgeValidationError(field, "nul_byte", "must not contain NUL bytes")
    return value


DERIVED_TITLE_CHARS = 80


def derive_task_title(payload: str) -> str | None:
    """A short title from a payload: its `title`/`task` field, else its text."""
    lines = (_drop_controls(line) for line in _title_source(payload).splitlines())
    first_line = next((line for line in lines if line.strip()), "")
    title = " ".join(first_line.split())
    if len(title) > DERIVED_TITLE_CHARS:
        return title[: DERIVED_TITLE_CHARS - 1] + "…"
    return title or None


def _drop_controls(line: str) -> str:
    # Whitespace controls such as tab stay, so the collapse turns them into a space.
    return "".join(
        char for char in line
        if char.isspace() or unicodedata.category(char) != "Cc"
    )


def _title_source(payload: str) -> str:
    try:
        parsed = json.loads(payload)
    except (ValueError, RecursionError):
        return payload
    if isinstance(parsed, dict):
        for field in ("title", "task"):
            value = parsed.get(field)
            if isinstance(value, str) and value.strip():
                return value
    return payload


def _resolve_title(title: str | None, payload: str) -> str | None:
    return derive_task_title(payload) if title is None else validate_title(title)


# Columns added after v1.3.0; an older DB gets them in place on startup.
_TASK_ADDED_COLUMNS = {
    "worked_by": "TEXT",
    "notes_read_seq": "INTEGER NOT NULL DEFAULT 0",
    "title": "TEXT",
}


@contextmanager
def _savepoint(conn: sqlite3.Connection) -> Iterator[None]:
    # Generated by us, not user input, and therefore safe as a SQL identifier.
    name = f"bridge_task_{uuid.uuid4().hex}"
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        conn.execute(f"RELEASE SAVEPOINT {name}")
        raise
    else:
        conn.execute(f"RELEASE SAVEPOINT {name}")


def ensure_taskqueue_schema(conn: sqlite3.Connection) -> None:
    """Create the task-queue schema idempotently and register its version."""

    with _savepoint(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bridge_schema_components (
                component  TEXT PRIMARY KEY,
                version    INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT version FROM bridge_schema_components WHERE component = ?",
            ("taskqueue",),
        ).fetchone()
        if row is not None and int(row[0]) > TASKQUEUE_SCHEMA_VERSION:
            raise TaskQueueError(
                "database task-queue schema is newer than this server supports"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                seq              INTEGER PRIMARY KEY AUTOINCREMENT,
                id               TEXT    NOT NULL UNIQUE,
                channel          TEXT    NOT NULL,
                payload          TEXT    NOT NULL,
                status           TEXT    NOT NULL CHECK (
                    status IN ('pending','claimed','completed','failed','dead')),
                priority         INTEGER NOT NULL DEFAULT 0,
                attempts         INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                max_attempts     INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
                available_at     TEXT    NOT NULL,
                lease_owner      TEXT,
                lease_token      TEXT,
                lease_expires_at TEXT,
                result           TEXT,
                last_error       TEXT,
                idempotency_key  TEXT,
                enqueued_by      TEXT,
                worked_by        TEXT,
                notes_read_seq   INTEGER NOT NULL DEFAULT 0,
                title            TEXT,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                CHECK (
                    (status = 'claimed'
                        AND lease_owner IS NOT NULL
                        AND lease_token IS NOT NULL
                        AND lease_expires_at IS NOT NULL)
                    OR
                    (status != 'claimed'
                        AND lease_owner IS NULL
                        AND lease_token IS NULL
                        AND lease_expires_at IS NULL)
                )
            )
            """
        )
        add_missing_columns(conn, "tasks", _TASK_ADDED_COLUMNS)
        # Claim scan: oldest eligible pending task on a channel, priority first.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_ready "
            "ON tasks(channel, priority DESC, available_at, seq) WHERE status = 'pending'"
        )
        # Lease-expiry sweep.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_lease "
            "ON tasks(lease_expires_at) WHERE status = 'claimed'"
        )
        # Enqueue dedupe by idempotency key, scoped per channel.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency "
            "ON tasks(channel, idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_notes (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                id         TEXT    NOT NULL UNIQUE,
                channel    TEXT    NOT NULL,
                task_id    TEXT    NOT NULL,
                sender     TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_notes_task ON task_notes(task_id, seq)"
        )
        # Inspection / counts.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_channel_status "
            "ON tasks(channel, status)"
        )
        now = _timestamp(_utc_now())
        conn.execute(
            "INSERT INTO bridge_schema_components(component, version, updated_at) "
            "VALUES (?, ?, ?) ON CONFLICT(component) DO UPDATE SET "
            "version = excluded.version, updated_at = excluded.updated_at "
            "WHERE bridge_schema_components.version < excluded.version",
            ("taskqueue", TASKQUEUE_SCHEMA_VERSION, now),
        )


@dataclass(frozen=True, slots=True)
class Task:
    seq: int
    id: str
    channel: str
    payload: str
    status: TaskStatus
    priority: int
    attempts: int
    max_attempts: int
    available_at: str
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: str | None
    result: str | None
    last_error: str | None
    idempotency_key: str | None
    enqueued_by: str | None
    worked_by: str | None  # Last consumer that claimed the task; never cleared.
    notes_read_seq: int  # Highest note seq delivered to the current lease.
    title: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TaskNote:
    seq: int
    id: str
    channel: str
    task_id: str
    sender: str
    content: str
    created_at: str


@dataclass(frozen=True, slots=True)
class TaskWithNotes:
    """A task write result plus the notes its worker must see now."""

    task: Task
    notes: list[TaskNote]


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    task: Task
    created: bool  # False when an idempotency key returned an existing task.


@dataclass(frozen=True, slots=True)
class SweepResult:
    requeued: int
    dead_lettered: int


# One column order for SELECT and row mapping: the field order of Task.
_TASK_FIELDS = tuple(field.name for field in fields(Task))
_TASK_COLUMNS = ", ".join(_TASK_FIELDS)
_TASK_SELECT = f"SELECT {_TASK_COLUMNS} FROM tasks "


def _task_from_row(row: sqlite3.Row | tuple) -> Task:
    values = dict(zip(_TASK_FIELDS, tuple(row), strict=True))
    values["status"] = TaskStatus(values["status"])
    return Task(**values)


_NOTE_SELECT = (
    "SELECT seq, id, channel, task_id, sender, content, created_at FROM task_notes "
)


def _note_from_row(row: sqlite3.Row | tuple) -> TaskNote:
    return TaskNote(
        seq=int(row[0]),
        id=row[1],
        channel=row[2],
        task_id=row[3],
        sender=row[4],
        content=row[5],
        created_at=row[6],
    )


class TaskStore:
    """Repository for the exclusive task queue."""

    def __init__(self, conn: sqlite3.Connection, *, initialize: bool = True) -> None:
        self.conn = conn
        self._lock = threading.RLock()
        if initialize:
            with self._lock:
                ensure_taskqueue_schema(conn)

    # -- helpers ----------------------------------------------------------------

    def _get(self, channel: str, task_id: str) -> Task | None:
        row = self.conn.execute(
            _TASK_SELECT + "WHERE channel = ? AND id = ?", (channel, task_id)
        ).fetchone()
        return _task_from_row(row) if row is not None else None

    def _resolve_expired_leases(self, channel: str, instant: str) -> None:
        """Requeue (or dead-letter) leases past their visibility timeout.

        Called at the start of a claim so an abandoned task becomes claimable
        immediately, without waiting for the background sweep.
        """

        self.conn.execute(
            "UPDATE tasks SET status = 'pending', lease_owner = NULL, "
            "lease_token = NULL, lease_expires_at = NULL, updated_at = ? "
            "WHERE channel = ? AND status = 'claimed' AND lease_expires_at <= ? "
            "AND attempts < max_attempts",
            (instant, channel, instant),
        )
        self.conn.execute(
            "UPDATE tasks SET status = 'dead', lease_owner = NULL, "
            "lease_token = NULL, lease_expires_at = NULL, updated_at = ?, "
            "last_error = 'lease expired after max attempts' "
            "WHERE channel = ? AND status = 'claimed' AND lease_expires_at <= ? "
            "AND attempts >= max_attempts",
            (instant, channel, instant),
        )

    # -- operations -------------------------------------------------------------

    def enqueue(
        self,
        *,
        channel: str,
        payload: str,
        priority: int = 0,
        max_attempts: int = 3,
        delay_seconds: int = 0,
        idempotency_key: str | None = None,
        enqueued_by: str | None = None,
        title: str | None = None,
        now: datetime | None = None,
    ) -> EnqueueResult:
        channel = validate_channel(channel)
        payload = _require_text(payload, "payload", DEFAULT_LIMITS.max_message_bytes)
        title = _resolve_title(title, payload)
        priority = validate_non_negative_int(priority, "priority", maximum=_MAX_COUNT)
        max_attempts = validate_non_negative_int(
            max_attempts, "max_attempts", maximum=_MAX_COUNT
        )
        if max_attempts < 1:
            raise BridgeValidationError(
                "max_attempts", "out_of_range", "must be at least 1"
            )
        delay_seconds = validate_non_negative_int(
            delay_seconds, "delay_seconds", maximum=_MAX_TASK_SECONDS
        )
        if idempotency_key is not None:
            idempotency_key = validate_reference(idempotency_key, "idempotency_key")
        if enqueued_by is not None:
            enqueued_by = validate_reference(enqueued_by, "enqueued_by")

        instant = _as_utc(now or _utc_now())
        created_at = _timestamp(instant)
        available_at = _timestamp(instant + timedelta(seconds=delay_seconds))
        task_id = "tsk_" + uuid.uuid4().hex

        with self._lock, _savepoint(self.conn):
            if idempotency_key is not None:
                existing = self.conn.execute(
                    _TASK_SELECT + "WHERE channel = ? AND idempotency_key = ?",
                    (channel, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return EnqueueResult(task=_task_from_row(existing), created=False)
            self.conn.execute(
                "INSERT INTO tasks (id, channel, payload, status, priority, attempts, "
                "max_attempts, available_at, idempotency_key, enqueued_by, title, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    channel,
                    payload,
                    priority,
                    max_attempts,
                    available_at,
                    idempotency_key,
                    enqueued_by,
                    title,
                    created_at,
                    created_at,
                ),
            )
            row = self.conn.execute(
                _TASK_SELECT + "WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:  # Defensive: INSERT/SELECT share one savepoint.
                raise TaskQueueError("task disappeared after insert")
            return EnqueueResult(task=_task_from_row(row), created=True)

    def claim(
        self,
        *,
        channel: str,
        consumer: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> Task | None:
        channel = validate_channel(channel)
        consumer = validate_consumer(consumer)
        lease_seconds = validate_non_negative_int(
            lease_seconds, "lease_seconds", maximum=_MAX_TASK_SECONDS
        )
        if lease_seconds < 1:
            raise BridgeValidationError(
                "lease_seconds", "out_of_range", "must be at least 1"
            )
        instant = _as_utc(now or _utc_now())
        now_iso = _timestamp(instant)
        lease_expires_at = _timestamp(instant + timedelta(seconds=lease_seconds))
        lease_token = uuid.uuid4().hex

        with self._lock, _savepoint(self.conn):
            self._resolve_expired_leases(channel, now_iso)
            row = self.conn.execute(
                "SELECT seq FROM tasks WHERE channel = ? AND status = 'pending' "
                "AND available_at <= ? ORDER BY priority DESC, seq ASC LIMIT 1",
                (channel, now_iso),
            ).fetchone()
            if row is None:
                return None
            seq = int(row[0])
            self.conn.execute(
                "UPDATE tasks SET status = 'claimed', lease_owner = ?, worked_by = ?, "
                "lease_token = ?, lease_expires_at = ?, attempts = attempts + 1, "
                "notes_read_seq = (SELECT COALESCE(MAX(seq), 0) FROM task_notes "
                "WHERE task_notes.task_id = tasks.id), "
                "updated_at = ? WHERE seq = ? AND status = 'pending'",
                (consumer, consumer, lease_token, lease_expires_at, now_iso, seq),
            )
            claimed = self.conn.execute(
                _TASK_SELECT + "WHERE seq = ?", (seq,)
            ).fetchone()
            return _task_from_row(claimed) if claimed is not None else None

    def complete(
        self,
        *,
        channel: str,
        task_id: str,
        lease_token: str,
        result: str | None = None,
        now: datetime | None = None,
    ) -> Task:
        channel = validate_channel(channel)
        task_id = validate_reference(task_id, "task_id")
        lease_token = validate_reference(lease_token, "lease_token")
        if result is not None:
            result = _require_text(result, "result", DEFAULT_LIMITS.max_message_bytes)
        now_iso = _timestamp(_as_utc(now or _utc_now()))

        with self._lock, _savepoint(self.conn):
            cur = self.conn.execute(
                "UPDATE tasks SET status = 'completed', result = ?, lease_owner = NULL, "
                "lease_token = NULL, lease_expires_at = NULL, updated_at = ? "
                "WHERE id = ? AND channel = ? AND status = 'claimed' AND lease_token = ?",
                (result, now_iso, task_id, channel, lease_token),
            )
            if cur.rowcount == 0:
                self._raise_fence_error(channel, task_id)
            row = self.conn.execute(
                _TASK_SELECT + "WHERE channel = ? AND id = ?", (channel, task_id)
            ).fetchone()
            return _task_from_row(row)

    def fail(
        self,
        *,
        channel: str,
        task_id: str,
        lease_token: str,
        requeue: bool = True,
        error: str | None = None,
        retry_delay_seconds: int = 0,
        now: datetime | None = None,
    ) -> Task:
        channel = validate_channel(channel)
        task_id = validate_reference(task_id, "task_id")
        lease_token = validate_reference(lease_token, "lease_token")
        if error is not None:
            error = _require_text(error, "error", DEFAULT_LIMITS.max_message_bytes)
        retry_delay_seconds = validate_non_negative_int(
            retry_delay_seconds, "retry_delay_seconds", maximum=_MAX_TASK_SECONDS
        )
        instant = _as_utc(now or _utc_now())
        now_iso = _timestamp(instant)
        available_at = _timestamp(instant + timedelta(seconds=retry_delay_seconds))

        with self._lock, _savepoint(self.conn):
            row = self.conn.execute(
                _TASK_SELECT + "WHERE id = ? AND channel = ? AND status = 'claimed' "
                "AND lease_token = ?",
                (task_id, channel, lease_token),
            ).fetchone()
            if row is None:
                self._raise_fence_error(channel, task_id)
            current = _task_from_row(row)
            if requeue and current.attempts < current.max_attempts:
                self.conn.execute(
                    "UPDATE tasks SET status = 'pending', lease_owner = NULL, "
                    "lease_token = NULL, lease_expires_at = NULL, available_at = ?, "
                    "last_error = ?, updated_at = ? WHERE seq = ?",
                    (available_at, error, now_iso, current.seq),
                )
            else:
                self.conn.execute(
                    "UPDATE tasks SET status = 'dead', lease_owner = NULL, "
                    "lease_token = NULL, lease_expires_at = NULL, last_error = ?, "
                    "updated_at = ? WHERE seq = ?",
                    (error, now_iso, current.seq),
                )
            updated = self.conn.execute(
                _TASK_SELECT + "WHERE seq = ?", (current.seq,)
            ).fetchone()
            return _task_from_row(updated)

    def add_note(
        self,
        *,
        channel: str,
        task_id: str,
        sender: str,
        content: str,
        now: datetime | None = None,
    ) -> TaskNote:
        """Attach a note to a pending or claimed task for its (next) worker."""
        channel = validate_channel(channel)
        task_id = validate_reference(task_id, "task_id")
        sender = validate_sender(sender)
        content = _require_text(content, "content", MAX_NOTE_BYTES)
        if not content.strip():
            raise BridgeValidationError("content", "required", "must not be empty")
        note_id = "note_" + uuid.uuid4().hex
        created_at = _timestamp(_as_utc(now or _utc_now()))

        with self._lock, _savepoint(self.conn):
            task = self._get(channel, task_id)
            if task is None:
                raise TaskNotFoundError(channel, task_id)
            if task.status not in (TaskStatus.PENDING, TaskStatus.CLAIMED):
                raise TaskNotActiveError(channel, task_id)
            self._check_room_for_note(task_id, content)
            cur = self.conn.execute(
                "INSERT INTO task_notes (id, channel, task_id, sender, content, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, channel, task_id, sender, content, created_at),
            )
            return TaskNote(
                seq=int(cur.lastrowid),
                id=note_id,
                channel=channel,
                task_id=task_id,
                sender=sender,
                content=content,
                created_at=created_at,
            )

    def _check_room_for_note(self, task_id: str, content: str) -> None:
        count, used_bytes = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(length(CAST(content AS BLOB))), 0) "
            "FROM task_notes WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if count >= MAX_NOTES_PER_TASK:
            raise BridgeValidationError(
                "task_id", "too_many_notes", f"already has {MAX_NOTES_PER_TASK} notes"
            )
        if used_bytes + len(content.encode("utf-8")) > MAX_NOTE_BYTES_PER_TASK:
            raise BridgeValidationError(
                "content",
                "task_notes_too_large",
                f"would take the notes of the task over {MAX_NOTE_BYTES_PER_TASK} "
                "UTF-8 bytes",
            )

    def all_notes(self, task: Task) -> list[TaskNote]:
        """Every note of the task in send order."""
        return self._notes_after(task.id, 0)

    def unread_notes(self, task: Task) -> list[TaskNote]:
        """Notes the current (or last) lease has not seen yet."""
        return self._notes_after(task.id, task.notes_read_seq)

    def _notes_after(self, task_id: str, seq: int) -> list[TaskNote]:
        with self._lock:
            rows = self.conn.execute(
                _NOTE_SELECT + "WHERE task_id = ? AND seq > ? ORDER BY seq",
                (task_id, seq),
            ).fetchall()
        return [_note_from_row(r) for r in rows]

    def take_new_notes(
        self, *, channel: str, task_id: str, lease_token: str
    ) -> list[TaskNote]:
        """Return notes sent since the lease last read them, and advance its cursor."""
        channel = validate_channel(channel)
        task_id = validate_reference(task_id, "task_id")
        lease_token = validate_reference(lease_token, "lease_token")

        with self._lock, _savepoint(self.conn):
            row = self.conn.execute(
                _TASK_SELECT + "WHERE id = ? AND channel = ? AND status = 'claimed' "
                "AND lease_token = ?",
                (task_id, channel, lease_token),
            ).fetchone()
            if row is None:
                self._raise_fence_error(channel, task_id)
            task = _task_from_row(row)
            new_notes = self.unread_notes(task)
            if new_notes:
                self.conn.execute(
                    "UPDATE tasks SET notes_read_seq = ? WHERE seq = ?",
                    (new_notes[-1].seq, task.seq),
                )
            return new_notes

    def replace(
        self,
        *,
        channel: str,
        task_id: str,
        sender: str,
        payload: str,
        priority: int | None = None,
        delay_seconds: int | None = None,
        title: str | None = None,
        now: datetime | None = None,
    ) -> Task:
        """Swap a pending task's payload in place; id and queue position stay.

        Only the original enqueuer may replace. Sender names are self-asserted.
        """
        channel = validate_channel(channel)
        task_id = validate_reference(task_id, "task_id")
        sender = validate_reference(sender, "sender")
        payload = _require_text(payload, "payload", DEFAULT_LIMITS.max_message_bytes)
        title = _resolve_title(title, payload)
        if priority is not None:
            priority = validate_non_negative_int(priority, "priority", maximum=_MAX_COUNT)
        instant = _as_utc(now or _utc_now())
        available_at = None
        if delay_seconds is not None:
            delay_seconds = validate_non_negative_int(
                delay_seconds, "delay_seconds", maximum=_MAX_TASK_SECONDS
            )
            available_at = _timestamp(instant + timedelta(seconds=delay_seconds))

        with self._lock, _savepoint(self.conn):
            current = self._require_replaceable(channel, task_id, sender)
            # A replaced task is new work, so earlier attempts and errors no longer apply.
            self.conn.execute(
                "UPDATE tasks SET payload = ?, title = ?, "
                "priority = COALESCE(?, priority), "
                "available_at = COALESCE(?, available_at), attempts = 0, "
                "last_error = NULL, updated_at = ? WHERE seq = ?",
                (
                    payload,
                    title,
                    priority,
                    available_at,
                    _timestamp(instant),
                    current.seq,
                ),
            )
            row = self.conn.execute(
                _TASK_SELECT + "WHERE seq = ?", (current.seq,)
            ).fetchone()
            return _task_from_row(row)

    def _require_replaceable(self, channel: str, task_id: str, sender: str) -> Task:
        current = self._get(channel, task_id)
        if current is None:
            raise TaskNotFoundError(channel, task_id)
        if current.enqueued_by != sender:
            raise TaskPermissionError(channel, task_id, TaskAction.REPLACE)
        if current.status is not TaskStatus.PENDING:
            raise TaskStateError(channel, task_id, current.status, TaskAction.REPLACE)
        return current

    def _raise_fence_error(self, channel: str, task_id: str) -> None:
        """Distinguish an unknown task from a lost lease for a helpful error."""
        if self._get(channel, task_id) is None:
            raise TaskNotFoundError(channel, task_id)
        raise TaskLeaseError(channel, task_id)

    def counts(self, *, channel: str) -> dict[str, int]:
        channel = validate_channel(channel)
        with self._lock:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) FROM tasks WHERE channel = ? GROUP BY status",
                (channel,),
            ).fetchall()
        counts = {s.value: 0 for s in TaskStatus}
        for status, count in rows:
            counts[status] = int(count)
        return counts

    def list_tasks(
        self, *, channel: str, status: str | None = None, limit: int = 50
    ) -> list[Task]:
        channel = validate_channel(channel)
        limit = normalize_limit(limit, default=50, maximum=500)
        query = _TASK_SELECT + "WHERE channel = ?"
        params: list = [channel]
        if status is not None:
            if status not in {s.value for s in TaskStatus}:
                raise BridgeValidationError(
                    "status", "invalid", "must be one of "
                    + ", ".join(s.value for s in TaskStatus)
                )
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [_task_from_row(r) for r in rows]

    def requeue_expired(
        self, *, now: datetime | None = None, limit: int = 1000
    ) -> SweepResult:
        """Background sweep: requeue or dead-letter leases past their timeout."""
        instant = _timestamp(_as_utc(now or _utc_now()))
        limit = normalize_limit(limit, default=1000, maximum=10_000)
        with self._lock, _savepoint(self.conn):
            requeued = self.conn.execute(
                "UPDATE tasks SET status = 'pending', lease_owner = NULL, "
                "lease_token = NULL, lease_expires_at = NULL, updated_at = ? "
                "WHERE rowid IN (SELECT rowid FROM tasks WHERE status = 'claimed' "
                "AND lease_expires_at <= ? AND attempts < max_attempts "
                "ORDER BY lease_expires_at LIMIT ?)",
                (instant, instant, limit),
            ).rowcount
            dead = self.conn.execute(
                "UPDATE tasks SET status = 'dead', lease_owner = NULL, "
                "lease_token = NULL, lease_expires_at = NULL, updated_at = ?, "
                "last_error = 'lease expired after max attempts' "
                "WHERE rowid IN (SELECT rowid FROM tasks WHERE status = 'claimed' "
                "AND lease_expires_at <= ? AND attempts >= max_attempts "
                "ORDER BY lease_expires_at LIMIT ?)",
                (instant, instant, limit),
            ).rowcount
        return SweepResult(requeued=requeued, dead_lettered=dead)

    def prune_terminal(self, *, older_than_iso: str, limit: int = 1000) -> int:
        """Delete finished tasks (completed/failed/dead) older than a cutoff."""
        limit = normalize_limit(limit, default=1000, maximum=10_000)
        doomed = (
            "SELECT rowid FROM tasks WHERE status IN ('completed','failed','dead') "
            "AND updated_at < ? ORDER BY updated_at, seq LIMIT ?"
        )
        with self._lock, _savepoint(self.conn):
            self.conn.execute(
                "DELETE FROM task_notes WHERE task_id IN "
                f"(SELECT id FROM tasks WHERE rowid IN ({doomed}))",
                (older_than_iso, limit),
            )
            return self.conn.execute(
                f"DELETE FROM tasks WHERE rowid IN ({doomed})",
                (older_than_iso, limit),
            ).rowcount

    def delete_orphan_notes(self) -> int:
        """Delete notes whose task is gone, e.g. pruned by a server without notes."""
        with self._lock, _savepoint(self.conn):
            return self.conn.execute(
                "DELETE FROM task_notes WHERE NOT EXISTS "
                "(SELECT 1 FROM tasks WHERE tasks.id = task_notes.task_id)"
            ).rowcount

    def delete_channel(self, *, channel: str) -> int:
        """Remove every task and task note on a channel (used by bridge_clear)."""
        channel = validate_channel(channel)
        with self._lock, _savepoint(self.conn):
            self.conn.execute("DELETE FROM task_notes WHERE channel = ?", (channel,))
            return self.conn.execute(
                "DELETE FROM tasks WHERE channel = ?", (channel,)
            ).rowcount


def task_to_dict(task: Task, *, include_payload: bool = True) -> dict:
    """Serialize a task for a tool/API response (lease_token omitted by design)."""
    data = {
        "task_id": task.id,
        "channel": task.channel,
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "available_at": task.available_at,
        "lease_owner": task.lease_owner,
        "lease_expires_at": task.lease_expires_at,
        "result": task.result,
        "last_error": task.last_error,
        "idempotency_key": task.idempotency_key,
        "enqueued_by": task.enqueued_by,
        "worked_by": task.worked_by,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
    if include_payload:
        data["payload"] = task.payload
    return data


def note_to_dict(note: TaskNote) -> dict:
    return {
        "seq": note.seq,
        "id": note.id,
        "task_id": note.task_id,
        "sender": note.sender,
        "content": note.content,
        "created_at": note.created_at,
    }


def notes_to_dicts(notes: list[TaskNote]) -> list[dict]:
    return [note_to_dict(n) for n in notes]


__all__ = [
    "EnqueueResult",
    "MAX_NOTE_BYTES",
    "MAX_NOTE_BYTES_PER_TASK",
    "MAX_NOTES_PER_TASK",
    "SweepResult",
    "TASKQUEUE_SCHEMA_VERSION",
    "Task",
    "TaskAction",
    "TaskLeaseError",
    "TaskNote",
    "TaskNotActiveError",
    "TaskNotFoundError",
    "TaskPermissionError",
    "TaskQueueError",
    "TaskStateError",
    "TaskStatus",
    "TaskStore",
    "TaskWithNotes",
    "derive_task_title",
    "ensure_taskqueue_schema",
    "note_to_dict",
    "notes_to_dicts",
    "task_to_dict",
]
