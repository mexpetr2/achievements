"""Recuperation de la raretee des succes (pourcentage global de joueurs).

Cette donnee est mondiale, pas personnelle : elle n'existe donc nulle part
dans le cache Steam local et doit venir de l'API publique
`GetGlobalAchievementPercentagesForApp`, qui repond sans cle.

Meme principe que steam_catalog.py : best-effort, avec cache local, pour ne
jamais rendre l'extraction dependante du reseau. La raretee bouge lentement,
un cache de plusieurs semaines suffit largement.
"""

import json
import logging
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

GLOBAL_STATS_URL = (
    "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
)


def fetch_global_percentages(appid: int, timeout: float = 10) -> dict[str, float] | None:
    """Retourne {api_name: pourcentage} pour un jeu, ou None si indisponible.

    Leve en cas d'erreur reseau : c'est a l'appelant de decider du repli.
    Certains appids (outils Valve par exemple) repondent 403 ; l'appelant
    traite cela comme une absence definitive plutot qu'une erreur.
    """
    url = f"{GLOBAL_STATS_URL}?gameid={appid}"
    with urllib.request.urlopen(url, timeout=timeout) as reponse:
        payload = json.loads(reponse.read().decode("utf-8"))

    entrees = payload.get("achievementpercentages", {}).get("achievements")
    if not entrees:
        return None

    pourcentages: dict[str, float] = {}
    for entree in entrees:
        nom = entree.get("name")
        if not nom:
            continue
        try:
            # L'API renvoie le pourcentage sous forme de chaine ("10.4").
            pourcentages[str(nom)] = float(entree.get("percent"))
        except (TypeError, ValueError):
            continue
    return pourcentages or None


def _load_cache(cache_path: Path) -> dict:
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_global_percentages(
    appids: list[int],
    cache_path: Path,
    max_age_days: int = 30,
    fetch: Callable[..., dict[str, float] | None] = fetch_global_percentages,
    request_delay: float = 0.2,
) -> dict[int, dict[str, float]]:
    """Retourne {appid: {api_name: pourcentage}}, best-effort.

    Un appid dont la recuperation echoue est simplement absent du resultat et
    n'est pas mis en cache : on retentera au prochain run. Un appid sans
    donnees publiques est en revanche mis en cache, pour eviter de reinterroger
    l'API a chaque fois.
    """
    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    max_age_seconds = max_age_days * 86400
    maintenant = time.time()

    resultat: dict[int, dict[str, float]] = {}
    modifie = False
    deja_interroge = False

    for appid in appids:
        entree = cache.get(str(appid))
        if entree is not None and maintenant - entree.get("fetched_at", 0) <= max_age_seconds:
            connues = entree.get("percentages")
            if connues:
                resultat[appid] = {str(k): float(v) for k, v in connues.items()}
            continue

        if deja_interroge:
            time.sleep(request_delay)
        deja_interroge = True

        try:
            pourcentages = fetch(appid)
        except Exception as erreur:  # noqa: BLE001 - best effort, jamais bloquant
            logger.warning("raretee indisponible pour l'appid %s : %s", appid, erreur)
            continue

        cache[str(appid)] = {"percentages": pourcentages, "fetched_at": maintenant}
        modifie = True
        if pourcentages:
            resultat[appid] = pourcentages

    if modifie:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
        except OSError as erreur:
            logger.warning("ecriture du cache de raretee impossible : %s", erreur)

    return resultat
