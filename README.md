# Media Organizer

Aplicação desktop local, gratuita e open source, para Ubuntu, que gere uma biblioteca de **filmes** e **música**: inventário, análise técnica, legendas, capas, metadados, duplicados e compatibilidade com **Jellyfin**. Os originais ficam sempre preservados.

> Versão actual: **0.2.0**: fundação, inventário e organização/renomeação de filmes (Fases 1–3).
> A especificação completa está em [`docs/ESPECIFICACAO.txt`](docs/ESPECIFICACAO.txt).

## Instalar no Windows

1. Nesta página do GitHub, carregue no botão verde **Code** → **Download ZIP**.
2. Extraia o ZIP para uma pasta à sua escolha, por exemplo `Documentos\MediaOrganizer`.
3. Abra essa pasta e faça **duplo clique em `instalar.bat`**.
   Se o Windows mostrar "O Windows protegeu o seu PC", carregue em **Mais informações** → **Executar mesmo assim**.
4. No fim aparece o atalho **Media Organizer** no Ambiente de Trabalho e no Menu Iniciar.

O instalador trata de tudo: instala o Python 3.12 e o FFmpeg pelo `winget` se faltarem, cria o ambiente próprio da aplicação e os atalhos.
Se a aplicação não abrir, faça duplo clique em `arrancar_com_consola.bat` para ver a mensagem de erro.

Pasta de filmes sugerida no Windows: `C:\Users\<utilizador>\Videos\Filmes` (pode ser alterada na Configuração).

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

## Organizar e renomear filmes

1. **Filmes** → **Analisar agora** (faz o inventário; não altera nada).
2. **Organizar** → **Analisar e propor**: aparece a lista com o nome novo de cada filme.
3. Reveja. Os incertos (sem ano no nome) não vêm seleccionados: duplo clique para corrigir título e ano.
4. **Aplicar seleccionados**. Se não gostar do resultado: **Reverter último lote**.

Resultado:

```
Filmes/
  Interstellar (2014)/
    Interstellar (2014).mkv
    Interstellar (2014).pt-PT.srt
    Interstellar (2014).en.srt
    cover.jpg
    Interstellar (2014).nfo
    Interstellar (2014).metadata.json
```

- Na pasta final **só ficam** o vídeo, as legendas, a capa, o NFO e o metadata.json.
- **Legendas em subpastas** (`Subs/`, `Legendas/`, `Subs/2_English.srt`…) são recolhidas e renomeadas com o idioma (`.pt-PT`, `.pt-BR`, `.pt`, `.en`, …).
- O resto (`.txt`, samples, `.nfo` de grupos de release, links, imagens extra) vai para a **quarentena** `Restos_Organizacao`, no mesmo disco, fora da biblioteca. Nada é apagado.
- A pasta antiga, se ficar vazia, é removida; a reversão volta a criá-la.
- Duas versões do mesmo filme ficam juntas: `Gladiator (2000).mkv` e `Gladiator (2000) - 720p.mkv`.
- Nunca escreve por cima de um ficheiro existente; se houver conflito, o filme fica assinalado e não é tocado.
- Opcional: com uma chave gratuita do **TMDb** (Configuração), título e ano são confirmados online.

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
3. ✅ Organização e renomeação de filmes (`Título (Ano)/`)
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
