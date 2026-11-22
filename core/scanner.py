"""Inventário de filmes e música (só leitura — nunca altera ficheiros).

* Incremental: ficheiros com o mesmo tamanho e data de modificação não são
  reanalisados.
* Ficheiros de 0 bytes: registados e assinalados, sem FFprobe, sem interromper.
* Ficheiros que desapareceram ficam com estado 'missing'.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from movies.identification import parse_filename
from music import tagging

from .config import (AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, MOVIE_COVER_NAMES,
                     MUSIC_COVER_NAMES, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS)
from .database import Database, now_iso
from .logger import get_logger
from .mediainfo import ProbeError, ffprobe_path, probe, summarize_audio, summarize_video

log = get_logger("scanner")

ProgressFn = Callable[[int, int, str], None]

IGNORED_DIRS = {".git", ".Trash", ".trash", "@eaDir", "lost+found", ".thumbnails",
                "$RECYCLE.BIN", "System Volume Information"}


def _walk(root: Path, extensions: set[str], skip: set[Path]) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
                       and (dp / d).resolve() not in skip]
        for fn in filenames:
            if fn.startswith("."):
                continue
            if Path(fn).suffix.lower() in extensions:
                out.append(dp / fn)
    out.sort()
    return out


class Scanner:
    def __init__(self, db: Database, progress: ProgressFn | None = None):
        self.db = db
        self.progress = progress or (lambda *_: None)
        self._cancel = False
        self.timeout = int(db.get_setting("ffprobe_timeout") or 30)
        quarantine = Path(db.get_setting("quarantine_folder") or "")
        self.skip = {quarantine.resolve()} if str(quarantine) else set()

    def cancel(self) -> None:
        self._cancel = True

    # -- utilitário de tarefas --------------------------------------------
    def _job_start(self, kind: str) -> int:
        cur = self.db.execute(
            "INSERT INTO jobs(job_type, started_at, status, total, processed) "
            "VALUES(?, ?, 'running', 0, 0)", (kind, now_iso()))
        return cur.lastrowid

    def _job_end(self, job_id: int, status: str, total: int, processed: int, msg: str) -> None:
        self.db.execute(
            "UPDATE jobs SET finished_at=?, status=?, total=?, processed=?, message=? WHERE id=?",
            (now_iso(), status, total, processed, msg, job_id))

    def _known(self, table: str, folder: Path) -> dict[str, dict]:
        prefix = os.path.join(str(folder), "")
        rows = self.db.query(f"SELECT path, size, mtime, status FROM {table}")
        return {r["path"]: r for r in rows if r["path"].startswith(prefix)}

    def _mark_missing(self, table: str, known: dict, seen: set[str]) -> int:
        n = 0
        for p, r in known.items():
            if p not in seen and r["status"] not in ("missing", "quarantined"):
                self.db.execute(f"UPDATE {table} SET status='missing', scanned_at=? WHERE path=?",
                                (now_iso(), p))
                n += 1
        return n

    # -- FILMES ------------------------------------------------------------
    def scan_movies(self, folder: str | Path) -> dict:
        folder = Path(folder).expanduser()
        if not folder.is_dir():
            raise FileNotFoundError(f"A pasta de filmes não existe: {folder}")
        job = self._job_start("inventario_filmes")
        self.progress(0, 0, "A procurar ficheiros de vídeo…")
        files = _walk(folder, VIDEO_EXTENSIONS, self.skip)
        known = self._known("movies", folder)
        incremental = bool(self.db.get_setting("incremental"))
        has_probe = ffprobe_path() is not None
        if not has_probe:
            self.db.log_error("warning", "scanner", None,
                              "FFprobe não encontrado: análise técnica indisponível.")
        stats = {"total": len(files), "new": 0, "updated": 0, "skipped": 0,
                 "zero_bytes": 0, "invalid": 0, "missing": 0}
        seen: set[str] = set()
        for i, f in enumerate(files, 1):
            if self._cancel:
                self._job_end(job, "cancelled", len(files), i - 1, "Cancelado pelo utilizador.")
                stats["cancelled"] = True
                return stats
            self.progress(i, len(files), f.name)
            sp = str(f)
            seen.add(sp)
            try:
                st = f.stat()
            except OSError as e:
                self.db.log_error("error", "scanner", sp, f"Sem acesso: {e}")
                continue
            prev = known.get(sp)
            if (incremental and prev and prev["size"] == st.st_size
                    and prev["mtime"] == st.st_mtime and prev["status"] != "missing"):
                stats["skipped"] += 1
                self._refresh_movie_sidecars(f)
                continue
            row = self._analyse_movie(f, st, has_probe)
            if row["status"] in ("zero_bytes", "invalid"):
                stats[row["status"]] += 1
            stats["updated" if prev else "new"] += 1
            self.db.upsert_movie(row)
        stats["missing"] = self._mark_missing("movies", known, seen)
        self._job_end(job, "completed", len(files), len(files),
                      f"{stats['new']} novos, {stats['updated']} actualizados, "
                      f"{stats['skipped']} sem alterações, {stats['missing']} em falta")
        log.info("Inventário de filmes concluído: %s", stats)
        return stats

    def _movie_sidecars(self, f: Path) -> dict:
        stem = f.stem
        try:
            siblings = list(f.parent.iterdir())
        except OSError:
            siblings = []
        videos_here = [s for s in siblings if s.suffix.lower() in VIDEO_EXTENSIONS]
        alone = len(videos_here) == 1
        subs, cover = [], None
        for s in siblings:
            ext = s.suffix.lower()
            if ext in SUBTITLE_EXTENSIONS and (s.name.startswith(stem) or alone):
                subs.append(s.name)
            elif ext in IMAGE_EXTENSIONS and cover is None:
                base = s.stem.lower()
                if (alone and base in MOVIE_COVER_NAMES) or base in (
                        f"{stem.lower()}-poster", f"{stem.lower()}.poster", f"{stem.lower()}"):
                    cover = str(s)
        names = {s.name.lower() for s in siblings}
        has_nfo = f"{stem.lower()}.nfo" in names or (alone and "movie.nfo" in names)
        has_json = f"{stem.lower()}.metadata.json" in names
        return {
            "external_subtitles": ", ".join(sorted(subs)),
            "has_cover": 1 if cover else 0, "cover_path": cover,
            "has_nfo": 1 if has_nfo else 0, "has_metadata_json": 1 if has_json else 0,
        }

    def _refresh_movie_sidecars(self, f: Path) -> None:
        sc = self._movie_sidecars(f)
        self.db.execute(
            "UPDATE movies SET external_subtitles=?, has_cover=?, cover_path=?, has_nfo=?, "
            "has_metadata_json=? WHERE path=?",
            (sc["external_subtitles"], sc["has_cover"], sc["cover_path"], sc["has_nfo"],
             sc["has_metadata_json"], str(f)))

    def _analyse_movie(self, f: Path, st: os.stat_result, has_probe: bool) -> dict:
        guess = parse_filename(f.name)
        # se o nome do ficheiro não tem ano, tentar a pasta (ex.: "Filme (2010)/filme.mkv")
        if not guess["year"] and f.parent.name:
            g2 = parse_filename(f.parent.name + ".x")
            if g2["year"]:
                guess = g2
        row = {
            "path": str(f), "folder": str(f.parent), "filename": f.name,
            "extension": f.suffix.lower().lstrip("."), "size": st.st_size, "mtime": st.st_mtime,
            "title_guess": guess["title"], "year_guess": guess["year"],
            "confidence": guess["confidence"], "scanned_at": now_iso(), "probe_error": None,
        }
        row.update(self._movie_sidecars(f))
        if st.st_size == 0:
            row["status"] = "zero_bytes"
            self.db.log_error("warning", "scanner", str(f),
                              "Ficheiro de vídeo com 0 bytes (preservado, não processado).")
            return row
        if not has_probe:
            row["status"] = "ok"
            return row
        try:
            info = summarize_video(probe(f, self.timeout))
            if not info.pop("has_video"):
                raise ProbeError("Sem fluxo de vídeo.")
            row.update(info)
            row["status"] = "ok"
        except ProbeError as e:
            row["status"] = "invalid"
            row["probe_error"] = str(e)
            self.db.log_error("warning", "scanner", str(f), f"Vídeo inválido ou incompleto: {e}")
        return row

    # -- MÚSICA ------------------------------------------------------------
    def scan_music(self, folder: str | Path) -> dict:
        folder = Path(folder).expanduser()
        if not folder.is_dir():
            raise FileNotFoundError(f"A pasta de música não existe: {folder}")
        job = self._job_start("inventario_musica")
        self.progress(0, 0, "A procurar ficheiros de áudio…")
        files = _walk(folder, AUDIO_EXTENSIONS, self.skip)
        known = self._known("music", folder)
        incremental = bool(self.db.get_setting("incremental"))
        has_probe = ffprobe_path() is not None
        stats = {"total": len(files), "new": 0, "updated": 0, "skipped": 0,
                 "zero_bytes": 0, "invalid": 0, "missing": 0}
        seen: set[str] = set()
        cover_cache: dict[Path, str | None] = {}
        for i, f in enumerate(files, 1):
            if self._cancel:
                self._job_end(job, "cancelled", len(files), i - 1, "Cancelado pelo utilizador.")
                stats["cancelled"] = True
                return stats
            self.progress(i, len(files), f.name)
            sp = str(f)
            seen.add(sp)
            try:
                st = f.stat()
            except OSError as e:
                self.db.log_error("error", "scanner", sp, f"Sem acesso: {e}")
                continue
            prev = known.get(sp)
            if (incremental and prev and prev["size"] == st.st_size
                    and prev["mtime"] == st.st_mtime and prev["status"] != "missing"):
                stats["skipped"] += 1
                continue
            row = self._analyse_track(f, st, has_probe, cover_cache)
            if row["status"] in ("zero_bytes", "invalid"):
                stats[row["status"]] += 1
            stats["updated" if prev else "new"] += 1
            self.db.upsert_music(row)
        stats["missing"] = self._mark_missing("music", known, seen)
        self._job_end(job, "completed", len(files), len(files),
                      f"{stats['new']} novas, {stats['updated']} actualizadas, "
                      f"{stats['skipped']} sem alterações, {stats['missing']} em falta")
        log.info("Inventário de música concluído: %s", stats)
        return stats

    def _folder_cover(self, folder: Path, cache: dict) -> str | None:
        if folder in cache:
            return cache[folder]
        found = None
        try:
            for s in folder.iterdir():
                if s.suffix.lower() in IMAGE_EXTENSIONS and s.stem.lower() in MUSIC_COVER_NAMES:
                    found = str(s)
                    break
        except OSError:
            pass
        cache[folder] = found
        return found

    def _analyse_track(self, f: Path, st: os.stat_result, has_probe: bool, cache: dict) -> dict:
        row = {
            "path": str(f), "folder": str(f.parent), "filename": f.name,
            "extension": f.suffix.lower().lstrip("."), "size": st.st_size, "mtime": st.st_mtime,
            "scanned_at": now_iso(), "probe_error": None,
            "folder_cover": self._folder_cover(f.parent, cache), "has_embedded_cover": 0,
        }
        if st.st_size == 0:
            row["status"] = "zero_bytes"
            self.db.log_error("warning", "scanner", str(f),
                              "Ficheiro de áudio com 0 bytes (preservado, não processado).")
            return row
        tags: dict = {}
        cover = False
        if tagging.HAS_MUTAGEN:
            try:
                tags, cover = tagging.read_tags_mutagen(f)
            except Exception as e:  # noqa: BLE001
                log.debug("Mutagen falhou em %s: %s", f, e)
        status = "ok"
        if has_probe:
            try:
                info = summarize_audio(probe(f, self.timeout))
                if not info["has_audio"]:
                    raise ProbeError("Sem fluxo de áudio.")
                for k in ("codec", "duration", "bitrate", "sample_rate", "channels"):
                    row[k] = info[k]
                cover = cover or info["has_embedded_cover"]
                if not tags:
                    tags = tagging.normalize(info["tags"])
            except ProbeError as e:
                status = "invalid"
                row["probe_error"] = str(e)
                self.db.log_error("warning", "scanner", str(f), f"Áudio inválido: {e}")
        row.update({k: tags.get(k) for k in ("artist", "album_artist", "album", "title",
                                              "track", "disc", "year", "genre")})
        row["has_embedded_cover"] = 1 if cover else 0
        row["status"] = status
        artist_id = self.db.get_or_create_artist(row.get("album_artist") or row.get("artist"))
        row["artist_id"] = artist_id
        row["album_id"] = self.db.get_or_create_album(artist_id, row.get("album"),
                                                      row.get("year"), str(f.parent))
        return row
