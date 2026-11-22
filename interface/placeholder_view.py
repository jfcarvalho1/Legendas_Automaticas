"""Páginas dos módulos das fases seguintes (estrutura já presente na interface)."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .context import AppContext
from .widgets import PageHeader

PLANNED = {
    "subtitles": ("Legendas", "Fases 4 e 5", [
        "Pesquisa em OpenSubtitles e legendas locais (por título, ano, ID e hash do vídeo).",
        "Prioridade: pt-PT → pt-BR → outros idiomas.",
        "Conversão SRT · ASS · SSA · VTT · SUB e validação da estrutura.",
        "Tradução local para Português de Portugal (Argos Translate), por blocos, com retoma.",
        "A legenda original nunca é substituída: a tradução vai para um ficheiro separado.",
    ]),
    "covers": ("Capas", "Fase 6", [
        "Pesquisa de posters no TMDb (com chave de API) e outras fontes legais.",
        "Evitar posters de filmes homónimos; preferir boa resolução.",
        "Capas existentes preservadas; substituição só com confirmação.",
        "Criação de metadata.json e NFO compatível com Jellyfin.",
    ]),
    "analysis": ("Análise", "Fase 3", [
        "Proposta de nomes normalizados «Título (Ano)» e estrutura de pastas.",
        "Modo análise (só propõe) e modo execução (aplica o que foi aprovado).",
        "Casos de identificação incerta nunca são alterados automaticamente.",
    ]),
    "duplicates": ("Duplicados", "Fase 8", [
        "Duplicados exactos por SHA256 e prováveis por nome, tamanho, duração e metadados.",
        "Distinguir versões, remasterizações, ao vivo e qualidades diferentes.",
        "Espaço potencialmente libertável e recomendações.",
        "Nunca apaga: apenas sugere quarentena, reversível.",
    ]),
    "automation": ("Automatização", "Fase 9", [
        "Tarefas agendadas: análise, legendas, capas, relatórios.",
        "Modos: Análise · Automático · Reparação · Recuperação.",
        "Retoma de tarefas interrompidas e execução incremental.",
    ]),
}


class PlaceholderView(QWidget):
    def __init__(self, ctx: AppContext, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        title, phase, items = PLANNED[key]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(PageHeader(title, f"Módulo previsto para a {phase} do plano de construção."))
        f = QFrame()
        f.setObjectName("Panel")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(22, 18, 22, 20)
        t = QLabel("O que este módulo vai fazer")
        t.setObjectName("SectionTitle")
        fl.addWidget(t)
        for it in items:
            lbl = QLabel(f"•  {it}")
            lbl.setWordWrap(True)
            fl.addWidget(lbl)
        note = QLabel("Na versão 0.1 a prioridade é a fundação: inventário, base de dados, "
                      "registos, protecção dos ficheiros e recuperação de operações.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        fl.addSpacing(8)
        fl.addWidget(note)
        lay.addWidget(f)
        lay.addStretch(1)
