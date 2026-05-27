"""Console-script entry point for `claude-bridge`."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-bridge",
        description="Real-time cross-machine MCP relay server for Claude Code agents.",
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="Interface to bind (default: 0.0.0.0 — all interfaces)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to listen on (default: 8765)")
    parser.add_argument("--db", default=None,
                        help="SQLite database path (default: ./claude-bridge.db, "
                             "or the value of the CLAUDE_BRIDGE_DB env var)")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Disable the web dashboard mount at /")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Apply flags via env BEFORE importing the server module so its module-level
    # constants (DB_PATH, WEB_DIR) pick them up.
    if args.db:
        os.environ["CLAUDE_BRIDGE_DB"] = args.db
    if args.no_dashboard:
        os.environ["CLAUDE_BRIDGE_NO_DASHBOARD"] = "1"

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    import uvicorn

    from . import server as bridge_server

    bar = "━" * 50
    print(bar)
    print("  Claude Bridge — General MCP Relay Server")
    print(f"  Version: {__version__}")
    print(f"  DB: {os.path.abspath(bridge_server.DB_PATH)}")
    print(f"  http://localhost:{args.port}/             ← Dashboard")
    print(f"  http://localhost:{args.port}/sse          ← Local MCP config")
    print(f"  http://<host-address>:{args.port}/sse    ← Remote machines (LAN/Tailscale)")
    print(f"  http://localhost:{args.port}/api/state    ← JSON state for dashboard")
    print(f"  http://localhost:{args.port}/status       ← Health check")
    print(bar)
    sys.stdout.flush()

    bridge_server.db()  # initialize DB before serving
    uvicorn.run(bridge_server.app, host=args.host, port=args.port)
    return 0
