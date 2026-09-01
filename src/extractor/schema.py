"""Lecture des definitions de succes depuis UserGameStatsSchema_<appid>.bin."""

import html
import re
from dataclasses import dataclass

from extractor.binary_vdf import parse_binary_vdf

# Steam stocke parfois un nom de code interne au lieu du vrai titre.
PLACEHOLDER_NAME = re.compile(r"^ValveTestApp\d+$")

# Ordre de preference des langues pour les libelles.
LANGUAGES = ("french", "english")


@dataclass(frozen=True)
class AchievementDef:
    """Definition d'un succes, telle que publiee par le jeu."""

    api_name: str
    name: str
    description: str
    icon: str
    icon_gray: str
    hidden: bool


@dataclass(frozen=True)
class GameSchema:
    """Ensemble des definitions de succes d'un jeu."""

    appid: int
    name: str
    achievements: dict[tuple[str, int], AchievementDef]


def _pick_language(block: object) -> str:
    """Retourne le libelle dans la premiere langue disponible.

    Les libelles publies par certains studios contiennent des entites HTML
    brutes ("Je fais peur&nbsp;?") : on les decode ici, a la source, pour que
    tout l'aval manipule du texte lisible.
    """
    if not isinstance(block, dict):
        return ""
    for language in LANGUAGES:
        value = block.get(language)
        if value:
            return html.unescape(str(value))
    return ""


def parse_schema(data: bytes, appid: int) -> GameSchema:
    """Parse un schema binaire en definitions de succes.

    Les succes sont indexes par (stat_id, bit_index) : les index de bits sont
    relatifs a chaque stat id, jamais globaux.
    """
    parsed = parse_binary_vdf(data)
    root = parsed[str(appid)]

    raw_name = str(root.get("gamename") or "")
    name = f"App {appid}" if not raw_name or PLACEHOLDER_NAME.match(raw_name) else raw_name

    achievements: dict[tuple[str, int], AchievementDef] = {}
    stats = root.get("stats", {})
    if isinstance(stats, dict):
        for stat_id, stat in stats.items():
            if not isinstance(stat, dict):
                continue
            bits = stat.get("bits")
            if not isinstance(bits, dict):
                continue
            for bit_index, bit in bits.items():
                if not isinstance(bit, dict) or not str(bit_index).isdigit():
                    continue
                display = bit.get("display", {})
                display = display if isinstance(display, dict) else {}
                achievements[(str(stat_id), int(bit_index))] = AchievementDef(
                    api_name=str(bit.get("name", "")),
                    name=_pick_language(display.get("name")),
                    description=_pick_language(display.get("desc")),
                    icon=str(display.get("icon", "")),
                    icon_gray=str(display.get("icon_gray", "")),
                    hidden=bool(display.get("hidden", 0)),
                )

    return GameSchema(appid=appid, name=name, achievements=achievements)
