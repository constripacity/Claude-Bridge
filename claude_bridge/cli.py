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
                        help="Interface to bind for HTTP/SSE (default: 0.0.0.0 — all interfaces)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to listen on for HTTP/SSE (default: 8765)")
    parser.add_argument("--db", default=None,
                        help="SQLite database path (default: ./claude-bridge.db, "
                             "or the value of the CLAUDE_BRIDGE_DB env var)")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Disable the web dashboard mount at / (HTTP mode only)")
    parser.add_argument("--auth-token", default=None,
                        help="Require Authorization: Bearer <token> on every endpoint "
                             "except /status (HTTP mode only). Also reads "
                             "CLAUDE_BRIDGE_AUTH_TOKEN env var; the CLI flag wins. "
                             "If unset, the bridge runs without auth (default).")
    parser.add_argument("--cors-origin", action="append", default=None, metavar="ORIGIN",
                        help="Allow this origin to make cross-origin requests "
                             "(repeatable). Default allows only localhost/127.0.0.1/::1 "
                             "on any port. Also reads CLAUDE_BRIDGE_CORS_ORIGIN env var "
                             "(comma-separated). Passing the CLI flag clears the env "
                             "value and uses only what's on the command line.")
    parser.add_argument("--stdio", action="store_true",
                        help="Run as a stdio MCP server (no HTTP, no dashboard) — "
                             "for single-process / local subprocess use")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Apply flags via env BEFORE importing the server module so its module-level
    # constants (DB_PATH, WEB_DIR) pick them up.
    if args.db:
        os.environ["CLAUDE_BRIDGE_DB"] = args.db
    if args.no_dashboard:
        os.environ["CLAUDE_BRIDGE_NO_DASHBOARD"] = "1"
    if args.auth_token:
        os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"] = args.auth_token
    if args.cors_origin:
        os.environ["CLAUDE_BRIDGE_CORS_ORIGIN"] = ",".join(args.cors_origin)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    if args.stdio:
        return _run_stdio()
    return _run_http(args)


def _run_stdio() -> int:
    """Run the bridge as a stdio MCP server. No banner — stdout is reserved
    for JSON-RPC traffic."""
    import asyncio

    from . import server as bridge_server

    bridge_server.db()  # initialize DB before serving
    try:
        asyncio.run(bridge_server.run_stdio())
    except KeyboardInterrupt:
        pass
    return 0


def _run_http(args: argparse.Namespace) -> int:
    """Run the bridge on uvicorn (HTTP + SSE + web dashboard)."""
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
    if bridge_server.AUTH_TOKEN:
        print(f"  Auth: Bearer token required (set via CLAUDE_BRIDGE_AUTH_TOKEN / --auth-token)")
    print(bar)
    sys.stdout.flush()

    bridge_server.db()  # initialize DB before serving
    uvicorn.run(bridge_server.app, host=args.host, port=args.port)
    return 0
