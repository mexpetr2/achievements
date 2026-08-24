# Plan d'implémentation — Outil de suivi et visualisation de succès de jeux (v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraire l'état réel des succès depuis les fichiers locaux de Steam sur le PC Windows, l'exporter en JSON lisible vers un dossier partagé, et l'afficher dans un tableau de bord web Dockerisé hébergé sur le NAS, protégé par mot de passe.

**Architecture :** Deux composants indépendants reliés uniquement par des fichiers JSON déposés dans un dossier partagé. L'extracteur (PC) parse les fichiers VDF binaires du cache Steam et écrit un JSON horodaté. L'appli web (NAS, Docker) surveille ce dossier, ingère les JSON dans SQLite, et sert un tableau de bord Flask. Aucun appel réseau vers Steam.

**Tech Stack :** Python 3.11, Flask, SQLite (stdlib `sqlite3`), pytest, ruff, Docker.

---

## Découvertes techniques validées sur la machine cible

Ces faits ont été vérifiés en exécutant des sondes sur l'installation Steam réelle. Ils orientent le plan et **remplacent** deux hypothèses de la spec :

1. **Emplacement des données :** `C:\Program Files (x86)\Steam\appcache\stats\` contient deux familles de fichiers VDF binaires :
   - `UserGameStatsSchema_<appid>.bin` — définitions des succès (nom API, libellés localisés, descriptions, icônes)
   - `UserGameStats_<accountid>_<appid>.bin` — état de déblocage de l'utilisateur
   Sur cette machine : **95 jeux**, avec les deux fichiers présents pour chacun (aucun orphelin).

2. **La limitation « jeux installés uniquement » de la spec ne s'applique pas.** Les 95 jeux présents dans `appcache/stats` incluent des jeux joués puis désinstallés. On énumère donc directement depuis ce dossier — **pas besoin des fichiers `.acf`** comme source principale.

3. **Format VDF binaire.** Chaque valeur est précédée d'un octet de type, suivi d'une clé terminée par `\x00` :
   - `0x00` = objet imbriqué (récursion jusqu'à `0x08`)
   - `0x01` = chaîne UTF-8 terminée par `\x00`
   - `0x02` = int32 little-endian (4 octets)
   - `0x08` = fin d'objet
   Les types `0x03` (float32), `0x07` (uint64) et `0x0A` (int64) n'apparaissent pas dans les 95 fichiers testés mais doivent être gérés défensivement.

4. **Mapping succès ↔ déblocage (point le plus subtil).** Les index de bits sont **relatifs à chaque « stat id »**, pas globaux. Une première hypothèse d'index global s'est révélée fausse (15 correspondances sur 34). La clé correcte est le couple `(stat_id, bit_index)` :
   - Schéma : `<appid>.stats.<stat_id>.bits.<bit_index>` → `{name, display:{name:{english,french,...}, desc:{...}, icon, icon_gray}, hidden}`
   - État : `cache.<stat_id>.AchievementTimes.<bit_index>` → horodatage Unix du déblocage
   Validé sur Elden Ring : 42 succès dans le schéma, **34/34 déblocages associés**. Le bitfield `cache.<stat_id>.data` est parfaitement redondant avec les clés de `AchievementTimes` — on utilise `AchievementTimes` car il porte en plus la date.

5. **Noms de jeux :** `<appid>.gamename` est présent dans 90/95 schémas. 5 n'en ont aucun, et certains portent un nom de code interne (`ValveTestApp260` pour l'appid 730). Repli : `gamename` si exploitable, sinon `App <appid>`.

6. **Icônes :** les icônes de succès ne sont pas présentes dans `appcache\librarycache\` sous une forme exploitable. On stocke donc l'URL CDN Steam construite depuis le nom de fichier du schéma :
   `https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/<appid>/<icon>.jpg`
   Le navigateur du visiteur la chargera — ni le NAS ni le PC ne font de requête réseau.

7. **Compte Steam :** l'identifiant présent dans les noms de fichiers (`145526594`) est un **account ID Steam3**, pas un SteamID64. Conversion : `steamid64 = accountid + 76561197960265728`.

---

## Structure des fichiers

```
S:\Achievements\
├── src/
│   ├── extractor/                  # Composant PC Windows
│   │   ├── __init__.py
│   │   ├── binary_vdf.py           # Parseur VDF binaire (pur, sans I/O)
│   │   ├── steam_paths.py          # Localisation Steam + compte + decouverte
│   │   ├── schema.py               # Schema .bin -> definitions de succes
│   │   ├── userstats.py            # UserGameStats .bin -> etats debloques
│   │   ├── export.py               # Assemblage + ecriture du JSON
│   │   └── __main__.py             # CLI: python -m extractor
│   └── web/                        # Composant NAS Docker
│       ├── __init__.py
│       ├── db.py                   # Schema SQLite + connexion
│       ├── ingest.py               # JSON -> SQLite
│       ├── watcher.py              # Tache de fond (poll du dossier)
│       ├── auth.py                 # Mot de passe + session
│       ├── queries.py              # Requetes de lecture du tableau de bord
│       ├── app.py                  # Flask: routes + factory
│       ├── wsgi.py                 # Point d'entree production
│       └── templates/
│           ├── base.html
│           ├── login.html
│           ├── index.html
│           └── game.html
├── scripts/
│   └── generate_password_hash.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/build_fixtures.py  # Genere des .bin synthetiques
│   ├── test_binary_vdf.py
│   ├── test_fixtures.py
│   ├── test_schema.py
│   ├── test_userstats.py
│   ├── test_steam_paths.py
│   ├── test_export.py
│   ├── test_cli.py
│   ├── test_db.py
│   ├── test_ingest.py
│   ├── test_watcher.py
│   ├── test_auth.py
│   ├── test_queries.py
│   └── test_web.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

**Principe de découpage :** `binary_vdf.py` est une fonction pure sur des octets (testable sans Steam). Chaque module au-dessus a une responsabilité unique et ne dépend que de la couche inférieure. `extractor/` et `web/` ne s'importent jamais mutuellement — leur seul contrat est le format JSON.

---

## Task 1: Scaffolding du projet

**Files:**
- Create: `pyproject.toml`
- Create: `src/extractor/__init__.py`
- Create: `src/web/__init__.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Créer `pyproject.toml`**

```toml
[project]
name = "achievements"
version = "0.1.0"
description = "Suivi et visualisation de succes de jeux depuis les donnees locales Steam"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src", "."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Créer les paquets vides**

Créer `src/extractor/__init__.py` avec exactement :

```python
"""Extraction des succes depuis les fichiers locaux du client Steam."""
```

Créer `src/web/__init__.py` avec exactement :

```python
"""Application web de visualisation des succes."""
```

Créer `tests/conftest.py` avec exactement :

```python
"""Fixtures partagees par les tests."""
```

- [ ] **Step 3: Créer l'environnement virtuel et installer**

```bash
python -m venv .venv && .venv/Scripts/python.exe -m pip install --upgrade pip && .venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Attendu : `Successfully installed achievements-0.1.0 ... flask ... pytest ... ruff ...`

- [ ] **Step 4: Vérifier que pytest démarre**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Attendu : `no tests ran` — aucune erreur de collecte.

- [ ] **Step 5: Ajouter les exclusions au `.gitignore`**

Le fichier `.gitignore` existe déjà. Ajouter ces lignes à la fin :

```
# Sorties de l'extracteur
exports/
*.json.tmp

# Packaging
*.egg-info/

# Secrets de deploiement
.env
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/extractor/__init__.py src/web/__init__.py tests/conftest.py .gitignore && git commit -m "chore: scaffold project structure and tooling"
```

---

## Task 2: Parseur VDF binaire

Le cœur technique. Fonction pure sur des octets : aucun accès disque, entièrement testable avec des fixtures synthétiques.

**Files:**
- Create: `src/extractor/binary_vdf.py`
- Test: `tests/test_binary_vdf.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_binary_vdf.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_binary_vdf.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.binary_vdf'` — 12 erreurs de collecte.

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/binary_vdf.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_binary_vdf.py -q
```

Attendu : `12 passed`

- [ ] **Step 5: Vérifier le parseur sur les vrais fichiers Steam**

```bash
.venv/Scripts/python.exe -c "import glob; from extractor.binary_vdf import parse_binary_vdf; files = glob.glob(r'C:\Program Files (x86)\Steam\appcache\stats\*.bin'); ok = sum(1 for f in files if parse_binary_vdf(open(f, 'rb').read()) is not None); print(f'{ok}/{len(files)} fichiers parses')"
```

Attendu : `190/190 fichiers parses` (95 schémas + 95 fichiers utilisateur). Les deux nombres doivent être égaux et aucune exception ne doit être levée.

- [ ] **Step 6: Commit**

```bash
git add src/extractor/binary_vdf.py tests/test_binary_vdf.py && git commit -m "feat: add binary VDF parser for Steam cache files"
```

---

## Task 3: Générateur de fixtures .bin synthétiques

Les tâches suivantes ont besoin de fichiers `.bin` réalistes sans dépendre d'une installation Steam. Ce module les construit.

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/build_fixtures.py`
- Test: `tests/test_fixtures.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_fixtures.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_fixtures.py -q
```

