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
from .timestamps import as_utc, parse_timestamp, utc_timestamp
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
# Statuses of a task that is not finished yet (completed, failed and dead are).
_OPEN_STATUSES = "('pending', 'claimed')"


def _now_iso() -> str:
    return utc_timestamp(datetime.now(timezone.utc))


ONLINE_WITHIN = timedelta(minutes=10)
IDLE_WITHIN = timedelta(hours=24)
# A usage report older than this is stale; clients read the cutoff as usage.stale_at.
USAGE_STALE_AFTER = timedelta(minutes=15)


def presence(last_seen: str, now: datetime, *, has_open_work: bool = False) -> str:
    """'online', 'idle' or 'offline' by the time since the participant was seen.

    Open work keeps it online, but only within IDLE_WITHIN, so a crashed session ends offline.
    """
    age = now - parse_timestamp(last_seen)
    if age <= ONLINE_WITHIN or (has_open_work and age <= IDLE_WITHIN):
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


# Claude Code drops a window once it resets, and a weekly window resets within 7 days.
RESETS_AT_MAX_PAST = timedelta(days=1)
RESETS_AT_MAX_FUTURE = timedelta(days=8)


def parse_usage_report(body: Any, now: datetime | None = None) -> UsageReport:
    """Validate a `{session: {...}, weekly: {...}}` usage body; `now` defaults to server time."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(body, dict):
        raise BridgeValidationError("body", "invalid_type", "must be an object")
    unknown = sorted(set(body) - {"session", "weekly"})
    if unknown:
        raise BridgeValidationError(unknown[0], "unknown_field", "is not a usage window")
    return UsageReport(
        session=_parse_usage_window(body.get("session"), "session", now),
        weekly=_parse_usage_window(body.get("weekly"), "weekly", now),
    )


def _parse_usage_window(value: Any, field: str, now: datetime) -> UsageWindow | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BridgeValidationError(field, "invalid_type", "must be an object")
    unknown = sorted(set(value) - {"used_pct", "resets_at"})
    if unknown:
        raise BridgeValidationError(
            f"{field}.{unknown[0]}", "unknown_field", "is not a usage window field"
        )
    return UsageWindow(
        used_pct=_parse_used_pct(value.get("used_pct"), f"{field}.used_pct"),
        resets_at=_parse_resets_at(value.get("resets_at"), f"{field}.resets_at", now),
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_used_pct(value: Any, field: str) -> float:
    if not _is_number(value) or not math.isfinite(value):
        raise BridgeValidationError(field, "invalid_type", "must be a finite number")
    if not 0 <= value <= 100:
        raise BridgeValidationError(field, "out_of_range", "must be within 0..100")
    return float(value)


def _parse_resets_at(value: Any, field: str, now: datetime) -> str | None:
    """Normalize unix seconds or an ISO-8601 string with an offset near `now`."""
    if value is None:
        return None
    if not (_is_number(value) or isinstance(value, str)):
        raise BridgeValidationError(
            field, "invalid_type", "must be unix seconds or an ISO-8601 string"
        )
    try:
        instant = _instant_from(value)
    except (ValueError, OverflowError, OSError) as exc:
        raise _invalid_time(field) from exc
    if instant.tzinfo is None:
        raise BridgeValidationError(field, "invalid", "must include a UTC offset")
    try:
        utc_instant = as_utc(instant)
    except OverflowError as exc:  # The shift to UTC overflows near datetime.min/max.
        raise _invalid_time(field) from exc
    _require_plausible_reset(utc_instant, field, now)
    return utc_timestamp(utc_instant)


def _is_plausible_reset(instant: datetime, now: datetime) -> bool:
    return now - RESETS_AT_MAX_PAST <= instant <= now + RESETS_AT_MAX_FUTURE


def _require_plausible_reset(instant: datetime, field: str, now: datetime) -> None:
    if not _is_plausible_reset(instant, now):
        message = (
            f"must be within {RESETS_AT_MAX_PAST.days} day before and "
            f"{RESETS_AT_MAX_FUTURE.days} days after server time"
        )
        raise BridgeValidationError(field, "out_of_range", message)


def _invalid_time(field: str) -> BridgeValidationError:
    return BridgeValidationError(field, "invalid", "is not a valid time")


def _instant_from(value: float | str) -> datetime:
    if isinstance(value, str):
        return parse_timestamp(value)
    return datetime.fromtimestamp(value, timezone.utc)


def _window_columns(window: UsageWindow | None) -> tuple[float | None, str | None]:
    return (None, None) if window is None else (window.used_pct, window.resets_at)


def _window_from_columns(
    used_pct: float | None, resets_at: str | None, reported_at: datetime
) -> UsageWindow | None:
    if used_pct is None:
        return None
    return UsageWindow(used_pct, _stored_reset_or_none(resets_at, reported_at))


def _stored_reset_or_none(resets_at: str | None, reported_at: datetime) -> str | None:
    # Rows written before the plausibility check can hold a reset like 1970.
    if resets_at is None:
        return None
    try:
        plausible = _is_plausible_reset(parse_timestamp(resets_at), reported_at)
    except (ValueError, TypeError):  # Unparsable or offset-less legacy text.
        return None
    return resets_at if plausible else None


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
    open_tasks: int  # Tasks it enqueued that are not finished yet.
    held_tasks: int  # Tasks it holds a live lease on.

    @property
    def has_open_work(self) -> bool:
        return self.open_tasks > 0 or self.held_tasks > 0


def _overview_from_row(row: sqlite3.Row) -> ParticipantOverview:
    task_id = row["current_task_id"]
    current_task = None
    if row["claimed_since"] is not None:
        current_task = CurrentTask(task_id, row["task_title"], row["claimed_since"])
    usage = None
    if row["usage_reported_at"] is not None:
        reported_at = parse_timestamp(row["usage_reported_at"])
        usage = UsageReport(
            session=_window_from_columns(
                row["usage_session_pct"], row["usage_session_resets_at"], reported_at
            ),
            weekly=_window_from_columns(
                row["usage_weekly_pct"], row["usage_weekly_resets_at"], reported_at
            ),
        )
    return ParticipantOverview(
        participant=Participant(
            row["name"], row["last_seen"], row["current_channel"], task_id
        ),
        current_task=current_task,
        usage=usage,
        usage_reported_at=row["usage_reported_at"],
        open_tasks=row["open_tasks"],
        held_tasks=row["held_tasks"],
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
        """Forget participants with no task held or enqueued, not seen since the cutoff.

        A row with open enqueued tasks stays (offline after a day) so stuck work keeps an owner.
        """
        return self._conn.execute(
            "DELETE FROM participants WHERE current_task_id IS NULL AND last_seen < ? "
            "AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.enqueued_by = participants.name "
            f"AND tasks.status IN {_OPEN_STATUSES})",
            (last_seen_before,),
        ).rowcount

    def list_overview(self, *, limit: int, now: datetime) -> list[ParticipantOverview]:
        """The `limit` participants seen most recently, newest first, with task and usage."""
        cursor = self._conn.cursor()
        cursor.row_factory = sqlite3.Row  # Named columns, whatever the connection uses.
        rows = cursor.execute(
            "SELECT p.name, p.last_seen, p.current_channel, p.current_task_id, "
            "t.title AS task_title, t.updated_at AS claimed_since, "
            "p.usage_session_pct, p.usage_session_resets_at, "
            "p.usage_weekly_pct, p.usage_weekly_resets_at, p.usage_reported_at, "
            "COALESCE(enqueued.n, 0) AS open_tasks, COALESCE(held.n, 0) AS held_tasks "
            "FROM participants p LEFT JOIN tasks t ON t.id = p.current_task_id "
            "AND t.lease_owner = p.name AND t.status = 'claimed' "
            "AND t.lease_expires_at > :now "
            "LEFT JOIN (SELECT enqueued_by AS owner, COUNT(*) AS n FROM tasks "
            f"WHERE status IN {_OPEN_STATUSES} GROUP BY enqueued_by) enqueued "
            "ON enqueued.owner = p.name "
            "LEFT JOIN (SELECT lease_owner AS owner, COUNT(*) AS n FROM tasks "
            "WHERE status = 'claimed' AND lease_expires_at > :now GROUP BY lease_owner) held "
            "ON held.owner = p.name "
            "ORDER BY p.last_seen DESC, p.name LIMIT :limit",
            {"now": utc_timestamp(now), "limit": limit},
        ).fetchall()
        return [_overview_from_row(row) for row in rows]


def overview_to_dict(overview: ParticipantOverview, now: datetime) -> dict:
    """Serialize for the dashboard and bridge_participants; presence is against `now`."""
    participant = overview.participant
    return {
        "name": participant.name,
        "last_seen": participant.last_seen,
        "presence": presence(
            participant.last_seen, now, has_open_work=overview.has_open_work
        ),
        "current_channel": participant.current_channel,
        "current_task": _optional_asdict(overview.current_task),
        "open_tasks": overview.open_tasks,
        "usage": _usage_to_dict(overview.usage, overview.usage_reported_at),
    }


def _usage_to_dict(usage: UsageReport | None, reported_at: str | None) -> dict | None:
    if usage is None or reported_at is None:
        return None
    return {
        "session": _optional_asdict(usage.session),
        "weekly": _optional_asdict(usage.weekly),
        "reported_at": reported_at,
        "stale_at": utc_timestamp(parse_timestamp(reported_at) + USAGE_STALE_AFTER),
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
    "USAGE_STALE_AFTER",
    "UsageReport",
    "UsageWindow",
    "ensure_participants_schema",
    "overview_to_dict",
    "parse_usage_report",
    "presence",
]
