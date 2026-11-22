"""Gestão de legendas por filme: inventário, conversão para SRT e descarga."""
from __future__ import annotations

import json
from pathlib import Path

from core.config import SUBTITLE_EXTENSIONS
from core.database import Database, now_iso
from core.organizer import subtitle_suffix
from core.safety import SafeFileManager

from .subtitles import (SubtitleError, decode_bytes, detect_language, load_cues, parse_srt,
                        to_srt_bytes, validate_srt)

PRIORITY = ["pt-PT", "pt-BR", "pt", "en"]
TEXT_FORMATS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}


def free_name(folder: Path, stem: str, suffix: str, ext: str = ".srt") -> Path:
    p = folder / f"{stem}{suffix}{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem}{suffix}.{n}{ext}"
        n += 1
    return p


def list_subtitles(video: Path) -> list[dict]:
    """Legendas externas do filme (mesmo nome do vídeo; ou todas, se a pasta só tiver
    este filme). O idioma vem do nome e, se não houver, do conteúdo."""
    folder, stem = video.parent, video.stem
    try:
        files = sorted(folder.iterdir())
    except OSError:
        return []
    videos = [f for f in files if f.suffix.lower() in {".mkv", ".mp4", ".avi", ".m4v", ".mov",
                                                       ".wmv", ".mpg", ".mpeg", ".ts", ".webm"}]
    alone = len(videos) <= 1
    if alone:  # incluir subpastas (Subs/, Legendas/, Subs/Portuguese/…)
        import os
        files = files + sorted(Path(dp) / fn for dp, _d, fns in os.walk(folder)
                               if Path(dp) != folder for fn in fns)
    out = []
    for f in files:
        if not f.is_file() or f.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue
        if not (f.name.startswith(stem) or alone):
            continue
        rest = f.stem[len(stem):] if f.name.startswith(stem) else f.stem
        suffix = subtitle_suffix(rest)
        if not suffix and f.parent != folder:
            suffix = subtitle_suffix(f.parent.name)
        lang = suffix.split(".")[1] if suffix else None
        detected = False
        if not lang and f.suffix.lower() in TEXT_FORMATS:
            try:
                text, _enc = decode_bytes(f.read_bytes()[:200_000])
                lang, _c = detect_language(text)
                detected = lang is not None
            except OSError:
                pass
        out.append({"path": str(f), "name": str(f.relative_to(folder)), "format": f.suffix.lower().lstrip("."),
                    "language": lang, "detected": detected, "forced": ".forced" in suffix})
    return out


def best_language(subs: list[dict], embedded: str = "") -> str | None:
    langs = {s["language"] for s in subs if s["language"] and not s["forced"]}
    for emb in (embedded or "").split(","):
        e = emb.strip().lower()
        if e in ("por", "pt"):
            langs.add("pt")
        elif e in ("eng", "en"):
            langs.add("en")
    for p in PRIORITY:
        if p in langs:
            return p
    return next(iter(sorted(langs)), None)


