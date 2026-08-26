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


def test_games_table_has_presentation_columns(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
    assert {"cover", "playtime_minutes", "last_played"} <= columns


def test_init_db_migrates_a_legacy_games_table_without_losing_rows(tmp_path):
    # Base creee par une version anterieure : trois colonnes seulement.
    conn = connect(tmp_path / "legacy.db")
    conn.executescript(
        """
        CREATE TABLE games (
            appid       INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        INSERT INTO games (appid, name, updated_at) VALUES (1245620, 'Elden Ring', 'hier');
        """
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
    assert {"cover", "playtime_minutes", "last_played"} <= columns
    row = conn.execute("SELECT * FROM games").fetchone()
    assert row["name"] == "Elden Ring"  # la donnee existante survit
    assert row["cover"] is None  # les nouvelles colonnes demarrent vides


def test_migration_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    init_db(conn)
    init_db(conn)  # ne doit pas lever, meme sur une base deja migree
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(games)")]
    assert columns.count("cover") == 1


def test_foreign_keys_are_enforced(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO achievements "
            "(appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time) "
            "VALUES (404, 'ACH01', 'A', '', '', '', 0, 0, NULL)"
        )
