"""Base de dados SQLite: esquema, configurações, inventário e erros."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import DB_PATH, DEFAULT_SETTINGS, LOCKED_SETTINGS

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    folder TEXT, filename TEXT, extension TEXT,
    size INTEGER, mtime REAL,
    title_guess TEXT, year_guess INTEGER, confidence TEXT,
    width INTEGER, height INTEGER, resolution TEXT,
    video_codec TEXT, audio_codec TEXT, duration REAL,
    audio_languages TEXT, embedded_subtitles TEXT, external_subtitles TEXT,
    has_cover INTEGER DEFAULT 0, cover_path TEXT,
    has_nfo INTEGER DEFAULT 0, has_metadata_json INTEGER DEFAULT 0,
    status TEXT, probe_error TEXT,
    first_seen TEXT, scanned_at TEXT, extra TEXT
);

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id INTEGER REFERENCES artists(id),
    title TEXT NOT NULL, year INTEGER, folder TEXT,
    UNIQUE(artist_id, title, year)
);

CREATE TABLE IF NOT EXISTS music (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    folder TEXT, filename TEXT, extension TEXT,
    size INTEGER, mtime REAL,
    artist TEXT, album_artist TEXT, album TEXT, title TEXT,
    track INTEGER, disc INTEGER, year INTEGER, genre TEXT,
    duration REAL, bitrate INTEGER, sample_rate INTEGER, channels INTEGER, codec TEXT,
    has_embedded_cover INTEGER DEFAULT 0, folder_cover TEXT,
    artist_id INTEGER REFERENCES artists(id), album_id INTEGER REFERENCES albums(id),
    status TEXT, probe_error TEXT,
    first_seen TEXT, scanned_at TEXT, extra TEXT
);

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER REFERENCES movies(id),
    path TEXT UNIQUE NOT NULL, language TEXT, format TEXT,
    source TEXT, created_at TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS covers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_type TEXT, media_id INTEGER, path TEXT,
    source TEXT, width INTEGER, height INTEGER, created_at TEXT
);

CREATE TABLE IF NOT EXISTS duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT, media_type TEXT, path TEXT, sha256 TEXT,
    method TEXT, confidence TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT UNIQUE NOT NULL,
    operation TEXT NOT NULL,
    original_path TEXT, new_path TEXT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT, error TEXT, reason TEXT, details TEXT,
    reverted_by TEXT
);

CREATE TABLE IF NOT EXISTS operation_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
    path TEXT NOT NULL, role TEXT, sha256 TEXT, size INTEGER
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT, started_at TEXT, finished_at TEXT,
    status TEXT, total INTEGER, processed INTEGER, message TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, kind TEXT, enabled INTEGER DEFAULT 0, config TEXT
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, level TEXT, module TEXT, path TEXT, message TEXT,
    resolved INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_movies_status ON movies(status);
CREATE INDEX IF NOT EXISTS idx_music_status ON music(status);
CREATE INDEX IF NOT EXISTS idx_music_artist ON music(artist);
CREATE INDEX IF NOT EXISTS idx_ops_ts ON operations(timestamp);
CREATE INDEX IF NOT EXISTS idx_errors_resolved ON errors(resolved);
"""

