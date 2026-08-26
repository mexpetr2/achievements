"""Tests de la lecture du temps de jeu et du dernier lancement (localconfig.vdf)."""

from extractor.library import GameActivity, read_activity

LOCALCONFIG = """
"UserLocalConfigStore"
{
    "Software"
    {
        "Valve"
        {
            "Steam"
            {
                "apps"
                {
                    "1245620"
                    {
                        "LastPlayed"  "1787600904"
                        "Playtime"    "15"
                    }
                    "230410"
                    {
                        "LastPlayed"  "1775462400"
                        "Playtime"    "27066"
                    }
                    "999"
                    {
                        "LastPlayed"  "1775462400"
                    }
                    "888"
                    {
                        "Playtime"    "42"
                    }
                    "777"
                    {
                        "BadgeData"  "020000000809"
                    }
                }
            }
        }
    }
}
"""


def _write(tmp_path, content=LOCALCONFIG):
    path = tmp_path / "localconfig.vdf"
    path.write_text(content, encoding="utf-8")
    return path


def test_read_activity_returns_playtime_and_last_played(tmp_path):
    activity = read_activity(_write(tmp_path))
    assert activity[1245620] == GameActivity(playtime_minutes=15, last_played=1787600904)


def test_read_activity_handles_large_playtime(tmp_path):
    activity = read_activity(_write(tmp_path))
    assert activity[230410].playtime_minutes == 27066


def test_read_activity_allows_missing_playtime(tmp_path):
    activity = read_activity(_write(tmp_path))
    assert activity[999] == GameActivity(playtime_minutes=None, last_played=1775462400)


def test_read_activity_allows_missing_last_played(tmp_path):
    activity = read_activity(_write(tmp_path))
    assert activity[888] == GameActivity(playtime_minutes=42, last_played=None)


def test_read_activity_skips_apps_without_any_activity_field(tmp_path):
    assert 777 not in read_activity(_write(tmp_path))


def test_read_activity_returns_empty_when_file_missing(tmp_path):
    assert read_activity(tmp_path / "absent.vdf") == {}


def test_read_activity_returns_empty_when_structure_unexpected(tmp_path):
    path = _write(tmp_path, '"AutreChose" { "x" "y" }')
    assert read_activity(path) == {}


def test_read_activity_ignores_non_numeric_appid_keys(tmp_path):
    content = """
    "UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" {
        "pas_un_appid" { "Playtime" "10" }
        "1" { "Playtime" "10" }
    } } } } }
    """
    activity = read_activity(_write(tmp_path, content))
    assert list(activity) == [1]


def test_read_activity_ignores_non_numeric_values(tmp_path):
    content = """
    "UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" {
        "1" { "Playtime" "beaucoup" "LastPlayed" "hier" }
    } } } } }
    """
    assert read_activity(_write(tmp_path, content)) == {}


def test_read_activity_matches_keys_case_insensitively(tmp_path):
    content = """
    "userlocalconfigstore" { "software" { "valve" { "steam" { "apps" {
        "1" { "playtime" "10" "lastplayed" "1775462400" }
    } } } } }
    """
    activity = read_activity(_write(tmp_path, content))
    assert activity[1] == GameActivity(playtime_minutes=10, last_played=1775462400)
