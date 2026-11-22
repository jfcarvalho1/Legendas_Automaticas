"""Configuração: pastas, segurança, Jellyfin e diagnóstico."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.diagnostics import run_diagnostics

from . import theme
from .context import AppContext
from .widgets import PageHeader


def panel(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Panel")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 16, 20, 18)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setObjectName("SectionTitle")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return f, lay


class FolderField(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        b = QPushButton("Escolher…")
        b.clicked.connect(self._pick)
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta", self.edit.text() or "")
        if d:
            self.edit.setText(d)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, t: str):  # noqa: N802
        self.edit.setText(t or "")


class SettingsView(QWidget):
    FOLDERS = [
        ("movies_folder", "Pasta de filmes"),
        ("music_source_folder", "Música — pasta de origem"),
        ("music_library_folder", "Música — biblioteca organizada (destino)"),
        ("quarantine_folder", "Pasta de quarentena"),
    ]
    TOGGLES = [
        ("preserve_originals", "Preservar originais", True),
        ("auto_delete", "Eliminação automática (sempre desactivada)", True),
        ("quarantine_enabled", "Quarentena activada", False),
        ("logging_enabled", "Registos activados", True),
        ("incremental", "Reprocessamento incremental (não reanalisar ficheiros sem alterações)", False),
        ("clean_leftovers", "Ao organizar, deixar na pasta do filme só os ficheiros indicados "
                            "(o resto vai para a quarentena)", False),
        ("allow_cross_device_move", "Entre discos diferentes: remover o original depois de "
                                    "copiar e validar por SHA256", False),
        ("backups_enabled", "Backups da base de dados (configurável)", False),
    ]

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)

        header = PageHeader("Configuração", "Pastas, regras de segurança, Jellyfin e diagnóstico.")
        b_save = QPushButton("Guardar")
        b_save.setObjectName("Primary")
        b_save.clicked.connect(self.save)
        header.actions.addWidget(b_save)
        lay.addWidget(header)

        f, fl = panel("Pastas", "A análise só lê estas pastas. Nada é movido sem a sua ordem.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.folder_fields: dict[str, FolderField] = {}
        for i, (key, label) in enumerate(self.FOLDERS):
            grid.addWidget(QLabel(label), i, 0)
            ff = FolderField()
            self.folder_fields[key] = ff
            grid.addWidget(ff, i, 1)
        grid.setColumnStretch(1, 1)
        fl.addLayout(grid)
        lay.addWidget(f)

        f, fl = panel("Segurança", "As regras a cinzento estão bloqueadas por definição: "
                                   "a aplicação nunca apaga ficheiros.")
        self.toggles: dict[str, QCheckBox] = {}
        for key, label, locked in self.TOGGLES:
            cb = QCheckBox(label)
            cb.setEnabled(not locked)
            self.toggles[key] = cb
            fl.addWidget(cb)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tempo máximo do FFprobe por ficheiro (segundos)"))
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 600)
        row.addWidget(self.timeout)
        row.addStretch(1)
        fl.addLayout(row)
        lay.addWidget(f)

        f, fl = panel("Jellyfin (opcional)", "Convenções de nomes, posters e NFO. O endereço do "
                                             "servidor configura-se na página Automatização.")
        self.jf_enabled = QCheckBox("Usar convenções Jellyfin")
        fl.addWidget(self.jf_enabled)
        row = QHBoxLayout()
        row.addWidget(QLabel("Nome do ficheiro de capa"))
        self.jf_cover = QLineEdit()
        self.jf_cover.setMaximumWidth(220)
        row.addWidget(self.jf_cover)
        row.addStretch(1)
        fl.addLayout(row)
        lay.addWidget(f)

        f, fl = panel("TMDb (opcional)",
                      "Confirma título e ano dos filmes na base de dados The Movie Database. "
                      "É gratuito: crie conta em themoviedb.org → Definições → API e cole aqui a "
                      "«API Key» ou o «API Read Access Token». Sem chave, a identificação usa só "
                      "o nome do ficheiro.")
        row = QHBoxLayout()
        row.addWidget(QLabel("Chave"))
        self.tmdb_key = QLineEdit()
        self.tmdb_key.setEchoMode(QLineEdit.Password)
        self.tmdb_key.setPlaceholderText("cole aqui a chave")
        row.addWidget(self.tmdb_key, 1)
        row.addWidget(QLabel("Idioma dos títulos"))
        self.tmdb_lang = QLineEdit()
        self.tmdb_lang.setMaximumWidth(90)
        row.addWidget(self.tmdb_lang)
        b_test = QPushButton("Testar")
        b_test.clicked.connect(self._test_tmdb)
        row.addWidget(b_test)
        fl.addLayout(row)
        lay.addWidget(f)

        f, fl = panel("OpenSubtitles (opcional)",
                      "Para procurar legendas online: conta gratuita em opensubtitles.com e chave de API em "
                      "opensubtitles.com/consumers. As contas gratuitas têm limite diário de descargas.")
        grid2 = QGridLayout()
        self.os_key, self.os_user, self.os_pass = QLineEdit(), QLineEdit(), QLineEdit()
        self.os_key.setEchoMode(QLineEdit.Password)
        self.os_pass.setEchoMode(QLineEdit.Password)
        for i, (label, w) in enumerate((("Chave de API", self.os_key), ("Utilizador", self.os_user),
                                        ("Palavra-passe", self.os_pass))):
            grid2.addWidget(QLabel(label), i, 0)
            grid2.addWidget(w, i, 1)
        self.os_max = QSpinBox()
        self.os_max.setRange(1, 200)
        grid2.addWidget(QLabel("Máximo de descargas por execução automática"), 3, 0)
        grid2.addWidget(self.os_max, 3, 1)
        self.tr_max = QSpinBox()
        self.tr_max.setRange(1, 500)
        grid2.addWidget(QLabel("Máximo de traduções por execução automática"), 4, 0)
        grid2.addWidget(self.tr_max, 4, 1)
        grid2.setColumnStretch(1, 1)
        fl.addLayout(grid2)
        lay.addWidget(f)

        f, fl = panel("Música", "Copiar mantém sempre o original na pasta de origem (recomendado).")
        row = QHBoxLayout()
        row.addWidget(QLabel("Ao organizar"))
        self.music_mode = QComboBox()
        self.music_mode.addItem("Copiar para a biblioteca (original intacto)", "copy")
        self.music_mode.addItem("Mover para a biblioteca", "move")
        row.addWidget(self.music_mode)
        row.addStretch(1)
        fl.addLayout(row)
        lay.addWidget(f)

        f, fl = panel("Diagnóstico", "Ferramentas detectadas no sistema. "
                                     "A aplicação não instala nada por iniciativa própria.")
        self.diag = QTableWidget(0, 4)
        self.diag.setHorizontalHeaderLabels(["Ferramenta", "Estado", "Versão", "Para que serve"])
        self.diag.verticalHeader().hide()
        self.diag.setShowGrid(False)
        self.diag.setEditTriggers(QTableWidget.NoEditTriggers)
        self.diag.horizontalHeader().setStretchLastSection(True)
        self.diag.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.diag.setMinimumHeight(330)
        fl.addWidget(self.diag)
        b = QPushButton("Verificar novamente")
        b.clicked.connect(self.run_diag)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(b)
        fl.addLayout(r)
        lay.addWidget(f)
        lay.addStretch(1)

        self.load()
        self.run_diag()

    def load(self):
        s = self.ctx.db.all_settings()
        for k, ff in self.folder_fields.items():
            ff.setText(s.get(k) or "")
        for k, cb in self.toggles.items():
            cb.setChecked(bool(s.get(k)))
        self.timeout.setValue(int(s.get("ffprobe_timeout") or 30))
        self.jf_enabled.setChecked(bool(s.get("jellyfin_enabled")))
        self.jf_cover.setText(s.get("jellyfin_cover_name") or "cover.jpg")
        self.tmdb_key.setText(s.get("tmdb_api_key") or "")
        self.tmdb_lang.setText(s.get("tmdb_language") or "en-US")
        self.os_key.setText(s.get("opensubtitles_api_key") or "")
        self.os_user.setText(s.get("opensubtitles_username") or "")
        self.os_pass.setText(s.get("opensubtitles_password") or "")
        self.os_max.setValue(int(s.get("opensubtitles_max_per_run") or 10))
        self.tr_max.setValue(int(s.get("translate_max_per_run") or 5))
        self.music_mode.setCurrentIndex(max(0, self.music_mode.findData(s.get("music_mode") or "copy")))

    def save(self):
        db = self.ctx.db
        for k, ff in self.folder_fields.items():
            db.set_setting(k, ff.text())
        for k, cb in self.toggles.items():
            db.set_setting(k, cb.isChecked())
        db.set_setting("ffprobe_timeout", self.timeout.value())
        db.set_setting("jellyfin_enabled", self.jf_enabled.isChecked())
        db.set_setting("jellyfin_cover_name", self.jf_cover.text().strip() or "cover.jpg")
        db.set_setting("tmdb_api_key", self.tmdb_key.text().strip())
        db.set_setting("tmdb_language", self.tmdb_lang.text().strip() or "en-US")
        db.set_setting("opensubtitles_api_key", self.os_key.text().strip())
        db.set_setting("opensubtitles_username", self.os_user.text().strip())
        db.set_setting("opensubtitles_password", self.os_pass.text())
        db.set_setting("opensubtitles_max_per_run", self.os_max.value())
        db.set_setting("translate_max_per_run", self.tr_max.value())
        db.set_setting("music_mode", self.music_mode.currentData())
        self.load()
        self.ctx.data_changed.emit()
        QMessageBox.information(self, "Configuração", "Configuração guardada.")

    def _test_tmdb(self):
        from integrations.tmdb import TMDbClient, TMDbError
        key = self.tmdb_key.text().strip()
        if not key:
            QMessageBox.information(self, "TMDb", "Cole primeiro a chave.")
            return
        try:
            TMDbClient(key).test()
            QMessageBox.information(self, "TMDb", "Chave válida. Não se esqueça de carregar em Guardar.")
        except TMDbError as e:
            QMessageBox.warning(self, "TMDb", str(e))

    def run_diag(self):
        res = run_diagnostics()
        self.diag.setRowCount(len(res))
        for i, t in enumerate(res):
            items = [
                QTableWidgetItem(t.name + (" *" if t.required else "")),
                QTableWidgetItem("✓ OK" if t.ok else ("✕ Em falta" if t.required else "— Em falta")),
                QTableWidgetItem(t.version),
                QTableWidgetItem(t.purpose + ("" if t.ok or not t.install_hint
                                              else f"  ·  instalar: {t.install_hint}")),
            ]
            items[1].setForeground(QColor(theme.OK if t.ok else
                                          (theme.DANGER if t.required else theme.MUTED)))
            for c, it in enumerate(items):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.diag.setItem(i, c, it)