Attendu : `ModuleNotFoundError: No module named 'tests.fixtures'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `tests/fixtures/__init__.py` avec exactement :

```python
"""Constructeurs de fichiers .bin synthetiques pour les tests."""
```

Créer `tests/fixtures/build_fixtures.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_fixtures.py -q
```

Attendu : `2 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/ tests/test_fixtures.py && git commit -m "test: add synthetic Steam .bin fixture builders"
```

---

## Task 4: Lecture du schéma des succès

**Files:**
- Create: `src/extractor/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_schema.py` :

```python
import pytest

from extractor.schema import AchievementDef, parse_schema
from tests.fixtures.build_fixtures import build_schema_bin

ACH_A = {
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
ACH_B = {
    "stat_id": "2",
    "bit": 5,
    "api_name": "ACH25",
    "english": "Great Rune",
    "french": "Grande Rune",
    "desc_english": "Restored a Great Rune.",
    "desc_french": "Grande Rune restauree.",
    "icon": "bbb222.jpg",
    "icon_gray": "bbb222_gray.jpg",
    "hidden": 1,
}


def test_parse_schema_returns_game_name():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    game = parse_schema(raw, appid=1245620)
    assert game.appid == 1245620
    assert game.name == "Elden Ring"


def test_parse_schema_keys_achievements_by_stat_and_bit():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A, ACH_B])
    game = parse_schema(raw, appid=1245620)
    assert set(game.achievements) == {("1", 1), ("2", 5)}


def test_parse_schema_prefers_french_labels():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    ach = parse_schema(raw, appid=1245620).achievements[("1", 1)]
    assert ach == AchievementDef(
        api_name="ACH01",
        name="Seigneur d'Elden",
        description="Obtenu le Cercle d'Elden.",
        icon="aaa111.jpg",
        icon_gray="aaa111_gray.jpg",
        hidden=False,
    )


def test_parse_schema_falls_back_to_english_when_french_missing():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    # Retirer la traduction francaise du nom
    raw = raw.replace("\x01french\x00Seigneur d'Elden\x00".encode("utf-8"), b"", 1)
    ach = parse_schema(raw, appid=1245620).achievements[("1", 1)]
    assert ach.name == "Elden Lord"


def test_parse_schema_marks_hidden_achievements():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A, ACH_B])
    achievements = parse_schema(raw, appid=1245620).achievements
    assert achievements[("1", 1)].hidden is False
    assert achievements[("2", 5)].hidden is True


def test_parse_schema_without_gamename_uses_appid_placeholder():
    raw = build_schema_bin(999999, "Temp", [ACH_A])
    raw = raw.replace(b"\x01gamename\x00Temp\x00", b"", 1)
    assert parse_schema(raw, appid=999999).name == "App 999999"


def test_parse_schema_rejects_placeholder_valve_names():
    raw = build_schema_bin(730, "ValveTestApp260", [ACH_A])
    assert parse_schema(raw, appid=730).name == "App 730"


def test_parse_schema_missing_appid_key_raises():
    raw = build_schema_bin(1245620, "Elden Ring", [ACH_A])
    with pytest.raises(KeyError):
        parse_schema(raw, appid=111111)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_schema.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.schema'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/schema.py` :

```python
"""Lecture des definitions de succes depuis UserGameStatsSchema_<appid>.bin."""

import re
from dataclasses import dataclass

from extractor.binary_vdf import parse_binary_vdf

# Steam stocke parfois un nom de code interne au lieu du vrai titre.
PLACEHOLDER_NAME = re.compile(r"^ValveTestApp\d+$")

# Ordre de preference des langues pour les libelles.
LANGUAGES = ("french", "english")


@dataclass(frozen=True)
class AchievementDef:
    """Definition d'un succes, telle que publiee par le jeu."""

    api_name: str
    name: str
    description: str
    icon: str
    icon_gray: str
    hidden: bool


@dataclass(frozen=True)
class GameSchema:
    """Ensemble des definitions de succes d'un jeu."""

    appid: int
    name: str
    achievements: dict[tuple[str, int], AchievementDef]


def _pick_language(block: object) -> str:
    """Retourne le libelle dans la premiere langue disponible."""
    if not isinstance(block, dict):
        return ""
    for language in LANGUAGES:
        value = block.get(language)
        if value:
            return str(value)
    return ""


def parse_schema(data: bytes, appid: int) -> GameSchema:
    """Parse un schema binaire en definitions de succes.

    Les succes sont indexes par (stat_id, bit_index) : les index de bits sont
    relatifs a chaque stat id, jamais globaux.
    """
    parsed = parse_binary_vdf(data)
    root = parsed[str(appid)]

    raw_name = str(root.get("gamename") or "")
    name = f"App {appid}" if not raw_name or PLACEHOLDER_NAME.match(raw_name) else raw_name

    achievements: dict[tuple[str, int], AchievementDef] = {}
    stats = root.get("stats", {})
    if isinstance(stats, dict):
        for stat_id, stat in stats.items():
            if not isinstance(stat, dict):
                continue
            bits = stat.get("bits")
            if not isinstance(bits, dict):
                continue
            for bit_index, bit in bits.items():
                if not isinstance(bit, dict) or not str(bit_index).isdigit():
                    continue
                display = bit.get("display", {})
                display = display if isinstance(display, dict) else {}
                achievements[(str(stat_id), int(bit_index))] = AchievementDef(
                    api_name=str(bit.get("name", "")),
                    name=_pick_language(display.get("name")),
                    description=_pick_language(display.get("desc")),
                    icon=str(display.get("icon", "")),
                    icon_gray=str(display.get("icon_gray", "")),
                    hidden=bool(display.get("hidden", 0)),
                )

    return GameSchema(appid=appid, name=name, achievements=achievements)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_schema.py -q
```

Attendu : `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/extractor/schema.py tests/test_schema.py && git commit -m "feat: parse achievement definitions from Steam schema files"
```

---

## Task 5: Lecture de l'état de déblocage

**Files:**
- Create: `src/extractor/userstats.py`
- Test: `tests/test_userstats.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_userstats.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_userstats.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.userstats'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/userstats.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_userstats.py -q
```

Attendu : `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/extractor/userstats.py tests/test_userstats.py && git commit -m "feat: parse achievement unlock state from Steam user stats files"
```

---

## Task 6: Localisation de Steam et découverte des jeux

**Files:**
- Create: `src/extractor/steam_paths.py`
- Test: `tests/test_steam_paths.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_steam_paths.py` :

```python
import pytest

from extractor.steam_paths import (
    SteamNotFoundError,
    discover_games,
    find_stats_dir,
    pick_account_id,
)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x08")


def test_find_stats_dir_returns_existing_candidate(tmp_path):
    stats = tmp_path / "Steam" / "appcache" / "stats"
    stats.mkdir(parents=True)
    assert find_stats_dir(candidates=[tmp_path / "absent", stats]) == stats


def test_find_stats_dir_raises_when_no_candidate_exists(tmp_path):
    with pytest.raises(SteamNotFoundError, match="dossier de statistiques Steam"):
        find_stats_dir(candidates=[tmp_path / "absent"])


def test_pick_account_id_returns_account_with_most_games(tmp_path):
    _touch(tmp_path / "UserGameStats_111_1.bin")
    _touch(tmp_path / "UserGameStats_222_1.bin")
    _touch(tmp_path / "UserGameStats_222_2.bin")
    assert pick_account_id(tmp_path) == "222"


def test_pick_account_id_raises_when_no_user_files(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_1.bin")
    with pytest.raises(SteamNotFoundError, match="aucun compte"):
        pick_account_id(tmp_path)


def test_discover_games_pairs_schema_and_user_files(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_1245620.bin")
    _touch(tmp_path / "UserGameStats_555_1245620.bin")
    games = discover_games(tmp_path, account_id="555")
    assert len(games) == 1
    assert games[0].appid == 1245620
    assert games[0].schema_path.name == "UserGameStatsSchema_1245620.bin"
    assert games[0].stats_path.name == "UserGameStats_555_1245620.bin"


def test_discover_games_skips_appid_without_schema(tmp_path):
    _touch(tmp_path / "UserGameStats_555_999.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_skips_appid_without_user_stats(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_999.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_ignores_other_accounts(tmp_path):
    _touch(tmp_path / "UserGameStatsSchema_42.bin")
    _touch(tmp_path / "UserGameStats_999_42.bin")
    assert discover_games(tmp_path, account_id="555") == []


def test_discover_games_sorted_by_appid(tmp_path):
    for appid in (300, 100, 200):
        _touch(tmp_path / f"UserGameStatsSchema_{appid}.bin")
        _touch(tmp_path / f"UserGameStats_555_{appid}.bin")
    assert [g.appid for g in discover_games(tmp_path, account_id="555")] == [100, 200, 300]
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_steam_paths.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.steam_paths'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/steam_paths.py` :

