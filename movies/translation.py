"""Tradução local de legendas para Português de Portugal.

* Motor separado da pesquisa (Argos Translate, local e open source).
* Tradução bloco a bloco: timestamps, numeração e estrutura nunca mudam.
* Processamento em lotes com ponto de retoma (se for interrompido, continua).
* Pós-processamento pt-BR → pt-PT (vocabulário e gerúndio).
* O ficheiro original nunca é tocado; o resultado é um ficheiro novo .pt-PT.srt.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from core.config import APP_ROOT

from .subtitles import Cue, SubtitleError, format_srt, load_cues, parse_srt, validate_srt

CHECKPOINT_DIR = APP_ROOT / "database" / "translations"
BATCH = 40


class TranslationError(Exception):
    pass


# ======================================================== pt-BR -> pt-PT
_VOCAB = [
    ("ônibus", "autocarro"), ("onibus", "autocarro"), ("trem", "comboio"), ("trens", "comboios"),
    ("celular", "telemóvel"), ("celulares", "telemóveis"), ("banheiro", "casa de banho"),
    ("geladeira", "frigorífico"), ("café da manhã", "pequeno-almoço"), ("sorvete", "gelado"),
    ("suco", "sumo"), ("xícara", "chávena"), ("tela", "ecrã"), ("usuário", "utilizador"),
    ("usuários", "utilizadores"), ("arquivo", "ficheiro"), ("arquivos", "ficheiros"),
    ("equipe", "equipa"), ("registro", "registo"), ("contato", "contacto"),
    ("contatos", "contactos"), ("fato", "facto"), ("garoto", "miúdo"), ("garota", "miúda"),
    ("garotos", "miúdos"), ("garotas", "miúdas"), ("moça", "rapariga"), ("moças", "raparigas"),
    ("legal", "fixe"), ("caminhão", "camião"), ("caminhões", "camiões"), ("grama", "relva"),
    ("açougue", "talho"), ("pedestre", "peão"), ("trem", "comboio"), ("aeromoça", "hospedeira"),
    ("terno", "fato"), ("cueca", "cuecas"), ("time", "equipa"), ("goleiro", "guarda-redes"),
    ("tô", "estou"), ("tá", "está"), ("pra", "para"), ("pro", "para o"), ("pros", "para os"),
    ("cadê", "onde está"), ("oi", "olá"), ("tchau", "adeus"), ("ótimo", "óptimo"),
    ("ótima", "óptima"), ("projeto", "projecto"), ("diretor", "director"), ("direção", "direcção"),
    ("ação", "acção"), ("ações", "acções"), ("atual", "actual"), ("exato", "exacto"),
    ("econômico", "económico"), ("gênio", "génio"), ("bebê", "bebé"), ("bebês", "bebés"),
    ("tênis", "ténis"), ("vôo", "voo"), ("crônica", "crónica"), ("fenômeno", "fenómeno"),
    ("polícia federal", "polícia judiciária"), ("parabéns pra você", "parabéns a você"),
]
_VOCAB_RE = [(re.compile(rf"(?<![\wÀ-ÿ]){re.escape(a)}(?![\wÀ-ÿ])", re.I), b) for a, b in _VOCAB]

_GER = re.compile(
    r"\b(estou|estás|está|estamos|estão|estava|estavas|estávamos|estavam|estive|esteve|"
    r"estivemos|estiveram|estarei|estará|estaremos|estarão|estaria|estariam|estar|esteja|"
    r"estejam|estivesse|fico|fica|ficamos|ficam|ficou|fiquei|ficar|continuo|continua|"
    r"continuamos|continuam|continuou|continuar|ando|anda|andamos|andam|andou|andar|vive|vivo)"
    r"(\s+)(\w+?)(ando|endo|indo|ondo)\b", re.I)
_GER_END = {"ando": "ar", "endo": "er", "indo": "ir", "ondo": "or"}


def _match_case(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def to_pt_pt(text: str) -> str:
    """Converte português do Brasil em Português de Portugal (heurístico, conservador)."""
    def ger(m):
        verb, sp, root, end = m.groups()
        inf = root + _GER_END[end.lower()]
        if root.lower() == "p" and end.lower() == "ondo":
            inf = "pôr"
        return f"{verb}{sp}a {inf}"
    out = _GER.sub(ger, text)
    for rx, repl in _VOCAB_RE:
        out = rx.sub(lambda m, r=repl: _match_case(m.group(0), r), out)
    # «você» no início de frase para tratamento por tu é arriscado; só casos seguros:
    out = re.sub(r"\bcom você\b", "consigo", out)
    out = re.sub(r"\bpara você\b", "para si", out)
    return out


# ================================================================ motores
class Engine:
    name = "base"

    def available(self) -> bool:
        return False

    def translate(self, texts: list[str], src: str) -> list[str]:
        raise NotImplementedError


class PtBrEngine(Engine):
    """pt-BR → pt-PT sem tradução automática: só adaptação."""
    name = "Adaptação pt-BR → pt-PT"

    def available(self) -> bool:
        return True

    def translate(self, texts, src):
        return [to_pt_pt(t) for t in texts]


class ArgosEngine(Engine):
    name = "Argos Translate (local)"

    def __init__(self):
        self._tr = {}

    def available(self) -> bool:
        try:
            import argostranslate.translate  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def installed_pairs(self) -> list[tuple[str, str]]:
        try:
            import argostranslate.translate as at
            langs = at.get_installed_languages()
            return [(a.code, b.code) for a in langs for b in langs
                    if a.code != b.code and a.get_translation(b) is not None]
        except Exception:  # noqa: BLE001
            return []

    def _get(self, src: str):
        if src in self._tr:
            return self._tr[src]
        import argostranslate.translate as at
        langs = {lang.code: lang for lang in at.get_installed_languages()}
        if src not in langs or "pt" not in langs:
            raise TranslationError(f"Modelo de tradução {src}→pt não instalado.")
        tr = langs[src].get_translation(langs["pt"])
        if tr is None:
            raise TranslationError(f"Modelo de tradução {src}→pt não instalado.")
        self._tr[src] = tr
        return tr

    def translate(self, texts, src):
        tr = self._get(src)
        return [to_pt_pt(tr.translate(t)) if t.strip() else t for t in texts]


def install_argos(progress: Callable[[str], None] = print, sources=("en", "es", "fr")) -> None:
    """Instala o Argos Translate e os modelos X→pt (descarga grande, uma só vez)."""
    progress("A instalar o Argos Translate (pode demorar vários minutos)…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "argostranslate"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise TranslationError("Falhou a instalação do Argos Translate:\n" + (r.stderr or "")[-800:])
    import importlib
    importlib.invalidate_caches()
    import argostranslate.package as ap
    progress("A obter a lista de modelos…")
    ap.update_package_index()
    avail = ap.get_available_packages()
    for src in sources:
        pkg = next((p for p in avail if p.from_code == src and p.to_code == "pt"), None)
        if pkg is None:
            continue
        progress(f"A descarregar o modelo {src}→pt…")
        ap.install_from_path(pkg.download())
    progress("Motor de tradução instalado.")


# ======================================================== tradução de SRT
_TAG = re.compile(r"</?[ibu]>|<font[^>]*>|</font>|\{\\[^}]*\}", re.I)


def _split_lines(text: str, width: int = 42) -> str:
    if len(text) <= width:
        return text
    words = text.split()
    best, half = None, len(text) / 2
    acc = 0
    for i, w in enumerate(words[:-1]):
        acc += len(w) + 1
        d = abs(acc - half)
        if best is None or d < best[0]:
            best = (d, i + 1)
    k = best[1] if best else len(words) // 2
    return " ".join(words[:k]) + "\n" + " ".join(words[k:])


def _prepare(text: str) -> tuple[str, bool, bool]:
    """Junta as linhas do bloco numa frase, retira etiquetas; lembra itálico e diálogo."""
    italic = bool(re.search(r"<i>", text, re.I))
    lines = [ln.strip() for ln in _TAG.sub("", text).split("\n") if ln.strip()]
    dialog = len(lines) > 1 and all(ln.startswith("-") for ln in lines)
    if dialog:
        return "\n".join(lines), italic, True
    return " ".join(lines), italic, False


def _restore(tr: str, italic: bool, dialog: bool) -> str:
    if dialog:
        lines = [ln.strip() for ln in tr.split("\n") if ln.strip()]
        lines = [ln if ln.startswith("-") else "- " + ln for ln in lines]
        out = "\n".join(lines)
    else:
        out = _split_lines(" ".join(tr.split()))
    return f"<i>{out}</i>" if italic else out


def _checkpoint_path(src: Path, src_lang: str) -> Path:
    key = hashlib.sha1(f"{src.resolve()}|{src.stat().st_size}|{src_lang}".encode()).hexdigest()[:16]
    return CHECKPOINT_DIR / f"{key}.json"


def translate_cues(cues: list[Cue], engine: Engine, src_lang: str,
                   progress: Callable[[int, int, str], None] | None = None,
                   cancelled: Callable[[], bool] | None = None,
                   checkpoint: Path | None = None) -> list[Cue]:
    progress = progress or (lambda *_: None)
    cancelled = cancelled or (lambda: False)
    done: dict[str, str] = {}
    if checkpoint and checkpoint.exists():
        try:
            done = json.loads(checkpoint.read_text(encoding="utf-8")).get("done", {})
        except (OSError, json.JSONDecodeError):
            done = {}
    prepared = [_prepare(c.text) for c in cues]
    total = len(cues)
    for start in range(0, total, BATCH):
        if cancelled():
            raise TranslationError("Tradução interrompida: continua onde parou na próxima vez.")
        idx = [i for i in range(start, min(start + BATCH, total)) if str(i) not in done]
        if idx:
            outs = engine.translate([prepared[i][0] for i in idx], src_lang)
            if len(outs) != len(idx):
                raise TranslationError("O motor devolveu um número diferente de linhas.")
            for i, o in zip(idx, outs):
                done[str(i)] = o
            if checkpoint:
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps({"done": done}, ensure_ascii=False), encoding="utf-8")
        progress(min(start + BATCH, total), total, "")
    out = []
    for i, c in enumerate(cues):
        _t, italic, dialog = prepared[i]
        out.append(Cue(c.index, c.start, c.end, _restore(done[str(i)], italic, dialog)))
    return out


def translate_subtitle_file(src: Path | str, src_lang: str, engine: Engine,
                            progress=None, cancelled=None) -> bytes:
    """Traduz um ficheiro de legenda e devolve o SRT pt-PT (UTF-8), já validado."""
    src = Path(src)
    cues, _enc = load_cues(src)
    for i, c in enumerate(cues, 1):
        c.index = i
    cp = _checkpoint_path(src, src_lang)
    out = translate_cues(cues, engine, src_lang, progress, cancelled, cp)
    # validação: mesma quantidade, mesmos tempos e numeração
    if len(out) != len(cues) or any((a.start, a.end, a.index) != (b.start, b.end, b.index)
                                    for a, b in zip(cues, out)):
        raise TranslationError("Validação falhou: a estrutura da legenda foi alterada.")
    text = format_srt(out)
    probs = [p for p in validate_srt(text) if "começa antes" not in p]
    if probs and parse_srt(text) == []:
        raise SubtitleError("Resultado inválido: " + probs[0])
    try:
        cp.unlink()
    except OSError:
        pass
    return text.encode("utf-8")


def pick_engine(src_lang: str) -> Engine:
    if src_lang in ("pt-BR", "pt"):
        return PtBrEngine()
    a = ArgosEngine()
    if not a.available():
        raise TranslationError("O motor de tradução local ainda não está instalado. "
                               "Use «Instalar motor de tradução» na página Legendas.")
    return a
