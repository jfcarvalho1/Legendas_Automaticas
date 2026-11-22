"""Dashboard: estado das bibliotecas, problemas e actividade recente."""
from __future__ import annotations

from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .context import AppContext
from .widgets import PageHeader, StatCard, fmt_int, human_size


class DashboardView(QWidget):
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

        header = PageHeader("Dashboard", "Visão geral da biblioteca de filmes e música.")
        self.btn_movies = QPushButton("Analisar filmes")
        self.btn_movies.setObjectName("Primary")
        self.btn_music = QPushButton("Analisar música")
        self.btn_movies.clicked.connect(lambda: self._scan("movies"))
        self.btn_music.clicked.connect(lambda: self._scan("music"))
        header.actions.addWidget(self.btn_music)
        header.actions.addWidget(self.btn_movies)
        lay.addWidget(header)

        # painel de progresso
        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("Panel")
        pl = QVBoxLayout(self.progress_panel)
        pl.setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        self.progress_title = QLabel("A analisar…")
        self.progress_title.setObjectName("SectionTitle")
        row.addWidget(self.progress_title, 1)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.ctx.cancel_scan)
        row.addWidget(self.btn_cancel)
        pl.addLayout(row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        pl.addWidget(self.progress_bar)
        self.progress_file = QLabel("")
        self.progress_file.setObjectName("Muted")
        pl.addWidget(self.progress_file)
        self.progress_panel.hide()
        lay.addWidget(self.progress_panel)

        # cartões
        self.cards: dict[str, StatCard] = {}

        def section(title: str, specs: list[tuple]):
            t = QLabel(title)
            t.setObjectName("SectionTitle")
            lay.addWidget(t)
            grid = QGridLayout()
            grid.setSpacing(12)
            for i, (key, label, icon, color, page, flt) in enumerate(specs):
                c = StatCard(label, icon, color)
                c.clicked.connect(lambda p=page, f=flt: self.ctx.navigate.emit(p, f))
                self.cards[key] = c
                grid.addWidget(c, i // 4, i % 4)
            for col in range(4):
                grid.setColumnStretch(col, 1)
            lay.addLayout(grid)

        A, W, D, B, M = theme.ACCENT, theme.WARN, theme.DANGER, theme.ACCENT_2, theme.MUTED
        section("Filmes", [
            ("m_total", "Filmes no inventário", "▶", A, "movies", "all"),
            ("m_subs", "Sem legendas", "✎", W, "movies", "no_subs"),
            ("m_cover", "Sem capa", "▢", W, "movies", "no_cover"),
            ("m_meta", "Metadados incompletos", "☰", W, "movies", "no_metadata"),
            ("m_uncertain", "Identificação incerta", "?", W, "movies", "uncertain"),
            ("m_zero", "Ficheiros de 0 bytes", "∅", D, "movies", "zero_bytes"),
            ("m_invalid", "Inválidos / incompletos", "✕", D, "movies", "invalid"),
            ("m_missing", "Ficheiros em falta", "⌕", M, "movies", "missing"),
        ])
        section("Música", [
            ("a_total", "Faixas no inventário", "♫", A, "music", "all"),
            ("a_artists", "Artistas · Álbuns", "◎", B, "music", "all"),
            ("a_cover", "Sem capa", "▢", W, "music", "no_cover"),
            ("a_tags", "Tags incompletas", "☰", W, "music", "incomplete_tags"),
            ("a_zero", "Ficheiros de 0 bytes", "∅", D, "music", "zero_bytes"),
            ("a_invalid", "Inválidos", "✕", D, "music", "invalid"),
            ("a_missing", "Ficheiros em falta", "⌕", M, "music", "missing"),
        ])
        section("Sistema", [
            ("s_errors", "Erros e avisos por resolver", "!", D, "history", "errors"),
            ("s_ops", "Operações registadas", "⟲", B, "history", "operations"),
            ("s_quar", "Em quarentena", "⧉", B, "history", "operations"),
            ("s_space", "Espaço potencialmente recuperável", "◔", A, "duplicates", ""),
        ])

        t = QLabel("Actividade recente")
        t.setObjectName("SectionTitle")
        lay.addWidget(t)
        self.recent = QListWidget()
        self.recent.setMinimumHeight(180)
        lay.addWidget(self.recent)
        lay.addStretch(1)

        ctx.data_changed.connect(self.refresh)
        ctx.scan_started.connect(self._on_started)
        ctx.scan_progress.connect(self._on_progress)
        ctx.scan_finished.connect(self._on_finished)
        ctx.scan_failed.connect(self._on_failed)
        self.refresh()

    # ---------------------------------------------------------------------
    def _scan(self, kind: str):
        err = self.ctx.start_scan(kind)
        if err:
            QMessageBox.information(self, "Análise", err)

    def _on_started(self, kind):
        self.progress_title.setText("A analisar filmes…" if kind == "movies" else "A analisar música…")
        self.progress_bar.setRange(0, 0)
        self.progress_file.setText("")
        self.progress_panel.show()
        self.btn_movies.setEnabled(False)
        self.btn_music.setEnabled(False)

    def _on_progress(self, cur, total, msg):
        if total:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(cur)
            self.progress_file.setText(f"{cur} de {total} · {msg}")
        else:
            self.progress_file.setText(msg)

    def _end(self):
        self.progress_panel.hide()
        self.btn_movies.setEnabled(True)
        self.btn_music.setEnabled(True)

    def _on_finished(self, kind, st):
        self._end()
        what = "Filmes" if kind == "movies" else "Música"
        msg = (f"{what}: {st.get('total', 0)} ficheiros encontrados\n"
               f"• {st.get('new', 0)} novos\n• {st.get('updated', 0)} actualizados\n"
               f"• {st.get('skipped', 0)} sem alterações\n"
               f"• {st.get('zero_bytes', 0)} com 0 bytes\n• {st.get('invalid', 0)} inválidos\n"
               f"• {st.get('missing', 0)} deixaram de existir")
        if st.get("cancelled"):
            msg = "Análise cancelada. O que já foi analisado ficou guardado."
        QMessageBox.information(self, "Análise concluída", msg)

    def _on_failed(self, _kind, msg):
        self._end()
        QMessageBox.warning(self, "Análise", msg)

    def refresh(self):
        db = self.ctx.db
        m, a, g = db.movie_stats(), db.music_stats(), db.general_stats()
        c = self.cards
        c["m_total"].set(fmt_int(m["total"]), human_size(m["size"]))
        c["m_subs"].set(fmt_int(m["no_subs"]), "sem ficheiro nem pista de legenda", m["no_subs"] > 0)
        c["m_cover"].set(fmt_int(m["no_cover"]), "capa a obter (Fase 6)", m["no_cover"] > 0)
        c["m_meta"].set(fmt_int(m["no_metadata"]), "sem NFO ou metadata.json", m["no_metadata"] > 0)
        c["m_uncertain"].set(fmt_int(m["uncertain"]), "nome sem ano identificável", m["uncertain"] > 0)
        c["m_zero"].set(fmt_int(m["zero_bytes"]), "preservados, não processados", m["zero_bytes"] > 0)
        c["m_invalid"].set(fmt_int(m["invalid"]), "FFprobe não conseguiu ler", m["invalid"] > 0)
        c["m_missing"].set(fmt_int(m["missing"]), "já não estão na pasta", m["missing"] > 0)
        c["a_total"].set(fmt_int(a["total"]), human_size(a["size"]))
        c["a_artists"].set(f"{fmt_int(a['artists'])} · {fmt_int(a['albums'])}", "artistas · álbuns")
        c["a_cover"].set(fmt_int(a["no_cover"]), "sem capa embutida nem na pasta", a["no_cover"] > 0)
        c["a_tags"].set(fmt_int(a["incomplete_tags"]), "falta artista, álbum ou título",
                        a["incomplete_tags"] > 0)
        c["a_zero"].set(fmt_int(a["zero_bytes"]), "preservados, não processados", a["zero_bytes"] > 0)
        c["a_invalid"].set(fmt_int(a["invalid"]), "não foi possível ler", a["invalid"] > 0)
        c["a_missing"].set(fmt_int(a["missing"]), "já não estão na pasta", a["missing"] > 0)
        c["s_errors"].set(fmt_int(g["errors"]), "abrir histórico de erros", g["errors"] > 0)
        c["s_ops"].set(fmt_int(g["operations"]), "todas reversíveis quando possível")
        c["s_quar"].set(fmt_int(g["quarantined"]), "quarentena não é eliminação")
        c["s_space"].set("—", "disponível com a análise de duplicados (Fase 8)")

        self.recent.clear()
        items = []
        for j in db.query("SELECT * FROM jobs ORDER BY id DESC LIMIT 6"):
            name = {"inventario_filmes": "Inventário de filmes",
                    "inventario_musica": "Inventário de música"}.get(j["job_type"], j["job_type"])
            items.append((j["started_at"] or "", f"{name} — {j['status']} · {j['message'] or ''}"))
        for o in db.query("SELECT * FROM operations WHERE operation!='reserved' "
                          "ORDER BY id DESC LIMIT 6"):
            items.append((o["timestamp"] or "",
                          f"{o['operation_id']} · {o['operation']} — {o['status']} · "
                          f"{o['original_path'] or ''}"))
        items.sort(reverse=True)
        if not items:
            self.recent.addItem(QListWidgetItem(
                "Ainda não há actividade. Comece por analisar a pasta de filmes ou de música."))
        for ts, text in items[:10]:
            self.recent.addItem(QListWidgetItem(f"{ts.replace('T', ' ')}   {text}"))