```python
"""Localisation de l'installation Steam et decouverte des jeux avec succes."""

import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_PATTERN = re.compile(r"^UserGameStatsSchema_(\d+)\.bin$")
USERSTATS_PATTERN = re.compile(r"^UserGameStats_(\d+)_(\d+)\.bin$")

DEFAULT_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Steam\appcache\stats"),
    Path(r"C:\Program Files\Steam\appcache\stats"),
)


class SteamNotFoundError(RuntimeError):
    """Leve quand les donnees locales de Steam sont introuvables."""


@dataclass(frozen=True)
class GameFiles:
    """Paire de fichiers .bin decrivant un jeu pour un compte donne."""

    appid: int
    schema_path: Path
    stats_path: Path


def find_stats_dir(candidates: list[Path] | None = None) -> Path:
    """Retourne le premier dossier appcache/stats existant."""
    searched = list(candidates) if candidates is not None else list(DEFAULT_CANDIDATES)
    for candidate in searched:
        if Path(candidate).is_dir():
            return Path(candidate)
    raise SteamNotFoundError(
        "dossier de statistiques Steam introuvable ; chemins essayes : "
        + ", ".join(str(c) for c in searched)
    )


def pick_account_id(stats_dir: Path) -> str:
    """Retourne l'account id Steam3 possedant le plus de jeux dans ce dossier."""
    counts: dict[str, int] = {}
    for path in Path(stats_dir).iterdir():
        match = USERSTATS_PATTERN.match(path.name)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    if not counts:
        raise SteamNotFoundError(f"aucun compte trouve dans {stats_dir}")
    return max(counts, key=lambda account: counts[account])


def discover_games(stats_dir: Path, account_id: str) -> list[GameFiles]:
    """Liste les jeux ayant a la fois un schema et des stats pour ce compte."""
    schemas: dict[int, Path] = {}
    stats: dict[int, Path] = {}

    for path in Path(stats_dir).iterdir():
        schema_match = SCHEMA_PATTERN.match(path.name)
        if schema_match:
            schemas[int(schema_match.group(1))] = path
            continue
        stats_match = USERSTATS_PATTERN.match(path.name)
        if stats_match and stats_match.group(1) == account_id:
            stats[int(stats_match.group(2))] = path

    return [
        GameFiles(appid=appid, schema_path=schemas[appid], stats_path=stats[appid])
        for appid in sorted(schemas.keys() & stats.keys())
    ]
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_steam_paths.py -q
```

Attendu : `9 passed`

- [ ] **Step 5: Vérifier la découverte sur la vraie installation**

```bash
.venv/Scripts/python.exe -c "from extractor.steam_paths import find_stats_dir, pick_account_id, discover_games; d = find_stats_dir(); a = pick_account_id(d); print('compte', a, '|', len(discover_games(d, a)), 'jeux')"
```

Attendu : `compte 145526594 | 95 jeux`

- [ ] **Step 6: Commit**

```bash
git add src/extractor/steam_paths.py tests/test_steam_paths.py && git commit -m "feat: locate Steam stats directory and discover games"
```

---

## Task 7: Assemblage et écriture de l'export JSON

**Files:**
- Create: `src/extractor/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_export.py` :

```python
import json
from datetime import datetime, timezone

import pytest

from extractor.export import build_export, build_game_export, icon_url, write_export
from extractor.steam_paths import GameFiles
from tests.fixtures.build_fixtures import build_schema_bin, build_userstats_bin

ACH_A = {
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
ACH_B = {
    "stat_id": "1",
    "bit": 2,
    "api_name": "ACH02",
    "english": "Age of the Stars",
    "french": "Age des etoiles",
    "desc_english": "Reached the Age of the Stars ending.",
    "desc_french": "Fin de l'Age des etoiles atteinte.",
    "icon": "bbb222.jpg",
    "icon_gray": "bbb222_gray.jpg",
    "hidden": 0,
}


def _write_game(tmp_path, appid=1245620, account="555", achievements=(ACH_A, ACH_B), unlocks=None):
    schema_path = tmp_path / f"UserGameStatsSchema_{appid}.bin"
    stats_path = tmp_path / f"UserGameStats_{account}_{appid}.bin"
    schema_path.write_bytes(build_schema_bin(appid, "Elden Ring", list(achievements)))
    stats_path.write_bytes(
        build_userstats_bin(unlocks if unlocks is not None else {"1": {1: 1710265440}})
    )
    return GameFiles(appid=appid, schema_path=schema_path, stats_path=stats_path)


def test_icon_url_builds_steam_cdn_path():
    assert icon_url(1245620, "aaa111.jpg") == (
        "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/"
        "1245620/aaa111.jpg"
    )


def test_icon_url_returns_empty_string_when_no_icon():
    assert icon_url(1245620, "") == ""


def test_build_game_export_marks_unlocked_and_locked(tmp_path):
    result = build_game_export(_write_game(tmp_path))
    by_name = {a["api_name"]: a for a in result["achievements"]}
    assert by_name["ACH01"]["unlocked"] is True
    assert by_name["ACH02"]["unlocked"] is False


def test_build_game_export_converts_unlock_time_to_iso_utc(tmp_path):
    game = _write_game(tmp_path, unlocks={"1": {1: 1710265440}})
    result = build_game_export(game)
    expected = datetime.fromtimestamp(1710265440, tz=timezone.utc).isoformat()
    unlocked = next(a for a in result["achievements"] if a["api_name"] == "ACH01")
    assert unlocked["unlock_time"] == expected


def test_build_game_export_sets_null_unlock_time_when_locked(tmp_path):
    locked = next(
        a for a in build_game_export(_write_game(tmp_path))["achievements"]
        if a["api_name"] == "ACH02"
    )
    assert locked["unlock_time"] is None


def test_build_game_export_includes_name_and_appid(tmp_path):
    result = build_game_export(_write_game(tmp_path))
    assert result["appid"] == 1245620
    assert result["name"] == "Elden Ring"


def test_build_export_skips_unreadable_game_and_continues(tmp_path):
    good = _write_game(tmp_path, appid=1245620)
    broken_schema = tmp_path / "UserGameStatsSchema_999.bin"
    broken_stats = tmp_path / "UserGameStats_555_999.bin"
    broken_schema.write_bytes(b"\x99corrompu\x00")
    broken_stats.write_bytes(b"\x08")
    broken = GameFiles(appid=999, schema_path=broken_schema, stats_path=broken_stats)

    export = build_export([broken, good], account_id="555")

    assert [g["appid"] for g in export["games"]] == [1245620]


def test_build_export_includes_metadata(tmp_path):
    export = build_export([_write_game(tmp_path)], account_id="555")
    assert export["account_id"] == "555"
    assert export["steam_id64"] == 76561197960266283
    datetime.fromisoformat(export["exported_at"])  # ne doit pas lever


def test_write_export_creates_timestamped_json(tmp_path):
    export = {"exported_at": "2026-08-24T22:10:00+00:00", "games": []}
    path = write_export(export, tmp_path)
    assert path.parent == tmp_path
    assert path.name.startswith("succes_") and path.name.endswith(".json")
    assert json.loads(path.read_text(encoding="utf-8")) == export


def test_write_export_leaves_no_temp_file_behind(tmp_path):
    write_export({"exported_at": "x", "games": []}, tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_export_raises_when_target_dir_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="dossier de destination"):
        write_export({"games": []}, tmp_path / "absent")
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.export'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/export.py` :

```python
"""Assemblage des donnees extraites en un export JSON lisible."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from extractor.schema import parse_schema
from extractor.steam_paths import GameFiles
from extractor.userstats import parse_userstats

logger = logging.getLogger(__name__)

CDN_BASE = "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps"

# Un account id Steam3 devient un SteamID64 en ajoutant cette base.
STEAMID64_BASE = 76561197960265728


def icon_url(appid: int, icon: str) -> str:
    """Construit l'URL CDN d'une icone de succes, ou une chaine vide si absente."""
    return f"{CDN_BASE}/{appid}/{icon}" if icon else ""


def build_game_export(game: GameFiles) -> dict:
    """Fusionne definitions et etat de deblocage pour un jeu."""
    schema = parse_schema(game.schema_path.read_bytes(), appid=game.appid)
    unlocks = parse_userstats(game.stats_path.read_bytes())

    achievements = []
    for key in sorted(schema.achievements, key=lambda k: (k[0], k[1])):
        definition = schema.achievements[key]
        timestamp = unlocks.get(key)
        achievements.append(
            {
                "api_name": definition.api_name,
                "name": definition.name,
                "description": definition.description,
                "icon": icon_url(game.appid, definition.icon),
                "icon_gray": icon_url(game.appid, definition.icon_gray),
                "hidden": definition.hidden,
                "unlocked": timestamp is not None,
                "unlock_time": (
                    datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                    if timestamp is not None
                    else None
                ),
            }
        )

    return {"appid": game.appid, "name": schema.name, "achievements": achievements}


def build_export(games: list[GameFiles], account_id: str) -> dict:
    """Construit l'export complet, en sautant les jeux illisibles."""
    exported_games = []
    for game in games:
        try:
            exported_games.append(build_game_export(game))
        except Exception as error:  # noqa: BLE001 - un jeu casse ne doit pas tout arreter
            logger.warning("jeu %s ignore : %s: %s", game.appid, type(error).__name__, error)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "steam_id64": int(account_id) + STEAMID64_BASE,
        "games": exported_games,
    }


def write_export(export: dict, target_dir: Path) -> Path:
    """Ecrit l'export en JSON horodate, de maniere atomique.

    L'ecriture passe par un fichier .tmp renomme ensuite : le surveillant du NAS
    ne peut jamais lire un fichier a moitie ecrit.
    """
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        raise FileNotFoundError(f"dossier de destination introuvable : {target_dir}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    final_path = target_dir / f"succes_{stamp}.json"
    temp_path = target_dir / f"succes_{stamp}.json.tmp"

    temp_path.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, final_path)
    return final_path
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -q
```

