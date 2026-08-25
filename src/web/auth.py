"""Authentification par mot de passe unique (PBKDF2 + comparaison a temps constant)."""

import hashlib
import hmac
import os

ITERATIONS = 260_000
ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """Retourne 'pbkdf2_sha256$<iterations>$<sel_hex>$<hash_hex>'."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(ALGORITHM, password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(stored: str, candidate: str) -> bool:
    """Verifie un mot de passe contre sa valeur stockee, sans fuite de timing."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != f"pbkdf2_{ALGORITHM}":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            ALGORITHM, candidate.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(expected, actual)
