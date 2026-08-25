import sqlite3

import pytest

from web.db import connect, init_db


def test_init_db_creates_expected_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"games", "achievements", "imports"} <= tables


def test_init_db_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    init_db(conn)  # ne doit pas lever
    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 0


def test_rows_are_accessible_by_column_name(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO games (appid, name, updated_at) VALUES (?, ?, ?)",
        (1245620, "Elden Ring", "2026-08-24T22:10:00+00:00"),
    )
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"


def test_achievements_primary_key_rejects_duplicates(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    conn.execute("INSERT INTO games (appid, name, updated_at) VALUES (1, 'X', 'now')")
    insert = (
        "INSERT INTO achievements "
        "(appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time) "
        "VALUES (1, 'ACH01', 'A', '', '', '', 0, 0, NULL)"
    )
    conn.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert)


def test_foreign_keys_are_enforced(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO achievements "
            "(appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time) "
            "VALUES (404, 'ACH01', 'A', '', '', '', 0, 0, NULL)"
        )
