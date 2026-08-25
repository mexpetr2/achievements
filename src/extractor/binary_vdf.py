"""Parseur du format VDF binaire utilise par les fichiers .bin du cache Steam.

Format : chaque entree est [octet de type][cle terminee par \\x00][valeur].
Un objet se termine par l'octet 0x08.
"""

import struct

BIN_NONE = 0x00
BIN_STRING = 0x01
BIN_INT32 = 0x02
BIN_FLOAT32 = 0x03
BIN_POINTER = 0x04
BIN_WIDESTRING = 0x05
BIN_COLOR = 0x06
BIN_UINT64 = 0x07
BIN_END = 0x08
BIN_INT64 = 0x0A


class VdfParseError(ValueError):
    """Leve quand les octets ne respectent pas le format VDF binaire attendu."""


def parse_binary_vdf(data: bytes) -> dict:
    """Parse des octets VDF binaires en dictionnaire imbrique."""
    result, _ = _parse_object(data, 0)
    return result


def _read_cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end == -1:
        raise VdfParseError(f"chaine non terminee a la position {pos}")
    return data[pos:end].decode("utf-8", errors="replace"), end + 1


def _read_struct(data: bytes, pos: int, fmt: str, size: int):
    if pos + size > len(data):
        raise VdfParseError(f"donnees tronquees a la position {pos}")
    return struct.unpack_from(fmt, data, pos)[0], pos + size


def _parse_object(data: bytes, pos: int) -> tuple[dict, int]:
    result: dict = {}
    while pos < len(data):
        type_byte = data[pos]
        pos += 1

        if type_byte == BIN_END:
            return result, pos

        key, pos = _read_cstring(data, pos)

        if type_byte == BIN_NONE:
            value, pos = _parse_object(data, pos)
        elif type_byte in (BIN_STRING, BIN_WIDESTRING):
            value, pos = _read_cstring(data, pos)
        elif type_byte in (BIN_INT32, BIN_POINTER, BIN_COLOR):
            value, pos = _read_struct(data, pos, "<i", 4)
        elif type_byte == BIN_FLOAT32:
            value, pos = _read_struct(data, pos, "<f", 4)
        elif type_byte == BIN_UINT64:
            value, pos = _read_struct(data, pos, "<Q", 8)
        elif type_byte == BIN_INT64:
            value, pos = _read_struct(data, pos, "<q", 8)
        else:
            raise VdfParseError(f"type inconnu {type_byte:#04x} a la position {pos - 1}")

        result[key] = value

    return result, pos
