"""Tests for the optional audit log (`--audit-log`, `GET /api/audit`)."""

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


@pytest.fixture
def client(fresh_db):
    return TestClient(bridge.app)


def _audit_rows(event: str | None = None):
    sql = "SELECT event, channel, detail, ip FROM audit"
    params: tuple = ()
    if event is not None:
        sql += " WHERE event = ?"
        params = (event,)
    sql += " ORDER BY id"
    return bridge.db().execute(sql, params).fetchall()


# ── Disabled by default ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_disabled_records_nothing(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUDIT_ENABLED", False)
    await bridge.insert_message("demo:c", "a", "hi")  # would be a channel_create
    await bridge.clear_channel("demo:c")              # would be a channel_clear
    await bridge.record_audit("manual", detail="x")   # direct call, still no-op

    assert _audit_rows() == []


# ── Channel create + clear ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_channel_create_then_clear(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUDIT_ENABLED", True)

    await bridge.insert_message("demo:c", "windows", "first")
    # Second message to an existing channel must NOT log another create.
    await bridge.insert_message("demo:c", "windows", "second")

    creates = _audit_rows("channel_create")
    assert len(creates) == 1
    assert creates[0]["channel"] == "demo:c"
    assert "windows" in creates[0]["detail"]

    await bridge.clear_channel("demo:c")
    clears = _audit_rows("channel_clear")
    assert len(clears) == 1
    assert clears[0]["channel"] == "demo:c"
    assert "2 message" in clears[0]["detail"]


# ── Auth failure is audited via the middleware hook ─────────────────────────


def test_audit_records_auth_failure(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUDIT_ENABLED", True)
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret")

    # Unauthenticated protected request → 401 → audited.
    assert client.get("/api/state").status_code == 401

    rows = _audit_rows("auth_failure")
    assert len(rows) == 1
    assert rows[0]["detail"] == "/api/state"

    # And it's readable through the API once we present the token.
    r = client.get("/api/audit", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert any(e["event"] == "auth_failure" and e["detail"] == "/api/state"
               for e in body["events"])


# ── Oversize reject is audited via the middleware hook ──────────────────────


def test_audit_records_oversize_reject(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUDIT_ENABLED", True)
    huge = "x" * (bridge.MAX_REQUEST_BYTES + 1024)

    r = client.post("/api/send", json={"channel": "c", "sender": "a", "content": huge})
    assert r.status_code == 413

    rows = _audit_rows("oversize_reject")
    assert len(rows) == 1
    assert rows[0]["detail"] == "/api/send"


# ── /api/audit when disabled, and its auth gate ─────────────────────────────


def test_api_audit_reports_disabled(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUDIT_ENABLED", False)
    r = client.get("/api/audit")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "events": []}


def test_api_audit_protected_when_auth_on(client, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", "s3cret")
    assert client.get("/api/audit").status_code == 401
    assert client.get(
        "/api/audit", headers={"Authorization": "Bearer s3cret"}
    ).status_code == 200
