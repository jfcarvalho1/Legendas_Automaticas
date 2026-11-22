"""Automatização (Fase 9): corre os módulos em sequência, com quatro modos.

  analise      — só lê e relata (nada é alterado)
  automatico   — aplica apenas o que é seguro (confiança alta, nunca apaga)
  reparacao    — completa o que falta (NFO, JSON, capas, legendas SRT/pt-PT)
  recuperacao  — retoma o que ficou interrompido e arruma restos de cópias parciais

Cada passo é independente: um erro fica registado e os restantes continuam.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from .config import DATABASE_DIR
from .database import Database, now_iso
from .logger import get_logger
from .safety import SafeFileManager

log = get_logger("automation")

MODES = {
    "analise": "Análise — só lê e relata, não altera nada",
    "automatico": "Automático — aplica só o que é seguro",
    "reparacao": "Reparação — completa o que falta",
    "recuperacao": "Recuperação — retoma tarefas interrompidas",
}
STEPS = [
    ("inventory", "Inventário de filmes e música"),
    ("organize_movies", "Organizar filmes"),
    ("organize_music", "Organizar música"),
    ("subtitles", "Legendas: converter, adaptar pt-BR→pt-PT, procurar"),
    ("translate", "Traduzir legendas para pt-PT (motor local)"),
    ("metadata", "Capas, NFO e metadata.json"),
    ("duplicates", "Análise de duplicados"),
    ("reports", "Relatórios"),
    ("jellyfin", "Jellyfin: verificar e actualizar biblioteca"),
]
LOCK = DATABASE_DIR / "automation.lock"


class Busy(Exception):
    pass


class Automation:
    def __init__(self, db: Database, log_fn: Callable[[str], None] | None = None,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancelled: Callable[[], bool] | None = None):
        self.db = db
        self.files = SafeFileManager(db)
        self.say = log_fn or (lambda m: log.info(m))
        self.progress = progress or (lambda *_: None)
        self.cancelled = cancelled or (lambda: False)
        self.summary: dict = {}

    # ------------------------------------------------------------ helpers
    def _tmdb(self):
        key = (self.db.get_setting("tmdb_api_key") or "").strip()
        if not key:
            return None
        from integrations.tmdb import TMDbClient
        return TMDbClient(key, self.db.get_setting("tmdb_language") or "en-US")

    def _opensubs(self):
        g = self.db.get_setting
        if not (g("opensubtitles_api_key") and g("opensubtitles_username") and g("opensubtitles_password")):
            return None
        from integrations.opensubtitles import OpenSubtitlesClient
        return OpenSubtitlesClient(g("opensubtitles_api_key"), g("opensubtitles_username"),
                                   g("opensubtitles_password"))

    def _lock(self):
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 6 * 3600:
            raise Busy("Já existe uma automatização em curso.")
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(str(os.getpid()))

    # ---------------------------------------------------------------- run
    def run(self, mode: str = "analise", steps: list[str] | None = None) -> dict:
        if mode not in MODES:
            raise ValueError(f"Modo desconhecido: {mode}")
        steps = steps or [k for k, _ in STEPS]
        self._lock()
        job = self.db.execute("INSERT INTO jobs(job_type, started_at, status, total, processed) "
                              "VALUES(?, ?, 'running', ?, 0)",
                              (f"automatizacao_{mode}", now_iso(), len(steps))).lastrowid
        self.say(f"== Automatização: {MODES[mode]} ==")
        status = "completed"
        try:
            if self.db.get_setting("backups_enabled"):
                from .backup import backup_database
                self.say(f"Backup da base de dados: {backup_database(self.db.path).name}")
            if mode == "recuperacao":
                self._recover()
            order = [k for k, _ in STEPS if k in steps]
            for n, key in enumerate(order, 1):
                if self.cancelled():
                    status = "cancelled"
                    self.say("Cancelado.")
                    break
                label = dict(STEPS)[key]
                self.progress(n, len(order), label)
                self.say(f"→ {label}")
                try:
                    getattr(self, f"step_{key}")(mode)
                except Exception as e:  # noqa: BLE001
                    log.exception("Passo %s falhou", key)
                    self.db.log_error("error", "automation", None, f"{label}: {e}")
                    self.say(f"   ! erro: {e}")
                self.db.execute("UPDATE jobs SET processed=? WHERE id=?", (n, job))
        finally:
            msg = "; ".join(f"{k}: {v}" for k, v in self.summary.items())[:900]
            self.db.execute("UPDATE jobs SET finished_at=?, status=?, message=? WHERE id=?",
                            (now_iso(), status, msg, job))
            try:
                LOCK.unlink()
            except OSError:
                pass
        self.say("== Concluído ==")
        return self.summary

    # --------------------------------------------------------------- passos
    def step_inventory(self, mode):
        from .scanner import Scanner
        if mode == "reparacao":   # reanalisar os inválidos
            self.db.execute("UPDATE movies SET mtime=NULL WHERE status='invalid'")
            self.db.execute("UPDATE music SET mtime=NULL WHERE status='invalid'")
        for key, kind in (("movies_folder", "filmes"), ("music_source_folder", "música")):
            folder = self.db.get_setting(key)
            if not folder or not Path(folder).is_dir():
                self.say(f"   pasta de {kind} não definida ou inexistente — ignorado")
                continue
            sc = Scanner(self.db)
            st = sc.scan_movies(folder) if kind == "filmes" else sc.scan_music(folder)
            self.say(f"   {kind}: {st['total']} ficheiros, {st['new']} novos, "
                     f"{st['zero_bytes']} com 0 bytes, {st['invalid']} inválidos")
            self.summary[f"inventário {kind}"] = st["total"]

    def step_organize_movies(self, mode):
        from .organizer import READY, MovieOrganizer
        folder = self.db.get_setting("movies_folder")
        if not folder or not Path(folder).is_dir():
            self.say("   pasta de filmes não definida ou inexistente — ignorado")
            return
        org = MovieOrganizer(self.db, self.files, self._tmdb())
        props = org.propose(cancelled=self.cancelled)
        allowed = {"alta"} | ({"média"} if self.db.get_setting("auto_apply_medium") else set())
        safe = [p for p in props if p["status"] == READY and p["confidence"] in allowed]
        pending = sum(1 for p in props if p["status"] == READY) - len(safe)
        if mode != "automatico":
            self.say(f"   {sum(1 for p in props if p['status'] == READY)} filmes por organizar "
                     f"(nada alterado neste modo)")
            return
        for p in props:
            p["checked"] = p in safe
        s = org.apply(props)
        self.say(f"   {s['movies']} filmes organizados (lote {s['batch']}); "
                 f"{pending} ficam para revisão manual")
        self.summary["filmes organizados"] = s["movies"]

    def step_organize_music(self, mode):
        from music.organizer import MusicOrganizer
        from .organizer import READY
        g = self.db.get_setting
        if not (g("music_source_folder") and g("music_library_folder")):
            self.say("   pastas de música não definidas — ignorado")
            return
        mb = None
        if g("musicbrainz_enabled"):
            from integrations.musicbrainz import MusicBrainzClient
            mb = MusicBrainzClient()
        org = MusicOrganizer(self.db, self.files, mb)
        props = org.propose(cancelled=self.cancelled)
        ready = [p for p in props if p["status"] == READY and p["confidence"] == "alta"]
        if mode != "automatico":
            self.say(f"   {len(ready)} faixas prontas a organizar (nada alterado neste modo)")
            return
        for p in props:
            p["checked"] = p in ready
        s = org.apply(props)
        self.say(f"   {s['tracks']} faixas na biblioteca, {s['covers']} capas (lote {s['batch']})")
        self.summary["faixas organizadas"] = s["tracks"]

    def step_subtitles(self, mode):
        from movies.subtitle_manager import SubtitleManager, free_name
        from movies.translation import PtBrEngine, translate_subtitle_file
        sm = SubtitleManager(self.db, self.files)
        rows = sm.overview()
        missing = [r for r in rows if "pt-PT" not in r["langs"]]
        self.say(f"   {len(rows)} filmes · {len(missing)} sem legenda pt-PT")
        if mode == "analise":
            return
        conv = adapt = down = 0
        for r in missing:
            if self.cancelled():
                return
            video = Path(r["path"])
            # 1) adaptar pt-BR → pt-PT (sem internet, sem motor)
            br = next((s for s in r["subs"] if s["language"] == "pt-BR"), None)
            if br:
                try:
                    data = translate_subtitle_file(br["path"], "pt-BR", PtBrEngine())
                    self.files.create_file(free_name(video.parent, video.stem, ".pt-PT"), data,
                                           reason="Adaptação pt-BR → pt-PT",
                                           details={"kind": "subtitle_adapt", "source": br["path"]})
                    adapt += 1
                    continue
                except Exception as e:  # noqa: BLE001
                    self.db.log_error("warning", "subtitles", br["path"], str(e))
            # 2) converter formatos não-SRT
            for s in r["subs"]:
                if s["format"] in ("ass", "ssa", "vtt") and not any(
                        x["format"] == "srt" and x["language"] == s["language"] for x in r["subs"]):
                    try:
                        sm.convert_to_srt(r, s["path"])
                        conv += 1
                    except Exception as e:  # noqa: BLE001
                        self.db.log_error("warning", "subtitles", s["path"], str(e))
        # 3) procurar online (limite por execução para respeitar o serviço)
        client = self._opensubs() if mode == "automatico" else None
        if client:
            limit = int(self.db.get_setting("opensubtitles_max_per_run") or 10)
            for r in [x for x in sm.overview() if not x["langs"] & {"pt-PT", "pt-BR"}][:limit]:
                if self.cancelled():
                    break
                try:
                    if sm.download(r, client):
                        down += 1
                except Exception as e:  # noqa: BLE001
                    self.say(f"   OpenSubtitles: {e}")
                    if "Limite" in str(e) or "inválid" in str(e):
                        break
        self.say(f"   {adapt} adaptadas pt-BR→pt-PT, {conv} convertidas para SRT, {down} descarregadas")
        self.summary["legendas novas"] = adapt + conv + down

    def step_translate(self, mode):
        from movies.subtitle_manager import SubtitleManager, free_name
        from movies.translation import ArgosEngine, translate_subtitle_file
        if mode == "analise":
            return
        eng = ArgosEngine()
        if not eng.available():
            self.say("   motor de tradução não instalado — ignorado")
            return
        pairs = {a for a, b in eng.installed_pairs() if b == "pt"}
        sm = SubtitleManager(self.db, self.files)
        limit = int(self.db.get_setting("translate_max_per_run") or 5)
        n = 0
        for r in sm.overview():
            if n >= limit or self.cancelled():
                break
            if r["langs"] & {"pt-PT", "pt-BR", "pt"}:
                continue
            src = next((s for s in r["subs"] if s["language"] in pairs and s["format"] in
                        ("srt", "ass", "ssa", "vtt")), None)
            if not src:
                continue
            video = Path(r["path"])
            self.say(f"   a traduzir {video.name} ({src['language']}→pt-PT)…")
            data = translate_subtitle_file(src["path"], src["language"], eng, cancelled=self.cancelled)
            self.files.create_file(free_name(video.parent, video.stem, ".pt-PT"), data,
                                   reason=f"Tradução local {src['language']}→pt-PT",
                                   details={"kind": "subtitle_translate", "source": src["path"],
                                            "engine": eng.name})
            n += 1
        self.say(f"   {n} legendas traduzidas")
        self.summary["legendas traduzidas"] = n

    def step_metadata(self, mode):
        from movies.metadata import MetadataManager
        rows = self.db.query("SELECT * FROM movies WHERE status='ok' AND (has_nfo=0 OR has_metadata_json=0 "
                             "OR has_cover=0)")
        self.say(f"   {len(rows)} filmes com capa, NFO ou metadata.json em falta")
        if mode == "analise":
            return
        mm = MetadataManager(self.db, self.files, self._tmdb())
        done = 0
        for m in rows:
            if self.cancelled():
                break
            if not Path(m["path"]).exists():
                continue
            r = mm.safe_process(m)
            if "criado" in (r["nfo"], r["json"]) or r["cover"] == "obtida":
                done += 1
        self.say(f"   {done} filmes completados")
        self.summary["metadados"] = done

    def step_duplicates(self, mode):
        from .duplicates import DuplicateFinder
        s = DuplicateFinder(self.db).analyse(cancelled=self.cancelled)
        if s.get("cancelled"):
            return
        gb = s["space_exact"] / 2**30
        self.say(f"   {s['exact']} duplicados exactos ({gb:.2f} GB recuperáveis), "
                 f"{s['probable']} prováveis, {s['versions']} em grupos de versões — nada apagado")
        self.summary["duplicados exactos"] = s["exact"]

    def step_reports(self, mode):
        from .reporting import export_report
        paths = [export_report(self.db, k, "html").name
                 for k in ("filmes", "musica", "erros", "operacoes", "duplicados", "legendas")]
        self.say(f"   relatórios: {', '.join(paths)}")

    def step_jellyfin(self, mode):
        from .jellyfin_check import check_movies
        c = check_movies(self.db)
        self.say(f"   compatibilidade Jellyfin: {c['ok']} filmes OK, {len(c['issues'])} com avisos")
        url, key = self.db.get_setting("jellyfin_url"), self.db.get_setting("jellyfin_api_key")
        if mode != "analise" and self.db.get_setting("jellyfin_enabled") and url and key:
            from integrations.jellyfin import JellyfinClient
            JellyfinClient(url, key).refresh()
            self.say("   pedido de actualização enviado ao Jellyfin")

    # ----------------------------------------------------------- recuperação
    def _recover(self):
        n = self.db.execute("UPDATE jobs SET status='interrupted', finished_at=? WHERE status='running' "
                            "AND job_type NOT LIKE 'automatizacao_%'", (now_iso(),)).rowcount
        self.say(f"   {n} tarefas interrompidas marcadas")
        roots = [self.db.get_setting(k) for k in ("movies_folder", "music_source_folder",
                                                  "music_library_folder")]
        partial = 0
        for root in filter(None, roots):
            if not Path(root).is_dir():
                continue
            for p in Path(root).rglob("*.mo-partial"):
                try:
                    self.files.quarantine(p, "Conflitos", "Cópia parcial de uma operação interrompida")
                    partial += 1
                except Exception as e:  # noqa: BLE001
                    self.say(f"   ! {p.name}: {e}")
        failed = self.db.scalar("SELECT COUNT(*) FROM operations WHERE status='failed'")
        from movies.translation import CHECKPOINT_DIR
        pend = len(list(CHECKPOINT_DIR.glob("*.json"))) if CHECKPOINT_DIR.exists() else 0
        self.say(f"   {partial} cópias parciais para a quarentena · {failed} operações falhadas no "
                 f"histórico · {pend} traduções por retomar (continuam no passo de tradução)")

