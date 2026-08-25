import json

import pytest

from web.db import connect, init_db
from web.ingest import InvalidExportError, ingest_export, ingest_file


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    return connection


def _export(appid=1245620, name="Elden Ring", unlocked=True):
    return {
        "exported_at": "2026-08-24T22:10:00+00:00",
        "account_id": "555",
        "games": [
            {
                "appid": appid,
                "name": name,
                "achievements": [
                    {
                        "api_name": "ACH01",
                        "name": "Seigneur d'Elden",
                        "description": "Obtenu le Cercle d'Elden.",
                        "icon": "https://cdn.example/a.jpg",
                        "icon_gray": "https://cdn.example/a_gray.jpg",
                        "hidden": False,
                        "unlocked": unlocked,
                        "unlock_time": "2024-03-12T18:44:00+00:00" if unlocked else None,
                    }
                ],
            }
        ],
    }


def test_ingest_export_inserts_game_and_achievements(conn):
    ingest_export(conn, _export())
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"
    row = conn.execute("SELECT * FROM achievements").fetchone()
    assert row["api_name"] == "ACH01"
    assert row["unlocked"] == 1


def test_ingest_export_returns_counts(conn):
    assert ingest_export(conn, _export()) == {"games": 1, "achievements": 1}


def test_ingest_export_updates_existing_rows_without_duplicating(conn):
    ingest_export(conn, _export(name="Ancien nom", unlocked=False))
    ingest_export(conn, _export(name="Elden Ring", unlocked=True))

    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM achievements").fetchone()["n"] == 1
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"
    assert conn.execute("SELECT unlocked FROM achievements").fetchone()["unlocked"] == 1


def test_ingest_export_never_relocks_an_unlocked_achievement(conn):
    # Un succes deja debloque ne doit pas repasser a verrouille si un export
    # plus ancien ou incomplet arrive ensuite.
    ingest_export(conn, _export(unlocked=True))
    ingest_export(conn, _export(unlocked=False))
    row = conn.execute("SELECT unlocked, unlock_time FROM achievements").fetchone()
    assert row["unlocked"] == 1
    assert row["unlock_time"] == "2024-03-12T18:44:00+00:00"


def test_ingest_export_rejects_payload_without_games_list(conn):
    with pytest.raises(InvalidExportError, match="games"):
        ingest_export(conn, {"exported_at": "x"})


def test_ingest_export_rejects_game_without_appid(conn):
    payload = _export()
    del payload["games"][0]["appid"]
    with pytest.raises(InvalidExportError, match="appid"):
        ingest_export(conn, payload)


def test_ingest_file_records_success_in_imports(conn, tmp_path):
    path = tmp_path / "succes_1.json"
    path.write_text(json.dumps(_export()), encoding="utf-8")

    ingest_file(conn, path)

    row = conn.execute("SELECT * FROM imports").fetchone()
    assert row["filename"] == "succes_1.json"
    assert row["status"] == "ok"


def test_ingest_file_records_failure_and_raises(conn, tmp_path):
    path = tmp_path / "casse.json"
    path.write_text("{ pas du json", encoding="utf-8")

    with pytest.raises(InvalidExportError):
        ingest_file(conn, path)

    row = conn.execute("SELECT * FROM imports").fetchone()
    assert row["status"] == "erreur"
    assert "JSON" in row["detail"]


def test_ingest_file_leaves_no_partial_data_on_failure(conn, tmp_path):
    payload = _export()
    payload["games"].append({"name": "sans appid", "achievements": []})
    path = tmp_path / "partiel.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidExportError):
        ingest_file(conn, path)

    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 0
