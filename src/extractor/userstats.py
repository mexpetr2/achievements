"""Lecture de l'etat de deblocage depuis UserGameStats_<account>_<appid>.bin."""

from extractor.binary_vdf import parse_binary_vdf


def parse_userstats(data: bytes) -> dict[tuple[str, int], int]:
    """Retourne {(stat_id, bit_index): horodatage_unix} pour les succes debloques.

    On lit `AchievementTimes` plutot que le bitfield `data` : les deux portent
    exactement les memes bits, mais `AchievementTimes` fournit en plus la date.
    """
    parsed = parse_binary_vdf(data)
    cache = parsed.get("cache")
    if not isinstance(cache, dict):
        return {}

    unlocks: dict[tuple[str, int], int] = {}
    for stat_id, block in cache.items():
        if not str(stat_id).isdigit() or not isinstance(block, dict):
            continue
        times = block.get("AchievementTimes")
        if not isinstance(times, dict):
            continue
        for bit_index, timestamp in times.items():
            if str(bit_index).isdigit() and isinstance(timestamp, int):
                unlocks[(str(stat_id), int(bit_index))] = timestamp
    return unlocks
