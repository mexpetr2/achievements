"""Schema SQLite et acces a la base de l'application web."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid       INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS achievements (
    appid        INTEGER NOT NULL REFERENCES games(appid) ON DELETE CASCADE,
    api_name     TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    icon         TEXT NOT NULL DEFAULT '',
    icon_gray    TEXT NOT NULL DEFAULT '',
    hidden       INTEGER NOT NULL DEFAULT 0,
    unlocked     INTEGER NOT NULL DEFAULT 0,
    unlock_time  TEXT,
    PRIMARY KEY (appid, api_name)
);

CREATE INDEX IF NOT EXISTS idx_achievements_unlocked
    ON achievements(unlocked, unlock_time DESC);

CREATE TABLE IF NOT EXISTS imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    processed_at  TEXT NOT NULL,
    status        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les cles etrangeres actives."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Cree les tables si elles n'existent pas."""
    conn.executescript(SCHEMA)
    conn.commit()
