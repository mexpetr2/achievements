"""Point d'entree CLI : python -m extractor --output-dir <dossier partage>."""

import argparse
import logging
import sys
from pathlib import Path

from extractor.export import build_export, write_export
from extractor.global_stats import resolve_global_percentages
from extractor.library import read_activity
from extractor.playnite import merge_activity, read_playnite_activity
from extractor.steam_catalog import resolve_catalog_names
from extractor.steam_paths import (
    SteamNotFoundError,
    discover_games,
    find_localconfig,
    find_stats_dir,
    pick_account_id,
)

CACHE_DIR = Path.home() / ".cache" / "achievements-extractor"
DEFAULT_CATALOG_CACHE = CACHE_DIR / "steam_catalog.json"
DEFAULT_RARITY_CACHE = CACHE_DIR / "steam_rarity.json"


def main(
    argv: list[str] | None = None,
    resolve_names=resolve_catalog_names,
    resolve_rarity=resolve_global_percentages,
) -> int:
    parser = argparse.ArgumentParser(
        prog="extractor",
        description="Exporte les succes Steam locaux vers un fichier JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Dossier de destination (le dossier partage du NAS).",
    )
    parser.add_argument(
        "--stats-dir",
        default=None,
        help="Dossier appcache/stats de Steam (detecte automatiquement si absent).",
    )
    parser.add_argument(
        "--account-id",
        default=None,
        help="Account id Steam3 (detecte automatiquement si absent).",
    )
    parser.add_argument(
        "--no-catalog-lookup",
        action="store_true",
        help=(
            "Desactive la resolution du vrai nom public des jeux via le catalogue "
            "Steam (store.steampowered.com). Sans cette option, l'extracteur "
            "l'interroge en best-effort (avec cache local) pour corriger les noms "
            "peu fiables du cache local Steam (placeholders, noms de code internes)."
        ),
    )
    parser.add_argument(
        "--catalog-cache",
        default=str(DEFAULT_CATALOG_CACHE),
        help=f"Fichier de cache des noms resolus (defaut : {DEFAULT_CATALOG_CACHE}).",
    )
    parser.add_argument(
        "--no-rarity",
        action="store_true",
        help=(
            "Desactive la recuperation du pourcentage mondial de joueurs ayant "
            "obtenu chaque succes. Cette donnee est globale, donc absente du "
            "cache Steam local : elle vient de l'API publique, en best-effort."
        ),
    )
    parser.add_argument(
        "--rarity-cache",
        default=str(DEFAULT_RARITY_CACHE),
        help=f"Fichier de cache des pourcentages (defaut : {DEFAULT_RARITY_CACHE}).",
    )
    parser.add_argument(
        "--playnite",
        default=None,
        help=(
            "Fichier JSON de temps de jeu exporte par l'extension Playnite. "
            "Ces temps priment sur ceux de Steam, qui ne comptent que les "
            "parties lancees via le client Steam."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Affiche les jeux ignores.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        format="%(levelname)s: %(message)s",
    )

    try:
        if args.stats_dir:
            stats_dir = Path(args.stats_dir)
            if not stats_dir.is_dir():
                raise SteamNotFoundError(
                    f"dossier de statistiques Steam introuvable : {stats_dir}"
                )
        else:
            stats_dir = find_stats_dir()

        account_id = args.account_id or pick_account_id(stats_dir)
        games = discover_games(stats_dir, account_id)

        catalog_names, not_found_appids = {}, set()
        if not args.no_catalog_lookup:
            lookup = resolve_names([g.appid for g in games], Path(args.catalog_cache))
            catalog_names, not_found_appids = lookup.names, lookup.not_found

        localconfig = find_localconfig(stats_dir, account_id)
        activity = read_activity(localconfig) if localconfig else {}
        if args.playnite:
            activity = merge_activity(activity, read_playnite_activity(Path(args.playnite)))

        rarity = {}
        if not args.no_rarity:
            rarity = resolve_rarity([g.appid for g in games], Path(args.rarity_cache))

        export = build_export(
            games, account_id, catalog_names, not_found_appids, activity, rarity
        )
        path = write_export(export, Path(args.output_dir))
    except (SteamNotFoundError, FileNotFoundError, PermissionError, OSError) as error:
        print(f"Echec de l'export : {error}", file=sys.stderr)
        return 1

    total = sum(len(g["achievements"]) for g in export["games"])
    unlocked = sum(1 for g in export["games"] for a in g["achievements"] if a["unlocked"])
    label = "jeu" if len(export["games"]) == 1 else "jeux"
    print(f"{len(export['games'])} {label}, {unlocked}/{total} succes debloques -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
