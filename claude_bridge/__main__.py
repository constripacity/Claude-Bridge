"""Allow `python -m claude_bridge` to start the bridge, same as the `claude-bridge` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
