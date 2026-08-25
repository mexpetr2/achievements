"""Assemblage des donnees extraites en un export JSON lisible."""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from extractor.schema import parse_schema
from extractor.steam_paths import GameFiles
from extractor.userstats import parse_userstats

logger = logging.getLogger(__name__)

CDN_BASE = "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps"

# Un account id Steam3 devient un SteamID64 en ajoutant cette base.
STEAMID64_BASE = 76561197960265728


def icon_url(appid: int, icon: str) -> str:
    """Construit l'URL CDN d'une icone de succes, ou une chaine vide si absente."""
    return f"{CDN_BASE}/{appid}/{icon}" if icon else ""


def build_game_export(game: GameFiles, catalog_name: str | None = None) -> dict:
    """Fusionne definitions et etat de deblocage pour un jeu.

    `catalog_name` (nom public resolu via le catalogue Steam, voir
    steam_catalog.py) est prefere au `gamename` du schema local quand
    disponible : ce dernier est parfois un nom de code interne au studio
    (ex. "Popsicle" pour Marvel's Spider-Man 2) ou un placeholder Valve.
    """
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
                "unlocked": timestamp is not None,
                "unlock_time": (
                    datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
                    if timestamp is not None
                    else None
                ),
            }
        )

    return {"appid": game.appid, "name": catalog_name or schema.name, "achievements": achievements}


def build_export(
    games: list[GameFiles], account_id: str, catalog_names: dict[int, str] | None = None
) -> dict:
    """Construit l'export complet, en sautant les jeux illisibles."""
    catalog_names = catalog_names or {}
    exported_games = []
    for game in games:
        try:
            exported_games.append(build_game_export(game, catalog_names.get(game.appid)))
        except Exception as error:  # noqa: BLE001 - un jeu casse ne doit pas tout arreter
            logger.warning("jeu %s ignore : %s: %s", game.appid, type(error).__name__, error)

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
