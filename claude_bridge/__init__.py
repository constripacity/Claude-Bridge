"""Claude Bridge — real-time cross-machine MCP relay for Claude Code agents.

Importing this package has no server side effects: it exposes only the version.
Import :mod:`claude_bridge.server` explicitly for the ASGI ``app`` object. This
isolation is what lets ``cli.main()`` apply CLI flags (via environment
variables) before the server module is first imported. See :mod:`._version`.
"""

from ._version import VERSION as __version__

__all__ = ["__version__"]
