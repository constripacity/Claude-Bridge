"""Claude Bridge — real-time cross-machine MCP relay for Claude Code agents."""

from .server import VERSION as __version__, app

__all__ = ["__version__", "app"]
