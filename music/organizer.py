"""Organização da música (Fase 7): Artista/Álbum (Ano)/NN - Faixa.ext

* Por defeito COPIA da pasta de origem para a biblioteca (o original fica intacto,
  validado por SHA256). Modo «mover» configurável.
* Nunca converte nem altera a qualidade do áudio.
* Versões diferentes são preservadas (nome com formato/bitrate).
* Correcções de tags só nas cópias da biblioteca e só quando o utilizador as indica.
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.database import Database
from core.logger import get_logger
from core.organizer import CONFLICT, DONE, ERROR, ORGANIZED, READY, UNCERTAIN, sanitize
from core.safety import SafeFileManager, SafetyError, sha256_file

from . import tagging

log = get_logger("music.organizer")

_FN = re.compile(r"^\s*(?:(\d{1,3})\s*[-._)]\s*)?(?:(.+?)\s+-\s+)?(.+?)\s*$")


def parse_track_filename(stem: str) -> dict:
    """'03 - Artista - Título' / '03. Título' / 'Artista - Título'."""
    m = _FN.match(stem.replace("_", " "))
    if not m:
        return {}
    track, artist, title = m.groups()
    return {"track": int(track) if track else None, "artist": artist, "title": title}


class MusicOrganizer:
    def __init__(self, db: Database, files: SafeFileManager | None = None, musicbrainz=None):
        self.db = db
        self.files = files or SafeFileManager(db)
        self.mb = musicbrainz
        self.source = Path(db.get_setting("music_source_folder") or "").expanduser()
        self.library = Path(db.get_setting("music_library_folder") or "").expanduser()
        self.mode = db.get_setting("music_mode") or "copy"
        self.cover_name = db.get_setting("jellyfin_cover_name") or "cover.jpg"

    # ------------------------------------------------------------- propor
    def propose(self, progress: Callable | None = None, cancelled: Callable | None = None) -> list[dict]:
        progress = progress or (lambda *_: None)
        cancelled = cancelled or (lambda: False)
        if not self.source.is_dir():
            raise FileNotFoundError(f"A pasta de origem da música não existe: {self.source}")
        if not str(self.library) or str(self.library) == ".":
            raise FileNotFoundError("Defina a pasta da biblioteca de música na Configuração.")
        prefix = os.path.join(str(self.source), "")
        tracks = [t for t in self.db.query("SELECT * FROM music WHERE status='ok' ORDER BY path")
                  if t["path"].startswith(prefix) and Path(t["path"]).exists()]
        props = []
        for i, t in enumerate(tracks, 1):
            if cancelled():
                break
            progress(i, len(tracks), t["filename"])
            props.append(self._identify(t))
        self._album_years(props)
        for p in props:
            self._plan(p)
        self._collisions(props)
        return props

    def _identify(self, t: dict) -> dict:
        src = Path(t["path"])
        p = {"music_id": t["id"], "path": str(src), "filename": src.name,
             "artist": t.get("album_artist") or t.get("artist"), "album": t.get("album"),
             "title": t.get("title"), "track": t.get("track"), "disc": t.get("disc"),
             "year": t.get("year"), "codec": t.get("codec") or src.suffix.lstrip("."),
             "bitrate": t.get("bitrate"), "size": t.get("size"),
             "folder_cover": t.get("folder_cover"), "embedded": bool(t.get("has_embedded_cover")),
             "confidence": "alta", "source": "tags", "note": "", "tag_updates": {},
             "checked": False, "status": UNCERTAIN, "target": "", "files": []}
        guessed: list[str] = []          # campos deduzidos do nome (não vêm das tags)
        if not p["title"] or not p["track"]:
            g = parse_track_filename(src.stem)
            if not p["title"] and g.get("title"):
                p["title"] = g["title"]
                guessed.append("title")
            if not p["track"] and g.get("track"):
                p["track"] = g["track"]
                guessed.append("track")
            if not p["artist"] and g.get("artist"):
                p["artist"] = g["artist"]
                guessed.append("artist")
        rel = src.parent.relative_to(self.source).parts if src.parent != self.source else ()
        if not p["album"] and len(rel) >= 1:
            p["album"] = re.sub(r"\s*[\[(]\d{4}[\])]\s*$", "", rel[-1]).strip()
            guessed.append("album")
        if not p["artist"] and len(rel) >= 2:
            p["artist"] = rel[-2]
            guessed.append("artist")
        if guessed:
            labels = {"title": "título", "track": "faixa", "artist": "artista", "album": "álbum"}
            p["confidence"] = "média"
            p["source"] = "nome do ficheiro/pasta"
            p["note"] = "Deduzido do nome: " + ", ".join(labels[g] for g in guessed) + ". Confirme."
            p["tag_updates"] = {g: p[g] for g in guessed}
        if not p["artist"] or not p["title"]:
            p["confidence"] = "baixa"
            p["note"] = "Sem artista ou título: corrija antes de organizar."
        return p

    def _album_years(self, props: list[dict]) -> None:
        """Um álbum fica numa só pasta: usa o ano mais frequente das faixas
        (e, se faltar, o do MusicBrainz quando activo)."""
        groups = defaultdict(list)
        for p in props:
            if p["artist"] and p["album"]:
                groups[(p["artist"].lower(), p["album"].lower())].append(p)
        for (_a, _b), items in groups.items():
            years = [p["year"] for p in items if p["year"]]
            year = Counter(years).most_common(1)[0][0] if years else None
            if not year and self.mb:
                try:
                    r = self.mb.release(items[0]["artist"], items[0]["album"])
                    if r:
                        year = r["year"]
                        for p in items:
                            p["tag_updates"]["year"] = year
                            p["source"] += " + MusicBrainz"
                except Exception as e:  # noqa: BLE001
                    log.info("MusicBrainz: %s", e)
            multi = any((p["disc"] or 1) > 1 for p in items)
            for p in items:
                p["album_year"] = year
                p["multi_disc"] = multi

    def _plan(self, p: dict, quality_suffix: bool = False) -> None:
        if p["confidence"] == "baixa":
            p["status"], p["checked"] = UNCERTAIN, False
            return
        src = Path(p["path"])
        artist = sanitize(p["artist"]) or "Desconhecido"
        album = sanitize(p["album"] or "Sem álbum")
        year = p.get("album_year") or p.get("year")
        album_dir = self.library / artist / (f"{album} ({year})" if year else album)
        title = sanitize(p["title"])
        if p.get("track"):
            num = f"{p['track']:02d}"
            if p.get("multi_disc"):
                num = f"{p.get('disc') or 1}-{num}"
            name = f"{num} - {title}"
        else:
            name = title
        if quality_suffix:
            kb = f" {round(p['bitrate'] / 1000)}kbps" if p.get("bitrate") else ""
            name += f" [{(p['codec'] or '').upper()}{kb}]"
        dst = album_dir / f"{name}{src.suffix.lower()}"
        p["target"] = str(dst)
        p["album_dir"] = str(album_dir)
        p["files"] = [{"src": str(src), "dst": str(dst), "kind": "faixa"}]
        if str(src).lower() == str(dst).lower():
            p["status"], p["checked"] = ORGANIZED, False
        else:
            p["status"] = READY
            # deduzidos do nome («média») ficam por confirmar pelo utilizador
            p["checked"] = p["confidence"] in ("alta", "manual")

    def _collisions(self, props: list[dict]) -> None:
        claimed: dict[str, dict] = {}
        for p in props:
            if p["status"] != READY:
                continue
            for attempt in (False, True):
                if attempt:
                    self._plan(p, quality_suffix=True)
                key = p["target"].lower()
                dst = Path(p["target"])
                if key in claimed:
                    other = claimed[key]
                    if other.get("size") == p.get("size") and \
                            sha256_file(other["path"]) == sha256_file(p["path"]):
                        p["status"], p["checked"] = ORGANIZED, False
                        p["note"] = "Duplicado exacto de outra faixa da lista: não é copiado."
                        break
                    continue
                if dst.exists():
                    if dst.stat().st_size == p.get("size") and sha256_file(dst) == sha256_file(p["path"]):
                        p["status"], p["checked"] = ORGANIZED, False
                        p["note"] = "Já existe na biblioteca (idêntico)."
                        break
                    continue
                claimed[key] = p
                if attempt:
                    p["note"] = "Outra versão já existe: guardada com formato/bitrate no nome."
                break
            else:
                p["status"], p["checked"] = CONFLICT, False
                p["note"] = "Conflito de nomes na biblioteca."

    def edit(self, props: list[dict], indexes: list[int], values: dict) -> None:
        """Correcção manual (aplica-se a uma ou várias faixas)."""
        for i in indexes:
            p = props[i]
            for k in ("artist", "album", "year", "title", "track"):
                if values.get(k) not in (None, ""):
                    p[k] = values[k]
                    p["tag_updates"][k] = values[k]
                    if k == "year":
                        p["album_year"] = values[k]
            if p["artist"] and p["title"]:
                p["confidence"], p["source"], p["note"] = "manual", "manual", ""
        for i in indexes:
            self._plan(props[i])
        self._collisions(props)

    # ------------------------------------------------------------ aplicar
    def apply(self, props: list[dict], progress: Callable | None = None) -> dict:
        progress = progress or (lambda *_: None)
        todo = [p for p in props if p.get("checked") and p["status"] == READY]
        batch = datetime.now().strftime("MUSICA_%Y%m%d_%H%M%S")
        s = {"batch": batch, "tracks": 0, "covers": 0, "tags": 0, "errors": []}
        covers_done: set[str] = set()
        for i, p in enumerate(todo, 1):
            progress(i, len(todo), p["filename"])
            details = {"batch": batch, "music_id": p["music_id"], "kind": "faixa"}
            try:
                if self.mode == "move":
                    self.files.safe_move(p["path"], p["target"], "move",
                                         reason="Organizar música", details=details)
                else:
                    self.files.safe_copy(p["path"], p["target"], reason="Organizar música",
                                         details=details)
                s["tracks"] += 1
            except (SafetyError, OSError) as e:
                p["status"], p["checked"] = ERROR, False
                s["errors"].append(f"{p['filename']}: {e}")
                continue
            if p.get("tag_updates") and tagging.HAS_MUTAGEN:
                try:
                    old = tagging.write_tags(p["target"], p["tag_updates"])
                    op = self.files.ops.new_operation_id()
                    self.files.ops.record(op, "tag", None, p["target"], "completed",
                                          result="Tags corrigidas na cópia da biblioteca.",
                                          details={"batch": batch, "new": p["tag_updates"],
                                                   "old": old})
                    s["tags"] += 1
                except Exception as e:  # noqa: BLE001
                    s["errors"].append(f"Tags de {p['filename']}: {e}")
            ad = p["album_dir"]
            if ad not in covers_done:
                try:
                    if self._album_cover(p, batch):
                        s["covers"] += 1
                        covers_done.add(ad)
                except (SafetyError, OSError) as e:
                    s["errors"].append(f"Capa de {Path(ad).name}: {e}")
                    covers_done.add(ad)
            p["status"], p["checked"] = DONE, False
        self.db.set_setting("last_music_batch", batch)
        log.info("Música organizada: %s", s)
        return s

    def _album_cover(self, p: dict, batch: str) -> bool:
        album_dir = Path(p["album_dir"])
        try:
            if any(f.stem.lower() in ("cover", "folder", "front") for f in album_dir.iterdir()):
                return False
        except OSError:
            return False
        details = {"batch": batch, "kind": "cover"}
        src = p.get("folder_cover")
        if src and Path(src).exists():
            dst = album_dir / (Path(self.cover_name).stem + Path(src).suffix.lower())
            self.files.safe_copy(src, dst, reason="Capa do álbum", details={**details, "source": "pasta"})
            return True
        data = tagging.embedded_cover(p["target"]) if p.get("embedded") else None
        if data:
            from movies.posters import image_kind
            ext = image_kind(data) or ".jpg"
            self.files.create_file(album_dir / (Path(self.cover_name).stem + ext), data, "create",
                                   reason="Capa embutida extraída",
                                   details={**details, "source": "capa embutida"})
            return True
        return False
