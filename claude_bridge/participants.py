"""Who is on the bridge: when each participant was last seen and what it holds.

Every client shares one bearer token, so a name is self-declared: this is a
presence hint for operators, not an identity or an access-control record.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .migrations import add_missing_columns
from .validation import BridgeValidationError

# Usage columns added after the participants table first shipped.
_PARTICIPANT_ADDED_COLUMNS = {
    "usage_session_pct": "REAL",
    "usage_session_resets_at": "TEXT",
    "usage_weekly_pct": "REAL",
    "usage_weekly_resets_at": "TEXT",
    "usage_reported_at": "TEXT",
}


def ensure_participants_schema(conn: sqlite3.Connection) -> None:
    """Create the participants table idempotently and add newer columns."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
            name                    TEXT PRIMARY KEY,
            last_seen               TEXT NOT NULL,
            current_channel         TEXT,
            current_task_id         TEXT,
            usage_session_pct       REAL,
            usage_session_resets_at TEXT,
            usage_weekly_pct        REAL,
            usage_weekly_resets_at  TEXT,
            usage_reported_at       TEXT
        )
        """
    )
    add_missing_columns(conn, "participants", _PARTICIPANT_ADDED_COLUMNS)


# Tasks the participant row holds a live lease on; `:now` is bound per query.
_LIVE_LEASE = (
    "FROM tasks WHERE tasks.lease_owner = participants.name "
    "AND tasks.status = 'claimed' AND tasks.lease_expires_at > :now "
)


def _timestamp(value: datetime) -> str:
    # Same fixed-width format as task timestamps, so text order is time order.
    stamp = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return stamp.replace("+00:00", "Z")


def _now_iso() -> str:
    return _timestamp(datetime.now(timezone.utc))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


ONLINE_WITHIN = timedelta(minutes=10)
IDLE_WITHIN = timedelta(hours=24)


def presence(last_seen: str, now: datetime) -> str:
    """'online', 'idle' or 'offline' by the time since the participant was seen."""
    age = now - _parse_timestamp(last_seen)
    if age <= ONLINE_WITHIN:
        return "online"
    if age <= IDLE_WITHIN:
        return "idle"
    return "offline"


@dataclass(frozen=True, slots=True)
class Participant:
    name: str
    last_seen: str
    current_channel: str | None  # Channel of the current task (or of the last one).
    current_task_id: str | None  # Newest task it holds a live lease on, if any.


@dataclass(frozen=True, slots=True)
class UsageWindow:
    used_pct: float
    resets_at: str | None


@dataclass(frozen=True, slots=True)
class UsageReport:
    """A client's last reported rate-limit use; a missing window is unknown."""

    session: UsageWindow | None  # The rolling five-hour window.
    weekly: UsageWindow | None


def parse_usage_report(body: Any) -> UsageReport:
    """Validate a `{session: {...}, weekly: {...}}` usage body."""
    if not isinstance(body, dict):
        raise BridgeValidationError("body", "invalid_type", "must be an object")
    unknown = sorted(set(body) - {"session", "weekly"})
    if unknown:
        raise BridgeValidationError(unknown[0], "unknown_field", "is not a usage window")
    return UsageReport(
        session=_parse_usage_window(body.get("session"), "session"),
        weekly=_parse_usage_window(body.get("weekly"), "weekly"),
    )


