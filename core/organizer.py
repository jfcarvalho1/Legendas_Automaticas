"""Organização e renomeação de filmes (Fase 3).

Fluxo: propor (só lê) → o utilizador revê/edita → aplicar (lote reversível).

Estrutura final:
    Filmes/Título (Ano)/Título (Ano).mkv
                       /Título (Ano).pt-PT.srt
                       /cover.jpg
                       /Título (Ano).nfo
                       /Título (Ano).metadata.json
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from movies.identification import parse_filename

from .config import IMAGE_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from .database import Database, now_iso
from .logger import get_logger
from .safety import SafeFileManager, SafetyError

log = get_logger("organizer")

READY = "pronto"
ORGANIZED = "organizado"
UNCERTAIN = "incerto"
CONFLICT = "conflito"
DONE = "aplicado"
ERROR = "erro"

COVER_PREFERENCE = ("cover", "poster", "folder", "movie", "front")
SUB_FOLDER_HINT = ("sub", "subs", "subtitles", "legendas", "legenda", "subtitulos")

_WORDS = {
    "portuguese": "pt", "portugues": "pt", "português": "pt",
    "english": "en", "ingles": "en", "inglês": "en",
    "spanish": "es", "espanol": "es", "español": "es", "castellano": "es", "latino": "es",
    "french": "fr", "francais": "fr", "français": "fr", "german": "de", "deutsch": "de",
    "italian": "it", "italiano": "it", "dutch": "nl", "japanese": "ja", "chinese": "zh",
    "russian": "ru", "arabic": "ar", "polish": "pl", "turkish": "tr", "greek": "el",
    "romanian": "ro", "swedish": "sv", "danish": "da", "norwegian": "no", "finnish": "fi",
    "czech": "cs", "hungarian": "hu", "hebrew": "he", "korean": "ko",
}
# códigos curtos: só valem no fim do nome ("Filme.en.srt"), para não confundir
# palavras de títulos como "Cidade de Deus" com alemão.
_CODES = {
    "pt": "pt", "por": "pt", "en": "en", "eng": "en", "es": "es", "spa": "es", "fr": "fr",
    "fre": "fr", "fra": "fr", "de": "de", "ger": "de", "deu": "de", "it": "it", "ita": "it",
    "nl": "nl", "dut": "nl", "nld": "nl", "ja": "ja", "jpn": "ja", "zh": "zh", "chi": "zh",
    "zho": "zh", "ru": "ru", "rus": "ru", "ar": "ar", "ara": "ar", "pl": "pl", "pol": "pl",
    "tr": "tr", "tur": "tr", "el": "el", "gre": "el", "ro": "ro", "rum": "ro", "sv": "sv",
    "swe": "sv", "da": "da", "dan": "da", "fi": "fi", "fin": "fi", "cs": "cs", "cze": "cs",
    "hu": "hu", "hun": "hu", "he": "he", "heb": "he", "ko": "ko", "kor": "ko",
}
_FLAGS = ("forced", "sdh", "cc")
_BR = {"ptbr", "pob", "brazil", "brazilian", "brasil", "brasileiro", "brasileira"}
_PT = {"ptpt", "portugal", "europeu", "european"}

def sanitize(name: str) -> str:
    """Nome válido em Linux e Windows."""
    name = name.replace(":", " -").replace("/", "-").replace("\\", "-")
    name = re.sub(r'[<>"|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:180]


def clean_title(title: str, strip_the: bool) -> str:
    t = sanitize(title)
    if strip_the and re.match(r"^the\s+\S", t, re.I):
        t = t[4:].lstrip()
    return t


def subtitle_suffix(text: str) -> str:
    """Idioma de uma legenda a partir do nome.
    '.pt-PT' -> '.pt-PT' · '2_English' -> '.en' · 'Portuguese (Brazil)' -> '.pt-BR'
    'Filme.por.forced' -> '.pt.forced' · sem idioma reconhecido -> ''."""
    t = (text or "").lower()
    t = re.sub(r"pt[-_ ]?br\b", " ptbr ", t)
    t = re.sub(r"pt[-_ ]?pt\b", " ptpt ", t)
    tokens = [x for x in re.split(r"[^0-9a-zà-ÿ]+", t) if x]
    toks = set(tokens)
    flags = [f for f in _FLAGS if f in toks]
    core = [x for x in tokens if x not in _FLAGS and not x.isdigit()]
    lang = None
    if toks & _BR:
        lang = "pt-BR"
    elif "ptpt" in toks or "portugal" in toks or (toks & _PT and toks & {"portuguese", "portugues"}):
        lang = "pt-PT"
    else:
        for x in reversed(core):
            if x in _WORDS:
                lang = _WORDS[x]
                break
        if lang is None and core and core[-1] in _CODES:
            lang = _CODES[core[-1]]
    if not lang:
        return ""
    return "." + lang + "".join("." + f for f in flags)


def is_jellyfin_nfo(path: Path) -> bool:
    """NFO em XML (Kodi/Jellyfin). Os .nfo de texto dos grupos de release não contam."""
    try:
        head = path.read_bytes()[:4096].decode("utf-8", "ignore").lower()
    except OSError:
        return False
    return "<movie" in head or "<?xml" in head


def is_sample(path: Path) -> bool:
    low = path.stem.lower()
    return ("sample" in low or "trailer" in low
            or any(part.lower() in ("sample", "samples", "extras", "featurettes", "trailers")
                   for part in path.parent.parts[-2:]))


class MovieOrganizer:
    def __init__(self, db: Database, files: SafeFileManager | None = None, tmdb=None):
        self.db = db
        self.files = files or SafeFileManager(db)
        self.tmdb = tmdb
        self.strip_the = bool(db.get_setting("strip_leading_the"))
        self.clean_leftovers = bool(db.get_setting("clean_leftovers"))
        self.cover_name = db.get_setting("jellyfin_cover_name") or "cover.jpg"
        self.root = Path(db.get_setting("movies_folder") or "").expanduser()

    # ------------------------------------------------------------------ propor
    def propose(self, progress: Callable[[int, int, str], None] | None = None,
                cancelled: Callable[[], bool] | None = None) -> list[dict]:
        progress = progress or (lambda *_: None)
        cancelled = cancelled or (lambda: False)
        if not self.root.is_dir():
            raise FileNotFoundError(f"A pasta de filmes não existe: {self.root}")
        prefix = os.path.join(str(self.root), "")
        movies = [m for m in self.db.query("SELECT * FROM movies WHERE status='ok' ORDER BY path")
                  if m["path"].startswith(prefix) and Path(m["path"]).exists()]
        props: list[dict] = []
        tmdb_error = None
        for i, m in enumerate(movies, 1):
            if cancelled():
                break
            progress(i, len(movies), m["filename"])
            title, year, conf, source, note = self._identify(m)
            extra = {}
            if self.tmdb and title and tmdb_error is None:
                try:
                    hit = self.tmdb.match(title, year)
                    if hit:
                        title, year, conf, source = hit["title"], hit["year"], hit["confidence"], "TMDb"
                        extra = {"tmdb_id": hit["tmdb_id"], "original_title": hit["original_title"]}
                    else:
                        note = "Não confirmado no TMDb."
                except Exception as e:  # noqa: BLE001
                    tmdb_error = str(e)
                    note = f"TMDb indisponível: {e}"
            props.append(self.build(m, title, year, conf, source, note, extra))
        self.resolve_collisions(props)
        return props

    def _identify(self, m: dict) -> tuple:
        g = parse_filename(m["filename"])
        source = "nome do ficheiro"
        if not g["year"]:
            pg = parse_filename(Path(m["folder"]).name + ".x")
            if pg["year"]:
                g, source = pg, "nome da pasta"
        note = "" if g["year"] else "Sem ano no nome: confirme o título e o ano."
        return g["title"], g["year"], g["confidence"], source, note

    def build(self, m: dict, title: str | None, year: int | None, conf: str, source: str,
              note: str = "", extra: dict | None = None) -> dict:
        """Constrói a proposta de um filme (não toca em ficheiros)."""
        src = Path(m["path"])
        p = {
            "movie_id": m["id"], "path": str(src), "filename": src.name,
            "resolution": m.get("resolution") or "", "title": title, "year": year,
            "confidence": conf, "source": source, "note": note, "extra": extra or {},
            "files": [], "checked": False, "status": UNCERTAIN, "target": "",
        }
        if not title or not year or conf == "baixa":
            p["note"] = note or "Identificação incerta: não será alterado sem confirmação."
            return p
        base = f"{clean_title(title, self.strip_the)} ({year})"
        p["base"] = base
        self._plan(p, src, base)
        return p

    def _dedicated(self, folder: Path) -> bool:
        """A pasta (e subpastas) pertence só a este filme? (1 vídeo principal)"""
        if folder == self.root:
            return False
        n = 0
        for dp, _dn, fns in os.walk(folder):
            for fn in fns:
                f = Path(dp) / fn
                if f.suffix.lower() in VIDEO_EXTENSIONS and not is_sample(f):
                    n += 1
                    if n > 1:
                        return False
        return True

    def _plan(self, p: dict, src: Path, base: str, version: str = "") -> None:
        """Define o destino de cada ficheiro. Na pasta final só ficam: vídeo, legendas,
        capa, NFO e metadata.json. O resto da pasta do filme vai para a quarentena."""
        target_dir = self.root / base
        name = base + (f" - {version}" if version else "")
        files = [(src, target_dir / f"{name}{src.suffix.lower()}", "vídeo")]
        folder, stem = src.parent, src.stem
        dedicated = self._dedicated(folder)
        if dedicated:   # tudo o que está na pasta do filme, incluindo Subs/ e afins
            cands = sorted(Path(dp) / fn for dp, _d, fns in os.walk(folder) for fn in fns)
        else:           # pasta partilhada: só ficheiros com o mesmo nome do vídeo
            try:
                cands = sorted(f for f in folder.iterdir() if f.is_file() and f.name.startswith(stem))
            except OSError:
                cands = []
        cands = [c for c in cands if c != src]

        images = [c for c in cands if c.suffix.lower() in IMAGE_EXTENSIONS]

        def cover_rank(c: Path):
            low = c.stem.lower()
            for i, n in enumerate(COVER_PREFERENCE):
                if low == n or low.endswith(f"-{n}") or low.endswith(f".{n}"):
                    return (i, c.parent != folder)
            if c.stem == stem:
                return (len(COVER_PREFERENCE), False)
            return None
        ranked = sorted((r, c) for c in images if (r := cover_rank(c)) is not None)
        cover = ranked[0][1] if ranked else None
        cover_stem = Path(self.cover_name).stem or "cover"

        used = {files[0][1].name.lower()}
        leftovers: list[Path] = []

        def add(s: Path, new_name: str, kind: str):
            n, k = new_name, 2
            while n.lower() in used:
                st, ext = os.path.splitext(new_name)
                n, k = f"{st}.{k}{ext}", k + 1
            used.add(n.lower())
            files.append((s, target_dir / n, kind))

        subs_all = [c for c in cands if c.suffix.lower() in SUBTITLE_EXTENSIONS]
        # legendas que já estão na pasta final com o nome certo mantêm-no
        settled = [c for c in subs_all if c.parent == target_dir
                   and c.name.lower().startswith(name.lower() + ".")
                   and c.name.lower() not in used]
        for c in settled:
            used.add(c.name.lower())
            files.append((c, c, "legenda"))
        subs_first = sorted((c for c in subs_all if c not in settled),
                            key=lambda c: (c.parent != folder, str(c).lower()))
        for c in subs_first:
            rest = c.stem[len(stem):] if c.name.startswith(stem) else c.stem
            lang = subtitle_suffix(rest)
            if not lang and c.parent != folder:      # Subs/Portuguese/1.srt
                lang = subtitle_suffix(c.parent.name)
            add(c, f"{name}{lang}{c.suffix.lower()}", "legenda")
        for c in cands:
            ext = c.suffix.lower()
            if ext in SUBTITLE_EXTENSIONS:
                continue
            if c == cover:
                add(c, f"{cover_stem}{ext}", "capa")
            elif c.name.lower().endswith(".metadata.json"):
                add(c, f"{name}.metadata.json", "metadados")
            elif ext == ".nfo" and is_jellyfin_nfo(c):
                add(c, f"{name}.nfo", "nfo")
            elif dedicated:
                leftovers.append(c)

        p["files"] = [{"src": str(a), "dst": str(b), "kind": k} for a, b, k in files]
        p["leftovers"] = [str(x) for x in leftovers] if self.clean_leftovers else []
        p["old_dir"] = str(folder) if dedicated else ""
        p["target"] = str(files[0][1])
        p["version"] = version
        if all(a == b for a, b, _k in files) and not p["leftovers"]:
            p["status"], p["checked"] = ORGANIZED, False
        else:
            p["status"] = READY
            p["checked"] = p["confidence"] in ("alta", "média", "manual")

    def resolve_collisions(self, props: list[dict]) -> None:
        """Evita que dois filmes vão para o mesmo nome e nunca escreve por cima de nada.
        Se o nome já estiver ocupado tenta «Título (Ano) - 1080p» (versões no Jellyfin)."""
        claimed: dict[str, dict] = {}

        def clash_of(p: dict) -> str | None:
            demoted = []
            for f in p["files"]:
                k = f["dst"].lower()
                other = k in claimed and claimed[k] is not p
                exists = f["src"].lower() != k and Path(f["dst"]).exists()
                if not (other or exists):
                    continue
                if f["kind"] in ("capa", "nfo", "metadados"):
                    demoted.append(f)    # preservar o que já existe no destino
                    continue
                return ("Outro filme da lista vai para o mesmo nome." if other
                        else f"Já existe no destino: {Path(f['dst']).name}")
            for f in demoted:
                p["files"].remove(f)
                if self.clean_leftovers and p.get("old_dir"):
                    p["leftovers"].append(f["src"])
            return None

        def claim(p: dict) -> None:
            for f in p["files"]:
                claimed[f["dst"].lower()] = p

        for p in props:                        # reavaliar conflitos antigos
            if p["status"] == CONFLICT and p.get("base"):
                self._plan(p, Path(p["path"]), p["base"])
        for p in props:                        # os já organizados mantêm o seu nome
            if p["status"] == ORGANIZED:
                claim(p)
        for p in props:
            if p["status"] != READY:
                continue
            c = clash_of(p)
            if c and p.get("resolution") and not p.get("version"):
                self._plan(p, Path(p["path"]), p["base"], p["resolution"])
                c = clash_of(p)
                if not c:
                    p["note"] = f"Outra versão já existe: fica como «{Path(p['target']).name}»."
            if c:
                p["status"], p["checked"], p["note"] = CONFLICT, False, c
                continue
            claim(p)

    def edit(self, props: list[dict], index: int, title: str, year: int | None) -> dict:
        """Correcção manual do utilizador (título/ano)."""
        old = props[index]
        m = self.db.query_one("SELECT * FROM movies WHERE id=?", (old["movie_id"],))
        p = self.build(m, title.strip(), year, "manual" if title.strip() and year else "baixa",
                       "manual", "", old.get("extra"))
        props[index] = p
        self.resolve_collisions(props)
        return props[index]

    # ----------------------------------------------------------------- aplicar
    def apply(self, props: list[dict],
              progress: Callable[[int, int, str], None] | None = None) -> dict:
        progress = progress or (lambda *_: None)
        todo = [p for p in props if p.get("checked") and p["status"] == READY]
        batch = datetime.now().strftime("LOTE_%Y%m%d_%H%M%S")
        summary = {"batch": batch, "movies": 0, "files": 0, "leftovers": 0, "errors": [],
                   "empty_folders": 0}
        for i, p in enumerate(todo, 1):
            progress(i, len(todo), p["filename"])
            old_dir = Path(p["path"]).parent
            ok = True
            for f in p["files"]:
                if f["src"] == f["dst"]:
                    continue
                try:
                    self.files.safe_move(
                        f["src"], f["dst"], "rename",
                        reason=f"Organizar filme: {p.get('base')}",
                        details={"batch": batch, "movie_id": p["movie_id"], "kind": f["kind"],
                                 "source": p["source"], "confidence": p["confidence"]})
                    summary["files"] += 1
                except (SafetyError, OSError) as e:
                    summary["errors"].append(f"{Path(f['src']).name}: {e}")
                    if f["kind"] == "vídeo":
                        ok = False
                        break
            if not ok:
                p["status"], p["checked"] = ERROR, False
                continue
            for lf in p.get("leftovers", []):
                if not Path(lf).exists():
                    continue
                try:
                    self.files.quarantine(lf, "Restos_Organizacao",
                                          f"Não faz parte do filme organizado ({p.get('base')})",
                                          root=self.quarantine_root(),
                                          details={"batch": batch, "movie_id": p["movie_id"]})
                    summary["leftovers"] += 1
                except (SafetyError, OSError) as e:
                    summary["errors"].append(f"{Path(lf).name}: {e}")
            self._update_inventory(p)
            p["status"], p["checked"] = DONE, False
            summary["movies"] += 1
            summary["empty_folders"] += self._remove_empty_tree(old_dir, Path(p["target"]).parent, batch)
        self.db.set_setting("last_rename_batch", batch)
        log.info("Organização aplicada: %s", summary)
        return summary

    def _update_inventory(self, p: dict) -> None:
        from .scanner import Scanner
        new = Path(p["target"])
        extra = json.dumps(p.get("extra") or {}, ensure_ascii=False)
        self.db.execute(
            "UPDATE movies SET path=?, folder=?, filename=?, title_guess=?, year_guess=?, "
            "confidence=?, extra=?, scanned_at=? WHERE id=?",
            (str(new), str(new.parent), new.name, p["title"], p["year"],
             "alta" if p["confidence"] in ("alta", "manual") else p["confidence"], extra,
             now_iso(), p["movie_id"]))
        Scanner(self.db).refresh_movie_sidecars(new)

    def quarantine_root(self) -> Path:
        """Quarentena no mesmo disco dos filmes (movimento instantâneo, sem cópias).
        Fica ao lado da pasta Filmes, fora da biblioteca do Jellyfin."""
        from .safety import same_device
        q = Path(self.db.get_setting("quarantine_folder") or "")
        try:
            if str(q) and same_device(self.root, q):
                return q
        except OSError:
            pass
        return self.root.parent / "Quarentena_MediaOrganizer"

    def _remove_empty_tree(self, folder: Path, keep: Path, batch: str) -> int:
        """Remove pastas que ficaram completamente vazias (ex.: a antiga e a Subs/).
        Nunca remove a pasta Filmes nem a pasta final. A reversão recria-as."""
        if not folder.is_dir() or folder == self.root or self.root not in folder.parents:
            return 0
        n = 0
        for dp, _dn, _fn in sorted(os.walk(folder), key=lambda x: len(x[0]), reverse=True):
            d = Path(dp)
            if d == keep or d == self.root:
                continue
            try:
                if any(d.iterdir()):
                    continue
                op_id = self.files.ops.new_operation_id()
                d.rmdir()
                self.files.ops.record(op_id, "remove_empty_folder", str(d), None, "completed",
                                      result="Pasta vazia removida (recriada ao reverter o lote).",
                                      details={"batch": batch})
                n += 1
            except OSError:
                pass
        return n