Attendu : `11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/extractor/export.py tests/test_export.py && git commit -m "feat: assemble and write JSON achievement exports"
```

---

## Task 8: CLI de l'extracteur

**Files:**
- Create: `src/extractor/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_cli.py` :

```python
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

    code = main(["--stats-dir", str(stats), "--output-dir", str(out)])

    assert code == 0
    exports = list(out.glob("succes_*.json"))
    assert len(exports) == 1
    payload = json.loads(exports[0].read_text(encoding="utf-8"))
    assert payload["games"][0]["name"] == "Elden Ring"
    assert "1 jeu" in capsys.readouterr().out


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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -q
```

Attendu : `ModuleNotFoundError: No module named 'extractor.__main__'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/extractor/__main__.py` :

```python
"""Point d'entree CLI : python -m extractor --output-dir <dossier partage>."""

import argparse
import logging
import sys
from pathlib import Path

from extractor.export import build_export, write_export
from extractor.steam_paths import (
    SteamNotFoundError,
    discover_games,
    find_stats_dir,
    pick_account_id,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extractor",
        description="Exporte les succes Steam locaux vers un fichier JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Dossier de destination (le dossier partage du NAS).",
    )
    parser.add_argument(
        "--stats-dir",
        default=None,
        help="Dossier appcache/stats de Steam (detecte automatiquement si absent).",
    )
    parser.add_argument(
        "--account-id",
        default=None,
        help="Account id Steam3 (detecte automatiquement si absent).",
    )
    parser.add_argument("--verbose", action="store_true", help="Affiche les jeux ignores.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        format="%(levelname)s: %(message)s",
    )

    try:
        if args.stats_dir:
            stats_dir = Path(args.stats_dir)
            if not stats_dir.is_dir():
                raise SteamNotFoundError(
                    f"dossier de statistiques Steam introuvable : {stats_dir}"
                )
        else:
            stats_dir = find_stats_dir()

        account_id = args.account_id or pick_account_id(stats_dir)
        games = discover_games(stats_dir, account_id)
        export = build_export(games, account_id)
        path = write_export(export, Path(args.output_dir))
    except (SteamNotFoundError, FileNotFoundError, PermissionError, OSError) as error:
        print(f"Echec de l'export : {error}", file=sys.stderr)
        return 1

    total = sum(len(g["achievements"]) for g in export["games"])
    unlocked = sum(1 for g in export["games"] for a in g["achievements"] if a["unlocked"])
    label = "jeu" if len(export["games"]) == 1 else "jeux"
    print(f"{len(export['games'])} {label}, {unlocked}/{total} succes debloques -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -q
```

Attendu : `3 passed`

- [ ] **Step 5: Lancer l'extracteur sur les vraies données Steam**

```bash
mkdir -p exports && .venv/Scripts/python.exe -m extractor --output-dir exports --verbose
```

Attendu : une ligne du type `95 jeux, NNN/MMM succes debloques -> exports\succes_<horodatage>.json`

- [ ] **Step 6: Inspecter l'export produit**

```bash
.venv/Scripts/python.exe -c "import glob, json; p = sorted(glob.glob('exports/succes_*.json'))[-1]; d = json.load(open(p, encoding='utf-8')); g = next(x for x in d['games'] if x['appid'] == 1245620); print(g['name'], len(g['achievements']), 'succes,', sum(a['unlocked'] for a in g['achievements']), 'debloques')"
```

Attendu : `Elden Ring 42 succes, 34 debloques`

- [ ] **Step 7: Commit**

```bash
git add src/extractor/__main__.py tests/test_cli.py && git commit -m "feat: add extractor CLI entry point"
```

---

## Task 9: Schéma de base de données SQLite

**Files:**
- Create: `src/web/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_db.py` :

```python
import sqlite3

import pytest

from web.db import connect, init_db


def test_init_db_creates_expected_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"games", "achievements", "imports"} <= tables


def test_init_db_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    init_db(conn)  # ne doit pas lever
    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 0


def test_rows_are_accessible_by_column_name(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO games (appid, name, updated_at) VALUES (?, ?, ?)",
        (1245620, "Elden Ring", "2026-08-24T22:10:00+00:00"),
    )
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"


def test_achievements_primary_key_rejects_duplicates(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    conn.execute("INSERT INTO games (appid, name, updated_at) VALUES (1, 'X', 'now')")
    insert = (
        "INSERT INTO achievements "
        "(appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time) "
        "VALUES (1, 'ACH01', 'A', '', '', '', 0, 0, NULL)"
    )
    conn.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert)


def test_foreign_keys_are_enforced(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO achievements "
            "(appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time) "
            "VALUES (404, 'ACH01', 'A', '', '', '', 0, 0, NULL)"
        )
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_db.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.db'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/web/db.py` :

```python
"""Schema SQLite et acces a la base de l'application web."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid       INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS achievements (
    appid        INTEGER NOT NULL REFERENCES games(appid) ON DELETE CASCADE,
    api_name     TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    icon         TEXT NOT NULL DEFAULT '',
    icon_gray    TEXT NOT NULL DEFAULT '',
    hidden       INTEGER NOT NULL DEFAULT 0,
    unlocked     INTEGER NOT NULL DEFAULT 0,
    unlock_time  TEXT,
    PRIMARY KEY (appid, api_name)
);

CREATE INDEX IF NOT EXISTS idx_achievements_unlocked
    ON achievements(unlocked, unlock_time DESC);

CREATE TABLE IF NOT EXISTS imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    processed_at  TEXT NOT NULL,
    status        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les cles etrangeres actives."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Cree les tables si elles n'existent pas."""
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_db.py -q
```

Attendu : `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/web/db.py tests/test_db.py && git commit -m "feat: add SQLite schema for achievements storage"
```

---

## Task 10: Ingestion des exports JSON

**Files:**
- Create: `src/web/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_ingest.py` :

```python
import json

import pytest

from web.db import connect, init_db
from web.ingest import InvalidExportError, ingest_export, ingest_file


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    return connection


def _export(appid=1245620, name="Elden Ring", unlocked=True):
    return {
        "exported_at": "2026-08-24T22:10:00+00:00",
        "account_id": "555",
        "games": [
            {
                "appid": appid,
                "name": name,
                "achievements": [
                    {
                        "api_name": "ACH01",
                        "name": "Seigneur d'Elden",
                        "description": "Obtenu le Cercle d'Elden.",
                        "icon": "https://cdn.example/a.jpg",
                        "icon_gray": "https://cdn.example/a_gray.jpg",
                        "hidden": False,
                        "unlocked": unlocked,
                        "unlock_time": "2024-03-12T18:44:00+00:00" if unlocked else None,
                    }
                ],
            }
        ],
    }


def test_ingest_export_inserts_game_and_achievements(conn):
    ingest_export(conn, _export())
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"
    row = conn.execute("SELECT * FROM achievements").fetchone()
    assert row["api_name"] == "ACH01"
    assert row["unlocked"] == 1


def test_ingest_export_returns_counts(conn):
    assert ingest_export(conn, _export()) == {"games": 1, "achievements": 1}


def test_ingest_export_updates_existing_rows_without_duplicating(conn):
    ingest_export(conn, _export(name="Ancien nom", unlocked=False))
    ingest_export(conn, _export(name="Elden Ring", unlocked=True))

    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM achievements").fetchone()["n"] == 1
    assert conn.execute("SELECT name FROM games").fetchone()["name"] == "Elden Ring"
    assert conn.execute("SELECT unlocked FROM achievements").fetchone()["unlocked"] == 1


def test_ingest_export_never_relocks_an_unlocked_achievement(conn):
    # Un succes deja debloque ne doit pas repasser a verrouille si un export
    # plus ancien ou incomplet arrive ensuite.
    ingest_export(conn, _export(unlocked=True))
    ingest_export(conn, _export(unlocked=False))
    row = conn.execute("SELECT unlocked, unlock_time FROM achievements").fetchone()
    assert row["unlocked"] == 1
    assert row["unlock_time"] == "2024-03-12T18:44:00+00:00"


def test_ingest_export_rejects_payload_without_games_list(conn):
    with pytest.raises(InvalidExportError, match="games"):
        ingest_export(conn, {"exported_at": "x"})


def test_ingest_export_rejects_game_without_appid(conn):
    payload = _export()
    del payload["games"][0]["appid"]
    with pytest.raises(InvalidExportError, match="appid"):
        ingest_export(conn, payload)


def test_ingest_file_records_success_in_imports(conn, tmp_path):
    path = tmp_path / "succes_1.json"
    path.write_text(json.dumps(_export()), encoding="utf-8")

    ingest_file(conn, path)

    row = conn.execute("SELECT * FROM imports").fetchone()
    assert row["filename"] == "succes_1.json"
    assert row["status"] == "ok"


def test_ingest_file_records_failure_and_raises(conn, tmp_path):
    path = tmp_path / "casse.json"
    path.write_text("{ pas du json", encoding="utf-8")

    with pytest.raises(InvalidExportError):
        ingest_file(conn, path)

    row = conn.execute("SELECT * FROM imports").fetchone()
    assert row["status"] == "erreur"
    assert "JSON" in row["detail"]


def test_ingest_file_leaves_no_partial_data_on_failure(conn, tmp_path):
    payload = _export()
    payload["games"].append({"name": "sans appid", "achievements": []})
    path = tmp_path / "partiel.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidExportError):
        ingest_file(conn, path)

    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 0
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ingest.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.ingest'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/web/ingest.py` :

