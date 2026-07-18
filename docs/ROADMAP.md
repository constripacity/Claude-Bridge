# Roadmap

Claude Bridge aims to be the smallest dependable, self-hosted message transport
for independent coding agents. It is intentionally not a full agent
orchestrator.

Dates are not promises. A milestone ships only when its acceptance gates pass;
features may move as real deployments provide better evidence.

## Current forward build — `1.2.0`

Theme: secure interoperability and reliable delivery primitives.

- Streamable HTTP at `/mcp`, stdio, and a migration path from legacy `/sse`.
- Fail-closed network binding with explicit trusted hosts and authentication.
- Consistent validation and streaming request limits across REST and MCP.
- Structured protocol-v1 envelopes while preserving legacy strings.
- Idempotent sends, durable consumer cursors, `bridge_wait`, and `bridge_ack`.
- Structured MCP results, server instructions, and tool annotations.
- Locally bundled dashboard assets and a restrictive Content Security Policy.
- Opaque, revocable dashboard sessions and cookie-authenticated event streams;
  Bearer tokens are not stored in browser storage or accepted in query strings.
- A transactional SQLite event outbox for cross-process live propagation.
- Windows, macOS, Linux, and Python 3.10–3.13 CI coverage.
- Security policy, compatibility evidence, protocol documentation, and
  reproducible package smoke tests.

Release gates:

1. all unit, API, transport, and package-install tests pass;
2. no CLI option is applied after server configuration is initialized;
3. a real MCP SDK initializes `/mcp`, lists tools, sends, waits, and acks;
4. the same retry key cannot create duplicate messages;
5. cross-channel cursors are rejected;
6. non-loopback startup fails without an explicit security policy; and
7. the [migration guide](MIGRATING-0.9-TO-1.2.md) explains every behavior
   change from `0.9.1`.

## `1.3` — native agent experience

- Tested setup helpers and diagnostic output for Claude Code and Codex.
- A machine-readable compatibility report recording client and protocol
  versions.
- An experimental Claude Code Channels companion that converts bridge messages
  into native channel notifications when the client permits custom channels.
- Notification adapters that can wake or alert an operator without granting the
  bridge arbitrary command-execution authority.
- Session-management diagnostics and operator-visible expiry information.

Release gates include vendor-client smoke reports on Windows and macOS. Until
then, compatibility claims remain protocol-level rather than vendor-certified.

## `1.4` — teams and authorization

- Individually revocable credentials bound to stable identities.
- Namespace and channel read/write policies.
- A separate destructive permission for channel clearing and administration.
- Token rotation without downtime, quotas, and rate limits.
- Bounded audit retention, export, and privacy-aware event fields.
- Signed webhooks for integrations that need outbound delivery.

The shared Bearer token remains the simple personal-use mode. Team features
must not make localhost setup depend on an identity provider.

## `1.5` — operations and scale

- Health/readiness separation and documented backup/restore procedures.
- Prometheus/OpenTelemetry-compatible metrics without message-content labels.
- Delivery-gap diagnostics, explicit resynchronization, and subscriber
  backpressure reporting.
- Response-byte budgets with explicit truncation and continuation cursors for
  large histories and aggregate status calls.
- A storage interface plus an optional production backend for multi-process or
  high-availability deployment.
- Multi-architecture container images, SBOMs, signed provenance, and trusted
  package publishing.

SQLite remains the default. A heavier backend ships only with benchmarks and a
real multi-process use case.

## `2.0` — federation, if demand proves it

- Stable protocol and migration policy.
- Optional bridge-to-bridge federation with loop prevention and scoped trust.
- An adapter between bridge tasks/messages/artifacts and the open A2A protocol.
- Capability discovery for agents that can consume typed tasks or artifacts.

Federation will not silently forward private channels. Trust, namespace
ownership, hop limits, and observability must be designed before it is enabled.

## Explicit non-goals

- Running arbitrary shell commands received from a channel.
- Replacing an agent's own planner, worktree manager, or task orchestrator.
- Uploading large artifact bytes into SQLite messages.
- Claiming exactly-once side effects across independent processes.
- Requiring a hosted Claude Bridge account or proprietary cloud service.
- Advertising a client as supported without a reproducible compatibility
  report.

## Product evidence to track

Social impressions are useful discovery evidence, but the roadmap should be
driven by successful use:

- completed two-machine setups;
- weekly active bridges and returning operators;
- sends that are retried or acknowledged correctly;
- median setup time and the most common setup failure;
- client/version combinations proven by reports; and
- external contributors and production deployments.

Issue proposals should explain which measured problem they address and why the
bridge, rather than a client-specific layer, is the right place to solve it.
