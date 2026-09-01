import json
from datetime import UTC, datetime

import pytest

from extractor.export import (
    build_export,
    build_game_export,
    cover_url,
    icon_url,
    write_export,
)
from extractor.library import GameActivity
from extractor.steam_paths import GameFiles
from tests.fixtures.build_fixtures import build_schema_bin, build_userstats_bin

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
    "stat_id": "1",
    "bit": 2,
    "api_name": "ACH02",
    "english": "Age of the Stars",
    "french": "Age des etoiles",
    "desc_english": "Reached the Age of the Stars ending.",
    "desc_french": "Fin de l'Age des etoiles atteinte.",
    "icon": "bbb222.jpg",
    "icon_gray": "bbb222_gray.jpg",
    "hidden": 0,
}


def _write_game(tmp_path, appid=1245620, account="555", achievements=(ACH_A, ACH_B), unlocks=None):
    schema_path = tmp_path / f"UserGameStatsSchema_{appid}.bin"
    stats_path = tmp_path / f"UserGameStats_{account}_{appid}.bin"
    schema_path.write_bytes(build_schema_bin(appid, "Elden Ring", list(achievements)))
    stats_path.write_bytes(
        build_userstats_bin(unlocks if unlocks is not None else {"1": {1: 1710265440}})
    )
    return GameFiles(appid=appid, schema_path=schema_path, stats_path=stats_path)


def test_icon_url_builds_steam_cdn_path():
    # Chemin community_assets : l'ancien steamcommunity/public ne sert plus les
    # icones recemment ajoutees (constate sur Palworld).
    assert icon_url(1245620, "aaa111.jpg") == (
        "https://shared.akamai.steamstatic.com/community_assets/images/apps/1245620/aaa111.jpg"
    )


def test_icon_url_returns_empty_string_when_no_icon():
    assert icon_url(1245620, "") == ""


def test_build_game_export_marks_unlocked_and_locked(tmp_path):
    result = build_game_export(_write_game(tmp_path))
    by_name = {a["api_name"]: a for a in result["achievements"]}
    assert by_name["ACH01"]["unlocked"] is True
    assert by_name["ACH02"]["unlocked"] is False


def test_build_game_export_converts_unlock_time_to_iso_utc(tmp_path):
    game = _write_game(tmp_path, unlocks={"1": {1: 1710265440}})
    result = build_game_export(game)
    expected = datetime.fromtimestamp(1710265440, tz=UTC).isoformat()
    unlocked = next(a for a in result["achievements"] if a["api_name"] == "ACH01")
    assert unlocked["unlock_time"] == expected


def test_build_game_export_sets_null_unlock_time_when_locked(tmp_path):
    locked = next(
        a for a in build_game_export(_write_game(tmp_path))["achievements"]
        if a["api_name"] == "ACH02"
    )
    assert locked["unlock_time"] is None


def test_build_game_export_includes_name_and_appid(tmp_path):
    result = build_game_export(_write_game(tmp_path))
    assert result["appid"] == 1245620
    assert result["name"] == "Elden Ring"


def test_cover_url_builds_steam_library_art_path():
    assert cover_url(1245620) == (
        "https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/library_600x900.jpg"
    )


def test_build_game_export_includes_global_percent(tmp_path):
    result = build_game_export(_write_game(tmp_path), global_percentages={"ACH01": 10.4})
    par_nom = {a["api_name"]: a for a in result["achievements"]}
    assert par_nom["ACH01"]["global_percent"] == 10.4


def test_build_game_export_sets_null_global_percent_when_unknown(tmp_path):
    result = build_game_export(_write_game(tmp_path), global_percentages={"ACH01": 10.4})
    par_nom = {a["api_name"]: a for a in result["achievements"]}
    assert par_nom["ACH02"]["global_percent"] is None


def test_build_export_passes_global_percentages_by_appid(tmp_path):
    game = _write_game(tmp_path, appid=1245620)

    export = build_export([game], account_id="555", global_percentages={1245620: {"ACH01": 42.0}})

    par_nom = {a["api_name"]: a for a in export["games"][0]["achievements"]}
    assert par_nom["ACH01"]["global_percent"] == 42.0


def test_build_game_export_includes_cover_url(tmp_path):
    result = build_game_export(_write_game(tmp_path))
    assert result["cover"] == cover_url(1245620)


def test_build_game_export_includes_activity_when_known(tmp_path):
    activity = GameActivity(playtime_minutes=27066, last_played=1775462400)
    result = build_game_export(_write_game(tmp_path), activity=activity)
    assert result["playtime_minutes"] == 27066
    assert result["last_played"] == datetime.fromtimestamp(1775462400, tz=UTC).isoformat()


def test_build_game_export_sets_null_activity_when_unknown(tmp_path):
    result = build_game_export(_write_game(tmp_path), activity=None)
    assert result["playtime_minutes"] is None
    assert result["last_played"] is None