```python
"""Ingestion des exports JSON de l'extracteur dans SQLite."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class InvalidExportError(ValueError):
    """Leve quand un fichier d'export ne respecte pas le format attendu."""


UPSERT_GAME = """
INSERT INTO games (appid, name, updated_at)
VALUES (:appid, :name, :updated_at)
ON CONFLICT(appid) DO UPDATE SET
    name = excluded.name,
    updated_at = excluded.updated_at
"""

# Un succes debloque le reste : on ne repasse jamais unlocked de 1 a 0.
UPSERT_ACHIEVEMENT = """
INSERT INTO achievements
    (appid, api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time)
VALUES
    (:appid, :api_name, :name, :description, :icon, :icon_gray, :hidden, :unlocked, :unlock_time)
ON CONFLICT(appid, api_name) DO UPDATE SET
    name = excluded.name,
    description = excluded.description,
    icon = excluded.icon,
    icon_gray = excluded.icon_gray,
    hidden = excluded.hidden,
    unlocked = MAX(achievements.unlocked, excluded.unlocked),
    unlock_time = COALESCE(achievements.unlock_time, excluded.unlock_time)
"""


def ingest_export(conn: sqlite3.Connection, payload: dict) -> dict:
    """Insere ou met a jour le contenu d'un export. Transaction tout-ou-rien."""
    games = payload.get("games")
    if not isinstance(games, list):
        raise InvalidExportError("export invalide : cle 'games' absente ou mal typee")

    updated_at = str(payload.get("exported_at") or datetime.now(timezone.utc).isoformat())
    game_count = 0
    achievement_count = 0

    try:
        with conn:  # rollback automatique si une exception remonte
            for game in games:
                if not isinstance(game, dict) or not isinstance(game.get("appid"), int):
                    raise InvalidExportError("export invalide : jeu sans appid entier")

                appid = game["appid"]
                conn.execute(
                    UPSERT_GAME,
                    {
                        "appid": appid,
                        "name": str(game.get("name") or f"App {appid}"),
                        "updated_at": updated_at,
                    },
                )
                game_count += 1

                for ach in game.get("achievements") or []:
                    if not isinstance(ach, dict) or not ach.get("api_name"):
                        raise InvalidExportError(
                            f"export invalide : succes sans api_name (jeu {appid})"
                        )
                    conn.execute(
                        UPSERT_ACHIEVEMENT,
                        {
                            "appid": appid,
                            "api_name": str(ach["api_name"]),
                            "name": str(ach.get("name") or ach["api_name"]),
                            "description": str(ach.get("description") or ""),
                            "icon": str(ach.get("icon") or ""),
                            "icon_gray": str(ach.get("icon_gray") or ""),
                            "hidden": int(bool(ach.get("hidden"))),
                            "unlocked": int(bool(ach.get("unlocked"))),
                            "unlock_time": ach.get("unlock_time"),
                        },
                    )
                    achievement_count += 1
    except sqlite3.DatabaseError as error:
        raise InvalidExportError(f"echec de l'ecriture en base : {error}") from error

    return {"games": game_count, "achievements": achievement_count}


def _record_import(conn: sqlite3.Connection, filename: str, status: str, detail: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO imports (filename, processed_at, status, detail) VALUES (?, ?, ?, ?)",
            (filename, datetime.now(timezone.utc).isoformat(), status, detail),
        )


def ingest_file(conn: sqlite3.Connection, path: Path) -> dict:
    """Lit et ingere un fichier d'export, en journalisant le resultat."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        _record_import(conn, path.name, "erreur", f"JSON illisible : {error}")
        raise InvalidExportError(f"JSON illisible dans {path.name} : {error}") from error
    except OSError as error:
        _record_import(conn, path.name, "erreur", f"lecture impossible : {error}")
        raise InvalidExportError(f"lecture impossible de {path.name} : {error}") from error

    try:
        result = ingest_export(conn, payload)
    except InvalidExportError as error:
        _record_import(conn, path.name, "erreur", str(error))
        raise

    _record_import(
        conn, path.name, "ok", f"{result['games']} jeux, {result['achievements']} succes"
    )
    return result
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ingest.py -q
```

Attendu : `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/web/ingest.py tests/test_ingest.py && git commit -m "feat: ingest JSON exports into SQLite"
```

---

## Task 11: Surveillance du dossier partagé

**Files:**
- Create: `src/web/watcher.py`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_watcher.py` :

```python
import json

import pytest

from web.db import connect, init_db
from web.watcher import scan_once


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    return connection


@pytest.fixture
def inbox(tmp_path):
    folder = tmp_path / "partage"
    folder.mkdir()
    return folder


def _valid_export():
    return {
        "exported_at": "2026-08-24T22:10:00+00:00",
        "games": [
            {
                "appid": 1245620,
                "name": "Elden Ring",
                "achievements": [
                    {
                        "api_name": "ACH01",
                        "name": "Seigneur d'Elden",
                        "unlocked": True,
                        "unlock_time": "2024-03-12T18:44:00+00:00",
                    }
                ],
            }
        ],
    }


def test_scan_once_ingests_and_moves_valid_file(conn, inbox):
    (inbox / "succes_1.json").write_text(json.dumps(_valid_export()), encoding="utf-8")

    result = scan_once(conn, inbox)

    assert result == {"ok": 1, "erreur": 0}
    assert not (inbox / "succes_1.json").exists()
    assert (inbox / "importes" / "succes_1.json").exists()
    assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1


def test_scan_once_moves_invalid_file_to_error_folder(conn, inbox):
    (inbox / "casse.json").write_text("{ pas du json", encoding="utf-8")

    result = scan_once(conn, inbox)

    assert result == {"ok": 0, "erreur": 1}
    assert (inbox / "erreurs" / "casse.json").exists()


def test_scan_once_ignores_non_json_files(conn, inbox):
    (inbox / "notes.txt").write_text("bonjour", encoding="utf-8")
    assert scan_once(conn, inbox) == {"ok": 0, "erreur": 0}
    assert (inbox / "notes.txt").exists()


def test_scan_once_ignores_temp_files_being_written(conn, inbox):
    (inbox / "succes_2.json.tmp").write_text(json.dumps(_valid_export()), encoding="utf-8")
    assert scan_once(conn, inbox) == {"ok": 0, "erreur": 0}
    assert (inbox / "succes_2.json.tmp").exists()


def test_scan_once_returns_zero_when_inbox_missing(conn, tmp_path):
    assert scan_once(conn, tmp_path / "absent") == {"ok": 0, "erreur": 0}


def test_scan_once_renames_on_collision_instead_of_overwriting(conn, inbox):
    processed = inbox / "importes"
    processed.mkdir()
    (processed / "succes_1.json").write_text("ancien", encoding="utf-8")
    (inbox / "succes_1.json").write_text(json.dumps(_valid_export()), encoding="utf-8")

    scan_once(conn, inbox)

    assert (processed / "succes_1.json").read_text(encoding="utf-8") == "ancien"
    assert len(list(processed.glob("succes_1*.json"))) == 2
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_watcher.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.watcher'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/web/watcher.py` :

```python
"""Surveillance du dossier partage : ingere les nouveaux exports JSON."""

import logging
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from web.ingest import InvalidExportError, ingest_file

logger = logging.getLogger(__name__)

PROCESSED_DIR = "importes"
ERROR_DIR = "erreurs"


def _move_without_overwriting(source: Path, target_dir: Path) -> Path:
    """Deplace un fichier, en le renommant si le nom est deja pris."""
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = target_dir / f"{source.stem}_{stamp}{source.suffix}"
    shutil.move(str(source), str(target))
    return target


def scan_once(conn: sqlite3.Connection, inbox: Path) -> dict:
    """Ingere tous les .json du dossier, puis les deplace. Retourne les compteurs."""
    inbox = Path(inbox)
    counts = {"ok": 0, "erreur": 0}
    if not inbox.is_dir():
        logger.warning("dossier partage introuvable : %s", inbox)
        return counts

    for path in sorted(inbox.glob("*.json")):
        if not path.is_file():
            continue
        try:
            ingest_file(conn, path)
        except InvalidExportError as error:
            logger.warning("fichier rejete %s : %s", path.name, error)
            _move_without_overwriting(path, inbox / ERROR_DIR)
            counts["erreur"] += 1
        else:
            _move_without_overwriting(path, inbox / PROCESSED_DIR)
            counts["ok"] += 1

    return counts


def start_watcher(
    conn: sqlite3.Connection,
    inbox: Path,
    interval_seconds: int,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Lance la surveillance en tache de fond (thread demon)."""
    stop = stop_event or threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                scan_once(conn, inbox)
            except Exception:  # noqa: BLE001 - la boucle ne doit jamais mourir
                logger.exception("erreur inattendue pendant la surveillance")
            stop.wait(interval_seconds)

    thread = threading.Thread(target=loop, name="watcher", daemon=True)
    thread.start()
    return thread
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_watcher.py -q
```

