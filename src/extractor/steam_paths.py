"""Localisation de l'installation Steam et decouverte des jeux avec succes."""

import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_PATTERN = re.compile(r"^UserGameStatsSchema_(\d+)\.bin$")
USERSTATS_PATTERN = re.compile(r"^UserGameStats_(\d+)_(\d+)\.bin$")

DEFAULT_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Steam\appcache\stats"),
    Path(r"C:\Program Files\Steam\appcache\stats"),
)


class SteamNotFoundError(RuntimeError):
    """Leve quand les donnees locales de Steam sont introuvables."""


@dataclass(frozen=True)
class GameFiles:
    """Paire de fichiers .bin decrivant un jeu pour un compte donne."""

    appid: int
    schema_path: Path
    stats_path: Path


def find_stats_dir(candidates: list[Path] | None = None) -> Path:
    """Retourne le premier dossier appcache/stats existant."""
    searched = list(candidates) if candidates is not None else list(DEFAULT_CANDIDATES)
    for candidate in searched:
        if Path(candidate).is_dir():
            return Path(candidate)
    raise SteamNotFoundError(
        "dossier de statistiques Steam introuvable ; chemins essayes : "
        + ", ".join(str(c) for c in searched)
    )


def pick_account_id(stats_dir: Path) -> str:
    """Retourne l'account id Steam3 possedant le plus de jeux dans ce dossier."""
    counts: dict[str, int] = {}
    for path in Path(stats_dir).iterdir():
        match = USERSTATS_PATTERN.match(path.name)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    if not counts:
        raise SteamNotFoundError(f"aucun compte trouve dans {stats_dir}")
    return max(counts, key=lambda account: counts[account])


def discover_games(stats_dir: Path, account_id: str) -> list[GameFiles]:
    """Liste les jeux ayant a la fois un schema et des stats pour ce compte."""
    schemas: dict[int, Path] = {}
    stats: dict[int, Path] = {}

    for path in Path(stats_dir).iterdir():
        schema_match = SCHEMA_PATTERN.match(path.name)
        if schema_match:
            schemas[int(schema_match.group(1))] = path
            continue
        stats_match = USERSTATS_PATTERN.match(path.name)
        if stats_match and stats_match.group(1) == account_id:
            stats[int(stats_match.group(2))] = path

    return [
        GameFiles(appid=appid, schema_path=schemas[appid], stats_path=stats[appid])
        for appid in sorted(schemas.keys() & stats.keys())
    ]
