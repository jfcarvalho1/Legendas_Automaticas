"""Base para páginas que correm tarefas demoradas em fundo, com tabela e progresso."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QTableView, QVBoxLayout, QWidget)

from .context import AppContext, FuncWorker
from .widgets import PageHeader, RowsModel


def make_table(model: RowsModel, multi: bool = True) -> QTableView:
    v = QTableView()
    v.setModel(model)
    v.setSortingEnabled(True)
    v.setAlternatingRowColors(True)
    v.setSelectionBehavior(QAbstractItemView.SelectRows)
    v.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
    v.setShowGrid(False)
    v.verticalHeader().hide()
    v.verticalHeader().setDefaultSectionSize(30)
    v.horizontalHeader().setStretchLastSection(True)
    v.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    return v


class TaskPage(QWidget):
    def __init__(self, ctx: AppContext, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.worker: FuncWorker | None = None
        self.setObjectName("Page")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(32, 28, 32, 20)
        self.lay.setSpacing(12)
        self.header = PageHeader(title, subtitle)
        self.lay.addWidget(self.header)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(lambda: self.worker and self.worker.cancel())
        row.addWidget(self.btn_cancel)
        self.lay.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(10)
        self.progress.hide()
        self.lay.addWidget(self.progress)
        self.task_buttons: list[QPushButton] = []

    def add_action(self, text: str, slot, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        self.header.actions.addWidget(b)
        self.task_buttons.append(b)
        return b

    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def run_task(self, fn, on_done, label: str = "A trabalhar…"):
        """fn(progress, cancelled) corre numa thread; on_done(resultado) na interface."""
        if self.running or self.ctx.busy:
            QMessageBox.information(self, "Ocupado", "Espere que a tarefa em curso termine.")
            return
        self.worker = FuncWorker(fn, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(lambda r: (self._end(), on_done(r)))
        self.worker.failed.connect(self._failed)
        for b in self.task_buttons:
            b.setEnabled(False)
        self.status.setText(label)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.btn_cancel.show()
        self.worker.start()

    def _on_progress(self, cur, total, msg):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(cur)
        if msg:
            self.status.setText(f"{cur}/{total} · {msg}" if total else msg)

    def _end(self):
        self.progress.hide()
        self.btn_cancel.hide()
        for b in self.task_buttons:
            b.setEnabled(True)
        self.ctx.data_changed.emit()

    def _failed(self, msg):
        self._end()
        self.status.setText("")
        QMessageBox.warning(self, "Erro", msg)


class Rows(RowsModel):
    """RowsModel com coluna 0 opcionalmente seleccionável (checkbox)."""

    def __init__(self, columns, parent=None, checkable: bool = False):
        super().__init__(columns, parent)
        self.checkable = checkable

    def flags(self, index):
        f = super().flags(index)
        if self.checkable and index.isValid() and index.column() == 0 and \
                self.rows[index.row()].get("_checkable", True):
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        if self.checkable and index.isValid() and index.column() == 0:
            r = self.rows[index.row()]
            if role == Qt.CheckStateRole and r.get("_checkable", True):
                return Qt.Checked if r.get("checked") else Qt.Unchecked
            if role == Qt.DisplayRole:
                return ""
            return None
        return super().data(index, role)

    def setData(self, index, value, role=Qt.EditRole):  # noqa: N802
        if self.checkable and index.isValid() and index.column() == 0 and role == Qt.CheckStateRole:
            try:
                on = Qt.CheckState(value) == Qt.CheckState.Checked
            except (TypeError, ValueError):
                on = value in (2, Qt.Checked)
            self.rows[index.row()]["checked"] = on
            self.dataChanged.emit(index, index, [role])
            return True
        return False
