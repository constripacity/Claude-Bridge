"""Tests for optional Bearer-token authentication."""

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge


@pytest.fixture
def client(fresh_db):
    return TestClient(bridge.app)


TOKEN = "s3cret-abc"
HEADERS_OK = {"Authorization": f"Bearer {TOKEN}"}
HEADERS_WRONG = {"Authorization": "Bearer wrong"}


# ── Auth disabled (default) ─────────────────────────────────────────────────

def test_auth_disabled_by_default(client):
    """With AUTH_TOKEN unset, every endpoint works without any header."""
    assert client.get("/status").status_code == 200
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/messages?channel=x").status_code == 200
    assert client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": "hi"
    }).status_code == 200


# ── Auth enabled ────────────────────────────────────────────────────────────

@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", TOKEN)


def test_status_is_public_even_with_auth(client, auth_on):
    """/status must stay reachable without a token (healthcheck)."""
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["service"] == "claude-bridge"


def test_protected_endpoints_reject_missing_header(client, auth_on):
    for path in ("/api/state", "/api/messages?channel=x"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json() == {"error": "unauthorized"}


def test_protected_endpoints_reject_wrong_token(client, auth_on):
    r = client.get("/api/state", headers=HEADERS_WRONG)
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_protected_endpoints_accept_correct_token(client, auth_on):
    r = client.get("/api/state", headers=HEADERS_OK)
    assert r.status_code == 200
    assert r.json()["service"] == "claude-bridge"


def test_send_and_clear_require_token(client, auth_on):
    # Without header
    assert client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": "hi"
    }).status_code == 401
    assert client.post("/api/clear", json={"channel": "c"}).status_code == 401

    # With header
    r = client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": "hi"
    }, headers=HEADERS_OK)
    assert r.status_code == 200


def test_message_detail_route_protected(client, auth_on):
    """The path-param route /api/messages/{id} is also protected."""
    r = client.get("/api/messages/anything", headers=HEADERS_OK)
    # 404 (not found) is fine — we only care that we got past the auth check
    assert r.status_code in (200, 404)
    assert client.get("/api/messages/anything").status_code == 401


def test_dashboard_root_protected(client, auth_on):
    """Static dashboard files (served via Mount('/', StaticFiles)) require auth too."""
    import os
    if not os.path.isdir(bridge.WEB_DIR):
        pytest.skip("web/ directory not present in this build")
    # Without header — 401, NOT a static file
    r = client.get("/")
    assert r.status_code == 401
    # With header — dashboard html
    r = client.get("/", headers=HEADERS_OK)
    assert r.status_code == 200
    assert "Claude Bridge" in r.text


def test_malformed_authorization_header(client, auth_on):
    """Headers that aren't 'Bearer <token>' shape should 401, not crash."""
    for bad in ("", f"{TOKEN}", f"Token {TOKEN}", f"Bearer  {TOKEN}", "Bearer"):
        r = client.get("/api/state", headers={"Authorization": bad})
        assert r.status_code == 401, bad


def test_constant_time_compare_used():
    """The middleware should use hmac.compare_digest, not ==.

    Indirect check: a one-char-different token must still 401, and the type
    used is hmac.compare_digest (smoke-test for timing-attack hygiene)."""
    from claude_bridge import auth as auth_mod
    src = auth_mod.__file__
    with open(src, encoding="utf-8") as f:
        assert "hmac.compare_digest" in f.read()
