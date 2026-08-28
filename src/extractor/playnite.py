"""Lecture du temps de jeu fourni par l'extension Playnite.

Playnite stocke sa bibliotheque dans un LiteDB (`games.db`) verrouille tant
que l'application tourne, et sans lecteur Python fiable : c'est donc
l'extension, qui a acces a l'API Playnite, qui exporte les temps de jeu dans
un JSON simple que ce module relit.

Interet par rapport a Steam : Playnite compte aussi le temps des parties
lancees hors Steam, la ou `Playtime` de localconfig.vdf ne voit que ce qui
est passe par le client Steam.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from extractor.library import GameActivity

logger = logging.getLogger(__name__)


def _parse_timestamp(value: object) -> int | None:
    """Convertit une date ISO en horodatage Unix. None si absente/invalide."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def read_playnite_activity(path: Path) -> dict[int, GameActivity]:
    """Retourne {appid: GameActivity} depuis l'export de l'extension Playnite.

    Best-effort : fichier absent, illisible ou mal forme donne un dictionnaire
    vide. Le temps de jeu est un enrichissement, jamais une raison de faire
    echouer l'extraction des succes.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("export Playnite illisible (%s) : temps de jeu Steam conserve", error)
        return {}

    games = payload.get("games")
    if not isinstance(games, dict):
        logger.warning("export Playnite sans cle 'games' : temps de jeu Steam conserve")
        return {}

    activity: dict[int, GameActivity] = {}
    for appid, entry in games.items():
        if not str(appid).isdigit() or not isinstance(entry, dict):
            continue
        playtime = entry.get("playtime_minutes")
        if not isinstance(playtime, int):
            continue
        activity[int(appid)] = GameActivity(
            playtime_minutes=playtime,
            last_played=_parse_timestamp(entry.get("last_played")),
        )
    return activity


def merge_activity(
    steam: dict[int, GameActivity], playnite: dict[int, GameActivity]
) -> dict[int, GameActivity]:
    """Fusionne les deux sources, Playnite prioritaire sur Steam.

    Playnite l'emporte car il compte les parties lancees hors Steam. Sa date
    de derniere partie peut manquer : on retombe alors sur celle de Steam
    plutot que de perdre l'information.
    """
    merged = dict(steam)
    for appid, entry in playnite.items():
        connue = merged.get(appid)
        merged[appid] = GameActivity(
            playtime_minutes=entry.playtime_minutes,
            last_played=entry.last_played or (connue.last_played if connue else None),
        )
    return merged
