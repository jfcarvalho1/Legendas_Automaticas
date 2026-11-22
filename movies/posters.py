"""Capas/posters de filmes."""
from __future__ import annotations

from pathlib import Path

from core.config import IMAGE_EXTENSIONS

COVER_NAMES = ("cover", "poster", "folder", "movie")


def existing_cover(folder: Path, stem: str) -> Path | None:
    try:
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in IMAGE_EXTENSIONS and (
                    f.stem.lower() in COVER_NAMES or f.stem.lower() in (
                        f"{stem.lower()}-poster", stem.lower())):
                return f
    except OSError:
        pass
    return None


def image_kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def choose_poster(details: dict) -> str | None:
    """Melhor poster: português, depois inglês, depois sem texto; maior e mais votado."""
    posters = ((details.get("images") or {}).get("posters")) or []

    def key(p):
        lang = p.get("iso_639_1")
        rank = {"pt": 0, "en": 1, None: 2}.get(lang, 3)
        return (rank, -(p.get("vote_average") or 0), -(p.get("width") or 0))
    good = [p for p in posters if (p.get("width") or 0) >= 500]
    if good:
        return sorted(good, key=key)[0]["file_path"]
    return details.get("poster_path")
