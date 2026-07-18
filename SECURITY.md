# Security policy

Claude Bridge moves agent-authored content between machines. Treat it as a
network service and a message transport, not as a security boundary between
mutually hostile users.

## Supported versions

| Version | Status |
|---|---|
| `main` (unreleased) | Active development; security fixes land here first |
| `1.2.0` (latest stable) | Supported |
| Older release lines | Upgrade required before a fix is backported |

Pre-release builds are provided for testing and may change before the stable
release. The project does not promise long-term support for older minor
versions.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's
[private vulnerability reporting form](https://github.com/constripacity/Claude-Bridge/security/advisories/new)
and include:

- the affected version or commit;
- deployment details, including transport and authentication mode;
- minimal reproduction steps or a proof of concept;
- the expected impact; and
- any suggested mitigation, if known.

Avoid accessing data that is not yours, degrading a public deployment, or
publishing details before a fix is available. Maintainers will acknowledge a
report when capacity permits, reproduce it, prepare a fix, and coordinate a
disclosure date with the reporter. This is a volunteer project and does not
currently offer a bug bounty or guaranteed response SLA.

## Trust model

- The default HTTP listener is loopback-only. Stdio is local to the process
  that launches it.
- A wildcard non-loopback listener fails closed unless the operator supplies at
  least one `--trusted-host`. A concrete bind address is trusted automatically.
  Every non-loopback listener also requires Bearer authentication unless the
  operator explicitly accepts the risk with
  `--allow-unauthenticated-network`.
- `--trusted-host` protects the HTTP `Host` boundary; it is not authentication.
- The current Bearer token is one shared secret with bridge-wide access. It
  does not provide per-user identity, per-channel ACLs, or separate read,
  write, and clear permissions.
- Consumer acknowledgement cursors (`bridge_ack`) are keyed by a caller-supplied
  `consumer_id` that is not bound to an identity. Any token holder can advance
  any consumer's cursor, so consumers are a coordination convenience, not an
  isolation boundary. Per-identity, revocable credentials are planned for a
  later teams/authorization release.
- `/status` intentionally remains unauthenticated and exposes only health
  information. Protected APIs and MCP endpoints require the token when one is
  configured.
- Messages are stored as plaintext in SQLite. HTTP does not provide transport
  encryption. Use HTTPS at the bridge or a trusted encrypted overlay such as a
  private tailnet when traffic leaves one machine.
- New SQLite files are created owner-only (`0600`) on POSIX systems. Existing
  group/world-accessible files are not silently changed, but startup logs a
  warning so the operator can correct or deliberately retain that policy.
- Agent names and envelope `sender` values are caller assertions. They are not
  cryptographic identities.
- Message content is untrusted input. Receiving agents must not treat a bridged
  message as a system or developer instruction merely because it arrived over
  MCP.
- Artifact entries are references, not uploaded bytes. Consumers must validate
  the referenced location, content type, size, and digest before opening one.
- Retention removes old bridge data and acknowledgements are delivery cursors;
  neither feature turns the bridge into a backup system.

## Safe network deployment

Generate a high-entropy token and allow only the hostnames or IP addresses
clients actually use:

```bash
export CLAUDE_BRIDGE_AUTH_TOKEN="$(openssl rand -hex 32)"
claude-bridge \
  --host 0.0.0.0 \
  --trusted-host 100.100.20.30
```

For a DNS name behind a reverse proxy:

```bash
export CLAUDE_BRIDGE_AUTH_TOKEN="$(openssl rand -hex 32)"
claude-bridge \
  --host 127.0.0.1 \
  --trusted-host bridge.example.internal
```

Require authentication at the bridge even when a reverse proxy also performs
authentication. Do not rely on apparent loopback client addresses after
proxying as proof that a request is local.

Also:

1. Terminate TLS before traffic crosses an untrusted network.
2. Restrict the listening port with the host firewall or overlay-network ACL.
3. Prefer `--auth-token-file` or the environment variable over a literal
   `--auth-token`, which can appear in process listings.
4. Keep the SQLite database and token file readable only by the bridge account.
5. Set message and audit retention appropriate to the data being transported.
6. Rotate the shared token after exposure or when a collaborator loses access.
7. Do not use `--allow-unauthenticated-network` on public Wi-Fi or the public
   internet. It is an explicit escape hatch for a controlled private network.

## Browser sessions and event streams

Bearer headers are preferred for MCP, REST scripts, and the TUI. The dashboard
exchanges the Bearer token once at `POST /api/session` for an opaque,
short-lived `HttpOnly`, `SameSite=Strict` cookie. The master token is not stored
in browser storage or inserted into an event-stream URL. `?token=` query
authentication is rejected because query strings can leak through history,
proxies, observability products, screenshots, and access logs.

Dashboard sessions are held in server memory, are revocable by logging out,
expire after the configured TTL, and are all invalidated on server restart. A
session cookie cannot create a replacement session: only the master Bearer
credential can mint one, and minting rotates any existing cookie. Open event
streams revalidate session expiry/revocation at least every five seconds.
Browser access is same-origin by default; even another localhost port requires
an explicit `--cors-origin`. Use HTTPS so the cookie receives the `Secure`
attribute when the dashboard is accessed across a network. When TLS terminates
at a reverse proxy that forwards `X-Forwarded-Proto: https`, the `Secure`
attribute and HSTS are still applied even though the bridge itself sees plain
HTTP.

## Operational limits

- The bridge uses a single SQLite connection driven from the event loop. Under
  heavy concurrent write contention, read requests may return a retryable `503`
  (with `Retry-After`) rather than block; clients should honor it.
- Clearing or applying retention to a very large channel runs as one
  transaction and briefly occupies the event loop for the duration of the
  delete. This is acceptable for typical channel sizes; batched deletion for
  very large channels is a planned operations-tier improvement. SQLite remains
  the default and is not intended for high-write multi-process fan-in.

## Dependency and release hygiene

GitHub Actions are pinned to immutable commit SHAs. Pull requests build the
package and container without publishing either. Release credentials must not
be added to pull-request workflows. A future publishing workflow should use
short-lived trusted publishing rather than a long-lived PyPI token.
