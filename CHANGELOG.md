# Changelog

Notable changes to Claude Bridge. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases use semantic
versioning where the Python packaging format allows.

## [1.2.0] - 2026-08-17

> `1.2.0rc1` (2026-08-17) is the first pre-release of this line, staged for a soak on PyPI (`pip install --pre` / `uvx claude-code-bridge==1.2.0rc1`). `1.2.0` final follows after the soak. This is a **major release with breaking changes** — see `docs/MIGRATING-0.9-TO-1.2.md`.

### Added

- MCP Streamable HTTP at `/mcp`, with stdio retained for local subprocesses and
  the old HTTP+SSE endpoints retained as a compatibility transport.
- Protocol-v1 structured message envelopes with threads, replies, correlation
  and causation identifiers, recipients, artifact references, metadata, and
  extensions while preserving legacy string messages.
- Idempotent sends and persistent, channel-scoped consumer cursors.
- `bridge_wait` for bounded long polling and `bridge_ack` for monotonic consumer
  acknowledgements.
- MCP server instructions, structured results, schemas, and tool-behavior
  annotations.
- Host-header, browser-origin, JSON media-type, and streaming request-size
  enforcement.
- A locally bundled dashboard build and restrictive Content Security Policy;
  the browser no longer downloads React or Babel from a third-party CDN.
- Opaque, revocable `HttpOnly` dashboard sessions. Event streams authenticate
  with the session cookie, and token query parameters are rejected.
- A transactional SQLite event outbox that propagates stdio/process-external
  writes to HTTP event subscribers in commit order without retaining duplicate
  message bodies.
- Cross-platform CI coverage and package-install smoke tests.
- Correct MCP Registry package arguments so `--stdio` is passed to the bridge
  package rather than interpreted as an `uvx` runtime option.

### Changed

- Version loading no longer imports or initializes the server, so CLI settings
  are applied before runtime configuration is constructed.
- Binding a non-loopback interface now requires a trusted host plus Bearer
  authentication, unless the operator deliberately passes
  `--allow-unauthenticated-network`.
- Remote examples use Streamable HTTP. `/sse` is now described as legacy rather
  than the preferred MCP transport.
- Channel names, sender IDs, message sizes, cursors, and numeric limits use the
  same validation rules across HTTP and MCP paths.
- The package now declares and tests Python 3.13 support.
- The TUI HTTP client ignores ambient proxy variables by default, avoiding
  accidental SOCKS/proxy dependency failures for direct bridge connections.

### Fixed

- CLI flags such as `--auth-token`, `--db`, `--no-dashboard`, CORS, retention,
  and audit settings being applied too late to affect the imported server.
- SSE resume no longer double-delivers a message committed in the window
  between subscriber registration and backlog replay (the live copy is now
  dropped when the same message id was already sent in the backlog).
- A transient error in the inline post-commit event relay no longer fails an
  already-committed send; the durable outbox loop redelivers the event.
- Protocol envelopes bound the artifact count before running per-item hashing
  and canonical-JSON validation.
- A cursor from one channel being accepted as a cursor for another channel.
- Negative or extreme MCP receive limits returning unbounded history.
- MCP sends bypassing the message-size limits used by the REST API.
- Chunked or incorrectly framed requests bypassing the request-body limit.
- Concurrent first-time process startup racing during SQLite WAL/schema setup.
- Database contention blocking the event loop or surfacing as an untyped 500;
  writes now use bounded async retry and return retryable 503 responses.
- Clears and retention leaving idempotency keys pointing at deleted messages.
- Audit failures making an already-committed mutation appear to have failed.
- Deeply nested legacy or request JSON raising recursion errors on read paths.

### Security

- Network listeners fail closed unless their host and authentication policy is
  explicit.
- Unauthenticated access behind a same-host reverse proxy is now rejected: a
  loopback peer is trusted only when the request carries no proxy-forwarding
  header (`X-Forwarded-For` / `X-Real-IP` / `Forwarded`). Otherwise every remote
  request fronted by nginx/Caddy/Tailscale Funnel would arrive as `127.0.0.1`
  and defeat the fail-closed gate. Set a token or pass
  `--allow-unauthenticated-network` for a deliberately open trusted network.
- Cross-origin browser mutations, invalid Host headers, and unsupported JSON
  media types are rejected before reaching handlers.
- Audit retention is bounded instead of growing indefinitely.
- Ambiguous transfer framing, duplicate authority/origin headers, and declared
  body-length mismatches are rejected.
- New POSIX database files are owner-only, dashboard sessions cannot self-renew,
  and active cookie-authenticated event streams revalidate revocation/expiry.

## [0.9.7] - 2026-08-17

Add MCP tool-behavior annotations. No functional change.

### Added

- Every tool now declares MCP annotation hints (`readOnlyHint`,
  `destructiveHint`, `idempotentHint`, `openWorldHint`, and a `title`). The four
  read tools (`bridge_receive`, `bridge_channels`, `bridge_ping`,
  `bridge_status`) are marked read-only; `bridge_send` is a non-destructive
  write; `bridge_clear` is destructive + idempotent; all are closed-world. Lets
  MCP clients (and directory scorers) understand each tool's behavior before
  calling it.

## [0.9.6] - 2026-08-17

Packaging/registry fix so `uvx` â€” and MCP directories (e.g. Glama) that
auto-launch servers via `uvx` â€” can install and run the stdio server. No
functional change to the bridge itself.

### Fixed

- **`uvx claude-code-bridge` now works.** The PyPI distribution is
  `claude-code-bridge` but the console command was only `claude-bridge`, so
  `uvx claude-code-bridge` failed ("executable not provided by package"). Added a
  `claude-code-bridge` console-script alias (identical entry point; `claude-bridge`
  stays primary), so the package name resolves as a command.
