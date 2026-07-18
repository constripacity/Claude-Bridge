# Contributing to Claude Bridge

Claude Bridge is deliberately small: a dependable message transport for
independent agents, not an agent framework. Contributions are welcome when
they preserve that boundary and include evidence for the behavior they add.

## Before opening a pull request

- Use an issue for a substantial feature or protocol change so its scope and
  compatibility story can be agreed first.
- Search existing issues and the [roadmap](docs/ROADMAP.md).
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md), never in a
  public issue or pull request.
- Do not include real Bearer tokens, private channel content, personal paths,
  or production databases in fixtures and logs.

Good contributions include:

- correctness and security fixes;
- protocol and vendor-client compatibility tests;
- clearer setup diagnostics and actionable errors;
- bounded reliability improvements;
- accessible dashboard/TUI improvements;
- reproducible benchmarks; and
- documentation tied to behavior that exists or is explicitly marked planned.

Changes that need strong justification include:

- heavy or hosted runtime dependencies;
- orchestration, planning, or arbitrary command execution;
- breaking MCP tool or stored-message changes;
- a second persistence backend without a demonstrated deployment need; and
- vendor-support claims without a reproducible compatibility report.

## Set up a development environment

Python 3.10–3.13 are supported.

```bash
git clone https://github.com/constripacity/Claude-Bridge.git
cd Claude-Bridge
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate the virtual environment using the command appropriate for your shell.
Do not commit `.venv`, local SQLite databases, or generated credentials.

## Make a focused change

1. Branch from current `main`.
2. Keep unrelated formatting or refactors out of the patch.
3. Add a regression test before or with every bug fix.
4. Update `CHANGELOG.md` for user-visible behavior.
5. Update protocol, compatibility, security, and README documentation when the
   public contract changes.
6. Preserve legacy string messages unless a formally documented major-version
   migration says otherwise.

## Run the checks

```bash
ruff check claude_bridge tests
pytest -v
python -m build
```

For package or CLI changes, also install the built wheel into a clean virtual
environment and run:

```bash
claude-bridge --version
claude-bridge --help
```

For network or transport changes, cover both the normal flow and rejection
paths. Examples include invalid Host and Origin headers, absent auth, chunked
oversize bodies, stale/cross-channel cursors, duplicate idempotency keys,
timeouts, disconnects, and session shutdown.

CI runs Linux across Python 3.10–3.13 and current Python smoke jobs on Windows
and macOS. It also builds and installs both package artifact types. A local
pass on one platform does not replace the matrix.

## Compatibility evidence

Use the terms in [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md):

- **protocol-tested** for an automated complete MCP SDK exchange;
- **implementation-tested** for adapter/unit coverage;
- **manually reported** for a recorded external-client run; and
- **unverified** when compatibility is inferred only from documentation.

A manual report should include client and bridge versions, OS, transport,
authentication/TLS mode, and redacted initialization/tool-call results. Never
upgrade “expected compatible” to “verified” based only on matching protocol
names.

## Protocol rules

- Server sequence is the source of message ordering.
- Cursors and acknowledgements are scoped to both consumer and channel.
- A retry key is scoped to channel and sender and cannot be reused for a
  different payload.
- Unknown future envelopes remain observable as raw content.
- Acknowledgement is monotonic and supplies an at-least-once building block,
  not exactly-once external side effects.
- Received content remains untrusted input.

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the complete contract.

## Pull-request description

Please include:

- the problem and why it belongs in the bridge;
- the behavior before and after;
- compatibility or migration impact;
- security and privacy impact;
- tests run and their results; and
- screenshots only when visual behavior changed.

Keep commits reviewable. Maintainers may ask for a large feature to be split
into a protocol/contract change and one or more implementation changes.

## Release discipline

- Do not edit a released tag.
- The package version, changelog, registry manifest, and container tags must
  agree for a stable release.
- Pre-release features must not be described as stable.
- Publishing should use short-lived trusted credentials and should never run
  with secrets for untrusted pull requests.
- Deprecations need a replacement, a migration example, and at least one
  documented compatibility window.

Questions and small proposals can be opened as GitHub issues.
