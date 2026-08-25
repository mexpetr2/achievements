"""Construit des fichiers VDF binaires synthetiques imitant le cache Steam."""

import struct


def _s(key: str, value: str) -> bytes:
    """Entree chaine."""
    return b"\x01" + key.encode("utf-8") + b"\x00" + value.encode("utf-8") + b"\x00"


def _i(key: str, value: int) -> bytes:
    """Entree int32."""
    return b"\x02" + key.encode("utf-8") + b"\x00" + struct.pack("<i", value)


def _obj(key: str, body: bytes) -> bytes:
    """Objet imbrique."""
    return b"\x00" + key.encode("utf-8") + b"\x00" + body + b"\x08"


def build_schema_bin(appid: int, gamename: str, achievements: list[dict]) -> bytes:
    """Construit un UserGameStatsSchema_<appid>.bin synthetique.

    Chaque element de `achievements` est un dict avec les cles :
    stat_id, bit, api_name, english, french, desc_english, desc_french,
    icon, icon_gray, hidden.
    """
    by_stat: dict[str, list[dict]] = {}
    for ach in achievements:
        by_stat.setdefault(ach["stat_id"], []).append(ach)

    stats_body = b""
    for stat_id, entries in by_stat.items():
        bits_body = b""
        for ach in entries:
            display = _obj(
                "display",
                _obj("name", _s("english", ach["english"]) + _s("french", ach["french"]))
                + _obj(
                    "desc",
                    _s("english", ach["desc_english"]) + _s("french", ach["desc_french"]),
                )
                + _s("icon", ach["icon"])
                + _s("icon_gray", ach["icon_gray"])
                + _i("hidden", ach["hidden"]),
            )
            bits_body += _obj(str(ach["bit"]), _s("name", ach["api_name"]) + display)
        stats_body += _obj(stat_id, _i("type", 4) + _obj("bits", bits_body))

    return _obj(
        str(appid),
        _obj("stats", stats_body) + _i("version", 1) + _s("gamename", gamename),
    )


def build_userstats_bin(unlocks: dict[str, dict[int, int]]) -> bytes:
    """Construit un UserGameStats_<account>_<appid>.bin synthetique.

    `unlocks` associe un stat_id a {bit_index: horodatage_unix}.
    """
    cache_body = b""
    for stat_id, times in unlocks.items():
        bitfield = 0
        times_body = b""
        for bit, timestamp in times.items():
            bitfield |= 1 << bit
            times_body += _i(str(bit), timestamp)
        cache_body += _obj(
            stat_id,
            _i("data", bitfield)
            + _i("state", 2)
            + _i("pendingbits", 0)
            + _obj("AchievementTimes", times_body),
        )
    return _obj("cache", _i("crc", 0) + _i("PendingChanges", 1) + cache_body)
