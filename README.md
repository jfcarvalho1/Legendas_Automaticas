# Media Organizer

Aplicação desktop local, gratuita e open source, para Ubuntu, que gere uma biblioteca de **filmes** e **música**: inventário, análise técnica, legendas, capas, metadados, duplicados e compatibilidade com **Jellyfin**. Os originais ficam sempre preservados.

> Versão actual: **0.1.0**, a fundação (Fase 1 + inventário da Fase 2).
> A especificação completa está em [`docs/ESPECIFICACAO.txt`](docs/ESPECIFICACAO.txt).

## Instalar (Ubuntu)

Abra um terminal e cole:

```bash
cd ~
git clone https://github.com/jfcarvalho1/Legendas_Automaticas.git MediaOrganizer
bash MediaOrganizer/instalar.sh
```

O instalador:
- instala apenas o que faltar no sistema (`ffmpeg`, `python3-venv`, `libxcb-cursor0`), pedindo a palavra-passe;
- cria um ambiente Python próprio em `.venv` (não mexe no Python do sistema);
- cria o atalho **Media Organizer** no menu de aplicações e no ambiente de trabalho.

Depois disso basta abrir a aplicação pelo atalho.

### Actualizar

```bash
cd ~/MediaOrganizer && git pull && bash instalar.sh
```

A base de dados, os registos e a quarentena não são tocados pela actualização.

## O que a versão 0.1 faz

| Área | Estado |
|---|---|
| Interface com dashboard e menu lateral (tema escuro) | ✅ |
| Assistente inicial e configuração de pastas | ✅ |
| Inventário de filmes: título e ano prováveis, resolução, codecs, duração, idiomas, legendas, capa, NFO | ✅ |
| Inventário de música: artista, álbum, faixa, disco, ano, género, formato, bitrate, amostragem, capa | ✅ |
| Análise incremental (não reanalisa ficheiros que não mudaram) | ✅ |
| Ficheiros de 0 bytes: assinalados, preservados, sem FFprobe | ✅ |
| Ficheiros inválidos e ficheiros em falta | ✅ |
| Sistema de operações `OP_AAAAMMDD_NNN` com registo em base de dados e `logs/operations.jsonl` | ✅ |
| Quarentena com manifesto JSON e reposição a partir do Histórico | ✅ |
| Relatórios HTML, CSV, JSON e TXT | ✅ |
| Diagnóstico de ferramentas (FFprobe, Mutagen, Beets, Czkawka, Argos…) | ✅ |
| Legendas, tradução, capas, renomeação, duplicados, automatização | Fases seguintes |

## Regras de segurança

- A **análise só lê**: nunca altera, move ou apaga ficheiros.
- **Eliminação automática: sempre desactivada**. Não há nenhuma função que apague ficheiros.
- Mover só acontece por ordem do utilizador e passa por verificações: origem existe, destino livre (nunca sobrescreve), permissões e registo.
- Entre discos diferentes: cópia, depois validação SHA256, e o original é **mantido** (a não ser que active a opção na Configuração).
- **Quarentena não é eliminação**: guarda nome e local originais, data, motivo e identificador da operação, e pode ser revertida.
- Tarefas interrompidas (por exemplo, se o computador se desligar) ficam marcadas como interrompidas no arranque seguinte.

## Estrutura

```
app.py                 arranque
core/                  base de dados, inventário, segurança, operações, registos, relatórios, diagnóstico
movies/                identificação de filmes (título/ano)
music/                 leitura de tags
integrations/          (TMDb, OpenSubtitles, MusicBrainz, Beets, Jellyfin — fases seguintes)
interface/             janelas PySide6
tests/                 testes do núcleo
database/ logs/ reports/ backups/ quarantine/   dados locais (fora do Git)
```

## Testes

```bash
cd ~/MediaOrganizer && .venv/bin/python -m unittest discover -s tests -v
```

## Plano

1. ✅ Fundação: interface, base de dados, configurações, registos, segurança, diagnóstico
2. ✅ Inventário de filmes e música (pesquisa e filtros)
3. Organização e renomeação de filmes (`Título (Ano)/`)
4. Legendas: pesquisa, associação, idioma, conversão, validação
5. Tradução local para Português de Portugal
6. Capas, NFO e metadata.json
7. Música: tags, álbuns, capas, Beets, MusicBrainz
8. Duplicados e espaço recuperável
9. Automatização e tarefas agendadas
10. Integração Jellyfin
11. Testes com bibliotecas reais
12. Empacotamento e versão estável

Licença: MIT.
