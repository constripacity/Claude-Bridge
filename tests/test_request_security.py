"""Focused tests for request-boundary security middleware."""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from claude_bridge.auth import RequestPolicyMiddleware, RequestSizeLimitMiddleware


async def _echo_body(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse({"body": body.decode("utf-8")})


def _body_app() -> Starlette:
    return Starlette(routes=[Route("/body", _echo_body, methods=["POST"])])


async def _asgi_request(
    app,
    chunks: Iterable[bytes],
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict]:
    """Call an ASGI app with deliberately controlled request framing."""
    bodies = list(chunks)
    incoming = [
        {
            "type": "http.request",
            "body": body,
            "more_body": index < len(bodies) - 1,
        }
        for index, body in enumerate(bodies)
    ]
    if not incoming:
        incoming.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        if incoming:
            return incoming.pop(0)
        return {"type": "http.disconnect"}

    outgoing = []

    async def send(message):
        outgoing.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/body",
        "raw_path": b"/body",
        "query_string": b"",
        "root_path": "",
        "headers": headers or [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    status = next(
        message["status"]
        for message in outgoing
        if message["type"] == "http.response.start"
    )
    raw_body = b"".join(
        message.get("body", b"")
        for message in outgoing
        if message["type"] == "http.response.body"
    )
    return status, json.loads(raw_body)


@pytest.mark.asyncio
async def test_streaming_limit_rejects_chunked_body_without_content_length():
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=5)

    status, body = await _asgi_request(app, [b"abc", b"def"])

    assert status == 413
    assert body == {"error": "request body too large"}


@pytest.mark.asyncio
async def test_streaming_limit_rejects_body_larger_than_claimed_length():
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=5)

    status, body = await _asgi_request(
        app,
        [b"abc", b"def"],
        headers=[(b"host", b"testserver"), (b"content-length", b"3")],
    )

    assert status == 413
    assert body == {"error": "request body too large"}


@pytest.mark.asyncio
async def test_streaming_limit_replays_valid_chunked_body():
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=6)

    status, body = await _asgi_request(app, [b"abc", b"def"])

    assert status == 200
    assert body == {"body": "abcdef"}


@pytest.mark.asyncio
async def test_streaming_limit_rejects_content_length_mismatch_under_cap():
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=10)
    status, body = await _asgi_request(
        app,
        [b"abcd"],
        headers=[(b"host", b"testserver"), (b"content-length", b"3")],
    )
    assert status == 400
    assert body == {"error": "content-length mismatch"}


@pytest.mark.asyncio
async def test_streaming_limit_rejects_transfer_encoding_with_content_length():
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=10)
    status, body = await _asgi_request(
        app,
        [b"abc"],
        headers=[
            (b"host", b"testserver"),
            (b"content-length", b"3"),
            (b"transfer-encoding", b"chunked"),
        ],
    )
    assert status == 400
    assert body == {"error": "ambiguous request framing"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "length_headers",
    [
        [(b"content-length", b"-1")],
        [(b"content-length", b"+1")],
        [(b"content-length", b"1"), (b"content-length", b"1")],
    ],
)
async def test_invalid_or_duplicate_content_length_is_rejected(length_headers):
    app = RequestSizeLimitMiddleware(_body_app(), max_bytes=5)
    headers = [(b"host", b"testserver"), *length_headers]

    status, body = await _asgi_request(app, [b"a"], headers=headers)

    assert status == 400
    assert body == {"error": "invalid content-length"}


async def _json_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"received": await request.json()})


async def _read_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _policy_client(**overrides) -> TestClient:
    app = Starlette(
        routes=[
            Route("/api/send", _json_endpoint, methods=["POST"]),
            Route("/api/state", _read_endpoint, methods=["GET"]),
        ]
    )
    options = {
        "allowed_hosts": (
            "testserver",
            "localhost",
            "127.0.0.1",
            "::1",
            "*.bridge.test",
        ),
        "allowed_origins": (),
        "json_paths": ("/api/send",),
    }
    options.update(overrides)
    return TestClient(RequestPolicyMiddleware(app, **options))


def test_policy_rejects_cross_port_localhost_mutations_by_default():
    with _policy_client() as client:
        response = client.post(
            "/api/send",
            json={"content": "hello"},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 403


def test_policy_allows_explicit_localhost_origin():
    with _policy_client(allowed_origins=("http://localhost:3000",)) as client:
        response = client.post(
            "/api/send",
            json={"content": "hello"},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 200


def test_policy_preserves_non_browser_clients_without_origin():
    with _policy_client() as client:
        response = client.post("/api/send", json={"content": "hello"})

    assert response.status_code == 200


def test_policy_rejects_cross_origin_mutation_but_not_read():
    with _policy_client() as client:
        mutation = client.post(
            "/api/send",
            json={"content": "hello"},
            headers={"Origin": "https://evil.example"},
        )
        read = client.get(
            "/api/state",
            headers={"Origin": "https://evil.example"},
        )

    assert mutation.status_code == 403
    assert mutation.json() == {"error": "origin not allowed"}
    assert read.status_code == 200


def test_policy_accepts_same_origin_and_configured_external_origin():
    with _policy_client(allowed_origins=("https://dashboard.example",)) as client:
        same_origin = client.post(
            "/api/send",
            json={"content": "same"},
            headers={"Host": "node.bridge.test", "Origin": "http://node.bridge.test"},
        )
        configured = client.post(
            "/api/send",
            json={"content": "configured"},
            headers={"Origin": "https://dashboard.example"},
        )

    assert same_origin.status_code == 200
    assert configured.status_code == 200


def test_policy_rejects_untrusted_host():
    with _policy_client() as client:
        response = client.get("/api/state", headers={"Host": "evil.example"})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid host header"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "duplicate_headers",
    [
        [(b"host", b"testserver"), (b"host", b"testserver")],
        [
            (b"host", b"testserver"),
            (b"origin", b"http://testserver"),
            (b"origin", b"http://testserver"),
        ],
    ],
)
async def test_policy_rejects_duplicate_authority_headers(duplicate_headers):
    app = RequestPolicyMiddleware(
        _body_app(),
        allowed_hosts=("testserver",),
    )
    status, body = await _asgi_request(app, [b"ok"], headers=duplicate_headers)
    assert status == 400
    assert "header" in body["error"]


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        (None, 415),
        ("text/plain", 415),
        ("application/json; charset=utf-8", 200),
        ("application/problem+json", 200),
    ],
)
def test_policy_enforces_json_media_types(content_type, expected):
    headers = {} if content_type is None else {"Content-Type": content_type}
    with _policy_client() as client:
        response = client.post(
            "/api/send", content=b'{"content":"hello"}', headers=headers
        )

    assert response.status_code == expected
    if expected == 415:
        assert response.json() == {"error": "content-type must be application/json"}
