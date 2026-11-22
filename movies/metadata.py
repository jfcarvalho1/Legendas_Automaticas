"""Capas, metadata.json e NFO dos filmes (Fase 6).

Regras: capas e ficheiros existentes são preservados. Só com «substituir» é que
o antigo vai para a quarentena antes de o novo ser criado. A fonte fica registada.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.database import Database, now_iso
from core.safety import SafeFileManager, SafetyError

from .nfo import build_nfo
from .posters import choose_poster, existing_cover, image_kind
from .subtitle_manager import list_subtitles


def _extra(movie: dict) -> dict:
    try:
        return json.loads(movie.get("extra") or "{}")
    except json.JSONDecodeError:
        return {}


class MetadataManager:
    def __init__(self, db: Database, files: SafeFileManager | None = None, tmdb=None):
        self.db = db
        self.files = files or SafeFileManager(db)
        self.tmdb = tmdb
        self.cover_name = db.get_setting("jellyfin_cover_name") or "cover.jpg"

    # ------------------------------------------------------------ recolha
    def gather(self, movie: dict) -> tuple[dict, str]:
        """Junta a informação local com a do TMDb (se houver). Devolve (info, nota)."""
        video = Path(movie["path"])
        extra = _extra(movie)
        subs = [s["language"] for s in list_subtitles(video) if s["language"]]
        info = {
            "title": movie.get("title_guess"),
            "original_title": extra.get("original_title") or movie.get("title_guess"),
            "year": movie.get("year_guess"),
            "duration_minutes": round(movie["duration"] / 60) if movie.get("duration") else None,
            "video_file": video.name,
            "subtitle": next((s["name"] for s in list_subtitles(video)
                              if s["language"] == "pt-PT"), None),
            "subtitle_languages": sorted(set(subs)),
            "technical": {
                "resolution": movie.get("resolution"), "width": movie.get("width"),
                "height": movie.get("height"), "video_codec": movie.get("video_codec"),
                "audio_codec": movie.get("audio_codec"),
                "audio_languages": movie.get("audio_languages"),
                "duration_seconds": round(movie["duration"]) if movie.get("duration") else None,
            },
            "sources": ["ficheiro"],
            "updated": now_iso(),
        }
        note = ""
        if not self.tmdb:
            return info, "Sem TMDb: só dados locais."
        tmdb_id = extra.get("tmdb_id")
        if not tmdb_id and info["title"]:
            hit = self.tmdb.match(info["title"], info["year"])
            tmdb_id = hit["tmdb_id"] if hit else None
        if not tmdb_id:
            return info, "Não encontrado no TMDb com confiança suficiente."
        d = self.tmdb.details(tmdb_id, self.db.get_setting("tmdb_metadata_language") or "pt-PT")
        ry = int(d["release_date"][:4]) if (d.get("release_date") or "")[:4].isdigit() else None
        if info["year"] and ry and abs(ry - int(info["year"])) > 1:
            return info, f"TMDb devolveu um filme de {ry}: ignorado (possível homónimo)."
        if not (d.get("overview") or "").strip():   # sem sinopse em pt-PT: tentar inglês
            try:
                d_en = self.tmdb.details(tmdb_id, "en-US")
                d["overview"] = d_en.get("overview")
            except Exception:  # noqa: BLE001
                pass
        crew = (d.get("credits") or {}).get("crew") or []
        cast = (d.get("credits") or {}).get("cast") or []
        info.update({
            "original_title": d.get("original_title") or info["original_title"],
            "year": ry or info["year"],
            "release_date": d.get("release_date"),
            "imdb_id": d.get("imdb_id") or (d.get("external_ids") or {}).get("imdb_id"),
            "tmdb_id": tmdb_id,
            "genre": [g["name"] for g in d.get("genres") or []],
            "plot": d.get("overview"),
            "tagline": d.get("tagline"),
            "directors": [c["name"] for c in crew if c.get("job") == "Director"],
            "actors": [{"name": c.get("name"), "role": c.get("character")} for c in cast[:15]],
            "countries": [c.get("name") for c in d.get("production_countries") or []],
            "duration_minutes": d.get("runtime") or info["duration_minutes"],
            "sources": ["ficheiro", "TMDb"],
            "_poster_path": choose_poster(d),
        })
        return info, note

    # ------------------------------------------------------------- escrita
    def _replace_or_create(self, path: Path, data: bytes, replace: bool, kind: str,
                           source: str) -> str:
        if path.exists():
            if not replace:
                return "mantido"
            if path.read_bytes() == data:
                return "igual"
            self.files.quarantine(path, "Revertidos", f"Substituído por novo {kind}")
        self.files.create_file(path, data, "create", reason=f"{kind} ({source})",
                               details={"kind": kind, "source": source})
        return "criado"

    def process(self, movie: dict, cover: bool = True, nfo: bool = True, meta: bool = True,
                replace: bool = False) -> dict:
        video = Path(movie["path"])
        folder, stem = video.parent, video.stem
        info, note = self.gather(movie)
        source = "TMDb" if "TMDb" in info["sources"] else "dados locais"
        res = {"cover": "—", "nfo": "—", "json": "—", "note": note}
        poster_path = info.pop("_poster_path", None)

        # capa
        if cover:
            cur = existing_cover(folder, stem)
            if cur and not replace:
                res["cover"] = "mantida"
                info["poster"] = cur.name
            elif self.tmdb and poster_path:
                data = self.tmdb.image(poster_path)
                ext = image_kind(data)
                if not ext:
                    res["cover"] = "imagem inválida"
                else:
                    name = Path(self.cover_name).stem + ext
                    if cur and replace:
                        self.files.quarantine(cur, "Revertidos", "Capa substituída")
                    self.files.create_file(folder / name, data, "create",
                                           reason="Capa (TMDb)",
                                           details={"kind": "cover", "source": "TMDb",
                                                    "url_path": poster_path})
                    self.db.execute(
                        "INSERT INTO covers(media_type, media_id, path, source, created_at) "
                        "VALUES('movie', ?, ?, ?, ?)",
                        (movie["id"], str(folder / name), f"TMDb {poster_path}", now_iso()))
                    res["cover"] = "obtida"
                    info["poster"] = name
            else:
                res["cover"] = "sem fonte" if not cur else "mantida"

        # metadata.json (campos extra existentes são mantidos)
        if meta:
            jp = folder / f"{stem}.metadata.json"
            current = {}
            if jp.exists():
                try:
                    current = json.loads(jp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    current = {}
            merged = {**current, **{k: v for k, v in info.items() if v not in (None, "", [])}}
            data = json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")
            res["json"] = self._replace_or_create(jp, data, replace, "metadata.json", source)

        # NFO
        if nfo:
            np_ = folder / f"{stem}.nfo"
            res["nfo"] = self._replace_or_create(np_, build_nfo(info), replace, "NFO", source)

        # inventário
        extra = _extra(movie)
        for k in ("tmdb_id", "imdb_id", "original_title"):
            if info.get(k):
                extra[k] = info[k]
        self.db.execute("UPDATE movies SET extra=? WHERE id=?",
                        (json.dumps(extra, ensure_ascii=False), movie["id"]))
        from core.scanner import Scanner
        Scanner(self.db).refresh_movie_sidecars(video)
        return res

    def safe_process(self, movie: dict, **kw) -> dict:
        try:
            return self.process(movie, **kw)
        except (SafetyError, OSError, Exception) as e:  # noqa: BLE001
            self.db.log_error("error", "metadata", movie.get("path"), str(e))
            return {"cover": "erro", "nfo": "erro", "json": "erro", "note": str(e)}
