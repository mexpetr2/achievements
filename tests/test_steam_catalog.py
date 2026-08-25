"""Tests du resolveur best-effort de noms publics via le catalogue Steam.

Design par appid (pas de recuperation en bloc) car l'API officielle
`GetAppList` n'est plus accessible sans cle : verifie a la main que
`ISteamApps/GetAppList` renvoie 404 sans cle sur `api.steampowered.com`,
alors que `store.steampowered.com/api/appdetails` marche bien sans cle,
par appid.
"""

import json
import time
from unittest.mock import patch

from extractor.steam_catalog import fetch_app_name, resolve_catalog_names


def _seed_cache(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_resolve_catalog_names_uses_fresh_cache_entry_without_fetching(tmp_path):
    cache = tmp_path / "cache.json"
    _seed_cache(cache, {"2651280": {"name": "Marvel's Spider-Man 2", "fetched_at": time.time()}})

    def boom(appid, timeout=10):
        raise AssertionError("le reseau ne doit pas etre appele si le cache est frais")

    result = resolve_catalog_names([2651280], cache, max_age_days=30, fetch=boom)
    assert result == {2651280: "Marvel's Spider-Man 2"}


def test_resolve_catalog_names_fetches_missing_entries(tmp_path):
    cache = tmp_path / "cache.json"

    result = resolve_catalog_names(
        [323470], cache, max_age_days=30, fetch=lambda appid, timeout=10: "DRAGON BALL XENOVERSE"
    )

    assert result == {323470: "DRAGON BALL XENOVERSE"}
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["323470"]["name"] == "DRAGON BALL XENOVERSE"


def test_resolve_catalog_names_refetches_stale_entries(tmp_path):
    cache = tmp_path / "cache.json"
    old = time.time() - 40 * 24 * 3600
    _seed_cache(cache, {"1": {"name": "Ancien nom", "fetched_at": old}})

    result = resolve_catalog_names(
        [1], cache, max_age_days=30, fetch=lambda appid, timeout=10: "Nouveau nom"
    )

    assert result == {1: "Nouveau nom"}


def test_resolve_catalog_names_skips_appid_when_fetch_fails(tmp_path):
    cache = tmp_path / "cache.json"

    def fail(appid, timeout=10):
        raise OSError("pas de reseau")

    result = resolve_catalog_names([999], cache, max_age_days=30, fetch=fail)

    assert result == {}
    assert not cache.exists()  # rien a sauver, on retentera au prochain run


def test_resolve_catalog_names_caches_not_found_result(tmp_path):
    cache = tmp_path / "cache.json"
    calls = []

    def fetch(appid, timeout=10):
        calls.append(appid)
        return None  # l'appid n'existe pas sur le store

    result = resolve_catalog_names([404404], cache, max_age_days=30, fetch=fetch)
    assert result == {}
    assert calls == [404404]

    # deuxieme appel : entree "non trouve" encore fraiche, pas de nouvel appel reseau
    result = resolve_catalog_names([404404], cache, max_age_days=30, fetch=fetch)
    assert result == {}
    assert calls == [404404]


def test_resolve_catalog_names_ignores_corrupted_cache_file(tmp_path):
    cache = tmp_path / "cache.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{ pas du json", encoding="utf-8")

    result = resolve_catalog_names(
        [5], cache, max_age_days=30, fetch=lambda appid, timeout=10: "Recupere"
    )

    assert result == {5: "Recupere"}


def test_resolve_catalog_names_only_fetches_stale_or_missing_appids(tmp_path):
    cache = tmp_path / "cache.json"
    _seed_cache(cache, {"1": {"name": "Deja en cache", "fetched_at": time.time()}})
    calls = []

    def fetch(appid, timeout=10):
        calls.append(appid)
        return f"Nom de {appid}"

    result = resolve_catalog_names([1, 2, 3], cache, max_age_days=30, fetch=fetch)

    assert calls == [2, 3]
    assert result == {1: "Deja en cache", 2: "Nom de 2", 3: "Nom de 3"}


def test_resolve_catalog_names_sleeps_between_real_fetches_but_not_before_the_first(tmp_path):
    cache = tmp_path / "cache.json"
    sleeps = []

    with patch("extractor.steam_catalog.time.sleep", side_effect=sleeps.append):
        resolve_catalog_names(
            [1, 2, 3],
            cache,
            max_age_days=30,
            fetch=lambda appid, timeout=10: f"Nom {appid}",
            request_delay=0.2,
        )

    assert sleeps == [0.2, 0.2]


def test_resolve_catalog_names_does_not_sleep_when_all_cached(tmp_path):
    cache = tmp_path / "cache.json"
    _seed_cache(cache, {"1": {"name": "X", "fetched_at": time.time()}})

    with patch("extractor.steam_catalog.time.sleep") as mock_sleep:
        resolve_catalog_names([1], cache, max_age_days=30, fetch=lambda a, timeout=10: "Y")

    mock_sleep.assert_not_called()


def test_fetch_app_name_parses_successful_response():
    fake_payload = json.dumps(
        {"2651280": {"success": True, "data": {"name": "Marvel's Spider-Man 2"}}}
    ).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return fake_payload

    with patch("extractor.steam_catalog.urllib.request.urlopen", return_value=FakeResponse()):
        assert fetch_app_name(2651280) == "Marvel's Spider-Man 2"


def test_fetch_app_name_returns_none_when_not_found_on_store():
    fake_payload = json.dumps({"999999999": {"success": False}}).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return fake_payload

    with patch("extractor.steam_catalog.urllib.request.urlopen", return_value=FakeResponse()):
        assert fetch_app_name(999999999) is None
