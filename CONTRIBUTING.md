# Contributing to Claude Bridge

Thanks for your interest. Claude Bridge is intentionally small and focused —
contributions that keep it that way are most welcome.

## What we want

- Bug fixes
- Better error messages
- Improved docs or examples
- New transport options (stdio, WebSocket)
- Optional SQLite persistence layer
- Auth token support

## What we don't want

- Heavy dependencies
- Features that duplicate what Claude Code already does natively
- Breaking changes to the MCP tool interface

## How to contribute

1. Fork the repo and create a branch: `git checkout -b fix/your-fix`
2. Editable install with dev deps: `pip install -e .[dev]`
3. Make your changes under `claude_bridge/`
4. Run `ruff check claude_bridge tests/` — keep it clean
5. Run `pytest -v` — keep all tests green
6. Open a PR with a clear description of what changed and why

## Ground rules

- Keep the runtime small. The bridge is a relay, not an orchestrator — heavy dependencies or feature creep should be argued for, not assumed.
- Don't add auth by default — keep the default path simple, opt-in complexity.
- Test against Python 3.10+.

## Questions

Open an issue. We respond fast.
