"""Sistema de duplicados transversal (Fase 8).

* Exactos: mesmo tamanho e mesmo SHA256 (filmes, música, legendas, capas, auxiliares).
* Prováveis: filmes com o mesmo título e ano; faixas com o mesmo artista, título e
  duração (±3 s).
* Versões diferentes (ao vivo, remix, remaster, edições, qualidades): assinaladas
  como «versão», nunca como duplicado definitivo.
* Nunca apaga: o utilizador pode enviar para a quarentena (reversível).
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from .database import Database, now_iso
from .safety import sha256_file

EXACT, PROBABLE, VERSION = "exacto", "provável", "versão"
VERSION_WORDS = re.compile(
    r"\b(live|ao vivo|en vivo|remix|mix|remaster(ed)?|remasterizad[oa]|acoustic|ac[uú]stic[oa]|"
    r"demo|edit|radio edit|extended|instrumental|karaoke|version|vers[aã]o|deluxe|mono|stereo|"
    r"director'?s cut|unrated|extended cut|theatrical)\b", re.I)

AUX_EXT = {".nfo", ".json", ".txt"}

HASH_TABLE = """CREATE TABLE IF NOT EXISTS file_hashes (
    path TEXT PRIMARY KEY, size INTEGER, mtime REAL, sha256 TEXT)"""


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "filme"
    if ext in AUDIO_EXTENSIONS:
        return "música"
    if ext in SUBTITLE_EXTENSIONS:
        return "legenda"
    if ext in IMAGE_EXTENSIONS:
        return "capa"
    return "auxiliar"


class DuplicateFinder:
    def __init__(self, db: Database):
        self.db = db
        db.execute(HASH_TABLE)

    def roots(self) -> list[Path]:
        out = []
        for key in ("movies_folder", "music_source_folder", "music_library_folder"):
            v = self.db.get_setting(key)
            if v and Path(v).is_dir():
                p = Path(v).resolve()
                if not any(p == r or r in p.parents for r in out):
                    out = [r for r in out if p not in r.parents] + [p]
        return out

    def _hash(self, path: Path, st: os.stat_result) -> str:
        r = self.db.query_one("SELECT size, mtime, sha256 FROM file_hashes WHERE path=?", (str(path),))
        if r and r["size"] == st.st_size and r["mtime"] == st.st_mtime:
            return r["sha256"]
        h = sha256_file(path)
        self.db.execute("INSERT OR REPLACE INTO file_hashes(path, size, mtime, sha256) VALUES(?,?,?,?)",
                        (str(path), st.st_size, st.st_mtime, h))
        return h

    # ----------------------------------------------------------------------
    def analyse(self, progress: Callable | None = None, cancelled: Callable | None = None) -> dict:
        progress = progress or (lambda *_: None)
        cancelled = cancelled or (lambda: False)
        quarantine = Path(self.db.get_setting("quarantine_folder") or "").resolve()
        exts = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | SUBTITLE_EXTENSIONS | IMAGE_EXTENSIONS | AUX_EXT
        by_size: dict[int, list[Path]] = defaultdict(list)
        progress(0, 0, "A listar ficheiros…")
        for root in self.roots():
            for dp, dn, fns in os.walk(root):
                dn[:] = [d for d in dn if not d.startswith(".") and "Quarentena" not in d
                         and Path(dp, d).resolve() != quarantine]
                for fn in fns:
                    p = Path(dp) / fn
                    if p.suffix.lower() not in exts:
                        continue
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    if st.st_size > 0:
                        by_size[st.st_size].append(p)
        candidates = [ps for ps in by_size.values() if len(ps) > 1]
        total = sum(len(ps) for ps in candidates)
        groups: list[dict] = []
        n = 0
        for ps in candidates:
            by_hash = defaultdict(list)
            for p in ps:
                if cancelled():
                    return {"cancelled": True}
                n += 1
                progress(n, total, p.name)
                try:
                    by_hash[self._hash(p, p.stat())].append(p)
                except OSError:
                    continue
            for h, same in by_hash.items():
                if len(same) > 1:
                    keep = self._keep_exact(same)
                    groups.append({"type": EXACT, "kind": kind_of(str(same[0])), "sha256": h,
                                   "size": same[0].stat().st_size,
                                   "items": [{"path": str(p), "size": p.stat().st_size,
                                              "keep": p == keep, "info": ""} for p in same],
                                   "recommendation": f"Manter «{keep.name}» ({keep.parent.name}); "
                                                     "os outros são cópias exactas."})
        exact_paths = {i["path"] for g in groups for i in g["items"]}
        groups += self._probable_movies(exact_paths)
        groups += self._probable_music(exact_paths)
        self._store(groups)
        return self.summary(groups)

    @staticmethod
    def _keep_exact(paths: list[Path]) -> Path:
        # preferir o que está numa pasta já organizada «Título (Ano)» / biblioteca, e o caminho mais curto
        def score(p: Path):
            organised = bool(re.search(r"\(\d{4}\)", p.parent.name))
            return (not organised, len(p.parts), str(p))
        return sorted(paths, key=score)[0]

    def _probable_movies(self, exclude: set[str]) -> list[dict]:
        rows = self.db.query("SELECT * FROM movies WHERE status='ok'")
        groups = defaultdict(list)
        for r in rows:
            if r["path"] in exclude or not r["title_guess"] or not r["year_guess"]:
                continue
            groups[(norm(r["title_guess"]), r["year_guess"])].append(r)
        out = []
        for (_t, _y), items in groups.items():
            if len(items) < 2:
                continue
            best = max(items, key=lambda r: ((r["height"] or 0), (r["size"] or 0)))
            versions = len({(r["resolution"], r["video_codec"]) for r in items}) > 1 or \
                any(VERSION_WORDS.search(r["filename"]) for r in items)
            out.append({
                "type": VERSION if versions else PROBABLE, "kind": "filme",
                "size": sum(r["size"] or 0 for r in items) - (best["size"] or 0),
                "items": [{"path": r["path"], "size": r["size"], "keep": r is best,
                           "info": f"{r['resolution'] or '?'} {r['video_codec'] or ''} "
                                   f"{round((r['size'] or 0) / 2**30, 2)} GB".strip()} for r in items],
                "recommendation": (f"Versões diferentes do mesmo filme. Se só quiser uma, a de "
                                   f"melhor qualidade é «{Path(best['path']).name}».") if versions else
                                  f"Provavelmente o mesmo filme. Manter «{Path(best['path']).name}».",
            })
        return out

    def _probable_music(self, exclude: set[str]) -> list[dict]:
        rows = self.db.query("SELECT * FROM music WHERE status='ok' AND title IS NOT NULL")
        groups = defaultdict(list)
        for r in rows:
            if r["path"] in exclude:
                continue
            groups[(norm(r["album_artist"] or r["artist"]), norm(r["title"]))].append(r)
        out = []
        for _k, items in groups.items():
            if len(items) < 2:
                continue
            # agrupar por duração parecida (±3 s)
            items.sort(key=lambda r: r["duration"] or 0)
            clusters, cur = [], [items[0]]
            for r in items[1:]:
                if abs((r["duration"] or 0) - (cur[-1]["duration"] or 0)) <= 3:
                    cur.append(r)
                else:
                    clusters.append(cur)
                    cur = [r]
            clusters.append(cur)
            for cl in clusters:
                if len(cl) < 2:
                    continue
                best = max(cl, key=lambda r: ((r["bitrate"] or 0), (r["sample_rate"] or 0)))
                texts = [f"{r['title']} {r['album'] or ''}" for r in cl]
                versions = any(VERSION_WORDS.search(t) for t in texts) or \
                    len({norm(r["album"]) for r in cl}) > 1
                out.append({
                    "type": VERSION if versions else PROBABLE, "kind": "música",
                    "size": sum(r["size"] or 0 for r in cl) - (best["size"] or 0),
                    "items": [{"path": r["path"], "size": r["size"], "keep": r is best,
                               "info": f"{(r['codec'] or '').upper()} "
                                       f"{round((r['bitrate'] or 0) / 1000)} kbps · {r['album'] or '—'}"}
                              for r in cl],
                    "recommendation": ("Possíveis versões diferentes (álbuns/edições distintos): "
                                       "verifique antes de mexer.") if versions else
                                      f"Mesma faixa. Melhor qualidade: «{Path(best['path']).name}».",
                })
        return out

    def _store(self, groups: list[dict]) -> None:
        self.db.execute("DELETE FROM duplicates")
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        for i, g in enumerate(groups, 1):
            gid = f"G{stamp}_{i:04d}"
            g["group_id"] = gid
            for it in g["items"]:
                self.db.execute(
                    "INSERT INTO duplicates(group_id, media_type, path, sha256, method, confidence, created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (gid, g["kind"], it["path"], g.get("sha256"), g["type"],
                     "manter" if it["keep"] else "candidato", now_iso()))

    @staticmethod
    def summary(groups: list[dict]) -> dict:
        exact = [g for g in groups if g["type"] == EXACT]
        prob = [g for g in groups if g["type"] == PROBABLE]
        vers = [g for g in groups if g["type"] == VERSION]
        return {
            "groups": groups,
            "exact": sum(len(g["items"]) - 1 for g in exact),
            "probable": sum(len(g["items"]) - 1 for g in prob),
            "versions": sum(len(g["items"]) for g in vers),
            "space_exact": sum(g["size"] * (len(g["items"]) - 1) for g in exact),
            "space_probable": sum(g["size"] for g in prob),
        }
