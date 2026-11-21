"""In-place, additive schema upgrades shared by the SQLite stores."""

from __future__ import annotations

import sqlite3


def add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    """Add each column (name -> DDL) that an older database does not have yet."""
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


__all__ = ["add_missing_columns"]
