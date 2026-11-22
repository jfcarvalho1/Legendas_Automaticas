"""Organizar música: Artista/Álbum (Ano)/NN - Faixa, com revisão, correcção e reversão."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from core.organizer import CONFLICT, DONE, ERROR, ORGANIZED, READY, UNCERTAIN
from music.organizer import MusicOrganizer

from .organize_view import CONF_LABEL, OrganizeView
from .task_page import Rows, TaskPage, make_table
from .widgets import status_fmt


class TrackEditDialog(QDialog):
    def __init__(self, props: list[dict], parent=None):
        super().__init__(parent)
        one = len(props) == 1
        p = props[0]
        self.setWindowTitle("Corrigir dados da faixa" if one else f"Corrigir {len(props)} faixas")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        if not one:
            lay.addWidget(QLabel("Os campos preenchidos aplicam-se a todas as faixas seleccionadas."))
        form = QFormLayout()
        self.f = {}
        for key, label in (("artist", "Artista"), ("album", "Álbum")):
            e = QLineEdit(p.get(key) or "" if one or all(x.get(key) == p.get(key) for x in props) else "")
            self.f[key] = e
            form.addRow(label, e)
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setSpecialValueText("—")
        self.year.setValue(int(p.get("album_year") or p.get("year") or 0))
        form.addRow("Ano", self.year)
        if one:
            self.f["title"] = QLineEdit(p.get("title") or "")
            form.addRow("Título", self.f["title"])
            self.track = QSpinBox()
            self.track.setRange(0, 999)
            self.track.setSpecialValueText("—")
            self.track.setValue(int(p.get("track") or 0))
            form.addRow("N.º da faixa", self.track)
        lay.addLayout(form)
        note = QLabel("As correcções são escritas nas tags da cópia na biblioteca; o original fica igual.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.one = one

    def values(self) -> dict:
        v = {k: e.text().strip() for k, e in self.f.items() if e.text().strip()}
        if self.year.value():
            v["year"] = self.year.value()
        if self.one and self.track.value():
            v["track"] = self.track.value()
        return v


class MusicOrganizeView(TaskPage):
    FILTERS = [("all", "Todas"), (READY, "Prontas"), (UNCERTAIN, "Incertas"), (CONFLICT, "Conflitos"),
               (ORGANIZED, "Já na biblioteca"), (DONE, "Aplicadas"), (ERROR, "Com erro")]

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Organizar música",
                         "Copia da pasta de origem para a biblioteca em Artista/Álbum (Ano)/NN - Faixa, "
                         "com cover.jpg por álbum. Os originais ficam intactos e a qualidade nunca é alterada.",
                         parent)
        self.props: list[dict] = []
        self.org: MusicOrganizer | None = None
        self.b_revert = self.add_action("Reverter último lote", self._revert)
        self.add_action("Analisar e propor", self._propose)
        self.b_apply = self.add_action("Aplicar seleccionadas", self._apply, primary=True)

        bar = QHBoxLayout()
        self.cb_mb = QCheckBox("Completar anos em falta com o MusicBrainz")
        self.cb_mb.setChecked(bool(ctx.db.get_setting("musicbrainz_enabled")))
        self.cb_mb.toggled.connect(lambda v: ctx.db.set_setting("musicbrainz_enabled", v))
        self.filter = QComboBox()
        for k, label in self.FILTERS:
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(lambda _i: self._show())
        b_all = QPushButton("Seleccionar prontas")
        b_all.clicked.connect(lambda: self._check(True))
        b_none = QPushButton("Limpar selecção")
        b_none.clicked.connect(lambda: self._check(False))
        b_edit = QPushButton("Corrigir…")
        b_edit.clicked.connect(self._edit)
        bar.addWidget(self.cb_mb)
        bar.addStretch(1)
        for w in (self.filter, b_all, b_none, b_edit):
            bar.addWidget(w)
        self.lay.addLayout(bar)

        self.model = Rows([
            ("checked", "", None),
            ("status", "Estado", status_fmt),
            ("confidence", "Confiança", lambda v, r: CONF_LABEL.get(v, v or "")),
            ("artist", "Artista", None),
            ("album", "Álbum", None),
            ("album_year", "Ano", None),
            ("title", "Título", None),
            ("target", "Destino", lambda v, r: self._rel(v) if v else "—"),
            ("note", "Observações", None),
            ("filename", "Ficheiro de origem", None),
        ], self, checkable=True)
        self.view = make_table(self.model)
        self.view.doubleClicked.connect(lambda _i: self._edit())
        self.model.dataChanged.connect(lambda *_: self._counts())
        self.lay.addWidget(self.view, 1)

    def _rel(self, p):
        try:
            return str(Path(p).relative_to(self.ctx.db.get_setting("music_library_folder") or ""))
        except ValueError:
            return p

    def _show(self):
        k = self.filter.currentData()
        for p in self.props:
            p["_checkable"] = p["status"] == READY
        self.model.set_rows(self.props if k == "all" else [p for p in self.props if p["status"] == k])
        self._counts()

    def _counts(self):
        c = {}
        for p in self.props:
            c[p["status"]] = c.get(p["status"], 0) + 1
        sel = sum(1 for p in self.props if p.get("checked") and p["status"] == READY)
        if self.props:
            self.status.setText(f"{len(self.props)} faixas · {c.get(READY, 0)} prontas · "
                                f"{c.get(UNCERTAIN, 0)} incertas · {c.get(CONFLICT, 0)} conflitos · "
                                f"{c.get(ORGANIZED, 0)} já na biblioteca")
        self.b_apply.setText(f"Aplicar seleccionadas ({sel})")

    def _check(self, on):
        for p in self.props:
            if p["status"] == READY:
                p["checked"] = on
        self._show()

    def _selected_indexes(self) -> list[int]:
        rows = [self.model.row(i.row()) for i in self.view.selectionModel().selectedRows()]
        return [k for k, p in enumerate(self.props) if any(p is r for r in rows)]

    def _propose(self):
        db = self.ctx.db
        if not db.get_setting("music_library_folder"):
            QMessageBox.information(self, "Música", "Defina a pasta da biblioteca de música na Configuração.")
            return
        if not db.scalar("SELECT COUNT(*) FROM music WHERE status='ok'"):
            QMessageBox.information(self, "Música", "Faça primeiro a análise na página Música.")
            return
        mb = None
        if self.cb_mb.isChecked():
            from integrations.musicbrainz import MusicBrainzClient
            mb = MusicBrainzClient()
        self.org = MusicOrganizer(db, self.ctx.files, mb)

        def done(props):
            self.props = props
            self._show()
        self.run_task(lambda prog, cancel: self.org.propose(prog, cancel), done, "A preparar propostas…")

    def _edit(self):
        idx = self._selected_indexes()
        if not idx or not self.org:
            return
        idx = [i for i in idx if self.props[i]["status"] in (READY, UNCERTAIN, CONFLICT)]
        if not idx:
            return
        dlg = TrackEditDialog([self.props[i] for i in idx], self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.org.edit(self.props, idx, dlg.values())
        for i in idx:
            if self.props[i]["status"] == READY:
                self.props[i]["checked"] = True
        self._show()

    def _apply(self):
        todo = [p for p in self.props if p.get("checked") and p["status"] == READY]
        if not todo:
            return
        mode = "copiadas" if (self.ctx.db.get_setting("music_mode") or "copy") == "copy" else "movidas"
        q = QMessageBox.question(self, "Aplicar", f"{len(todo)} faixas vão ser {mode} para a biblioteca.\n"
                                                  "Cada operação é registada e o lote pode ser revertido.")
        if q != QMessageBox.Yes:
            return

        def done(s):
            self._show()
            msg = (f"{s['tracks']} faixas na biblioteca · {s['covers']} capas · {s['tags']} correcções "
                   f"de tags.\nLote: {s['batch']}")
            if s["errors"]:
                msg += "\n\nProblemas:\n" + "\n".join(s["errors"][:12])
            QMessageBox.information(self, "Música", msg)
        self.run_task(lambda prog, cancel: self.org.apply(self.props, prog), done, "A organizar…")

    def _revert(self):
        batch = self.ctx.db.get_setting("last_music_batch")
        if not batch:
            QMessageBox.information(self, "Reverter", "Não há nenhum lote de música para reverter.")
            return
        q = QMessageBox.question(self, "Reverter", f"Reverter o lote {batch}?\nAs cópias criadas vão "
                                                   "para a quarentena; os originais não são tocados.")
        if q != QMessageBox.Yes:
            return
        done, errs = self.ctx.files.revert_batch(batch)
        self.ctx.db.set_setting("last_music_batch", "")
        self.props = []
        self._show()
        self.ctx.data_changed.emit()
        QMessageBox.information(self, "Reverter", f"{done} operações revertidas." +
                                ("\n\n" + "\n".join(errs[:10]) if errs else ""))


class OrganizeHub(QWidget):
    """Página «Organizar» com separadores Filmes e Música."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        self.tabs = QTabWidget()
        self.movies = OrganizeView(ctx)
        self.music = MusicOrganizeView(ctx)
        self.tabs.addTab(self.movies, "Filmes")
        self.tabs.addTab(self.music, "Música")
        lay.addWidget(self.tabs)

    def show_tab(self, key: str):
        self.tabs.setCurrentIndex(1 if key == "music" else 0)
