"""Leitura de tags musicais (Mutagen quando disponível; FFprobe como recurso).

Nesta versão só se lêem tags. A escrita/correcção fica para a Fase 7.
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    import mutagen  # type: ignore
    HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    mutagen = None
    HAS_MUTAGEN = False

FIELDS = ("artist", "albumartist", "album", "title", "tracknumber", "discnumber",
          "date", "genre")


def _first_int(value) -> int | None:
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def _year(value) -> int | None:
    if value is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def normalize(raw: dict) -> dict:
    def g(*keys):
        for k in keys:
            v = raw.get(k)
            if isinstance(v, list):
                v = v[0] if v else None
            if v not in (None, ""):
                return str(v).strip()
        return None

    return {
        "artist": g("artist"),
        "album_artist": g("albumartist", "album_artist", "album artist"),
        "album": g("album"),
        "title": g("title"),
        "track": _first_int(g("tracknumber", "track")),
        "disc": _first_int(g("discnumber", "disc")),
        "year": _year(g("date", "year", "originaldate")),
        "genre": g("genre"),
    }


def read_tags_mutagen(path: Path) -> tuple[dict, bool]:
    """Devolve (tags normalizadas, tem_capa_embutida)."""
    f = mutagen.File(str(path), easy=True)
    if f is None:
        return {}, False
    raw = {k.lower(): v for k, v in (f.tags or {}).items()} if f.tags else {}
    cover = False
    try:
        full = mutagen.File(str(path))
        if full is not None:
            if getattr(full, "pictures", None):
                cover = True
            elif full.tags is not None:
                keys = [str(k) for k in full.tags.keys()]
                cover = any(k.startswith("APIC") or k in ("covr", "METADATA_BLOCK_PICTURE",
                                                          "metadata_block_picture",
                                                          "WM/Picture") for k in keys)
    except Exception:  # noqa: BLE001
        pass
    return normalize(raw), cover
