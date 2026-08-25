"""Genere le hash a placer dans ACHIEVEMENTS_PASSWORD_HASH.

Usage : python scripts/generate_password_hash.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web.auth import hash_password  # noqa: E402

if __name__ == "__main__":
    password = getpass.getpass("Mot de passe du tableau de bord : ")
    confirm = getpass.getpass("Confirmer : ")
    if password != confirm:
        print("Les mots de passe ne correspondent pas.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 8:
        print("Choisir un mot de passe d'au moins 8 caracteres.", file=sys.stderr)
        raise SystemExit(1)
    print("\nACHIEVEMENTS_PASSWORD_HASH=" + hash_password(password))
