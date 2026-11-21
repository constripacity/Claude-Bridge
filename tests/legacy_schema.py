"""The v1.3.0 ``tasks`` table, used to prove in-place migrations."""

from __future__ import annotations

import sqlite3

V130_TASKS_DDL = """
CREATE TABLE tasks (
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
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    CHECK (
        (status = 'claimed' AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status != 'claimed' AND lease_owner IS NULL
            AND lease_token IS NULL AND lease_expires_at IS NULL)
    )
)
"""


def create_v130_database(path: str, *, pending_task_id: str) -> None:
    """Write a v1.3.0 database holding one pending task on channel ``old``."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(V130_TASKS_DDL)
        conn.execute(
            "INSERT INTO tasks (id, channel, payload, status, available_at, "
            "created_at, updated_at) VALUES (?, 'old', 'legacy', 'pending', "
            "'2000-01-01T00:00:00.000000Z', '2000-01-01T00:00:00.000000Z', "
            "'2000-01-01T00:00:00.000000Z')",
            (pending_task_id,),
        )
        conn.commit()
    finally:
        conn.close()
