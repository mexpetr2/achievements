"""Parseur du format VDF *texte* (fichiers de configuration Steam lisibles).

Distinct de binary_vdf.py, qui traite le format binaire des caches de succes.
Ici la syntaxe est celle de localconfig.vdf : des paires "cle" "valeur" et des
blocs delimites par des accolades.

Tolerant par conception : ces fichiers sont ecrits par Steam et peuvent etre
tronques (Steam en cours d'ecriture). Un bloc non ferme rend simplement ce qui
a pu etre lu, plutot que de faire echouer toute l'extraction.
"""

import re

# Une chaine entre guillemets (avec echappements), ou une accolade.
# Les commentaires // hors chaine sont naturellement ignores : ils ne
# correspondent a aucun de ces deux motifs.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_text_vdf(text: str) -> dict:
    """Parse un VDF texte en dictionnaire imbrique.

    Toutes les valeurs scalaires restent des chaines : la conversion (entier,
    horodatage...) appartient a l'appelant, qui seul connait le sens des champs.
    """
    root: dict = {}
    stack: list[dict] = [root]
    pending_key: str | None = None

    for match in _TOKEN.finditer(text):
        string, brace = match.group(1), match.group(2)

        if brace == "{":
            child: dict = {}
            if pending_key is not None:
                stack[-1][pending_key] = child
                pending_key = None
            stack.append(child)
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
        elif pending_key is None:
            pending_key = string
        else:
            stack[-1][pending_key] = string
            pending_key = None

    return root
