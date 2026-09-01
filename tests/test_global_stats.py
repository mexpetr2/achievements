"""Tests de la recuperation de la raretee des succes (pourcentage global)."""

import json
import time
from unittest.mock import patch

from extractor.global_stats import fetch_global_percentages, resolve_global_percentages


def _seed(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


class FakeResponse:
    """Reponse HTTP simulee, utilisable comme gestionnaire de contexte."""

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_resolve_uses_fresh_cache_without_fetching(tmp_path):
    cache = tmp_path / "rarete.json"
    _seed(cache, {"1245620": {"percentages": {"ACH00": 10.4}, "fetched_at": time.time()}})

    def boom(appid, timeout=10):
        raise AssertionError("le reseau ne doit pas etre appele si le cache est frais")

    assert resolve_global_percentages([1245620], cache, fetch=boom) == {1245620: {"ACH00": 10.4}}


def test_resolve_fetches_missing_appids(tmp_path):
    cache = tmp_path / "rarete.json"

    result = resolve_global_percentages(
        [1245620], cache, fetch=lambda appid, timeout=10: {"ACH00": 10.4}
    )

    assert result == {1245620: {"ACH00": 10.4}}
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["1245620"]["percentages"]["ACH00"] == 10.4


def test_resolve_refetches_stale_entries(tmp_path):
    cache = tmp_path / "rarete.json"
    _seed(cache, {"1": {"percentages": {"A": 1.0}, "fetched_at": time.time() - 40 * 86400}})

    result = resolve_global_percentages(
        [1], cache, max_age_days=30, fetch=lambda appid, timeout=10: {"A": 2.0}
    )

    assert result == {1: {"A": 2.0}}


def test_resolve_skips_appid_when_fetch_fails(tmp_path):
    cache = tmp_path / "rarete.json"

    def fail(appid, timeout=10):
        raise OSError("pas de reseau")

    assert resolve_global_percentages([1], cache, fetch=fail) == {}


def test_resolve_caches_absence_to_avoid_refetching(tmp_path):
    # Certains appids repondent 403 : inutile de reinterroger a chaque run.
    cache = tmp_path / "rarete.json"
    appels = []

    def fetch(appid, timeout=10):
        appels.append(appid)
        return None

    assert resolve_global_percentages([480], cache, fetch=fetch) == {}
    assert resolve_global_percentages([480], cache, fetch=fetch) == {}
    assert appels == [480]


def test_resolve_ignores_corrupted_cache(tmp_path):
    cache = tmp_path / "rarete.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{ pas du json", encoding="utf-8")

    result = resolve_global_percentages([1], cache, fetch=lambda appid, timeout=10: {"A": 5.0})
    assert result == {1: {"A": 5.0}}


def test_resolve_only_fetches_what_is_missing(tmp_path):
    cache = tmp_path / "rarete.json"
    _seed(cache, {"1": {"percentages": {"A": 1.0}, "fetched_at": time.time()}})
    appels = []

    def fetch(appid, timeout=10):
        appels.append(appid)
        return {"B": 2.0}

    resolve_global_percentages([1, 2], cache, fetch=fetch)
    assert appels == [2]


def test_resolve_never_raises_on_unexpected_error(tmp_path):
    def fetch(appid, timeout=10):
        raise ValueError("reponse inattendue")

    assert resolve_global_percentages([1], tmp_path / "r.json", fetch=fetch) == {}


def test_fetch_parses_percentages_as_floats():
    payload = json.dumps(
        {
            "achievementpercentages": {
                "achievements": [
                    {"name": "ACH00", "percent": "10.4"},
                    {"name": "ACH39", "percent": "75.0"},
                ]
            }
        }
    ).encode("utf-8")

    with patch(
        "extractor.global_stats.urllib.request.urlopen", return_value=FakeResponse(payload)
    ):
        assert fetch_global_percentages(1245620) == {"ACH00": 10.4, "ACH39": 75.0}


def test_fetch_returns_none_when_payload_has_no_achievements():
    payload = json.dumps({"achievementpercentages": {}}).encode("utf-8")

    with patch(
        "extractor.global_stats.urllib.request.urlopen", return_value=FakeResponse(payload)
    ):
        assert fetch_global_percentages(1) is None


def test_fetch_skips_entries_with_unparsable_percent():
    payload = json.dumps(
        {
            "achievementpercentages": {
                "achievements": [
                    {"name": "BON", "percent": "12.5"},
                    {"name": "CASSE", "percent": "beaucoup"},
                ]
            }
        }
    ).encode("utf-8")

    with patch(
        "extractor.global_stats.urllib.request.urlopen", return_value=FakeResponse(payload)
    ):
        assert fetch_global_percentages(1) == {"BON": 12.5}
