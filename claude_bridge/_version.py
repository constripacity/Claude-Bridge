"""Package version without importing the server or constructing the ASGI app.

Keeping this value in a dependency-free module is security-sensitive: the CLI
must be able to parse and apply its configuration before :mod:`server` reads
environment-backed settings.
"""

VERSION = "1.2.0"
