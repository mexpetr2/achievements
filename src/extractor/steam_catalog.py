"""Resolution best-effort des noms publics de jeux via le catalogue Steam.

Le champ `gamename` du cache local Steam (voir schema.py) n'est pas fiable :
tantot un placeholder Valve, tantot un nom de code interne au studio (ex.
"Popsicle" pour Marvel's Spider-Man 2). Ce module recupere en repli le nom
public via la fiche boutique Steam (store.steampowered.com/api/appdetails),
appid par appid, mis en cache localement pour rester utilisable hors ligne.

L'API officielle ISteamApps/GetAppList n'est plus accessible sans cle
(verifie : 404 sur api.steampowered.com sans cle) ; la fiche boutique, elle,
ne demande pas de cle et repond par appid. Best-effort : ne leve jamais,
retourne un dict vide (ou partiel) si rien n'est disponible.
"""

import json
import logging
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"


class CatalogLookup(NamedTuple):
    """Resultat de resolve_catalog_names.

    `names` : appid -> nom public, pour les jeux confirmes sur le store.
    `not_found` : appids confirmes absents du store (app de test/outil interne
    sans fiche boutique) - a distinguer d'un appid simplement pas encore
    verifie (echec reseau, ou lookup desactive), qui n'apparait dans aucun
    des deux et doit rester affiche avec son nom local en repli.
    """

    names: dict[int, str]
    not_found: set[int]


def fetch_app_name(appid: int, timeout: float = 10) -> str | None:
    """Interroge la fiche boutique Steam pour le nom public d'un jeu.

    Retourne None si le jeu n'existe pas/plus sur le store. Leve en cas
    d'erreur reseau : c'est a l'appelant (resolve_catalog_names) de decider
    du repli, pas a cette fonction.
    """
    url = f"{APPDETAILS_URL}?appids={appid}&filters=basic"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entry = payload.get(str(appid), {})
    if not entry.get("success"):
        return None
    name = entry.get("data", {}).get("name")
    return str(name) if name else None


def _load_cache(cache_path: Path) -> dict:
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")


def resolve_catalog_names(
    appids: list[int],
    cache_path: Path,
    max_age_days: int = 30,
    fetch: Callable[..., str | None] = fetch_app_name,
    request_delay: float = 0.2,
) -> CatalogLookup:
    """Resout les noms publics des `appids` donnes, best-effort.

    Priorite par appid : cache frais -> reseau (puis mise a jour du cache).
    Un echec reseau sur un appid ne bloque pas les autres et n'ecrit rien
    au cache pour lui (on retentera au prochain run) : il n'apparait alors
    dans aucun des deux ensembles retournes. Une reponse "non trouve" (le
    store confirme que l'appid n'existe pas) est mise en cache et rapportee
    dans `not_found`, pour eviter de re-interroger inutilement le store et
    permettre a l'appelant d'exclure ces apps (outils/tests internes sans
    fiche boutique). Ne leve jamais : conserve l'extraction utilisable hors
    ligne.
    """
    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    max_age_seconds = max_age_days * 86400
    now = time.time()

    resolved: dict[int, str] = {}
    not_found: set[int] = set()
    dirty = False
    fetched_once = False

    for appid in appids:
        entry = cache.get(str(appid))
        if entry is not None and now - entry.get("fetched_at", 0) <= max_age_seconds:
            if entry.get("name"):
                resolved[appid] = entry["name"]
            else:
                not_found.add(appid)
            continue

        if fetched_once:
            time.sleep(request_delay)
        fetched_once = True

        try:
            name = fetch(appid)
        except Exception as error:  # noqa: BLE001 - best effort, jamais bloquant
            logger.warning("resolution du nom pour l'appid %s impossible : %s", appid, error)
            continue

        cache[str(appid)] = {"name": name, "fetched_at": now}
        dirty = True
        if name:
            resolved[appid] = name
        else:
            not_found.add(appid)

    if dirty:
        try:
            _save_cache(cache_path, cache)
        except OSError as error:
            logger.warning("ecriture du cache catalogue impossible : %s", error)

    return CatalogLookup(names=resolved, not_found=not_found)
