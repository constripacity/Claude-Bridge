"""Single source of truth for the package version.

This module deliberately imports nothing from the server. Reading the version
— for ``claude-bridge --version``, ``claude_bridge.__version__``, or hatch's
build-time version hook — must never trigger server module initialization.

That import isolation is the fix for the v0.9.1 configuration bug: the console
entry point imports the package to read ``__version__``, and the server module
freezes its configuration (auth token, DB path, dashboard mount, retention,
audit) from environment variables at import time. If importing the package
pulled in the server, that snapshot was taken *before* ``cli.main()`` applied
the CLI flags, making ``--auth-token``, ``--db``, ``--no-dashboard``,
``--cors-origin``, ``--retention-days`` and ``--audit-log`` silent no-ops.
"""

VERSION = "0.9.2"
