# Alterações

## 0.2.0 — 2026-11-22
- Página **Organizar**: propostas «Título (Ano)/Título (Ano).ext», revisão, correcção manual,
  aplicação em lote e reversão do lote inteiro.
- Legendas recolhidas também de subpastas (Subs/, Legendas/…), com detecção de idioma
  (pt-PT, pt-BR, pt, en, es, …, forced/SDH).
- Na pasta final ficam só vídeo, legendas, cover.jpg, NFO (XML) e metadata.json; o resto vai
  para a quarentena `Restos_Organizacao` no mesmo disco.
- Versões do mesmo filme: «Título (Ano) - 1080p».
- Integração opcional com o TMDb para confirmar título e ano.
- Renomeações só de maiúsculas/minúsculas funcionam no Windows.

## 0.1.1 — 2026-11-22
- Compatibilidade com Windows: instalador de duplo clique (`instalar.bat`), atalhos no
  Ambiente de Trabalho e Menu Iniciar, ícone `.ico`, detecção do FFmpeg instalado pelo winget,
  sem janelas de consola ao correr o FFprobe, caminhos com `\`, abrir pastas no Explorador.
- `arrancar_com_consola.bat` para diagnosticar problemas de arranque.

## 0.1.0 — 2026-11-22
Primeira versão: fundação da aplicação.
- Interface PySide6 com tema escuro, menu lateral e dashboard com indicadores clicáveis.
- Base de dados SQLite com todas as tabelas previstas na especificação.
- Inventário incremental de filmes (FFprobe) e música (Mutagen ou FFprobe).
- Tratamento de ficheiros de 0 bytes, inválidos e em falta.
- Sistema de operações com identificador único, diário JSONL e reposição.
- Quarentena com manifesto e reversão a partir do Histórico.
- Relatórios HTML/CSV/JSON/TXT, diagnóstico de ferramentas e assistente inicial.
- Instalador automático para Ubuntu com atalho no menu.
