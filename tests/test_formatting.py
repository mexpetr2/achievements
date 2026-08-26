"""Tests du formatage d'affichage (durees de jeu, dates)."""

from web.formatting import format_date, format_playtime


def test_format_playtime_shows_minutes_under_an_hour():
    assert format_playtime(45) == "45 min"


def test_format_playtime_shows_hours_and_minutes():
    assert format_playtime(150) == "2 h 30"


def test_format_playtime_omits_zero_minutes():
    assert format_playtime(120) == "2 h"


def test_format_playtime_handles_large_values():
    assert format_playtime(27066) == "451 h 6"


def test_format_playtime_handles_zero():
    assert format_playtime(0) == "jamais lance"


def test_format_playtime_handles_unknown():
    assert format_playtime(None) == "temps inconnu"


def test_format_date_renders_day_first():
    assert format_date("2026-04-06T10:00:00+00:00") == "06/04/2026"


def test_format_date_accepts_date_only_string():
    assert format_date("2026-04-06") == "06/04/2026"


def test_format_date_returns_placeholder_for_none():
    assert format_date(None) == "jamais"


def test_format_date_returns_placeholder_for_unparsable_value():
    assert format_date("pas une date") == "jamais"
