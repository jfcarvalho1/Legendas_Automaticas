"""Janela principal com menu lateral."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from core.config import APP_NAME, APP_VERSION, ASSETS_DIR

from .context import AppContext
from .dashboard import DashboardView
from .history_view import HistoryView
from .movies_view import MoviesView
from .music_view import MusicView
from .organize_view import OrganizeView
from .placeholder_view import PlaceholderView
from .settings_view import FolderField, SettingsView

NAV = [
    ("dashboard", "◈   Dashboard"),
    ("movies", "▶   Filmes"),
    ("music", "♫   Música"),
    ("subtitles", "✎   Legendas"),
    ("covers", "▢   Capas"),
    ("analysis", "⌕   Organizar"),
    ("duplicates", "⧉   Duplicados"),
    ("automation", "⟳   Automatização"),
    ("history", "☰   Histórico"),
    ("settings", "⚙   Configuração"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        icon = ASSETS_DIR / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1360, 860)
        self.setMinimumSize(1050, 680)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 6, 0, 6)
        sl.setSpacing(2)
        brand = QLabel("Media Organizer")
        brand.setObjectName("Brand")
        sub = QLabel("Filmes · Música · Jellyfin")
        sub.setObjectName("BrandSub")
        sl.addWidget(brand)
        sl.addWidget(sub)

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "dashboard": DashboardView(ctx),
            "movies": MoviesView(ctx),
            "music": MusicView(ctx),
            "subtitles": PlaceholderView(ctx, "subtitles"),
            "covers": PlaceholderView(ctx, "covers"),
            "analysis": OrganizeView(ctx),
            "duplicates": PlaceholderView(ctx, "duplicates"),
            "automation": PlaceholderView(ctx, "automation"),
            "history": HistoryView(ctx),
            "settings": SettingsView(ctx),
        }
        self.buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, label in NAV:
            b = QPushButton(label)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(b)
            self.buttons[key] = b
            sl.addWidget(b)
            self.stack.addWidget(self.pages[key])
        sl.addStretch(1)
        footer = QLabel(f"Versão {APP_VERSION}\nOriginais sempre preservados")
        footer.setObjectName("SidebarFooter")
        sl.addWidget(footer)

        root.addWidget(side)
        root.addWidget(self.stack, 1)

        self.statusBar().showMessage("Pronto.")
        ctx.navigate.connect(self.navigate)
        ctx.scan_started.connect(lambda k: self.statusBar().showMessage(
            "Análise de filmes em curso…" if k == "movies" else "Análise de música em curso…"))
        ctx.scan_progress.connect(lambda c, t, m: self.statusBar().showMessage(
            f"A analisar {c}/{t}: {m}" if t else m))
        ctx.scan_finished.connect(lambda *_: self.statusBar().showMessage("Análise concluída.", 8000))
        ctx.scan_failed.connect(lambda _k, m: self.statusBar().showMessage(f"Falhou: {m}", 10000))
        self.show_page("dashboard")

    def show_page(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.buttons[key].setChecked(True)

    def navigate(self, page: str, flt: str):
        if page not in self.pages:
            return
        p = self.pages[page]
        if flt and hasattr(p, "set_filter"):
            p.set_filter(flt)
        if flt and hasattr(p, "show_tab"):
            p.show_tab(flt)
        self.show_page(page)

    def closeEvent(self, e):  # noqa: N802
        if self.ctx.busy:
            self.ctx.cancel_scan()
            self.ctx.worker.wait(5000)
        super().closeEvent(e)


class FirstRunDialog(QDialog):
    """Assistente de configuração inicial."""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Bem-vindo ao Media Organizer")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(10)
        t = QLabel("Bem-vindo")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        s = QLabel("Indique onde estão os seus filmes e a sua música. A aplicação começa por "
                   "fazer apenas um inventário: lê os ficheiros, não altera nada.")
        s.setObjectName("PageSubtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addSpacing(6)
        lay.addWidget(QLabel("Pasta de filmes"))
        self.movies = FolderField()
        self.movies.setText(ctx.db.get_setting("movies_folder"))
        lay.addWidget(self.movies)
        lay.addWidget(QLabel("Pasta de música (origem)"))
        self.music = FolderField()
        self.music.setText(ctx.db.get_setting("music_source_folder"))
        lay.addWidget(self.music)
        note = QLabel("Segurança: preservar originais ✓ · eliminação automática ✕ · "
                      "quarentena ✓ · registos ✓")
        note.setObjectName("Muted")
        lay.addSpacing(6)
        lay.addWidget(note)
        bb = QDialogButtonBox()
        ok = bb.addButton("Começar", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        bb.addButton("Mais tarde", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addSpacing(8)
        lay.addWidget(bb)

    def accept(self):
        self.ctx.db.set_setting("movies_folder", self.movies.text())
        self.ctx.db.set_setting("music_source_folder", self.music.text())
        self.ctx.db.set_setting("first_run_done", True)
        super().accept()
