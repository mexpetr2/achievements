"""Lecture du temps de jeu et du dernier lancement depuis localconfig.vdf.

Ces deux informations n'existent pas dans les caches de succes : Steam les
stocke dans le fichier de configuration du compte, au format VDF texte.

Attention a l'interpretation : `Playtime` ne compte que le temps de jeu
*lance via Steam*. Un jeu joue en dehors de Steam affichera un temps tres
inferieur au temps reellement passe.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from extractor.text_vdf import parse_text_vdf

logger = logging.getLogger(__name__)

# Chemin du bloc des jeux dans localconfig.vdf.
APPS_PATH = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")


@dataclass(frozen=True)
class GameActivity:
    """Activite d'un jeu telle que Steam la connait localement."""

    playtime_minutes: int | None
    last_played: int | None


def _descend(node: dict, path: tuple[str, ...]) -> dict | None:
    """Suit un chemin de cles, sans tenir compte de la casse."""
    for wanted in path:
        if not isinstance(node, dict):
            return None
        match = next((k for k in node if k.lower() == wanted.lower()), None)
        if match is None:
            return None
        node = node[match]
    return node if isinstance(node, dict) else None


def _read_int(entry: dict, field: str) -> int | None:
    """Lit un champ entier, sans tenir compte de la casse. None si absent/invalide."""
    key = next((k for k in entry if k.lower() == field.lower()), None)
    if key is None:
        return None
    try:
        return int(entry[key])
    except (TypeError, ValueError):
        return None


def read_activity(localconfig_path: Path) -> dict[int, GameActivity]:
    """Retourne {appid: GameActivity} pour les jeux ayant une activite connue.

    Best-effort : un fichier absent, illisible ou de structure inattendue
    donne un dictionnaire vide plutot qu'une erreur. Le temps de jeu et la
    date de derniere partie sont des enrichissements de confort, jamais une
    raison de faire echouer l'extraction des succes.
    """
    try:
        text = Path(localconfig_path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        logger.warning("localconfig.vdf illisible (%s) : temps de jeu indisponible", error)
        return {}

    apps = _descend(parse_text_vdf(text), APPS_PATH)
    if apps is None:
        logger.warning("structure inattendue dans localconfig.vdf : temps de jeu indisponible")
        return {}

    activity: dict[int, GameActivity] = {}
    for appid, entry in apps.items():
        if not appid.isdigit() or not isinstance(entry, dict):
            continue
        playtime = _read_int(entry, "Playtime")
        last_played = _read_int(entry, "LastPlayed")
        if playtime is None and last_played is None:
            continue
        activity[int(appid)] = GameActivity(playtime_minutes=playtime, last_played=last_played)
    return activity
