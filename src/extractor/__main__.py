"""Point d'entree CLI : python -m extractor --output-dir <dossier partage>."""

import argparse
import logging
import sys
from pathlib import Path

from extractor.export import build_export, write_export
from extractor.steam_paths import (
    SteamNotFoundError,
    discover_games,
    find_stats_dir,
    pick_account_id,
)


def main(argv: list[str] | None = None) -> int:
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
        export = build_export(games, account_id)
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
