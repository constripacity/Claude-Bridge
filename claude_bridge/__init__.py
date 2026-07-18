"""Claude Bridge — a vendor-neutral relay for coding agents.

Importing the package deliberately has no server side effects.  Applications
that need the ASGI object should import ``claude_bridge.server:app`` directly.
"""

from ._version import VERSION as __version__

__all__ = ["__version__"]
