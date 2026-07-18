# Compatibility

Claude Bridge implements the Model Context Protocol (MCP); it does not call a
Claude, OpenAI, or other model API. Client compatibility depends on the MCP
transport that client supports.

## What “verified” means

This project uses the following labels deliberately:

- **Protocol-tested** — an automated test uses the MCP Python SDK to initialize
  a session, negotiate the protocol, and list or call bridge tools.
- **Implementation-tested** — project tests cover the transport adapter or
  broker, but not a complete vendor client process.
- **Manually reported** — a maintainer or user exercised the workflow; it is not
  reproduced in CI.
- **Unverified** — the protocol should align, but this repository has no test
  evidence yet.

Protocol compatibility is not the same as vendor end-to-end certification.
Claude Code, Codex, and other clients are independently released and can change
their configuration, authentication, or MCP behavior.

## Transport matrix

| Transport | Endpoint/mode | Status | Intended use |
|---|---|---|---|
| MCP Streamable HTTP | `/mcp` | Protocol-tested over a real socket for initialize, list-tools, ping, send, receive, acknowledge, and wait | Recommended remote transport |
| MCP stdio | `claude-bridge --stdio` | Implementation-tested | Local subprocess launched by a client |
| Legacy MCP HTTP+SSE | `/sse` + `/messages/` | Retained and implementation-tested | Existing configurations during migration |
| Channel event SSE | `/events/channel/<channel>` | Implementation-tested | Dashboard, TUI, and custom HTTP consumers; **not** an MCP transport |
| JSON API | `/api/*` | API-tested | Dashboard, scripts, and integrations |

The old `/sse` route is maintained for compatibility, but new remote
configurations should use `/mcp`.

## Client matrix

| Client | Local stdio | Remote `/mcp` | Legacy `/sse` | Evidence in this repository |
|---|---|---|---|---|
| Claude Code | Expected compatible | Expected compatible | Historically exercised manually | Protocol tests, not a current Claude Code E2E CI job |
| Codex CLI | Expected compatible | Expected compatible | Not a documented target | Protocol tests, not a Codex E2E CI job |
| Generic MCP SDK client | Depends on SDK | Protocol-tested | Depends on SDK | MCP Python SDK exercises initialize/list/ping/send/receive/ack/wait over a real socket |
| Cursor / other MCP hosts | Unverified | Unverified | Unverified | No vendor E2E test yet |
| Direct REST client | N/A | N/A | N/A | API tests |

“Expected compatible” means the bridge implements a transport the client
documents. It is not a claim that every released client version has been
manually tested. Reports with the client version, OS, transport, and logs are
welcome.

## Claude Code examples

Remote, recommended transport:

```bash
claude mcp add --transport http -s user claude-bridge \
  http://127.0.0.1:8765/mcp
```

Local subprocess:

```bash
claude mcp add -s user claude-bridge -- claude-bridge --stdio
```

Existing legacy configuration:

```bash
claude mcp add --transport sse -s user claude-bridge \
  http://127.0.0.1:8765/sse
```

For a protected remote bridge, attach
`Authorization: Bearer <token>` using the header option supported by the
installed Claude Code version. Do not paste a real token into a repository.

## Codex examples

Local stdio in `~/.codex/config.toml`:

```toml
[mcp_servers.claude_bridge]
command = "claude-bridge"
args = ["--stdio"]
```

Remote Streamable HTTP:

```toml
[mcp_servers.claude_bridge]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "CLAUDE_BRIDGE_AUTH_TOKEN"
```

Restart the client or reload its MCP configuration after adding the server.
Exact commands and configuration keys should be checked against the installed
client's current documentation.

## Compatibility test checklist

A vendor-client compatibility report should record:

1. bridge version and installation method;
2. client name and exact version;
3. operating system and Python version;
4. stdio, Streamable HTTP, or legacy SSE;
5. whether authentication and TLS were enabled;
6. initialization and tool-list result;
7. one send, one receive/wait, and one acknowledgement; and
8. reconnect behavior using the previous consumer cursor.

Do not include tokens or private message content in logs.
