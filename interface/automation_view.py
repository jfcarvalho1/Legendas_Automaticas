"""Automatização: executar agora, agendar, Jellyfin."""
from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTimeEdit,
                               QVBoxLayout)

from core import scheduler
from core.automation import MODES, STEPS, Automation, Busy

from .task_page import TaskPage


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Panel")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    t = QLabel(title)
    t.setObjectName("SectionTitle")
    lay.addWidget(t)
    return f, lay


class AutomationView(TaskPage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Automatização",
                         "Corre os módulos em sequência. Em modo automático só se aplica o que é "
                         "seguro: nada é apagado, casos incertos ficam para revisão.", parent)
        self.add_action("Executar agora", self._run, primary=True)
        db = ctx.db

        top = QHBoxLayout()
        # --- o quê
        f, fl = _panel("Execução")
        self.mode = QComboBox()
        for k, label in MODES.items():
            self.mode.addItem(label, k)
        fl.addWidget(self.mode)
        grid = QGridLayout()
        self.steps: dict[str, QCheckBox] = {}
        for i, (k, label) in enumerate(STEPS):
            cb = QCheckBox(label)
            cb.setChecked(True)
            self.steps[k] = cb
            grid.addWidget(cb, i // 2, i % 2)
        fl.addLayout(grid)
        self.cb_medium = QCheckBox("No modo automático, organizar também filmes com confiança média "
                                   "(nome com ano claro, sem confirmação no TMDb)")
        self.cb_medium.setChecked(bool(db.get_setting("auto_apply_medium")))
        self.cb_medium.toggled.connect(lambda v: db.set_setting("auto_apply_medium", v))
        fl.addWidget(self.cb_medium)
        top.addWidget(f, 3)

        # --- agendamento + Jellyfin
        col = QVBoxLayout()
        f, fl = _panel("Agendamento diário")
        row = QHBoxLayout()
        row.addWidget(QLabel("Hora"))
        self.time = QTimeEdit(QTime(3, 17))
        self.time.setDisplayFormat("HH:mm")
        row.addWidget(self.time)
        self.sched_mode = QComboBox()
        for k, label in MODES.items():
            self.sched_mode.addItem(label.split(" — ")[0], k)
        i = self.sched_mode.findData(db.get_setting("schedule_mode") or "automatico")
        self.sched_mode.setCurrentIndex(max(i, 0))
        row.addWidget(self.sched_mode)
        fl.addLayout(row)
        row = QHBoxLayout()
        b = QPushButton("Activar")
        b.clicked.connect(self._schedule)
        b2 = QPushButton("Remover")
        b2.clicked.connect(self._unschedule)
        row.addWidget(b)
        row.addWidget(b2)
        row.addStretch(1)
        fl.addLayout(row)
        self.sched_status = QLabel("")
        self.sched_status.setObjectName("Muted")
        self.sched_status.setWordWrap(True)
        fl.addWidget(self.sched_status)
        col.addWidget(f)

        f, fl = _panel("Jellyfin")
        self.jf_url = QLineEdit(db.get_setting("jellyfin_url") or "")
        self.jf_url.setPlaceholderText("http://endereço-do-servidor:8096")
        self.jf_key = QLineEdit(db.get_setting("jellyfin_api_key") or "")
        self.jf_key.setEchoMode(QLineEdit.Password)
        self.jf_key.setPlaceholderText("chave de API (Painel → Chaves de API)")
        fl.addWidget(self.jf_url)
        fl.addWidget(self.jf_key)
        row = QHBoxLayout()
        for text, slot in (("Guardar e testar", self._jf_test), ("Actualizar biblioteca", self._jf_refresh),
                           ("Verificar compatibilidade", self._jf_check)):
            bb = QPushButton(text)
            bb.clicked.connect(slot)
            row.addWidget(bb)
        fl.addLayout(row)
        col.addWidget(f)
        top.addLayout(col, 2)
        self.lay.addLayout(top)

        t = QLabel("Registo da execução")
        t.setObjectName("SectionTitle")
        self.lay.addWidget(t)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.lay.addWidget(self.log, 1)
        self._sched_refresh()

    # -------------------------------------------------------------- correr
    def _on_progress(self, cur, total, msg):
        if cur == -1:
            self.log.appendPlainText(msg)
            return
        super()._on_progress(cur, total, msg)

    def _run(self):
        mode = self.mode.currentData()
        steps = [k for k, cb in self.steps.items() if cb.isChecked()]
        if mode == "automatico":
            q = QMessageBox.question(self, "Automático",
                                     "O modo automático vai organizar, criar legendas/capas/NFO e copiar "
                                     "música, só nos casos seguros. Nada é apagado e cada lote pode ser "
                                     "revertido. Continuar?")
            if q != QMessageBox.Yes:
                return
        self.log.clear()

        def job(prog, cancel):
            a = Automation(self.ctx.db, log_fn=lambda m: prog(-1, -1, m), progress=prog, cancelled=cancel)
            try:
                return a.run(mode, steps)
            except Busy as e:
                prog(-1, -1, str(e))
                return {}
        self.run_task(job, lambda s: self.status.setText("Concluído. " + (
            "; ".join(f"{k}: {v}" for k, v in s.items()) if s else "")), "A executar…")

    # ---------------------------------------------------------- agendamento
    def _sched_refresh(self):
        st = scheduler.status()
        self.sched_status.setText(f"Agendado: {st}." if st else "Sem agendamento activo.")

    def _schedule(self):
        t = self.time.time()
        mode = self.sched_mode.currentData()
        self.ctx.db.set_setting("schedule_mode", mode)
        try:
            msg = scheduler.install(t.hour(), t.minute(), mode)
            QMessageBox.information(self, "Agendamento", msg + "\nO computador tem de estar ligado a essa hora.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Agendamento", f"Não foi possível agendar:\n{e}")
        self._sched_refresh()

    def _unschedule(self):
        try:
            QMessageBox.information(self, "Agendamento", scheduler.remove())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Agendamento", str(e))
        self._sched_refresh()

    # -------------------------------------------------------------- Jellyfin
    def _jf(self):
        from integrations.jellyfin import JellyfinClient
        db = self.ctx.db
        db.set_setting("jellyfin_url", self.jf_url.text().strip())
        db.set_setting("jellyfin_api_key", self.jf_key.text().strip())
        if not (self.jf_url.text().strip() and self.jf_key.text().strip()):
            raise RuntimeError("Indique o endereço e a chave de API do Jellyfin.")
        db.set_setting("jellyfin_enabled", True)
        return JellyfinClient(self.jf_url.text().strip(), self.jf_key.text().strip())

    def _jf_test(self):
        try:
            QMessageBox.information(self, "Jellyfin", f"Ligação OK: {self._jf().test()}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Jellyfin", str(e))

    def _jf_refresh(self):
        try:
            self._jf().refresh()
            QMessageBox.information(self, "Jellyfin", "Pedido de actualização da biblioteca enviado.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Jellyfin", str(e))

    def _jf_check(self):
        from core.jellyfin_check import check_movies
        c = check_movies(self.ctx.db)
        self.log.clear()
        self.log.appendPlainText(f"Compatibilidade Jellyfin — {c['ok']} filmes sem avisos, "
                                 f"{len(c['issues'])} com avisos:")
        for i in c["issues"][:500]:
            self.log.appendPlainText(f"  • {i['path']}: {', '.join(i['problems'])}")
