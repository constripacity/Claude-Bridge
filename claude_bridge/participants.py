"""Who is on the bridge: when each participant was last seen and what it holds.

Every client shares one bearer token, so a name is self-declared: this is a
presence hint for operators, not an identity or an access-control record.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def ensure_participants_schema(conn: sqlite3.Connection) -> None:
    """Create the participants table idempotently."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
            name            TEXT PRIMARY KEY,
            last_seen       TEXT NOT NULL,
            current_channel TEXT,
            current_task_id TEXT
        )
        """
    )


def _now_iso() -> str:
    # Same fixed-width format as task timestamps, so text order is time order.
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    return stamp.replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Participant:
    name: str
    last_seen: str
    current_channel: str | None  # Channel of the current task (or of the last one).
    current_task_id: str | None  # Newest task it holds a live lease on, if any.


class ParticipantStore:
    """Repository for participant presence; callers own the transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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

    def reconcile_current_tasks(self) -> None:
        """Repoint every current task that lost its live lease to the newest one left.

        This one pass covers complete, fail, lease expiry and channel clear.
        """
        live_lease = (
            "FROM tasks WHERE tasks.lease_owner = participants.name "
            "AND tasks.status = 'claimed' AND tasks.lease_expires_at > :now "
        )
        self._conn.execute(
            "UPDATE participants SET "
            f"current_task_id = (SELECT id {live_lease} ORDER BY seq DESC LIMIT 1), "
            f"current_channel = COALESCE((SELECT channel {live_lease} "
            "ORDER BY seq DESC LIMIT 1), current_channel) "
            "WHERE current_task_id IS NOT NULL AND NOT EXISTS (SELECT 1 "
            f"{live_lease} AND tasks.id = participants.current_task_id)",
            {"now": _now_iso()},
        )

    def prune_idle(self, *, last_seen_before: str) -> int:
        """Forget participants that hold no task and were not seen since the cutoff."""
        return self._conn.execute(
            "DELETE FROM participants WHERE current_task_id IS NULL AND last_seen < ?",
            (last_seen_before,),
        ).rowcount

    def list_all(self) -> list[Participant]:
        rows = self._conn.execute(
            "SELECT name, last_seen, current_channel, current_task_id "
            "FROM participants ORDER BY last_seen DESC, name"
        ).fetchall()
        return [Participant(*tuple(row)) for row in rows]


def participant_to_dict(participant: Participant) -> dict:
    return asdict(participant)


__all__ = [
    "Participant",
    "ParticipantStore",
    "ensure_participants_schema",
    "participant_to_dict",
]
