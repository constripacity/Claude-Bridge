"""Tests for message retention / TTL (`--retention-days`)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


def _age_message(msg_id: str, days_old: float) -> None:
    """Backdate a message's stored timestamp by `days_old` days."""
    old = (datetime.now(timezone.utc) - timedelta(days=days_old))
    iso = old.isoformat().replace("+00:00", "Z")
    bridge.db().execute("UPDATE messages SET timestamp = ? WHERE id = ?", (iso, msg_id))


# ── Cutoff helper ───────────────────────────────────────────────────────────


def test_retention_cutoff_iso_shape_and_value():
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = bridge._retention_cutoff_iso(7, now=now)
    # Same `...Z` UTC shape as stored timestamps so SQL string compare == time compare.
    assert cutoff == "2026-05-25T12:00:00Z"


# ── Disabled by default ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retention_disabled_is_noop(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 0)
    mid, _, _ = await bridge.insert_message("demo:c", "a", "keep me")
    _age_message(mid, 999)  # ancient, but retention is off

    deleted = await bridge.retention_sweep_once()

    assert deleted == 0
    assert bridge.db().execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 1


# ── Deletes old, keeps new ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retention_deletes_old_keeps_new(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 7)

    old_id, _, _ = await bridge.insert_message("demo:c", "a", "old")
    _age_message(old_id, 30)  # older than the 7-day window
    await bridge.insert_message("demo:c", "a", "fresh")  # now()

    deleted = await bridge.retention_sweep_once()

    assert deleted == 1
    rows = bridge.db().execute("SELECT content FROM messages ORDER BY seq").fetchall()
    assert [r["content"] for r in rows] == ["fresh"]


# ── delete_messages_before is exclusive on the cutoff ───────────────────────


@pytest.mark.asyncio
async def test_delete_messages_before_counts(fresh_db):
    a, _, _ = await bridge.insert_message("demo:c", "x", "a")
    b, _, _ = await bridge.insert_message("demo:c", "x", "b")
    _age_message(a, 10)
    _age_message(b, 10)
    await bridge.insert_message("demo:c", "x", "c")  # recent

    cutoff = bridge._retention_cutoff_iso(5)
    deleted = await bridge.delete_messages_before(cutoff)

    assert deleted == 2
    assert bridge.db().execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 1


# ── Lifespan runs the startup sweep and tears the loop down cleanly ─────────


def test_lifespan_startup_sweep_and_clean_shutdown(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "RETENTION_DAYS", 7)
    monkeypatch.setattr(bridge, "RETENTION_SWEEP_SECONDS", 3600)
    # Seed an ancient message directly (no event loop needed here).
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    bridge.db().execute(
        "INSERT INTO messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "demo:c", "a", "old", old),
    )

    # Entering the TestClient context runs the app lifespan: immediate startup
    # sweep + the periodic loop. Exiting must cancel the loop without hanging
    # (the pytest-timeout backstop would catch a regression here).
    with TestClient(bridge.app) as client:
        assert client.get("/status").status_code == 200

    assert bridge.db().execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 0

