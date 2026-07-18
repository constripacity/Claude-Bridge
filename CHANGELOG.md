# Changelog

Notable changes to Claude Bridge are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[semantic versioning](https://semver.org/) where the Python packaging format
allows it.

## [Unreleased]

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
- Cross-origin browser mutations, invalid Host headers, and unsupported JSON
  media types are rejected before reaching handlers.
- Audit retention is bounded instead of growing indefinitely.
- Ambiguous transfer framing, duplicate authority/origin headers, and declared
  body-length mismatches are rejected.
- New POSIX database files are owner-only, dashboard sessions cannot self-renew,
  and active cookie-authenticated event streams revalidate revocation/expiry.

## [0.9.1] - 2026-06-01

- Hardened audit behavior and moved CI actions to their Node 24 revisions.

## [0.9.0] - 2026-06-01

- Added direct TLS support, message retention, an audit log, and the official
  container build.

## [0.8.0] - 2026-05-28

- Added the per-channel live SSE event stream used by the dashboard and TUI.

## [0.7.0] - 2026-05-27

- Added optional Bearer authentication. The `0.7.x` patch releases subsequently
  tightened CORS, request limits, default binding, cursors, CI, and local font
  assets.

## [0.6.1] - 2026-05-27

- Added the stdio MCP transport.

## [0.5.0] - 2026-05-27

- Added the dashboard, JSON API, package layout, and initial cross-machine MCP
  relay workflow.

[Unreleased]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.7.6...v0.8.0
[0.7.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.5.0...v0.6.1
[0.5.0]: https://github.com/constripacity/Claude-Bridge/releases/tag/v0.5.0
