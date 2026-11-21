#!/usr/bin/env python3
"""Claude Code statusLine command that reports Claude usage to Claude Bridge.

Claude Code pipes a JSON status to stdin. This prints one short line such as
``5h 42% | wk 17%`` and, at most once a minute, posts the rate-limit windows
to ``POST {CLAUDE_BRIDGE_URL}/api/participants/{name}/usage``.

Environment: CLAUDE_BRIDGE_URL, CLAUDE_BRIDGE_TOKEN (optional when the bridge
has no token), CLAUDE_BRIDGE_PARTICIPANT. Stdlib only, Python 3.9+. It never
raises: a status line must always render.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

THROTTLE_SECONDS = 60
TIMEOUT_SECONDS = 2
# Bridge window name, Claude Code rate_limits key, status-line label.
WINDOWS = (("session", "five_hour", "5h"), ("weekly", "seven_day", "wk"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_usage(status: Any) -> Optional[dict]:
    """The bridge usage body from a status, or None when no window is present."""
    limits = status.get("rate_limits") if isinstance(status, dict) else None
    if not isinstance(limits, dict):
        return None
    report = {}
    for name, key, _label in WINDOWS:
        window = limits.get(key)
        if isinstance(window, dict) and _is_number(window.get("used_percentage")):
            resets_at = window.get("resets_at")
            report[name] = {
                "used_pct": min(100.0, max(0.0, float(window["used_percentage"]))),
                "resets_at": resets_at if _is_number(resets_at) else None,
            }
    return report or None


def format_line(report: Optional[dict]) -> str:
    if not report:
        return "-"
    parts = [
        f"{label} {round(report[name]['used_pct'])}%"
        for name, _key, label in WINDOWS
        if name in report
    ]
    return " | ".join(parts)


def should_send(last_sent: Optional[float], now: float) -> bool:
    # A stamp from the future (clock change) must not block reports forever.
    return last_sent is None or not 0 <= now - last_sent < THROTTLE_SECONDS


def build_request(
    base_url: str, token: str, participant: str, report: dict
) -> urllib.request.Request:
    name = urllib.parse.quote(participant, safe="")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(
        f"{base_url.rstrip('/')}/api/participants/{name}/usage",
        data=json.dumps(report).encode("utf-8"),
        headers=headers,
        method="POST",
    )


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect must not carry the bearer token to another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_RefuseRedirect)


def stamp_dir() -> str:
    # Under the user's home, not the shared temp dir that other users can write.
    return os.path.join(os.path.expanduser("~"), ".cache", "claude-bridge")


def stamp_path(directory: str, participant: str) -> str:
    digest = hashlib.sha256(participant.encode("utf-8")).hexdigest()[:16]
    return os.path.join(directory, f"usage-{digest}.stamp")


def read_stamp(path: str) -> Optional[float]:
    try:
        with open(path, encoding="utf-8") as handle:
            return float(handle.read().strip())
    except (OSError, ValueError):
        return None


def write_stamp(path: str, now: float) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    # O_NOFOLLOW refuses a planted symlink; Windows has no such flag.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as handle:
        handle.write(str(now))


def report_usage(report: Optional[dict], env: dict, now: float) -> None:
    base_url = env.get("CLAUDE_BRIDGE_URL", "")
    participant = env.get("CLAUDE_BRIDGE_PARTICIPANT", "")
    if not (report and base_url and participant):
        return
    path = stamp_path(stamp_dir(), participant)
    if not should_send(read_stamp(path), now):
        return
    # Stamp first: a bridge that is down is then tried once a minute, not always.
    # No stamp, no send: else an unwritable home sends on every status refresh.
    write_stamp(path, now)
    request = build_request(base_url, env.get("CLAUDE_BRIDGE_TOKEN", ""), participant, report)
    OPENER.open(request, timeout=TIMEOUT_SECONDS).close()


def main() -> None:
    report = None
    try:
        report = parse_usage(json.load(sys.stdin))
    except Exception:
        pass
    print(format_line(report), flush=True)
    try:
        report_usage(report, dict(os.environ), time.time())
    except Exception:
        pass


if __name__ == "__main__":
    main()
