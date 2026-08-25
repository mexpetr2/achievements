import pytest

from extractor.schema import AchievementDef, parse_schema
from tests.fixtures.build_fixtures import build_schema_bin

ACH_A = {
    "stat_id": "1",
    "bit": 1,
    "api_name": "ACH01",
    "english": "Elden Lord",
    "french": "Seigneur d'Elden",
    "desc_english": "Obtained the Elden Ring.",
    "desc_french": "Obtenu le Cercle d'Elden.",
    "icon": "aaa111.jpg",
    "icon_gray": "aaa111_gray.jpg",
    "hidden": 0,
}
ACH_B = {
    "stat_id": "2",
    "bit": 5,
    "api_name": "ACH25",
    "english": "Great Rune",
    "french": "Grande Rune",
    "desc_english": "Restored a Great Rune.",
    "desc_french": "Grande Rune restauree.",
    "icon": "bbb222.jpg",
    "icon_gray": "bbb222_gray.jpg",
    "hidden": 1,
}


def test_parse_schema_returns_game_name():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    game = parse_schema(raw, appid=1245620)
    assert game.appid == 1245620
    assert game.name == "Elden Ring"


def test_parse_schema_keys_achievements_by_stat_and_bit():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A, ACH_B])
    game = parse_schema(raw, appid=1245620)
    assert set(game.achievements) == {("1", 1), ("2", 5)}


def test_parse_schema_prefers_french_labels():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    ach = parse_schema(raw, appid=1245620).achievements[("1", 1)]
    assert ach == AchievementDef(
        api_name="ACH01",
        name="Seigneur d'Elden",
        description="Obtenu le Cercle d'Elden.",
        icon="aaa111.jpg",
        icon_gray="aaa111_gray.jpg",
        hidden=False,
    )


def test_parse_schema_falls_back_to_english_when_french_missing():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    # Retirer la traduction francaise du nom
    raw = raw.replace("\x01french\x00Seigneur d'Elden\x00".encode("utf-8"), b"", 1)
    ach = parse_schema(raw, appid=1245620).achievements[("1", 1)]
    assert ach.name == "Elden Lord"


def test_parse_schema_marks_hidden_achievements():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A, ACH_B])
    achievements = parse_schema(raw, appid=1245620).achievements
    assert achievements[("1", 1)].hidden is False
    assert achievements[("2", 5)].hidden is True


def test_parse_schema_without_gamename_uses_appid_placeholder():
    raw = build_schema_bin(999999, "Temp", [ACH_A])
    raw = raw.replace(b"\x01gamename\x00Temp\x00", b"", 1)
    assert parse_schema(raw, appid=999999).name == "App 999999"


def test_parse_schema_rejects_placeholder_valve_names():
    raw = build_schema_bin(730, "ValveTestApp260", [ACH_A])
    assert parse_schema(raw, appid=730).name == "App 730"


def test_parse_schema_missing_appid_key_raises():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    with pytest.raises(KeyError):
        parse_schema(raw, appid=111111)
