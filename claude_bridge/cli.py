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
    parser.add_argument("--host", default="127.0.0.1",
                        help="Interface to bind for HTTP/SSE (default: 127.0.0.1 — localhost only). "
                             "Pass 0.0.0.0 to accept connections from other machines on the network.")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to listen on for HTTP/SSE (default: 8765)")
    parser.add_argument("--db", default=None,
                        help="SQLite database path (default: ./claude-bridge.db, "
                             "or the value of the CLAUDE_BRIDGE_DB env var)")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Disable the web dashboard mount at / (HTTP mode only)")
    parser.add_argument("--auth-token", default=None, metavar="TOKEN",
                        help="Require Authorization: Bearer <token> on every endpoint "
                             "except /status (HTTP mode only). Prefer --auth-token-file or "
                             "the CLAUDE_BRIDGE_AUTH_TOKEN env var; the literal value passed "
                             "here is visible in `ps` output and /proc/<pid>/cmdline. "
                             "Precedence: --auth-token > --auth-token-file > env var. "
                             "Unset = no auth (default).")
    parser.add_argument("--auth-token-file", default=None, metavar="PATH",
                        help="Read the auth token from a file (trailing whitespace stripped). "
                             "Safer than --auth-token because the token never appears in the "
                             "process command line.")
    parser.add_argument("--cors-origin", action="append", default=None, metavar="ORIGIN",
                        help="Allow this origin to make cross-origin requests "
                             "(repeatable). Default allows only localhost/127.0.0.1/::1 "
                             "on any port. Also reads CLAUDE_BRIDGE_CORS_ORIGIN env var "
                             "(comma-separated). Passing the CLI flag clears the env "
                             "value and uses only what's on the command line.")
    parser.add_argument("--tls-cert", default=None, metavar="PATH",
                        help="Path to a TLS certificate (PEM) to serve HTTPS directly "
                             "instead of plain HTTP. Must be passed together with "
                             "--tls-key. Without these the bridge serves HTTP and you "
                             "should terminate TLS at a reverse proxy / Tailscale. "
                             "(HTTP mode only — ignored with --stdio.)")
    parser.add_argument("--tls-key", default=None, metavar="PATH",
                        help="Path to the TLS private key (PEM) matching --tls-cert.")
    parser.add_argument("--retention-days", type=int, default=None, metavar="N",
                        help="Delete messages older than N days via a background sweep "
                             "(default: keep forever). Opt-in; deletes historical state. "
                             "Also reads CLAUDE_BRIDGE_RETENTION_DAYS.")
    parser.add_argument("--audit-log", action="store_true",
                        help="Record auth failures, oversize rejects, channel clears, and "
                             "channel creates to an audit table, readable at /api/audit "
                             "(auth-protected). Off by default.")
    parser.add_argument("--stdio", action="store_true",
                        help="Run as a stdio MCP server (no HTTP, no dashboard) — "
                             "for single-process / local subprocess use")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # TLS: cert and key are all-or-nothing, and must exist before we hand them
    # to uvicorn (a clear CLI error beats an opaque SSL stack trace at bind).
    if bool(args.tls_cert) != bool(args.tls_key):
        print("error: --tls-cert and --tls-key must be passed together", file=sys.stderr)
        return 2
    for label, path in (("--tls-cert", args.tls_cert), ("--tls-key", args.tls_key)):
        if path and not os.path.isfile(path):
            print(f"error: {label} file not found: {path}", file=sys.stderr)
            return 2

    # Apply flags via env BEFORE importing the server module so its module-level
    # constants (DB_PATH, WEB_DIR) pick them up.
    if args.db:
        os.environ["CLAUDE_BRIDGE_DB"] = args.db
    if args.no_dashboard:
        os.environ["CLAUDE_BRIDGE_NO_DASHBOARD"] = "1"
    if args.auth_token:
        os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"] = args.auth_token
    elif args.auth_token_file:
        try:
            with open(args.auth_token_file, encoding="utf-8") as f:
                os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"] = f.read().strip()
        except OSError as e:
            print(f"error: could not read --auth-token-file: {e}", file=sys.stderr)
            return 2
    if args.cors_origin:
        os.environ["CLAUDE_BRIDGE_CORS_ORIGIN"] = ",".join(args.cors_origin)
    if args.retention_days is not None:
        os.environ["CLAUDE_BRIDGE_RETENTION_DAYS"] = str(args.retention_days)
    if args.audit_log:
        os.environ["CLAUDE_BRIDGE_AUDIT_LOG"] = "1"

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

    scheme = "https" if args.tls_cert else "http"
    bar = "━" * 50
    print(bar)
    print("  Claude Bridge — General MCP Relay Server")
    print(f"  Version: {__version__}")
    print(f"  DB: {os.path.abspath(bridge_server.DB_PATH)}")
    print(f"  {scheme}://localhost:{args.port}/             ← Dashboard")
    print(f"  {scheme}://localhost:{args.port}/sse          ← Local MCP config")
    print(f"  {scheme}://<host-address>:{args.port}/sse    ← Remote machines (LAN/Tailscale)")
    print(f"  {scheme}://localhost:{args.port}/api/state    ← JSON state for dashboard")
    print(f"  {scheme}://localhost:{args.port}/status       ← Health check")
    if args.tls_cert:
        print(f"  TLS: enabled (cert {os.path.abspath(args.tls_cert)})")
    if bridge_server.AUTH_TOKEN:
        print("  Auth: Bearer token required (set via CLAUDE_BRIDGE_AUTH_TOKEN / --auth-token)")
    if bridge_server.RETENTION_DAYS > 0:
        print(f"  ⚠ Retention: messages older than {bridge_server.RETENTION_DAYS} day(s) "
              f"are DELETED (sweep every {bridge_server.RETENTION_SWEEP_SECONDS}s)")
    if bridge_server.AUDIT_ENABLED:
        print(f"  Audit log: enabled → {scheme}://localhost:{args.port}/api/audit")
    print(bar)
    sys.stdout.flush()

    bridge_server.db()  # initialize DB before serving
    uvicorn.run(
        bridge_server.app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.tls_cert,
        ssl_keyfile=args.tls_key,
    )
    return 0
