"""Legendas: leitura, codificação, conversão para SRT, validação e idioma.

Regras: o ficheiro original nunca é alterado; conversões e traduções vão
sempre para ficheiros novos. Timestamps e numeração são preservados.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class SubtitleError(Exception):
    pass


@dataclass
class Cue:
    index: int
    start: int   # milissegundos
    end: int
    text: str


# ----------------------------------------------------------------- codificação
def decode_bytes(data: bytes) -> tuple[str, str]:
    """Devolve (texto, codificação). Tenta UTF-8 e depois as codificações
    habituais em legendas portuguesas/europeias."""
    for enc in ("utf-8-sig", "utf-16"):
        if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            continue
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    for enc in ("cp1252", "iso-8859-15", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace"), "latin-1"


def read_text(path: Path | str) -> tuple[str, str]:
    return decode_bytes(Path(path).read_bytes())


# ------------------------------------------------------------------------ SRT
_TS = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
_SRT_TIME = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")


def _ms(h, m, s, ms) -> int:
    ms = (ms + "00")[:3]
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def fmt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(text: str) -> list[Cue]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for b in blocks:
        lines = [ln for ln in b.split("\n")]
        if not any(ln.strip() for ln in lines):
            continue
        i = 0
        idx = None
        if lines[0].strip().isdigit():
            idx = int(lines[0].strip())
            i = 1
        if i >= len(lines):
            continue
        m = _SRT_TIME.match(lines[i])
        if not m:
            raise SubtitleError(f"Bloco sem tempo válido: «{lines[0][:60]}»")
        g = m.groups()
        start, end = _ms(*g[:4]), _ms(*g[4:])
        body = "\n".join(lines[i + 1:]).strip("\n")
        cues.append(Cue(idx if idx is not None else len(cues) + 1, start, end, body))
    return cues


def format_srt(cues: list[Cue]) -> str:
    out = []
    for c in cues:
        out.append(f"{c.index}\n{fmt_time(c.start)} --> {fmt_time(c.end)}\n{c.text}\n")
    return "\n".join(out)


def validate_srt(text: str) -> list[str]:
    """Lista de problemas encontrados (vazia = válido)."""
    try:
        cues = parse_srt(text)
    except SubtitleError as e:
        return [str(e)]
    probs = []
    if not cues:
        return ["Sem legendas."]
    prev_end = -1
    for n, c in enumerate(cues, 1):
        if c.end < c.start:
            probs.append(f"Bloco {c.index}: fim antes do início.")
        if c.start < prev_end - 1000:
            probs.append(f"Bloco {c.index}: começa antes do anterior terminar.")
        if not c.text.strip():
            probs.append(f"Bloco {c.index}: sem texto.")
        if c.index != n:
            probs.append(f"Bloco {c.index}: numeração fora de ordem (esperado {n}).")
        prev_end = max(prev_end, c.end)
        if len(probs) > 20:
            probs.append("…")
            break
    return probs


# --------------------------------------------------------------- ASS / SSA
def _ass_time(t: str) -> int:
    h, m, rest = t.strip().split(":")
    s, cs = rest.split(".")
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int((cs + "0")[:2]) * 10


def parse_ass(text: str) -> list[Cue]:
    fmt = None
    in_events = False
    cues = []
    for line in text.replace("\r", "").split("\n"):
        st = line.strip()
        if st.startswith("["):
            in_events = st.lower() == "[events]"
            continue
        if not in_events:
            continue
        if st.lower().startswith("format:"):
            fmt = [x.strip().lower() for x in st[7:].split(",")]
        elif st.lower().startswith("dialogue:") and fmt:
            parts = st[9:].lstrip().split(",", len(fmt) - 1)
            row = dict(zip(fmt, parts))
            body = row.get("text", "")
            italic = "\\i1" in body
            body = re.sub(r"\{[^}]*\}", "", body).replace("\\N", "\n").replace("\\n", "\n")
            body = body.replace("\\h", " ").strip()
            if not body:
                continue
            if italic:
                body = f"<i>{body}</i>"
            cues.append(Cue(0, _ass_time(row["start"]), _ass_time(row["end"]), body))
    if not cues:
        raise SubtitleError("Ficheiro ASS/SSA sem diálogos legíveis.")
    cues.sort(key=lambda c: (c.start, c.end))
    for i, c in enumerate(cues, 1):
        c.index = i
    return cues


# ------------------------------------------------------------------- WebVTT
_VTT_TIME = re.compile(r"^\s*(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})")


def parse_vtt(text: str) -> list[Cue]:
    text = text.replace("\r", "").lstrip("﻿")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip("\n").split("\n")
        for i, ln in enumerate(lines):
            m = _VTT_TIME.match(ln)
            if m:
                g = m.groups()
                start = _ms(g[0] or 0, g[1], g[2], g[3])
                end = _ms(g[4] or 0, g[5], g[6], g[7])
                body = "\n".join(lines[i + 1:])
                body = re.sub(r"</?(?:c|v|lang|ruby|rt)[^>]*>", "", body).strip()
                if body:
                    cues.append(Cue(len(cues) + 1, start, end, body))
                break
    if not cues:
        raise SubtitleError("Ficheiro VTT sem legendas legíveis.")
    return cues


# --------------------------------------------------------- MicroDVD (.sub)
_MDVD = re.compile(r"^\{(\d+)\}\{(\d+)\}(.*)$")


def parse_microdvd(text: str, fps: float = 23.976) -> list[Cue]:
    cues = []
    for ln in text.replace("\r", "").split("\n"):
        m = _MDVD.match(ln.strip())
        if not m:
            continue
        a, b, body = int(m.group(1)), int(m.group(2)), m.group(3)
        if a == b == 1 and re.match(r"^\d+(\.\d+)?$", body.strip()):
            fps = float(body)  # primeira linha {1}{1}23.976 indica o fps
            continue
        body = re.sub(r"\{[^}]*\}", "", body).replace("|", "\n").strip()
        if body:
            cues.append(Cue(len(cues) + 1, round(a * 1000 / fps), round(b * 1000 / fps), body))
    if not cues:
        raise SubtitleError("Ficheiro SUB não é MicroDVD (texto). Legendas VobSub (imagem, "
                            ".sub + .idx) não podem ser convertidas para texto.")
    return cues


def load_cues(path: Path | str, fps: float | None = None) -> tuple[list[Cue], str]:
    """Lê qualquer formato suportado. Devolve (cues, codificação original)."""
    path = Path(path)
    data = path.read_bytes()
    ext = path.suffix.lower()
    if ext == ".sub" and b"\x00" in data[:2048]:
        raise SubtitleError("Legenda VobSub (imagem): não convertível para texto.")
    if ext in (".sup", ".idx"):
        raise SubtitleError("Legenda em imagem (PGS/VobSub): não convertível para texto.")
    text, enc = decode_bytes(data)
    if ext == ".srt":
        return parse_srt(text), enc
    if ext in (".ass", ".ssa"):
        return parse_ass(text), enc
    if ext == ".vtt":
        return parse_vtt(text), enc
    if ext == ".sub":
        return parse_microdvd(text, fps or 23.976), enc
    raise SubtitleError(f"Formato não suportado: {ext}")


def to_srt_bytes(cues: list[Cue]) -> bytes:
    for i, c in enumerate(cues, 1):
        c.index = i
    return format_srt(cues).encode("utf-8")


# ------------------------------------------------------------------- idioma
_STOP = {
    "pt": {"não", "que", "de", "um", "uma", "você", "isso", "está", "para", "com", "mas", "eu",
           "ele", "ela", "é", "o", "os", "as", "meu", "minha", "aqui", "muito", "bem", "sim",
           "por", "favor", "obrigado", "também", "então", "agora", "estou", "vamos", "sei"},
    "en": {"the", "you", "and", "is", "to", "what", "that", "it", "of", "i", "me", "my", "this",
           "your", "are", "have", "we", "don't", "know", "not", "be", "in", "on", "with"},
    "es": {"el", "que", "de", "y", "no", "la", "es", "lo", "en", "qué", "por", "un", "una",
           "está", "pero", "yo", "tú", "usted", "muy", "bien", "sí", "gracias", "ahora", "vamos"},
    "fr": {"le", "la", "les", "de", "et", "est", "pas", "je", "tu", "vous", "que", "qui",
           "une", "un", "ce", "ne", "oui", "non", "merci", "c'est", "il", "elle", "nous"},
    "it": {"il", "che", "di", "non", "è", "un", "una", "la", "per", "sono", "mi", "ti", "ci",
           "questo", "cosa", "bene", "grazie", "perché", "io", "lei", "lui"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ich", "du", "sie", "es", "ein", "eine",
           "zu", "was", "ja", "nein", "danke", "wir", "mit", "auf", "den"},
}
_PT_BR = {"você", "vocês", "ônibus", "trem", "celular", "banheiro", "geladeira", "garoto",
          "garota", "cara", "legal", "time", "tô", "pra", "moça", "café da manhã", "registro",
          "equipe", "usuário", "tela", "arquivo", "xícara", "sorvete", "suco"}
_PT_PT = {"estás", "tu", "vós", "telemóvel", "autocarro", "comboio", "casa de banho",
          "frigorífico", "miúdo", "miúda", "rapariga", "fixe", "equipa", "ecrã", "ficheiro",
          "pequeno-almoço", "sumo", "gelado", "chávena", "utilizador", "facto", "contacto"}


def detect_language(text: str) -> tuple[str | None, float]:
    """Idioma provável do texto de uma legenda: ('pt-PT'|'pt-BR'|'pt'|'en'|…, confiança)."""
    clean = re.sub(r"<[^>]+>|\{[^}]*\}|\d+:\d+:\d+[,.]\d+|-->", " ", text.lower())
    words = re.findall(r"[a-zà-ÿ'’]+", clean)
    if len(words) < 20:
        return None, 0.0
    counts = {k: sum(1 for w in words if w in v) for k, v in _STOP.items()}
    best = max(counts, key=counts.get)
    total = sum(counts.values()) or 1
    conf = counts[best] / total
    if counts[best] < 5:
        return None, 0.0
    if best != "pt":
        return best, conf
    br = sum(1 for w in words if w in _PT_BR) + len(re.findall(r"\b(est\w+) \w+(ando|endo|indo)\b", clean))
    pt = sum(1 for w in words if w in _PT_PT) + len(re.findall(r"\b(est\w+) a \w+(ar|er|ir)\b", clean))
    if br > pt * 1.5 and br >= 3:
        return "pt-BR", conf
    if pt > br * 1.5 and pt >= 3:
        return "pt-PT", conf
    return "pt", conf


LANG_NAMES = {"pt-PT": "Português (Portugal)", "pt-BR": "Português (Brasil)", "pt": "Português",
              "en": "Inglês", "es": "Espanhol", "fr": "Francês", "it": "Italiano", "de": "Alemão"}
