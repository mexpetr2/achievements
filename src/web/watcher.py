"""Surveillance du dossier partage : ingere les nouveaux exports JSON."""

import logging
import shutil
import sqlite3
import threading
import time
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