Attendu : `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/web/watcher.py tests/test_watcher.py && git commit -m "feat: watch shared folder and ingest new exports"
```

---

## Task 12: Authentification par mot de passe

**Files:**
- Create: `src/web/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_auth.py` :

```python
from web.auth import check_password, hash_password


def test_hash_password_produces_verifiable_hash():
    stored = hash_password("secret-du-nas")
    assert check_password(stored, "secret-du-nas") is True


def test_check_password_rejects_wrong_password():
    stored = hash_password("secret-du-nas")
    assert check_password(stored, "mauvais") is False


def test_hash_password_uses_random_salt():
    assert hash_password("meme-mot-de-passe") != hash_password("meme-mot-de-passe")


def test_check_password_rejects_malformed_stored_value():
    assert check_password("n-importe-quoi", "secret") is False


def test_check_password_rejects_empty_stored_value():
    assert check_password("", "secret") is False
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_auth.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.auth'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/web/auth.py` :

```python
"""Authentification par mot de passe unique (PBKDF2 + comparaison a temps constant)."""

import hashlib
import hmac
import os

ITERATIONS = 260_000
ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """Retourne 'pbkdf2_sha256$<iterations>$<sel_hex>$<hash_hex>'."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(ALGORITHM, password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(stored: str, candidate: str) -> bool:
    """Verifie un mot de passe contre sa valeur stockee, sans fuite de timing."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != f"pbkdf2_{ALGORITHM}":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            ALGORITHM, candidate.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(expected, actual)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_auth.py -q
```

Attendu : `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/web/auth.py tests/test_auth.py && git commit -m "feat: add password hashing and verification"
```

---

## Task 13: Requêtes de lecture pour le tableau de bord

**Files:**
- Create: `src/web/queries.py`
- Test: `tests/test_queries.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_queries.py` :

```python
import pytest

from web.db import connect, init_db
from web.ingest import ingest_export
from web.queries import get_game, list_games, recent_unlocks


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    ingest_export(
        connection,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                {
                    "appid": 1,
                    "name": "Jeu A",
                    "achievements": [
                        {
                            "api_name": "A1",
                            "name": "Premier",
                            "unlocked": True,
                            "unlock_time": "2024-01-01T10:00:00+00:00",
                        },
                        {"api_name": "A2", "name": "Second", "unlocked": False},
                    ],
                },
                {
                    "appid": 2,
                    "name": "Jeu B",
                    "achievements": [
                        {
                            "api_name": "B1",
                            "name": "Unique",
                            "unlocked": True,
                            "unlock_time": "2024-06-01T10:00:00+00:00",
                        }
                    ],
                },
            ],
        },
    )
    return connection


def test_list_games_returns_completion_counts(conn):
    games = {g["appid"]: g for g in list_games(conn)}
    assert games[1]["total"] == 2
    assert games[1]["unlocked"] == 1
    assert games[2]["unlocked"] == 1


def test_list_games_computes_percentage(conn):
    games = {g["appid"]: g for g in list_games(conn)}
    assert games[1]["percent"] == 50
    assert games[2]["percent"] == 100


def test_list_games_sorted_by_percentage_desc(conn):
    assert [g["appid"] for g in list_games(conn)] == [2, 1]


def test_list_games_handles_game_without_achievements(conn):
    ingest_export(
        conn,
        {"exported_at": "x", "games": [{"appid": 3, "name": "Vide", "achievements": []}]},
    )
    empty = next(g for g in list_games(conn) if g["appid"] == 3)
    assert empty["total"] == 0
    assert empty["percent"] == 0


def test_get_game_returns_game_with_achievements(conn):
    game = get_game(conn, 1)
    assert game["name"] == "Jeu A"
    assert [a["api_name"] for a in game["achievements"]] == ["A1", "A2"]


def test_get_game_lists_unlocked_before_locked(conn):
    assert [a["unlocked"] for a in get_game(conn, 1)["achievements"]] == [1, 0]


def test_get_game_returns_none_for_unknown_appid(conn):
    assert get_game(conn, 404) is None


def test_recent_unlocks_returns_newest_first_across_games(conn):
    rows = recent_unlocks(conn, limit=10)
    assert [r["api_name"] for r in rows] == ["B1", "A1"]
    assert rows[0]["game_name"] == "Jeu B"


def test_recent_unlocks_respects_limit(conn):
    assert len(recent_unlocks(conn, limit=1)) == 1


def test_recent_unlocks_excludes_locked_achievements(conn):
    assert all(r["api_name"] != "A2" for r in recent_unlocks(conn, limit=10))
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_queries.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.queries'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `src/web/queries.py` :

```python
"""Requetes de lecture alimentant les pages du tableau de bord."""

import sqlite3

LIST_GAMES = """
SELECT
    g.appid,
    g.name,
    g.updated_at,
    COUNT(a.api_name) AS total,
    COALESCE(SUM(a.unlocked), 0) AS unlocked
FROM games g
LEFT JOIN achievements a ON a.appid = g.appid
GROUP BY g.appid, g.name, g.updated_at
"""

GET_ACHIEVEMENTS = """
SELECT api_name, name, description, icon, icon_gray, hidden, unlocked, unlock_time
FROM achievements
WHERE appid = ?
ORDER BY unlocked DESC, unlock_time ASC, name COLLATE NOCASE
"""

RECENT_UNLOCKS = """
SELECT a.appid, a.api_name, a.name, a.icon, a.unlock_time, g.name AS game_name
FROM achievements a
JOIN games g ON g.appid = a.appid
WHERE a.unlocked = 1 AND a.unlock_time IS NOT NULL
ORDER BY a.unlock_time DESC
LIMIT ?
"""


def list_games(conn: sqlite3.Connection) -> list[dict]:
    """Liste les jeux avec leur taux de completion, du plus complet au moins complet."""
    games = []
    for row in conn.execute(LIST_GAMES):
        total = row["total"]
        unlocked = row["unlocked"]
        games.append(
            {
                "appid": row["appid"],
                "name": row["name"],
                "updated_at": row["updated_at"],
                "total": total,
                "unlocked": unlocked,
                "percent": round(unlocked * 100 / total) if total else 0,
            }
        )
    games.sort(key=lambda g: (-g["percent"], g["name"].lower()))
    return games


def get_game(conn: sqlite3.Connection, appid: int) -> dict | None:
    """Retourne un jeu et ses succes, ou None s'il n'existe pas."""
    row = conn.execute(
        "SELECT appid, name, updated_at FROM games WHERE appid = ?", (appid,)
    ).fetchone()
    if row is None:
        return None

    achievements = [dict(a) for a in conn.execute(GET_ACHIEVEMENTS, (appid,))]
    unlocked = sum(a["unlocked"] for a in achievements)
    total = len(achievements)
    return {
        "appid": row["appid"],
        "name": row["name"],
        "updated_at": row["updated_at"],
        "total": total,
        "unlocked": unlocked,
        "percent": round(unlocked * 100 / total) if total else 0,
        "achievements": achievements,
    }


