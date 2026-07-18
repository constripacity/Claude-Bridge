# Migrating from 0.9.1 to the 1.2 forward build

The `1.2.0.dev1` forward build preserves the existing `messages` table, legacy
string payloads, stdio mode, and the old `/sse` transport. It also changes a
few defaults and security boundaries deliberately. Test a copy of the SQLite
database before replacing a bridge that matters to active work.

## Before upgrading

1. Stop every process writing to the database.
2. Copy the database and, if present, its `-wal` and `-shm` files together.
3. Record the current command, environment variables, MCP client versions, and
   whether clients use stdio, `/sse`, or a remote URL.
4. Install the forward build in a separate virtual environment and point it at
   the copied database first.

The upgrade adds auxiliary reliability, consumer-cursor, schema-component, and
event-outbox tables. Downgrading leaves those tables in place; 0.9.1 ignores
them, but new idempotency/cursor behavior is unavailable after a downgrade.

## Required deployment changes

### Network listeners fail closed

A non-loopback listener now requires both an explicit trusted Host value and a
Bearer token, unless `--allow-unauthenticated-network` is passed deliberately:

```bash
export CLAUDE_BRIDGE_AUTH_TOKEN="$(openssl rand -hex 32)"
claude-bridge --host 0.0.0.0 --trusted-host 100.100.20.30
```

Reverse-proxy DNS names and tailnet/LAN addresses used by clients must be in
`--trusted-host` / `CLAUDE_BRIDGE_TRUSTED_HOSTS`. The exported ASGI app also
blocks unauthenticated non-loopback clients by default, so launching it outside
the CLI does not bypass the network policy.

### Browser authentication no longer accepts query tokens

Remove `?token=...` from event-stream URLs. The bundled dashboard exchanges the
master Bearer token once at `POST /api/session` for an opaque `HttpOnly` cookie.
A session cookie cannot create more sessions, logout revokes it, and open event
streams revalidate it periodically. Separate browser origins—including another
localhost port—must be listed explicitly with `--cors-origin`.

### Prefer Streamable HTTP

New remote MCP configurations should use `http://HOST:8765/mcp`. Existing
`/sse` plus `/messages/` configurations remain available as a migration path.
Stdio remains the simplest local subprocess mode.

## Message and delivery changes

- `bridge_send` accepts either the legacy `content` string or a protocol-v1
  `message` object, never both.
- Supplying an `idempotency_key` deduplicates identical retries while the
  original message remains retained. Clearing or retention removes the linked
  key as part of the same destructive reset.
- `bridge_receive` supports durable `consumer_id` cursors in addition to
  `since_id`; cursors are channel-scoped.
- `bridge_wait` provides bounded long polling, and `bridge_ack` advances a
  consumer cursor monotonically after successful processing.
- A stale, deleted, or cross-channel `since_id` produces an explicit warning
  instead of silently replaying a different channel or the full history.
- Tool calls return structured MCP content as well as readable text.

Legacy strings and historical rows remain readable. A JSON object is treated
as a protocol envelope only when it has `schema_version`, `type`, and `content`.

## Operational changes

- The dashboard is fully self-hosted; it no longer downloads React or Babel at
  runtime.
- Live events from a separate stdio/HTTP process are relayed through a durable
  ordered outbox. The outbox stores message references, not duplicate content.
- New database files are created owner-only on POSIX systems. Existing
  group/world-readable files produce a warning and should be reviewed.
- Invalid environment values fail startup with a concise configuration error.
- The TUI ignores ambient proxy variables by default; use `--trust-env` only
  when the bridge should be reached through configured HTTP/SOCKS proxies.
- Audit rows, event-outbox rows, requests, messages, replay pages, and session
  lifetimes all have documented bounds.

## Verification after upgrading

1. `claude-bridge --version` reports `1.2.0.dev1`.
2. `GET /status` is healthy and contains no database path or channel data.
3. Each client initializes and lists all eight tools.
4. Send, receive/wait, and acknowledge one test message.
5. Retry that send with the same key and verify the message count does not
   increase.
6. Restart one client and verify its durable consumer resumes correctly.
7. If multiple processes share the database, write through one and confirm the
   dashboard connected to the other receives the event in order.
8. Confirm the dashboard can log in, log out, and no token appears in its URL
   or browser storage.

Keep the backup until these checks pass with the actual client versions and
network route used by the deployment.
