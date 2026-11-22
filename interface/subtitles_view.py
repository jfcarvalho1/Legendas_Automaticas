"""Legendas: estado por filme, procurar online, converter, traduzir para pt-PT."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QSplitter, QTextBrowser, QVBoxLayout)

from movies.subtitle_manager import SubtitleManager, free_name
from movies.subtitles import LANG_NAMES, read_text, validate_srt

from .task_page import Rows, TaskPage, make_table


def _yes(lang):
    return lambda v, r: "✓" if lang in r["langs"] else ""


class SubtitlesView(TaskPage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Legendas",
                         "Prioridade: Português de Portugal → Português do Brasil → outros. "
                         "As legendas originais nunca são alteradas: conversões e traduções "
                         "ficam em ficheiros novos.", parent)
        self.rows: list[dict] = []
        self.add_action("Instalar motor de tradução", self._install)
        self.add_action("Converter para SRT", self._convert)
        self.add_action("Procurar online", self._download)
        self.add_action("Traduzir para pt-PT", self._translate, primary=True)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar filme…")
        self.search.textChanged.connect(lambda _t: self._show())
        self.filter = QComboBox()
        for k, label in (("no_ptpt", "Sem legenda pt-PT"), ("none", "Sem nenhuma legenda"),
                         ("all", "Todos")):
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(lambda _i: self._show())
        bar.addWidget(self.search, 2)
        bar.addWidget(self.filter, 1)
        hint = QLabel("Sem selecção, as acções aplicam-se a todos os filmes da lista.")
        hint.setObjectName("Muted")
        bar.addWidget(hint)
        self.lay.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        self.model = Rows([
            ("title_guess", "Filme", None),
            ("year_guess", "Ano", None),
            ("pt-PT", "pt-PT", _yes("pt-PT")),
            ("pt-BR", "pt-BR", _yes("pt-BR")),
            ("pt", "pt", _yes("pt")),
            ("en", "en", _yes("en")),
            ("others", "Outras", lambda v, r: ", ".join(sorted(l for l in r["langs"]
                                                               if l not in ("pt-PT", "pt-BR", "pt", "en")))),
            ("best", "Melhor disponível", lambda v, r: LANG_NAMES.get(v, v or "nenhuma")),
            ("subs", "Ficheiros", lambda v, r: str(len(v))),
        ], self)
        self.view = make_table(self.model)
        self.view.selectionModel().selectionChanged.connect(self._detail)
        split.addWidget(self.view)
        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 14)
        self.detail = QTextBrowser()
        self.detail.setStyleSheet("border: none; background: transparent;")
        pl.addWidget(self.detail)
        split.addWidget(panel)
        split.setSizes([860, 380])
        self.lay.addWidget(split, 1)
        ctx.data_changed.connect(self._maybe_refresh)
        self._dirty = True

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self._dirty and not self.running:
            self.refresh()

    def _maybe_refresh(self):
        self._dirty = True
        if self.isVisible() and not self.running:
            self.refresh()

    # --------------------------------------------------------------- dados
    def refresh(self):
        self._dirty = False
        self.rows = SubtitleManager(self.ctx.db, self.ctx.files).overview()
        self._show()

    def _show(self):
        k = self.filter.currentData()
        t = self.search.text().strip().lower()
        rows = [r for r in self.rows
                if (k == "all" or (k == "no_ptpt" and "pt-PT" not in r["langs"])
                    or (k == "none" and not r["langs"]))
                and (not t or t in (r["title_guess"] or "").lower() or t in r["filename"].lower())]
        self.model.set_rows(rows)
        total = len(self.rows)
        miss = sum(1 for r in self.rows if "pt-PT" not in r["langs"])
        none = sum(1 for r in self.rows if not r["langs"])
        self.status.setText(f"{total} filmes · {miss} sem pt-PT · {none} sem nenhuma legenda")

    def _targets(self) -> list[dict]:
        idx = self.view.selectionModel().selectedRows()
        return [self.model.row(i.row()) for i in idx] or list(self.model.rows)

    def _detail(self, *_):
        idx = self.view.selectionModel().selectedRows()
        if len(idx) != 1:
            return
        r = self.model.row(idx[0].row())
        e = html.escape
        items = []
        for s in r["subs"]:
            lang = LANG_NAMES.get(s["language"], s["language"] or "idioma desconhecido")
            extra = " (detectado pelo texto)" if s["detected"] else ""
            check = ""
            if s["format"] == "srt":
                try:
                    probs = validate_srt(read_text(s["path"])[0])
                    check = ("<span style='color:#46c37b'>SRT válido</span>" if not probs else
                             f"<span style='color:#e3a33b'>{e(probs[0])}</span>")
                except OSError:
                    pass
            items.append(f"<li><b>{e(s['name'])}</b><br>{e(lang)}{extra} · {s['format'].upper()} {check}</li>")
        emb = r.get("embedded_subtitles") or ""
        self.detail.setHtml(
            f"<h3>{e(r['title_guess'] or r['filename'])} ({e(str(r['year_guess'] or '?'))})</h3>"
            + (f"<ul>{''.join(items)}</ul>" if items else "<p style='color:#8b98a5'>Sem legendas externas.</p>")
            + (f"<p style='color:#8b98a5'>Embutidas no vídeo: {e(emb)}</p>" if emb else ""))

    # ------------------------------------------------------------- acções
    def _convert(self):
        targets = self._targets()

        def job(prog, cancel):
            sm = SubtitleManager(self.ctx.db, self.ctx.files)
            done, errs = 0, []
            for i, r in enumerate(targets, 1):
                if cancel():
                    break
                prog(i, len(targets), r["filename"])
                for s in r["subs"]:
                    if s["format"] in ("ass", "ssa", "vtt", "sub"):
                        try:
                            sm.convert_to_srt(r, s["path"])
                            done += 1
                        except Exception as ex:  # noqa: BLE001
                            errs.append(f"{s['name']}: {ex}")
            return done, errs
        self.run_task(job, lambda res: self._report("Converter", f"{res[0]} legendas convertidas para SRT.",
                                                    res[1]), "A converter…")

    def _download(self):
        g = self.ctx.db.get_setting
        if not (g("opensubtitles_api_key") and g("opensubtitles_username") and g("opensubtitles_password")):
            QMessageBox.information(self, "OpenSubtitles",
                                    "Para procurar legendas online preencha, na Configuração, a chave de "
                                    "API, o utilizador e a palavra-passe do OpenSubtitles (conta gratuita).")
            return
        targets = [r for r in self._targets() if "pt-PT" not in r["langs"]]
        if not targets:
            return
        from integrations.opensubtitles import OpenSubtitlesClient

        def job(prog, cancel):
            client = OpenSubtitlesClient(g("opensubtitles_api_key"), g("opensubtitles_username"),
                                         g("opensubtitles_password"))
            sm = SubtitleManager(self.ctx.db, self.ctx.files)
            found, none, errs = 0, 0, []
            for i, r in enumerate(targets, 1):
                if cancel():
                    break
                prog(i, len(targets), r["filename"])
                try:
                    res = sm.download(r, client)
                    if res:
                        found += 1
                    else:
                        none += 1
                except Exception as ex:  # noqa: BLE001
                    errs.append(f"{r['filename']}: {ex}")
                    if "Limite" in str(ex) or "inválid" in str(ex):
                        break
            return found, none, errs
        self.run_task(job, lambda res: self._report(
            "OpenSubtitles", f"{res[0]} legendas descarregadas · {res[1]} filmes sem resultados.", res[2]),
            "A procurar no OpenSubtitles…")

    def _translate(self):
        from movies.translation import ArgosEngine, PtBrEngine, translate_subtitle_file
        targets = [r for r in self._targets() if "pt-PT" not in r["langs"]]
        if not targets:
            QMessageBox.information(self, "Traduzir", "Todos os filmes da lista já têm legenda pt-PT.")
            return
        argos = ArgosEngine()
        pairs = {a for a, b in argos.installed_pairs() if b == "pt"} if argos.available() else set()

        def pick(r):
            for lang in ("pt-BR", "pt"):
                s = next((x for x in r["subs"] if x["language"] == lang and x["format"] != "sub"), None)
                if s:
                    return s, PtBrEngine()
            for lang in ("en", "es", "fr", "it", "de"):
                s = next((x for x in r["subs"] if x["language"] == lang
                          and x["format"] in ("srt", "ass", "ssa", "vtt")), None)
                if s and lang in pairs:
                    return s, argos
            return None, None

        plan = [(r, *pick(r)) for r in targets]
        doable = [p for p in plan if p[1]]
        if not doable:
            need = "" if pairs else ("\n\nO motor de tradução local ainda não está instalado: use "
                                     "«Instalar motor de tradução».")
            QMessageBox.information(self, "Traduzir", "Nenhum destes filmes tem uma legenda que se "
                                                      "possa traduzir (pt-BR, inglês, …)." + need)
            return

        def job(prog, cancel):
            done, errs = 0, []
            for n, (r, s, eng) in enumerate(doable, 1):
                if cancel():
                    break
                video = Path(r["path"])

                def p(c, t, _m, n=n):
                    prog(n, len(doable), f"{video.name} — bloco {c}/{t}")
                try:
                    data = translate_subtitle_file(s["path"], s["language"], eng, p, cancel)
                    self.ctx.files.create_file(
                        free_name(video.parent, video.stem, ".pt-PT"), data,
                        reason=f"{eng.name}: {s['language']}→pt-PT",
                        details={"kind": "subtitle_translate", "source": s["path"], "engine": eng.name})
                    done += 1
                except Exception as ex:  # noqa: BLE001
                    errs.append(f"{video.name}: {ex}")
            return done, errs
        self.run_task(job, lambda res: self._report(
            "Traduzir", f"{res[0]} legendas pt-PT criadas (ficheiros novos; originais intactos).",
            res[1]), "A traduzir…")

    def _install(self):
        from movies.translation import ArgosEngine, install_argos
        if ArgosEngine().available() and ArgosEngine().installed_pairs():
            QMessageBox.information(self, "Motor de tradução", "O motor de tradução já está instalado.")
            return
        q = QMessageBox.question(self, "Motor de tradução",
                                 "Vai ser instalado o Argos Translate (gratuito, open source, funciona "
                                 "sem internet depois de instalado) e os modelos inglês, espanhol e "
                                 "francês → português.\n\nA descarga é grande (cerca de 1 GB) e pode "
                                 "demorar. Continuar?")
        if q != QMessageBox.Yes:
            return

        def job(prog, cancel):
            install_argos(lambda m: prog(0, 0, m))
            return True
        self.run_task(job, lambda _r: QMessageBox.information(
            self, "Motor de tradução", "Instalado. Já pode traduzir legendas para pt-PT."),
            "A instalar o motor de tradução…")

    def _report(self, title, msg, errs):
        self.refresh()
        if errs:
            msg += "\n\nProblemas:\n" + "\n".join(errs[:12])
        QMessageBox.information(self, title, msg)