def _parse_usage_window(value: Any, field: str) -> UsageWindow | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BridgeValidationError(field, "invalid_type", "must be an object")
    return UsageWindow(
        used_pct=_parse_used_pct(value.get("used_pct"), f"{field}.used_pct"),
        resets_at=_parse_resets_at(value.get("resets_at"), f"{field}.resets_at"),
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_used_pct(value: Any, field: str) -> float:
    if not _is_number(value) or not math.isfinite(value):
        raise BridgeValidationError(field, "invalid_type", "must be a finite number")
    if not 0 <= value <= 100:
        raise BridgeValidationError(field, "out_of_range", "must be within 0..100")
    return float(value)


def _parse_resets_at(value: Any, field: str) -> str | None:
    """Normalize unix seconds or an ISO-8601 string with an offset."""
    if value is None:
        return None
    if not (_is_number(value) or isinstance(value, str)):
        raise BridgeValidationError(
            field, "invalid_type", "must be unix seconds or an ISO-8601 string"
        )
    try:
        instant = _instant_from(value)
        # The UTC conversion overflows near datetime.min/max, so it stays in the try.
        stamp = None if instant.tzinfo is None else _timestamp(instant)
    except (ValueError, OverflowError, OSError) as exc:
        raise BridgeValidationError(field, "invalid", "is not a valid time") from exc
    if stamp is None:
        raise BridgeValidationError(field, "invalid", "must include a UTC offset")
    return stamp


def _instant_from(value: float | str) -> datetime:
    if isinstance(value, str):
        return _parse_timestamp(value)
    return datetime.fromtimestamp(value, timezone.utc)


def _window_columns(window: UsageWindow | None) -> tuple[float | None, str | None]:
    return (None, None) if window is None else (window.used_pct, window.resets_at)


def _window_from_columns(
    used_pct: float | None, resets_at: str | None
) -> UsageWindow | None:
    return None if used_pct is None else UsageWindow(used_pct, resets_at)


@dataclass(frozen=True, slots=True)
class CurrentTask:
    id: str
    title: str | None
    claimed_since: str  # A claimed task's updated_at is its claim time.


@dataclass(frozen=True, slots=True)
class ParticipantOverview:
    """A participant with its live task and its latest usage report."""

    participant: Participant
    current_task: CurrentTask | None
    usage: UsageReport | None
    usage_reported_at: str | None


def _overview_from_row(row: sqlite3.Row | tuple) -> ParticipantOverview:
    (name, last_seen, channel, task_id, task_title, claimed_since,
     session_pct, session_resets, weekly_pct, weekly_resets, reported_at) = tuple(row)
    current_task = (
        None if claimed_since is None else CurrentTask(task_id, task_title, claimed_since)
    )
    usage = None
    if reported_at is not None:
        usage = UsageReport(
            session=_window_from_columns(session_pct, session_resets),
            weekly=_window_from_columns(weekly_pct, weekly_resets),
        )
    return ParticipantOverview(
        participant=Participant(name, last_seen, channel, task_id),
        current_task=current_task,
        usage=usage,
        usage_reported_at=reported_at,
    )


class ParticipantStore:
    """Repository for participant presence; callers own the transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def touch(self, name: str) -> None:
        """Record activity without changing what the participant works on."""
        self._conn.execute(
            "INSERT INTO participants(name, last_seen) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET last_seen = excluded.last_seen",
            (name, _now_iso()),
        )

    def start_task(self, name: str, *, channel: str, task_id: str) -> None:
        """Make a just-claimed task the participant's current task."""
        self._conn.execute(
            "INSERT INTO participants(name, last_seen, current_channel, current_task_id) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
            "last_seen = excluded.last_seen, current_channel = excluded.current_channel, "
            "current_task_id = excluded.current_task_id",
            (name, _now_iso(), channel, task_id),
        )

    def report_usage(self, name: str, report: UsageReport) -> str:
        """Replace the participant's usage with this report; return its timestamp."""
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO participants(name, last_seen, usage_session_pct, "
            "usage_session_resets_at, usage_weekly_pct, usage_weekly_resets_at, "
            "usage_reported_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET last_seen = excluded.last_seen, "
            "usage_session_pct = excluded.usage_session_pct, "
            "usage_session_resets_at = excluded.usage_session_resets_at, "
            "usage_weekly_pct = excluded.usage_weekly_pct, "
            "usage_weekly_resets_at = excluded.usage_weekly_resets_at, "
            "usage_reported_at = excluded.usage_reported_at",
            (
                name,
                now,
                *_window_columns(report.session),
                *_window_columns(report.weekly),
                now,
            ),
        )
        return now

    def reconcile_current_tasks(self) -> None:
        """Repoint every current task that lost its live lease to the newest one left.

        This one pass covers complete, fail, lease expiry and channel clear.
        """
        self._conn.execute(
            "UPDATE participants SET "
            f"current_task_id = (SELECT id {_LIVE_LEASE} ORDER BY seq DESC LIMIT 1), "
            f"current_channel = COALESCE((SELECT channel {_LIVE_LEASE} "
            "ORDER BY seq DESC LIMIT 1), current_channel) "
            "WHERE current_task_id IS NOT NULL AND NOT EXISTS (SELECT 1 "
            f"{_LIVE_LEASE} AND tasks.id = participants.current_task_id)",
            {"now": _now_iso()},
        )

    def prune_idle(self, *, last_seen_before: str) -> int:
        """Forget participants that hold no task and were not seen since the cutoff."""
        return self._conn.execute(
            "DELETE FROM participants WHERE current_task_id IS NULL AND last_seen < ?",
            (last_seen_before,),
        ).rowcount

    def list_recent(self, *, limit: int) -> list[Participant]:
        """The `limit` participants seen most recently, newest first."""
        rows = self._conn.execute(
            "SELECT name, last_seen, current_channel, current_task_id "
            "FROM participants ORDER BY last_seen DESC, name LIMIT ?",
            (limit,),
        ).fetchall()
        return [Participant(*tuple(row)) for row in rows]

    def list_overview(self, *, limit: int, now: datetime) -> list[ParticipantOverview]:
        """Like list_recent, joined in one query to the task each one holds live."""
        rows = self._conn.execute(
            "SELECT p.name, p.last_seen, p.current_channel, p.current_task_id, "
            "t.title, t.updated_at, p.usage_session_pct, p.usage_session_resets_at, "
            "p.usage_weekly_pct, p.usage_weekly_resets_at, p.usage_reported_at "
            "FROM participants p LEFT JOIN tasks t ON t.id = p.current_task_id "
            "AND t.lease_owner = p.name AND t.status = 'claimed' "
            "AND t.lease_expires_at > ? "
            "ORDER BY p.last_seen DESC, p.name LIMIT ?",
            (_timestamp(now), limit),
        ).fetchall()
        return [_overview_from_row(row) for row in rows]


def participant_to_dict(participant: Participant) -> dict:
    return asdict(participant)


def overview_to_dict(overview: ParticipantOverview, now: datetime) -> dict:
    """Serialize for the dashboard; presence is computed against `now`."""
    participant = overview.participant
    return {
        "name": participant.name,
        "last_seen": participant.last_seen,
        "presence": presence(participant.last_seen, now),
        "current_channel": participant.current_channel,
        "current_task": _optional_asdict(overview.current_task),
        "usage": _usage_to_dict(overview.usage, overview.usage_reported_at),
    }


def _usage_to_dict(usage: UsageReport | None, reported_at: str | None) -> dict | None:
    if usage is None:
        return None
    return {
        "session": _optional_asdict(usage.session),
        "weekly": _optional_asdict(usage.weekly),
        "reported_at": reported_at,
    }


def _optional_asdict(value: Any) -> dict | None:
    return None if value is None else asdict(value)


__all__ = [
    "CurrentTask",
    "IDLE_WITHIN",
    "ONLINE_WITHIN",
    "Participant",
    "ParticipantOverview",
    "ParticipantStore",
    "UsageReport",
    "UsageWindow",
    "ensure_participants_schema",
    "overview_to_dict",
    "parse_usage_report",
    "participant_to_dict",
    "presence",
]
