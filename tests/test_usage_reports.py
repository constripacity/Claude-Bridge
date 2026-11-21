"""Usage reports: a participant's Claude rate-limit windows, posted over REST."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

import claude_bridge.server as bridge
from claude_bridge.participants import UsageWindow, parse_usage_report
from claude_bridge.timestamps import utc_timestamp
from claude_bridge.validation import BridgeValidationError

from .legacy_schema import create_pre_usage_database

TOKEN = "dummy-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
# Reset times relative to the real clock, as the endpoint checks them against server time.
SESSION_RESET = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=3)
WEEKLY_RESET = SESSION_RESET.astimezone(timezone(timedelta(hours=2))) + timedelta(days=5)
REPORT = {
    "session": {"used_pct": 42, "resets_at": int(SESSION_RESET.timestamp())},
    "weekly": {"used_pct": 17.5, "resets_at": WEEKLY_RESET.isoformat()},
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
        utc_timestamp(SESSION_RESET),
        17.5,
        utc_timestamp(WEEKLY_RESET),
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
        ({"session": {"used_pct": 1, "used_percentage": 1}}, "session.used_percentage"),
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


HOUR = 3600
DAY = 24 * HOUR


@pytest.mark.parametrize(
    "resets_at",
    [1, time.time() - 2 * DAY, time.time() + 9 * DAY],
    ids=["1970", "2_days_ago", "9_days_ahead"],
)
def test_implausible_reset_time_is_out_of_range(client, resets_at):
    r = post_usage(client, "w1", {"weekly": {"used_pct": 1, "resets_at": resets_at}})
    assert r.status_code == 400
    assert (r.json()["field"], r.json()["code"]) == ("weekly.resets_at", "out_of_range")
    assert stored_usage("w1") is None


@pytest.mark.parametrize(
    "resets_at", [time.time() + HOUR, time.time() + 6 * DAY], ids=["1_hour_ahead", "6_days_ahead"]
)
def test_plausible_reset_time_is_accepted(client, resets_at):
    r = post_usage(client, "w1", {"weekly": {"used_pct": 1, "resets_at": resets_at}})
    assert r.status_code == 200


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


def test_empty_report_has_no_windows():
    report = parse_usage_report({})
    assert report.session is None and report.weekly is None


def test_window_without_reset_time_is_allowed():
    report = parse_usage_report({"session": {"used_pct": 0, "resets_at": None}})
    assert report.session == UsageWindow(used_pct=0.0, resets_at=None)


FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "resets_at",
    [
        FIXED_NOW - timedelta(days=1, seconds=1),
        FIXED_NOW + timedelta(days=8, seconds=1),
    ],
)
def test_reset_time_just_outside_the_window_is_out_of_range(resets_at):
    with pytest.raises(BridgeValidationError) as err:
        parse_usage_report(
            {"session": {"used_pct": 1, "resets_at": resets_at.isoformat()}}, now=FIXED_NOW
        )
    assert (err.value.field, err.value.code) == ("session.resets_at", "out_of_range")


@pytest.mark.parametrize("delta", [timedelta(days=-1), timedelta(days=8)])
def test_reset_time_on_the_window_edge_is_accepted(delta):
    body = {"session": {"used_pct": 1, "resets_at": (FIXED_NOW + delta).timestamp()}}
    report = parse_usage_report(body, now=FIXED_NOW)
    assert report.session.resets_at == utc_timestamp(FIXED_NOW + delta)


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
