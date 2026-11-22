"""Fixed-width UTC timestamps shared by the stores, so text order is time order."""

from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def utc_timestamp(value: datetime) -> str:
    """Microsecond ISO-8601 in UTC with a Z suffix."""
    return as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """ISO-8601, also with a Z suffix; the offset is kept, and none gives a naive value."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
