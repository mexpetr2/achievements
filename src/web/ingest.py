"""Ingestion des exports JSON de l'extracteur dans SQLite."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class InvalidExportError(ValueError):
    """Leve quand un fichier d'export ne respecte pas le format attendu."""


UPSERT_GAME = """
INSERT INTO games (appid, name, updated_at, cover, playtime_minutes, last_played)
VALUES (:appid, :name, :updated_at, :cover, :playtime_minutes, :last_played)
ON CONFLICT(appid) DO UPDATE SET
    name = excluded.name,
    updated_at = excluded.updated_at,
    cover = excluded.cover,
    -- Un export plus ancien ou incomplet ne doit pas effacer une valeur connue.
    playtime_minutes = COALESCE(excluded.playtime_minutes, games.playtime_minutes),
    last_played = COALESCE(excluded.last_played, games.last_played)
"""

# Un succes debloque le reste : on ne repasse jamais unlocked de 1 a 0.
UPSERT_ACHIEVEMENT = """
INSERT INTO achievements
    (appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time,
     global_percent)
VALUES
    (:appid, :api_name, :name, :description, :icon, :icon_gray, :hidden, :unlocked, :unlock_time,
     :global_percent)
ON CONFLICT(appid, api_name) DO UPDATE SET
    name = excluded.name,
    description = excluded.description,
    icon = excluded.icon,
    icon_gray = excluded.icon_gray,
    hidden = excluded.hidden,
    -- Un export sans raretee (mode hors ligne) ne doit pas effacer la valeur connue.
    global_percent = COALESCE(excluded.global_percent, achievements.global_percent),
    unlocked = MAX(achievements.unlocked, excluded.unlocked),
    unlock_time = COALESCE(achievements.unlock_time, excluded.unlock_time)
"""


def ingest_export(conn: sqlite3.Connection, payload: dict) -> dict:
    """Insere ou met a jour le contenu d'un export. Transaction tout-ou-rien."""
    games = payload.get("games")
    if not isinstance(games, list):
        raise InvalidExportError("export invalide : cle 'games' absente ou mal typee")

    updated_at = str(payload.get("exported_at") or datetime.now(UTC).isoformat())
    game_count = 0
    achievement_count = 0

    try:
        with conn:  # rollback automatique si une exception remonte
            for game in games:
                if not isinstance(game, dict) or not isinstance(game.get("appid"), int):
                    raise InvalidExportError("export invalide : jeu sans appid entier")

                appid = game["appid"]
                playtime = game.get("playtime_minutes")
                conn.execute(
                    UPSERT_GAME,
                    {
                        "appid": appid,
                        "name": str(game.get("name") or f"App {appid}"),
                        "updated_at": updated_at,
                        "cover": str(game.get("cover") or ""),
                        "playtime_minutes": playtime if isinstance(playtime, int) else None,
                        "last_played": game.get("last_played") or None,
                    },
                )
                game_count += 1

                for ach in game.get("achievements") or []:
                    if not isinstance(ach, dict) or not ach.get("api_name"):
                        raise InvalidExportError(
                            f"export invalide : succes sans api_name (jeu {appid})"
                        )
                    conn.execute(
                        UPSERT_ACHIEVEMENT,
                        {
                            "appid": appid,
                            "api_name": str(ach["api_name"]),
                            "name": str(ach.get("name") or ach["api_name"]),
                            "description": str(ach.get("description") or ""),
                            "icon": str(ach.get("icon") or ""),
                            "icon_gray": str(ach.get("icon_gray") or ""),
                            "hidden": int(bool(ach.get("hidden"))),
                            "unlocked": int(bool(ach.get("unlocked"))),
                            "unlock_time": ach.get("unlock_time"),
                            "global_percent": (
                                float(ach["global_percent"])
                                if isinstance(ach.get("global_percent"), (int, float))
                                else None
                            ),
                        },
                    )
                    achievement_count += 1
    except sqlite3.DatabaseError as error:
        raise InvalidExportError(f"echec de l'ecriture en base : {error}") from error

    return {"games": game_count, "achievements": achievement_count}


def _record_import(conn: sqlite3.Connection, filename: str, status: str, detail: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO imports (filename, processed_at, status, detail) VALUES (?, ?, ?, ?)",
            (filename, datetime.now(UTC).isoformat(), status, detail),
        )


def ingest_file(conn: sqlite3.Connection, path: Path) -> dict:
    """Lit et ingere un fichier d'export, en journalisant le resultat."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        _record_import(conn, path.name, "erreur", f"JSON illisible : {error}")
        raise InvalidExportError(f"JSON illisible dans {path.name} : {error}") from error
    except OSError as error:
        _record_import(conn, path.name, "erreur", f"lecture impossible : {error}")
        raise InvalidExportError(f"lecture impossible de {path.name} : {error}") from error

    try:
        result = ingest_export(conn, payload)
    except InvalidExportError as error:
        _record_import(conn, path.name, "erreur", str(error))
        raise

    _record_import(
        conn, path.name, "ok", f"{result['games']} jeux, {result['achievements']} succes"
    )
    return result
