"""Backups da base de dados (cópia consistente com a API de backup do SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .config import BACKUPS_DIR, DB_PATH


def backup_database(db_path: Path = DB_PATH, keep: int = 10, out_dir: Path = BACKUPS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"mediaorganizer_{datetime.now():%Y%m%d_%H%M%S}.db"
    src = sqlite3.connect(db_path)
    try:
        out = sqlite3.connect(dst)
        with out:
            src.backup(out)
        out.close()
    finally:
        src.close()
    olds = sorted(out_dir.glob("mediaorganizer_*.db"))
    for old in olds[:-keep] if keep > 0 else []:
        try:
            old.unlink()   # só backups antigos da própria aplicação
        except OSError:
            pass
    return dst


def list_backups(out_dir: Path = BACKUPS_DIR) -> list[Path]:
    return sorted(out_dir.glob("mediaorganizer_*.db"), reverse=True)
