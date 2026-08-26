import pytest

from web.db import connect, init_db
from web.ingest import ingest_export
from web.queries import get_game, list_games


def _game(appid, name, last_played, playtime=None, achievements=None):
    return {
        "appid": appid,
        "name": name,
        "cover": f"https://cdn.example/{appid}.jpg",
        "playtime_minutes": playtime,
        "last_played": last_played,
        "achievements": achievements or [],
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    ingest_export(
        connection,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                _game(
                    1,
                    "Jeu A",
                    "2024-01-01T10:00:00+00:00",
                    playtime=120,
                    achievements=[
                        {
                            "api_name": "A1",
                            "name": "Premier",
                            "unlocked": True,
                            "unlock_time": "2024-01-01T10:00:00+00:00",
                        },
                        {"api_name": "A2", "name": "Second", "unlocked": False},
                    ],
                ),
                _game(
                    2,
                    "Jeu B",
                    "2024-06-01T10:00:00+00:00",
                    playtime=30,
                    achievements=[
                        {
                            "api_name": "B1",
                            "name": "Unique",
                            "unlocked": True,
                            "unlock_time": "2024-06-01T10:00:00+00:00",
                        }
                    ],
                ),
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


def test_list_games_sorted_by_last_played_desc(conn):
    # Jeu B joue en juin, Jeu A en janvier : B passe devant, meme si son
    # taux de completion n'entre plus en compte dans l'ordre.
    assert [g["appid"] for g in list_games(conn)] == [2, 1]


def test_list_games_places_never_played_games_last(conn):
    ingest_export(conn, {"exported_at": "x", "games": [_game(3, "Jamais joue", None)]})
    assert [g["appid"] for g in list_games(conn)] == [2, 1, 3]


def test_list_games_exposes_cover_and_playtime(conn):
    games = {g["appid"]: g for g in list_games(conn)}
    assert games[1]["cover"] == "https://cdn.example/1.jpg"
    assert games[1]["playtime_minutes"] == 120
    assert games[1]["last_played"] == "2024-01-01T10:00:00+00:00"


def test_list_games_handles_game_without_achievements(conn):
    ingest_export(conn, {"exported_at": "x", "games": [_game(3, "Vide", None)]})
    empty = next(g for g in list_games(conn) if g["appid"] == 3)
    assert empty["total"] == 0
    assert empty["percent"] == 0


def test_get_game_returns_game_with_achievements(conn):
    game = get_game(conn, 1)
    assert game["name"] == "Jeu A"
    assert [a["api_name"] for a in game["achievements"]] == ["A1", "A2"]


def test_get_game_exposes_cover_and_playtime(conn):
    game = get_game(conn, 1)
    assert game["cover"] == "https://cdn.example/1.jpg"
    assert game["playtime_minutes"] == 120


def test_get_game_lists_unlocked_before_locked(conn):
    assert [a["unlocked"] for a in get_game(conn, 1)["achievements"]] == [1, 0]


def test_get_game_returns_none_for_unknown_appid(conn):
    assert get_game(conn, 404) is None