def test_build_game_export_handles_partial_activity(tmp_path):
    activity = GameActivity(playtime_minutes=42, last_played=None)
    result = build_game_export(_write_game(tmp_path), activity=activity)
    assert result["playtime_minutes"] == 42
    assert result["last_played"] is None


def test_build_game_export_prefers_catalog_name_over_schema_name(tmp_path):
    game = _write_game(tmp_path)
    result = build_game_export(game, catalog_name="Nom public officiel")
    assert result["name"] == "Nom public officiel"


def test_build_game_export_falls_back_to_schema_name_when_no_catalog_name(tmp_path):
    game = _write_game(tmp_path)
    result = build_game_export(game, catalog_name=None)
    assert result["name"] == "Elden Ring"


def test_build_game_export_falls_back_to_schema_name_when_catalog_name_empty(tmp_path):
    game = _write_game(tmp_path)
    result = build_game_export(game, catalog_name="")
    assert result["name"] == "Elden Ring"


def test_build_export_skips_unreadable_game_and_continues(tmp_path):
    good = _write_game(tmp_path, appid=1245620)
    broken_schema = tmp_path / "UserGameStatsSchema_999.bin"
    broken_stats = tmp_path / "UserGameStats_555_999.bin"
    broken_schema.write_bytes(b"\x99corrompu\x00")
    broken_stats.write_bytes(b"\x08")
    broken = GameFiles(appid=999, schema_path=broken_schema, stats_path=broken_stats)

    export = build_export([broken, good], account_id="555")

    assert [g["appid"] for g in export["games"]] == [1245620]


def test_build_export_uses_catalog_names_when_provided(tmp_path):
    game = _write_game(tmp_path, appid=2651280)

    export = build_export(
        [game], account_id="555", catalog_names={2651280: "Marvel's Spider-Man 2"}
    )

    assert export["games"][0]["name"] == "Marvel's Spider-Man 2"


def test_build_export_falls_back_to_schema_name_for_appid_missing_from_catalog(tmp_path):
    game = _write_game(tmp_path, appid=1245620)

    export = build_export([game], account_id="555", catalog_names={999999: "Autre jeu"})

    assert export["games"][0]["name"] == "Elden Ring"


def test_build_export_excludes_not_found_game_with_zero_unlocks(tmp_path):
    game = _write_game(tmp_path, appid=999999, unlocks={})

    export = build_export([game], account_id="555", not_found_appids={999999})

    assert export["games"] == []


def test_build_export_keeps_not_found_game_with_at_least_one_unlock(tmp_path):
    # Jeu ferme depuis (plus de fiche boutique) mais reellement joue : ses
    # succes reels ne doivent pas disparaitre de l'outil.
    game = _write_game(tmp_path, appid=200110, unlocks={"1": {1: 1710265440}})

    export = build_export([game], account_id="555", not_found_appids={200110})

    assert [g["appid"] for g in export["games"]] == [200110]
    assert export["games"][0]["name"] == "Elden Ring"  # repli sur le nom local du schema


def test_build_export_passes_activity_through_by_appid(tmp_path):
    game = _write_game(tmp_path, appid=1245620)
    activity = {1245620: GameActivity(playtime_minutes=900, last_played=1775462400)}

    export = build_export([game], account_id="555", activity=activity)

    assert export["games"][0]["playtime_minutes"] == 900


def test_build_export_leaves_activity_null_for_appid_without_data(tmp_path):
    game = _write_game(tmp_path, appid=1245620)

    export = build_export([game], account_id="555", activity={999: GameActivity(1, 2)})

    assert export["games"][0]["playtime_minutes"] is None
    assert export["games"][0]["last_played"] is None


def test_build_export_keeps_game_with_zero_unlocks_when_not_in_not_found_set(tmp_path):
    # Jeu recemment ajoute a la bibliotheque, pas encore joue : doit rester
    # visible tant qu'il n'est pas confirme absent du store.
    game = _write_game(tmp_path, appid=1245620, unlocks={})

    export = build_export([game], account_id="555", not_found_appids=set())

    assert [g["appid"] for g in export["games"]] == [1245620]


def test_build_export_includes_metadata(tmp_path):
    export = build_export([_write_game(tmp_path)], account_id="555")
    assert export["account_id"] == "555"
    assert export["steam_id64"] == 76561197960266283
    datetime.fromisoformat(export["exported_at"])  # ne doit pas lever


def test_write_export_creates_timestamped_json(tmp_path):
    export = {"exported_at": "2026-08-24T22:10:00+00:00", "games": []}
    path = write_export(export, tmp_path)
    assert path.parent == tmp_path
    assert path.name.startswith("succes_") and path.name.endswith(".json")
    assert json.loads(path.read_text(encoding="utf-8")) == export


def test_write_export_leaves_no_temp_file_behind(tmp_path):
    write_export({"exported_at": "x", "games": []}, tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_export_raises_when_target_dir_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="dossier de destination"):
        write_export({"games": []}, tmp_path / "absent")
