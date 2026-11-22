# Media Organizer

Aplicação desktop local, gratuita e open source (Windows e Ubuntu) para gerir uma biblioteca de **filmes** e **música** compatível com **Jellyfin**:

- organiza e renomeia em `Título (Ano)/`;
- encontra, converte e traduz legendas para **Português de Portugal**;
- obtém capas e cria NFO e `metadata.json`;
- organiza a música em `Artista/Álbum (Ano)/`;
- encontra duplicados e corre tudo automaticamente, com agendamento diário.

**Os originais são sempre preservados**: nada é apagado, tudo fica registado e pode ser revertido.

Versão: **1.0.0**. A especificação completa está em [`docs/ESPECIFICACAO.txt`](docs/ESPECIFICACAO.txt).

---

## Instalar

### Windows

1. Nesta página, carregue no botão verde **Code** → **Download ZIP**.
2. Extraia o ZIP para uma pasta, por exemplo `Documentos\MediaOrganizer`.
3. Faça **duplo clique em `instalar.bat`**. Se o Windows mostrar "O Windows protegeu o seu PC", carregue em **Mais informações** → **Executar mesmo assim**.
4. No fim aparece o atalho **Media Organizer** no Ambiente de Trabalho e no Menu Iniciar.

O instalador instala o Python e o FFmpeg (pelo `winget`) se faltarem, e cria o ambiente da aplicação.
Se a aplicação não abrir, faça duplo clique em `arrancar_com_consola.bat` para ver o erro.

### Ubuntu

```bash
cd ~
git clone https://github.com/jfcarvalho1/Legendas_Automaticas.git MediaOrganizer
bash MediaOrganizer/instalar.sh
```

### Actualizar

- Windows: descarregue o ZIP de novo, extraia por cima da pasta antiga e corra `instalar.bat`.
- Ubuntu: `cd ~/MediaOrganizer && git pull && bash instalar.sh`.

A base de dados, os registos, os backups e a quarentena não são tocados pela actualização.

---

## Primeiros passos

1. Na primeira vez, indique a pasta dos **filmes** e a da **música**.
2. **Filmes** → **Analisar agora**. Faz o inventário e não altera nada.
3. **Organizar** → separador **Filmes** → **Analisar e propor** → reveja → **Aplicar seleccionados**.
4. **Legendas** → **Procurar online** e/ou **Traduzir para pt-PT**.
5. **Capas** → **Processar seleccionados / em falta**.
6. **Música** → **Analisar agora** → **Organizar música…** → **Aplicar seleccionadas**.
7. **Duplicados** → **Analisar duplicados**.
8. **Automatização** → escolha o modo → **Executar agora**, ou **Activar** o agendamento diário.

Serviços opcionais (todos gratuitos; configurar em **Configuração**):

| Serviço | Para quê | Como obter |
|---|---|---|
| TMDb | confirmar título/ano, capas, sinopse, NFO completo | themoviedb.org → Definições → API |
| OpenSubtitles | procurar e descarregar legendas | conta em opensubtitles.com + chave em opensubtitles.com/consumers |
| Argos Translate | traduzir legendas sem internet | botão **Instalar motor de tradução** na página Legendas (~1 GB) |
| MusicBrainz | completar anos de álbuns | não precisa de conta |
| Jellyfin | actualizar a biblioteca no fim | Painel do Jellyfin → Chaves de API (na página Automatização) |

Sem nenhum destes serviços, a aplicação continua a funcionar com os dados dos próprios ficheiros.

---

## O que faz cada módulo

### Filmes: organizar e renomear

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

- Na pasta final **só ficam** o vídeo, as legendas, a capa, o NFO e o `metadata.json`. O resto (`.txt`, samples, `.nfo` de grupos de release, links, imagens extra) vai para a quarentena `Restos_Organizacao`.
- As legendas que estão em **subpastas** (`Subs/`, `Legendas/`, `Subs/2_English.srt`…) são recolhidas e ficam com o idioma no nome (`.pt-PT`, `.pt-BR`, `.pt`, `.en`, `.forced`…).
- Casos incertos (sem ano) nunca são alterados sem confirmação: duplo clique para corrigir.
- Duas versões do mesmo filme ficam juntas: `Gladiator (2000).mkv` e `Gladiator (2000) - 720p.mkv`.
- Nunca escreve por cima de nada. Cada lote é reversível com **Reverter último lote**.

### Legendas e tradução

- **Prioridade:** pt-PT → pt-BR → outros idiomas.
- **Formatos:** SRT, ASS, SSA, VTT e SUB (MicroDVD) são convertidos para SRT UTF-8. As legendas em imagem (VobSub/PGS) são assinaladas, porque não é possível convertê-las em texto.
- **Idioma:** é detectado pelo nome do ficheiro e, se não houver, pelo próprio texto, distinguindo pt-PT de pt-BR.
- **OpenSubtitles:** a pesquisa é feita pelo hash do vídeo, depois pelo IMDb/TMDb e por fim pelo título e ano. Respeita os limites diários do serviço.
- **Tradução local:** com o Argos Translate, bloco a bloco. Timestamps e numeração nunca mudam. Se for interrompida, continua onde parou.
- **pt-BR → pt-PT:** adaptação automática de vocabulário ("celular" → "telemóvel", "ônibus" → "autocarro"…) e do gerúndio ("está falando" → "está a falar"). Não precisa de internet.
- A legenda original nunca é substituída: o resultado vai sempre para um ficheiro novo.

