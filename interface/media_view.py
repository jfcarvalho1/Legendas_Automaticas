"""Vista genérica de inventário (usada por Filmes e Música)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSplitter,
                               QTableView, QTextBrowser, QVBoxLayout, QWidget)

from core.config import QUARANTINE_CATEGORIES
from core.reporting import FORMATS, export_report
from core.safety import SafetyError

from .context import AppContext
from .widgets import Column, PageHeader, RowsModel, fmt_int, open_in_file_manager


class MediaView(QWidget):
    table: str = ""
    kind: str = ""                 # 'movies' | 'music'
    report_kind: str = ""
    title: str = ""
    subtitle: str = ""
    columns: list[Column] = []
    filters: list[tuple[str, str, str]] = []   # (chave, rótulo, WHERE)
    search_cols: tuple[str, ...] = ()
    order_by: str = "id"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 20)
        lay.setSpacing(12)

        header = PageHeader(self.title, self.subtitle)
        self.btn_report = QPushButton("Exportar relatório")
        menu = QMenu(self)
        for fmt in FORMATS:
            act = QAction(fmt.upper(), self)
            act.triggered.connect(lambda _=False, f=fmt: self._export(f))
            menu.addAction(act)
        self.btn_report.setMenu(menu)
        self.btn_scan = QPushButton("Analisar agora")
        self.btn_scan.setObjectName("Primary")
        self.btn_scan.clicked.connect(self._scan)
        header.actions.addWidget(self.btn_report)
        header.actions.addWidget(self.btn_scan)
        lay.addWidget(header)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar…")
        self.search.setClearButtonEnabled(True)
        self.filter = QComboBox()
        for key, label, _w in self.filters:
            self.filter.addItem(label, key)
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        bar.addWidget(self.search, 3)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.count)
        lay.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)
        self.model = RowsModel(self.columns, self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setShowGrid(False)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(30)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.doubleClicked.connect(lambda idx: open_in_file_manager(self.model.row(idx.row())["path"]))
        self.view.selectionModel().selectionChanged.connect(self._show_detail)
        split.addWidget(self.view)

        self.detail_frame = QFrame()
        self.detail_frame.setObjectName("Panel")
        dl = QVBoxLayout(self.detail_frame)
        dl.setContentsMargins(16, 14, 16, 14)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        self.detail.setStyleSheet("border: none; background: transparent;")
        dl.addWidget(self.detail)
        split.addWidget(self.detail_frame)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 320])
        lay.addWidget(split, 1)

        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh())
        ctx.data_changed.connect(self.refresh)
        ctx.scan_started.connect(lambda _k: self.btn_scan.setEnabled(False))
        ctx.scan_finished.connect(lambda *_: self.btn_scan.setEnabled(True))
        ctx.scan_failed.connect(lambda *_: self.btn_scan.setEnabled(True))
        self._sized = False
        self.refresh()

    # ---------------------------------------------------------------------
    def set_filter(self, key: str) -> None:
        i = self.filter.findData(key)
        if i >= 0:
            self.filter.setCurrentIndex(i)

    def refresh(self):
        where, params = [], []
        key = self.filter.currentData()
        for k, _l, w in self.filters:
            if k == key and w:
                where.append(w)
        text = self.search.text().strip()
        if text:
            where.append("(" + " OR ".join(f"{c} LIKE ?" for c in self.search_cols) + ")")
            params += [f"%{text}%"] * len(self.search_cols)
        sql = f"SELECT * FROM {self.table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {self.order_by} LIMIT 20000"
        rows = self.ctx.db.query(sql, params)
        self.model.set_rows(rows)
        self.count.setText(f"{fmt_int(len(rows))} itens")
        if rows and not self._sized:
            self.view.resizeColumnsToContents()
            for c in range(self.model.columnCount()):
                if self.view.columnWidth(c) > 340:
                    self.view.setColumnWidth(c, 340)
            self._sized = True
        if not rows:
            self.detail.setHtml(self.empty_html())

    def empty_html(self) -> str:
        return ("<p style='color:#8b98a5'>Sem itens para mostrar.<br><br>"
                "Use <b>Analisar agora</b> para criar o inventário. "
                "A análise só lê os ficheiros — nada é alterado.</p>")

    def selected_rows(self) -> list[dict]:
        idx = self.view.selectionModel().selectedRows()
        return [self.model.row(i.row()) for i in idx]

    def _show_detail(self, *_):
        rows = self.selected_rows()
        if not rows:
            return
        if len(rows) > 1:
            self.detail.setHtml(f"<h3>{len(rows)} itens seleccionados</h3>")
            return
        self.detail.setHtml(self.detail_html(rows[0]))

    def detail_html(self, r: dict) -> str:  # sobreposto nas subclasses
        return ""

    def _scan(self):
        err = self.ctx.start_scan(self.kind)
        if err:
            QMessageBox.information(self, "Análise", err)

    def _export(self, fmt: str):
        try:
            p = export_report(self.ctx.db, self.report_kind, fmt)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Relatório", str(e))
            return
        QMessageBox.information(self, "Relatório", f"Relatório criado em:\n{p}")
        open_in_file_manager(p)

    def _menu(self, pos):
        rows = self.selected_rows()
        if not rows:
            return
        m = QMenu(self)
        a_open = m.addAction("Abrir pasta")
        sub = m.addMenu("Enviar para quarentena")
        acts = {sub.addAction(c.replace("_", " ")): c for c in QUARANTINE_CATEGORIES}
        chosen = m.exec(self.view.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == a_open:
            open_in_file_manager(rows[0]["path"])
        elif chosen in acts:
            self._quarantine(rows, acts[chosen])

    def _quarantine(self, rows: list[dict], category: str):
        rows = [r for r in rows if r.get("status") not in ("missing", "quarantined")]
        if not rows:
            return
        names = "\n".join(Path(r["path"]).name for r in rows[:8])
        more = f"\n… e mais {len(rows) - 8}" if len(rows) > 8 else ""
        ok = QMessageBox.question(
            self, "Enviar para quarentena",
            f"Mover {len(rows)} ficheiro(s) para Quarentena/{category}?\n\n{names}{more}\n\n"
            "Nada é apagado. Cada operação fica registada e pode ser revertida no Histórico.")
        if ok != QMessageBox.Yes:
            return
        done, errors = 0, []
        for r in rows:
            try:
                self.ctx.files.quarantine(r["path"], category, f"Enviado manualmente ({category})")
                done += 1
            except (SafetyError, OSError) as e:
                errors.append(f"{Path(r['path']).name}: {e}")
        self.ctx.data_changed.emit()
        msg = f"{done} ficheiro(s) enviados para quarentena."
        if errors:
            msg += "\n\nNão foi possível:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Quarentena", msg)
