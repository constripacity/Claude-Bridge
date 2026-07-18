# Changelog

Notable changes to Claude Bridge. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases use semantic
versioning where the Python packaging format allows.

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

[0.9.2]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.7.6...v0.8.0
[0.7.0]: https://github.com/constripacity/Claude-Bridge/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/constripacity/Claude-Bridge/compare/v0.5.0...v0.6.1
[0.5.0]: https://github.com/constripacity/Claude-Bridge/releases/tag/v0.5.0
