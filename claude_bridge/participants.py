"""Who is on the bridge: when each participant was last seen and what it holds.

Every client shares one bearer token, so a name is self-declared: this is a
presence hint for operators, not an identity or an access-control record.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
        if isinstance(value, str):
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            instant = datetime.fromtimestamp(value, timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise BridgeValidationError(field, "invalid", "is not a valid time") from exc
    if instant.tzinfo is None:
        raise BridgeValidationError(field, "invalid", "must include a UTC offset")
    return _timestamp(instant)


def _window_columns(window: UsageWindow | None) -> tuple[float | None, str | None]:
    return (None, None) if window is None else (window.used_pct, window.resets_at)


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


def participant_to_dict(participant: Participant) -> dict:
    return asdict(participant)


__all__ = [
    "Participant",
    "ParticipantStore",
    "UsageReport",
    "UsageWindow",
    "ensure_participants_schema",
    "parse_usage_report",
    "participant_to_dict",
]
