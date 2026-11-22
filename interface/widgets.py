"""Componentes reutilizáveis: cabeçalhos, cartões, modelo de tabela, utilitários."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme


def human_size(n: int | float | None) -> str:
    if not n:
        return "0 B"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} TB"


def human_duration(sec: float | None) -> str:
    if not sec:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_int(n: int | None) -> str:
    return f"{n or 0:,}".replace(",", " ")


def open_in_file_manager(path: str | Path) -> None:
    p = Path(path)
    target = p if p.is_dir() else p.parent
    try:
        subprocess.Popen(["xdg-open", str(target)])
    except OSError:
        pass


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            s.setWordWrap(True)
            col.addWidget(s)
        lay.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)


class StatCard(QFrame):
    """Cartão clicável do dashboard."""
    clicked = Signal()

    def __init__(self, label: str, icon: str = "", color: str = theme.ACCENT, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(108)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setObjectName("CardLabel")
        top.addWidget(self._label, 1)
        if icon:
            ic = QLabel(icon)
            ic.setStyleSheet(f"color: {color}; font-size: 15pt;")
            top.addWidget(ic)
        lay.addLayout(top)
        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        self.value.setStyleSheet(f"color: {theme.TEXT};")
        lay.addWidget(self.value)
        self.hint = QLabel("")
        self.hint.setObjectName("CardHint")
        lay.addWidget(self.hint)
        lay.addStretch(1)
        self._color = color

    def set(self, value: str, hint: str = "", alert: bool = False) -> None:
        self.value.setText(value)
        self.hint.setText(hint)
        self.value.setStyleSheet(f"color: {self._color if alert else theme.TEXT};")

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


Column = tuple[str, str, Callable[[Any, dict], str] | None]

STATUS_LABELS = {
    "ok": "OK", "zero_bytes": "0 bytes", "invalid": "Inválido", "missing": "Em falta",
    "quarantined": "Quarentena", "pending": "Por reanalisar",
    "completed": "Concluída", "copied": "Copiada", "failed": "Falhou", "reverted": "Revertida",
}
STATUS_COLORS = {
    "zero_bytes": theme.WARN, "invalid": theme.DANGER, "missing": theme.MUTED,
    "quarantined": theme.ACCENT_2, "failed": theme.DANGER, "reverted": theme.MUTED,
    "completed": theme.OK, "ok": theme.OK, "copied": theme.ACCENT_2,
}


def status_fmt(v, _row) -> str:
    return STATUS_LABELS.get(v, v or "")


class RowsModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def row(self, i: int) -> dict:
        return self.rows[i]

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        key, _h, fmt = self.columns[index.column()]
        v = r.get(key)
        if role == Qt.DisplayRole:
            if fmt:
                return fmt(v, r)
            return "" if v is None else str(v)
        if role == Qt.ToolTipRole:
            return r.get("path") or r.get("original_path") or None
        if role == Qt.ForegroundRole and key == "status" and v in STATUS_COLORS:
            return QColor(STATUS_COLORS[v])
        if role == Qt.TextAlignmentRole and isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        key = self.columns[column][0]
        self.layoutAboutToBeChanged.emit()

        def k(r):
            v = r.get(key)
            return (v is None, v if not isinstance(v, str) else v.lower())
        try:
            self.rows.sort(key=k, reverse=(order == Qt.DescendingOrder))
        except TypeError:
            self.rows.sort(key=lambda r: str(r.get(key) or ""),
                           reverse=(order == Qt.DescendingOrder))
        self.layoutChanged.emit()