def recent_unlocks(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Retourne les derniers succes debloques, tous jeux confondus."""
    return [dict(row) for row in conn.execute(RECENT_UNLOCKS, (limit,))]
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_queries.py -q
```

Attendu : `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/web/queries.py tests/test_queries.py && git commit -m "feat: add dashboard read queries"
```

---

## Task 14: Application Flask, routes et gabarits

**Files:**
- Create: `src/web/app.py`
- Create: `src/web/templates/base.html`
- Create: `src/web/templates/login.html`
- Create: `src/web/templates/index.html`
- Create: `src/web/templates/game.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_web.py` :

```python
import pytest

from web.app import create_app
from web.auth import hash_password
from web.db import connect, init_db
from web.ingest import ingest_export

PASSWORD = "secret-du-nas"


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    init_db(conn)
    ingest_export(
        conn,
        {
            "exported_at": "2026-08-24T22:10:00+00:00",
            "games": [
                {
                    "appid": 1245620,
                    "name": "Elden Ring",
                    "achievements": [
                        {
                            "api_name": "ACH01",
                            "name": "Seigneur d'Elden",
                            "description": "Obtenu le Cercle d'Elden.",
                            "unlocked": True,
                            "unlock_time": "2024-03-12T18:44:00+00:00",
                        },
                        {"api_name": "ACH02", "name": "Verrouille", "unlocked": False},
                    ],
                }
            ],
        },
    )
    conn.close()

    return create_app(
        {
            "DATABASE": str(db_path),
            "PASSWORD_HASH": hash_password(PASSWORD),
            "SECRET_KEY": "cle-de-test",
            "TESTING": True,
            "START_WATCHER": False,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"password": PASSWORD})
    return client


def test_index_redirects_to_login_when_anonymous(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_game_page_redirects_to_login_when_anonymous(client):
    assert client.get("/game/1245620").status_code == 302


def test_login_with_correct_password_grants_access(client):
    response = client.post("/login", data={"password": PASSWORD}, follow_redirects=True)
    assert response.status_code == 200
    assert "Elden Ring" in response.get_data(as_text=True)


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/login", data={"password": "mauvais"})
    assert response.status_code == 401
    assert "incorrect" in response.get_data(as_text=True).lower()


def test_index_shows_completion_percentage(logged_in):
    body = logged_in.get("/").get_data(as_text=True)
    assert "Elden Ring" in body
    assert "50" in body


def test_game_page_shows_unlocked_and_locked_achievements(logged_in):
    body = logged_in.get("/game/1245620").get_data(as_text=True)
    assert "Seigneur d&#39;Elden" in body or "Seigneur d'Elden" in body
    assert "Verrouille" in body


def test_unknown_game_returns_404(logged_in):
    assert logged_in.get("/game/999999").status_code == 404


def test_logout_revokes_access(logged_in):
    logged_in.post("/logout")
    assert logged_in.get("/").status_code == 302


def test_healthcheck_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_create_app_requires_password_hash(tmp_path):
    with pytest.raises(RuntimeError, match="PASSWORD_HASH"):
        create_app(
            {"DATABASE": str(tmp_path / "x.db"), "SECRET_KEY": "k", "START_WATCHER": False}
        )
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web.py -q
```

Attendu : `ModuleNotFoundError: No module named 'web.app'`

- [ ] **Step 3: Écrire l'application Flask**

Créer `src/web/app.py` :

```python
"""Application Flask : tableau de bord des succes."""

import functools
import os
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from web.auth import check_password
from web.db import connect, init_db
from web.queries import get_game, list_games, recent_unlocks
from web.watcher import start_watcher


def _get_conn():
    """Connexion SQLite propre a la requete courante."""
    if "conn" not in g:
        g.conn = connect(current_app.config["DATABASE"])
    return g.conn


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("ACHIEVEMENTS_DB", "/data/achievements.db"),
        PASSWORD_HASH=os.environ.get("ACHIEVEMENTS_PASSWORD_HASH", ""),
        SECRET_KEY=os.environ.get("ACHIEVEMENTS_SECRET_KEY", ""),
        INBOX=os.environ.get("ACHIEVEMENTS_INBOX", "/inbox"),
        SCAN_INTERVAL=int(os.environ.get("ACHIEVEMENTS_SCAN_INTERVAL", "300")),
        START_WATCHER=True,
    )
    if config:
        app.config.update(config)

    if not app.config["PASSWORD_HASH"]:
        raise RuntimeError(
            "PASSWORD_HASH manquant : definir ACHIEVEMENTS_PASSWORD_HASH avant le demarrage"
        )
    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "SECRET_KEY manquante : definir ACHIEVEMENTS_SECRET_KEY avant le demarrage"
        )

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not app.config.get("TESTING", False),
    )

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    setup_conn = connect(app.config["DATABASE"])
    init_db(setup_conn)

    if app.config["START_WATCHER"]:
        start_watcher(setup_conn, Path(app.config["INBOX"]), app.config["SCAN_INTERVAL"])

    @app.teardown_appcontext
    def close_conn(_exception):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if check_password(app.config["PASSWORD_HASH"], request.form.get("password", "")):
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("index"))
            return render_template("login.html", error="Mot de passe incorrect."), 401
        return render_template("login.html", error=None)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        conn = _get_conn()
        return render_template(
            "index.html", games=list_games(conn), recent=recent_unlocks(conn, limit=15)
        )

    @app.get("/game/<int:appid>")
    @login_required
    def game_detail(appid: int):
        game = get_game(_get_conn(), appid)
        if game is None:
            abort(404)
        return render_template("game.html", game=game)

    return app
```

- [ ] **Step 4: Créer `src/web/templates/base.html`**

```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Mes succès{% endblock %}</title>
  <style>
    :root {
      --bg: #12141a; --card: #1c1f28; --text: #e8eaf0;
      --muted: #949bb0; --accent: #6c9cff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 1.5rem; background: var(--bg); color: var(--text);
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.5;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    header { display: flex; justify-content: space-between; align-items: center;
             gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
    h1 { font-size: 1.5rem; margin: 0; }
    .grid { display: grid; gap: 1rem;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
    .card { background: var(--card); border-radius: 10px; padding: 1rem; }
    .muted { color: var(--muted); font-size: 0.875rem; }
    .bar { height: 6px; background: #2b3040; border-radius: 3px;
           overflow: hidden; margin-top: 0.5rem; }
    .bar span { display: block; height: 100%; background: var(--accent); }
    .ach { display: flex; gap: 0.75rem; align-items: flex-start; }
    .ach img { width: 48px; height: 48px; border-radius: 6px; flex-shrink: 0; }
    .ach.locked { opacity: 0.45; }
    .ach.locked img { filter: grayscale(1); }
    button { background: var(--accent); color: #0b0d12; border: 0;
             border-radius: 6px; padding: 0.5rem 1rem; font: inherit; cursor: pointer; }
    input { background: var(--card); border: 1px solid #2b3040; border-radius: 6px;
            color: var(--text); padding: 0.5rem 0.75rem; font: inherit; width: 100%; }
    .error { color: #ff8a8a; }
  </style>
</head>
<body>
  {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Créer `src/web/templates/login.html`**

```html
{% extends "base.html" %}
{% block title %}Connexion — Mes succès{% endblock %}
{% block body %}
<div class="card" style="max-width: 340px; margin: 4rem auto;">
  <h1>Mes succès</h1>
  <form method="post" action="{{ url_for('login') }}">
    <p><label for="password">Mot de passe</label></p>
    <p><input type="password" id="password" name="password" autofocus required></p>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <p><button type="submit">Se connecter</button></p>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Créer `src/web/templates/index.html`**

```html
{% extends "base.html" %}
{% block title %}Mes succès{% endblock %}
{% block body %}
<header>
  <h1>Mes succès</h1>
  <form method="post" action="{{ url_for('logout') }}">
    <button type="submit">Déconnexion</button>
  </form>
</header>

{% if recent %}
<h2 style="font-size: 1.1rem;">Derniers débloqués</h2>
<div class="grid" style="margin-bottom: 2rem;">
  {% for item in recent %}
  <div class="card ach">
    {% if item.icon %}<img src="{{ item.icon }}" alt="" loading="lazy">{% endif %}
    <div>
      <strong>{{ item.name }}</strong>
      <div class="muted">{{ item.game_name }}</div>
      <div class="muted">{{ item.unlock_time[:10] }}</div>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

<h2 style="font-size: 1.1rem;">Jeux ({{ games|length }})</h2>
<div class="grid">
  {% for game in games %}
  <a class="card" href="{{ url_for('game_detail', appid=game.appid) }}">
    <strong>{{ game.name }}</strong>
    <div class="muted">{{ game.unlocked }} / {{ game.total }} — {{ game.percent }} %</div>
    <div class="bar"><span style="width: {{ game.percent }}%"></span></div>
  </a>
  {% else %}
  <p class="muted">Aucun jeu importé pour l'instant.</p>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 7: Créer `src/web/templates/game.html`**

```html
{% extends "base.html" %}
{% block title %}{{ game.name }} — Mes succès{% endblock %}
{% block body %}
<header>
  <h1>{{ game.name }}</h1>
  <a href="{{ url_for('index') }}">← Tous les jeux</a>
</header>

<p class="muted">
  {{ game.unlocked }} / {{ game.total }} succès — {{ game.percent }} %
  · mis à jour le {{ game.updated_at[:10] }}
</p>
<div class="bar" style="margin-bottom: 1.5rem;">
  <span style="width: {{ game.percent }}%"></span>
</div>

<div class="grid">
  {% for ach in game.achievements %}
  <div class="card ach {% if not ach.unlocked %}locked{% endif %}">
    {% set image = ach.icon if ach.unlocked else (ach.icon_gray or ach.icon) %}
    {% if image %}<img src="{{ image }}" alt="" loading="lazy">{% endif %}
    <div>
      <strong>{{ ach.name }}</strong>
      {% if ach.description %}<div class="muted">{{ ach.description }}</div>{% endif %}
      {% if ach.unlocked and ach.unlock_time %}
      <div class="muted">Débloqué le {{ ach.unlock_time[:10] }}</div>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 8: Lancer les tests pour vérifier qu'ils passent**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web.py -q
```

Attendu : `10 passed`

- [ ] **Step 9: Commit**

```bash
git add src/web/app.py src/web/templates/ tests/test_web.py && git commit -m "feat: add Flask dashboard with password auth"
```

---

## Task 15: Empaquetage Docker

**Files:**
- Create: `src/web/wsgi.py`
- Create: `scripts/generate_password_hash.py`
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Créer le point d'entrée WSGI**

Créer `src/web/wsgi.py` :

```python
"""Point d'entree WSGI pour le serveur de production."""

from web.app import create_app

app = create_app()
```

- [ ] **Step 2: Créer l'utilitaire de génération de hash**

Créer `scripts/generate_password_hash.py` :

```python
"""Genere le hash a placer dans ACHIEVEMENTS_PASSWORD_HASH.

Usage : python scripts/generate_password_hash.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web.auth import hash_password  # noqa: E402

if __name__ == "__main__":
    password = getpass.getpass("Mot de passe du tableau de bord : ")
    confirm = getpass.getpass("Confirmer : ")
    if password != confirm:
        print("Les mots de passe ne correspondent pas.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 8:
        print("Choisir un mot de passe d'au moins 8 caracteres.", file=sys.stderr)
        raise SystemExit(1)
    print("\nACHIEVEMENTS_PASSWORD_HASH=" + hash_password(password))
```

- [ ] **Step 3: Créer le `Dockerfile`**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . gunicorn

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /inbox \
    && chown -R app:app /data /inbox
USER app

VOLUME ["/data", "/inbox"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

# Un seul worker : le surveillant de dossier et la connexion SQLite sont partages en memoire.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "web.wsgi:app"]
```

- [ ] **Step 4: Créer le `docker-compose.yml`**

```yaml
services:
  achievements:
    build: .
    container_name: achievements
    restart: unless-stopped
    ports:
      - "8080:8000"
    environment:
      ACHIEVEMENTS_DB: /data/achievements.db
      ACHIEVEMENTS_INBOX: /inbox
      ACHIEVEMENTS_SCAN_INTERVAL: "300"
      # Generer avec : python scripts/generate_password_hash.py
      ACHIEVEMENTS_PASSWORD_HASH: "${ACHIEVEMENTS_PASSWORD_HASH:?definir dans .env}"
      # Generer avec : python -c "import secrets; print(secrets.token_hex(32))"
      ACHIEVEMENTS_SECRET_KEY: "${ACHIEVEMENTS_SECRET_KEY:?definir dans .env}"
    volumes:
      - achievements-data:/data
      # Adapter ce chemin au dossier partage reel du NAS :
      - /volume1/partage/succes:/inbox

volumes:
  achievements-data:
```

- [ ] **Step 5: Construire l'image**

```bash
docker build -t achievements:latest .
```

Attendu : `naming to docker.io/library/achievements:latest` en fin de sortie, sans erreur.

- [ ] **Step 6: Générer un hash de test et démarrer le conteneur**

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0, 'src'); from web.auth import hash_password; print(hash_password('test1234'))" > .hash_test.txt && docker run --rm -d --name achievements-test -p 8080:8000 -e ACHIEVEMENTS_PASSWORD_HASH="$(cat .hash_test.txt)" -e ACHIEVEMENTS_SECRET_KEY="cle-de-test" achievements:latest
```

Attendu : un identifiant de conteneur affiché.

- [ ] **Step 7: Vérifier que le service répond**

```bash
curl -s http://localhost:8080/healthz
```

Attendu : `{"status":"ok"}`

- [ ] **Step 8: Arrêter le conteneur et nettoyer**

```bash
docker stop achievements-test && rm -f .hash_test.txt
```

- [ ] **Step 9: Commit**

```bash
git add Dockerfile docker-compose.yml src/web/wsgi.py scripts/generate_password_hash.py && git commit -m "feat: package web app as Docker container"
```

---

## Task 16: Documentation et validation de bout en bout

**Files:**
- Create: `README.md`

- [ ] **Step 1: Lancer toute la suite de tests**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Attendu : `95 passed` (12 + 2 + 8 + 5 + 9 + 11 + 3 + 5 + 9 + 6 + 5 + 10 + 10 = 95)

- [ ] **Step 2: Lancer le linter**

```bash
.venv/Scripts/python.exe -m ruff check src tests scripts
```

Attendu : `All checks passed!` — corriger toute erreur signalée avant de continuer.

- [ ] **Step 3: Vérifier le parcours complet extracteur → ingestion → lecture**

```bash
mkdir -p exports && .venv/Scripts/python.exe -m extractor --output-dir exports && .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
from web.db import connect, init_db
from web.watcher import scan_once
from web.queries import list_games
conn = connect('exports/verif.db'); init_db(conn)
print(scan_once(conn, Path('exports')))
games = list_games(conn)
print(len(games), 'jeux en base')
print('exemple :', games[0]['name'], games[0]['percent'], '%')
"
```

Attendu : `{'ok': 1, 'erreur': 0}`, puis `95 jeux en base` et une ligne d'exemple.

- [ ] **Step 4: Nettoyer les artefacts de vérification**

```bash
rm -rf exports
```

- [ ] **Step 5: Créer le `README.md`**

````markdown
# Suivi de succès de jeux

Extrait l'état réel de vos succès depuis les **fichiers locaux de Steam**, et les
affiche dans un tableau de bord web hébergé sur votre NAS. Aucune requête vers
l'API Steam : tout est lu sur disque.

## Architecture

```
[PC Windows]                [Dossier partagé NAS]      [NAS Docker]
Steam (appcache/stats)
     │
     ▼
python -m extractor  ──►  succes_<horodatage>.json  ──►  appli web (surveille + ingère)
                                                                 │
                                                                 ▼
                                                    https://votredomaine.tld
```

## 1. Extracteur (PC Windows)

Installation :

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Lancement (remplacer le chemin par votre dossier partagé) :

```bash
.venv/Scripts/python.exe -m extractor --output-dir "\\\\NAS\\partage\\succes"
```

Options : `--stats-dir` et `--account-id` remplacent la détection automatique,
`--verbose` affiche les jeux ignorés.

### Automatiser (Planificateur de tâches Windows)

Créer une tâche déclenchée à l'ouverture de session :
- Programme : `S:\Achievements\.venv\Scripts\python.exe`
- Arguments : `-m extractor --output-dir "\\NAS\partage\succes"`
- Démarrer dans : `S:\Achievements`

## 2. Appli web (NAS)

Générer les secrets :

```bash
python scripts/generate_password_hash.py
python -c "import secrets; print('ACHIEVEMENTS_SECRET_KEY=' + secrets.token_hex(32))"
```

Placer les deux lignes produites dans un fichier `.env` à côté du
`docker-compose.yml`, ajuster le chemin du dossier partagé dans le
`docker-compose.yml`, puis :

```bash
docker compose up -d
```

Le tableau de bord écoute sur le port 8080. Le placer derrière votre reverse
proxy pour l'exposer via votre nom de domaine en HTTPS.

## Fonctionnement du dossier partagé

L'extracteur écrit `succes_<horodatage>.json`. L'appli le repère (toutes les
5 minutes par défaut), l'ingère, puis le déplace dans `importes/`. Un fichier
illisible part dans `erreurs/` sans interrompre le service. Les fichiers `.tmp`
en cours d'écriture sont ignorés.

## Limites connues

- Seuls les jeux **Steam** ayant déjà généré un cache local sont détectés
  (95 jeux sur la machine de référence, y compris des jeux désinstallés).
- Les icônes sont chargées depuis le CDN Steam par le navigateur du visiteur.
- Un succès déjà enregistré comme débloqué ne repasse jamais à verrouillé,
  même si un export plus ancien est ingéré ensuite.

## Évolutions prévues (v2)

- Extension Playnite déclenchant l'extraction à la fermeture d'un jeu
  (sur le modèle de l'intégration Ludusavi/Playnite `OnGameStopped`).
- Support d'autres launchers via Playnite.
````

- [ ] **Step 6: Commit**

```bash
git add README.md && git commit -m "docs: add setup and usage documentation"
```

---

## Auto-revue du plan

**Couverture de la spec :**

| Exigence de la spec | Tâche |
|---|---|
| Lire les succès depuis les fichiers locaux Steam | 2, 4, 5, 6 |
| Export JSON lisible | 7, 8 |
| Dossier partagé surveillé | 11 |
| Ingestion SQLite (`games`, `achievements`, `imports`) | 9, 10 |
| Tableau de bord : accueil + détail par jeu | 13, 14 |
| Authentification par mot de passe | 12, 14 |
| Conteneur Docker unique pour le NAS | 15 |
| Erreur : jeu illisible sauté, log d'avertissement | 7 (`build_export`) |
| Erreur : JSON invalide → dossier `erreurs/` | 11 |
| Erreur : dossier injoignable → message clair, arrêt propre | 8, 11 |
| Tests du parseur sans installation Steam | 2, 3 |
| Tests d'ingestion et des routes | 10, 14 |
| Icônes : repli sur l'URL CDN | 7 |
| Pas de test end-to-end Docker automatisé (hors scope v1) | 15 (vérification manuelle) |

**Écarts assumés par rapport à la spec**, justifiés par les sondes exécutées sur la machine :
- La spec prévoyait d'énumérer les jeux via les fichiers `.acf` (jeux installés uniquement). Le plan énumère depuis `appcache/stats`, ce qui **couvre davantage** de jeux (dont des désinstallés) et supprime la dépendance à `libraryfolders.vdf`.
- La spec envisageait de résoudre les icônes localement en priorité. Les sondes montrent qu'elles n'y sont pas : le plan utilise directement l'URL CDN, qui était le repli prévu.
