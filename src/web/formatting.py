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


def format_date(value: str | None) -> str:
    """Rend une date ISO au format jour/mois/annee, ou 'jamais' si inconnue."""
    if not value:
        return "jamais"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "jamais"
