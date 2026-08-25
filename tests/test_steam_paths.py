import pytest

from extractor.steam_paths import (
    SteamNotFoundError,
    discover_games,
    find_stats_dir,
    pick_account_id,
)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x08")


def test_find_stats_dir_returns_existing_candidate(tmp_path):
    stats = tmp_path / "Steam" / "appcache" / "stats"
    stats.mkdir(parents=True)
    assert find_stats_dir(candidates=[tmp_path / "absent", stats]) == stats


def test_find_stats_dir_raises_when_no_candidate_exists(tmp_path):
    with pytest.raises(SteamNotFoundError, match="dossier de statistiques Steam"):
        find_stats_dir(candidates=[tmp_path / "absent"])


def test_pick_account_id_returns_account_with_most_games(tmp_path):
    _touch(tmp_path / "UserGameStats_111_1.bin")
    _touch(tmp_path / "UserGameStats_222_1.bin")
    _touch(tmp_path / "UserGameStats_222_2.bin")
    assert pick_account_id(tmp_path) == "222"


def test_pick_account_id_raises_when_no_user_files(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_1.bin")
    with pytest.raises(SteamNotFoundError, match="aucun compte"):
        pick_account_id(tmp_path)


def test_discover_games_pairs_schema_and_user_files(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_1245620.bin")
    _touch(tmp_path / "UserGameStats_555_1245620.bin")
    games = discover_games(tmp_path, account_id="555")
    assert len(games) == 1
    assert games[0].appid == 1245620
    assert games[0].schema_path.name == "UserGameStatsSchema_1245620.bin"
    assert games[0].stats_path.name == "UserGameStats_555_1245620.bin"


def test_discover_games_skips_appid_without_schema(tmp_path):
    _touch(tmp_path / "UserGameStats_555_999.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_skips_appid_without_user_stats(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_999.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_ignores_other_accounts(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_42.bin")
    _touch(tmp_path / "UserGameStats_999_42.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_sorted_by_appid(tmp_path):
    for appid in (300, 100, 200):
        _touch(tmp_path / f"UserGameStatsSchema_{appid}.bin")
        _touch(tmp_path / f"UserGameStats_555_{appid}.bin")
    assert [g.appid for g in discover_games(tmp_path, account_id="555")] == [100, 200, 300]
