"""Configuração base: caminhos, valores por defeito e extensões suportadas."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Media Organizer"
APP_VERSION = "0.1.0"

# Raiz do projecto (pasta onde está o app.py). Pode ser alterada com a
# variável de ambiente MEDIAORGANIZER_HOME (útil para testes).
APP_ROOT = Path(os.environ.get("MEDIAORGANIZER_HOME", Path(__file__).resolve().parent.parent))

DATABASE_DIR = APP_ROOT / "database"
DB_PATH = DATABASE_DIR / "mediaorganizer.db"
LOGS_DIR = APP_ROOT / "logs"
REPORTS_DIR = APP_ROOT / "reports"
BACKUPS_DIR = APP_ROOT / "backups"
QUARANTINE_DIR = APP_ROOT / "quarantine"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

QUARANTINE_CATEGORIES = ("Duplicados", "Ficheiros_0_bytes", "Identificacao_Incerta", "Conflitos")


def ensure_dirs() -> None:
    for d in (DATABASE_DIR, LOGS_DIR, REPORTS_DIR, BACKUPS_DIR, QUARANTINE_DIR):
        d.mkdir(parents=True, exist_ok=True)


DEFAULT_SETTINGS: dict = {
    # Pastas
    "movies_folder": str(Path.home() / "Vídeos" / "Filmes"),
    "music_source_folder": "",
    "music_library_folder": "",
    "quarantine_folder": str(QUARANTINE_DIR),
    # Segurança (secção 31 da especificação)
    "preserve_originals": True,
    "auto_delete": False,          # bloqueado: nunca é activado pela aplicação
    "quarantine_enabled": True,
    "logging_enabled": True,
    "backups_enabled": False,
    "incremental": True,
    "allow_cross_device_move": False,  # entre discos: copia+verifica e mantém o original
    # Jellyfin
    "jellyfin_enabled": False,
    "jellyfin_cover_name": "cover.jpg",
    # Técnico
    "ffprobe_timeout": 30,
    "first_run_done": False,
}

# Opções que a interface nunca deixa alterar.
LOCKED_SETTINGS = {"auto_delete": False, "preserve_originals": True}

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".mpg", ".mpeg", ".ts", ".m2ts",
    ".webm", ".flv", ".vob", ".divx", ".ogv", ".3gp",
}
AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".alac",
    ".aiff", ".aif", ".ape", ".wv",
}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MOVIE_COVER_NAMES = ("cover", "poster", "folder", "movie")
MUSIC_COVER_NAMES = ("cover", "folder", "front", "album")
