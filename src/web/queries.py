"""Requetes de lecture alimentant les pages du tableau de bord."""

import sqlite3

LIST_GAMES = """
SELECT
    g.appid,
    g.name,
    g.updated_at,
    g.cover,
    g.playtime_minutes,
    g.last_played,
    COUNT(a.api_name) AS total,
    COALESCE(SUM(a.unlocked), 0) AS unlocked
FROM games g
LEFT JOIN achievements a ON a.appid = g.appid
GROUP BY g.appid, g.name, g.updated_at, g.cover, g.playtime_minutes, g.last_played
-- Les jeux jamais lances (last_played NULL) ferment la marche.
ORDER BY g.last_played IS NULL, g.last_played DESC, g.name COLLATE NOCASE
"""

GET_ACHIEVEMENTS = """
SELECT api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time
FROM achievements
WHERE appid = ?
ORDER BY unlocked DESC, unlock_time ASC, name COLLATE NOCASE
"""

GET_GAME = """
SELECT appid, name, updated_at, cover, playtime_minutes, last_played
FROM games
WHERE appid = ?
"""


def _summarise(row: sqlite3.Row, total: int, unlocked: int) -> dict:
    """Champs communs a la liste et au detail d'un jeu."""
    return {
        "appid": row["appid"],
        "name": row["name"],
        "updated_at": row["updated_at"],
        "cover": row["cover"],
        "playtime_minutes": row["playtime_minutes"],
        "last_played": row["last_played"],
        "total": total,
        "unlocked": unlocked,
        "percent": round(unlocked * 100 / total) if total else 0,
    }


def list_games(conn: sqlite3.Connection) -> list[dict]:
    """Liste les jeux du plus recemment joue au plus ancien."""
    return [_summarise(row, row["total"], row["unlocked"]) for row in conn.execute(LIST_GAMES)]


def get_game(conn: sqlite3.Connection, appid: int) -> dict | None:
    """Retourne un jeu et ses succes, ou None s'il n'existe pas."""
    row = conn.execute(GET_GAME, (appid,)).fetchone()
    if row is None:
        return None

    achievements = [dict(a) for a in conn.execute(GET_ACHIEVEMENTS, (appid,))]
    game = _summarise(row, len(achievements), sum(a["unlocked"] for a in achievements))
    game["achievements"] = achievements
    return game
