"""Requetes de lecture alimentant les pages du tableau de bord."""

import sqlite3

LIST_GAMES = """
SELECT
    g.appid,
    g.name,
    g.updated_at,
    COUNT(a.api_name) AS total,
    COALESCE(SUM(a.unlocked), 0) AS unlocked
FROM games g
LEFT JOIN achievements a ON a.appid = g.appid
GROUP BY g.appid, g.name, g.updated_at
"""

GET_ACHIEVEMENTS = """
SELECT api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time
FROM achievements
WHERE appid = ?
ORDER BY unlocked DESC, unlock_time ASC, name COLLATE NOCASE
"""

RECENT_UNLOCKS = """
SELECT a.appid, a.api_name, a.name, a.icon, a.unlock_time, g.name AS game_name
FROM achievements a
JOIN games g ON g.appid = a.appid
WHERE a.unlocked = 1 AND a.unlock_time IS NOT NULL
ORDER BY a.unlock_time DESC
LIMIT ?
"""


def list_games(conn: sqlite3.Connection) -> list[dict]:
    """Liste les jeux avec leur taux de completion, du plus complet au moins complet."""
    games = []
    for row in conn.execute(LIST_GAMES):
        total = row["total"]
        unlocked = row["unlocked"]
        games.append(
            {
                "appid": row["appid"],
                "name": row["name"],
                "updated_at": row["updated_at"],
                "total": total,
                "unlocked": unlocked,
                "percent": round(unlocked * 100 / total) if total else 0,
            }
        )
    games.sort(key=lambda g: (-g["percent"], g["name"].lower()))
    return games


def get_game(conn: sqlite3.Connection, appid: int) -> dict | None:
    """Retourne un jeu et ses succes, ou None s'il n'existe pas."""
    row = conn.execute(
        "SELECT appid, name, updated_at FROM games WHERE appid = ?", (appid,)
    ).fetchone()
    if row is None:
        return None

    achievements = [dict(a) for a in conn.execute(GET_ACHIEVEMENTS, (appid,))]
    unlocked = sum(a["unlocked"] for a in achievements)
    total = len(achievements)
    return {
        "appid": row["appid"],
        "name": row["name"],
        "updated_at": row["updated_at"],
        "total": total,
        "unlocked": unlocked,
        "percent": round(unlocked * 100 / total) if total else 0,
        "achievements": achievements,
    }


def recent_unlocks(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Retourne les derniers succes debloques, tous jeux confondus."""
    return [dict(row) for row in conn.execute(RECENT_UNLOCKS, (limit,))]
