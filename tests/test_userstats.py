from extractor.userstats import parse_userstats
from tests.fixtures.build_fixtures import build_userstats_bin


def test_parse_userstats_keys_unlocks_by_stat_and_bit():
    raw = build_userstats_bin({"1": {1: 1710265440, 4: 1710265450}})
    assert parse_userstats(raw) == {("1", 1): 1710265440, ("1", 4): 1710265450}


def test_parse_userstats_handles_multiple_stat_blocks():
    raw = build_userstats_bin({"1": {1: 1000}, "2": {5: 2000}})
    assert parse_userstats(raw) == {("1", 1): 1000, ("2", 5): 2000}


def test_parse_userstats_returns_empty_when_nothing_unlocked():
    raw = build_userstats_bin({})
    assert parse_userstats(raw) == {}


def test_parse_userstats_ignores_non_numeric_cache_keys():
    # 'crc' et 'PendingChanges' sont des cles de service, pas des stat ids
    raw = build_userstats_bin({"1": {1: 1000}})
    result = parse_userstats(raw)
    assert all(stat_id.isdigit() for stat_id, _ in result)


def test_parse_userstats_returns_empty_when_cache_absent():
    assert parse_userstats(b"\x01other\x00value\x00\x08") == {}
