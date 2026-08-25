import json

from extractor.__main__ import main
from extractor.steam_catalog import CatalogLookup
from tests.fixtures.build_fixtures import build_schema_bin, build_userstats_bin

ACH = {
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


def _fake_stats_dir(tmp_path, unlocks=None):
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "UserGameStatsSchema_1245620.bin").write_bytes(
        build_schema_bin(1245620, "Elden Ring", [ACH])
    )
    (stats / "UserGameStats_555_1245620.bin").write_bytes(
        build_userstats_bin(unlocks if unlocks is not None else {"1": {1: 1710265440}})
    )
    return stats


def test_main_writes_export_and_returns_zero(tmp_path, capsys):
    stats = _fake_stats_dir(tmp_path)
    out = tmp_path / "partage"
    out.mkdir()

    code = main(
        ["--stats-dir", str(stats), "--output-dir", str(out), "--no-catalog-lookup"]
    )

    assert code == 0
    exports = list(out.glob("succes_*.json"))
    assert len(exports) == 1
    payload = json.loads(exports[0].read_text(encoding="utf-8"))
    assert payload["games"][0]["name"] == "Elden Ring"
    assert "1 jeu" in capsys.readouterr().out


def test_main_uses_resolved_catalog_name(tmp_path):
    stats = _fake_stats_dir(tmp_path)
    out = tmp_path / "partage"
    out.mkdir()

    def fake_resolve(appids, cache_path, **kwargs):
        assert list(appids) == [1245620]
        return CatalogLookup(names={1245620: "Nom public resolu"}, not_found=set())

    code = main(
        ["--stats-dir", str(stats), "--output-dir", str(out)],
        resolve_names=fake_resolve,
    )

    assert code == 0
    payload = json.loads(next(out.glob("succes_*.json")).read_text(encoding="utf-8"))
    assert payload["games"][0]["name"] == "Nom public resolu"


def test_main_skips_catalog_lookup_when_flag_set(tmp_path):
    stats = _fake_stats_dir(tmp_path)
    out = tmp_path / "partage"
    out.mkdir()

    def boom(appids, cache_path, **kwargs):
        raise AssertionError("le catalogue ne doit pas etre interroge avec --no-catalog-lookup")

    code = main(
        ["--stats-dir", str(stats), "--output-dir", str(out), "--no-catalog-lookup"],
        resolve_names=boom,
    )

    assert code == 0
    payload = json.loads(next(out.glob("succes_*.json")).read_text(encoding="utf-8"))
    assert payload["games"][0]["name"] == "Elden Ring"


def test_main_excludes_games_confirmed_absent_from_store_with_no_unlocks(tmp_path, capsys):
    # App sans fiche boutique ET aucun succes reel : vrai outil/test interne,
    # a exclure.
    stats = _fake_stats_dir(tmp_path, unlocks={})
    out = tmp_path / "partage"
    out.mkdir()

    def fake_resolve(appids, cache_path, **kwargs):
        return CatalogLookup(names={}, not_found={1245620})

    code = main(
        ["--stats-dir", str(stats), "--output-dir", str(out)],
        resolve_names=fake_resolve,
    )

    assert code == 0
    payload = json.loads(next(out.glob("succes_*.json")).read_text(encoding="utf-8"))
    assert payload["games"] == []
    assert "0 jeu" in capsys.readouterr().out


def test_main_keeps_games_confirmed_absent_from_store_but_with_real_unlocks(tmp_path):
    # Jeu ferme depuis (plus de fiche boutique) mais reellement joue : ses
    # succes ne doivent pas disparaitre de l'outil.
    stats = _fake_stats_dir(tmp_path)  # unlocks par defaut : ACH01 debloque
    out = tmp_path / "partage"
    out.mkdir()

    def fake_resolve(appids, cache_path, **kwargs):
        return CatalogLookup(names={}, not_found={1245620})

    code = main(
        ["--stats-dir", str(stats), "--output-dir", str(out)],
        resolve_names=fake_resolve,
    )

    assert code == 0
    payload = json.loads(next(out.glob("succes_*.json")).read_text(encoding="utf-8"))
    assert [g["appid"] for g in payload["games"]] == [1245620]


def test_main_reports_missing_output_dir(tmp_path, capsys):
    stats = _fake_stats_dir(tmp_path)
    code = main(
        [
            "--stats-dir",
            str(stats),
            "--output-dir",
            str(tmp_path / "absent"),
            "--no-catalog-lookup",
        ]
    )
    assert code == 1
    assert "dossier de destination introuvable" in capsys.readouterr().err


def test_main_reports_missing_steam_dir(tmp_path, capsys):
    out = tmp_path / "partage"
    out.mkdir()
    code = main(
        [
            "--stats-dir",
            str(tmp_path / "nulle-part"),
            "--output-dir",
            str(out),
            "--no-catalog-lookup",
        ]
    )
    assert code == 1
    assert "Steam" in capsys.readouterr().err
