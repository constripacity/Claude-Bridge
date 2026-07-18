"""Protocol-level coverage for the modern MCP Streamable HTTP endpoint."""

from __future__ import annotations

import socket

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from claude_bridge.server import _transport_host_patterns, server
from claude_bridge.streamable_http import (
    StreamableHTTPApp,
    StreamableHTTPConfig,
    create_streamable_http_app,
)


PROTOCOL_VERSION = "2025-06-18"
TEST_CONFIG = StreamableHTTPConfig(allowed_hosts=("testserver",))
BASE_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


def _initialize(
    client: TestClient, extra_headers: dict[str, str] | None = None
) -> tuple[str, dict]:
    response = client.post(
        "/mcp",
        headers={**BASE_HEADERS, **(extra_headers or {})},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "bridge-test", "version": "1"},
            },
        },
    )
    assert response.status_code == 200
    return response.headers["mcp-session-id"], response.json()


def _session_headers(session_id: str) -> dict[str, str]:
    return {
        **BASE_HEADERS,
        "mcp-session-id": session_id,
        "mcp-protocol-version": PROTOCOL_VERSION,
    }


def test_streamable_http_initializes_and_lists_bridge_tools(fresh_db):
    app = create_streamable_http_app(server, config=TEST_CONFIG)

    with TestClient(app) as client:
        session_id, initialized = _initialize(client)

        assert initialized["result"]["serverInfo"]["name"] == "claude-bridge"
        assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION

        notification = client.post(
            "/mcp",
            headers=_session_headers(session_id),
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notification.status_code == 202

        tools = client.post(
            "/mcp",
            headers=_session_headers(session_id),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert tools.status_code == 200
        assert {tool["name"] for tool in tools.json()["result"]["tools"]} >= {
            "bridge_send",
            "bridge_receive",
            "bridge_channels",
            "bridge_ping",
            "bridge_clear",
            "bridge_status",
        }

        ping = client.post(
            "/mcp",
            headers=_session_headers(session_id),
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "bridge_ping", "arguments": {}},
            },
        )
        assert ping.status_code == 200
        assert ping.json()["result"]["content"][0]["text"].startswith(
            "✓ Claude Bridge online"
        )


def test_streamable_http_session_can_be_terminated():
    transport = StreamableHTTPApp(server, TEST_CONFIG)

    with TestClient(transport.standalone_app()) as client:
        session_id, _ = _initialize(client)
        headers = _session_headers(session_id)

        deleted = client.delete("/mcp", headers=headers)
        assert deleted.status_code == 200

        expired = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        assert expired.status_code == 404


def test_streamable_http_rejects_untrusted_host():
    config = StreamableHTTPConfig(allowed_hosts=("bridge.example.test",))
    app = create_streamable_http_app(server, config=config)

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers=BASE_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "bridge-test", "version": "1"},
                },
            },
        )

    assert response.status_code == 421


@pytest.mark.parametrize(
    ("configured", "wire_host"),
    [
        ("bridge.example", "bridge.example"),
        ("bridge.example:8765", "bridge.example:443"),
        ("2001:db8::1", "[2001:db8::1]"),
        ("[2001:db8::1]:8765", "[2001:db8::1]:443"),
    ],
)
def test_streamable_http_trusted_hosts_accept_bare_and_port_forms(
    configured, wire_host, fresh_db
):
    config = StreamableHTTPConfig(
        allowed_hosts=_transport_host_patterns(configured)
    )
    app = create_streamable_http_app(server, config=config)
    with TestClient(app) as client:
        session_id, initialized = _initialize(client, {"Host": wire_host})
    assert session_id
    assert initialized["result"]["serverInfo"]["name"] == "claude-bridge"


@pytest.mark.asyncio
async def test_official_mcp_client_handshake_over_real_http(fresh_db):
    """Exercise the same client transport used by modern MCP consumers.

    A real loopback socket matters here: in-memory ASGI transports generally
    buffer long-lived GET event streams and can hide lifecycle bugs.
    """

    app = create_streamable_http_app(server)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", lifespan="on")
    )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(uvicorn_server.serve, [listener])
        with anyio.fail_after(5):
            while not uvicorn_server.started:
                await anyio.sleep(0.01)

        try:
            # Do not inherit CI/developer proxy variables for a loopback test.
            async with httpx.AsyncClient(trust_env=False) as http_client:
                async with streamable_http_client(
                    f"http://127.0.0.1:{port}/mcp",
                    http_client=http_client,
                ) as (read_stream, write_stream, get_session_id):
                    async with ClientSession(read_stream, write_stream) as session:
                        initialized = await session.initialize()
                        tools = await session.list_tools()
                        ping = await session.call_tool("bridge_ping", {})

                        sent = await session.call_tool(
                            "bridge_send",
                            {
                                "channel": "sdk:integration",
                                "sender": "official-client",
                                "content": "sent through Streamable HTTP",
                                "idempotency_key": "real-socket-send-1",
                            },
                        )
                        assert sent.structuredContent is not None
                        sent_id = sent.structuredContent["id"]
                        received = await session.call_tool(
                            "bridge_receive",
                            {"channel": "sdk:integration"},
                        )
                        acknowledged = await session.call_tool(
                            "bridge_ack",
                            {
                                "channel": "sdk:integration",
                                "consumer_id": "official-client-consumer",
                                "message_id": sent_id,
                            },
                        )
                        waited = await session.call_tool(
                            "bridge_wait",
                            {
                                "channel": "sdk:integration",
                                "consumer_id": "official-client-consumer",
                                "timeout_seconds": 0,
                            },
                        )

                        assert initialized.serverInfo.name == "claude-bridge"
                        assert get_session_id()
                        assert "bridge_send" in {tool.name for tool in tools.tools}
                        assert ping.content[0].text.startswith("✓ Claude Bridge online")
                        assert received.structuredContent is not None
                        assert received.structuredContent["messages"][0]["id"] == sent_id
                        assert acknowledged.structuredContent is not None
                        assert acknowledged.structuredContent["last_message_id"] == sent_id
                        assert waited.structuredContent is not None
                        assert waited.structuredContent["timed_out"] is True
        finally:
            uvicorn_server.should_exit = True


def test_streamable_http_manager_must_be_running():
    transport = StreamableHTTPApp(server)
    app = StarletteWithoutLifespan(transport)

    with TestClient(app) as client:
        response = client.post("/mcp", headers=BASE_HEADERS, json={})

    assert response.status_code == 500


class StarletteWithoutLifespan:
    """Tiny test harness proving the SDK lifecycle contract is enforced."""

    def __init__(self, endpoint: StreamableHTTPApp) -> None:
        self.endpoint = endpoint

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            try:
                await self.endpoint(scope, receive, send)
            except RuntimeError as exc:
                assert "Make sure to use run()" in str(exc)
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": b"lifecycle missing"})
