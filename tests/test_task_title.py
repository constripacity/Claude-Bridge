"""Task titles: a short label per task, explicit or derived from the payload."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

import claude_bridge.server as bridge
from claude_bridge.taskqueue import DERIVED_TITLE_CHARS, derive_task_title
from claude_bridge.validation import BridgeValidationError, validate_title

from .legacy_schema import create_v130_database


async def call(name, args):
    return await bridge.dispatch_tool(name, args, structured=True)


async def data(name, args):
    _content, result = await call(name, args)
    return result


async def enqueue(**args):
    return await data(
        "bridge_enqueue", {"channel": "jobs", "enqueued_by": "lead", **args}
    )


async def claim(channel="jobs"):
    return await call("bridge_claim", {"channel": channel, "consumer": "w1"})


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("fix the build", "fix the build"),
        ("\n  \n  first   line\t here \nsecond", "first line here"),
        ('{"title": "From title", "task": "From task"}', "From title"),
        ('{"title": " ", "task": "From task"}', "From task"),
        ('{"title": 5, "action": "x"}', '{"title": 5, "action": "x"}'),
        ('["title"]', '["title"]'),
        ("", None),
        ("   \n\t", None),
        ("\x1b[31mred\x00 alert\x7f", "[31mred alert"),
        ('{"title": "a\\u0000b\\tc"}', "ab c"),
        ("\x1b\n\x00 \nreal", "real"),
    ],
)
def test_derive_task_title(payload, expected):
    assert derive_task_title(payload) == expected


def test_derived_title_passes_title_validation():
    title = derive_task_title("\x1b[1mbold\x07 job\x00")
    assert validate_title(title) == title


def test_derived_title_is_cut_with_an_ellipsis():
    title = derive_task_title("x" * 200)
    assert len(title) == DERIVED_TITLE_CHARS and title.endswith("…")
    assert derive_task_title("y" * DERIVED_TITLE_CHARS) == "y" * DERIVED_TITLE_CHARS


@pytest.mark.asyncio
async def test_enqueue_derives_a_title_and_claim_shows_it(fresh_db):
    queued = await enqueue(payload={"task": "Run the tests", "scope": "all"})
    assert queued["title"] == "Run the tests"

    content, claimed = await claim()
    assert claimed["task"]["title"] == "Run the tests"
    assert "title: Run the tests" in content[0].text


@pytest.mark.asyncio
async def test_explicit_title_wins_and_shows_in_the_task_list(fresh_db):
    queued = await enqueue(content="long text", title="Short")
    assert queued["title"] == "Short"

    content, listing = await call("bridge_tasks", {"channel": "jobs"})
    assert listing["tasks"][0]["title"] == "Short"
    assert "· Short" in content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["", " padded", "x" * 121, "two\nlines", 7])
async def test_invalid_title_is_rejected(fresh_db, title):
    with pytest.raises(BridgeValidationError) as excinfo:
        await enqueue(content="work", title=title)
    assert excinfo.value.field == "title"


@pytest.mark.asyncio
async def test_replace_derives_from_the_new_payload_unless_a_title_is_given(fresh_db):
    task_id = (await enqueue(content="old work", title="Old"))["task_id"]
    args = {"channel": "jobs", "task_id": task_id, "sender": "lead"}

    replaced = await data("bridge_replace", {**args, "content": "new work"})
    assert replaced["title"] == "new work"
    replaced = await data("bridge_replace", {**args, "content": "newer", "title": "Mine"})
    assert replaced["title"] == "Mine"


@pytest.mark.asyncio
async def test_legacy_database_gains_the_title_column(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    create_v130_database(str(db_path), pending_task_id="tsk_legacy")
    monkeypatch.setattr(bridge, "DB_PATH", str(db_path))
    monkeypatch.setattr(bridge, "_conn", None)
    try:
        _content, claimed = await claim(channel="old")
        assert claimed["task"]["task_id"] == "tsk_legacy"
        assert claimed["task"]["title"] is None
    finally:
        bridge._conn.close()
        monkeypatch.setattr(bridge, "_conn", None)
    with closing(sqlite3.connect(db_path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    assert "title" in columns


@pytest.mark.asyncio
async def test_tool_listing_declares_the_title_input():
    tools = {tool.name: tool for tool in await bridge.list_tools()}
    for name in ("bridge_enqueue", "bridge_replace"):
        assert tools[name].inputSchema["properties"]["title"]["maxLength"] == 120
