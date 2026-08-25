from extractor.binary_vdf import parse_binary_vdf
from tests.fixtures.build_fixtures import build_schema_bin, build_userstats_bin


def test_built_schema_roundtrips_through_parser():
    raw = build_schema_bin(
        appid=1245620,
        gamename="Elden Ring",
        achievements=[
            {
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
        ],
    )
    parsed = parse_binary_vdf(raw)
    bit = parsed["1245620"]["stats"]["1"]["bits"]["1"]
    assert parsed["1245620"]["gamename"] == "Elden Ring"
    assert bit["name"] == "ACH01"
    assert bit["display"]["name"]["french"] == "Seigneur d'Elden"
    assert bit["display"]["icon"] == "aaa111.jpg"


def test_built_userstats_roundtrips_through_parser():
    raw = build_userstats_bin(unlocks={"1": {1: 1710265440, 4: 1710265450}})
    parsed = parse_binary_vdf(raw)
    times = parsed["cache"]["1"]["AchievementTimes"]
    assert times == {"1": 1710265440, "4": 1710265450}
