"""Validated runtime configuration for Claude Bridge.

The v0.9.x server read and converted environment variables throughout
``server.py``.  A typo such as ``CLAUDE_BRIDGE_MAX_SSE=many`` therefore caused
an opaque import-time traceback, while values such as ``AUDIT_LOG=false`` were
truthy.  These helpers centralise parsing and produce actionable errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


class ConfigurationError(ValueError):
    """Raised when a runtime setting is invalid."""


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} must be one of true/false, yes/no, on/off, or 1/0"
    )


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.environ.get(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigurationError(f"{name} must be at most {maximum}")
    return value


def env_csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    )


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: str
    auth_token: str | None
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    allow_unauthenticated_network: bool
    max_request_bytes: int
    max_message_bytes: int
    max_sse_subscribers: int
    max_sse_per_channel: int
    sse_replay_limit: int
    retention_days: int
    retention_sweep_seconds: int
    audit_enabled: bool
    audit_retention_days: int
    no_dashboard: bool
    streamable_http_stateless: bool
    session_ttl_seconds: int
    event_poll_ms: int
    event_retention_days: int

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("CLAUDE_BRIDGE_AUTH_TOKEN")
        token = token.strip() if token else None
        return cls(
            db_path=os.environ.get("CLAUDE_BRIDGE_DB", "claude-bridge.db"),
            auth_token=token,
            cors_origins=env_csv("CLAUDE_BRIDGE_CORS_ORIGIN"),
            trusted_hosts=env_csv("CLAUDE_BRIDGE_TRUSTED_HOSTS"),
            allow_unauthenticated_network=env_bool(
                "CLAUDE_BRIDGE_ALLOW_UNAUTHENTICATED_NETWORK", False
            ),
            max_request_bytes=env_int(
                "CLAUDE_BRIDGE_MAX_REQUEST_BYTES", 256 * 1024, minimum=1024
            ),
            max_message_bytes=env_int(
                "CLAUDE_BRIDGE_MAX_MESSAGE_BYTES",
                128 * 1024,
                minimum=1,
                maximum=128 * 1024,
            ),
            max_sse_subscribers=env_int(
                "CLAUDE_BRIDGE_MAX_SSE", 100, minimum=1
            ),
            max_sse_per_channel=env_int(
                "CLAUDE_BRIDGE_MAX_SSE_PER_CHANNEL", 25, minimum=1
            ),
            sse_replay_limit=env_int(
                "CLAUDE_BRIDGE_SSE_REPLAY_LIMIT", 500, minimum=1, maximum=10000
            ),
            retention_days=env_int(
                "CLAUDE_BRIDGE_RETENTION_DAYS", 0, minimum=0
            ),
            retention_sweep_seconds=env_int(
                "CLAUDE_BRIDGE_RETENTION_SWEEP_SECONDS", 3600, minimum=10
            ),
            audit_enabled=env_bool("CLAUDE_BRIDGE_AUDIT_LOG", False),
            audit_retention_days=env_int(
                "CLAUDE_BRIDGE_AUDIT_RETENTION_DAYS", 90, minimum=1
            ),
            no_dashboard=env_bool("CLAUDE_BRIDGE_NO_DASHBOARD", False),
            streamable_http_stateless=env_bool(
                "CLAUDE_BRIDGE_STATELESS_HTTP", False
            ),
            session_ttl_seconds=env_int(
                "CLAUDE_BRIDGE_SESSION_TTL_SECONDS", 8 * 60 * 60, minimum=60
            ),
            event_poll_ms=env_int(
                "CLAUDE_BRIDGE_EVENT_POLL_MS", 500, minimum=50, maximum=10_000
            ),
            event_retention_days=env_int(
                "CLAUDE_BRIDGE_EVENT_RETENTION_DAYS", 7, minimum=1
            ),
        )
