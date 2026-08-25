"""Point d'entree WSGI pour le serveur de production."""

from web.app import create_app

app = create_app()
