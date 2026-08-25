import pytest

from web.db import connect, init_db
from web.ingest import ingest_export
from web.queries import get_game, list_games, recent_unlocks


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    ingest_export(
        connection,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                {
                    "appid": 1,
                    "name": "Jeu A",
                    "achievements": [
                        {
                            "api_name": "A1",
                            "name": "Premier",
                            "unlocked": True,
                            "unlock_time": "2024-01-01T10:00:00+00:00",
                        },
                        {"api_name": "A2", "name": "Second", "unlocked": False},
                    ],
                },
                {
                    "appid": 2,
                    "name": "Jeu B",
                    "achievements": [
                        {
                            "api_name": "B1",
                            "name": "Unique",
                            "unlocked": True,
                            "unlock_time": "2024-06-01T10:00:00+00:00",
                        }
                    ],
                },
            ],
        },
    )
    return connection


def test_list_games_returns_completion_counts(conn):
    games = {g["appid"]: g for g in list_games(conn)}
    assert games[1]["total"] == 2
    assert games[1]["unlocked"] == 1
    assert games[2]["unlocked"] == 1


def test_list_games_computes_percentage(conn):
    games = {g["appid"]: g for g in list_games(conn)}
    assert games[1]["percent"] == 50
    assert games[2]["percent"] == 100


def test_list_games_sorted_by_percentage_desc(conn):
    assert [g["appid"] for g in list_games(conn)] == [2, 1]


def test_list_games_handles_game_without_achievements(conn):
    ingest_export(
        conn,
        {"exported_at": "x", "games": [{"appid": 3, "name": "Vide", "achievements": []}]},
    )
    empty = next(g for g in list_games(conn) if g["appid"] == 3)
    assert empty["total"] == 0
    assert empty["percent"] == 0


def test_get_game_returns_game_with_achievements(conn):
    game = get_game(conn, 1)
    assert game["name"] == "Jeu A"
    assert [a["api_name"] for a in game["achievements"]] == ["A1", "A2"]


def test_get_game_lists_unlocked_before_locked(conn):
    assert [a["unlocked"] for a in get_game(conn, 1)["achievements"]] == [1, 0]


def test_get_game_returns_none_for_unknown_appid(conn):
    assert get_game(conn, 404) is None


def test_recent_unlocks_returns_newest_first_across_games(conn):
    rows = recent_unlocks(conn, limit=10)
    assert [r["api_name"] for r in rows] == ["B1", "A1"]
    assert rows[0]["game_name"] == "Jeu B"


def test_recent_unlocks_respects_limit(conn):
    assert len(recent_unlocks(conn, limit=1)) == 1


def test_recent_unlocks_excludes_locked_achievements(conn):
    assert all(r["api_name"] != "A2" for r in recent_unlocks(conn, limit=10))
