"""Capas, NFO e metadata.json dos filmes."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox

from integrations.tmdb import TMDbClient
from movies.metadata import MetadataManager

from .task_page import Rows, TaskPage, make_table


def _y(v, _r):
    return "✓" if v else "—"


class CoversView(TaskPage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Capas e metadados",
                         "Obtém o poster (cover.jpg) e cria o NFO para o Jellyfin e o "
                         "metadata.json. Capas e ficheiros existentes são preservados.", parent)
        self.results: dict[int, str] = {}
        self.add_action("Processar seleccionados / em falta", self._run, primary=True)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar filme…")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.filter = QComboBox()
        for k, label in (("missing", "Com algo em falta"), ("no_cover", "Sem capa"), ("all", "Todos")):
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cb_cover = QCheckBox("Capa")
        self.cb_nfo = QCheckBox("NFO")
        self.cb_json = QCheckBox("metadata.json")
        for cb in (self.cb_cover, self.cb_nfo, self.cb_json):
            cb.setChecked(True)
        self.cb_replace = QCheckBox("Substituir existentes (os antigos vão para a quarentena)")
        bar.addWidget(self.search, 2)
        bar.addWidget(self.filter, 1)
        bar.addSpacing(12)
        for cb in (self.cb_cover, self.cb_nfo, self.cb_json, self.cb_replace):
            bar.addWidget(cb)
        self.lay.addLayout(bar)
        self.tmdb_hint = QLabel("")
        self.tmdb_hint.setObjectName("Muted")
        self.lay.addWidget(self.tmdb_hint)

        self.model = Rows([
            ("title_guess", "Filme", None),
            ("year_guess", "Ano", None),
            ("has_cover", "Capa", _y),
            ("has_nfo", "NFO", _y),
            ("has_metadata_json", "metadata.json", _y),
            ("extra", "TMDb / IMDb", lambda v, r: " · ".join(
                str(x) for x in (_ex(r).get("tmdb_id"), _ex(r).get("imdb_id")) if x)),
            ("id", "Resultado", lambda v, r: self.results.get(v, "")),
            ("filename", "Ficheiro", None),
        ], self)
        self.view = make_table(self.model)
        self.lay.addWidget(self.view, 1)
        ctx.data_changed.connect(lambda: (not self.running) and self.refresh())
        self.refresh()

    def refresh(self):
        k = self.filter.currentData()
        where = {"missing": "AND (has_cover=0 OR has_nfo=0 OR has_metadata_json=0)",
                 "no_cover": "AND has_cover=0", "all": ""}.get(k, "")
        rows = self.ctx.db.query(f"SELECT * FROM movies WHERE status='ok' {where} "
                                 "ORDER BY title_guess COLLATE NOCASE")
        t = self.search.text().strip().lower()
        if t:
            rows = [r for r in rows if t in (r["title_guess"] or "").lower() or t in r["filename"].lower()]
        self.model.set_rows(rows)
        has_key = bool((self.ctx.db.get_setting("tmdb_api_key") or "").strip())
        self.tmdb_hint.setText(
            f"{len(rows)} filmes. " + ("Fonte: TMDb (capa, sinopse, género, elenco, IMDb)." if has_key else
                                       "Sem chave TMDb: só NFO e metadata.json com os dados locais. Para "
                                       "capas, coloque a chave TMDb (gratuita) na Configuração."))

    def _run(self):
        idx = self.view.selectionModel().selectedRows()
        targets = [self.model.row(i.row()) for i in idx] or list(self.model.rows)
        if not targets:
            return
        if self.cb_replace.isChecked():
            q = QMessageBox.question(self, "Substituir",
                                     f"Substituir capas/NFO/JSON existentes em {len(targets)} filme(s)?\n"
                                     "Os ficheiros antigos vão para a quarentena (reversível).")
            if q != QMessageBox.Yes:
                return
        db = self.ctx.db
        key = (db.get_setting("tmdb_api_key") or "").strip()
        opts = dict(cover=self.cb_cover.isChecked(), nfo=self.cb_nfo.isChecked(),
                    meta=self.cb_json.isChecked(), replace=self.cb_replace.isChecked())

        def job(prog, cancel):
            tmdb = TMDbClient(key, db.get_setting("tmdb_language") or "en-US") if key else None
            mm = MetadataManager(db, self.ctx.files, tmdb)
            out = {}
            for i, m in enumerate(targets, 1):
                if cancel():
                    break
                prog(i, len(targets), m["filename"])
                if not Path(m["path"]).exists():
                    out[m["id"]] = "ficheiro em falta"
                    continue
                r = mm.safe_process(m, **opts)
                out[m["id"]] = f"capa: {r['cover']} · NFO: {r['nfo']} · JSON: {r['json']}" + (
                    f" — {r['note']}" if r.get("note") else "")
            return out

        def done(out):
            self.results.update(out)
            self.refresh()
            n = sum(1 for v in out.values() if "criado" in v or "obtida" in v)
            QMessageBox.information(self, "Capas e metadados",
                                    f"{len(out)} filmes processados, {n} com ficheiros novos.")
        self.run_task(job, done, "A obter capas e metadados…")


def _ex(r: dict) -> dict:
    try:
        return json.loads(r.get("extra") or "{}")
    except json.JSONDecodeError:
        return {}
