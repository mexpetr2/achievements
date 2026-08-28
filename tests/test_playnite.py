"""Tests de la lecture du temps de jeu fourni par l'extension Playnite."""

import json

from extractor.library import GameActivity
from extractor.playnite import merge_activity, read_playnite_activity


def _write(tmp_path, payload):
    path = tmp_path / "playnite.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_read_playnite_activity_returns_playtime_by_appid(tmp_path):
    path = _write(
        tmp_path,
        {
            "games": {
                "1091500": {
                    "playtime_minutes": 8880,
                    "last_played": "2026-08-24T21:27:58+00:00",
                }
            }
        },
    )
    activity = read_playnite_activity(path)
    assert activity[1091500].playtime_minutes == 8880
    assert activity[1091500].last_played == 1787606878


def test_read_playnite_activity_allows_missing_last_played(tmp_path):
    path = _write(tmp_path, {"games": {"1": {"playtime_minutes": 60}}})
    assert read_playnite_activity(path) == {
        1: GameActivity(playtime_minutes=60, last_played=None)
    }


def test_read_playnite_activity_skips_entries_without_playtime(tmp_path):
    path = _write(tmp_path, {"games": {"1": {"last_played": "2026-01-01T00:00:00+00:00"}}})
    assert read_playnite_activity(path) == {}


def test_read_playnite_activity_ignores_non_numeric_appids(tmp_path):
    path = _write(
        tmp_path,
        {"games": {"pas_un_appid": {"playtime_minutes": 10}, "2": {"playtime_minutes": 20}}},
    )
    assert list(read_playnite_activity(path)) == [2]


def test_read_playnite_activity_returns_empty_when_file_missing(tmp_path):
    assert read_playnite_activity(tmp_path / "absent.json") == {}


def test_read_playnite_activity_returns_empty_for_invalid_json(tmp_path):
    path = tmp_path / "casse.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert read_playnite_activity(path) == {}


def test_read_playnite_activity_returns_empty_when_games_key_missing(tmp_path):
    assert read_playnite_activity(_write(tmp_path, {"autre": 1})) == {}


def test_merge_activity_prefers_playnite_playtime():
    steam = {1: GameActivity(playtime_minutes=33, last_played=1000)}
    playnite = {1: GameActivity(playtime_minutes=8880, last_played=2000)}
    assert merge_activity(steam, playnite)[1].playtime_minutes == 8880


def test_merge_activity_keeps_steam_entry_when_playnite_has_none():
    steam = {1: GameActivity(playtime_minutes=33, last_played=1000)}
    assert merge_activity(steam, {})[1].playtime_minutes == 33


def test_merge_activity_adds_games_only_playnite_knows():
    playnite = {2: GameActivity(playtime_minutes=500, last_played=2000)}
    merged = merge_activity({}, playnite)
    assert merged[2].playtime_minutes == 500


def test_merge_activity_falls_back_to_steam_last_played_when_playnite_lacks_it():
    steam = {1: GameActivity(playtime_minutes=33, last_played=1000)}
    playnite = {1: GameActivity(playtime_minutes=8880, last_played=None)}
    merged = merge_activity(steam, playnite)
    assert merged[1] == GameActivity(playtime_minutes=8880, last_played=1000)


def test_merge_activity_does_not_mutate_its_inputs():
    steam = {1: GameActivity(playtime_minutes=33, last_played=1000)}
    playnite = {1: GameActivity(playtime_minutes=8880, last_played=2000)}
    merge_activity(steam, playnite)
    assert steam[1].playtime_minutes == 33