MOVIE_COLUMNS = (
    "path", "folder", "filename", "extension", "size", "mtime", "title_guess", "year_guess",
    "confidence", "width", "height", "resolution", "video_codec", "audio_codec", "duration",
    "audio_languages", "embedded_subtitles", "external_subtitles", "has_cover", "cover_path",
    "has_nfo", "has_metadata_json", "status", "probe_error", "scanned_at", "extra",
)
MUSIC_COLUMNS = (
    "path", "folder", "filename", "extension", "size", "mtime", "artist", "album_artist",
    "album", "title", "track", "disc", "year", "genre", "duration", "bitrate", "sample_rate",
    "channels", "codec", "has_embedded_cover", "folder_cover", "artist_id", "album_id",
    "status", "probe_error", "scanned_at", "extra",
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    """Uma ligação SQLite por thread (a análise corre numa thread própria)."""

    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.init_schema()

    # -- ligação -----------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    def init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.conn:
            return self.conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        r = self.conn.execute(sql, tuple(params)).fetchone()
        return dict(r) if r else None

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        r = self.conn.execute(sql, tuple(params)).fetchone()
        return r[0] if r else None

    # -- configurações -----------------------------------------------------
    def get_setting(self, key: str) -> Any:
        if key in LOCKED_SETTINGS:
            return LOCKED_SETTINGS[key]
        r = self.query_one("SELECT value FROM settings WHERE key=?", (key,))
        if r is None:
            return DEFAULT_SETTINGS.get(key)
        return json.loads(r["value"])

    def set_setting(self, key: str, value: Any) -> None:
        if key in LOCKED_SETTINGS:
            value = LOCKED_SETTINGS[key]
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def all_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        for r in self.query("SELECT key, value FROM settings"):
            s[r["key"]] = json.loads(r["value"])
        s.update(LOCKED_SETTINGS)
        return s

    # -- erros -------------------------------------------------------------
    def log_error(self, level: str, module: str, path: str | None, message: str) -> None:
        self.execute(
            "INSERT INTO errors(timestamp, level, module, path, message) VALUES(?,?,?,?,?)",
            (now_iso(), level, module, path, message),
        )

    # -- inventário --------------------------------------------------------
    def _upsert(self, table: str, columns: tuple, row: dict) -> None:
        data = {k: row.get(k) for k in columns}
        cols = ", ".join(data.keys())
        marks = ", ".join("?" for _ in data)
        updates = ", ".join(f"{k}=excluded.{k}" for k in data if k != "path")
        sql = (f"INSERT INTO {table}({cols}, first_seen) VALUES({marks}, ?) "
               f"ON CONFLICT(path) DO UPDATE SET {updates}")
        self.execute(sql, list(data.values()) + [now_iso()])

    def upsert_movie(self, row: dict) -> None:
        self._upsert("movies", MOVIE_COLUMNS, row)

    def upsert_music(self, row: dict) -> None:
        self._upsert("music", MUSIC_COLUMNS, row)

    def get_or_create_artist(self, name: str | None) -> int | None:
        if not name:
            return None
        self.execute("INSERT OR IGNORE INTO artists(name) VALUES(?)", (name,))
        return self.scalar("SELECT id FROM artists WHERE name=?", (name,))

    def get_or_create_album(self, artist_id: int | None, title: str | None,
                            year: int | None, folder: str | None) -> int | None:
        if not title:
            return None
        self.execute(
            "INSERT OR IGNORE INTO albums(artist_id, title, year, folder) VALUES(?,?,?,?)",
            (artist_id, title, year, folder),
        )
        return self.scalar(
            "SELECT id FROM albums WHERE artist_id IS ? AND title=? AND year IS ?",
            (artist_id, title, year),
        )

    # -- estatísticas para o dashboard ------------------------------------
    def movie_stats(self) -> dict:
        q = self.scalar
        active = "status NOT IN ('missing', 'quarantined')"
        return {
            "total": q(f"SELECT COUNT(*) FROM movies WHERE {active}") or 0,
            "size": q(f"SELECT COALESCE(SUM(size),0) FROM movies WHERE {active}") or 0,
            "zero_bytes": q("SELECT COUNT(*) FROM movies WHERE status='zero_bytes'") or 0,
            "invalid": q("SELECT COUNT(*) FROM movies WHERE status='invalid'") or 0,
            "missing": q("SELECT COUNT(*) FROM movies WHERE status='missing'") or 0,
            "no_subs": q(f"SELECT COUNT(*) FROM movies WHERE {active} AND status='ok' "
                         "AND COALESCE(external_subtitles,'')='' "
                         "AND COALESCE(embedded_subtitles,'')=''") or 0,
            "no_cover": q(f"SELECT COUNT(*) FROM movies WHERE status='ok' AND has_cover=0") or 0,
            "no_metadata": q("SELECT COUNT(*) FROM movies WHERE status='ok' "
                             "AND (has_nfo=0 OR has_metadata_json=0)") or 0,
            "uncertain": q("SELECT COUNT(*) FROM movies WHERE status='ok' "
                           "AND confidence='baixa'") or 0,
        }

    def music_stats(self) -> dict:
        q = self.scalar
        active = "status NOT IN ('missing', 'quarantined')"
        return {
            "total": q(f"SELECT COUNT(*) FROM music WHERE {active}") or 0,
            "size": q(f"SELECT COALESCE(SUM(size),0) FROM music WHERE {active}") or 0,
            "artists": q(f"SELECT COUNT(DISTINCT COALESCE(album_artist, artist)) FROM music "
                         f"WHERE {active} AND COALESCE(album_artist, artist) IS NOT NULL") or 0,
            "albums": q(f"SELECT COUNT(DISTINCT album_id) FROM music WHERE {active}") or 0,
            "zero_bytes": q("SELECT COUNT(*) FROM music WHERE status='zero_bytes'") or 0,
            "invalid": q("SELECT COUNT(*) FROM music WHERE status='invalid'") or 0,
            "missing": q("SELECT COUNT(*) FROM music WHERE status='missing'") or 0,
            "no_cover": q("SELECT COUNT(*) FROM music WHERE status='ok' AND has_embedded_cover=0 "
                          "AND COALESCE(folder_cover,'')=''") or 0,
            "incomplete_tags": q("SELECT COUNT(*) FROM music WHERE status='ok' AND "
                                 "(COALESCE(artist,'')='' OR COALESCE(title,'')='' "
                                 "OR COALESCE(album,'')='')") or 0,
        }

    def general_stats(self) -> dict:
        return {
            "errors": self.scalar("SELECT COUNT(*) FROM errors WHERE resolved=0") or 0,
            "operations": self.scalar("SELECT COUNT(*) FROM operations") or 0,
            "jobs_running": self.scalar("SELECT COUNT(*) FROM jobs WHERE status='running'") or 0,
            "quarantined": self.scalar(
                "SELECT COUNT(*) FROM operations WHERE operation='quarantine' "
                "AND status='completed'") or 0,
        }
