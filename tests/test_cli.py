"""Tests for the `claude-bridge` CLI entry point — flag parsing, TLS validation,
and env-var wiring. The actual `uvicorn.run` is monkeypatched so no socket is
bound; we only assert what the CLI hands it."""

import os

import claude_bridge.cli as cli


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
