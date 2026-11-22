"""Organizar filmes: propostas de nome «Título (Ano)», revisão, aplicação e reversão."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QSplitter, QTableView, QTextBrowser, QVBoxLayout, QWidget)

from core.organizer import CONFLICT, DONE, ERROR, ORGANIZED, READY, UNCERTAIN, MovieOrganizer
from integrations.tmdb import TMDbClient

from .context import AppContext, FuncWorker
from .widgets import PageHeader, RowsModel, status_fmt

CONF_LABEL = {"alta": "Alta", "média": "Média", "baixa": "Baixa", "manual": "Manual"}


class ProposalModel(RowsModel):
    checked_changed = Signal()

    def flags(self, index):
        f = super().flags(index)
        if index.isValid() and index.column() == 0 and self.rows[index.row()]["status"] == READY:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and index.column() == 0:
            r = self.rows[index.row()]
            if role == Qt.CheckStateRole and r["status"] == READY:
                return Qt.Checked if r["checked"] else Qt.Unchecked
            if role == Qt.DisplayRole:
                return ""
            return None
        return super().data(index, role)

    def setData(self, index, value, role=Qt.EditRole):  # noqa: N802
        if index.isValid() and index.column() == 0 and role == Qt.CheckStateRole:
            try:
                checked = Qt.CheckState(value) == Qt.CheckState.Checked
            except (TypeError, ValueError):
                checked = value in (2, Qt.Checked)
            self.rows[index.row()]["checked"] = checked
            self.dataChanged.emit(index, index, [role])
            self.checked_changed.emit()
            return True
        return False


class EditDialog(QDialog):
    def __init__(self, prop: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Corrigir título e ano")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        info = QLabel(f"Ficheiro: <b>{html.escape(prop['filename'])}</b>")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addSpacing(6)
        lay.addWidget(QLabel("Título"))
        self.title = QLineEdit(prop.get("title") or "")
        lay.addWidget(self.title)
        lay.addWidget(QLabel("Ano"))
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setSpecialValueText("—")
        self.year.setValue(int(prop.get("year") or 0))
        lay.addWidget(self.year)
        hint = QLabel("O nome final fica «Título (Ano)». Sem ano o filme não é alterado.")
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> tuple[str, int | None]:
        return self.title.text().strip(), (self.year.value() or None)


class OrganizeView(QWidget):
    FILTERS = [("all", "Todos"), (READY, "Prontos a aplicar"), (UNCERTAIN, "Incertos"),
               (CONFLICT, "Conflitos"), (ORGANIZED, "Já organizados"), (DONE, "Aplicados"),
               (ERROR, "Com erro")]

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.props: list[dict] = []
        self.organizer: MovieOrganizer | None = None
        self.worker: FuncWorker | None = None
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 20)
        lay.setSpacing(12)

        header = PageHeader(
            "Organizar filmes",
            "Propõe o nome «Título (Ano)» e a pasta de cada filme, levando legendas, capas e NFO. "
            "Nada é alterado até carregar em Aplicar, e cada lote pode ser revertido.")
        self.b_revert = QPushButton("Reverter último lote")
        self.b_revert.clicked.connect(self._revert_last)
        self.b_propose = QPushButton("Analisar e propor")
        self.b_propose.clicked.connect(self._propose)
        self.b_apply = QPushButton("Aplicar seleccionados")
        self.b_apply.setObjectName("Primary")
        self.b_apply.setEnabled(False)
        self.b_apply.clicked.connect(self._apply)
        header.actions.addWidget(self.b_revert)
        header.actions.addWidget(self.b_propose)
        header.actions.addWidget(self.b_apply)
        lay.addWidget(header)

        opts = QHBoxLayout()
        self.cb_the = QCheckBox("Remover «The» do início (The Matrix → Matrix (1999))")
        self.cb_the.toggled.connect(lambda v: self.ctx.db.set_setting("strip_leading_the", v))
        self.cb_clean = QCheckBox("Na pasta final deixar só os ficheiros do filme "
                                  "(o resto vai para a quarentena)")
        self.cb_clean.toggled.connect(lambda v: self.ctx.db.set_setting("clean_leftovers", v))
        self.cb_tmdb = QCheckBox("Confirmar título e ano no TMDb")
        self.tmdb_hint = QLabel("")
        self.tmdb_hint.setObjectName("Muted")
        opts.addWidget(self.cb_the)
        opts.addSpacing(18)
        opts.addWidget(self.cb_clean)
        opts.addStretch(1)
        lay.addLayout(opts)
        opts2 = QHBoxLayout()
        opts2.addWidget(self.cb_tmdb)
        opts2.addWidget(self.tmdb_hint)
        opts2.addStretch(1)
        lay.addLayout(opts2)

        bar = QHBoxLayout()
        self.summary = QLabel("Carregue em «Analisar e propor». Primeiro faça a análise "
                              "(inventário) na página Filmes, se ainda não fez.")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.filter = QComboBox()
        for k, label in self.FILTERS:
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(lambda _i: self._show())
        b_all = QPushButton("Seleccionar prontos")
        b_all.clicked.connect(lambda: self._check_all(True))
        b_none = QPushButton("Limpar selecção")
        b_none.clicked.connect(lambda: self._check_all(False))
        self.b_edit = QPushButton("Corrigir título/ano…")
        self.b_edit.setEnabled(False)
        self.b_edit.clicked.connect(self._edit_current)
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.filter)
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addWidget(self.b_edit)
        lay.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(10)
        self.progress.hide()
        lay.addWidget(self.progress)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)
        self.model = ProposalModel([
            ("checked", "", None),
            ("status", "Estado", status_fmt),
            ("confidence", "Confiança", lambda v, r: CONF_LABEL.get(v, v or "")),
            ("filename", "Ficheiro actual", None),
            ("target", "Novo nome", lambda v, r: self._rel(v) if v else "—"),
            ("files", "Ficheiros", lambda v, r: (str(len(v)) + (f" +{len(r['leftovers'])} extra"
                                                 if r.get("leftovers") else "")) if v else ""),
            ("source", "Fonte", None),
            ("note", "Observações", None),
        ], self)
        self.model.checked_changed.connect(self._update_counts)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setShowGrid(False)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(30)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.setColumnWidth(0, 34)
        self.view.doubleClicked.connect(lambda _i: self._edit_current())
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
        split.setSizes([900, 360])
        lay.addWidget(split, 1)

        ctx.data_changed.connect(self._load_options)
        self._load_options()

    # ----------------------------------------------------------------- util
    def _rel(self, p: str) -> str:
        root = self.ctx.db.get_setting("movies_folder") or ""
        try:
            return str(Path(p).relative_to(root))
        except ValueError:
            return p

    def _load_options(self):
        db = self.ctx.db
        self.cb_the.blockSignals(True)
        self.cb_the.setChecked(bool(db.get_setting("strip_leading_the")))
        self.cb_the.blockSignals(False)
        self.cb_clean.blockSignals(True)
        self.cb_clean.setChecked(bool(db.get_setting("clean_leftovers")))
        self.cb_clean.blockSignals(False)
        has_key = bool((db.get_setting("tmdb_api_key") or "").strip())
        self.cb_tmdb.setEnabled(has_key)
        if not has_key:
            self.cb_tmdb.setChecked(False)
        elif not self.props:
            self.cb_tmdb.setChecked(True)
        self.tmdb_hint.setText("" if has_key else "(opcional: coloque a chave TMDb na Configuração)")
        self.b_revert.setEnabled(bool(db.get_setting("last_rename_batch")))

    def _busy(self, on: bool):
        self.b_propose.setEnabled(not on)
        self.b_revert.setEnabled(not on and bool(self.ctx.db.get_setting("last_rename_batch")))
        self.b_apply.setEnabled(not on and any(p["checked"] for p in self.props))
        self.progress.setVisible(on)
        if on:
            self.progress.setRange(0, 0)

    def _on_progress(self, cur, total, _msg):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(cur)

    def _show(self):
        key = self.filter.currentData()
        rows = self.props if key == "all" else [p for p in self.props if p["status"] == key]
        self.model.set_rows(rows)
        self._update_counts()

    def _update_counts(self):
        c = {}
        for p in self.props:
            c[p["status"]] = c.get(p["status"], 0) + 1
        sel = sum(1 for p in self.props if p["checked"])
        if self.props:
            self.summary.setText(
                f"{len(self.props)} filmes · {c.get(READY, 0)} prontos · {c.get(UNCERTAIN, 0)} incertos · "
                f"{c.get(CONFLICT, 0)} conflitos · {c.get(ORGANIZED, 0)} já organizados"
                + (f" · {c.get(DONE, 0)} aplicados" if c.get(DONE) else ""))
        self.b_apply.setText(f"Aplicar seleccionados ({sel})")
        self.b_apply.setEnabled(sel > 0 and not (self.worker and self.worker.isRunning()))

    def _current(self) -> tuple[int, dict] | None:
        idx = self.view.selectionModel().selectedRows()
        if not idx:
            return None
        row = self.model.row(idx[0].row())
        for i, p in enumerate(self.props):
            if p is row:
                return i, p
        return None

    def _detail(self, *_):
        cur = self._current()
        self.b_edit.setEnabled(bool(cur) and cur[1]["status"] in (READY, UNCERTAIN, CONFLICT))
        if not cur:
            return
        p = cur[1]
        e = html.escape
        files = "".join(
            f"<tr><td style='color:#8b98a5;padding:2px 8px 2px 0'>{e(f['kind'])}</td>"
            f"<td>{e(Path(f['src']).name)}<br><span style='color:#3fb6a8'>→ {e(self._rel(f['dst']))}"
            f"</span></td></tr>" for f in p["files"])
        self.detail.setHtml(
            f"<h3 style='margin-bottom:2px'>{e(p.get('title') or '?')} ({e(str(p.get('year') or '?'))})</h3>"
            f"<div style='color:#8b98a5'>{e(status_fmt(p['status'], p))} · confiança "
            f"{e(CONF_LABEL.get(p['confidence'], p['confidence'] or ''))} · fonte: {e(p['source'])}</div>"
            + (f"<p style='color:#e3a33b'>{e(p['note'])}</p>" if p.get("note") else "")
            + (f"<table style='margin-top:8px'>{files}</table>" if files else "")
            + (("<p style='color:#8b98a5;margin-top:8px'><b>Vai para a quarentena</b> (não faz "
                "parte do filme):<br>" + "<br>".join(e(self._rel(x)) for x in p["leftovers"]) + "</p>")
               if p.get("leftovers") else "")
            + "<p style='color:#8b98a5;font-size:9pt'>Duplo clique para corrigir o título ou o ano.</p>")

    def _check_all(self, on: bool):
        for p in self.props:
            if p["status"] == READY:
                p["checked"] = on
        self._show()

    # -------------------------------------------------------------- acções
    def _propose(self):
        if self.ctx.busy:
            QMessageBox.information(self, "Organizar", "Espere que a análise em curso termine.")
            return
        db = self.ctx.db
        if not db.scalar("SELECT COUNT(*) FROM movies WHERE status='ok'"):
            QMessageBox.information(self, "Organizar",
                                    "O inventário de filmes está vazio.\n"
                                    "Vá a Filmes e carregue em «Analisar agora» primeiro.")
            return
        tmdb = None
        if self.cb_tmdb.isChecked():
            tmdb = TMDbClient(db.get_setting("tmdb_api_key"), db.get_setting("tmdb_language") or "en-US")
        self.organizer = MovieOrganizer(db, self.ctx.files, tmdb)
        self.worker = FuncWorker(lambda prog, cancel: self.organizer.propose(prog, cancel), self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._proposed)
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _proposed(self, props):
        self._busy(False)
        self.props = props
        self._show()
        if not props:
            QMessageBox.information(self, "Organizar", "Não há filmes para organizar nesta pasta.")

    def _failed(self, msg):
        self._busy(False)
        QMessageBox.warning(self, "Organizar", msg)

    def _edit_current(self):
        cur = self._current()
        if not cur or not self.organizer or cur[1]["status"] not in (READY, UNCERTAIN, CONFLICT):
            return
        i, p = cur
        dlg = EditDialog(p, self)
        if dlg.exec() != QDialog.Accepted:
            return
        title, year = dlg.values()
        if not title or not year:
            QMessageBox.information(self, "Corrigir", "Indique o título e o ano.")
            return
        self.organizer.edit(self.props, i, title, year)
        self._show()

    def _apply(self):
        todo = [p for p in self.props if p["checked"] and p["status"] == READY]
        if not todo:
            return
        nfiles = sum(sum(1 for f in p["files"] if f["src"] != f["dst"]) for p in todo)
        nleft = sum(len(p.get("leftovers") or []) for p in todo)
        q = QMessageBox.question(
            self, "Aplicar",
            f"Vai organizar {len(todo)} filme(s): {nfiles} ficheiro(s) renomeados/movidos"
            + (f" e {nleft} ficheiro(s) extra enviados para a quarentena" if nleft else "") + ".\n\n"
            "Nada é apagado. Cada movimento fica registado e o lote inteiro pode ser "
            "revertido com «Reverter último lote».\n\nContinuar?")
        if q != QMessageBox.Yes:
            return
        self.worker = FuncWorker(lambda prog, cancel: self.organizer.apply(self.props, prog), self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._applied)
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _applied(self, s: dict):
        self._busy(False)
        self._show()
        self.ctx.data_changed.emit()
        msg = (f"{s['movies']} filme(s) organizados, {s['files']} ficheiro(s) movidos.\n"
               f"Lote: {s['batch']}")
        if s.get("leftovers"):
            msg += f"\n{s['leftovers']} ficheiro(s) extra enviados para a quarentena (reversível)."
        if s["empty_folders"]:
            msg += f"\n{s['empty_folders']} pasta(s) antigas ficaram vazias e foram removidas."
        if s["errors"]:
            msg += "\n\nProblemas:\n" + "\n".join(s["errors"][:12])
        QMessageBox.information(self, "Organização concluída", msg)

    def _revert_last(self):
        batch = self.ctx.db.get_setting("last_rename_batch")
        if not batch:
            return
        q = QMessageBox.question(self, "Reverter",
                                 f"Repor todos os ficheiros do lote {batch} nos nomes e "
                                 "pastas originais?")
        if q != QMessageBox.Yes:
            return
        done, errors = self.ctx.files.revert_batch(batch)
        self.ctx.db.set_setting("last_rename_batch", "")
        self.props = []
        self._show()
        self.ctx.data_changed.emit()
        msg = f"{done} ficheiro(s) repostos."
        if errors:
            msg += "\n\nNão foi possível:\n" + "\n".join(errors[:12])
        QMessageBox.information(self, "Reverter", msg)