- **MCP Registry launch config:** `--stdio` moved from `runtimeArguments` (flags
  for `uvx` itself) to `packageArguments` (args for the server), so the registry
  entry launches `uvx claude-code-bridge --stdio` correctly â€” unblocking the
  directory auto-installers that previously reported "cannot be installed."

## [0.9.5] - 2026-08-08

Dependency-hardening patch. No feature or API changes.

### Fixed

- Upper-bounded every remaining runtime, TUI, and dev dependency below its next
  major (`starlette<2`, `uvicorn<1`, `anyio<5`, `sse-starlette<4`, `textual<9`,
  `httpx<1`, and the dev pins). 0.9.4 capped only `mcp`; this extends the same
  protection to the rest, so no unpinned upgrade can break a released line or
  turn CI red on unchanged code. Verified in a clean venv (all deps resolve
  within the caps, 110 tests pass).

## [0.9.4] - 2026-08-08

Field-use fixes from a live two-agent pairing session (same-machine, legacy
`/sse`), plus a dependency cap that keeps the package installable. No new
transport, protocol, or configuration surface. Supersedes and replaces 0.9.3,
which was withdrawn before it reached PyPI because its dependency metadata was
unbounded (see below).

### Fixed

- **Capped `mcp<2` so the package still installs and runs.** The dependency was
  declared `mcp>=1.0.0` with no upper bound; once `mcp 2.0` shipped it removed
  the low-level `@server.list_tools()` / `@server.call_tool()` decorator API this
  server is built on, so a fresh `pip install` resolved `mcp 2.0` and failed to
  import. The cap pins the 1.x API. (This affected every prior 0.9.x release;
  0.9.0â€“0.9.2 have been yanked from PyPI.)
- Pinned the ruff lint rule set to its historical default (`E4/E7/E9/F`) in
  `pyproject.toml`, so an unpinned ruff upgrade broadening its defaults can no
  longer turn CI red on unchanged code (ruff 0.16 did exactly that).

### Added

- `GET /api/messages?full=true` returns each message's whole `content` instead
  of a truncated `preview`, so a conversation reads in one request rather than
  N+1 per-message detail fetches (F-004).

### Changed

- `GET /api/messages` now returns `ts` as full ISO-8601 with the trailing `Z`
  (previously a bare `HH:MM:SS`), and the dashboard renders every timestamp in
  the viewer's local zone with a zone label. An unlabelled UTC time two hours
  off the reader's clock reads as a local one and gets believed (F-006).
- `POST /api/messages` (a common wrong guess for sending) now returns a pointed
  405 naming `POST /api/send`, instead of a bare "Method Not Allowed" (F-003).

### Documentation

- `CLAUDE.md`: start the bridge **before** any agent session; if a session
  attached before the bridge was up (or the bridge restarted under it), every
  tool fails with `-32602` and the fix is `/mcp` â†’ Reconnect in each session
  (F-001, F-002). Added a same-machine, role-based sender-ID convention for two
  agents on one host (F-005).
- `README.md`: documented `POST /api/send` as the write endpoint and `?full=true`
  on the messages listing, and which operations are REST vs MCP (F-003, F-004).

## [0.9.2] - 2026-07-18

Security/correctness patch. Small, targeted fix on the 0.9.1 base â€” no new
transport, protocol, or configuration surface.

### Security

- **CLI configuration flags are now applied before the server initializes.**
  In 0.9.0â€“0.9.1 the console entry point imported the server module (via the
  package's `__init__`) to read `__version__`, and the server froze its
  configuration from environment variables at import time â€” *before*
  `cli.main()` set those variables from the command line. As a result
  `--auth-token`, `--auth-token-file`, `--db`, `--no-dashboard`, `--cors-origin`,
  `--retention-days`, and `--audit-log` were **silent no-ops**. An operator who
  started the bridge with `--auth-token <secret> --host 0.0.0.0` believing it was
  protected was serving an **unauthenticated, network-exposed** bridge. Setting
  the corresponding `CLAUDE_BRIDGE_*` environment variables was, and remains,
  effective â€” only the CLI flags were affected.

  **Anyone who relied on the CLI flags (rather than the environment variables)
  for authentication should upgrade to 0.9.2 and confirm auth is enforced.**

### Fixed

- The package version now lives in a dependency-free `claude_bridge/_version.py`;
  importing `claude_bridge` no longer imports the server, so CLI flags set by
  `cli.main()` take effect. Added regression tests that fail if the package
  import pulls in the server or if a flag's env var is not seen by the server.

## [0.9.1] - 2026-06-01

- Hardened audit behavior; moved CI actions to their Node 24 revisions.

## [0.9.0] - 2026-06-01

- Direct TLS support, message retention, an audit log, and the official
  container image (GHCR).

## [0.8.0] - 2026-05-28

- Per-channel live SSE event stream used by the dashboard and TUI.

## [0.7.0] - 2026-05-27

- Optional Bearer authentication; the 0.7.x patches tightened CORS, request
  limits, default binding, cursors, CI, and local font assets.

## [0.6.1] - 2026-05-27

- stdio MCP transport.

## [0.5.0] - 2026-05-27

- Dashboard, JSON API, package layout, and the initial cross-machine relay.

[1.2.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.7...v1.2.0
[0.9.7]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.6...v0.9.7
[0.9.6]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.5...v0.9.6
[0.9.5]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.2...v0.9.4
[0.9.2]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.7.6...v0.8.0
[0.7.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.5.0...v0.6.1
[0.5.0]: https://github.com/constripacity/Claude-Bridge/releases/tag/v0.5.0
