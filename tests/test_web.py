import pytest

from web.app import create_app
from web.auth import hash_password
from web.db import connect, init_db
from web.ingest import ingest_export

PASSWORD = "secret-du-nas"


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    init_db(conn)
    ingest_export(
        conn,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                {
                    "appid": 1245620,
                    "name": "Elden Ring",
                    "achievements": [
                        {
                            "api_name": "ACH01",
                            "name": "Seigneur d'Elden",
                            "description": "Obtenu le Cercle d'Elden.",
                            "unlocked": True,
                            "unlock_time": "2024-03-12T18:44:00+00:00",
                        },
                        {"api_name": "ACH02", "name": "Verrouille", "unlocked": False},
                    ],
                }
            ],
        },
    )
    conn.close()

    return create_app(
        {
            "DATABASE": str(db_path),
            "PASSWORD_HASH": hash_password(PASSWORD),
            "SECRET_KEY": "cle-de-test",
            "TESTING": True,
            "START_WATCHER": False,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"password": PASSWORD})
    return client


def test_index_redirects_to_login_when_anonymous(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_game_page_redirects_to_login_when_anonymous(client):
    assert client.get("/game/1245620").status_code == 302


def test_login_with_correct_password_grants_access(client):
    response = client.post("/login", data={"password": PASSWORD}, follow_redirects=True)
    assert response.status_code == 200
    assert "Elden Ring" in response.get_data(as_text=True)


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/login", data={"password": "mauvais"})
    assert response.status_code == 401
    assert "incorrect" in response.get_data(as_text=True).lower()


def test_index_shows_completion_percentage(logged_in):
    body = logged_in.get("/").get_data(as_text=True)
    assert "Elden Ring" in body
    assert "50" in body


def test_index_has_a_search_field(logged_in):
    body = logged_in.get("/").get_data(as_text=True)
    assert 'id="recherche"' in body


def test_index_uses_the_french_plural_of_jeu(logged_in):
    body = logged_in.get("/").get_data(as_text=True)
    assert "jeus" not in body


def test_index_no_longer_shows_recent_unlocks_section(logged_in):
    body = logged_in.get("/").get_data(as_text=True)
    assert "Derniers débloqués" not in body


def test_index_does_not_inline_achievement_details(logged_in):
    # Les succes sont charges a la demande : la liste ne doit pas les contenir.
    body = logged_in.get("/").get_data(as_text=True)
    assert "Obtenu le Cercle d&#39;Elden." not in body
    assert "Obtenu le Cercle d'Elden." not in body


def test_api_game_returns_achievements_as_json(logged_in):
    payload = logged_in.get("/api/game/1245620").get_json()
    assert payload["name"] == "Elden Ring"
    assert [a["api_name"] for a in payload["achievements"]] == ["ACH01", "ACH02"]


def test_api_game_requires_login(client):
    assert client.get("/api/game/1245620").status_code == 302


def test_api_game_returns_404_for_unknown_appid(logged_in):
    assert logged_in.get("/api/game/999999").status_code == 404


def test_game_page_shows_unlocked_and_locked_achievements(logged_in):
    body = logged_in.get("/game/1245620").get_data(as_text=True)
    assert "Seigneur d&#39;Elden" in body or "Seigneur d'Elden" in body
    assert "Verrouille" in body


def test_unknown_game_returns_404(logged_in):
    assert logged_in.get("/game/999999").status_code == 404


def test_logout_revokes_access(logged_in):
    logged_in.post("/logout")
    assert logged_in.get("/").status_code == 302


def test_healthcheck_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_create_app_requires_password_hash(tmp_path):
    with pytest.raises(RuntimeError, match="PASSWORD_HASH"):
        create_app(
            {"DATABASE": str(tmp_path / "x.db"), "SECRET_KEY": "k", "START_WATCHER": False}
        )


def test_game_page_hides_spoiler_for_locked_hidden_achievement(tmp_path):
    db_path = tmp_path / "spoiler.db"
    conn = connect(db_path)
    init_db(conn)
    ingest_export(
        conn,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                {
                    "appid": 999,
                    "name": "Jeu Spoiler",
                    "achievements": [
                        {
                            "api_name": "SECRET_LOCKED",
                            "name": "La fin secrete",
                            "description": "Vous avez trahi tout le monde.",
                            "hidden": True,
                            "unlocked": False,
                        },
                        {
                            "api_name": "SECRET_UNLOCKED",
                            "name": "Fin secrete debloquee",
                            "description": "Recompense pour la fin secrete.",
                            "hidden": True,
                            "unlocked": True,
                            "unlock_time": "2024-01-01T00:00:00+00:00",
                        },
                    ],
                }
            ],
        },
    )
    conn.close()

    app = create_app(
        {
            "DATABASE": str(db_path),
            "PASSWORD_HASH": hash_password(PASSWORD),
            "SECRET_KEY": "cle-de-test",
            "TESTING": True,
            "START_WATCHER": False,
        }
    )
    client = app.test_client()
    client.post("/login", data={"password": PASSWORD})

    body = client.get("/game/999").get_data(as_text=True)

    assert "La fin secrete" not in body
    assert "Vous avez trahi tout le monde." not in body
    assert "Succès caché" in body

    assert "Fin secrete debloquee" in body
    assert "Recompense pour la fin secrete." in body
