"""Usage reports: a participant's Claude rate-limit windows, posted over REST."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge
from claude_bridge.participants import UsageWindow, parse_usage_report
from claude_bridge.validation import BridgeValidationError

from .legacy_schema import create_pre_usage_database

TOKEN = "dummy-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
REPORT = {
    "session": {"used_pct": 42, "resets_at": 1767225600},
    "weekly": {"used_pct": 17.5, "resets_at": "2026-01-08T00:00:00+02:00"},
}


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.setattr(bridge, "AUTH_TOKEN", TOKEN)
    return TestClient(bridge.app, base_url="http://localhost")


def stored_usage(name):
    row = bridge.db().execute(
        "SELECT usage_session_pct, usage_session_resets_at, usage_weekly_pct, "
        "usage_weekly_resets_at, usage_reported_at, last_seen "
        "FROM participants WHERE name = ?",
        (name,),
    ).fetchone()
    return None if row is None else tuple(row)


def post_usage(client, name, body, headers=AUTH):
    return client.post(f"/api/participants/{name}/usage", json=body, headers=headers)


def test_usage_report_requires_the_token(client):
    assert post_usage(client, "w1", REPORT, headers={}).status_code == 401
    assert stored_usage("w1") is None


def test_usage_report_upserts_and_normalizes_reset_times(client):
    r = post_usage(client, "w1", REPORT)
    assert r.status_code == 200
    reported_at = r.json()["usage_reported_at"]
    assert r.json()["name"] == "w1" and reported_at.endswith("Z")

    assert stored_usage("w1") == (
        42.0,
        "2026-01-01T00:00:00.000000Z",
        17.5,
        "2026-01-07T22:00:00.000000Z",
        reported_at,
        reported_at,
    )


def test_a_new_report_replaces_the_old_one_and_keeps_the_task(client):
    bridge.db().execute(
        "INSERT INTO participants (name, last_seen, current_channel, current_task_id) "
        "VALUES ('w1', '2000-01-01T00:00:00.000000Z', 'jobs', 'tsk_1')"
    )
    bridge.db().commit()
    post_usage(client, "w1", REPORT)
    assert post_usage(client, "w1", {"weekly": {"used_pct": 3}}).status_code == 200

    session_pct, session_reset, weekly_pct, weekly_reset, *_ = stored_usage("w1")
    assert (session_pct, session_reset, weekly_pct, weekly_reset) == (None, None, 3.0, None)
    task = bridge.db().execute(
        "SELECT current_channel, current_task_id FROM participants WHERE name = 'w1'"
    ).fetchone()
    assert tuple(task) == ("jobs", "tsk_1")


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ([], "body"),
        ({"daily": {"used_pct": 1}}, "daily"),
        ({"session": 5}, "session"),
        ({"session": {}}, "session.used_pct"),
        ({"session": {"used_pct": "5"}}, "session.used_pct"),
        ({"session": {"used_pct": True}}, "session.used_pct"),
        ({"session": {"used_pct": 100.5}}, "session.used_pct"),
        ({"session": {"used_pct": -1}}, "session.used_pct"),
        ({"weekly": {"used_pct": 1, "resets_at": "soon"}}, "weekly.resets_at"),
        ({"weekly": {"used_pct": 1, "resets_at": "2026-01-01T00:00:00"}}, "weekly.resets_at"),
        ({"weekly": {"used_pct": 1, "resets_at": 1e30}}, "weekly.resets_at"),
        ({"weekly": {"used_pct": 1, "resets_at": "9999-12-31T23:59:59-01:00"}}, "weekly.resets_at"),
        ({"weekly": {"used_pct": 1, "resets_at": "0001-01-01T00:00:00+01:00"}}, "weekly.resets_at"),
        ({"weekly": {"used_pct": 1, "resets_at": [1]}}, "weekly.resets_at"),
    ],
)
def test_bad_usage_report_is_a_400_naming_the_field(client, body, field):
    r = post_usage(client, "w1", body)
    assert r.status_code == 400
    assert r.json()["field"] == field
    assert stored_usage("w1") is None


def test_bad_participant_name_is_a_400(client):
    r = post_usage(client, "%20padded", REPORT)
    assert r.status_code == 400 and r.json()["field"] == "name"


def test_invalid_json_is_a_400(client):
    r = client.post(
        "/api/participants/w1/usage",
        content=b"{not json",
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_usage_report_needs_a_json_content_type(client):
    r = client.post(
        "/api/participants/w1/usage", content=b"{}", headers={**AUTH, "Content-Type": "text/plain"}
    )
    assert r.status_code == 415


def test_empty_report_clears_the_usage():
    report = parse_usage_report({})
    assert report.session is None and report.weekly is None


def test_window_without_reset_time_is_allowed():
    report = parse_usage_report({"session": {"used_pct": 0, "resets_at": None}})
    assert report.session == UsageWindow(used_pct=0.0, resets_at=None)


def test_nan_percent_is_rejected():
    with pytest.raises(BridgeValidationError):
        parse_usage_report({"session": {"used_pct": float("nan")}})


def test_pre_usage_participants_table_gains_the_usage_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    create_pre_usage_database(str(db_path), participant="veteran")
    monkeypatch.setattr(bridge, "DB_PATH", str(db_path))
    monkeypatch.setattr(bridge, "_conn", None)
    monkeypatch.setattr(bridge, "AUTH_TOKEN", TOKEN)
    try:
        client = TestClient(bridge.app, base_url="http://localhost")
        assert post_usage(client, "veteran", REPORT).status_code == 200
        assert stored_usage("veteran")[0] == 42.0
    finally:
        bridge._conn.close()
        monkeypatch.setattr(bridge, "_conn", None)


def test_a_name_with_a_slash_can_report(client):
    r = post_usage(client, "team%2Fw1", REPORT)
    assert r.status_code == 200 and r.json()["name"] == "team/w1"
    assert stored_usage("team/w1")[0] == 42.0