class SubtitleManager:
    def __init__(self, db: Database, files: SafeFileManager | None = None):
        self.db = db
        self.files = files or SafeFileManager(db)

    # --------------------------------------------------------- inventário
    def refresh(self, movie: dict) -> list[dict]:
        subs = list_subtitles(Path(movie["path"]))
        self.db.execute("DELETE FROM subtitles WHERE movie_id=? AND source!='download'",
                        (movie["id"],))
        for s in subs:
            self.db.execute(
                "INSERT INTO subtitles(movie_id, path, language, format, source, created_at, status) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET language=excluded.language, "
                "format=excluded.format, movie_id=excluded.movie_id",
                (movie["id"], s["path"], s["language"], s["format"], "local", now_iso(), "ok"))
        return subs

    def overview(self) -> list[dict]:
        rows = []
        for m in self.db.query("SELECT * FROM movies WHERE status='ok' ORDER BY title_guess COLLATE NOCASE"):
            if not Path(m["path"]).exists():
                continue
            subs = list_subtitles(Path(m["path"]))
            langs = {s["language"] for s in subs if s["language"]}
            rows.append({**m, "subs": subs, "langs": langs,
                         "best": best_language(subs, m.get("embedded_subtitles") or "")})
        return rows

    # ---------------------------------------------------------- conversão
    def convert_to_srt(self, movie: dict, sub_path: str) -> dict:
        """Converte ASS/SSA/VTT/SUB (ou SRT noutra codificação) para SRT UTF-8 num
        ficheiro novo. O original fica intacto."""
        src = Path(sub_path)
        video = Path(movie["path"])
        cues, enc = load_cues(src)
        rest = src.stem[len(video.stem):] if src.name.startswith(video.stem) else src.stem
        suffix = subtitle_suffix(rest)
        if not suffix:
            lang, _ = detect_language("\n".join(c.text for c in cues[:400]))
            suffix = f".{lang}" if lang else ""
        if src.suffix.lower() == ".srt":
            if enc in ("utf-8", "utf-8-sig"):
                raise SubtitleError("Já é SRT em UTF-8: não precisa de conversão.")
            suffix += ".utf8"
        dst = free_name(video.parent, video.stem, suffix)
        data = to_srt_bytes(cues)
        probs = validate_srt(data.decode("utf-8"))
        if probs and any("sem tempo" in p.lower() for p in probs):
            raise SubtitleError("A conversão não produziu um SRT válido: " + probs[0])
        return self.files.create_file(dst, data, "create", reason=f"Conversão de {src.name} para SRT",
                                      details={"kind": "subtitle_convert", "source": str(src),
                                               "source_encoding": enc})

    # ------------------------------------------------------------ descarga
    def download(self, movie: dict, client, languages=None) -> dict | None:
        """Procura no OpenSubtitles (hash do vídeo → IMDb/TMDb → título e ano) e guarda
        a melhor legenda segundo a prioridade pt-PT > pt-BR > en. None se nada houver."""
        from integrations.opensubtitles import LANG_PRIORITY, movie_hash
        languages = languages or LANG_PRIORITY
        video = Path(movie["path"])
        extra = {}
        try:
            extra = json.loads(movie.get("extra") or "{}")
        except json.JSONDecodeError:
            pass
        results = []
        h = movie_hash(video)
        if h:
            results = client.search(moviehash=h, languages=languages)
        if not results and (extra.get("imdb_id") or extra.get("tmdb_id")):
            results = client.search(imdb_id=extra.get("imdb_id"), tmdb_id=extra.get("tmdb_id"),
                                    languages=languages)
        if not results and movie.get("title_guess"):
            results = client.search(query=movie["title_guess"], year=movie.get("year_guess"),
                                    languages=languages)
        best = client.best(results, languages)
        if not best:
            return None
        data, _name = client.download(best["file_id"])
        text, _enc = decode_bytes(data)
        try:
            if not parse_srt(text):
                raise SubtitleError("vazia")
        except SubtitleError as e:
            raise SubtitleError(f"A legenda descarregada não é um SRT válido ({e}).") from e
        dst = free_name(video.parent, video.stem, f".{best['language']}")
        op = self.files.create_file(
            dst, text.encode("utf-8"), "create",
            reason=f"Legenda {best['language']} do OpenSubtitles",
            details={"kind": "subtitle_download", "source": "OpenSubtitles",
                     "file_id": best["file_id"], "release": best["release"],
                     "hash_match": best["hash_match"], "language": best["language"]})
        self.db.execute(
            "INSERT OR REPLACE INTO subtitles(movie_id, path, language, format, source, created_at, status) "
            "VALUES(?,?,?,?,?,?,?)", (movie["id"], str(dst), best["language"], "srt", "download",
                                      now_iso(), "ok"))
        return {"op": op, "language": best["language"], "path": str(dst),
                "hash_match": best["hash_match"]}
