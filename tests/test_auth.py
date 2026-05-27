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


def test_dashboard_root_is_public_even_with_auth(client, auth_on):
    """Static dashboard files must load WITHOUT auth so the JS can prompt
    the user for a token — otherwise the bootstrap is impossible."""
    import os
    if not os.path.isdir(bridge.WEB_DIR):
        pytest.skip("web/ directory not present in this build")
    r = client.get("/")
    assert r.status_code == 200
    assert "Claude Bridge" in r.text
    # And the JSX bundle is also public
    r = client.get("/shared.jsx")
    assert r.status_code == 200


def test_malformed_authorization_header(client, auth_on):
    """Headers that aren't 'Bearer <token>' shape should 401, not crash."""
    for bad in ("", f"{TOKEN}", f"Token {TOKEN}", f"Bearer  {TOKEN}", "Bearer", "Bearer "):
        r = client.get("/api/state", headers={"Authorization": bad})
        assert r.status_code == 401, bad


def test_bearer_scheme_case_insensitive(client, auth_on):
    """RFC 7235: auth-scheme is case-insensitive. `bearer` and `BEARER` must
    accept the token; only the credential half is byte-compared."""
    for scheme in ("bearer", "Bearer", "BEARER", "BeArEr"):
        r = client.get("/api/state", headers={"Authorization": f"{scheme} {TOKEN}"})
        assert r.status_code == 200, scheme


def test_constant_time_compare_used():
    """The middleware should use hmac.compare_digest, not ==.

    Indirect check: source file references compare_digest (smoke-test for
    timing-attack hygiene)."""
    from claude_bridge import auth as auth_mod
    src = auth_mod.__file__
    with open(src, encoding="utf-8") as f:
        assert "hmac.compare_digest" in f.read()


# ── /sse and /messages/ are protected ──────────────────────────────────────

def test_sse_requires_token(client, auth_on):
    """GET /sse must reject unauthenticated requests when auth is on.

    We only assert the rejection path here — the happy path opens a long-
    lived stream that TestClient (sync) can't easily tear down. The
    successful-auth case is covered by the empirical claude-mcp-add
    verification documented in the v0.7.0 release notes."""
    assert client.get("/sse").status_code == 401


def test_messages_post_requires_token(client, auth_on):
    """POST /messages/<session> must reject unauthenticated requests."""
    assert client.post("/messages/?session_id=x", json={}).status_code == 401


# ── Request size limit ──────────────────────────────────────────────────────

def test_oversized_post_rejected_before_handler(client):
    """Content-Length above MAX_REQUEST_BYTES is rejected with 413."""
    huge_content = "x" * (bridge.MAX_REQUEST_BYTES + 1024)
    r = client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": huge_content,
    })
    assert r.status_code == 413
    assert "too large" in r.json()["error"]


def test_oversized_content_rejected_after_decode(client):
    """A small JSON wrapper with a long content field still trips the
    per-message cap inside the handler."""
    # Just over MAX_MESSAGE_BYTES, but well under MAX_REQUEST_BYTES so the
    # middleware doesn't catch it. Confirms the defense-in-depth handler check.
    content = "x" * (bridge.MAX_MESSAGE_BYTES + 1)
    r = client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": content,
    })
    assert r.status_code == 413
    assert "exceeds" in r.json()["error"]


def test_normal_send_unaffected(client):
    """Reasonable message size still works."""
    r = client.post("/api/send", json={
        "channel": "c", "sender": "a", "content": "hello"
    })
    assert r.status_code == 200


# ── CORS: localhost-only by default ────────────────────────────────────────

def test_cors_default_allows_localhost(client):
    """Default CORS config accepts requests claiming a localhost origin."""
    r = client.options("/api/state", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_default_rejects_external_origin(client):
    """A drive-by site origin is NOT echoed back, so the browser blocks it."""
    r = client.options("/api/state", headers={
        "Origin": "https://evil.example.com",
        "Access-Control-Request-Method": "GET",
    })
    # Either no allow-origin header at all, or one that doesn't match evil.*.
    # In neither case can the browser read the response.
    allowed = r.headers.get("access-control-allow-origin")
    assert allowed != "https://evil.example.com"
    assert allowed != "*"
