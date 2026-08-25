import json

import pytest

from web.db import connect, init_db
from web.watcher import scan_once


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    return connection


@pytest.fixture
def inbox(tmp_path):
    folder = tmp_path / "partage"
    folder.mkdir()
    return folder


def _valid_export():
    return {
        "exported_at": "2026-08-24T22:10:00+00:00",
        "games": [
            {
                "appid": 1245620,
                "name": "Elden Ring",
                "achievements": [
                    {
                        "api_name": "ACH01",
                        "name": "Seigneur d'Elden",
                        "unlocked": True,
                        "unlock_time": "2024-03-12T18:44:00+00:00",
                    }
                ],
            }
        ],
    }


def test_scan_once_ingests_and_moves_valid_file(conn, inbox):
    (inbox / "succes_1.json").write_text(json.dumps(_valid_export()), encoding="utf-8")

    result = scan_once(conn, inbox)

    assert result == {"ok": 1, "erreur": 0}
    assert not (inbox / "succes_1.json").exists()
    assert (inbox / "importes" / "succes_1.json").exists()
    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1


def test_scan_once_moves_invalid_file_to_error_folder(conn, inbox):
    (inbox / "casse.json").write_text("{ pas du json", encoding="utf-8")

    result = scan_once(conn, inbox)

    assert result == {"ok": 0, "erreur": 1}
    assert (inbox / "erreurs" / "casse.json").exists()


def test_scan_once_ignores_non_json_files(conn, inbox):
    (inbox / "notes.txt").write_text("bonjour", encoding="utf-8")
    assert scan_once(conn, inbox) == {"ok": 0, "erreur": 0}
    assert (inbox / "notes.txt").exists()


def test_scan_once_ignores_temp_files_being_written(conn, inbox):
    (inbox / "succes_2.json.tmp").write_text(json.dumps(_valid_export()), encoding="utf-8")
    assert scan_once(conn, inbox) == {"ok": 0, "erreur": 0}
    assert (inbox / "succes_2.json.tmp").exists()


def test_scan_once_returns_zero_when_inbox_missing(conn, tmp_path):
    assert scan_once(conn, tmp_path / "absent") == {"ok": 0, "erreur": 0}


def test_scan_once_renames_on_collision_instead_of_overwriting(conn, inbox):
    processed = inbox / "importes"
    processed.mkdir()
    (processed / "succes_1.json").write_text("ancien", encoding="utf-8")
    (inbox / "succes_1.json").write_text(json.dumps(_valid_export()), encoding="utf-8")

    scan_once(conn, inbox)

    assert (processed / "succes_1.json").read_text(encoding="utf-8") == "ancien"
    assert len(list(processed.glob("succes_1*.json"))) == 2
