"""Histórico: operações (com reversão), erros e tarefas."""
from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox,
                               QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget)

from core.config import LOGS_DIR
from core.reporting import export_report
from core.safety import SafetyError

from .context import AppContext
from .widgets import PageHeader, RowsModel, open_in_file_manager, status_fmt

OP_LABELS = {"quarantine": "Quarentena", "move": "Mover", "rename": "Renomear",
             "revert": "Reposição", "interrupted": "Interrompida"}


def _table(model: RowsModel) -> QTableView:
    v = QTableView()
    v.setModel(model)
    v.setSortingEnabled(True)
    v.setAlternatingRowColors(True)
    v.setSelectionBehavior(QAbstractItemView.SelectRows)
    v.setSelectionMode(QAbstractItemView.SingleSelection)
    v.setShowGrid(False)
    v.verticalHeader().hide()
    v.verticalHeader().setDefaultSectionSize(30)
    v.horizontalHeader().setStretchLastSection(True)
    v.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    return v


class HistoryView(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 20)
        header = PageHeader("Histórico",
                            "Todas as operações ficam registadas com identificador único. "
                            "Quarentena e movimentos podem ser revertidos.")
        b_logs = QPushButton("Abrir pasta de registos")
        b_logs.clicked.connect(lambda: open_in_file_manager(LOGS_DIR / "x"))
        b_rep = QPushButton("Relatório de operações")
        b_rep.clicked.connect(self._report)
        header.actions.addWidget(b_logs)
        header.actions.addWidget(b_rep)
        lay.addWidget(header)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # operações
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 10, 0, 0)
        self.ops_model = RowsModel([
            ("operation_id", "Identificador", None),
            ("operation", "Tipo", lambda v, r: OP_LABELS.get(v, v or "")),
            ("timestamp", "Data", lambda v, r: (v or "").replace("T", " ")),
            ("status", "Estado", status_fmt),
            ("original_path", "Origem", None),
            ("new_path", "Destino", None),
            ("result", "Resultado", lambda v, r: r.get("error") or v or ""),
        ], self)
        self.ops_view = _table(self.ops_model)
        self.ops_view.selectionModel().selectionChanged.connect(self._sel)
        wl.addWidget(self.ops_view, 1)
        row = QHBoxLayout()
        self.b_revert = QPushButton("Reverter operação seleccionada")
        self.b_revert.setObjectName("Primary")
        self.b_revert.setEnabled(False)
        self.b_revert.clicked.connect(self._revert)
        self.b_open = QPushButton("Abrir localização")
        self.b_open.clicked.connect(self._open)
        row.addStretch(1)
        row.addWidget(self.b_open)
        row.addWidget(self.b_revert)
        wl.addLayout(row)
        self.tabs.addTab(w, "Operações")

        # erros
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 10, 0, 0)
        self.err_model = RowsModel([
            ("timestamp", "Data", lambda v, r: (v or "").replace("T", " ")),
            ("level", "Nível", lambda v, r: {"warning": "Aviso", "error": "Erro"}.get(v, v or "")),
            ("module", "Módulo", None),
            ("message", "Mensagem", None),
            ("path", "Ficheiro", None),
            ("resolved", "Resolvido", lambda v, r: "✓" if v else ""),
        ], self)
        self.err_view = _table(self.err_model)
        l2.addWidget(self.err_view, 1)
        r2 = QHBoxLayout()
        b_res = QPushButton("Marcar todos como vistos")
        b_res.clicked.connect(self._resolve_all)
        r2.addStretch(1)
        r2.addWidget(b_res)
        l2.addLayout(r2)
        self.tabs.addTab(w2, "Erros e avisos")

        # tarefas
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        l3.setContentsMargins(0, 10, 0, 0)
        self.jobs_model = RowsModel([
            ("job_type", "Tarefa", lambda v, r: {"inventario_filmes": "Inventário de filmes",
                                                 "inventario_musica": "Inventário de música"}.get(v, v)),
            ("started_at", "Início", lambda v, r: (v or "").replace("T", " ")),
            ("finished_at", "Fim", lambda v, r: (v or "").replace("T", " ")),
            ("status", "Estado", None),
            ("processed", "Processados", None),
            ("message", "Resumo", None),
        ], self)
        l3.addWidget(_table(self.jobs_model), 1)
        self.tabs.addTab(w3, "Tarefas")

        ctx.data_changed.connect(self.refresh)
        self.refresh()

    def show_tab(self, key: str):
        self.tabs.setCurrentIndex({"operations": 0, "errors": 1, "jobs": 2}.get(key, 0))

    def refresh(self):
        db = self.ctx.db
        self.ops_model.set_rows(self.ctx.ops.list(2000))
        self.err_model.set_rows(db.query("SELECT * FROM errors ORDER BY id DESC LIMIT 5000"))
        self.jobs_model.set_rows(db.query("SELECT * FROM jobs ORDER BY id DESC LIMIT 500"))
        self.tabs.setTabText(1, f"Erros e avisos ({db.general_stats()['errors']})")
        self._sel()

    def _current(self) -> dict | None:
        idx = self.ops_view.selectionModel().selectedRows()
        return self.ops_model.row(idx[0].row()) if idx else None

    def _sel(self, *_):
        op = self._current()
        ok, _why = self.ctx.ops.can_revert(op) if op else (False, "")
        self.b_revert.setEnabled(ok)
        self.b_open.setEnabled(op is not None)

    def _open(self):
        op = self._current()
        if op:
            open_in_file_manager(op.get("new_path") or op.get("original_path") or "")

    def _revert(self):
        op = self._current()
        if not op:
            return
        q = QMessageBox.question(
            self, "Reverter operação",
            f"Repor o ficheiro no local original?\n\n{op['new_path']}\n→ {op['original_path']}")
        if q != QMessageBox.Yes:
            return
        try:
            new = self.ctx.files.revert(op["operation_id"])
            QMessageBox.information(self, "Reverter",
                                    f"Reposição concluída ({new['operation_id']}).")
        except (SafetyError, OSError) as e:
            QMessageBox.warning(self, "Reverter", f"Não foi possível reverter:\n{e}")
        self.ctx.data_changed.emit()

    def _resolve_all(self):
        self.ctx.db.execute("UPDATE errors SET resolved=1 WHERE resolved=0")
        self.ctx.data_changed.emit()

    def _report(self):
        p = export_report(self.ctx.db, "operacoes", "html")
        open_in_file_manager(p)
