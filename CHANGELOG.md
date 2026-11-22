# Alterações

## 1.0.2 — 2026-11-22
- Instalador do Windows completo, de início ao fim: Python 3.12 (compatível com todos os
  componentes), FFmpeg, PySide6/Mutagen, motor de tradução local com os modelos
  inglês/espanhol/francês → português, atalhos, verificação final (`app.py --check`) e abertura
  automática do programa. Fecha o programa se estiver aberto e refaz o ambiente se a versão do
  Python mudar. Registo em `logs/instalacao.log`.

## 1.0.1 — 2026-11-22
- Corrigido: no Windows em português a aplicação fechava ao arrancar (resposta do Agendador de
  Tarefas com acentos na codificação OEM). As respostas da consola são agora lidas na codificação
  certa e nunca impedem o arranque.

## 1.0.0 — 2026-11-22 — versão estável
- **Legendas**: inventário por filme (incl. subpastas Subs/), detecção de idioma pelo nome e pelo
  texto (pt-PT/pt-BR), conversão ASS/SSA/VTT/SUB → SRT UTF-8, validação, OpenSubtitles (hash do
  vídeo, IMDb/TMDb, título) com prioridade pt-PT > pt-BR > en.
- **Tradução local** (Argos Translate) para pt-PT, bloco a bloco com retoma, timestamps preservados;
  adaptação pt-BR → pt-PT (vocabulário e gerúndio) sem internet; instalação do motor com um botão.
- **Capas, NFO e metadata.json** com TMDb (poster em português, verificação do ano contra homónimos);
  NFO Jellyfin/Kodi; campos extra do JSON preservados; substituição só com quarentena.
- **Música**: Artista/Álbum (Ano)/NN - Faixa, cópia validada (original intacto), capas por álbum,
  dedução do nome/pasta para faixas sem tags, correcção de tags na cópia, MusicBrainz opcional.
- **Duplicados**: exactos por SHA256 (com cache), prováveis por título/ano e artista/título/duração,
  versões diferentes assinaladas, espaço libertável, envio para quarentena.
- **Automatização**: modos Análise/Automático/Reparação/Recuperação, agendamento diário (Windows e
  Ubuntu), execução sem janela `app.py --auto`, bloqueio contra execuções simultâneas.
- **Jellyfin**: teste de ligação, actualização da biblioteca, verificação de compatibilidade.
- Backups automáticos da base de dados; operações de criação/cópia reversíveis; relatórios de
  duplicados e legendas.

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
