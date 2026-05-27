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
2. Make your changes to `server.py`
3. Run `ruff check server.py` — keep it clean
4. Open a PR with a clear description of what changed and why

## Ground rules

- Keep `server.py` as a single file. The whole point is zero-friction setup.
- Don't add auth by default — keep the default path simple, opt-in complexity.
- Test against Python 3.10+.

## Questions

Open an issue. We respond fast.