### Capas, NFO e metadata.json

- Poster do TMDb (de preferência em português, boa resolução), guardado como `cover.jpg`.
- Para evitar homónimos, o ano tem de coincidir.
- O NFO é compatível com Jellyfin e Kodi: título, título original, ano, sinopse, géneros, realizador, elenco, IMDb, TMDb e dados técnicos.
- O `metadata.json` aceita campos extra: os que já lá estiverem são mantidos.
- Capas e ficheiros existentes são preservados. Com **Substituir**, os antigos vão primeiro para a quarentena.

### Música

- Fica em `Biblioteca/Artista/Álbum (Ano)/01 - Faixa.flac`. Nos álbuns com vários discos fica `1-01 - Faixa`.
- Por defeito **copia** da pasta de origem e valida a cópia por SHA256. O original fica intacto. A qualidade nunca é alterada.
- Cada álbum recebe `cover.jpg`, a partir da imagem da pasta ou da capa embutida.
- Faixas sem tags são deduzidas do nome e da pasta e ficam por confirmar. As correcções vão para as tags da cópia.
- Duplicados exactos não são copiados duas vezes. Versões diferentes (outro formato ou bitrate) são preservadas.

### Duplicados

- **Exactos:** mesmo tamanho e mesmo SHA256 (filmes, música, legendas, capas, auxiliares).
- **Prováveis:** mesmo filme (título e ano), ou mesma faixa (artista, título e duração ±3 s).
- **Versões diferentes** (ao vivo, remix, remaster, 720p/1080p…) são assinaladas para preservar.
- Mostra o espaço potencialmente libertável e uma recomendação para cada grupo.
- **Nunca apaga.** Os ficheiros marcados vão para `Quarentena/Duplicados`.

### Automatização

| Modo | O que faz |
|---|---|
| Análise | inventário, propostas e relatórios; não altera nada |
| Automático | aplica só o que é seguro (confiança alta), adapta pt-BR → pt-PT, procura legendas, cria NFO, JSON e capas, organiza a música, actualiza o Jellyfin |
| Reparação | completa NFO, JSON e capas em falta, converte legendas, reanalisa ficheiros inválidos |
| Recuperação | marca tarefas interrompidas, põe cópias parciais na quarentena, retoma traduções |

- **Agendamento diário:** Agendador de Tarefas do Windows ou cron no Ubuntu. O computador tem de estar ligado à hora marcada.
- **Linha de comandos:** `app.py --auto --mode automatico`.

### Segurança

- A **análise só lê**. A **eliminação automática está sempre desactivada**.
- Cada operação tem um identificador `OP_AAAAMMDD_NNN` e fica registada na base de dados e em `logs/operations.jsonl`.
- Antes de mover: verifica a origem e o destino (nunca sobrescreve) e as permissões. Entre discos, copia e valida por SHA256.
- **A quarentena não é eliminação.** Cada ficheiro tem um manifesto JSON (nome e local originais, data, motivo, operação) e pode ser reposto no **Histórico**.
- Backups automáticos da base de dados em `backups/` (os últimos 10).
- Ficheiros de 0 bytes: assinalados e preservados, sem tentativas de processamento.

### Relatórios

Em HTML, CSV, JSON e TXT: filmes, música, erros, operações, duplicados, legendas e ficheiros em falta. Os HTML podem ser guardados em PDF pela opção Imprimir do navegador.

---

## Estrutura

```
app.py            arranque (interface ou --auto)
core/             base de dados, inventário, segurança, operações, organizador,
                  duplicados, automatização, agendamento, backups, relatórios
movies/           identificação, legendas, tradução, capas, NFO, metadados
music/            tags, organização da música
integrations/     TMDb, OpenSubtitles, MusicBrainz, Jellyfin
interface/        janelas (PySide6)
tests/            testes automáticos
database/ logs/ reports/ backups/ quarantine/   dados locais (fora do Git)
```

## Testes

```bash
.venv/bin/python -m unittest discover -s tests -v        # Ubuntu
.venv\Scripts\python -m unittest discover -s tests -v     # Windows
```

## Limitações conhecidas

- A tradução automática (Argos) é boa para perceber o filme, mas não iguala uma legenda feita por pessoas. Por isso, a ordem de prioridade é sempre: legenda pt-PT humana, depois pt-BR adaptada, e só por fim tradução automática.
- As legendas em imagem (VobSub `.sub/.idx`, PGS `.sup`) não são convertidas. Seria preciso OCR, que não está incluído.
- A escrita de tags na música precisa do Mutagen, que o instalador inclui.
- A IA local (Ollama) não está integrada nesta versão.

Licença: MIT.
