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
