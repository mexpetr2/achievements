"""Mise en forme des valeurs affichees (durees de jeu, dates).

Fonctions pures, exposees ensuite comme filtres Jinja par app.py.
"""

from datetime import datetime


def format_playtime(minutes: int | None) -> str:
    """Rend un temps de jeu lisible : '45 min', '2 h 30', '451 h 6'."""
    if minutes is None:
        return "temps inconnu"
    if minutes <= 0:
        return "jamais lance"
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} h {remainder}" if remainder else f"{hours} h"


def format_rarity(percent: float | None) -> str:
    """Rend la raretee d'un succes : '10,4 % des joueurs'.

    Sous 1 %, on garde deux decimales : c'est justement la ou l'ecart est
    interessant (0,12 % et 0,9 % ne racontent pas la meme histoire).
    """
    if percent is None:
        return ""
    decimales = 2 if percent < 1 else 1
    valeur = f"{percent:.{decimales}f}".replace(".", ",")
    return f"{valeur} % des joueurs"


def format_date(value: str | None) -> str:
    """Rend une date ISO au format jour/mois/annee, ou 'jamais' si inconnue."""
    if not value:
        return "jamais"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "jamais"
