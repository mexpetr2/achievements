import json

from extractor.__main__ import main
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


def _fake_stats_dir(tmp_path):
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "UserGameStatsSchema_1245620.bin").write_bytes(
        build_schema_bin(1245620, "Elden Ring", [ACH])
    )
    (stats / "UserGameStats_555_1245620.bin").write_bytes(
        build_userstats_bin({"1": {1: 1710265440}})
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
        return {1245620: "Nom public resolu"}

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


def test_main_reports_missing_output_dir(tmp_path, capsys):
    stats = _fake_stats_dir(tmp_path)
    code = main(["--stats-dir", str(stats), "--output-dir", str(tmp_path / "absent")])
    assert code == 1
    assert "dossier de destination introuvable" in capsys.readouterr().err


def test_main_reports_missing_steam_dir(tmp_path, capsys):
    out = tmp_path / "partage"
    out.mkdir()
    code = main(["--stats-dir", str(tmp_path / "nulle-part"), "--output-dir", str(out)])
    assert code == 1
    assert "Steam" in capsys.readouterr().err
