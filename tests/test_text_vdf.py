"""Tests du parseur VDF texte (localconfig.vdf), distinct du format binaire."""

from extractor.text_vdf import parse_text_vdf


def test_parse_flat_key_value():
    assert parse_text_vdf('"nom"  "valeur"') == {"nom": "valeur"}


def test_parse_nested_block():
    text = """
    "racine"
    {
        "cle"  "valeur"
    }
    """
    assert parse_text_vdf(text) == {"racine": {"cle": "valeur"}}


def test_parse_deeply_nested_blocks():
    text = """
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
                    }
                }
            }
        }
    }
    """
    parsed = parse_text_vdf(text)
    app = parsed["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]["1245620"]
    assert app == {"LastPlayed": "1787600904", "Playtime": "15"}


def test_parse_multiple_siblings_keep_independent_values():
    text = """
    "apps"
    {
        "1"  { "Playtime" "10" }
        "2"  { "Playtime" "20" }
    }
    """
    assert parse_text_vdf(text)["apps"] == {
        "1": {"Playtime": "10"},
        "2": {"Playtime": "20"},
    }


def test_parse_keeps_slashes_inside_quoted_values():
    assert parse_text_vdf('"url"  "https://exemple.test/a"') == {"url": "https://exemple.test/a"}


def test_parse_returns_empty_dict_for_empty_input():
    assert parse_text_vdf("") == {}


def test_parse_tolerates_unclosed_block():
    assert parse_text_vdf('"racine" { "cle" "valeur"') == {"racine": {"cle": "valeur"}}


def test_parse_tolerates_extra_closing_brace():
    assert parse_text_vdf('"cle" "valeur" }') == {"cle": "valeur"}


def test_parse_handles_accented_values():
    assert parse_text_vdf('"jeu"  "Cercle d\'Elden"') == {"jeu": "Cercle d'Elden"}
