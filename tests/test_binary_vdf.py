import struct

import pytest

from extractor.binary_vdf import VdfParseError, parse_binary_vdf


def test_parse_flat_string_value():
    # 0x01 = chaine ; cle "name" ; valeur "Elden Ring" ; 0x08 = fin
    data = b"\x01name\x00Elden Ring\x00\x08"
    assert parse_binary_vdf(data) == {"name": "Elden Ring"}


def test_parse_int32_value():
    data = b"\x02count\x00" + struct.pack("<i", 42) + b"\x08"
    assert parse_binary_vdf(data) == {"count": 42}


def test_parse_nested_object():
    data = b"\x00display\x00" + b"\x01english\x00Elden Lord\x00" + b"\x08" + b"\x08"
    assert parse_binary_vdf(data) == {"display": {"english": "Elden Lord"}}


def test_parse_deeply_nested_structure():
    inner = b"\x01name\x00ACH01\x00\x08"
    middle = b"\x00" + b"1\x00" + inner + b"\x08"
    outer = b"\x00bits\x00" + middle + b"\x08"
    assert parse_binary_vdf(outer) == {"bits": {"1": {"name": "ACH01"}}}


def test_parse_utf8_accented_text():
    data = "\x01french\x00Cercle d'Elden\x00\x08".encode("utf-8")
    assert parse_binary_vdf(data) == {"french": "Cercle d'Elden"}


def test_parse_uint64_value():
    data = b"\x07id\x00" + struct.pack("<Q", 76561197960265728) + b"\x08"
    assert parse_binary_vdf(data) == {"id": 76561197960265728}


def test_parse_float32_value():
    data = b"\x03ratio\x00" + struct.pack("<f", 1.5) + b"\x08"
    assert parse_binary_vdf(data) == {"ratio": pytest.approx(1.5)}


def test_parse_stops_at_top_level_end_marker():
    data = b"\x01a\x00x\x00\x08\x01b\x00y\x00"
    assert parse_binary_vdf(data) == {"a": "x"}


def test_parse_tolerates_missing_trailing_end_marker():
    # Certains fichiers Steam se terminent sans 0x08 final
    data = b"\x01name\x00Terraria\x00"
    assert parse_binary_vdf(data) == {"name": "Terraria"}


def test_unknown_type_byte_raises():
    data = b"\x99broken\x00"
    with pytest.raises(VdfParseError, match="type inconnu"):
        parse_binary_vdf(data)


def test_truncated_string_raises():
    data = b"\x01name\x00Elden Ring"
    with pytest.raises(VdfParseError, match="chaine non terminee"):
        parse_binary_vdf(data)


def test_truncated_int_raises():
    data = b"\x02count\x00\x01\x02"
    with pytest.raises(VdfParseError, match="donnees tronquees"):
        parse_binary_vdf(data)
