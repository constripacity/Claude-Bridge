# Changelog

Notable changes to Claude Bridge. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases use semantic
versioning where the Python packaging format allows.

## [0.9.3] - 2026-08-08

Field-use fixes from a live two-agent pairing session (same-machine, legacy
`/sse`). No new transport, protocol, or configuration surface.

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
  tool fails with `-32602` and the fix is `/mcp` → Reconnect in each session
  (F-001, F-002). Added a same-machine, role-based sender-ID convention for two
  agents on one host (F-005).
- `README.md`: documented `POST /api/send` as the write endpoint and `?full=true`
  on the messages listing, and which operations are REST vs MCP (F-003, F-004).

## [0.9.2] - 2026-07-18

Security/correctness patch. Small, targeted fix on the 0.9.1 base — no new
transport, protocol, or configuration surface.

### Security

- **CLI configuration flags are now applied before the server initializes.**
  In 0.9.0–0.9.1 the console entry point imported the server module (via the
  package's `__init__`) to read `__version__`, and the server froze its
  configuration from environment variables at import time — *before*
  `cli.main()` set those variables from the command line. As a result
  `--auth-token`, `--auth-token-file`, `--db`, `--no-dashboard`, `--cors-origin`,
  `--retention-days`, and `--audit-log` were **silent no-ops**. An operator who
  started the bridge with `--auth-token <secret> --host 0.0.0.0` believing it was
  protected was serving an **unauthenticated, network-exposed** bridge. Setting
  the corresponding `CLAUDE_BRIDGE_*` environment variables was, and remains,
  effective — only the CLI flags were affected.

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

[0.9.3]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.7.6...v0.8.0
[0.7.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.5.0...v0.6.1
[0.5.0]: https://github.com/constripacity/Claude-Bridge/releases/tag/v0.5.0
