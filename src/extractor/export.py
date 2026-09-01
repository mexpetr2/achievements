"""Assemblage des donnees extraites en un export JSON lisible."""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from extractor.library import GameActivity
from extractor.schema import parse_schema
from extractor.steam_paths import GameFiles
from extractor.userstats import parse_userstats

logger = logging.getLogger(__name__)

# Icones de succes. L'ancien chemin (steamcommunity/public/images/apps) ne sert
# plus les icones ajoutees recemment : sur Palworld, 20 succes sur 75 y
# repondaient 404, tous parmi les plus recents. C'est ce chemin que Steam
# utilise lui-meme aujourd'hui, et il sert aussi bien les anciennes icones.
CDN_BASE = "https://shared.akamai.steamstatic.com/community_assets/images/apps"

# Jaquette verticale de la bibliotheque Steam (format 600x900).
LIBRARY_ART_BASE = "https://cdn.cloudflare.steamstatic.com/steam/apps"

# Un account id Steam3 devient un SteamID64 en ajoutant cette base.
STEAMID64_BASE = 76561197960265728


def icon_url(appid: int, icon: str) -> str:
    """Construit l'URL CDN d'une icone de succes, ou une chaine vide si absente."""
    return f"{CDN_BASE}/{appid}/{icon}" if icon else ""


def cover_url(appid: int) -> str:
    """Construit l'URL CDN de la jaquette verticale du jeu."""
    return f"{LIBRARY_ART_BASE}/{appid}/library_600x900.jpg"


def build_game_export(
    game: GameFiles,
    catalog_name: str | None = None,
    activity: GameActivity | None = None,
    global_percentages: dict[str, float] | None = None,
) -> dict:
    """Fusionne definitions et etat de deblocage pour un jeu.

    `catalog_name` (nom public resolu via le catalogue Steam, voir
    steam_catalog.py) est prefere au `gamename` du schema local quand
    disponible : ce dernier est parfois un nom de code interne au studio
    (ex. "Popsicle" pour Marvel's Spider-Man 2) ou un placeholder Valve.

    `activity` (voir library.py) porte le temps de jeu et la date de derniere
    partie. Absent pour les jeux que Steam n'a jamais vu tourner localement.

    `global_percentages` (voir global_stats.py) donne la part mondiale de
    joueurs ayant obtenu chaque succes, indexee par nom d'API.
    """
    global_percentages = global_percentages or {}
    schema = parse_schema(game.schema_path.read_bytes(), appid=game.appid)
    unlocks = parse_userstats(game.stats_path.read_bytes())

    achievements = []
    for key in sorted(schema.achievements, key=lambda k: (k[0], k[1])):
        definition = schema.achievements[key]
        timestamp = unlocks.get(key)
        achievements.append(
            {
                "api_name": definition.api_name,
                "name": definition.name,
                "description": definition.description,
                "icon": icon_url(game.appid, definition.icon),
                "icon_gray": icon_url(game.appid, definition.icon_gray),
                "hidden": definition.hidden,
                "global_percent": global_percentages.get(definition.api_name),
                "unlocked": timestamp is not None,
                "unlock_time": (
                    datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
                    if timestamp is not None
                    else None
                ),
            }
        )

    last_played = activity.last_played if activity else None
    return {
        "appid": game.appid,
        "name": catalog_name or schema.name,
        "cover": cover_url(game.appid),
        "playtime_minutes": activity.playtime_minutes if activity else None,
        "last_played": (
            datetime.fromtimestamp(last_played, tz=UTC).isoformat()
            if last_played is not None
            else None
        ),
        "achievements": achievements,
    }


def build_export(
    games: list[GameFiles],
    account_id: str,
    catalog_names: dict[int, str] | None = None,
    not_found_appids: set[int] | None = None,
    activity: dict[int, GameActivity] | None = None,
    global_percentages: dict[int, dict[str, float]] | None = None,
) -> dict:
    """Construit l'export complet, en sautant les jeux illisibles.

    `not_found_appids` : appids confirmes absents du store Steam (outils/apps
    de test internes, ou jeux fermes depuis). Un jeu de cet ensemble n'est
    exclu de l'export que s'il n'a par ailleurs aucun succes debloque : un
    jeu ferme mais reellement joue garde ses succes reels visibles.

    `activity` : temps de jeu et derniere partie par appid (voir library.py).
    """
    catalog_names = catalog_names or {}
    not_found_appids = not_found_appids or set()
    activity = activity or {}
    global_percentages = global_percentages or {}
    exported_games = []
    for game in games:
        try:
            game_export = build_game_export(
                game,
                catalog_names.get(game.appid),
                activity.get(game.appid),
                global_percentages.get(game.appid),
            )
        except Exception as error:  # noqa: BLE001 - un jeu casse ne doit pas tout arreter
            logger.warning("jeu %s ignore : %s: %s", game.appid, type(error).__name__, error)
            continue

        if game.appid in not_found_appids and not any(
            a["unlocked"] for a in game_export["achievements"]
        ):
            continue

        exported_games.append(game_export)

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account_id": account_id,
        "steam_id64": int(account_id) + STEAMID64_BASE,
        "games": exported_games,
    }


def write_export(export: dict, target_dir: Path) -> Path:
    """Ecrit l'export en JSON horodate, de maniere atomique.

    L'ecriture passe par un fichier .tmp renomme ensuite : le surveillant du NAS
    ne peut jamais lire un fichier a moitie ecrit.
    """
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        raise FileNotFoundError(f"dossier de destination introuvable : {target_dir}")

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    final_path = target_dir / f"succes_{stamp}.json"
    temp_path = target_dir / f"succes_{stamp}.json.tmp"

    temp_path.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, final_path)
    return final_path
