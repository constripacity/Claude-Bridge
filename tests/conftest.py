import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import server as bridge


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Give each test an isolated SQLite database."""
    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge, "DB_PATH", str(db_path))
    monkeypatch.setattr(bridge, "_conn", None)
    yield db_path
    if bridge._conn is not None:
        bridge._conn.close()
        monkeypatch.setattr(bridge, "_conn", None)
