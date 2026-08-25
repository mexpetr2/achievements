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
