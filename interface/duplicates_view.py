"""Duplicados: análise, recomendações e envio para a quarentena (nunca apaga)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGridLayout, QMessageBox

from core.duplicates import EXACT, PROBABLE, VERSION, DuplicateFinder
from core.safety import SafetyError

from . import theme
from .task_page import Rows, TaskPage, make_table
from .widgets import StatCard, fmt_int, human_size

TYPE_LABEL = {EXACT: "Exacto", PROBABLE: "Provável", VERSION: "Versão diferente"}


class DuplicatesView(TaskPage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Duplicados",
                         "Filmes, música, legendas, capas e ficheiros auxiliares. Exactos por SHA256; "
                         "prováveis por título, ano, duração e metadados. Nada é apagado: os "
                         "marcados vão para a quarentena e podem ser repostos.", parent)
        self.add_action("Enviar marcados para a quarentena", self._quarantine)
        self.add_action("Analisar duplicados", self._analyse, primary=True)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {
            "exact": StatCard("Duplicados exactos", "≡", theme.DANGER),
            "probable": StatCard("Duplicados prováveis", "≈", theme.WARN),
            "versions": StatCard("Ficheiros em grupos de versões", "◇", theme.ACCENT_2),
            "space": StatCard("Espaço potencialmente libertável", "◔", theme.ACCENT),
        }
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        self.lay.addLayout(grid)
        self.model = Rows([
            ("checked", "", None),
            ("group", "Grupo", None),
            ("type", "Tipo", lambda v, r: TYPE_LABEL.get(v, v)),
            ("kind", "Categoria", None),
            ("name", "Ficheiro", None),
            ("size", "Tamanho", lambda v, r: human_size(v)),
            ("info", "Características", None),
            ("keep", "Sugestão", lambda v, r: "manter" if v else "candidato"),
            ("folder", "Pasta", None),
            ("recommendation", "Recomendação", None),
        ], self, checkable=True)
        self.view = make_table(self.model)
        self.lay.addWidget(self.view, 1)
        self._load_last()

    def _load_last(self):
        last = self.ctx.db.get_setting("last_duplicates") or {}
        if last:
            self._cards(last)
            self.status.setText(f"Última análise: {last.get('date', '?').replace('T', ' ')}. "
                                "Volte a analisar para ver a lista.")

    def _cards(self, s):
        c = self.cards
        c["exact"].set(fmt_int(s.get("exact")), "cópias iguais byte a byte", bool(s.get("exact")))
        c["probable"].set(fmt_int(s.get("probable")), "mesmo filme/faixa, ficheiros diferentes",
                          bool(s.get("probable")))
        c["versions"].set(fmt_int(s.get("versions")), "ao vivo, remix, 720p/1080p… preservar")
        c["space"].set(human_size(s.get("space_exact")),
                       f"+ {human_size(s.get('space_probable'))} nos prováveis")

    def _analyse(self):
        def job(prog, cancel):
            return DuplicateFinder(self.ctx.db).analyse(prog, cancel)

        def done(s):
            if s.get("cancelled"):
                return
            from core.database import now_iso
            light = {k: v for k, v in s.items() if k != "groups"}
            light["date"] = now_iso()
            self.ctx.db.set_setting("last_duplicates", light)
            self._cards(s)
            rows = []
            for n, g in enumerate(s["groups"], 1):
                for it in g["items"]:
                    rows.append({"group": n, "type": g["type"], "kind": g["kind"],
                                 "name": Path(it["path"]).name, "folder": str(Path(it["path"]).parent),
                                 "path": it["path"], "size": it["size"], "info": it["info"],
                                 "keep": it["keep"], "recommendation": g["recommendation"],
                                 # só os exactos vêm pré-marcados; prováveis e versões: decisão sua
                                 "checked": g["type"] == EXACT and not it["keep"]})
            self.model.set_rows(rows)
            self.status.setText(f"{len(s['groups'])} grupos. Os exactos que não são para manter vêm "
                                "marcados; reveja antes de enviar para a quarentena.")
        self.run_task(job, done, "A analisar duplicados (cálculo de SHA256)…")

    def _quarantine(self):
        marked = [r for r in self.model.rows if r.get("checked")]
        if not marked:
            QMessageBox.information(self, "Quarentena", "Não há ficheiros marcados.")
            return
        groups = {}
        for r in self.model.rows:
            groups.setdefault(r["group"], []).append(r)
        for g, items in groups.items():
            if all(i.get("checked") for i in items):
                QMessageBox.warning(self, "Quarentena",
                                    f"No grupo {g} estão todos marcados. Deixe pelo menos um ficheiro "
                                    "por grupo.")
                return
        total = sum(r["size"] or 0 for r in marked)
        q = QMessageBox.question(self, "Quarentena",
                                 f"Enviar {len(marked)} ficheiro(s) ({human_size(total)}) para "
                                 "Quarentena/Duplicados?\nNada é apagado e tudo pode ser reposto no Histórico.")
        if q != QMessageBox.Yes:
            return
        done, errs = 0, []
        for r in marked:
            try:
                self.ctx.files.quarantine(r["path"], "Duplicados", f"Duplicado ({TYPE_LABEL[r['type']]})")
                r["checked"] = False
                r["_checkable"] = False
                r["keep"] = False
                r["info"] = "→ quarentena"
                done += 1
            except (SafetyError, OSError) as e:
                errs.append(f"{r['name']}: {e}")
        self.model.set_rows(self.model.rows)
        self.ctx.data_changed.emit()
        msg = f"{done} ficheiro(s) enviados para a quarentena."
        if errs:
            msg += "\n\n" + "\n".join(errs[:10])
        QMessageBox.information(self, "Quarentena", msg)
