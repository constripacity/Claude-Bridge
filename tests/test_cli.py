"""Tests for the `claude-bridge` CLI entry point — flag parsing, TLS validation,
and env-var wiring. The actual `uvicorn.run` is monkeypatched so no socket is
bound; we only assert what the CLI hands it."""

import os
import subprocess
import sys

import claude_bridge.cli as cli


# ── Regression: config-init ordering (the v0.9.1 auth-bypass bug) ────────────
# These run in subprocesses because sys.modules is process-global and other
# tests in the suite import claude_bridge.server, which would pollute an
# in-process check.


def test_importing_package_does_not_import_server():
    """Importing the package (which the console entry point does to read
    --version) must NOT import the server. If it does, the server snapshots its
    env-derived config before cli.main() applies the flags, silently turning
    --auth-token/--db/--no-dashboard/etc. into no-ops."""
    code = (
        "import claude_bridge, sys; "
        "assert 'claude_bridge.server' not in sys.modules, "
        "'server imported at package import — CLI flags would be no-ops'"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_cli_flag_env_is_seen_by_the_server():
    """End-to-end ordering: the package is imported first (as the --version path
    does), then the auth-token env var is set (as cli.main() does for
    --auth-token), then the server is imported. The server must pick the token
    up — proving the flag is effective."""
    code = (
        "import os, sys\n"
        "import claude_bridge\n"
        "assert 'claude_bridge.server' not in sys.modules\n"
        "os.environ['CLAUDE_BRIDGE_AUTH_TOKEN'] = 'secret'\n"
        "os.environ['CLAUDE_BRIDGE_DB'] = ':memory:'\n"
        "import claude_bridge.server as s\n"
        "assert s.AUTH_TOKEN == 'secret', 'auth-token flag ineffective (config frozen too early)'\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── TLS validation (no server start needed) ─────────────────────────────────


def test_tls_cert_without_key_errors():
    assert cli.main(["--tls-cert", "only-cert.pem"]) == 2


def test_tls_key_without_cert_errors():
    assert cli.main(["--tls-key", "only-key.pem"]) == 2


def test_tls_missing_file_errors(tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_text("dummy")
    # cert exists, key path doesn't → file-not-found error.
    assert cli.main(["--tls-cert", str(cert), "--tls-key", str(tmp_path / "missing.pem")]) == 2


def test_tls_cert_and_key_passed_to_uvicorn(tmp_path, monkeypatch, fresh_db):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("dummy")
    key.write_text("dummy")

    import uvicorn
    captured: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))

    rc = cli.main(["--tls-cert", str(cert), "--tls-key", str(key), "--port", "0"])

    assert rc == 0
    assert captured["ssl_certfile"] == str(cert)
    assert captured["ssl_keyfile"] == str(key)


def test_no_tls_passes_none_to_uvicorn(monkeypatch, fresh_db):
    import uvicorn
    captured: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))

    rc = cli.main(["--port", "0"])

    assert rc == 0
    assert captured["ssl_certfile"] is None
    assert captured["ssl_keyfile"] is None


# ── Retention / audit env wiring ────────────────────────────────────────────


def test_retention_days_flag_sets_env(monkeypatch, fresh_db):
    monkeypatch.delenv("CLAUDE_BRIDGE_RETENTION_DAYS", raising=False)
    monkeypatch.setattr(cli, "_run_http", lambda args: 0)

    assert cli.main(["--retention-days", "5"]) == 0
    assert os.environ["CLAUDE_BRIDGE_RETENTION_DAYS"] == "5"
    os.environ.pop("CLAUDE_BRIDGE_RETENTION_DAYS", None)


def test_audit_log_flag_sets_env(monkeypatch, fresh_db):
    monkeypatch.delenv("CLAUDE_BRIDGE_AUDIT_LOG", raising=False)
    monkeypatch.setattr(cli, "_run_http", lambda args: 0)

    assert cli.main(["--audit-log"]) == 0
    assert os.environ["CLAUDE_BRIDGE_AUDIT_LOG"] == "1"
    os.environ.pop("CLAUDE_BRIDGE_AUDIT_LOG", None)
