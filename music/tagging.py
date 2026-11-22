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


# ------------------------------------------------------------------ escrita
WRITE_KEYS = {"artist": "artist", "album_artist": "albumartist", "album": "album",
              "title": "title", "track": "tracknumber", "disc": "discnumber",
              "year": "date", "genre": "genre"}


def write_tags(path: Path | str, values: dict) -> dict:
    """Escreve só os campos indicados. Devolve os valores anteriores (para registo)."""
    if not HAS_MUTAGEN:
        raise RuntimeError("Mutagen não está instalado: não é possível escrever tags.")
    f = mutagen.File(str(path), easy=True)
    if f is None:
        raise RuntimeError("Formato sem suporte para escrita de tags.")
    if f.tags is None:
        f.add_tags()
    old = {}
    for k, v in values.items():
        key = WRITE_KEYS.get(k)
        if not key or v in (None, ""):
            continue
        try:
            old[k] = list(f.tags.get(key, [])) if key in f.tags else None
            f.tags[key] = [str(v)]
        except Exception:  # noqa: BLE001  (campo não suportado neste formato)
            continue
    f.save()
    return old


def embedded_cover(path: Path | str) -> bytes | None:
    """Extrai a capa embutida (Mutagen; recurso: FFmpeg)."""
    if HAS_MUTAGEN:
        try:
            f = mutagen.File(str(path))
            if f is not None:
                if getattr(f, "pictures", None):
                    return f.pictures[0].data
                tags = f.tags or {}
                for k in list(getattr(tags, "keys", lambda: [])()):
                    if str(k).startswith("APIC"):
                        return tags[k].data
                if "covr" in tags and tags["covr"]:
                    return bytes(tags["covr"][0])
                mbp = tags.get("metadata_block_picture") if hasattr(tags, "get") else None
                if mbp:
                    import base64
                    from mutagen.flac import Picture
                    return Picture(base64.b64decode(mbp[0])).data
        except Exception:  # noqa: BLE001
            pass
    from core.mediainfo import NO_WINDOW, find_tool
    import subprocess
    exe = find_tool("ffmpeg")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-v", "error", "-i", str(path), "-an", "-c:v", "copy",
                            "-f", "image2pipe", "-"], capture_output=True, timeout=30,
                           creationflags=NO_WINDOW)
        return r.stdout if r.returncode == 0 and len(r.stdout) > 100 else None
    except (OSError, subprocess.TimeoutExpired):
        return None
