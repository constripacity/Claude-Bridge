"""The Claude Code status-line script that reports usage to the bridge."""

from __future__ import annotations

import http.server
import importlib.util
import io
import json
import os
import threading
import urllib.error
from pathlib import Path

import pytest

from claude_bridge.participants import parse_usage_report

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claude-statusline-usage.py"
_spec = importlib.util.spec_from_file_location("claude_statusline_usage", SCRIPT)
statusline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(statusline)

FULL_STATUS = {
    "model": {"display_name": "Opus"},
    "rate_limits": {
        "five_hour": {"used_percentage": 42.4, "resets_at": 1767225600},
        "seven_day": {"used_percentage": 17, "resets_at": 1767744000},
    },
}


def test_parse_usage_maps_both_windows():
    assert statusline.parse_usage(FULL_STATUS) == {
        "session": {"used_pct": 42.4, "resets_at": 1767225600},
        "weekly": {"used_pct": 17.0, "resets_at": 1767744000},
    }


def test_parse_usage_keeps_a_window_that_is_present_alone():
    status = {"rate_limits": {"seven_day": {"used_percentage": 5}}}
    assert statusline.parse_usage(status) == {
        "weekly": {"used_pct": 5.0, "resets_at": None}
    }


@pytest.mark.parametrize(
    "status",
    [
        {},
        {"rate_limits": None},
        {"rate_limits": {}},
        {"rate_limits": {"five_hour": {"used_percentage": "42"}}},
        {"rate_limits": {"five_hour": {"used_percentage": True}}},
        [],
    ],
)
def test_parse_usage_without_windows_is_none(status):
    assert statusline.parse_usage(status) is None


def test_parse_usage_clamps_the_percent():
    status = {"rate_limits": {"five_hour": {"used_percentage": 100.4}}}
    assert statusline.parse_usage(status)["session"]["used_pct"] == 100.0


def test_parsed_report_is_a_valid_bridge_body():
    report = parse_usage_report(statusline.parse_usage(FULL_STATUS))
    assert report.session.used_pct == 42.4
    assert report.weekly.resets_at == "2026-01-07T00:00:00.000000Z"


@pytest.mark.parametrize(
    ("report", "line"),
    [
        (None, "-"),
        ({"session": {"used_pct": 42.4}, "weekly": {"used_pct": 17.0}}, "5h 42% | wk 17%"),
        ({"weekly": {"used_pct": 99.6}}, "wk 100%"),
    ],
)
def test_format_line(report, line):
    assert statusline.format_line(report) == line


@pytest.mark.parametrize(
    ("last_sent", "now", "expected"),
    [
        (None, 1000.0, True),
        (1000.0, 1059.9, False),
        (1000.0, 1060.0, True),
        (2000.0, 1000.0, True),
    ],
)
def test_should_send_at_most_once_a_minute(last_sent, now, expected):
    assert statusline.should_send(last_sent, now) is expected


def test_build_request_quotes_the_name_and_sends_the_token():
    report = {"weekly": {"used_pct": 1.0, "resets_at": None}}
    request = statusline.build_request("http://bridge:8765/", "tok", "win/a b", report)
    assert request.full_url == "http://bridge:8765/api/participants/win%2Fa%20b/usage"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer tok"
    assert json.loads(request.data) == report


def test_build_request_without_token_sends_no_auth_header():
    request = statusline.build_request("http://bridge", "", "w1", {})
    assert request.get_header("Authorization") is None


ENV = {"CLAUDE_BRIDGE_URL": "http://bridge", "CLAUDE_BRIDGE_PARTICIPANT": "w1"}
REPORT = {"session": {"used_pct": 1.0, "resets_at": None}}


@pytest.fixture
def sent(tmp_path, monkeypatch):
    monkeypatch.setattr(statusline, "stamp_dir", lambda: str(tmp_path / "stamps"))
    requests = []

    class _Response:
        def close(self):
            pass

    class _Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return _Response()

    monkeypatch.setattr(statusline, "OPENER", _Opener())
    return requests


def test_report_usage_throttles_by_the_stamp_file(sent):
    statusline.report_usage(REPORT, ENV, now=1000.0)
    statusline.report_usage(REPORT, ENV, now=1030.0)
    statusline.report_usage(REPORT, ENV, now=1061.0)
    assert len(sent) == 2
    assert sent[0][1] == statusline.TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("report", "env"),
    [
        (None, ENV),
        (REPORT, {"CLAUDE_BRIDGE_URL": "http://bridge"}),
        (REPORT, {"CLAUDE_BRIDGE_PARTICIPANT": "w1"}),
    ],
)
def test_report_usage_sends_nothing_without_data_or_config(sent, report, env):
    statusline.report_usage(report, env, now=1000.0)
    assert sent == []


def test_main_never_raises_and_prints_a_line(monkeypatch, capsys):
    def bridge_down(*_args):
        raise OSError("down")

    monkeypatch.setattr(statusline.sys, "stdin", io.StringIO("not json"))
    monkeypatch.setattr(statusline, "report_usage", bridge_down)
    statusline.main()
    assert capsys.readouterr().out.strip() == "-"


def test_stamp_dir_is_under_the_user_home(monkeypatch, tmp_path):
    monkeypatch.setattr(statusline.os.path, "expanduser", lambda _p: str(tmp_path))
    assert statusline.stamp_dir() == os.path.join(str(tmp_path), ".cache", "claude-bridge")


def test_write_stamp_creates_its_dir_and_round_trips(tmp_path):
    path = str(tmp_path / "new" / "s.stamp")
    statusline.write_stamp(path, 1234.5)
    assert statusline.read_stamp(path) == 1234.5


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="POSIX only")
def test_write_stamp_refuses_a_symlink(tmp_path):
    target = tmp_path / "victim"
    target.write_text("keep")
    link = tmp_path / "s.stamp"
    link.symlink_to(target)
    with pytest.raises(OSError):
        statusline.write_stamp(str(link), 1.0)
    assert target.read_text() == "keep"


@pytest.fixture
def redirecting_server():
    hits = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append((self.path, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", hits
    server.shutdown()
    server.server_close()


def test_opener_does_not_follow_a_redirect_with_the_token(redirecting_server):
    base_url, hits = redirecting_server
    request = statusline.build_request(base_url, "tok", "w1", REPORT)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        statusline.OPENER.open(request, timeout=statusline.TIMEOUT_SECONDS)
    excinfo.value.close()
    assert excinfo.value.code == 302
    assert [path for path, _auth in hits] == ["/api/participants/w1/usage"]
