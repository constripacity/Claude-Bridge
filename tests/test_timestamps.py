"""The shared ISO-8601 timestamp parser."""

from __future__ import annotations

from datetime import timedelta, timezone

from claude_bridge.timestamps import parse_timestamp


def test_z_suffix_parses_as_utc():
    assert parse_timestamp("2026-01-01T00:00:00.000000Z").tzinfo == timezone.utc


def test_an_explicit_offset_is_kept():
    parsed = parse_timestamp("2026-01-01T02:00:00+02:00")
    assert parsed.utcoffset() == timedelta(hours=2)


def test_no_offset_gives_a_naive_value():
    assert parse_timestamp("2026-01-01T00:00:00").tzinfo is None
